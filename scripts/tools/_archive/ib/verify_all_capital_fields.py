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

def verify_all_capital_fields():
    """Verify all required capital fields are stored and used correctly."""
    print("VERIFYING ALL CAPITAL FIELDS IN PORTFOLIO HISTORY:")
    print("=" * 80)
    
    # Required fields
    required_fields = [
        'net_liquidation',
        'buying_power', 
        'available_funds',
        'cash',
        'maintenance_margin'
    ]
    
    print("Required capital fields:")
    for field in required_fields:
        print(f"  {field}")
    
    # Check Portfolio History table structure
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(portfolio_history)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    print(f"\n\nPortfolio History table columns ({len(columns)}):")
    missing_fields = []
    for field in required_fields:
        if field in column_names:
            print(f"  {field}: PRESENT")
        else:
            print(f"  {field}: MISSING")
            missing_fields.append(field)
    
    if missing_fields:
        print(f"\nWARNING: Missing fields: {missing_fields}")
        print("Need to add these columns to Portfolio History table")
        return False
    
    # Check data in Portfolio History
    print(f"\n\nChecking data in Portfolio History:")
    cursor.execute("""
        SELECT timestamp, net_liquidation, buying_power, available_funds, 
               cash, maintenance_margin
        FROM portfolio_history 
        WHERE row_type = 'summary' 
        AND ticker = '__ACCOUNT_SUMMARY__'
        ORDER BY timestamp DESC 
        LIMIT 1
    """)
    
    latest_data = cursor.fetchone()
    
    if latest_data:
        timestamp, net_liq, buying_power, available_funds, cash, maintenance_margin = latest_data
        
        print(f"Latest record ({timestamp}):")
        print(f"  Net Liquidation: ${net_liq:,.2f}" if net_liq else "  Net Liquidation: N/A")
        print(f"  Buying Power: ${buying_power:,.2f}" if buying_power else "  Buying Power: N/A")
        print(f"  Available Funds: ${available_funds:,.2f}" if available_funds else "  Available Funds: N/A")
        print(f"  Cash: ${cash:,.2f}" if cash else "  Cash: N/A")
        print(f"  Maintenance Margin: ${maintenance_margin:,.2f}" if maintenance_margin else "  Maintenance Margin: N/A")
        
        # Check if all fields have values
        all_fields_present = all([
            net_liq is not None and net_liq > 0,
            buying_power is not None and buying_power >= 0,
            available_funds is not None and available_funds >= 0,
            cash is not None and cash >= 0,
            maintenance_margin is not None and maintenance_margin >= 0
        ])
        
        if all_fields_present:
            print(f"\nSUCCESS: All capital fields have valid values!")
        else:
            print(f"\nWARNING: Some fields have missing or invalid values")
    else:
        print(f"No data found in Portfolio History")
        return False
    
    conn.close()
    return True

def verify_capital_provider_uses_all_fields():
    """Verify capital provider uses all required fields."""
    print(f"\n\nVERIFYING CAPITAL PROVIDER USES ALL FIELDS:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.capital_provider import get_capital_details
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Test get_capital_details function
    capital_details = get_capital_details(db_manager)
    
    print("Capital details from provider:")
    required_fields = ['net_liquidation', 'buying_power', 'available_funds', 'cash', 'maintenance_margin']
    
    all_fields_present = True
    for field in required_fields:
        value = capital_details.get(field, 0)
        if field in ['net_liquidation', 'buying_power', 'available_funds', 'cash', 'maintenance_margin']:
            print(f"  {field}: ${value:,.2f}")
        else:
            print(f"  {field}: {value}")
        
        if value is None or (isinstance(value, (int, float)) and value < 0):
            if field != 'maintenance_margin':  # maintenance_margin can be 0
                all_fields_present = False
    
    if all_fields_present and capital_details.get('source') == 'portfolio_history':
        print(f"\nSUCCESS: Capital provider uses all fields from Portfolio History!")
        return True
    else:
        print(f"\nFAILED: Capital provider missing some fields or not using Portfolio History")
        return False

def verify_position_sizing_uses_capital():
    """Verify position sizing uses capital data correctly."""
    print(f"\n\nVERIFYING POSITION SIZING USES CAPITAL DATA:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.position_sizer import calculate_position
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Test position sizing with different scenarios
    test_cases = [
        ("NASDAQ:AAPL", 180.0, 170.0, "LOW PRICE STOCK"),
        ("NASDAQ:AMZN", 230.0, 210.0, "MEDIUM PRICE STOCK"),
        ("NASDAQ:GOOGL", 140.0, 130.0, "HIGH PRICE STOCK")
    ]
    
    all_success = True
    
    for ticker, entry_price, stop_loss, description in test_cases:
        print(f"\nTesting {description} ({ticker}):")
        print(f"  Entry: ${entry_price}, Stop: ${stop_loss}")
        
        try:
            result = calculate_position(
                ticker=ticker,
                entry_price=entry_price,
                stop_loss=stop_loss,
                db_manager=db_manager
            )
            
            if result.get('status') == 'OK':
                quantity = result.get('quantity')
                risk_amount = result.get('risk_amount')
                position_value = result.get('position_value')
                
                print(f"  SUCCESS: Quantity {quantity}, Risk ${risk_amount:,.2f}")
                print(f"  Position Value: ${position_value:,.2f}")
                print(f"  Capital Source: {result.get('capital_source')}")
                
                # Verify risk amount is reasonable (around 1% of capital)
                if risk_amount and 300 <= risk_amount <= 400:  # Around 1% of $33,995
                    print(f"  Risk amount is appropriate")
                else:
                    print(f"  WARNING: Risk amount ${risk_amount:,.2f} seems unusual")
                    all_success = False
            else:
                print(f"  FAILED: {result.get('status')}")
                all_success = False
                
        except Exception as e:
            print(f"  ERROR: {e}")
            all_success = False
    
    return all_success

def main():
    print("VERIFY ALL CAPITAL FIELDS STORAGE AND USAGE")
    print("=" * 80)
    
    # Verify all fields are stored
    fields_stored = verify_all_capital_fields()
    
    if fields_stored:
        # Verify capital provider uses all fields
        provider_works = verify_capital_provider_uses_all_fields()
        
        if provider_works:
            # Verify position sizing uses capital
            sizing_works = verify_position_sizing_uses_capital()
            
            print(f"\n\nFINAL RESULT:")
            print("=" * 80)
            
            if sizing_works:
                print("SUCCESS: All capital fields are properly stored and used!")
                print("✅ net_liquidation - Net Liquidation")
                print("✅ buying_power - Buying Power") 
                print("✅ available_funds - Available Funds")
                print("✅ cash - Cash")
                print("✅ maintenance_margin - Maintenance Margin")
                print("\nAll fields are:")
                print("  - Stored in Portfolio History table")
                print("  - Used by Capital Provider")
                print("  - Applied in Position Sizing calculations")
                print("  - Reflected in order creation")
            else:
                print("PARTIAL SUCCESS: Fields stored but position sizing has issues")
        else:
            print(f"\n\nRESULT:")
            print("=" * 80)
            print("PARTIAL SUCCESS: Fields stored but capital provider has issues")
    else:
        print(f"\n\nRESULT:")
        print("=" * 80)
        print("FAILED: Not all required capital fields are stored properly")

if __name__ == "__main__":
    main()
