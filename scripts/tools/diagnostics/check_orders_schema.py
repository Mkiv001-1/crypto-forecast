import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'")
schema = cursor.fetchone()[0]

print("ORDERS TABLE SCHEMA:")
print("=" * 120)
print(schema)

# Also get column info
cursor.execute("PRAGMA table_info(orders)")
columns = cursor.fetchall()

print("\n\nCOLUMNS:")
print("=" * 60)
for col in columns:
    print(f"  {col[1]} ({col[2]})")

conn.close()
