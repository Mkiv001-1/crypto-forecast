import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


def fix_duplicate_nvda_orders():
    """Fix duplicate NVDA orders by giving them unique trade_uids."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print("FIXING DUPLICATE NVDA ORDERS:")
    print("=" * 80)
    
    # Get the two NVDA entry orders
    cursor.execute("""
        SELECT id, ticker, trade_uid, created_at
        FROM orders 
        WHERE ticker = 'NASDAQ:NVDA' 
        AND UPPER(order_role) = 'ENTRY'
        AND status = 'QUEUED'
        AND id >= 49
        ORDER BY id
    """)
    
    nvda_orders = cursor.fetchall()
    
    if len(nvda_orders) != 2:
        print(f"Expected 2 NVDA orders, found {len(nvda_orders)}")
        conn.close()
        return
    
    order1_id, order1_ticker, order1_uid, order1_created = nvda_orders[0]
    order2_id, order2_ticker, order2_uid, order2_created = nvda_orders[1]
    
    print(f"Order 1: ID {order1_id}, UID {order1_uid}")
    print(f"Order 2: ID {order2_id}, UID {order2_uid}")
    
    # Create unique trade_uid for the second order
    new_uid = f"manual_NASDAQ:NVDA_2_{int(datetime.now().timestamp())}"
    
    print(f"Updating Order 2 trade_uid to: {new_uid}")
    
    # Update the second entry order
    cursor.execute("""
        UPDATE orders 
        SET trade_uid = ?
        WHERE id = ?
    """, (new_uid, order2_id))
    
    # Update all child orders of the second entry order
    cursor.execute("""
        UPDATE orders 
        SET trade_uid = ?
        WHERE ib_parent_id = ?
    """, (new_uid, order2_id))
    
    updated_child_count = cursor.rowcount
    print(f"Updated {updated_child_count} child orders")
    
    conn.commit()
    conn.close()
    
    return order2_id, new_uid

def verify_fixed_brackets():
    """Verify that all bracket orders are now complete."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print(f"\n\nVERIFYING FIXED BRACKET ORDER STRUCTURE:")
    print("=" * 80)
    
    # Get all entry orders created recently
    cursor.execute("""
        SELECT id, ticker, trade_uid
        FROM orders 
        WHERE status = 'QUEUED' 
        AND UPPER(order_role) = 'ENTRY'
        AND id >= 49
        ORDER BY id
    """)
    
    entry_orders = cursor.fetchall()
    
    complete_brackets = 0
    incomplete_brackets = 0
    
    for entry_order in entry_orders:
        entry_id = entry_order[0]
        ticker = entry_order[1]
        trade_uid = entry_order[2]
        
        # Count child orders for this specific trade_uid
        cursor.execute("""
            SELECT order_role, COUNT(*) as count
            FROM orders 
            WHERE trade_uid = ? AND id != ?
            GROUP BY order_role
        """, (trade_uid, entry_id))
        
        child_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        tp_count = child_counts.get('TAKE_PROFIT', 0)
        sl_count = child_counts.get('STOP_LOSS', 0)
        
        print(f"\nEntry {entry_id} ({ticker}) - UID: {trade_uid[-20:]}:")
        print(f"  TAKE_PROFIT: {tp_count}, STOP_LOSS: {sl_count}")
        
        if tp_count == 1 and sl_count == 1:
            print(f"  COMPLETE BRACKET")
            complete_brackets += 1
        else:
            print(f"  INCOMPLETE BRACKET")
            incomplete_brackets += 1
    
    print(f"\n\nFINAL SUMMARY:")
    print(f"Complete brackets: {complete_brackets}")
    print(f"Incomplete brackets: {incomplete_brackets}")
    
    # Show all queued orders
    cursor.execute("""
        SELECT id, ticker, order_role, status, trade_uid
        FROM orders 
        WHERE status = 'QUEUED' 
        AND id >= 49
        ORDER BY trade_uid, order_role
    """)
    
    all_orders = cursor.fetchall()
    
    print(f"\n\nALL QUEUED ORDERS:")
    print("=" * 80)
    current_uid = None
    for order in all_orders:
        order_id, ticker, role, status, trade_uid = order
        if trade_uid != current_uid:
            print(f"\nTrade UID: {trade_uid}")
            current_uid = trade_uid
        print(f"  ID {order_id}: {ticker} - {role} ({status})")
    
    conn.close()

def main():
    print("FIX DUPLICATE NVDA ORDERS AND VERIFY BRACKETS")
    print("=" * 80)
    
    # Fix duplicates
    fixed_order_id, new_uid = fix_duplicate_nvda_orders()
    
    # Verify all brackets are complete
    verify_fixed_brackets()

if __name__ == "__main__":
    main()
