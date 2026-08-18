#!/bin/bash
CLUSTER="harmonized-cluster"
REGION="us-east-1"

echo "================================================="
echo "🚀 HARM.AI CLUSTER TASK & DASHBOARD DISCOVERY"
echo "================================================="

TASKS=$(aws ecs list-tasks --cluster $CLUSTER --region $REGION --query 'taskArns[]' --output text 2>/dev/null)

if [ -z "$TASKS" ] || [ "$TASKS" == "None" ]; then
  echo "[-] No active tasks found in '$CLUSTER'."
  echo "================================================="
  exit 0
fi

for TASK_ARN in $TASKS; do
  TASK_ID="${TASK_ARN##*/}"
  
  DESC=$(aws ecs describe-tasks --cluster $CLUSTER --tasks "$TASK_ARN" --region $REGION 2>/dev/null)
  STATUS=$(echo "$DESC" | jq -r '.tasks[0].lastStatus // "UNKNOWN"')
  
  # Search both base task def and launch overrides for PRODUCTION flag
  IF_PROD=$(echo "$DESC" | jq -r '(.tasks[0].containers[0].environment[]?, .tasks[0].overrides.containerOverrides[0].environment[]?) | select(.name=="EXECUTION_ENV") | .value' 2>/dev/null | grep -i "PRODUCTION")
  GROUP=$(echo "$DESC" | jq -r '.tasks[0].group // ""')

  if [ -n "$IF_PROD" ] || [[ "$GROUP" == *"prod"* ]]; then
    MODE="PRODUCTION"
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
