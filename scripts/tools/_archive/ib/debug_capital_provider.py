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

def debug_capital_provider():
    """Debug capital provider to find why position sizing fails."""
    print("DEBUGGING CAPITAL PROVIDER:")
    print("=" * 80)
    
    # Check accounts table data
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM accounts")
    accounts = cursor.fetchall()
    
    # Get column names
    cursor.execute("PRAGMA table_info(accounts)")
    columns = [desc[1] for desc in cursor.fetchall()]
    
    print("Accounts table data:")
    for account in accounts:
        print(f"  {dict(zip(columns, account))}")
    
    conn.close()
    
    # Test capital provider functions
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.capital_provider import get_net_liquidation, _get_account_from_db, _preferred_type
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    print(f"\nTesting capital provider functions:")
    
    # Test preferred type
    preferred = _preferred_type(db_manager)
    print(f"  Preferred account type: {preferred}")
    
    # Test _get_account_from_db
    account = _get_account_from_db(db_manager, preferred)
    print(f"  Best account found: {account}")
    
    # Test get_net_liquidation
    try:
        net_liq = get_net_liquidation(db_manager)
        print(f"  Net liquidation: {net_liq}")
        
        if net_liq > 0:
            print(f"  SUCCESS: Capital provider working!")
            return True
        else:
            print(f"  FAILED: Net liquidation is 0")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_position_sizing_directly():
    """Test position sizing directly with capital provider."""
    print(f"\n\nTESTING POSITION SIZING DIRECTLY:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.position_sizer import calculate_position
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Test position sizing for MSFT
    ticker = "NASDAQ:MSFT"
    entry_price = 435.0
    stop_loss = 420.0
    
    print(f"Testing position sizing for {ticker}:")
    print(f"  Entry: ${entry_price}")
    print(f"  Stop: ${stop_loss}")
    
    try:
        result = calculate_position(
            ticker=ticker,
            entry_price=entry_price,
            stop_loss=stop_loss,
            db_manager=db_manager
        )
        
        print(f"  Result: {result}")
        
        if result.get('status') == 'OK':
            print(f"  SUCCESS: Position sizing worked!")
            print(f"    Quantity: {result.get('quantity')}")
            print(f"    Risk amount: ${result.get('risk_amount', 0):,.2f}")
            print(f"    Position value: ${result.get('position_value', 0):,.2f}")
            print(f"    Capital source: {result.get('capital_source')}")
            return True
        else:
            print(f"  FAILED: {result.get('status')}")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("DEBUG CAPITAL PROVIDER AND POSITION SIZING")
    print("=" * 80)
    
    # Debug capital provider
    capital_works = debug_capital_provider()
    
    # Test position sizing
    if capital_works:
        sizing_works = test_position_sizing_directly()
        
        print(f"\n\nFINAL RESULT:")
        print("=" * 80)
        
        if sizing_works:
            print("SUCCESS: Both capital provider and position sizing work!")
            print("Position sizing problem is SOLVED!")
        else:
            print("FAILED: Position sizing still has issues")
    else:
        print(f"\n\nRESULT:")
        print("=" * 80)
        print("FAILED: Capital provider has issues")
        print("Fix capital provider first")

if __name__ == "__main__":
    main()
