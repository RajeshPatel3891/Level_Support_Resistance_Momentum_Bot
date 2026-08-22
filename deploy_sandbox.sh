#!/bin/bash
set -e
echo "=================================================="
echo "🟡 HARM.AI // SANDBOX FLEET DEPLOYMENT"
echo "=================================================="

AWS_REGION="us-east-1"
CLUSTER_NAME="harmonized-cluster"
TASK_DEF_FAMILY="harmonized-trading-task"
IMAGE_NAME="harm-trading-bot"

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}"

SUBNET_ID=$(aws ec2 describe-subnets --region $AWS_REGION --query "Subnets[0].SubnetId" --output text)
SG_ID=$(aws ec2 describe-security-groups --region $AWS_REGION --query "SecurityGroups[0].GroupId" --output text)

SANDBOX_OVERIDES=$(python3 -c "
import json
env_vars = []
with open('.env.sandbox', 'r') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env_vars.append({'name': k.strip(), 'value': v.strip()})

overrides = {
    'containerOverrides': [{
        'name': 'harmonized-trading-container',
        'command': ['python3', '-u', 'src/smart_cso_daemon.py'],
        'environment': env_vars
    }]
}
print(json.dumps(overrides))
")

aws ecs run-task --enable-execute-command \
  --cluster $CLUSTER_NAME \
  --task-definition $TASK_DEF_FAMILY \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --overrides "$SANDBOX_OVERIDES" \
  --region $AWS_REGION

echo "[✓ SANDBOX FLEET LIVE]"
