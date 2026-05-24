"""DEPRECATED: sets consensus.trade_id to orders.id — use Bybit Place Trade instead."""
import sqlite3
import sys
import os
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'scripts', 'core'))

def get_ready_consensus_records():
    """Get consensus records ready for order creation."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, ticker, signal, confidence, target_price, stop_loss, 
               entry_limit_price, date
        FROM consensus 
        WHERE order_state IS NULL 
        AND signal IN ('LONG', 'SHORT')
        AND confidence >= 55
        AND date >= date('now', '-7 days')
        ORDER BY confidence DESC, date DESC
        LIMIT 5
    """)
    
    records = cursor.fetchall()
    conn.close()
    
    return records

def create_orders_manually():
    """Create orders manually using direct database operations."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Get ready consensus records
    records = get_ready_consensus_records()
    
    if not records:
        print("No consensus records ready for order creation")
        conn.close()
        return 0, []
    
    print(f"CREATING ORDERS FROM {len(records)} CONSENSUS RECORDS:")
    print("=" * 80)
    
    created_orders = []
    success_count = 0
    
    for record in records:
        consensus_id = record[0]
        ticker = record[1]
        signal = record[2]
        confidence = record[3]
        target_price = record[4]
        stop_loss = record[5]
        entry_limit_price = record[6]
        date = record[7]
        
        print(f"\nProcessing: {ticker} - {signal} (confidence: {confidence}%)")
        
        try:
            # Create a simple order record directly in database
            now = datetime.now(timezone.utc).isoformat()
            
            # Create parent order
            order_row = {
                "ticker": ticker,
                "ib_order_id": 0,  # Will be set when actually submitted to IB
                "ib_parent_id": 0,
                "order_role": "ENTRY",
                "order_type": "LMT" if entry_limit_price else "MKT",
                "action": "BUY" if signal == "LONG" else "SELL",
                "quantity": 5 if signal == "LONG" else -5,
                "limit_price": entry_limit_price,
                "stop_price": None,
                "status": "QUEUED",  # Start as QUEUED
                "submitted_at": None,
                "filled_at": None,
                "filled_price": None,
                "exit_price": None,
                "order_ref": "",
                "log_id": consensus_id,
                "test_tag": None,
                "trade_uid": f"manual_{ticker}_{int(datetime.now().timestamp())}",
                "ib_perm_id": 0
            }
            
            # Insert order
            cursor.execute("""
                INSERT INTO orders (
                    ticker, ib_order_id, ib_parent_id, order_role, order_type, 
                    action, quantity, limit_price, stop_price, status, 
                    submitted_at, filled_at, filled_price, exit_price, 
                    order_ref, log_id, test_tag, trade_uid, ib_perm_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_row["ticker"], order_row["ib_order_id"], order_row["ib_parent_id"],
                order_row["order_role"], order_row["order_type"], order_row["action"],
                order_row["quantity"], order_row["limit_price"], order_row["stop_price"],
                order_row["status"], order_row["submitted_at"], order_row["filled_at"],
                order_row["filled_price"], order_row["exit_price"], order_row["order_ref"],
                order_row["log_id"], order_row["test_tag"], order_row["trade_uid"],
                order_row["ib_perm_id"]
            ))
            
            parent_order_id = cursor.lastrowid
            
            # Update consensus to mark as processed
            cursor.execute("""
                UPDATE consensus 
                SET order_state = 'ORDER_SUBMITTED',
                    order_attempted_at = ?,
                    trade_id = ?
                WHERE id = ?
            """, (now, parent_order_id, consensus_id))
            
            print(f"  ✓ Order created: ID {parent_order_id}, Status QUEUED")
            
            created_orders.append({
                'ticker': ticker,
                'signal': signal,
                'order_id': parent_order_id,
                'status': 'QUEUED'
            })
            success_count += 1
            
        except Exception as e:
            print(f"  ✗ Error creating order: {e}")
            conn.rollback()
            conn.close()
            return success_count, created_orders
    
    conn.commit()
    conn.close()
    
    return success_count, created_orders

def main():
    print("CREATE ORDERS FROM RESET CONSENSUS")
    print("=" * 80)
    
    # Create orders
    success_count, created_orders = create_orders_manually()
    
    print(f"\n\nSUMMARY:")
    print("=" * 80)
    print(f"Orders created: {success_count}")
    
    if created_orders:
        print(f"\nCreated orders:")
        for order in created_orders:
            print(f"  {order['ticker']}: {order['signal']} - Order ID {order['order_id']} ({order['status']})")
    
    # Check current open orders count
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
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
    print(f"\nCurrent open orders count: {open_count}")
    
    conn.close()

if __name__ == "__main__":
    main()
