#!/bin/bash
set -e
echo "=================================================="
echo "🔴 HARM.AI // PRODUCTION FLEET DEPLOYMENT"
echo "=================================================="

AWS_REGION="us-east-1"
CLUSTER_NAME="harmonized-cluster"
TASK_DEF_FAMILY="harmonized-trading-task"
IMAGE_NAME="harm-trading-bot"

python3 -m unittest discover -s . -p "test_*.py" -v || { echo "[❌ FATAL] Unit tests failed! Aborting."; exit 1; }

BUILD_TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
docker build -t $IMAGE_NAME:latest -t $IMAGE_NAME:$BUILD_TAG .

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}"

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI
docker tag $IMAGE_NAME:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

SUBNET_ID=$(aws ec2 describe-subnets --region $AWS_REGION --query "Subnets[0].SubnetId" --output text)
SG_ID=$(aws ec2 describe-security-groups --region $AWS_REGION --query "SecurityGroups[0].GroupId" --output text)

PROD_OVERIDES=$(python3 -c "
import json
env_vars = []
with open('.env.prod', 'r') as f:
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
  --overrides "$PROD_OVERIDES" \
  --region $AWS_REGION

echo "[✓ PRODUCTION FLEET LIVE]"
