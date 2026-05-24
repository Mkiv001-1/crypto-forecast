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

def manual_activate_orders():
    """Manually activate orders by calling the consensus activation function."""
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.order_manager import activate_consensus_order
        from scripts.core.consensus import get_forecasts_for_consensus
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    print("MANUAL ORDER ACTIVATION:")
    print("=" * 80)
    
    # Get database manager
    db_manager = SQLiteManager(_get_db_path())
    
    # Get PENDING_ORDER consensus records
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, ticker, signal, confidence, target_price, stop_loss, 
               entry_limit_price, trade_id
        FROM consensus 
        WHERE order_state = 'PENDING_ORDER'
        ORDER BY id
    """)
    
    pending_consensus = cursor.fetchall()
    conn.close()
    
    if not pending_consensus:
        print("No PENDING_ORDER consensus found")
        return False
    
    print(f"Found {len(pending_consensus)} PENDING_ORDER consensus records:")
    
    success_count = 0
    
    for record in pending_consensus:
        consensus_id = record[0]
        ticker = record[1]
        signal = record[2]
        confidence = record[3]
        target_price = record[4]
        stop_loss = record[5]
        entry_limit_price = record[6]
        trade_id = record[7]
        
        print(f"\nProcessing consensus {consensus_id}: {ticker} - {signal}")
        print(f"  Confidence: {confidence}%, Target: {target_price}, Stop: {stop_loss}")
        
        try:
            # Get forecasts for this consensus
            forecasts = get_forecasts_for_consensus(db_manager, consensus_id)
            
            if not forecasts:
                print(f"  No forecasts found, skipping")
                continue
            
            # Build consensus dict
            consensus = {
                'ticker': ticker,
                'signal': signal,
                'confidence': confidence,
                'target_price': target_price,
                'stop_loss': stop_loss,
                'entry_limit_price': entry_limit_price,
                'forecasts': forecasts
            }
            
            # Calculate position size (simple fixed size)
            position_size = {
                'quantity': 5 if signal == 'LONG' else -5,
                'capital_allocated': 5000
            }
            
            print(f"  Calling activate_consensus_order...")
            
            # Activate the consensus order
            result = activate_consensus_order(
                consensus_id=consensus_id,
                ticker=ticker,
                consensus=consensus,
                position_size=position_size,
                db_manager=db_manager
            )
            
            print(f"  Result: {result}")
            
            if result and result.get('status') in ['SUBMITTED', 'QUEUED']:
                print(f"  SUCCESS: Order activated")
                success_count += 1
            else:
                print(f"  FAILED: {result}")
                
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n\nMANUAL ACTIVATION SUMMARY:")
    print(f"Successfully activated: {success_count}/{len(pending_consensus)}")
    
    return success_count > 0

def check_results():
    """Check the results of manual activation."""
    print(f"\n\nCHECKING RESULTS:")
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
    
    # Check for IB Order IDs
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM orders 
        WHERE id >= 49 AND ib_order_id > 0
    """)
    
    ib_orders = cursor.fetchone()[0]
    print(f"Orders with IB Order IDs: {ib_orders}")
    
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
    print("MANUAL ORDER SUBMISSION TO IB")
    print("=" * 80)
    
    # Try manual activation
    success = manual_activate_orders()
    
    # Check results
    check_results()
    
    if success:
        print(f"\n\nORDERS SHOULD NOW BE SUBMITTED TO IB!")
        print("Check IB TWS/Gateway for the orders")
    else:
        print(f"\n\nMANUAL ACTIVATION FAILED")
        print("Possible issues:")
        print("1. IB gateway not connected")
        print("2. ORDER_MODE not set correctly")
        print("3. Missing required imports or dependencies")
        print("4. activate_consensus_order function has errors")

if __name__ == "__main__":
    main()
