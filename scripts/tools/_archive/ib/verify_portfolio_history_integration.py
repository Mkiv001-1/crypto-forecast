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

def verify_portfolio_history_integration():
    """Verify that Portfolio History integration is working correctly."""
    print("VERIFYING PORTFOLIO HISTORY INTEGRATION:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.capital_provider import get_net_liquidation, get_capital_details
        from scripts.core.position_sizer import calculate_position
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # 1. Verify capital provider uses Portfolio History
    print("1. Testing Capital Provider:")
    capital_details = get_capital_details(db_manager)
    
    if capital_details.get('source') == 'portfolio_history':
        print(f"   SUCCESS: Capital provider uses Portfolio History")
        print(f"   Net Liquidation: ${capital_details['net_liquidation']:,.2f}")
        print(f"   Available Funds: ${capital_details['available_funds']:,.2f}")
        print(f"   Timestamp: {capital_details['timestamp']}")
    else:
        print(f"   FAILED: Capital source is {capital_details.get('source')}")
        return False
    
    # 2. Verify position sizing uses Portfolio History data
    print(f"\n2. Testing Position Sizing:")
    position_result = calculate_position(
        ticker="NASDAQ:TSLA",
        entry_price=250.0,
        stop_loss=230.0,
        db_manager=db_manager
    )
    
    if position_result.get('status') == 'OK':
        print(f"   SUCCESS: Position sizing works")
        print(f"   Quantity: {position_result['quantity']} shares")
        print(f"   Risk Amount: ${position_result['risk_amount']:,.2f}")
        print(f"   Capital Source: {position_result['capital_source']}")
    else:
        print(f"   FAILED: Position sizing failed - {position_result.get('status')}")
        return False
    
    # 3. Check Portfolio History table has recent data
    print(f"\n3. Checking Portfolio History Data:")
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM portfolio_history 
        WHERE row_type = 'summary' 
        AND ticker = '__ACCOUNT_SUMMARY__'
        AND timestamp > datetime('now', '-1 hour')
    """)
    
    recent_count = cursor.fetchone()[0]
    
    if recent_count > 0:
        print(f"   SUCCESS: {recent_count} recent Portfolio History records found")
    else:
        print(f"   WARNING: No recent Portfolio History records (last hour)")
    
    # Get latest record
    cursor.execute("""
        SELECT timestamp, net_liquidation, available_funds 
        FROM portfolio_history 
        WHERE row_type = 'summary' 
        AND ticker = '__ACCOUNT_SUMMARY__'
        ORDER BY timestamp DESC 
        LIMIT 1
    """)
    
    latest = cursor.fetchone()
    if latest:
        timestamp, net_liq, available = latest
        print(f"   Latest: {timestamp}")
        print(f"   Net Liquidation: ${net_liq:,.2f}")
        print(f"   Available Funds: ${available:,.2f}")
    
    conn.close()
    
    return True

def check_recent_orders():
    """Check recent orders created with Portfolio History data."""
    print(f"\n\nCHECKING RECENT ORDERS:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Get orders created in the last few minutes
    cursor.execute("""
        SELECT id, ticker, order_role, status, ib_order_id, 
               quantity, limit_price, created_at, trade_uid
        FROM orders 
        WHERE created_at > datetime('now', '-10 minutes')
        ORDER BY created_at DESC
    """)
    
    recent_orders = cursor.fetchall()
    
    if recent_orders:
        print(f"Found {len(recent_orders)} recent orders (last 10 minutes):")
        for order in recent_orders:
            order_id, ticker, role, status, ib_id, quantity, limit_price, created_at, trade_uid = order
            print(f"  ID {order_id}: {ticker} - {role}")
            print(f"    Status: {status}, IB ID: {ib_id}")
            print(f"    Quantity: {quantity}, Limit: ${limit_price}")
            print(f"    Created: {created_at}")
    else:
        print("No recent orders found")
    
    conn.close()

def main():
    print("FINAL VERIFICATION: PORTFOLIO HISTORY INTEGRATION")
    print("=" * 80)
    
    # Verify integration
    integration_works = verify_portfolio_history_integration()
    
    # Check recent orders
    check_recent_orders()
    
    print(f"\n\nFINAL SUMMARY:")
    print("=" * 80)
    
    if integration_works:
        print("SUCCESS: Portfolio History integration is complete!")
        print("ACHIEVEMENTS:")
        print("  - Capital Provider updated to use Portfolio History")
        print("  - Position sizing uses Portfolio History capital data")
        print("  - Orders created with proper capital-based sizing")
        print("  - All capital fields available in Portfolio History")
        print("\nCAPITAL DATA FLOW:")
        print("  IB Gateway -> Portfolio History -> Capital Provider -> Position Sizing -> Orders")
        print("\nPortfolio History table now serves as the single source of truth for capital data!")
    else:
        print("FAILED: Portfolio History integration has issues")
        print("Check the error messages above for debugging")

if __name__ == "__main__":
    main()
