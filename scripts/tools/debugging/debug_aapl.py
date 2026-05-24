import sqlite3
import re

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("AAPL LONG forecasts with exit_stop:")
cur.execute("""
    SELECT method, model, exit_stop, stop_loss, entry_price
    FROM logs 
    WHERE ticker = 'NASDAQ:AAPL' AND side = 'LONG' AND status = 'NEW'
    AND exit_stop IS NOT NULL
    LIMIT 10
""")

for row in cur.fetchall():
    exit_stop = row['exit_stop']
    nums = re.findall(r'[\d.]+', str(exit_stop))
    
    print(f"\n{row['method']} | {row['model']}")
    print(f"  exit_stop: '{exit_stop}'")
    print(f"  nums: {nums}")
    
    if nums:
        first = float(nums[0])
        last = float(nums[-1])
        print(f"  nums[0] = {first}")
        print(f"  nums[-1] = {last}")
        print(f"  entry_price: {row['entry_price']}")
        
        # Which is correct stop price?
        entry = row['entry_price'] or 262
        if first < entry * 0.5:  # Too low
            print(f"  -> {first} seems WRONG (too low)")
        else:
            print(f"  -> {first} seems OK")

conn.close()
