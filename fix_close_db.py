with open('dashboard_server.py', 'r') as f:
    content = f.read()

# Replace the broken KeyConditionExpression query with a clean scan for active trades
old_query_block = """    # 1. Fetch trade
    trades_res = trades_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('tenant_id').eq(tenant_id)
    )"""

new_scan_block = """    # 1. Fetch trade cleanly via scan
    from datetime import datetime
    trades_res = trades_table.scan(
        FilterExpression="ticker = :t AND (#s = :act OR exit_status = :act)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":t": ticker_to_close, ":act": "ACTIVE"}
    )"""

if old_query_block in content:
    content = content.replace(old_query_block, new_scan_block)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Cleanly patched trades_table.query -> scan in dashboard_server.py!')
else:
    print('[!] Query block pattern not found or already patched.')
