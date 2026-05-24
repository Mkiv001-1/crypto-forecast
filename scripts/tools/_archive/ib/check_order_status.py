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

def check_order_status():
    """Check current order status in database and IB."""
    print("CHECKING ORDER STATUS:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Get all orders with their status
    cursor.execute("""
        SELECT id, ticker, order_role, status, ib_order_id, 
               quantity, limit_price, stop_price, created_at, 
               submitted_at, trade_uid
        FROM orders 
        ORDER BY created_at DESC
    """)
    
    orders = cursor.fetchall()
    
    print(f"TOTAL ORDERS: {len(orders)}")
    print(f"{'ID':<5} {'TICKER':<12} {'ROLE':<12} {'STATUS':<12} {'IB_ID':<8} {'QTY':<6} {'PRICE':<10} {'CREATED':<20}")
    print("-" * 100)
    
    for order in orders:
        order_id, ticker, role, status, ib_id, quantity, limit_price, stop_price, created_at, submitted_at, trade_uid = order
        
        # Format price
        if limit_price:
            price_str = f"${limit_price:.2f}"
        elif stop_price:
            price_str = f"Stop ${stop_price:.2f}"
        else:
            price_str = "MKT"
        
        # Format created time
        created_str = created_at[:19] if created_at else "N/A"
        
        print(f"{order_id:<5} {ticker:<12} {role:<12} {status:<12} {ib_id:<8} {quantity:<6.0f} {price_str:<10} {created_str:<20}")
    
    # Check status summary
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM orders 
        GROUP BY status
        ORDER BY count DESC
    """)
    
    status_summary = cursor.fetchall()
    
    print(f"\nSTATUS SUMMARY:")
    for status, count in status_summary:
        print(f"  {status}: {count}")
    
    # Check recent orders (last 10 minutes)
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM orders 
        WHERE created_at > datetime('now', '-10 minutes')
    """)
    
    recent_count = cursor.fetchone()[0]
    print(f"\nRECENT ORDERS (last 10 minutes): {recent_count}")
    
    conn.close()

def check_ib_order_status():
    """Check order status directly from IB Gateway."""
    print(f"\n\nCHECKING IB GATEWAY ORDER STATUS:")
    print("=" * 80)
    
    try:
        from scripts.core.ib_gateway_client import (
            fetch_open_order_statuses,
            test_ib_connection
        )
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    # Test IB connection
    try:
        connection_result = test_ib_connection("127.0.0.1", 7497, 1)
        
        if not connection_result.get('connected', False):
            print(f"IB Gateway not connected: {connection_result.get('error', 'Unknown error')}")
            return False
        
        print(f"IB Gateway: CONNECTED")
        
        # Get open orders from IB
        open_orders = fetch_open_order_statuses("127.0.0.1", 7497, 1)
        
        if open_orders:
            print(f"OPEN ORDERS IN IB: {len(open_orders)}")
            for order in open_orders:
                print(f"  Order ID: {order.get('orderId', 'N/A')}")
                print(f"  Symbol: {order.get('symbol', 'N/A')}")
                print(f"  Action: {order.get('action', 'N/A')}")
                print(f"  Quantity: {order.get('totalQuantity', 'N/A')}")
                print(f"  Order Type: {order.get('orderType', 'N/A')}")
                print(f"  Status: {order.get('status', 'N/A')}")
                print(f"  Price: {order.get('lmtPrice', 'N/A')}")
                print(f"  ---")
        else:
            print(f"NO OPEN ORDERS IN IB")
            print(f"All orders may be filled or cancelled")
        
        return True
        
    except Exception as e:
        print(f"Error checking IB orders: {e}")
        return False

def check_recent_activity():
    """Check recent trading activity."""
    print(f"\n\nCHECKING RECENT ACTIVITY:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Check recent fills
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM orders 
        WHERE status = 'FILLED_ENTRY' 
        AND created_at > datetime('now', '-1 hour')
    """)
    
    recent_fills = cursor.fetchone()[0]
    print(f"RECENT FILLS (last hour): {recent_fills}")
    
    # Check recent submissions
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM orders 
        WHERE status = 'SUBMITTED' 
        AND created_at > datetime('now', '-1 hour')
    """)
    
    recent_submissions = cursor.fetchone()[0]
    print(f"RECENT SUBMISSIONS (last hour): {recent_submissions}")
    
    # Check IB transactions
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM ib_transactions 
        WHERE created_at > datetime('now', '-1 hour')
    """)
    
    recent_ib_transactions = cursor.fetchone()[0]
    print(f"RECENT IB TRANSACTIONS (last hour): {recent_ib_transactions}")
    
    # Show latest orders with details
    cursor.execute("""
        SELECT id, ticker, order_role, status, ib_order_id, 
               quantity, limit_price, created_at, submitted_at
        FROM orders 
        WHERE created_at > datetime('now', '-30 minutes')
        ORDER BY created_at DESC
        LIMIT 10
    """)
    
    latest_orders = cursor.fetchall()
    
    if latest_orders:
        print(f"\nLATEST ORDERS (last 30 minutes):")
        for order in latest_orders:
            order_id, ticker, role, status, ib_id, quantity, limit_price, created_at, submitted_at = order
            print(f"  ID {order_id}: {ticker} - {role}")
            print(f"    Status: {status}, IB ID: {ib_id}")
            print(f"    Quantity: {quantity}, Limit: ${limit_price}")
            print(f"    Created: {created_at}")
            print(f"    Submitted: {submitted_at}")
            print(f"    ---")
    
    conn.close()

def main():
    print("CHECKING IF ORDERS ARE PLACED")
    print("=" * 80)
    
    # Check order status in database
    check_order_status()
    
    # Check IB Gateway status
    ib_connected = check_ib_order_status()
    
    # Check recent activity
    check_recent_activity()
    
    print(f"\n\nSUMMARY:")
    print("=" * 80)
    
    if ib_connected:
        print("IB Gateway is connected and accessible")
        print("Order status check completed")
    else:
        print("IB Gateway connection issues")
        print("Cannot verify order status in IB")

if __name__ == "__main__":
    main()
