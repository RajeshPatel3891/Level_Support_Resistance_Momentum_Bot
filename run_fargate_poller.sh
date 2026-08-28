#!/bin/bash

CLUSTER_NAME="harmonized-cluster"
REGION="us-east-1"
TARGET_ENV="${1:-SANDBOX}"

echo "[*] Locating active Fargate task in cluster: ${CLUSTER_NAME} (${TARGET_ENV})..."

TASK_ARN=$(aws ecs list-tasks --cluster "$CLUSTER_NAME" --region "$REGION" --desired-status RUNNING --query "taskArns[0]" --output text)

if [ "$TASK_ARN" == "None" ] || [ -z "$TASK_ARN" ]; then
  echo "[!] Error: No running Fargate tasks found in cluster '$CLUSTER_NAME'."
  exit 1
fi

TASK_ID="${TASK_ARN##*/}"
echo "[✓] Connected to Fargate Task: ${TASK_ID}"

# Dynamically extract container name from task definition
CONTAINER_NAME=$(aws ecs describe-tasks --cluster "$CLUSTER_NAME" --tasks "$TASK_ID" --region "$REGION" --query "tasks[0].containers[0].name" --output text)
echo "[✓] Target Container: ${CONTAINER_NAME}"

B64_SCRIPT=$(base64 -w 0 remote_pnl.py)

aws ecs execute-command \
  --cluster "$CLUSTER_NAME" \
  --task "$TASK_ID" \
  --container "$CONTAINER_NAME" \
  --region "$REGION" \
  --interactive \
  --command "sh -c 'echo $B64_SCRIPT | base64 -d > /tmp/remote_pnl.py && python3 /tmp/remote_pnl.py $TARGET_ENV'"
