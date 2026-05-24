
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
