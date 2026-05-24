import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()

conn = sqlite3.connect(_get_db_path())
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check TQQQ data
print('TQQQ LONG forecasts:')
cur.execute("SELECT COUNT(*) FROM logs WHERE ticker = 'NASDAQ:TQQQ' AND side = 'LONG' AND status = 'NEW'")
print(f'  Total LONG: {cur.fetchone()[0]}')

cur.execute("SELECT COUNT(*) FROM logs WHERE ticker = 'NASDAQ:TQQQ' AND side = 'LONG' AND status = 'NEW' AND (stop_loss IS NOT NULL OR exit_stop IS NOT NULL)")
print(f'  With stop data: {cur.fetchone()[0]}')

# Sample data
print()
print('Sample TQQQ LONG with exit_stop:')
cur.execute("SELECT method, model, exit_stop, stop_loss FROM logs WHERE ticker = 'NASDAQ:TQQQ' AND side = 'LONG' AND status = 'NEW' AND exit_stop IS NOT NULL LIMIT 3")
for row in cur.fetchall():
    print(f'  {row[0]} | {row[1]}: exit_stop={repr(row[2])}, stop_loss={row[3]}')

# Check AAPL data  
print()
print('AAPL LONG forecasts:')
cur.execute("SELECT COUNT(*) FROM logs WHERE ticker = 'NASDAQ:AAPL' AND side = 'LONG' AND status = 'NEW'")
print(f'  Total LONG: {cur.fetchone()[0]}')

cur.execute("SELECT COUNT(*) FROM logs WHERE ticker = 'NASDAQ:AAPL' AND side = 'LONG' AND status = 'NEW' AND (stop_loss IS NOT NULL OR exit_stop IS NOT NULL)")
print(f'  With stop data: {cur.fetchone()[0]}')

# Sample data
print()
print('Sample AAPL LONG with exit_stop:')
cur.execute("SELECT method, model, exit_stop, stop_loss FROM logs WHERE ticker = 'NASDAQ:AAPL' AND side = 'LONG' AND status = 'NEW' AND exit_stop IS NOT NULL LIMIT 3")
for row in cur.fetchall():
    print(f'  {row[0]} | {row[1]}: exit_stop={repr(row[2])}, stop_loss={row[3]}')

conn.close()
