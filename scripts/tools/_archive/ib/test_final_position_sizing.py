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

def get_config_value(db_path, key, default=None):
    """Get configuration value from database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else default

def sync_ib_data():
    """Sync account and portfolio data from IB."""
    print("SYNCING IB DATA:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.ib_gateway_client import (
            sync_accounts_with_ib_safe,
            sync_portfolio_with_ib_safe,
            fetch_ib_portfolio_summary
        )
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Sync accounts
    print("Syncing accounts...")
    try:
        accounts_result = sync_accounts_with_ib_safe(db_manager)
        print(f"  Result: {accounts_result}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Sync portfolio
    print("Syncing portfolio...")
    try:
        portfolio_result = sync_portfolio_with_ib_safe(db_manager)
        print(f"  Result: {portfolio_result}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Get portfolio summary
    print("Getting portfolio summary...")
    try:
        summary = fetch_ib_portfolio_summary(db_manager)
        print(f"  Summary: {summary}")
        
        if summary and 'net_liquidation' in summary:
            print(f"  SUCCESS: Net Liquidation: ${summary['net_liquidation']:,.2f}")
            return True
        else:
            print(f"  WARNING: No net liquidation data")
            return False
            
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_position_sizing():
    """Test position sizing with real IB data."""
    print(f"\n\nTESTING POSITION SIZING WITH IB DATA:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.order_manager import submit_signal
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Check account data first
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT net_liquidation, available_funds, buying_power 
        FROM accounts 
        ORDER BY updated_at DESC 
        LIMIT 1
    """)
    
    account_data = cursor.fetchone()
    conn.close()
    
    if account_data and account_data[0]:
        print(f"Account data available:")
        print(f"  Net Liquidation: ${account_data[0]:,.2f}")
        print(f"  Available Funds: ${account_data[1]:,.2f}" if account_data[1] else "  Available Funds: N/A")
        print(f"  Buying Power: ${account_data[2]:,.2f}" if account_data[2] else "  Buying Power: N/A")
    else:
        print("No account data found - position sizing may fail")
    
    # Test order creation
    test_consensus = {
        'ticker': 'NASDAQ:MSFT',
        'signal': 'LONG',
        'confidence': 75.0,
        'target_price': 450.0,
        'stop_loss': 420.0,
        'entry_limit_price': 435.0,
        'forecasts': []
    }
    
    position_size = {
        'quantity': 3,  # Small test size
        'capital_allocated': 3000
    }
    
    print(f"\nTesting order creation for MSFT...")
    print(f"  Entry: ${test_consensus['entry_limit_price']}")
    print(f"  Target: ${test_consensus['target_price']}")
    print(f"  Stop: ${test_consensus['stop_loss']}")
    
    try:
        result = submit_signal(
            ticker='NASDAQ:MSFT',
            consensus=test_consensus,
            position_size=position_size,
            db_manager=db_manager
        )
        
        print(f"  Result: {result}")
        
        if result and result.get('status') not in ['UNKNOWN', None]:
            print(f"  SUCCESS: Position sizing worked!")
            print(f"    Status: {result.get('status')}")
            print(f"    Order IDs: {result.get('order_ids', [])}")
            print(f"    IB IDs: {result.get('ib_ids', {})}")
            return True
        else:
            print(f"  FAILED: Position sizing still unknown")
            print(f"    Message: {result.get('message', 'No message')}")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("TEST POSITION SIZING WITH IB DATA")
    print("=" * 80)
    print("ib_insync is installed - testing full functionality")
    
    # Sync IB data
    data_synced = sync_ib_data()
    
    # Test position sizing
    if data_synced:
        sizing_works = test_position_sizing()
        
        print(f"\n\nFINAL RESULT:")
        print("=" * 80)
        
        if sizing_works:
            print("SUCCESS: Position sizing now works with IB data!")
            print("The system can now create orders with proper sizing")
            print("Orders will be submitted to IB with correct quantities")
        else:
            print("FAILED: Position sizing still has issues")
            print("Check order_manager.py position sizing logic")
    else:
        print(f"\n\nFAILED: Could not sync IB data")
        print("Position sizing cannot work without account data")

if __name__ == "__main__":
    main()
