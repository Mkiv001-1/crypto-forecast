import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


def check_settings_table():
    """Check settings table structure and current risk configuration."""
    print("CHECKING SETTINGS TABLE FOR RISK CONFIGURATION:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Check if settings table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
    settings_table = cursor.fetchone()
    
    if not settings_table:
        print("No settings table found - need to create it")
        conn.close()
        return False
    
    # Get table schema
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='settings'")
    schema = cursor.fetchone()[0]
    
    print("Settings table schema:")
    print(schema)
    
    # Get column info
    cursor.execute("PRAGMA table_info(settings)")
    columns = cursor.fetchall()
    
    print(f"\n\nColumns ({len(columns)}):")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")
    
    # Check current settings
    cursor.execute("SELECT * FROM settings")
    current_settings = cursor.fetchall()
    
    print(f"\n\nCurrent settings ({len(current_settings)} records):")
    for setting in current_settings:
        print(f"  {setting}")
    
    # Look for risk-related settings
    cursor.execute("SELECT * FROM settings WHERE key LIKE '%RISK%' OR key LIKE '%CAPITAL%' OR key LIKE '%POSITION%'")
    risk_settings = cursor.fetchall()
    
    print(f"\n\nRisk-related settings:")
    if risk_settings:
        for setting in risk_settings:
            print(f"  {setting}")
    else:
        print("  No risk-related settings found")
    
    conn.close()
    return True

def check_config_table():
    """Check config table for current risk settings."""
    print(f"\n\nCHECKING CONFIG TABLE FOR CURRENT RISK SETTINGS:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Get risk-related config
    cursor.execute("SELECT key, value, description FROM config WHERE key LIKE '%RISK%' OR key LIKE '%CAPITAL%' OR key LIKE '%POSITION%' OR key LIKE '%DEFAULT%' ORDER BY key")
    risk_config = cursor.fetchall()
    
    print("Current risk configuration in config table:")
    if risk_config:
        for key, value, description in risk_config:
            print(f"  {key}: {value}")
            if description:
                print(f"    {description}")
    else:
        print("  No risk configuration found")
    
    conn.close()

def main():
    print("CHECK SETTINGS TABLE FOR RISK CONFIGURATION")
    print("=" * 80)
    
    # Check settings table
    settings_exists = check_settings_table()
    
    # Check config table for current risk settings
    check_config_table()
    
    print(f"\n\nNEXT STEPS:")
    print("=" * 80)
    
    if settings_exists:
        print("Settings table exists - need to add risk configuration fields")
        print("Required risk settings:")
        print("  - DEFAULT_RISK_PCT (default 1%)")
        print("  - MAX_POSITION_PCT (default 5%)")
        print("  - MAX_SECTOR_EXPOSURE_PCT (default 15%)")
        print("  - MAX_SECTOR_HARD_LIMIT_PCT (default 25%)")
        print("  - SECTOR_OVERWEIGHT_FACTOR (default 0.5)")
        print("  - RISK_MODE (default 'percent_of_capital')")
    else:
        print("Need to create settings table with risk configuration")

if __name__ == "__main__":
    main()
