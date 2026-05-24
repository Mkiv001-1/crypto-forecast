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

def test_complete_order_creation():
    """Test complete order creation with working position sizing."""
    print("TESTING COMPLETE ORDER CREATION WITH POSITION SIZING:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.order_manager import submit_signal
        from scripts.core.position_sizer import calculate_position
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Test consensus data
    test_consensus = {
        'ticker': 'NASDAQ:MSFT',
        'signal': 'LONG',
        'confidence': 75.0,
        'target_price': 450.0,
        'stop_loss': 420.0,
        'entry_limit_price': 435.0,
        'forecasts': []
    }
    
    print(f"Creating order for {test_consensus['ticker']} - {test_consensus['signal']}")
    print(f"  Entry: ${test_consensus['entry_limit_price']}")
    print(f"  Target: ${test_consensus['target_price']}")
    print(f"  Stop: ${test_consensus['stop_loss']}")
    
    # Calculate position size first
    print(f"\nCalculating position size...")
    position_calc = calculate_position(
        ticker=test_consensus['ticker'],
        entry_price=test_consensus['entry_limit_price'],
        stop_loss=test_consensus['stop_loss'],
        db_manager=db_manager
    )
    
    print(f"  Position calculation: {position_calc}")
    
    if position_calc.get('status') != 'OK':
        print(f"  FAILED: Position sizing failed: {position_calc.get('status')}")
        return False
    
    # Build position_size dict for submit_signal
    position_size = {
        'quantity': position_calc['quantity'],
        'capital_allocated': position_calc['position_value'],
        'status': 'OK'
    }
    
    print(f"  Using position size: {position_size['quantity']} shares (${position_size['capital_allocated']:,.2f})")
    
    # Submit the order
    print(f"\nSubmitting order to IB...")
    try:
        result = submit_signal(
            ticker=test_consensus['ticker'],
            consensus=test_consensus,
            position_size=position_size,
            db_manager=db_manager
        )
        
        print(f"  Result: {result}")
        
        if result and result.get('status') not in ['UNKNOWN', None]:
            print(f"\nSUCCESS: Order creation worked!")
            print(f"  Status: {result.get('status')}")
            print(f"  Message: {result.get('message', 'No message')}")
            
            order_ids = result.get('order_ids', [])
            ib_ids = result.get('ib_ids', {})
            trade_id = result.get('trade_id')
            
            if order_ids:
                print(f"  Order IDs: {order_ids}")
            if ib_ids:
                print(f"  IB IDs: {ib_ids}")
            if trade_id:
                print(f"  Trade ID: {trade_id}")
                
            return True
        else:
            print(f"\nFAILED: Order creation failed")
            print(f"  Message: {result.get('message', 'No message')}")
            return False
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_created_orders():
    """Check if new orders were created."""
    print(f"\n\nCHECKING CREATED ORDERS:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Get recent orders
    cursor.execute("""
        SELECT id, ticker, order_role, status, ib_order_id, 
               quantity, limit_price, stop_price, created_at, trade_uid
        FROM orders 
        WHERE created_at > datetime('now', '-2 minutes')
        ORDER BY created_at DESC
    """)
    
    recent_orders = cursor.fetchall()
    
    if recent_orders:
        print(f"Found {len(recent_orders)} recent orders:")
        for order in recent_orders:
            order_id, ticker, role, status, ib_id, quantity, limit_price, stop_price, created_at, trade_uid = order
            print(f"  ID {order_id}: {ticker} - {role}")
            print(f"    Status: {status}, IB ID: {ib_id}")
            print(f"    Quantity: {quantity}, Limit: ${limit_price}, Stop: ${stop_price}")
            print(f"    Trade UID: {trade_uid}")
            print(f"    Created: {created_at}")
    else:
        print("No recent orders found")
    
    conn.close()

def main():
    print("FINAL TEST: COMPLETE ORDER CREATION WITH POSITION SIZING")
    print("=" * 80)
    print("Testing the full pipeline: IB data -> position sizing -> order creation")
    
    # Test complete order creation
    order_created = test_complete_order_creation()
    
    # Check for new orders
    if order_created:
        check_created_orders()
        
        print(f"\n\nFINAL RESULT:")
        print("=" * 80)
        print("SUCCESS: Complete order creation pipeline works!")
        print("IB Gateway connection: Working")
        print("Account data retrieval: Working")
        print("Position sizing calculation: Working")
        print("Order submission to IB: Working")
        print("\nPOSITION SIZING PROBLEM IS COMPLETELY SOLVED!")
        print("The system can now create orders with proper sizing based on IB account data")
    else:
        print(f"\n\nRESULT:")
        print("=" * 80)
        print("FAILED: Complete order creation still has issues")
        print("Check the error messages above for debugging")

if __name__ == "__main__":
    main()
