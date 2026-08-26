#!/bin/bash
set -e

CLUSTER="harmonized-cluster"
TASK_DEF="harmonized-trading-task"
CONTAINER_NAME="harmonized-trading-container"
SUBNET=$(aws ec2 describe-subnets --query 'Subnets[0].SubnetId' --output text)
SG_ID=$(aws ec2 describe-security-groups --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo 'sg-01c0f0a51fb7ee502')

# Production Secrets
PROD_TOKEN=$(grep -E '^(TRADIER_ACCESS_TOKEN|TRADIER_TOKEN)=' .env.prod | head -n1 | cut -d '=' -f2 | tr -d '"'\''\r')
PROD_ACCT=$(grep -E '^TRADIER_ACCOUNT_ID=' .env.prod | head -n1 | cut -d '=' -f2 | tr -d '"'\''\r')
if [ -z "$PROD_ACCT" ]; then PROD_ACCT="6YB87601"; fi

# Sandbox Secrets
SB_TOKEN=$(grep -E '^(TRADIER_ACCESS_TOKEN|TRADIER_TOKEN|TRADIER_SANDBOX_TOKEN)=' .env.sandbox | head -n1 | cut -d '=' -f2 | tr -d '"'\''\r')
SB_ACCT=$(grep -E '^TRADIER_ACCOUNT_ID=' .env.sandbox | head -n1 | cut -d '=' -f2 | tr -d '"'\''\r')
if [ -z "$SB_ACCT" ]; then SB_ACCT="VA83416608"; fi
if [ -z "$SB_TOKEN" ]; then SB_TOKEN="hcY1t0sY8RZmcsfVjQCA41ecAkFT"; fi

# 1. Write Production JSON Override
cat << JSON_EOF > prod_overrides.json
{
  "containerOverrides": [
    {
      "name": "$CONTAINER_NAME",
      "environment": [
        {"name": "EXECUTION_ENV", "value": "PROD"},
        {"name": "TRADIER_ENV", "value": "PROD"},
        {"name": "TENANT_ID", "value": "COMPANY_A_PROD"},
        {"name": "ACTIVE_TICKERS", "value": "F,SOFI,AAL,RIVN"},
        {"name": "TRADIER_BASE_URL", "value": "https://api.tradier.com/v1"},
        {"name": "TRADIER_ACCOUNT_ID", "value": "$PROD_ACCT"},
        {"name": "TRADIER_TOKEN", "value": "$PROD_TOKEN"},
        {"name": "TRADIER_ACCESS_TOKEN", "value": "$PROD_TOKEN"}
      ]
    }
  ]
}
JSON_EOF

# 2. Write Sandbox JSON Override
cat << JSON_EOF > sandbox_overrides.json
{
  "containerOverrides": [
    {
      "name": "$CONTAINER_NAME",
      "environment": [
        {"name": "EXECUTION_ENV", "value": "SANDBOX"},
        {"name": "TRADIER_ENV", "value": "SANDBOX"},
        {"name": "TENANT_ID", "value": "COMPANY_A_SANDBOX"},
        {"name": "ACTIVE_TICKERS", "value": "NVDA,AAPL,TSLA,PLTR,RIVN,SOFI,F,AAL"},
        {"name": "TRADIER_BASE_URL", "value": "https://sandbox.tradier.com/v1"},
        {"name": "TRADIER_ACCOUNT_ID", "value": "$SB_ACCT"},
        {"name": "TRADIER_TOKEN", "value": "$SB_TOKEN"},
        {"name": "TRADIER_ACCESS_TOKEN", "value": "$SB_TOKEN"}
      ]
    }
  ]
}
JSON_EOF

echo "=========================================================="
echo "🛡️ DEPLOYING BULLETPROOF DUAL FARGATE FLEET"
echo "   PROD ACCT: $PROD_ACCT | SANDBOX ACCT: $SB_ACCT"
echo "=========================================================="

echo "[1/2] Launching LIVE PRODUCTION Container..."
PROD_TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --overrides file://prod_overrides.json \
  --query "tasks[0].taskArn" --output text)

echo "  [✓] LIVE PROD Task ARN: $PROD_TASK_ARN"

echo "[2/2] Launching SANDBOX PAPER Container..."
SANDBOX_TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --overrides file://sandbox_overrides.json \
  --query "tasks[0].taskArn" --output text)

echo "  [✓] SANDBOX PAPER Task ARN: $SANDBOX_TASK_ARN"

echo "=========================================================="
echo "🎯 DUAL FLEET LAUNCHED WITH FULL STATE ISOLATION"
echo "=========================================================="
