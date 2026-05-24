import os
import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


def create_risk_settings_table():
    """Create a separate table for risk configuration settings."""
    print("CREATING RISK SETTINGS TABLE:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Drop existing risk_settings if it exists
    cursor.execute("DROP TABLE IF EXISTS risk_settings")
    
    # Create risk_settings table
    cursor.execute("""
        CREATE TABLE risk_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT UNIQUE NOT NULL,
            setting_value TEXT NOT NULL,
            setting_type TEXT DEFAULT 'string',
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert default risk settings
    default_settings = [
        ('DEFAULT_RISK_PCT', '0.01', 'float', 'Risk per trade as fraction of NetLiquidation (1%)'),
        ('MAX_POSITION_PCT', '0.05', 'float', 'Max single position as fraction of NetLiquidation (5%)'),
        ('MAX_SECTOR_EXPOSURE_PCT', '0.15', 'float', 'Max sector exposure before overweight factor (15%)'),
        ('MAX_SECTOR_HARD_LIMIT_PCT', '0.25', 'float', 'Hard limit for sector exposure (25%)'),
        ('SECTOR_OVERWEIGHT_FACTOR', '0.5', 'float', 'Position size multiplier when sector soft limit exceeded'),
        ('RISK_MODE', 'percent_of_capital', 'string', 'Risk calculation mode: percent_of_capital or percent_of_portfolio_on_stop'),
        ('CAPITAL_STALENESS_MINUTES', '15', 'integer', 'Minutes before capital data is considered stale'),
        ('MAX_POSITIONS', '3', 'integer', 'Maximum simultaneous open positions'),
        ('MAX_RISK_PER_TRADE', '2.0', 'float', 'Maximum risk per trade percentage of account'),
        ('MIN_POSITION_SIZE_USD', '100', 'float', 'Minimum position size in USD')
    ]
    
    cursor.executemany("""
        INSERT INTO risk_settings (setting_key, setting_value, setting_type, description)
        VALUES (?, ?, ?, ?)
    """, default_settings)
    
    conn.commit()
    
    # Verify creation
    cursor.execute("SELECT COUNT(*) FROM risk_settings")
    count = cursor.fetchone()[0]
    
    print(f"Created risk_settings table with {count} default settings")
    
    # Show all settings
    cursor.execute("SELECT setting_key, setting_value, description FROM risk_settings ORDER BY setting_key")
    settings = cursor.fetchall()
    
    print(f"\nDefault risk settings:")
    for key, value, description in settings:
        print(f"  {key}: {value}")
        print(f"    {description}")
    
    conn.close()
    return True

def update_position_sizer_to_use_risk_settings():
    """Update position sizer to use risk_settings table instead of config."""
    print(f"\n\nUPDATING POSITION SIZER TO USE RISK SETTINGS:")
    print("=" * 80)
    
    # Create new position sizer functions
    new_functions = '''
def _get_risk_setting(db_manager, key: str, default_value):
    """Get risk setting from risk_settings table."""
    try:
        import sqlite3
        with sqlite3.connect(db_manager.db_file) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                "SELECT setting_value, setting_type FROM risk_settings WHERE setting_key = ?",
                (key,)
            ).fetchone()
            
            if row:
                value = row["setting_value"]
                setting_type = row["setting_type"]
                
                # Convert based on type
                if setting_type == "float":
                    return float(value)
                elif setting_type == "integer":
                    return int(value)
                else:
                    return value
            else:
                return default_value
    except Exception as e:
        logger.warning(f"position_sizer: Could not get risk setting {key}: {e}")
        return default_value

def _cfg_risk(db_manager, key: str, default_value):
    """Get configuration value from risk_settings table."""
    return _get_risk_setting(db_manager, key, default_value)

def _get_str_risk_config(db_manager, key: str, default: str) -> str:
    """Get string configuration value from risk_settings."""
    value = _get_risk_setting(db_manager, key, default)
    return str(value).strip() if value is not None else default
'''
    
    print("New functions for position sizer:")
    print(new_functions)
    
    # Save to file for reference
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'new_position_sizer_functions.py'), 'w') as f:
        f.write(new_functions)
    
    print("Saved to: new_position_sizer_functions.py")
    return True

def main():
    print("CREATE RISK SETTINGS IN SETTINGS TABLE")
    print("=" * 80)
    
    # Create risk settings table
    created = create_risk_settings_table()
    
    if created:
        # Update position sizer functions
        update_position_sizer_to_use_risk_settings()
        
        print(f"\n\nNEXT STEPS:")
        print("=" * 80)
        print("1. Update position_sizer.py to use new _cfg_risk functions")
        print("2. Test position sizing with risk_settings table")
        print("3. Verify all risk calculations use settings table")
    else:
        print(f"\n\nRESULT:")
        print("=" * 80)
        print("FAILED: Could not create risk settings table")

if __name__ == "__main__":
    main()
