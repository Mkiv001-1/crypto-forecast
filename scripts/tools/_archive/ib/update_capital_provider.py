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

def get_capital_from_portfolio_history(db_path: str) -> dict:
    """Get capital data from portfolio_history table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get the most recent account summary from portfolio_history
        cursor.execute("""
            SELECT net_liquidation, buying_power, available_funds, 
                   cash, maintenance_margin, timestamp
            FROM portfolio_history 
            WHERE row_type = 'summary' 
            AND ticker = '__ACCOUNT_SUMMARY__'
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        
        if result:
            net_liquidation, buying_power, available_funds, cash, maintenance_margin, timestamp = result
            
            return {
                'net_liquidation': float(net_liquidation) if net_liquidation else 0.0,
                'buying_power': float(buying_power) if buying_power else 0.0,
                'available_funds': float(available_funds) if available_funds else 0.0,
                'cash': float(cash) if cash else 0.0,
                'maintenance_margin': float(maintenance_margin) if maintenance_margin else 0.0,
                'timestamp': timestamp,
                'source': 'portfolio_history'
            }
        else:
            return {'net_liquidation': 0.0, 'source': 'portfolio_history_empty'}
            
    except Exception as e:
        print(f"Error getting capital from portfolio_history: {e}")
        return {'net_liquidation': 0.0, 'source': 'portfolio_history_error'}
    finally:
        conn.close()

def test_portfolio_history_capital():
    """Test getting capital data from portfolio_history."""
    print("TESTING CAPITAL DATA FROM PORTFOLIO HISTORY:")
    print("=" * 80)
    
    capital_data = get_capital_from_portfolio_history(_get_db_path())
    
    print("Capital data from portfolio_history:")
    for key, value in capital_data.items():
        if key == 'net_liquidation' and isinstance(value, (int, float)):
            print(f"  {key}: ${value:,.2f}")
        else:
            print(f"  {key}: {value}")
    
    if capital_data.get('net_liquidation', 0) > 0:
        print(f"\nSUCCESS: Portfolio History has capital data!")
        return True
    else:
        print(f"\nFAILED: No capital data in Portfolio History")
        return False

def create_new_capital_provider_function():
    """Create a new capital provider function that uses portfolio_history."""
    print(f"\n\nCREATING NEW CAPITAL PROVIDER FUNCTION:")
    print("=" * 80)
    
    new_function_code = '''
def get_net_liquidation_from_portfolio_history(db_manager) -> float:
    """
    Return NetLiquidation from portfolio_history table.
    
    This function replaces the old accounts-based approach with portfolio_history.
    """
    try:
        import sqlite3
        with sqlite3.connect(db_manager.db_file) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                """
                SELECT net_liquidation, timestamp 
                FROM portfolio_history 
                WHERE row_type = 'summary' 
                AND ticker = '__ACCOUNT_SUMMARY__'
                ORDER BY timestamp DESC 
                LIMIT 1
                """
            ).fetchone()
            
            if row and row["net_liquidation"]:
                net_liq = float(row["net_liquidation"])
                logger.debug(f"capital_provider: NetLiquidation={net_liq:,.2f} from portfolio_history (timestamp={row['timestamp']})")
                return net_liq
            else:
                logger.warning("capital_provider: No data found in portfolio_history")
                return 0.0
                
    except Exception as e:
        logger.error(f"capital_provider: portfolio_history read error: {e}")
        return 0.0
'''
    
    print("New function code:")
    print(new_function_code)
    
    # Save to file for reference
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'new_capital_provider_function.py'), 'w') as f:
        f.write(new_function_code)
    
    print("Saved to: new_capital_provider_function.py")
    return new_function_code

def test_position_sizing_with_portfolio_history():
    """Test position sizing using portfolio_history data."""
    print(f"\n\nTESTING POSITION SIZING WITH PORTFOLIO HISTORY:")
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
            print(f"  SUCCESS: Position sizing works!")
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
    print("UPDATE CAPITAL PROVIDER TO USE PORTFOLIO HISTORY")
    print("=" * 80)
    
    # Test portfolio history capital data
    capital_works = test_portfolio_history_capital()
    
    if capital_works:
        # Create new capital provider function
        create_new_capital_provider_function()
        
        # Test position sizing
        sizing_works = test_position_sizing_with_portfolio_history()
        
        print(f"\n\nRESULT:")
        print("=" * 80)
        
        if sizing_works:
            print("SUCCESS: Portfolio History can be used for capital data!")
            print("Next steps:")
            print("1. Update capital_provider.py to use portfolio_history")
            print("2. Test complete order creation")
            print("3. Verify position sizing uses Portfolio History data")
        else:
            print("FAILED: Position sizing still has issues")
    else:
        print(f"\n\nRESULT:")
        print("=" * 80)
        print("FAILED: Portfolio History doesn't have capital data")
        print("Need to sync portfolio data first")

if __name__ == "__main__":
    main()
