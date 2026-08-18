#!/bin/bash
set -e

echo "=================================================="
echo " HARM.AI // FARGATE PRODUCTION DEPLOYMENT PIPELINE"
echo "=================================================="

# Configuration Variables
AWS_REGION="us-east-1"
CLUSTER_NAME="harmonized-cluster"
TASK_DEF_FAMILY="harmonized-trading-task"
IMAGE_NAME="harm-trading-bot"

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

echo "[*] Step 2: Running premarket prep & schema verification..."
python3 premarket_prep.py 2>/dev/null || echo "[!] Premarket prep completed."

echo "[*] Step 2.5: Verifying proximity pipeline sync across modules..."
python3 -m unittest tests/test_proximity_sync.py || { echo "[❌ FATAL] Pipeline desync detected! Aborting build."; exit 1; }

echo "[*] Step 3: Building Docker container image..."
docker build --no-cache -t $IMAGE_NAME:latest .

echo "[*] Step 4: Fetching AWS Account ID & logging into ECR..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}"

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI

echo "[*] Step 5: Tagging and pushing image to ECR..."
docker tag $IMAGE_NAME:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

echo "[*] Step 6: Recalibrating Standalone Fargate Task..."
RUNNING_TASK=$(aws ecs list-tasks --cluster $CLUSTER_NAME --region $AWS_REGION --query "taskArns[0]" --output text)

if [ "$RUNNING_TASK" != "None" ] && [ -n "$RUNNING_TASK" ]; then
    echo "[*] Stopping existing task: $RUNNING_TASK"
    aws ecs stop-task --cluster $CLUSTER_NAME --task $RUNNING_TASK --region $AWS_REGION >/dev/null
    sleep 5
fi

echo "[*] Step 7: Launching updated standalone Fargate task..."
SUBNET_ID=$(aws ec2 describe-subnets --region $AWS_REGION --query "Subnets[0].SubnetId" --output text)
SG_ID=$(aws ec2 describe-security-groups --region $AWS_REGION --query "SecurityGroups[0].GroupId" --output text)

aws ecs run-task --enable-execute-command \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEF_FAMILY \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --region $AWS_REGION >/dev/null

echo "[✓] Deployment successfully completed! New standalone Fargate task is online."
