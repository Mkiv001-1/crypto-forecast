import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


def cleanup_stuck_submitted_orders():
    """Mark stuck SUBMITTED orders as STALE immediately."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Mark SUBMITTED orders older than 48 hours as STALE
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    
    cursor.execute("""
        UPDATE orders 
        SET status = 'STALE' 
        WHERE status = 'SUBMITTED' AND submitted_at < ?
    """, (cutoff,))
    
    stale_count = cursor.rowcount
    conn.commit()
    
    # Show what was changed
    cursor.execute("""
        SELECT ticker, ib_order_id, order_role, status, submitted_at
        FROM orders 
        WHERE status = 'STALE'
        ORDER BY submitted_at DESC
    """)
    
    stale_orders = cursor.fetchall()
    
    print(f"Marked {stale_count} SUBMITTED orders as STALE:")
    print("=" * 80)
    for order in stale_orders:
        print(f"{order[0]}: IB Order {order[1]}, Role {order[2]}, Status {order[3]}")
        print(f"  Submitted: {order[4]}")
    
    # Check new open orders count
    cursor.execute("""
        SELECT COUNT(*) 
        FROM orders o
        LEFT JOIN trades t ON t.ib_parent_id = o.ib_parent_id
        WHERE UPPER(o.order_role)='ENTRY' AND o.status != 'STALE' AND (
            o.status IN ('QUEUED','SUBMITTED') 
            OR (o.status = 'FILLED_ENTRY' AND COALESCE(UPPER(t.status), 'OPEN') = 'OPEN')
        )
    """)
    
    open_count = cursor.fetchone()[0]
    print(f"\nNew open orders count: {open_count}")
    
    conn.close()
    return stale_count

if __name__ == "__main__":
    cleanup_stuck_submitted_orders()
