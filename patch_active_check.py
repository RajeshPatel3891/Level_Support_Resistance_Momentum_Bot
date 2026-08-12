file_path = "./src/smart_cso_injector.py"

with open(file_path, "r") as f:
    code = f.read()

# Replace SQLite active trade check with DynamoDB check
old_check = "def is_active_position_exists(ticker):"
new_check = """
def is_active_position_exists(ticker):
    import boto3, os
    from boto3.dynamodb.conditions import Attr
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan(FilterExpression=Attr('ticker').eq(ticker) & Attr('exit_status').eq('ACTIVE'))
        return len(res.get('Items', [])) > 0
    except Exception as e:
        print(f'[!] DynamoDB active check warning: {e}')
        return False
"""

if "def is_active_position_exists(ticker):" in code and "boto3.resource('dynamodb'" not in code.split("def is_active_position_exists")[1].split("def ")[0]:
    code = code.replace(
        code.split("def is_active_position_exists")[1].split("return")[0] + "return" + code.split("def is_active_position_exists")[1].split("return")[1].split("\n")[0],
        new_check
    )
    with open(file_path, "w") as f:
        f.write(code)
    print(f"[✓] Successfully updated active position check to query DynamoDB in {file_path}!")
else:
    print(f"[✓] {file_path} is using live DynamoDB position checks.")
