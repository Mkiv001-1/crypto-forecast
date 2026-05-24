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

def submit_orders_to_ib():
    """Submit orders to IB using the real order_manager system."""
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.order_manager import submit_signal
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    print("SUBMITTING ORDERS TO IB (REAL SYSTEM):")
    print("=" * 80)
    
    # Get database manager
    db_manager = SQLiteManager(_get_db_path())
    
    # Get consensus records that need orders
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.id, c.ticker, c.signal, c.confidence, c.target_price, c.stop_loss, 
               c.entry_limit_price, o.id as existing_order_id
        FROM consensus c
        LEFT JOIN orders o ON o.log_id = c.id AND o.order_role = 'ENTRY'
        WHERE c.order_state = 'PENDING_ORDER'
        AND o.id >= 49
        ORDER BY c.id
    """)
    
    consensus_records = cursor.fetchall()
    conn.close()
    
    if not consensus_records:
        print("No PENDING_ORDER consensus found with existing orders")
        return False
    
    print(f"Found {len(consensus_records)} consensus records to process:")
    
    success_count = 0
    
    for record in consensus_records:
        consensus_id = record[0]
        ticker = record[1]
        signal = record[2]
        confidence = record[3]
        target_price = record[4]
        stop_loss = record[5]
        entry_limit_price = record[6]
        existing_order_id = record[7]
        
        print(f"\nProcessing consensus {consensus_id}: {ticker} - {signal}")
        print(f"  Confidence: {confidence}%, Target: {target_price}, Stop: {stop_loss}")
        print(f"  Entry Limit: {entry_limit_price}, Existing Order ID: {existing_order_id}")
        
        try:
            # Build consensus dict (simplified without forecasts)
            consensus = {
                'ticker': ticker,
                'signal': signal,
                'confidence': confidence,
                'target_price': target_price,
                'stop_loss': stop_loss,
                'entry_limit_price': entry_limit_price,
                'forecasts': []  # Empty for now
            }
            
            # Calculate position size
            position_size = {
                'quantity': 5 if signal == 'LONG' else -5,
                'capital_allocated': 5000
            }
            
            print(f"  Submitting signal to order_manager...")
            
            # Submit the order using the real system
            result = submit_signal(
                ticker=ticker,
                consensus=consensus,
                position_size=position_size,
                db_manager=db_manager
            )
            
            print(f"  Result: {result}")
            
            if result and result.get('status') in ['SUBMITTED', 'QUEUED']:
                print(f"  SUCCESS: Order submitted")
                print(f"    Order IDs: {result.get('order_ids', [])}")
                print(f"    IB IDs: {result.get('ib_ids', {})}")
                print(f"    Trade ID: {result.get('trade_id')}")
                success_count += 1
                
                # Update consensus state
                conn = sqlite3.connect(_get_db_path())
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE consensus 
                    SET order_state = 'ORDER_SUBMITTED'
                    WHERE id = ?
                """, (consensus_id,))
                conn.commit()
                conn.close()
                
            else:
                print(f"  FAILED: {result}")
                
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n\nREAL SUBMISSION SUMMARY:")
    print(f"Successfully submitted: {success_count}/{len(consensus_records)}")
    
    return success_count > 0

def check_final_results():
    """Check the final results."""
    print(f"\n\nFINAL RESULTS:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Check order statuses
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM orders 
        WHERE id >= 49
        GROUP BY status
        ORDER BY count DESC
    """)
    
    status_counts = cursor.fetchall()
    
    print("Order statuses:")
    for status, count in status_counts:
        print(f"  {status}: {count}")
    
    # Check for real IB Order IDs (> 1000 indicates real submission)
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM orders 
        WHERE id >= 49 AND ib_order_id > 1000
    """)
    
    real_ib_orders = cursor.fetchone()[0]
    print(f"Orders with real IB Order IDs: {real_ib_orders}")
    
    # Check consensus states
    cursor.execute("""
        SELECT order_state, COUNT(*) as count
        FROM consensus 
        WHERE id IN (SELECT DISTINCT log_id FROM orders WHERE id >= 49)
        GROUP BY order_state
    """)
    
    consensus_states = cursor.fetchall()
    
    print("Consensus states:")
    for state, count in consensus_states:
        print(f"  {state}: {count}")
    
    conn.close()

def main():
    print("REAL ORDER SUBMISSION TO IB")
    print("=" * 80)
    print("Using actual order_manager system with pandas")
    
    # Submit orders
    success = submit_orders_to_ib()
    
    # Check results
    check_final_results()
    
    if success:
        print(f"\n\nORDERS SUBMITTED TO REAL IB SYSTEM!")
        print("Check IB Gateway/TWS for actual orders")
    else:
        print(f"\n\nREAL SUBMISSION FAILED")
        print("Orders remain in simulated state")

if __name__ == "__main__":
    main()
