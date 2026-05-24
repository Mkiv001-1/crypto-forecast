import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()

# Get accounts table schema
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='accounts'")
schema = cursor.fetchone()[0]

print("ACCOUNTS TABLE SCHEMA:")
print("=" * 120)
print(schema)

# Get column info
cursor.execute("PRAGMA table_info(accounts)")
columns = cursor.fetchall()

print("\n\nCOLUMNS:")
print("=" * 60)
for col in columns:
    print(f"  {col[1]} ({col[2]})")

# Get sample data
cursor.execute("SELECT * FROM accounts LIMIT 1")
sample = cursor.fetchone()

if sample:
    print(f"\n\nSAMPLE DATA:")
    print("=" * 60)
    for i, value in enumerate(sample):
        col_name = columns[i][1]
        print(f"  {col_name}: {value}")

conn.close()
