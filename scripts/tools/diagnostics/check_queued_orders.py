import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Check all queued orders
cursor.execute("""
    SELECT id, ticker, status, ib_order_id, ib_parent_id, order_role, 
           order_type, action, quantity, limit_price, stop_price,
           created_at, submitted_at, filled_at
    FROM orders 
    WHERE status = 'QUEUED'
    ORDER BY created_at DESC
""")
queued_orders = cursor.fetchall()

print("QUEUED ORDERS:")
print("=" * 120)
for order in queued_orders:
    print(f"ID: {order[0]}, Ticker: {order[1]}, Status: {order[2]}")
    print(f"  IB Order ID: {order[3]}, IB Parent: {order[4]}, Role: {order[5]}")
    print(f"  Type: {order[6]}, Action: {order[7]}, Qty: {order[8]}")
    print(f"  Limit: {order[9]}, Stop: {order[10]}")
    print(f"  Created: {order[11]}, Submitted: {order[12]}, Filled: {order[13]}")
    print("-" * 60)

# Check recent orders to understand the pattern
cursor.execute("""
    SELECT id, ticker, status, ib_order_id, order_role, 
           order_type, created_at, submitted_at
    FROM orders 
    WHERE created_at > datetime('now', '-7 days')
    ORDER BY created_at DESC
    LIMIT 10
""")
recent_orders = cursor.fetchall()

print("\n\nRECENT ORDERS (last 7 days):")
print("=" * 120)
for order in recent_orders:
    print(f"ID: {order[0]}, Ticker: {order[1]}, Status: {order[2]}")
    print(f"  IB Order ID: {order[3]}, Role: {order[4]}, Type: {order[5]}")
    print(f"  Created: {order[6]}, Submitted: {order[7]}")
    print("-" * 60)

# Check queue-related scheduler configuration
cursor.execute("""
    SELECT key, value, description 
    FROM config 
    WHERE key IN ('ORDER_QUEUE_MAX_AGE_HOURS', 'PENDING_ORDERS_INTERVAL_MINUTES', 'ORDER_STATUS_SYNC_INTERVAL_SECONDS')
""")
config = cursor.fetchall()

print("\n\nORDER QUEUE CONFIGURATION:")
print("=" * 120)
for row in config:
    print(f"{row[0]}: {row[1]} ({row[2]})")

print("\nNOTE: legacy market-window config keys are deprecated in crypto 24/7 mode.")

conn.close()
