#!/bin/bash
TARGET_ENV="$(echo "${1:-SANDBOX}" | tr '[:lower:]' '[:upper:]')"
CLUSTER="harmonized-cluster"
REGION="us-east-1"

echo "[*] Searching for existing $TARGET_ENV tasks in '$CLUSTER' to tear down..."

TASKS=$(aws ecs list-tasks --cluster $CLUSTER --region $REGION --query "taskArns[]" --output text 2>/dev/null)

if [ -z "$TASKS" ] || [ "$TASKS" == "None" ]; then
  echo "[-] No active tasks found."
  exit 0
fi

for TASK_ARN in $TASKS; do
  [ "$TASK_ARN" == "None" ] && continue
  
  DESC=$(aws ecs describe-tasks --cluster $CLUSTER --tasks "$TASK_ARN" --region $REGION 2>/dev/null)
  
  # Search both base task def and launch overrides for PRODUCTION
  IF_PROD=$(echo "$DESC" | jq -r '(.tasks[0].containers[0].environment[]?, .tasks[0].overrides.containerOverrides[0].environment[]?) | select(.name=="EXECUTION_ENV") | .value' 2>/dev/null | grep -i "PRODUCTION")
  GROUP=$(echo "$DESC" | jq -r '.tasks[0].group // ""')

  if [ -n "$IF_PROD" ] || [[ "$GROUP" == *"prod"* ]]; then
    TASK_ENV="PRODUCTION"
  else
    TASK_ENV="SANDBOX"
  fi

  if [ "$TASK_ENV" == "$TARGET_ENV" ]; then
    TASK_ID="${TASK_ARN##*/}"
    echo "[🧹] Stopping stale $TARGET_ENV task: $TASK_ID"
    aws ecs stop-task --cluster $CLUSTER --task "$TASK_ARN" --reason "Tear down $TARGET_ENV task" --region $REGION >/dev/null
  fi
done
