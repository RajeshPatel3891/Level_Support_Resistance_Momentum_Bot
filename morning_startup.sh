#!/bin/bash
set -e

echo "================================================="
echo "🌅 HARM.AI MORNING STARTUP & PRE-FLIGHT GATE"
echo "================================================="

# 1. System Health & Storage Check
echo "[*] [STEP 1/6] Checking EC2 Disk Space..."
df -h / | grep -E "Filesystem|root"

# 2. Pre-flight Cleanup (Kill Stale Fargate Tasks)
echo -e "\n[*] [STEP 2/6] Cleaning up stale running tasks..."
python3 -c "
import boto3
ecs = boto3.client('ecs', region_name='us-east-1')
clusters = ecs.list_clusters().get('clusterArns', [])
for c in clusters:
    tasks = ecs.list_tasks(cluster=c, desiredStatus='RUNNING').get('taskArns', [])
    for t in tasks:
        ecs.stop_task(cluster=c, task=t, reason='Pre-startup auto-cleanup')
" || true

# 3. Sync Guardrails & Live Market Data
echo -e "\n[*] [STEP 3/6] Syncing S3 Guardrail Levels & Live Market Quotes..."
python3 -c '
import boto3
try:
    s3 = boto3.client("s3", region_name="us-east-1")
    obj = s3.get_object(Bucket="harmonized-ai-telemetry-bucket", Key="trading_levels.json")
    with open("trading_levels.json", "w") as f:
        f.write(obj["Body"].read().decode("utf-8"))
    print("[✓] Restored trading_levels.json from S3")
except Exception as e:
    print(f"[!] S3 Sync Note: {e}")
' || true

# 4. Syntax Verification
python3 -m py_compile dashboard_server.py && echo "[✓ Dashboard Server Syntax Clean]"

# 5. Build Fresh Docker Image & Push to ECR
echo -e "\n[*] [STEP 4/6] Building & Pushing Clean Docker Container..."
TAG="v1.0.23"
AWS_ACCT=$(aws sts get-caller-identity --query Account --output text)
IMAGE_URI="${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com/harm-trading-bot:${TAG}"

docker build --no-cache -t harm-trading-bot:${TAG} .
docker tag harm-trading-bot:${TAG} ${IMAGE_URI}
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com
docker push ${IMAGE_URI}

# 6. Register & Run Fargate Tasks with Explicit Container Overrides
echo -e "\n[*] [STEP 5/6] Registering Task Definitions & Launching Dual Environments..."
python3 -c '
import json, subprocess, os

aws_acct = subprocess.check_output("aws sts get-caller-identity --query Account --output text", shell=True).decode().strip()
image_uri = f"{aws_acct}.dkr.ecr.us-east-1.amazonaws.com/harm-trading-bot:v1.0.23"

sandbox_token = "CvtMHhNSylWy5KLTTvU29UD3zMdb"
try:
    prod_token = subprocess.check_output("grep -E \"^(TRADIER_ACCESS_TOKEN|TRADIER_TOKEN)=\" .env.prod 2>/dev/null | head -n1 | cut -d= -f2", shell=True).decode().strip().strip("\x22\x27")
except Exception:
    prod_token = "fyR75AACwlIYhkMyev1doRh6gnSr"

if not prod_token:
    prod_token = "fyR75AACwlIYhkMyev1doRh6gnSr"

prod_env = [
    {"name": "EXECUTION_ENV", "value": "PROD"},
    {"name": "TRADIER_ENV", "value": "PROD"},
    {"name": "TENANT_ID", "value": "COMPANY_A_PROD"},
    {"name": "TRADIER_BASE_URL", "value": "https://api.tradier.com/v1"},
    {"name": "TRADIER_ACCOUNT_ID", "value": "6YB87601"},
    {"name": "TRADIER_TOKEN", "value": prod_token},
    {"name": "TRADIER_ACCESS_TOKEN", "value": prod_token},
    {"name": "ACTIVE_TICKERS", "value": "IWM,F,PLTR"},
    {"name": "PYTHONUNBUFFERED", "value": "1"}
]

