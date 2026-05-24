import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Check consensus records that can create orders
cursor.execute("""
    SELECT id, ticker, signal, confidence, target_price, stop_loss, 
           entry_limit_price, order_state, trade_id, 
           date, order_checked_at
    FROM consensus 
    WHERE order_state IN ('PENDING_ORDER', 'READY') 
    OR (order_state IS NULL AND signal IS NOT NULL)
    ORDER BY date DESC
    LIMIT 20
""")

consensus_records = cursor.fetchall()

print("CONSENSUS RECORDS AVAILABLE FOR ORDER CREATION:")
print("=" * 120)

if not consensus_records:
    print("No consensus records found for order creation")
    
    # Check all consensus records to understand the situation
    cursor.execute("""
        SELECT order_state, COUNT(*) as count
        FROM consensus 
        GROUP BY order_state
        ORDER BY count DESC
    """)
    
    states = cursor.fetchall()
    print(f"\n\nAll consensus states:")
    print("=" * 60)
    for state in states:
        print(f"{state[0]}: {state[1]} records")
else:
    for record in consensus_records:
        print(f"ID: {record[0]}, Ticker: {record[1]}")
        print(f"  Signal: {record[2]}, Confidence: {record[3]}")
        print(f"  Target: {record[4]}, Stop: {record[5]}")
        print(f"  Entry Limit: {record[6]}")
        print(f"  Order State: {record[7]}, Trade ID: {record[8]}")
        print(f"  Date: {record[9]}, Checked: {record[10]}")
        print("-" * 60)

# Check if there are any tickers that had STALE orders and might have new consensus
print(f"\n\nCHECKING FOR NEW CONSENSUS ON PREVIOUSLY BLOCKED TICKERS:")
print("=" * 80)

cursor.execute("""
    SELECT DISTINCT o.ticker
    FROM orders o 
    WHERE o.status = 'STALE' AND UPPER(o.order_role) = 'ENTRY'
""")

blocked_tickers = [row[0] for row in cursor.fetchall()]

if blocked_tickers:
    print(f"Previously blocked tickers: {blocked_tickers}")
    
    placeholders = ','.join(['?' for _ in blocked_tickers])
    cursor.execute(f"""
        SELECT id, ticker, signal, confidence, order_state, date
        FROM consensus 
        WHERE ticker IN ({placeholders})
        AND (order_state IN ('PENDING_ORDER', 'READY')
        OR (order_state IS NULL AND signal IS NOT NULL))
        ORDER BY date DESC
    """, blocked_tickers)
    
    new_consensus = cursor.fetchall()
    
    if new_consensus:
        print(f"New consensus available for previously blocked tickers:")
        for record in new_consensus:
            print(f"  {record[1]}: ID {record[0]}, Signal {record[2]}, State {record[4]}")
    else:
        print("No new consensus for previously blocked tickers")
else:
    print("No previously blocked tickers found")

# Check current open orders count
cursor.execute("""
    SELECT COUNT(*) 
    FROM orders o
    LEFT JOIN trades t ON t.ib_parent_id = o.ib_parent_id
    WHERE UPPER(o.order_role)='ENTRY' AND o.status != 'STALE' AND (
        o.status IN ('QUEUED','SUBMITTED') 
        OR (o.status = 'FILLED_ENTRY' AND COALESCE(UPPER(t.status), 'OPEN') = 'OPEN')
    )
""")

open_count = cursor.fetchone()[0]
print(f"\n\nCurrent open orders count: {open_count}")

# Check MAX_OPEN_ORDERS setting
cursor.execute("SELECT value FROM config WHERE key = 'MAX_OPEN_ORDERS'")
result = cursor.fetchone()
max_open_orders = result[0] if result else "5"
print(f"MAX_OPEN_ORDERS setting: {max_open_orders}")

conn.close()
