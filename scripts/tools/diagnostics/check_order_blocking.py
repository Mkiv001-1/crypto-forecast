import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Check MAX_OPEN_ORDERS setting
cursor.execute("SELECT value FROM config WHERE key = 'MAX_OPEN_ORDERS'")
result = cursor.fetchone()
max_open_orders = result[0] if result else "5"
print(f"MAX_OPEN_ORDERS setting: {max_open_orders}")

# Check open orders count logic
cursor.execute("""
    SELECT COUNT(*) as open_orders_count
    FROM orders o
    LEFT JOIN trades t ON t.ib_parent_id = o.ib_parent_id
    WHERE UPPER(o.order_role)='ENTRY' AND (
        o.status IN ('QUEUED','SUBMITTED') 
        OR (o.status = 'FILLED_ENTRY' AND COALESCE(UPPER(t.status), 'OPEN') = 'OPEN')
    )
""")
open_orders_count = cursor.fetchone()[0]
print(f"Current open orders count: {open_orders_count}")

# Check which tickers are blocking new orders
cursor.execute("""
    SELECT DISTINCT ticker, status, order_role, created_at
    FROM orders 
    WHERE UPPER(order_role)='ENTRY' AND status IN ('QUEUED','SUBMITTED','FILLED_ENTRY')
    ORDER BY ticker
""")
blocking_orders = cursor.fetchall()

print(f"\n\nBLOCKING ORDERS (Entry orders):")
print("=" * 80)
for order in blocking_orders:
    created_at = datetime.fromisoformat(order[3].replace('Z', '+00:00'))
    age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
    print(f"Ticker: {order[0]}, Status: {order[1]}, Age: {age_hours:.1f} hours")

# Check if these orders actually exist in IB
print(f"\n\nCHECKING IF THESE ORDERS EXIST IN IB:")
print("=" * 80)
for order in blocking_orders:
    ticker = order[0]
    cursor.execute("""
        SELECT ib_order_id, status, created_at
        FROM orders 
        WHERE ticker = ? AND UPPER(order_role)='ENTRY' AND status IN ('QUEUED','SUBMITTED','FILLED_ENTRY')
        ORDER BY created_at DESC
    """, (ticker,))
    orders_for_ticker = cursor.fetchall()
    for o in orders_for_ticker:
        print(f"{ticker}: IB Order ID {o[0]}, Status {o[1]}")

# Check the age of all SUBMITTED orders
cursor.execute("""
    SELECT ticker, ib_order_id, order_role, created_at
    FROM orders 
    WHERE status = 'SUBMITTED'
    ORDER BY created_at
""")
all_submitted = cursor.fetchall()

print(f"\n\nALL SUBMITTED ORDERS AGE:")
print("=" * 80)
now = datetime.now(timezone.utc)
for order in all_submitted:
    created_at = datetime.fromisoformat(order[3].replace('Z', '+00:00'))
    age_hours = (now - created_at).total_seconds() / 3600
    age_days = age_hours / 24
    print(f"{order[0]}: IB Order {order[1]}, Role {order[2]}, Age: {age_days:.1f} days")

conn.close()
