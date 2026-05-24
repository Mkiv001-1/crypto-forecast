import urllib.request
import json
req = urllib.request.Request(
    'http://127.0.0.1:8000/logs?status=NEW&limit=5',
    headers={'X-API-Key': 'CHANGE-ME-TO-A-STRONG-SECRET-KEY'}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read().decode())
for item in data.get('items', []):
    print(f"ID: {item.get('id')}, Ticker: {item.get('ticker')}, Created: {item.get('created_at')}, Forecast: {item.get('forecast_date')}, Side: {item.get('side')}")
print(f"\nTotal NEW: {data.get('total')}")
