import json
import subprocess
import os

aws_acct = subprocess.check_output("aws sts get-caller-identity --query Account --output text", shell=True).decode().strip()
image_uri = f"{aws_acct}.dkr.ecr.us-east-1.amazonaws.com/harm-trading-bot:v1.0.24"

sandbox_token = "CvtMHhNSylWy5KLTTvU29UD3zMdb"
prod_token = "fyR75AACwlIYhkMyev1doRh6gnSr"
try:
    with open(".env.prod", "r") as f:
        for line in f:
            if line.startswith("TRADIER_TOKEN=") or line.startswith("TRADIER_ACCESS_TOKEN="):
                prod_token = line.split("=", 1)[1].strip().strip('"\'')
except Exception:
    pass

prod_env = [
    {"name": "EXECUTION_ENV", "value": "PROD"},
    {"name": "TRADIER_ENV", "value": "PROD"},
    {"name": "TENANT_ID", "value": "COMPANY_A_PROD"},
    {"name": "TRADIER_BASE_URL", "value": "https://api.tradier.com/v1"},
    {"name": "TRADIER_ACCOUNT_ID", "value": "6YB87601"},
    {"name": "TRADIER_TOKEN", "value": prod_token},
    {"name": "TRADIER_ACCESS_TOKEN", "value": prod_token},
    {"name": "ACTIVE_TICKERS", "value": "IWM,F,PLTR"},
    {"name": "PYTHONUNBUFFERED", "value": "1"}
]

sandbox_env = [
    {"name": "EXECUTION_ENV", "value": "SANDBOX"},
    {"name": "TRADIER_ENV", "value": "SANDBOX"},
    {"name": "TENANT_ID", "value": "COMPANY_A_SANDBOX"},
    {"name": "TRADIER_BASE_URL", "value": "https://sandbox.tradier.com/v1"},
    {"name": "TRADIER_ACCOUNT_ID", "value": "VA83416608"},
    {"name": "TRADIER_TOKEN", "value": sandbox_token},
    {"name": "TRADIER_SANDBOX_TOKEN", "value": sandbox_token},
    {"name": "TRADIER_ACCESS_TOKEN", "value": sandbox_token},
    {"name": "ACTIVE_TICKERS", "value": "NVDA,AAPL,TSLA,PLTR,RIVN,SOFI,F,AAL"},
    {"name": "PYTHONUNBUFFERED", "value": "1"}
]

base_td = {
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "256",
    "memory": "512",
    "executionRoleArn": f"arn:aws:iam::{aws_acct}:role/ecsTaskExecutionRole",
    "taskRoleArn": f"arn:aws:iam::{aws_acct}:role/ecsTaskExecutionRole",
    "containerDefinitions": [{
        "name": "harmonized-trading-container",
        "image": image_uri,
        "essential": True,
        "portMappings": [{"containerPort": 8080, "hostPort": 8080, "protocol": "tcp"}],
        "logConfiguration": {"logDriver": "awslogs", "options": {"awslogs-group": "/ecs/harmonized-trading-task", "awslogs-region": "us-east-1", "awslogs-stream-prefix": "ecs"}}
    }]
}

prod_td = {**base_td, "family": "harmonized-task-prod"}
sandbox_td = {**base_td, "family": "harmonized-task-sandbox"}
prod_td["containerDefinitions"][0]["environment"] = prod_env
sandbox_td["containerDefinitions"][0]["environment"] = sandbox_env

with open("/tmp/td_prod.json", "w") as f: json.dump(prod_td, f)
with open("/tmp/td_sandbox.json", "w") as f: json.dump(sandbox_td, f)

subprocess.run("aws ecs register-task-definition --cli-input-json file:///tmp/td_prod.json", shell=True, stdout=subprocess.DEVNULL)
subprocess.run("aws ecs register-task-definition --cli-input-json file:///tmp/td_sandbox.json", shell=True, stdout=subprocess.DEVNULL)

subnet = subprocess.check_output("aws ec2 describe-subnets --query 'Subnets[0].SubnetId' --output text", shell=True).decode().strip()
sg = subprocess.check_output("aws ec2 describe-security-groups --query 'SecurityGroups[0].GroupId' --output text", shell=True).decode().strip()
net_config = f"awsvpcConfiguration={{subnets=[{subnet}],securityGroups=[{sg}],assignPublicIp=ENABLED}}"

prod_override = json.dumps({"containerOverrides": [{"name": "harmonized-trading-container", "environment": prod_env}]})
sandbox_override = json.dumps({"containerOverrides": [{"name": "harmonized-trading-container", "environment": sandbox_env}]})

p_arn = subprocess.check_output(["aws", "ecs", "run-task", "--cluster", "harmonized-cluster", "--task-definition", "harmonized-task-prod", "--launch-type", "FARGATE", "--network-configuration", net_config, "--overrides", prod_override, "--query", "tasks[0].taskArn", "--output", "text"]).decode().strip()
s_arn = subprocess.check_output(["aws", "ecs", "run-task", "--cluster", "harmonized-cluster", "--task-definition", "harmonized-task-sandbox", "--launch-type", "FARGATE", "--network-configuration", net_config, "--overrides", sandbox_override, "--query", "tasks[0].taskArn", "--output", "text"]).decode().strip()

print(f"[✓ PROD TASK SUBMITTED]: {p_arn}")
print(f"[✓ SANDBOX TASK SUBMITTED]: {s_arn}")
