import sqlite3
import sys
sys.path.insert(0, 'scripts')
from core.consensus import calculate_consensus

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
    SELECT method, model, side, confidence, exit_target, exit_stop, stop_loss, entry_price
    FROM logs WHERE ticker = 'NASDAQ:TQQQ' AND status = 'NEW'
""")

forecasts = []
for row in cur.fetchall():
    target = None
    if row['exit_target']:
        import re
        nums = re.findall(r'[\d.]+', str(row['exit_target']))
        if nums:
            try:
                target = float(nums[-1])
            except:
                pass
    
    stop = row['stop_loss']
    if not stop and row['exit_stop']:
        import re
        nums = re.findall(r'[\d.]+', str(row['exit_stop']))
        if nums:
            try:
                stop = float(nums[0])
            except:
                pass
    
    forecasts.append({
        'method': row['method'],
        'model': row['model'],
        'side': row['side'] or 'NEUTRAL',
        'confidence': row['confidence'] or 50,
        'exit_target': row['exit_target'],
        'stop_loss': stop,
        'entry_limit_price': row['entry_price'],
    })

print(f'TQQQ: {len(forecasts)} forecasts')
longs = [f for f in forecasts if f['side'] == 'LONG']
print(f'  LONG: {len(longs)}')
print(f'  LONG with stop_loss: {len([f for f in longs if f["stop_loss"]])}')

if longs:
    stops = [f['stop_loss'] for f in longs if f['stop_loss']]
    entries = [f['entry_limit_price'] for f in longs if f['entry_limit_price']]
    print(f'  Stop values: {stops[:5]}...')
    print(f'  Entry values: {entries[:5]}...')
    
    cons = calculate_consensus(forecasts)
    print(f'\nConsensus:')
    print(f'  signal: {cons["signal"]}')
    print(f'  confidence: {cons["confidence"]}%')
    print(f'  target_price: {cons["target_price"]}')
    print(f'  stop_loss: {cons["stop_loss"]}')
    print(f'  entry_limit_price: {cons["entry_limit_price"]}')

conn.close()
