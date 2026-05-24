import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


def create_child_orders():
    """Create missing TAKE_PROFIT and STOP_LOSS orders for entry orders."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print("CREATING MISSING TAKE_PROFIT AND STOP_LOSS ORDERS:")
    print("=" * 80)
    
    # Get entry orders that need child orders
    cursor.execute("""
        SELECT o.id, o.ticker, o.quantity, o.trade_uid, o.created_at,
               c.signal, c.target_price, c.stop_loss, c.entry_limit_price
        FROM orders o
        LEFT JOIN consensus c ON c.trade_id = o.id
        WHERE o.status = 'QUEUED' 
        AND UPPER(o.order_role) = 'ENTRY'
        AND o.id >= 49
        ORDER BY o.created_at DESC
    """)
    
    entry_orders = cursor.fetchall()
    
    created_child_orders = []
    
    for entry_order in entry_orders:
        entry_id = entry_order[0]
        ticker = entry_order[1]
        quantity = entry_order[2]
        trade_uid = entry_order[3]
        created_at = entry_order[4]
        signal = entry_order[5]
        target_price = entry_order[6]
        stop_loss = entry_order[7]
        entry_limit_price = entry_order[8]
        
        print(f"\nProcessing Entry Order {entry_id} ({ticker}):")
        print(f"  Signal: {signal}, Qty: {quantity}")
        print(f"  Target: {target_price}, Stop: {stop_loss}")
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Create TAKE_PROFIT order
        if target_price and target_price > 0:
            try:
                # For SHORT signals, take profit is lower (buy to cover)
                # For LONG signals, take profit is higher (sell to close)
                tp_action = "BUY" if signal == "SHORT" else "SELL"
                tp_quantity = abs(quantity)  # Always positive for closing orders
                
                cursor.execute("""
                    INSERT INTO orders (
                        log_id, ticker, ib_order_id, ib_parent_id, order_role, 
                        order_type, action, quantity, limit_price, stop_price, 
                        status, account_type, created_at, submitted_at, 
                        filled_at, filled_price, execution_latency_ms, 
                        spread_at_submission, error_message, is_test, 
                        test_tag, trade_uid, ib_perm_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(entry_id),  # log_id
                    ticker,  # ticker
                    0,  # ib_order_id
                    entry_id,  # ib_parent_id (links to entry)
                    "TAKE_PROFIT",  # order_role
                    "LMT",  # order_type
                    tp_action,  # action
                    tp_quantity,  # quantity
                    float(target_price),  # limit_price
                    None,  # stop_price
                    "QUEUED",  # status
                    "",  # account_type
                    now,  # created_at
                    None,  # submitted_at
                    None,  # filled_at
                    None,  # filled_price
                    None,  # execution_latency_ms
                    None,  # spread_at_submission
                    "",  # error_message
                    0,  # is_test
                    None,  # test_tag
                    trade_uid,  # trade_uid (same as parent)
                    0  # ib_perm_id
                ))
                
                tp_order_id = cursor.lastrowid
                print(f"  ✓ TAKE_PROFIT created: ID {tp_order_id}, {tp_action} {tp_quantity} @ {target_price}")
                created_child_orders.append({
                    'parent_id': entry_id,
                    'child_id': tp_order_id,
                    'type': 'TAKE_PROFIT',
                    'ticker': ticker
                })
                
            except Exception as e:
                print(f"  ✗ Error creating TAKE_PROFIT: {e}")
        
        # Create STOP_LOSS order
        if stop_loss and stop_loss > 0:
            try:
                # For SHORT signals, stop loss is higher (buy to cover at loss)
                # For LONG signals, stop loss is lower (sell at loss)
                sl_action = "BUY" if signal == "SHORT" else "SELL"
                sl_quantity = abs(quantity)  # Always positive for closing orders
                
                cursor.execute("""
                    INSERT INTO orders (
                        log_id, ticker, ib_order_id, ib_parent_id, order_role, 
                        order_type, action, quantity, limit_price, stop_price, 
                        status, account_type, created_at, submitted_at, 
                        filled_at, filled_price, execution_latency_ms, 
                        spread_at_submission, error_message, is_test, 
                        test_tag, trade_uid, ib_perm_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(entry_id),  # log_id
                    ticker,  # ticker
                    0,  # ib_order_id
                    entry_id,  # ib_parent_id (links to entry)
                    "STOP_LOSS",  # order_role
                    "STP",  # order_type
                    sl_action,  # action
                    sl_quantity,  # quantity
                    None,  # limit_price
                    float(stop_loss),  # stop_price
                    "QUEUED",  # status
                    "",  # account_type
                    now,  # created_at
                    None,  # submitted_at
                    None,  # filled_at
                    None,  # filled_price
                    None,  # execution_latency_ms
                    None,  # spread_at_submission
                    "",  # error_message
                    0,  # is_test
                    None,  # test_tag
                    trade_uid,  # trade_uid (same as parent)
                    0  # ib_perm_id
                ))
                
                sl_order_id = cursor.lastrowid
                print(f"  ✓ STOP_LOSS created: ID {sl_order_id}, {sl_action} {sl_quantity} @ {stop_loss}")
                created_child_orders.append({
                    'parent_id': entry_id,
                    'child_id': sl_order_id,
                    'type': 'STOP_LOSS',
                    'ticker': ticker
                })
                
            except Exception as e:
                print(f"  ✗ Error creating STOP_LOSS: {e}")
    
    conn.commit()
    conn.close()
    
    return created_child_orders

def verify_bracket_orders():
    """Verify that all bracket orders are complete."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print(f"\n\nVERIFYING BRACKET ORDER STRUCTURE:")
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
        
        # Count child orders
        cursor.execute("""
            SELECT order_role, COUNT(*) as count
            FROM orders 
            WHERE trade_uid = ? AND id != ?
            GROUP BY order_role
        """, (trade_uid, entry_id))
        
        child_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        tp_count = child_counts.get('TAKE_PROFIT', 0)
        sl_count = child_counts.get('STOP_LOSS', 0)
        
        print(f"\nEntry {entry_id} ({ticker}):")
        print(f"  TAKE_PROFIT: {tp_count}, STOP_LOSS: {sl_count}")
        
        if tp_count == 1 and sl_count == 1:
            print(f"  ✓ COMPLETE BRACKET")
            complete_brackets += 1
        else:
            print(f"  ✗ INCOMPLETE BRACKET")
            incomplete_brackets += 1
    
    print(f"\n\nSUMMARY:")
    print(f"Complete brackets: {complete_brackets}")
    print(f"Incomplete brackets: {incomplete_brackets}")
    
    conn.close()

def main():
    print("CREATE MISSING CHILD ORDERS FOR BRACKET ORDERS")
    print("=" * 80)
    
    # Create child orders
    created_orders = create_child_orders()
    
    print(f"\n\nCREATED {len(created_orders)} CHILD ORDERS:")
    print("=" * 80)
    for order in created_orders:
        print(f"  {order['ticker']}: {order['type']} (Parent: {order['parent_id']}, Child: {order['child_id']})")
    
    # Verify bracket structure
    verify_bracket_orders()

if __name__ == "__main__":
    main()
