import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Check current open orders count with new logic
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
print(f"Current open orders count (excluding STALE): {open_count}")

# Check which tickers are still blocking
cursor.execute("""
    SELECT DISTINCT ticker, status, order_role
    FROM orders 
    WHERE UPPER(order_role)='ENTRY' AND status IN ('QUEUED','SUBMITTED','FILLED_ENTRY') AND status != 'STALE'
    ORDER BY ticker
""")

active_blockers = cursor.fetchall()

print(f"\n\nActive blocking orders:")
print("=" * 60)
if active_blockers:
    for order in active_blockers:
        print(f"Ticker: {order[0]}, Status: {order[1]}, Role: {order[2]}")
else:
    print("No active blocking orders found!")

# Check STALE orders
cursor.execute("""
    SELECT COUNT(*) FROM orders WHERE status = 'STALE'
""")
stale_count = cursor.fetchone()[0]

print(f"\n\nSTALE orders count: {stale_count}")

# Check MAX_OPEN_ORDERS setting
cursor.execute("SELECT value FROM config WHERE key = 'MAX_OPEN_ORDERS'")
result = cursor.fetchone()
max_open_orders = result[0] if result else "5"
print(f"MAX_OPEN_ORDERS setting: {max_open_orders}")

# Summary
print(f"\n\nSUMMARY:")
print("=" * 60)
print(f"Open orders: {open_count}/{max_open_orders}")
print(f"STALE orders: {stale_count}")
if open_count < int(max_open_orders):
    print("✅ NEW ORDERS CAN BE SUBMITTED")
else:
    print("❌ NEW ORDERS STILL BLOCKED")

conn.close()
