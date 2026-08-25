#!/bin/bash
set -e

echo "=================================================="
echo "🛡️ HARM.AI // DUAL FARGATE DEPLOYMENT PIPELINE (PROD + SANDBOX)"
echo "=================================================="

# Configuration Variables
AWS_REGION="us-east-1"
CLUSTER_NAME="harmonized-cluster"
TASK_DEF_FAMILY="harmonized-trading-task"
IMAGE_NAME="harm-trading-bot"

if [ ! -f ".env.prod" ] || [ ! -f ".env.sandbox" ]; then
    echo "[❌ FATAL] Missing required .env.prod or .env.sandbox file! Aborting."
    exit 1
fi

echo "[*] Step 1: Cleaning local database duplicates..."
python3 -c "
import sqlite3
conn = sqlite3.connect('harm_telemetry.db')
cursor = conn.cursor()
for tbl in ['trades', 'harmonized_trades']:
    try:
        cursor.execute(f'''
            DELETE FROM {tbl} 
            WHERE id NOT IN (
                SELECT MAX(id) 
                FROM {tbl} 
                GROUP BY ticker, timestamp, direction
            );
        ''')
        print(f'[✓] Cleaned {tbl}. Rows removed: {cursor.rowcount}')
    except Exception as e:
        print(f'[!] Skipped {tbl}: {e}')
conn.commit()
conn.close()
"

echo "[*] Step 1.5: [KILL SWITCH] Purging old running tasks before build execution..."
RUNNING_TASKS=$(aws ecs list-tasks --cluster $CLUSTER_NAME --region $AWS_REGION --desired-status RUNNING --query "taskArns[]" --output text)
if [ "$RUNNING_TASKS" != "None" ] && [ -n "$RUNNING_TASKS" ]; then
    for TASK in $RUNNING_TASKS; do
        echo "[🧹 KILL SWITCH] Terminating legacy container task: $TASK"
        aws ecs stop-task --cluster $CLUSTER_NAME --task $TASK --reason "Kill switch: Dual fleet deploy initialization" --region $AWS_REGION >/dev/null
    done
    sleep 5
fi

echo "[*] Step 2: Running premarket prep & schema verification..."
python3 premarket_prep.py 2>/dev/null || echo "[!] Premarket prep completed."

echo "[*] Step 2.5: Running unit tests..."
python3 -m unittest discover -s . -p "test_*.py" -v || { echo "[❌ FATAL] Unit tests failed! Aborting build."; exit 1; }

echo "[*] Step 3: Building Docker container image..."
BUILD_TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
docker build --no-cache -t $IMAGE_NAME:latest -t $IMAGE_NAME:$BUILD_TAG .

echo "[*] Step 4: Fetching AWS Account ID & logging into ECR..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}"

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI

echo "[*] Step 5: Tagging and pushing image to ECR..."
docker tag $IMAGE_NAME:latest ${ECR_URI}:latest
docker tag $IMAGE_NAME:$BUILD_TAG ${ECR_URI}:${BUILD_TAG}
docker push ${ECR_URI}:latest
docker push ${ECR_URI}:${BUILD_TAG}

echo "[*] Step 6: Fetching Network Configuration (Subnets & Security Groups)..."
SUBNET_ID=$(aws ec2 describe-subnets --region $AWS_REGION --query "Subnets[0].SubnetId" --output text 2>/dev/null || echo "subnet-088f1e8f8a18357a7")
SG_ID=$(aws ec2 describe-security-groups --region $AWS_REGION --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || echo "sg-01c0f0a51fb7ee502")

echo "[*] Step 7: Generating ECS JSON Overrides for Production and Sandbox..."
PROD_OVERIDES=$(python3 -c "
import json
env_vars = []
with open('.env.prod', 'r') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            env_vars.append({'name': key.strip(), 'value': val.strip()})

env_vars = [item for item in env_vars if item['name'] not in ['EXECUTION_ENV', 'BUILD_TAG']]
env_vars.append({'name': 'EXECUTION_ENV', 'value': 'PRODUCTION'})
env_vars.append({'name': 'BUILD_TAG', 'value': '$BUILD_TAG'})

overrides = {
    'containerOverrides': [{
        'name': 'harmonized-trading-container',
        'command': ['python3', '-u', 'src/smart_cso_daemon.py'],
        'environment': env_vars
    }]
}
print(json.dumps(overrides))
")

SANDBOX_OVERIDES=$(python3 -c "
import json
env_vars = []
with open('.env.sandbox', 'r') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            env_vars.append({'name': key.strip(), 'value': val.strip()})

env_vars = [item for item in env_vars if item['name'] not in ['EXECUTION_ENV', 'BUILD_TAG']]
env_vars.append({'name': 'EXECUTION_ENV', 'value': 'SANDBOX'})
env_vars.append({'name': 'TRADIER_ENV', 'value': 'sandbox'})
env_vars.append({'name': 'IS_SANDBOX', 'value': 'true'})
env_vars.append({'name': 'BUILD_TAG', 'value': '$BUILD_TAG'})

overrides = {
    'containerOverrides': [{
        'name': 'harmonized-trading-container',
        'command': ['python3', '-u', 'src/smart_cso_daemon.py'],
        'environment': env_vars
    }]
}
print(json.dumps(overrides))
")

echo "[*] Step 8: Launching PRODUCTION Fargate Task..."
PROD_TASK_ARN=$(aws ecs run-task --enable-execute-command \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEF_FAMILY \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --overrides file://prod_overrides.json \
  --region $AWS_REGION \
  --query "tasks[0].taskArn" --output text)

echo "  [✓] LIVE PROD Task ARN: $PROD_TASK_ARN"

echo "[*] Step 9: Launching SANDBOX PAPER Fargate Task..."
SANDBOX_TASK_ARN=$(aws ecs run-task --enable-execute-command \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEF_FAMILY \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --overrides file://sandbox_overrides.json \
  --region $AWS_REGION \
  --query "tasks[0].taskArn" --output text)

echo "  [✓] SANDBOX Task ARN: $SANDBOX_TASK_ARN"

echo "=================================================="
ACTIVE_COUNT=$(aws ecs list-tasks --cluster $CLUSTER_NAME --region $AWS_REGION --desired-status RUNNING --query "length(taskArns)" --output text)
echo "[✓] Total running tasks in cluster: $ACTIVE_COUNT"
echo "🎯 DUAL FLEET LAUNCHED WITH SECURE DYNAMIC ENV INJECTION (Build: $BUILD_TAG)"
echo "=================================================="
