import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()

conn = sqlite3.connect(_get_db_path())
cur = conn.cursor()

print('Checking logs table data:')
print()

# Check stop_loss values
print('1. Stop loss column:')
cur.execute('SELECT COUNT(*) FROM logs WHERE stop_loss IS NOT NULL')
with_stop = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM logs')
total = cur.fetchone()[0]
print(f'   Records with stop_loss: {with_stop}/{total}')

if with_stop > 0:
    cur.execute('SELECT MIN(stop_loss), MAX(stop_loss), AVG(stop_loss) FROM logs WHERE stop_loss IS NOT NULL')
    row = cur.fetchone()
    print(f'   Min: {row[0]}, Max: {row[1]}, Avg: {row[2]:.2f}')

# Check entry_price values
print()
print('2. Entry price column:')
cur.execute('SELECT COUNT(*) FROM logs WHERE entry_price IS NOT NULL AND entry_price > 0')
with_entry = cur.fetchone()[0]
print(f'   Records with entry_price > 0: {with_entry}/{total}')

if with_entry > 0:
    cur.execute('SELECT MIN(entry_price), MAX(entry_price) FROM logs WHERE entry_price > 0')
    row = cur.fetchone()
    print(f'   Min: {row[0]}, Max: {row[1]}')

# Sample data for TQQQ
print()
print('3. Sample TQQQ LONG forecasts:')
cur.execute("SELECT side, stop_loss, entry_price, exit_target FROM logs WHERE ticker='NASDAQ:TQQQ' AND side='LONG' LIMIT 3")
for row in cur.fetchall():
    print(f'   side={row[0]}, stop={row[1]}, entry={row[2]}, target={row[3]}')

# Check consensus table
print()
print('4. Consensus table:')
cur.execute('SELECT ticker, target_price, stop_loss FROM consensus')
for row in cur.fetchall():
    print(f'   {row[0]}: target={row[1]}, stop={row[2]}')

conn.close()
