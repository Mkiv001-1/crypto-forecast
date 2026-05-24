"""Verify stop_loss parsing logic for all tickers."""
import sqlite3
import re
import statistics

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get all tickers
cur.execute("SELECT DISTINCT ticker FROM logs WHERE status = 'NEW'")
tickers = [row[0] for row in cur.fetchall()]

print("=== STOP LOSS VERIFICATION ===\n")

for ticker in tickers:
    print(f"\n{ticker}:")
    print("-" * 50)
    
    cur.execute("""
        SELECT method, model, side, entry_price, exit_stop, stop_loss
        FROM logs 
        WHERE ticker = ? AND status = 'NEW' AND side IN ('LONG', 'SHORT')
    """, (ticker,))
    
    stops_found = []
    stops_parsed = []
    entries = []
    
    for row in cur.fetchall():
        entry = row['entry_price'] or 0
        if entry > 0:
            entries.append(entry)
        
        # Check stop_loss column
        stop = row['stop_loss']
        
        # Try to parse from exit_stop
        if not stop and row['exit_stop']:
            text = str(row['exit_stop'])
            nums = re.findall(r'[\d.]+', text)
            
            if len(nums) >= 2:
                # Two numbers: price and percent
                stop = float(nums[0])
            elif len(nums) == 1 and entry > 0:
                # One number: percentage
                pct = float(nums[0])
                if row['side'] == 'LONG':
                    stop = round(entry * (1 - pct/100), 2)
                else:  # SHORT
                    stop = round(entry * (1 + pct/100), 2)
        
        if stop:
            stops_parsed.append({
                'method': row['method'],
                'model': row['model'],
                'side': row['side'],
                'entry': entry,
                'stop': stop,
                'ratio': stop/entry if entry > 0 else 0
            })
            stops_found.append(stop)
    
    # Statistics
    if entries:
        avg_entry = statistics.median(entries)
        print(f"  Median entry: ${avg_entry:.2f}")
    
    if stops_found:
        print(f"  Forecasts with stop: {len(stops_found)}")
        print(f"  Stop range: ${min(stops_found):.2f} - ${max(stops_found):.2f}")
        print(f"  Median stop: ${statistics.median(stops_found):.2f}")
        
        # Check for suspicious values
        suspicious = [s for s in stops_parsed if s['entry'] > 0 and (s['stop'] < s['entry'] * 0.5 or s['stop'] > s['entry'] * 1.5)]
        if suspicious:
            print(f"  ⚠️  {len(suspicious)} suspicious stops:")
            for s in suspicious[:3]:
                print(f"      {s['method']}/{s['model']}: entry=${s['entry']:.2f}, stop=${s['stop']:.2f}")
    else:
        print("  ❌ No stops found!")

conn.close()
print("\n=== DONE ===")
