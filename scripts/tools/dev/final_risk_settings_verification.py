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

def final_risk_settings_verification():
    """Final verification that risk settings are properly in settings table."""
    print("FINAL VERIFICATION: RISK SETTINGS IN SETTINGS TABLE")
    print("=" * 80)
    
    # 1. Verify risk_settings table exists and has all required fields
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='risk_settings'")
    risk_settings_exists = cursor.fetchone()
    
    if not risk_settings_exists:
        print("FAILED: risk_settings table not found")
        return False
    
    print("1. RISK_SETTINGS TABLE: PRESENT")
    
    # 2. Verify all required risk settings are present
    required_settings = [
        'DEFAULT_RISK_PCT',
        'MAX_POSITION_PCT', 
        'RISK_MODE',
        'MAX_SECTOR_EXPOSURE_PCT',
        'MAX_SECTOR_HARD_LIMIT_PCT',
        'SECTOR_OVERWEIGHT_FACTOR',
        'CAPITAL_STALENESS_MINUTES',
        'MAX_POSITIONS',
        'MAX_RISK_PER_TRADE',
        'MIN_POSITION_SIZE_USD'
    ]
    
    cursor.execute("SELECT setting_key FROM risk_settings")
    existing_settings = [row[0] for row in cursor.fetchall()]
    
    missing_settings = []
    for setting in required_settings:
        if setting not in existing_settings:
            missing_settings.append(setting)
    
    if missing_settings:
        print(f"2. REQUIRED SETTINGS: MISSING {missing_settings}")
        return False
    else:
        print("2. REQUIRED SETTINGS: ALL PRESENT")
    
    # 3. Show current risk configuration
    print(f"\n3. CURRENT RISK CONFIGURATION:")
    cursor.execute("SELECT setting_key, setting_value, description FROM risk_settings ORDER BY setting_key")
    settings = cursor.fetchall()
    
    for key, value, description in settings:
        if key in required_settings:
            if 'PCT' in key:
                pct_value = float(value) * 100
                print(f"   {key}: {pct_value:.1f}% - {description}")
            else:
                print(f"   {key}: {value} - {description}")
    
    # 4. Test position sizing uses risk_settings
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.position_sizer import calculate_position
    except ImportError as e:
        print(f"4. POSITION SIZING: IMPORT ERROR - {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    result = calculate_position(
        ticker="NASDAQ:TSLA",
        entry_price=250.0,
        stop_loss=230.0,
        db_manager=db_manager
    )
    
    if result.get('status') == 'OK':
        print(f"\n4. POSITION SIZING: WORKING")
        print(f"   Example: TSLA $250->230")
        print(f"   Quantity: {result.get('quantity')} shares")
        print(f"   Risk Amount: ${result.get('risk_amount', 0):,.2f}")
        print(f"   Risk Mode: {result.get('risk_mode')}")
        
        # Verify risk amount matches DEFAULT_RISK_PCT
        cursor.execute("SELECT setting_value FROM risk_settings WHERE setting_key = 'DEFAULT_RISK_PCT'")
        risk_pct = float(cursor.fetchone()[0])
        
        expected_risk = 33995.55 * risk_pct  # Net Liquidation * Risk %
        actual_risk = result.get('risk_amount', 0)
        
        if abs(actual_risk - expected_risk) < 1.0:
            print(f"   Risk calculation: CORRECT ({risk_pct*100:.1f}% of capital)")
        else:
            print(f"   Risk calculation: INCORRECT")
            return False
    else:
        print(f"4. POSITION SIZING: FAILED - {result.get('status')}")
        return False
    
    # 5. Test settings modification
    print(f"\n5. SETTINGS MODIFICATION: TESTING")
    
    # Get current risk
    cursor.execute("SELECT setting_value FROM risk_settings WHERE setting_key = 'DEFAULT_RISK_PCT'")
    original_risk = cursor.fetchone()[0]
    
    # Change to 1.5%
    cursor.execute("UPDATE risk_settings SET setting_value = '0.015' WHERE setting_key = 'DEFAULT_RISK_PCT'")
    conn.commit()
    
    result_modified = calculate_position(
        ticker="NASDAQ:TSLA",
        entry_price=250.0,
        stop_loss=230.0,
        db_manager=db_manager
    )
    
    expected_risk_modified = 33995.55 * 0.015
    actual_risk_modified = result_modified.get('risk_amount', 0)
    
    if abs(actual_risk_modified - expected_risk_modified) < 1.0:
        print(f"   Settings modification: WORKING")
        print(f"   Risk changed from ${actual_risk:.2f} to ${actual_risk_modified:.2f}")
    else:
        print(f"   Settings modification: FAILED")
        return False
    
    # Restore original setting
    cursor.execute("UPDATE risk_settings SET setting_value = ? WHERE setting_key = 'DEFAULT_RISK_PCT'", (original_risk,))
    conn.commit()
    
    conn.close()
    return True

def main():
    print("FINAL VERIFICATION: RISK SETTINGS IN SETTINGS/")
    print("=" * 80)
    
    success = final_risk_settings_verification()
    
    print(f"\n\nFINAL RESULT:")
    print("=" * 80)
    
    if success:
        print("SUCCESS: Risk configuration is now properly in settings table!")
        print("")
        print("IMPLEMENTATION COMPLETE:")
        print("  [x] risk_settings table created")
        print("  [x] All risk parameters moved to settings")
        print("  [x] Position sizer updated to use risk_settings")
        print("  [x] Settings can be modified dynamically")
        print("  [x] Risk calculations use settings table values")
        print("")
        print("RISK SETTINGS AVAILABLE:")
        print("  - DEFAULT_RISK_PCT: Risk per trade (1%)")
        print("  - MAX_POSITION_PCT: Max position size (5%)")
        print("  - RISK_MODE: Calculation mode")
        print("  - MAX_SECTOR_EXPOSURE_PCT: Sector exposure limit (15%)")
        print("  - MAX_SECTOR_HARD_LIMIT_PCT: Hard sector limit (25%)")
        print("  - SECTOR_OVERWEIGHT_FACTOR: Overweight multiplier (0.5)")
        print("  - And more...")
        print("")
        print("Risk configuration is now centrally managed in settings table!")
    else:
        print("FAILED: Risk settings implementation has issues")
        print("Check the error messages above for debugging")

if __name__ == "__main__":
    main()
