import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Check if new settings exist in config
cursor.execute("""
    SELECT key, value, description 
    FROM config 
    WHERE key IN ('QUEUE_DAY_ORDERS', 'FILLED_ORDERS_RETENTION_DAYS')
""")
new_settings = cursor.fetchall()

print("NEW SETTINGS IN DATABASE:")
print("=" * 60)
for setting in new_settings:
    print(f"{setting[0]}: {setting[1]} ({setting[2]})")

if not new_settings:
    print("New settings not found - they will be added with default values when system restarts")

# Check current configuration
cursor.execute("""
    SELECT key, value, description 
    FROM config 
    WHERE key IN ('ALLOW_EXTENDED_HOURS', 'ORDER_QUEUE_MAX_AGE_HOURS')
""")
existing_settings = cursor.fetchall()

print("\n\nEXISTING RELATED SETTINGS:")
print("=" * 60)
for setting in existing_settings:
    print(f"{setting[0]}: {setting[1]} ({setting[2]})")

conn.close()
