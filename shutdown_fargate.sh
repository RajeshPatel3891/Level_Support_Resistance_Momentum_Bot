#!/bin/bash

echo "================================================="
echo "🌙 SHUTTING DOWN ALL FARGATE TASKS"
echo "================================================="

# 1. Stop individual running tasks
TASKS=$(aws ecs list-tasks --cluster harmonized-cluster --region us-east-1 --query 'taskArns[]' --output text 2>/dev/null)

if [ -n "$TASKS" ] && [ "$TASKS" != "None" ]; then
    for task in $TASKS; do
        echo "[*] Stopping task: ${task##*/}"
        aws ecs stop-task --cluster harmonized-cluster --task "$task" --region us-east-1 >/dev/null
    done
    echo "[✓] All active tasks stopped."
else
    echo "[-] No running tasks found in cluster."
fi

# 2. Set ECS Service desired-counts to 0
aws ecs update-service --cluster harmonized-cluster --service harmonized-container-prod-service --desired-count 0 --region us-east-1 2>/dev/null || true
aws ecs update-service --cluster harmonized-cluster --service harmonized-container-sandbox-service --desired-count 0 --region us-east-1 2>/dev/null || true

echo "================================================="
echo "💤 CLUSTER SCALED TO 0 — ALL COMPUTE PAUSED"
echo "================================================="
