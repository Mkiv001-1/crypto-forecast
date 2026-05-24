import urllib.request
import json

req = urllib.request.Request(
    'http://127.0.0.1:8000/system-log?lines=50',
    headers={'X-API-Key': 'CHANGE-ME-TO-A-STRONG-SECRET-KEY'}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read().decode())
for line in data.get('lines', []):
    if '2026-05-05' in line and ('Оценка' in line or 'Поиск' in line or 'NEW' in line or 'evaluate' in line.lower()):
        print(line)
