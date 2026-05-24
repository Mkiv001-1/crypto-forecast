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

def create_new_test_orders():
    """Create new test orders using the real system."""
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.order_manager import submit_signal
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    print("CREATING NEW TEST ORDERS WITH REAL SYSTEM:")
    print("=" * 80)
    
    # Get database manager
    db_manager = SQLiteManager(_get_db_path())
    
    # Create test consensus data
    test_consensus_data = [
        {
            'ticker': 'NASDAQ:MSFT',
            'signal': 'LONG',
            'confidence': 75.0,
            'target_price': 450.0,
            'stop_loss': 420.0,
            'entry_limit_price': 435.0
        },
        {
            'ticker': 'NASDAQ:GOOGL',
            'signal': 'SHORT', 
            'confidence': 80.0,
            'target_price': 160.0,
            'stop_loss': 175.0,
            'entry_limit_price': 168.0
        }
    ]
    
    success_count = 0
    
    for i, data in enumerate(test_consensus_data):
        print(f"\nCreating test order {i+1}: {data['ticker']} - {data['signal']}")
        
        try:
            # Build consensus dict
            consensus = {
                'ticker': data['ticker'],
                'signal': data['signal'],
                'confidence': data['confidence'],
                'target_price': data['target_price'],
                'stop_loss': data['stop_loss'],
                'entry_limit_price': data['entry_limit_price'],
                'forecasts': []  # Empty for test
            }
            
            # Calculate position size
            position_size = {
                'quantity': 3 if data['signal'] == 'LONG' else -3,
                'capital_allocated': 3000
            }
            
            print(f"  Submitting signal...")
            print(f"    Entry: {data['entry_limit_price']}")
            print(f"    Target: {data['target_price']}")
            print(f"    Stop: {data['stop_loss']}")
            
            # Submit the order using the real system
            result = submit_signal(
                ticker=data['ticker'],
                consensus=consensus,
                position_size=position_size,
                db_manager=db_manager
            )
            
            print(f"  Result: {result}")
            
            if result and result.get('status') in ['SUBMITTED', 'QUEUED']:
                print(f"  SUCCESS: Order created")
                print(f"    Order IDs: {result.get('order_ids', [])}")
                print(f"    IB IDs: {result.get('ib_ids', {})}")
                print(f"    Trade ID: {result.get('trade_id')}")
                success_count += 1
            else:
                print(f"  FAILED: {result}")
                
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n\nTEST CREATION SUMMARY:")
    print(f"Successfully created: {success_count}/{len(test_consensus_data)}")
    
    return success_count > 0

def check_system_status():
    """Check overall system status."""
    print(f"\n\nSYSTEM STATUS:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Check total orders
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM orders 
        GROUP BY status
        ORDER BY count DESC
    """)
    
    status_counts = cursor.fetchall()
    
    print("All orders by status:")
    for status, count in status_counts:
        print(f"  {status}: {count}")
    
    # Check recent orders
    cursor.execute("""
        SELECT id, ticker, order_role, status, ib_order_id, created_at
        FROM orders 
        WHERE created_at > datetime('now', '-10 minutes')
        ORDER BY created_at DESC
    """)
    
    recent_orders = cursor.fetchall()
    
    if recent_orders:
        print(f"\nRecent orders (last 10 minutes):")
        for order in recent_orders:
            print(f"  ID {order[0]}: {order[1]} - {order[2]} -> {order[3]} (IB: {order[4]})")
    else:
        print(f"\nNo recent orders found")
    
    # Check configuration
    cursor.execute("""
        SELECT key, value 
        FROM config 
        WHERE key IN ('ALLOW_EXTENDED_HOURS', 'QUEUE_DAY_ORDERS', 'ORDER_MODE')
    """)
    
    config = cursor.fetchall()
    
    print(f"\nConfiguration:")
    for key, value in config:
        print(f"  {key}: {value}")
    
    conn.close()

def main():
    print("TEST REAL ORDER CREATION SYSTEM")
    print("=" * 80)
    print("Pandas is installed - testing full functionality")
    
    # Check current status
    check_system_status()
    
    # Create new test orders
    success = create_new_test_orders()
    
    # Check final status
    check_system_status()
    
    if success:
        print(f"\n\nREAL SYSTEM WORKING!")
        print("New orders created using actual order_manager")
        print("They should be submitted to IB based on current settings")
    else:
        print(f"\n\nREAL SYSTEM ISSUES")
        print("Check IB Gateway connection and configuration")

if __name__ == "__main__":
    main()
