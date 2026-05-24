"""Check all AAPL records."""
import sqlite3
import re

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("All AAPL LONG records:")
cur.execute("""
    SELECT method, model, entry_price, exit_stop, stop_loss
    FROM logs 
    WHERE ticker = 'NASDAQ:AAPL' AND side = 'LONG' AND status = 'NEW'
""")

records = cur.fetchall()
print(f"Total: {len(records)} records")
print()

stops = []
for i, row in enumerate(records):
    # Parse stop
    stop = row['stop_loss']
    if not stop and row['exit_stop']:
        nums = re.findall(r'[\d.]+', str(row['exit_stop']))
        if len(nums) >= 2:
            stop = float(nums[0])
        elif len(nums) == 1 and row['entry_price']:
            pct = float(nums[0])
            stop = round(row['entry_price'] * (1 - pct/100), 2)
    
    if stop:
        stops.append(stop)
        # Flag suspicious
        entry = row['entry_price'] or 262
        if stop < entry * 0.5:
            print(f"#{i}: {row['method']}/{row['model']}")
            print(f"   entry={entry}, stop={stop}, exit_stop={repr(row['exit_stop'])}")
            print(f"   ⚠️ SUSPICIOUS: stop is {stop/entry:.1%} of entry")

print()
print(f"Stops found: {len(stops)}")
if stops:
    print(f"Min: {min(stops)}, Max: {max(stops)}")
    import statistics
    print(f"Median: {statistics.median(stops)}")

conn.close()
