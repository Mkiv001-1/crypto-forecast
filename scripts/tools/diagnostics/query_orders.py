import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Query orders with filled or hited status
cursor.execute("""
    SELECT id, ticker, status, ib_order_id, ib_parent_id, order_role, created_at 
    FROM orders 
    WHERE status LIKE '%FILLED%' OR status LIKE '%HITED%' 
    ORDER BY created_at DESC 
    LIMIT 10
""")
rows = cursor.fetchall()

print("Orders with FILLED/HITED status:")
print("-" * 100)
for row in rows:
    print(f'ID: {row[0]}, Ticker: {row[1]}, Status: {row[2]}, IB Order ID: {row[3]}, IB Parent ID: {row[4]}, Role: {row[5]}, Created: {row[6]}')

# Also check for any orders with 0 ib_order_id but non-submitted status
print("\n\nOrders with ib_order_id = 0 but not QUEUED status:")
print("-" * 100)
cursor.execute("""
    SELECT id, ticker, status, ib_order_id, ib_parent_id, order_role, created_at 
    FROM orders 
    WHERE ib_order_id = 0 AND status NOT IN ('QUEUED', 'ERROR')
    ORDER BY created_at DESC 
    LIMIT 10
""")
rows = cursor.fetchall()

for row in rows:
    print(f'ID: {row[0]}, Ticker: {row[1]}, Status: {row[2]}, IB Order ID: {row[3]}, IB Parent ID: {row[4]}, Role: {row[5]}, Created: {row[6]}')

conn.close()
