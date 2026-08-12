#!/bin/bash
set -e

echo "=========================================================="
echo "🦅 HARM.AI // PREFLIGHT INTEGRITY & UNIT TEST GATEWAY"
echo "=========================================================="

echo "[1/4] Initializing & Migrating SQLite Database Schemas..."
python3 rebuild_db.py
python3 preboot_db_fix.py

echo "[2/4] Running System Preflight Integrity Guard..."
python3 preflight_guard.py --update-checksums

echo "[3/4] Running DynamoDB-Monitor Parity & GSG/MTTP Unit Test..."
python3 test_gex_monitor_sync.py
if [ $? -ne 0 ]; then
    echo "❌ CRITICAL: GSG/MTTP Sync Unit Test Failed! Aborting Container Build."
    exit 1
fi

echo "[4/4] Running GSG Guard Unit Test..."
python3 test_live_gsg_guard.py
if [ $? -ne 0 ]; then
    echo "❌ CRITICAL: GSG Guard Unit Test Failed! Aborting Container Build."
    exit 1
fi

echo "=========================================================="
echo "[✓] ALL PASSED: All startup scripts and unit tests completed successfully."
echo "=========================================================="

echo ""
echo "=========================================================="
echo "⚡ HARMONIZED AI // FARGATE CONTAINER REBUILD & DEPLOY"
echo "=========================================================="

# 1. Resolve AWS Environment Variables
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text --region $AWS_REGION)
CLUSTER_NAME="harmonized-cluster"
TASK_DEF="harmonized-trading-task"

# 2. Resolve ECR Repository Name
ECR_REPO=$(aws ecr describe-repositories --query "repositories[0].repositoryName" --output text --region $AWS_REGION 2>/dev/null)
if [ -z "$ECR_REPO" ] || [ "$ECR_REPO" == "None" ]; then
    ECR_REPO="harmonized-ai"
fi

ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"

echo "[*] Account ID: $AWS_ACCOUNT_ID"
echo "[*] ECR Target: $ECR_URI"

# 3. Authenticate Docker with ECR
echo "[1/4] Authenticating with AWS ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# 4. Build Docker Image
echo "[2/4] Building Docker Image (Packaging suite)..."
docker build -t "$ECR_REPO:latest" .

# 5. Tag and Push to ECR
echo "[3/4] Tagging & Pushing Image to ECR..."
docker tag "$ECR_REPO:latest" "$ECR_URI"
docker push "$ECR_URI"

echo "[✓] Docker image successfully pushed to ECR!"

# 6. Fetch Subnet and Security Group IDs
SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=default-for-az,Values=true" --query "Subnets[0].SubnetId" --output text --region $AWS_REGION)
if [ -z "$SUBNET_ID" ] || [ "$SUBNET_ID" == "None" ]; then
    SUBNET_ID=$(aws ec2 describe-subnets --query "Subnets[0].SubnetId" --output text --region $AWS_REGION)
fi

SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=default" --query "SecurityGroups[0].GroupId" --output text --region $AWS_REGION)
if [ -z "$SG_ID" ] || [ "$SG_ID" == "None" ]; then
    SG_ID=$(aws ec2 describe-security-groups --query "SecurityGroups[0].GroupId" --output text --region $AWS_REGION)
fi

# 7. Spin up Task on Fargate (Spot with On-Demand Fallback)
echo "[4/4] Launching Task on Fargate..."
TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER_NAME" \
  --task-definition "$TASK_DEF" \
  --capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1 \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --query "tasks[0].taskArn" \
  --output text \
  --region $AWS_REGION 2>/dev/null)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" == "None" ]; then
    echo "[!] Spot unavailable. Falling back to Standard Fargate..."
    TASK_ARN=$(aws ecs run-task \
      --cluster "$CLUSTER_NAME" \
      --task-definition "$TASK_DEF" \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
      --query "tasks[0].taskArn" \
      --output text \
      --region $AWS_REGION)
fi

echo "[✓] Task Provisioned: $TASK_ARN"
echo "[*] Waiting for ENI & Public IP assignment..."

# 8. Resolve ENI & Public IP
ENI_ID=""
while [ -z "$ENI_ID" ] || [ "$ENI_ID" == "None" ]; do
  sleep 3
  ENI_ID=$(aws ecs describe-tasks --cluster "$CLUSTER_NAME" --tasks "$TASK_ARN" --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text --region $AWS_REGION 2>/dev/null)
done

PUBLIC_IP=""
while [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" == "None" ]; do
  sleep 2
  PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids "$ENI_ID" --query "NetworkInterfaces[0].Association.PublicIp" --output text --region $AWS_REGION 2>/dev/null)
done

echo "=========================================================="
echo "🦅 HARMONIZED SUITE LIVE ON FARGATE"
echo "🌐 DASHBOARD URL: http://$PUBLIC_IP:8080"
echo "=========================================================="
