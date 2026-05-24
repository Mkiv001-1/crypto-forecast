import sqlite3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
from core.sqlite_manager import SQLiteManager
from core.consensus import calculate_consensus

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== Debugging stop_loss extraction ===")
print()

# Check raw data from logs
cur.execute("""
    SELECT ticker, method, model, side, exit_stop, stop_loss, entry_price
    FROM logs 
    WHERE side IN ('LONG', 'SHORT') 
    AND (exit_stop IS NOT NULL OR stop_loss IS NOT NULL)
    LIMIT 5
""")

for row in cur.fetchall():
    print(f"Row: {row['ticker']} | {row['method']} | {row['model']}")
    print(f"  exit_stop text: '{row['exit_stop']}'")
    print(f"  stop_loss num:  {row['stop_loss']}")
    print(f"  entry_price:    {row['entry_price']}")
    
    # Test parsing
    stop = row['stop_loss']
    if not stop and row['exit_stop']:
        import re
        nums = re.findall(r'[\d.]+', str(row['exit_stop']))
        if nums:
            try:
                stop = float(nums[-1])
                print(f"  PARSED stop:    {stop}")
            except:
                print(f"  PARSE FAILED")
        else:
            print(f"  NO NUMBERS in exit_stop")
    else:
        print(f"  Using existing stop_loss: {stop}")
    print()

# Now test full consensus calculation for one ticker
cur.execute("""
    SELECT ticker, method, model, side, confidence, exit_target, exit_stop, stop_loss, entry_price
    FROM logs 
    WHERE ticker = 'NASDAQ:TQQQ' AND status = 'NEW'
""")

forecasts = []
for row in cur.fetchall():
    # Parse target
    target = None
    if row['exit_target']:
        import re
        nums = re.findall(r'[\d.]+', str(row['exit_target']))
        if nums:
            try:
                target = float(nums[-1])
            except:
                pass
    
    # Parse stop
    stop = row['stop_loss']
    if not stop and row['exit_stop']:
        import re
        nums = re.findall(r'[\d.]+', str(row['exit_stop']))
        if nums:
            try:
                stop = float(nums[-1])
            except:
                pass
    
    if row['side'] in ('LONG', 'SHORT'):
        forecasts.append({
            'model': row['model'],
            'method': row['method'],
            'side': row['side'],
            'confidence': row['confidence'] or 50,
            'exit_target': row['exit_target'],
            'stop_loss': stop,
            'entry_limit_price': row['entry_price'],
        })

print(f"=== Consensus calculation for TQQQ ({len(forecasts)} forecasts) ===")
if forecasts:
    cons = calculate_consensus(forecasts)
    print(f"Signal: {cons['signal']}")
    print(f"Confidence: {cons['confidence']:.1f}%")
    print(f"Target: {cons['target_price']}")
    print(f"Stop: {cons['stop_loss']}")
    print(f"Entry: {cons['entry_limit_price']}")
    
    # Check individual forecasts
    print()
    print("Individual LONG/SHORT forecasts with stops:")
    for f in forecasts[:5]:
        print(f"  {f['method']}/{f['model']}: side={f['side']}, stop={f['stop_loss']}, entry={f['entry_limit_price']}")

conn.close()
