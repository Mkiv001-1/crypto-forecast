import sqlite3
from datetime import datetime, timezone

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


def check_order_submission_conditions():
    """Check order submission timing in crypto 24/7 mode."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print("ORDER SUBMISSION TIMING ANALYSIS:")
    print("=" * 80)
    
    # Check current time and market hours
    now = datetime.now(timezone.utc)
    print(f"Current UTC time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Current weekday: {now.strftime('%A')} ({now.weekday()})")
    print("Market mode: crypto 24/7")
    print("Is market hours: True")
    
    # Check queued orders
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM orders 
        WHERE status = 'QUEUED' 
        AND UPPER(order_role) = 'ENTRY'
    """)
    
    queued_count = cursor.fetchone()[0]
    print(f"Queued ENTRY orders: {queued_count}")
    
    # Determine when orders will be submitted
    print(f"\n\nSUBMISSION TIMING:")
    print("=" * 80)
    print("ALLOWED: Orders can be submitted at any UTC time")
    print("STATUS: Orders should be submitted immediately")
    print("NOTE: legacy market-open windows are deprecated")
    submission_time = "IMMEDIATELY"
    
    # Check scheduler status
    print(f"\n\nSCHEDULER STATUS:")
    print("=" * 80)
    
    cursor.execute("""
        SELECT key, value 
        FROM config 
        WHERE key IN ('PENDING_ORDERS_INTERVAL_MINUTES', 'ORDER_STATUS_SYNC_INTERVAL_SECONDS')
    """)
    
    scheduler_settings = cursor.fetchall()
    for setting in scheduler_settings:
        print(f"{setting[0]}: {setting[1]}")
    
    print("\nThe scheduler processes PENDING_ORDER consensus every minute")
    print("This should trigger order submission when conditions are met")
    
    conn.close()
    
    return submission_time

def check_order_queue_status():
    """Check detailed status of queued orders."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print(f"\n\nDETAILED QUEUE STATUS:")
    print("=" * 80)
    
    cursor.execute("""
        SELECT id, ticker, order_role, status, created_at, trade_uid
        FROM orders 
        WHERE status = 'QUEUED' 
        AND id >= 49
        ORDER BY trade_uid, order_role
    """)
    
    queued_orders = cursor.fetchall()
    
    current_uid = None
    for order in queued_orders:
        order_id, ticker, role, status, created_at, trade_uid = order
        if trade_uid != current_uid:
            print(f"\nTrade: {trade_uid}")
            current_uid = trade_uid
        print(f"  ID {order_id}: {ticker} - {role} ({status})")
        print(f"    Created: {created_at}")
    
    conn.close()

def main():
    submission_time = check_order_submission_conditions()
    check_order_queue_status()
    
    print(f"\n\nFINAL ANSWER:")
    print("=" * 80)
    
    if submission_time == "IMMEDIATELY":
        print("Orders will be submitted IMMEDIATELY in crypto 24/7 mode")
    else:
        print(f"Orders will be submitted at {submission_time}")
        print("(Unexpected for current 24/7 mode)")

if __name__ == "__main__":
    main()
