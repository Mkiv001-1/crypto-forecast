import sqlite3
import re

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("AAPL LONG forecasts - exit_stop format:")
cur.execute("""
    SELECT method, model, exit_stop, stop_loss, entry_price
    FROM logs 
    WHERE ticker = 'NASDAQ:AAPL' AND side = 'LONG' AND status = 'NEW'
    LIMIT 10
""")

for row in cur.fetchall():
    exit_stop = row['exit_stop']
    nums = re.findall(r'[\d.]+', str(exit_stop))
    entry = row['entry_price'] or 262
    
    print(f"\n{row['method']} | {row['model']}")
    print(f"  exit_stop: {repr(exit_stop)}")
    print(f"  nums: {nums}")
    print(f"  entry_price: {entry}")
    
    if len(nums) == 1:
        # Only one number - likely percentage
        pct = float(nums[0])
        calc_stop = round(entry * (1 - pct/100), 2)
        print(f"  -> Single number {pct}%, calculated stop: {calc_stop}")
    elif len(nums) >= 2:
        # Two numbers - price and percentage
        price = float(nums[0])
        pct = float(nums[1])
        print(f"  -> Two numbers: price={price}, pct={pct}%")

conn.close()
