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

def reset_old_consensus_records():
    """Reset old consensus records to allow new order creation."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print("RESETTING OLD CONSENSUS RECORDS:")
    print("=" * 80)
    
    # Reset ORDER_SKIPPED records (old signals that were skipped)
    cursor.execute("""
        UPDATE consensus 
        SET order_state = NULL, 
            order_checked_at = NULL,
            order_attempted_at = NULL,
            order_reason = NULL,
            trade_id = NULL
        WHERE order_state = 'ORDER_SKIPPED'
        AND date >= date('now', '-7 days')
    """)
    
    skipped_reset = cursor.rowcount
    print(f"Reset {skipped_reset} ORDER_SKIPPED records from last 7 days")
    
    # Reset EXPIRED records (old signals that expired)
    cursor.execute("""
        UPDATE consensus 
        SET order_state = NULL, 
            order_checked_at = NULL,
            order_attempted_at = NULL,
            order_reason = NULL,
            trade_id = NULL
        WHERE order_state = 'EXPIRED'
        AND date >= date('now', '-7 days')
    """)
    
    expired_reset = cursor.rowcount
    print(f"Reset {expired_reset} EXPIRED records from last 7 days")
    
    conn.commit()
    conn.close()
    
    return skipped_reset + expired_reset

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
        LIMIT 10
    """)
    
    records = cursor.fetchall()
    conn.close()
    
    return records

def create_orders_from_consensus():
    """Create orders from consensus records."""
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.order_manager import submit_signal
        from scripts.core.consensus import get_forecasts_for_consensus
    except ImportError as e:
        print(f"Import error: {e}")
        return 0, []
    
    # Get database manager
    db_manager = SQLiteManager(_get_db_path())
    
    # Get ready consensus records
    records = get_ready_consensus_records()
    
    if not records:
        print("No consensus records ready for order creation")
        return 0, []
    
    print(f"\n\nCREATING ORDERS FROM {len(records)} CONSENSUS RECORDS:")
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
            # Get forecasts for this consensus
            forecasts = get_forecasts_for_consensus(db_manager, consensus_id)
            
            if not forecasts:
                print(f"  No forecasts found for consensus {consensus_id}")
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
            
            # Calculate position size (simple fixed size for demo)
            position_size = {
                'quantity': 5 if signal == 'LONG' else -5,
                'capital_allocated': 5000
            }
            
            # Submit order
            result = submit_signal(
                ticker=ticker,
                consensus=consensus,
                position_size=position_size,
                db_manager=db_manager
            )
            
            if result.get('status') == 'SUBMITTED':
                print(f"  ✓ Order created successfully: {result.get('message', '')}")
                created_orders.append({
                    'ticker': ticker,
                    'signal': signal,
                    'order_ids': result.get('order_ids', []),
                    'ib_ids': result.get('ib_ids', {}),
                    'trade_id': result.get('trade_id')
                })
                success_count += 1
            else:
                print(f"  ✗ Order creation failed: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            print(f"  ✗ Error processing consensus {consensus_id}: {e}")
    
    return success_count, created_orders

def main():
    print("RESET CONSENSUS AND CREATE NEW ORDERS")
    print("=" * 80)
    
    # Step 1: Reset old consensus records
    reset_count = reset_old_consensus_records()
    
    if reset_count == 0:
        print("\nNo old consensus records to reset")
        
        # Check if there are any recent consensus records at all
        conn = sqlite3.connect(_get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM consensus WHERE date >= date('now', '-7 days')")
        recent_count = cursor.fetchone()[0]
        conn.close()
        
        if recent_count == 0:
            print("No consensus records found from last 7 days")
            print("You need to generate new forecasts first")
            return
    else:
        print(f"\nReset {reset_count} old consensus records")
    
    # Step 2: Create orders from consensus
    success_count, created_orders = create_orders_from_consensus()
    
    print(f"\n\nSUMMARY:")
    print("=" * 80)
    print(f"Consensus records reset: {reset_count}")
    print(f"Orders created: {success_count}")
    
    if created_orders:
        print(f"\nCreated orders:")
        for order in created_orders:
            print(f"  {order['ticker']}: {order['signal']} - Trade ID {order.get('trade_id', 'N/A')}")

if __name__ == "__main__":
    main()
