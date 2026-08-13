#!/bin/bash
set -e

CLUSTER="harmonized-cluster"
TASK_DEF="harmonized-trading-task"
SUBNET="subnet-002aa08c02709142d"

echo "=========================================================="
echo "🛡️ DEPLOYING DUAL FARGATE FLEET (DYNAMIC ENV INJECTION)"
echo "=========================================================="

CONTAINER_NAME=$(aws ecs describe-task-definition \
  --task-definition "$TASK_DEF" \
  --region us-east-1 \
  --query "taskDefinition.containerDefinitions[0].name" \
  --output text)

# 1. LIVE PRODUCTION
if [ -f .env.prod ]; then
  PROD_TENANT=$(bash -c 'source .env.prod && echo "$TENANT_ID"')
  PROD_TICKERS=$(bash -c 'source .env.prod && echo "$ACTIVE_TICKERS"')
  PROD_URL=$(bash -c 'source .env.prod && echo "$TRADIER_BASE_URL"')
  PROD_ACCT=$(bash -c 'source .env.prod && echo "$TRADIER_ACCOUNT_ID"')
  PROD_TOKEN=$(bash -c 'source .env.prod && echo "$TRADIER_TOKEN"')
else
  echo "⛔ Missing .env.prod file!" && exit 1
fi

echo "[1/2] Launching LIVE PRODUCTION Container ($PROD_TICKERS)..."
PROD_TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "'"$CONTAINER_NAME"'",
      "environment": [
        {"name": "TENANT_ID", "value": "'"$PROD_TENANT"'"},
        {"name": "ACTIVE_TICKERS", "value": "'"$PROD_TICKERS"'"},
        {"name": "TRADIER_BASE_URL", "value": "'"$PROD_URL"'"},
        {"name": "TRADIER_ACCOUNT_ID", "value": "'"$PROD_ACCT"'"},
        {"name": "TRADIER_TOKEN", "value": "'"$PROD_TOKEN"'"}
      ]
    }]
  }' --query "tasks[0].taskArn" --output text)

echo "  [✓] LIVE PROD Task ARN: $PROD_TASK_ARN"

# 2. SANDBOX PAPER
if [ -f .env.sandbox ]; then
  SANDBOX_TENANT=$(bash -c 'source .env.sandbox && echo "$TENANT_ID"')
  SANDBOX_TICKERS=$(bash -c 'source .env.sandbox && echo "$ACTIVE_TICKERS"')
  SANDBOX_URL=$(bash -c 'source .env.sandbox && echo "$TRADIER_BASE_URL"')
  SANDBOX_ACCT=$(bash -c 'source .env.sandbox && echo "$TRADIER_ACCOUNT_ID"')
  SANDBOX_TOKEN=$(bash -c 'source .env.sandbox && echo "$TRADIER_TOKEN"')
else
  echo "⛔ Missing .env.sandbox file!" && exit 1
fi

echo "[2/2] Launching SANDBOX PAPER Container ($SANDBOX_TICKERS)..."
SANDBOX_TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "'"$CONTAINER_NAME"'",
      "environment": [
        {"name": "TENANT_ID", "value": "'"$SANDBOX_TENANT"'"},
        {"name": "ACTIVE_TICKERS", "value": "'"$SANDBOX_TICKERS"'"},
        {"name": "TRADIER_BASE_URL", "value": "'"$SANDBOX_URL"'"},
        {"name": "TRADIER_ACCOUNT_ID", "value": "'"$SANDBOX_ACCT"'"},
        {"name": "TRADIER_TOKEN", "value": "'"$SANDBOX_TOKEN"'"}
      ]
    }]
  }' --query "tasks[0].taskArn" --output text)

echo "  [✓] SANDBOX PAPER Task ARN: $SANDBOX_TASK_ARN"

echo "=========================================================="
echo "🎯 DUAL FLEET LAUNCHED WITH SECURE DYNAMIC ENV INJECTION"
echo "=========================================================="
