"""Debug AAPL stop parsing step by step."""
import sqlite3
import re

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("AAPL LONG forecasts - step by step parsing:")
print()

cur.execute("""
    SELECT method, model, side, entry_price, exit_stop, stop_loss
    FROM logs 
    WHERE ticker = 'NASDAQ:AAPL' AND side = 'LONG' AND status = 'NEW'
    LIMIT 5
""")

for row in cur.fetchall():
    print(f"Row: {row['method']} | {row['model']}")
    print(f"  entry_price: {row['entry_price']} (type: {type(row['entry_price'])})")
    print(f"  exit_stop: {repr(row['exit_stop'])}")
    print(f"  stop_loss (DB): {row['stop_loss']}")
    
    # Simulate parsing from recalculate_consensus.py
    stop_loss = row['stop_loss']
    if not stop_loss and row['exit_stop']:
        nums = re.findall(r'[\d.]+', str(row['exit_stop']))
        print(f"  nums from exit_stop: {nums}")
        
        if nums:
            try:
                entry = row['entry_price'] or 0
                print(f"  entry used: {entry}")
                
                if len(nums) >= 2:
                    stop_loss = float(nums[0])
                    print(f"  -> Using nums[0] (two numbers): {stop_loss}")
                elif len(nums) == 1 and entry > 0:
                    pct = float(nums[0])
                    stop_loss = round(entry * (1 - pct/100), 2)
                    print(f"  -> Calculated from {pct}%: {stop_loss}")
                else:
                    stop_loss = float(nums[0])
                    print(f"  -> Using nums[0] (fallback): {stop_loss}")
            except Exception as e:
                print(f"  -> Parse error: {e}")
    
    print(f"  FINAL stop_loss: {stop_loss}")
    print()

conn.close()
