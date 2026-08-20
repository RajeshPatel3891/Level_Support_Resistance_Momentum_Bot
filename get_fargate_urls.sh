#!/bin/bash
CLUSTER="harmonized-cluster"
REGION="us-east-1"

echo "================================================="
echo "🚀 HARM.AI CLUSTER TASK & DASHBOARD DISCOVERY"
echo "================================================="

TASKS=$(aws ecs list-tasks --cluster $CLUSTER --region $REGION --desired-status RUNNING --query 'taskArns[]' --output text 2>/dev/null)

if [ -z "$TASKS" ] || [ "$TASKS" == "None" ]; then
  echo "[-] No active tasks found in '$CLUSTER'."
  echo "================================================="
  exit 0
fi

# Robust Production Environment Evaluator
is_production_task() {
  local desc="$1"
  local env_str
  env_str=$(echo "$desc" | jq -r '
    (.tasks[0].containers[].environment[]? // empty),
    (.tasks[0].overrides.containerOverrides[].environment[]? // empty),
    (.tasks[0].containers[].overrides.environment[]? // empty)
    | "\(.name)=\(.value)"' 2>/dev/null)
  local group
  group=$(echo "$desc" | jq -r '.tasks[0].group // ""' 2>/dev/null)

  # Check for explicit PROD environment variables or PROD tickers (HOOD/MARA/UBER)
  if echo "$env_str" | grep -iE "EXECUTION_ENV=.*PROD|APP_ENV=.*PROD|HOOD|MARA|UBER" >/dev/null 2>&1 || [[ "$group" == *"prod"* ]]; then
    return 0
  else
    return 1
  fi
}

# --- STEP 1: AUTO-PRUNE STALE DUPLICATE TASKS ---
PROD_TASKS=()
SANDBOX_TASKS=()

for T_ARN in $TASKS; do
  DESC=$(aws ecs describe-tasks --cluster $CLUSTER --tasks "$T_ARN" --region $REGION 2>/dev/null)
  if is_production_task "$DESC"; then
    PROD_TASKS+=("$T_ARN")
  else
    SANDBOX_TASKS+=("$T_ARN")
  fi
done

# Prune duplicate PROD tasks (Keep newest)
if [ ${#PROD_TASKS[@]} -gt 1 ]; then
  NEWEST_PROD=$(aws ecs describe-tasks --cluster $CLUSTER --tasks "${PROD_TASKS[@]}" --region $REGION --query "sort_by(tasks, &createdAt)[-1].taskArn" --output text 2>/dev/null)
  for t in "${PROD_TASKS[@]}"; do
    if [ "$t" != "$NEWEST_PROD" ]; then
      echo "[🔌 AUTO-PRUNE] Stopping stale PRODUCTION task: ${t##*/}"
      aws ecs stop-task --cluster $CLUSTER --task "$t" --region $REGION > /dev/null 2>&1
    fi
  done
fi

# Prune duplicate SANDBOX tasks (Keep newest)
if [ ${#SANDBOX_TASKS[@]} -gt 1 ]; then
  NEWEST_SANDBOX=$(aws ecs describe-tasks --cluster $CLUSTER --tasks "${SANDBOX_TASKS[@]}" --region $REGION --query "sort_by(tasks, &createdAt)[-1].taskArn" --output text 2>/dev/null)
  for t in "${SANDBOX_TASKS[@]}"; do
    if [ "$t" != "$NEWEST_SANDBOX" ]; then
      echo "[🔌 AUTO-PRUNE] Stopping stale SANDBOX task: ${t##*/}"
      aws ecs stop-task --cluster $CLUSTER --task "$t" --region $REGION > /dev/null 2>&1
    fi
  done
fi

# --- STEP 2: DISPLAY ACTIVE TASKS & DASHBOARD URLS ---
UPDATED_TASKS=$(aws ecs list-tasks --cluster $CLUSTER --region $REGION --desired-status RUNNING --query 'taskArns[]' --output text 2>/dev/null)

for TASK_ARN in $UPDATED_TASKS; do
  TASK_ID="${TASK_ARN##*/}"
  DESC=$(aws ecs describe-tasks --cluster $CLUSTER --tasks "$TASK_ARN" --region $REGION 2>/dev/null)
  STATUS=$(echo "$DESC" | jq -r '.tasks[0].lastStatus // "UNKNOWN"')

  if is_production_task "$DESC"; then
    MODE="PROD"
  else
    MODE="SANDBOX"
  fi

  ENI_ID=$(echo "$DESC" | jq -r '.tasks[0].attachments[0].details[]? | select(.name=="networkInterfaceId") | .value')

  if [ -n "$ENI_ID" ] && [ "$ENI_ID" != "null" ] && [ "$ENI_ID" != "None" ]; then
    PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids "$ENI_ID" --region $REGION --query "NetworkInterfaces[0].Association.PublicIp" --output text 2>/dev/null)

    if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "null" ] && [ "$PUBLIC_IP" != "None" ]; then
      echo "[✓] [$MODE] Status: $STATUS | Task ID: $TASK_ID | Dashboard: http://$PUBLIC_IP:8080/"
    else
      echo "[⏳] [$MODE] Status: $STATUS | Task ID: $TASK_ID | Network Interface attaching (IP pending)..."
    fi
  else
    echo "[⏳] [$MODE] Status: $STATUS | Task ID: $TASK_ID | Provisioning container..."
  fi
done
echo "================================================="
