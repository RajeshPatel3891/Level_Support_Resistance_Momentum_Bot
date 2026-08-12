import re

file_path = "dashboard_server.py"

with open(file_path, "r") as f:
    code = f.read()

# 1. Strip out hardcoded active position mock arrays
code = re.sub(
    r'if\s+not\s+(?:items|active_trades|positions):\s*(?:items|active_trades|positions)\s*=\s*\[[\s\S]*?\]',
    'if not items: items = []',
    code
)

# 2. Inject live DynamoDB query handler into /api/active_positions
live_api_code = """
@app.route('/api/active_positions', methods=['GET'])
@app.route('/api/positions', methods=['GET'])
def get_live_active_positions():
    import boto3, os
    from boto3.dynamodb.conditions import Attr
    from flask import jsonify

    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        
        # Query true ACTIVE trades from DynamoDB
        res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        items = res.get('Items', [])
        
        return jsonify({'status': 'success', 'active_positions': items, 'count': len(items)}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e), 'active_positions': []}), 500
"""

if "get_live_active_positions" not in code:
    code += "\n" + live_api_code

with open(file_path, "w") as f:
    f.write(code)

print("[✓] Successfully purged mock fallbacks and connected live DynamoDB queries in dashboard_server.py!")
