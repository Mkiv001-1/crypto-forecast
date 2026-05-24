import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Check transaction history for order 136
cursor.execute("""
    SELECT occurred_at, event_type, operation_status, status_before, status_after, 
           ib_order_id, ib_perm_id, response_payload_json, error_message
    FROM ib_order_transactions 
    WHERE ib_order_id = 136
    ORDER BY occurred_at ASC
""")
rows = cursor.fetchall()

print("Transaction history for IB Order ID 136:")
print("-" * 120)
for row in rows:
    print(f"Time: {row[0]}")
    print(f"Event: {row[1]}, Operation: {row[2]}")
    print(f"Status: {row[3]} -> {row[4]}")
    print(f"IB Order ID: {row[5]}, Perm ID: {row[6]}")
    if row[7]:
        print(f"Response: {row[7][:200]}...")
    if row[8]:
        print(f"Error: {row[8]}")
    print("-" * 60)

# Also check the order details
cursor.execute("""
    SELECT * FROM orders WHERE ib_order_id = 136
""")
order_rows = cursor.fetchall()

print("\n\nOrder details for IB Order ID 136:")
print("-" * 120)
for row in order_rows:
    print(row)

conn.close()
