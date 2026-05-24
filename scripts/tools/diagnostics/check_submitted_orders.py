import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Check all SUBMITTED orders
cursor.execute("""
    SELECT id, ticker, status, ib_order_id, ib_parent_id, order_role, 
           order_type, action, quantity, limit_price, stop_price,
           created_at, submitted_at, filled_at
    FROM orders 
    WHERE status = 'SUBMITTED'
    ORDER BY created_at DESC
""")
submitted_orders = cursor.fetchall()

print("SUBMITTED ORDERS:")
print("=" * 120)
for order in submitted_orders:
    print(f"ID: {order[0]}, Ticker: {order[1]}, Status: {order[2]}")
    print(f"  IB Order ID: {order[3]}, IB Parent: {order[4]}, Role: {order[5]}")
    print(f"  Type: {order[6]}, Action: {order[7]}, Qty: {order[8]}")
    print(f"  Limit: {order[9]}, Stop: {order[10]}")
    print(f"  Created: {order[11]}, Submitted: {order[12]}, Filled: {order[13]}")
    print("-" * 60)

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

print(f"\n\nOPEN ORDERS COUNT (per system logic): {open_orders_count}")

# Check tickers with open orders
cursor.execute("""
    SELECT DISTINCT ticker, status, order_role
    FROM orders 
    WHERE UPPER(order_role)='ENTRY' AND status IN ('QUEUED','SUBMITTED','FILLED_ENTRY')
    ORDER BY ticker
""")
tickers_with_orders = cursor.fetchall()

print(f"\n\nTICKERS WITH OPEN ORDERS:")
print("=" * 80)
for ticker in tickers_with_orders:
    print(f"Ticker: {ticker[0]}, Status: {ticker[1]}, Role: {ticker[2]}")

# Check MAX_OPEN_ORDERS setting
cursor.execute("SELECT value FROM config WHERE key = 'MAX_OPEN_ORDERS'")
max_open_orders = cursor.fetchone()[0] if cursor.fetchone() else "5"

print(f"\n\nMAX_OPEN_ORDERS setting: {max_open_orders}")

# Check if any of these orders are actually old/stuck
print(f"\n\nORDER AGE ANALYSIS:")
print("=" * 80)
now = datetime.now(timezone.utc)
for order in submitted_orders:
    created_at = datetime.fromisoformat(order[11].replace('Z', '+00:00'))
    age_hours = (now - created_at).total_seconds() / 3600
    print(f"ID {order[0]} ({order[1]}): {age_hours:.1f} hours old")

conn.close()