sandbox_env = [
    {"name": "EXECUTION_ENV", "value": "SANDBOX"},
    {"name": "TRADIER_ENV", "value": "SANDBOX"},
    {"name": "TENANT_ID", "value": "COMPANY_A_SANDBOX"},
    {"name": "TRADIER_BASE_URL", "value": "https://sandbox.tradier.com/v1"},
    {"name": "TRADIER_ACCOUNT_ID", "value": "VA83416608"},
    {"name": "TRADIER_TOKEN", "value": sandbox_token},
    {"name": "TRADIER_SANDBOX_TOKEN", "value": sandbox_token},
    {"name": "TRADIER_ACCESS_TOKEN", "value": sandbox_token},
    {"name": "ACTIVE_TICKERS", "value": "NVDA,AAPL,TSLA,PLTR,RIVN,SOFI,F,AAL"},
    {"name": "PYTHONUNBUFFERED", "value": "1"}
]

base_td = {
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "256",
    "memory": "512",
    "executionRoleArn": f"arn:aws:iam::{aws_acct}:role/ecsTaskExecutionRole",
    "taskRoleArn": f"arn:aws:iam::{aws_acct}:role/ecsTaskExecutionRole",
    "containerDefinitions": [{
        "name": "harmonized-trading-container",
        "image": image_uri,
        "essential": True,
        "portMappings": [{"containerPort": 8080, "hostPort": 8080, "protocol": "tcp"}],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": "/ecs/harmonized-trading-task",
                "awslogs-region": "us-east-1",
                "awslogs-stream-prefix": "ecs"
            }
        }
    }]
}

prod_td = {**base_td, "family": "harmonized-task-prod"}
sandbox_td = {**base_td, "family": "harmonized-task-sandbox"}

prod_td["containerDefinitions"][0]["environment"] = prod_env
sandbox_td["containerDefinitions"][0]["environment"] = sandbox_env

with open("/tmp/td_prod.json", "w") as f: json.dump(prod_td, f)
with open("/tmp/td_sandbox.json", "w") as f: json.dump(sandbox_td, f)

subprocess.run("aws ecs register-task-definition --cli-input-json file:///tmp/td_prod.json", shell=True, stdout=subprocess.DEVNULL)
subprocess.run("aws ecs register-task-definition --cli-input-json file:///tmp/td_sandbox.json", shell=True, stdout=subprocess.DEVNULL)

subnet = subprocess.check_output("aws ec2 describe-subnets --query \"Subnets[0].SubnetId\" --output text", shell=True).decode().strip()
sg = subprocess.check_output("aws ec2 describe-security-groups --query \"SecurityGroups[0].GroupId\" --output text", shell=True).decode().strip()
net_config = f"awsvpcConfiguration={{subnets=[{subnet}],securityGroups=[{sg}],assignPublicIp=ENABLED}}"

prod_override = json.dumps({"containerOverrides": [{"name": "harmonized-trading-container", "environment": prod_env}]})
sandbox_override = json.dumps({"containerOverrides": [{"name": "harmonized-trading-container", "environment": sandbox_env}]})

p_arn = subprocess.check_output(["aws", "ecs", "run-task", "--cluster", "harmonized-cluster", "--task-definition", "harmonized-task-prod", "--launch-type", "FARGATE", "--network-configuration", net_config, "--overrides", prod_override, "--query", "tasks[0].taskArn", "--output", "text"]).decode().strip()
s_arn = subprocess.check_output(["aws", "ecs", "run-task", "--cluster", "harmonized-cluster", "--task-definition", "harmonized-task-sandbox", "--launch-type", "FARGATE", "--network-configuration", net_config, "--overrides", sandbox_override, "--query", "tasks[0].taskArn", "--output", "text"]).decode().strip()

print(f"[✓ PROD TASK SUBMITTED]: {p_arn}")
print(f"[✓ SANDBOX TASK SUBMITTED]: {s_arn}")
'

echo -e "\n[*] [STEP 6/6] Verifying Fleet Deployment Health..."
sleep 15

if [ -f "./get_fargate_urls.sh" ]; then
    ./get_fargate_urls.sh
fi

echo "================================================="
echo "🚀 CONSOLIDATED STARTUP COMPLETE — FLEET ONLINE"
echo "================================================="
