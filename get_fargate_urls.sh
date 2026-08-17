#!/bin/bash

echo "================================================="
echo "🚀 HARM.AI CLUSTER TASK & DASHBOARD DISCOVERY"
echo "================================================="

TASKS=$(aws ecs list-tasks --cluster harmonized-cluster --region us-east-1 --query 'taskArns[]' --output text 2>/dev/null)

if [ -n "$TASKS" ] && [ "$TASKS" != "None" ]; then
    for task in $TASKS; do
        # Extract Task Metadata
        eni=$(aws ecs describe-tasks --cluster harmonized-cluster --tasks "$task" --region us-east-1 --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text 2>/dev/null) 
        group=$(aws ecs describe-tasks --cluster harmonized-cluster --tasks "$task" --region us-east-1 --query 'tasks[0].group' --output text 2>/dev/null)
        status=$(aws ecs describe-tasks --cluster harmonized-cluster --tasks "$task" --region us-east-1 --query 'tasks[0].lastStatus' --output text 2>/dev/null)

        # Environment Classifier
        ENV_LABEL="SANDBOX"
        if [[ "$group" == *"prod"* ]]; then
            ENV_LABEL="PROD"
        fi

        if [ -n "$eni" ] && [ "$eni" != "None" ]; then
            ip=$(aws ec2 describe-network-interfaces --network-interface-ids "$eni" --region us-east-1 --query 'NetworkInterfaces[0].Association.PublicIp' --output text 2>/dev/null)
            if [ -n "$ip" ] && [ "$ip" != "None" ]; then
                echo "[✓] [${ENV_LABEL}] Status: ${status} | Task ID: ${task##*/} | Dashboard: http://${ip}:8080/"
            else
                echo "[⏳] [${ENV_LABEL}] Status: ${status} | Network Interface attaching (IP pending)..."
            fi
        else
            echo "[⏳] [${ENV_LABEL}] Status: ${status} | Provisioning container..."
        fi
    done
else
    echo "[-] No active tasks found in 'harmonized-cluster'."
fi
echo "================================================="
