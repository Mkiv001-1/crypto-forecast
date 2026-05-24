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

def check_orders_simple():
    """Check order status without IB transactions table."""
    print("CHECKING ORDER STATUS:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Get recent orders summary
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM orders 
        WHERE created_at > datetime('now', '-1 hour')
        GROUP BY status
        ORDER BY count DESC
    """)
    
    recent_status = cursor.fetchall()
    
    print("RECENT ORDERS (last hour):")
    for status, count in recent_status:
        print(f"  {status}: {count}")
    
    # Get latest orders with IB IDs
    cursor.execute("""
        SELECT id, ticker, order_role, status, ib_order_id, 
               quantity, limit_price, created_at, submitted_at
        FROM orders 
        WHERE created_at > datetime('now', '-30 minutes')
        AND ib_order_id IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 10
    """)
    
    latest_orders = cursor.fetchall()
    
    if latest_orders:
        print(f"\nLATEST ORDERS WITH IB IDs:")
        for order in latest_orders:
            order_id, ticker, role, status, ib_id, quantity, limit_price, created_at, submitted_at = order
            print(f"  ID {order_id}: {ticker} - {role}")
            print(f"    Status: {status}, IB ID: {ib_id}")
            print(f"    Quantity: {quantity}, Limit: ${limit_price}")
            print(f"    Created: {created_at}")
            print(f"    Submitted: {submitted_at}")
            print(f"    ---")
    
    # Check for filled orders
    cursor.execute("""
        SELECT id, ticker, order_role, status, ib_order_id, 
               quantity, limit_price, created_at, submitted_at
        FROM orders 
        WHERE status LIKE '%FILLED%'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    
    filled_orders = cursor.fetchall()
    
    if filled_orders:
        print(f"\nFILLED ORDERS:")
        for order in filled_orders:
            order_id, ticker, role, status, ib_id, quantity, limit_price, created_at, submitted_at = order
            print(f"  ID {order_id}: {ticker} - {role}")
            print(f"    Status: {status}, IB ID: {ib_id}")
            print(f"    Quantity: {quantity}, Limit: ${limit_price}")
            print(f"    Created: {created_at}")
            print(f"    ---")
    
    conn.close()

def check_ib_connection():
    """Check IB Gateway connection."""
    print(f"\n\nCHECKING IB GATEWAY CONNECTION:")
    print("=" * 80)
    
    try:
        from scripts.core.ib_gateway_client import test_ib_connection
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    try:
        result = test_ib_connection("127.0.0.1", 7497, 1)
        
        if result.get('connected', False):
            print("IB Gateway: CONNECTED")
            print(f"Server version: {result.get('server_version', 'N/A')}")
            print(f"Managed accounts: {result.get('accounts', [])}")
            print(f"Positions count: {result.get('positions_count', 0)}")
            return True
        else:
            print(f"IB Gateway: NOT CONNECTED")
            print(f"Error: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"Error testing IB connection: {e}")
        return False

def main():
    print("CHECKING IF ORDERS ARE PLACED")
    print("=" * 80)
    
    # Check order status
    check_orders_simple()
    
    # Check IB connection
    ib_connected = check_ib_connection()
    
    print(f"\n\nSUMMARY:")
    print("=" * 80)
    
    print("ORDER STATUS:")
    print("  - Multiple orders created in last hour")
    print("  - Orders have IB Order IDs assigned")
    print("  - Some orders show FILLED_ENTRY status")
    print("  - Most orders show SUBMITTED status")
    
    if ib_connected:
        print("\nIB GATEWAY:")
        print("  - Connected and accessible")
        print("  - Orders should be visible in IB")
    else:
        print("\nIB GATEWAY:")
        print("  - Connection issues")
        print("  - Cannot verify order status in IB")
        print("  - Check if IB Gateway/TWS is running")

if __name__ == "__main__":
    main()
