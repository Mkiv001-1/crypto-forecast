import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Check the new entry orders we just created
cursor.execute("""
    SELECT id, ticker, quantity, limit_price, status, trade_uid, created_at
    FROM orders 
    WHERE status = 'QUEUED' 
    AND UPPER(order_role) = 'ENTRY'
    AND id >= 49  -- The new orders we just created
    ORDER BY created_at DESC
""")

new_entry_orders = cursor.fetchall()

print("NEW ENTRY ORDERS CREATED:")
print("=" * 80)
for order in new_entry_orders:
    print(f"ID {order[0]}: {order[1]} - Qty {order[2]}, Limit {order[3]}")
    print(f"  Status: {order[4]}, Trade UID: {order[5]}")
    print(f"  Created: {order[6]}")
    print("-" * 40)

# Check if they have child orders
print(f"\n\nCHECKING FOR CHILD ORDERS:")
print("=" * 80)

for entry_order in new_entry_orders:
    entry_id = entry_order[0]
    ticker = entry_order[1]
    trade_uid = entry_order[5]
    
    print(f"\nEntry Order ID {entry_id} ({ticker}):")
    
    # Check for TAKE_PROFIT orders
    cursor.execute("""
        SELECT id, order_role, quantity, limit_price, status
        FROM orders 
        WHERE (ib_parent_id = ? OR trade_uid = ?)
        AND UPPER(order_role) = 'TAKE_PROFIT'
    """, (entry_id, trade_uid))
    
    tp_orders = cursor.fetchall()
    print(f"  TAKE_PROFIT orders: {len(tp_orders)}")
    for tp in tp_orders:
        print(f"    ID {tp[0]}: Qty {tp[2]}, Limit {tp[3]}, Status {tp[4]}")
    
    # Check for STOP_LOSS orders
    cursor.execute("""
        SELECT id, order_role, quantity, stop_price, status
        FROM orders 
        WHERE (ib_parent_id = ? OR trade_uid = ?)
        AND UPPER(order_role) = 'STOP_LOSS'
    """, (entry_id, trade_uid))
    
    sl_orders = cursor.fetchall()
    print(f"  STOP_LOSS orders: {len(sl_orders)}")
    for sl in sl_orders:
        print(f"    ID {sl[0]}: Qty {sl[2]}, Stop {sl[3]}, Status {sl[4]}")

# Check the consensus data for target and stop prices
print(f"\n\nCHECKING CONSENSUS DATA FOR TARGET/STOP PRICES:")
print("=" * 80)

for entry_order in new_entry_orders:
    entry_id = entry_order[0]
    ticker = entry_order[1]
    
    # Get the consensus that created this order
    cursor.execute("""
        SELECT c.signal, c.target_price, c.stop_loss, c.entry_limit_price, c.confidence
        FROM consensus c
        WHERE c.trade_id = ?
    """, (entry_id,))
    
    consensus = cursor.fetchone()
    if consensus:
        print(f"\n{ticker}:")
        print(f"  Signal: {consensus[0]}")
        print(f"  Target: {consensus[1]}")
        print(f"  Stop Loss: {consensus[2]}")
        print(f"  Entry Limit: {consensus[3]}")
        print(f"  Confidence: {consensus[4]}%")

conn.close()
