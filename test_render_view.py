import asyncio
from unittest.mock import MagicMock
from dashboard_server import index_view

mock_request = MagicMock()
res = asyncio.run(index_view(mock_request))
html = res.body.decode('utf-8')

print("=" * 60)
print(f"📊 HTML PAGE RENDER LENGTH: {len(html)} bytes")
print("=" * 60)

for line in html.splitlines():
    if any(k in line for k in ["deployed_capital", "DEPLOYED", "AAL", "PLTR", "INTC"]):
        print(f"  • {line.strip()[:110]}")

print("=" * 60)
