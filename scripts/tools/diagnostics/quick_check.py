import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()

conn = sqlite3.connect(_get_db_path())
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'STALE'")
print("STALE orders:", cursor.fetchone()[0])
cursor.execute("SELECT value FROM config WHERE key = 'MAX_OPEN_ORDERS'")
print("MAX_OPEN_ORDERS:", cursor.fetchone()[0])
cursor.execute("""
    SELECT COUNT(*) 
    FROM orders o
    LEFT JOIN trades t ON t.ib_parent_id = o.ib_parent_id
    WHERE UPPER(o.order_role)='ENTRY' AND o.status != 'STALE' AND (
        o.status IN ('QUEUED','SUBMITTED') 
        OR (o.status = 'FILLED_ENTRY' AND COALESCE(UPPER(t.status), 'OPEN') = 'OPEN')
    )
""")
print("Open orders:", cursor.fetchone()[0])
conn.close()
