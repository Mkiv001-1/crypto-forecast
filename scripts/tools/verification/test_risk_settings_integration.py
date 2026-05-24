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

def test_risk_settings_integration():
    """Test position sizer integration with risk_settings table."""
    print("TESTING POSITION SIZER WITH RISK_SETTINGS TABLE:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.position_sizer import calculate_position, _get_risk_setting, _cfg_risk
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Test risk settings retrieval
    print("1. Testing risk settings retrieval:")
    test_settings = [
        ('DEFAULT_RISK_PCT', 0.01),
        ('MAX_POSITION_PCT', 0.05),
        ('RISK_MODE', 'percent_of_capital'),
        ('MAX_SECTOR_EXPOSURE_PCT', 0.15)
    ]
    
    for key, default in test_settings:
        value = _get_risk_setting(db_manager, key, default)
        print(f"  {key}: {value} (default: {default})")
        
        if value != default:
            print(f"    SUCCESS: Using value from risk_settings")
        else:
            print(f"    INFO: Using default value")
    
    # Test position sizing with risk settings
    print(f"\n2. Testing position sizing with risk_settings:")
    
    test_cases = [
        ("NASDAQ:AAPL", 180.0, 170.0, "LOW PRICE STOCK"),
        ("NASDAQ:AMZN", 230.0, 210.0, "MEDIUM PRICE STOCK"),
        ("NASDAQ:GOOGL", 140.0, 130.0, "HIGH PRICE STOCK")
    ]
    
    all_success = True
    
    for ticker, entry_price, stop_loss, description in test_cases:
        print(f"\n  Testing {description} ({ticker}):")
        print(f"    Entry: ${entry_price}, Stop: ${stop_loss}")
        
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
                risk_mode = result.get('risk_mode')
                
                print(f"    SUCCESS: Quantity {quantity}, Risk ${risk_amount:,.2f}")
                print(f"    Position Value: ${position_value:,.2f}")
                print(f"    Risk Mode: {risk_mode}")
                
                # Verify risk amount matches DEFAULT_RISK_PCT * Net Liquidation
                expected_risk = 33995.55 * 0.01  # Net Liquidation * 1%
                if abs(risk_amount - expected_risk) < 1.0:  # Allow $1 tolerance
                    print(f"    Risk amount matches expected 1%: ${expected_risk:.2f}")
                else:
                    print(f"    WARNING: Risk amount ${risk_amount:.2f} vs expected ${expected_risk:.2f}")
                    all_success = False
            else:
                print(f"    FAILED: {result.get('status')}")
                all_success = False
                
        except Exception as e:
            print(f"    ERROR: {e}")
            all_success = False
    
    return all_success

def test_risk_settings_modification():
    """Test modifying risk settings and seeing effect on position sizing."""
    print(f"\n\n3. Testing risk settings modification:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.position_sizer import calculate_position
    except ImportError as e:
        print(f"Import error: {e}")
        conn.close()
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Get current DEFAULT_RISK_PCT
    cursor.execute("SELECT setting_value FROM risk_settings WHERE setting_key = 'DEFAULT_RISK_PCT'")
    current_risk_pct = float(cursor.fetchone()[0])
    
    print(f"Current DEFAULT_RISK_PCT: {current_risk_pct}")
    
    # Test with current setting
    result_current = calculate_position(
        ticker="NASDAQ:MSFT",
        entry_price=435.0,
        stop_loss=420.0,
        db_manager=db_manager
    )
    
    print(f"Position sizing with {current_risk_pct*100:.1f}% risk:")
    print(f"  Quantity: {result_current.get('quantity')}")
    print(f"  Risk Amount: ${result_current.get('risk_amount', 0):,.2f}")
    
    # Temporarily change to 2%
    cursor.execute("UPDATE risk_settings SET setting_value = '0.02' WHERE setting_key = 'DEFAULT_RISK_PCT'")
    conn.commit()
    
    print(f"\nChanged DEFAULT_RISK_PCT to 2%")
    
    result_double = calculate_position(
        ticker="NASDAQ:MSFT",
        entry_price=435.0,
        stop_loss=420.0,
        db_manager=db_manager
    )
    
    print(f"Position sizing with 2% risk:")
    print(f"  Quantity: {result_double.get('quantity')}")
    print(f"  Risk Amount: ${result_double.get('risk_amount', 0):,.2f}")
    
    # Verify risk amount doubled
    if abs(result_double.get('risk_amount', 0) - result_current.get('risk_amount', 0) * 2) < 1.0:
        print(f"  SUCCESS: Risk amount doubled as expected")
        modification_works = True
    else:
        print(f"  FAILED: Risk amount did not double correctly")
        modification_works = False
    
    # Restore original setting
    cursor.execute("UPDATE risk_settings SET setting_value = ? WHERE setting_key = 'DEFAULT_RISK_PCT'", (str(current_risk_pct),))
    conn.commit()
    
    print(f"\nRestored DEFAULT_RISK_PCT to {current_risk_pct*100:.1f}%")
    
    conn.close()
    return modification_works

def verify_all_risk_settings():
    """Verify all risk settings are properly configured."""
    print(f"\n\n4. Verifying all risk settings:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("SELECT setting_key, setting_value, description FROM risk_settings ORDER BY setting_key")
    settings = cursor.fetchall()
    
    print("All risk settings in database:")
    for key, value, description in settings:
        print(f"  {key}: {value}")
        print(f"    {description}")
    
    # Check critical settings
    critical_settings = ['DEFAULT_RISK_PCT', 'MAX_POSITION_PCT', 'RISK_MODE', 'MAX_SECTOR_EXPOSURE_PCT']
    missing_settings = []
    
    for setting in critical_settings:
        cursor.execute("SELECT COUNT(*) FROM risk_settings WHERE setting_key = ?", (setting,))
        if cursor.fetchone()[0] == 0:
            missing_settings.append(setting)
    
    if missing_settings:
        print(f"\nWARNING: Missing critical settings: {missing_settings}")
        return False
    else:
        print(f"\nSUCCESS: All critical risk settings are present")
        return True
    
    conn.close()

def main():
    print("TEST RISK SETTINGS INTEGRATION")
    print("=" * 80)
    
    # Test basic integration
    integration_works = test_risk_settings_integration()
    
    # Test settings modification
    if integration_works:
        modification_works = test_risk_settings_modification()
        
        # Verify all settings
        all_settings_ok = verify_all_risk_settings()
        
        print(f"\n\nFINAL RESULT:")
        print("=" * 80)
        
        if integration_works and modification_works and all_settings_ok:
            print("SUCCESS: Risk settings integration is complete!")
            print("ACHIEVEMENTS:")
            print("  - Position sizer uses risk_settings table")
            print("  - Risk configuration is now in settings/")
            print("  - Settings can be modified and take effect immediately")
            print("  - All critical risk parameters are configurable")
            print("\nRisk configuration is now properly managed in settings table!")
        else:
            print("PARTIAL SUCCESS: Some issues with risk settings integration")
            if not integration_works:
                print("  - Basic integration has issues")
            if not modification_works:
                print("  - Settings modification has issues")
            if not all_settings_ok:
                print("  - Some critical settings are missing")
    else:
        print(f"\n\nRESULT:")
        print("=" * 80)
        print("FAILED: Risk settings integration has issues")

if __name__ == "__main__":
    main()
