import sqlite3
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


def activate_consensus_for_submission():
    """Activate consensus records to trigger order submission."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print("ACTIVATING CONSENSUS FOR ORDER SUBMISSION:")
    print("=" * 80)
    
    # Get the consensus records that created our orders
    cursor.execute("""
        SELECT c.id, c.ticker, c.signal, c.order_state, o.id as order_id
        FROM consensus c
        LEFT JOIN orders o ON o.log_id = c.id AND o.order_role = 'ENTRY'
        WHERE o.id >= 49
        AND o.status = 'QUEUED'
        ORDER BY c.id
    """)
    
    consensus_records = cursor.fetchall()
    
    if not consensus_records:
        print("No consensus records found for the queued orders")
        conn.close()
        return 0
    
    print(f"Found {len(consensus_records)} consensus records to activate:")
    
    activated_count = 0
    now = datetime.now(timezone.utc).isoformat()
    
    for record in consensus_records:
        consensus_id = record[0]
        ticker = record[1]
        signal = record[2]
        current_state = record[3]
        order_id = record[4]
        
        print(f"\nConsensus ID {consensus_id}: {ticker} - {signal}")
        print(f"  Current state: {current_state}")
        print(f"  Order ID: {order_id}")
        
        # Update consensus to PENDING_ORDER state
        cursor.execute("""
            UPDATE consensus 
            SET order_state = 'PENDING_ORDER',
                order_checked_at = ?
            WHERE id = ?
        """, (now, consensus_id))
        
        print(f"  Updated to PENDING_ORDER")
        activated_count += 1
    
    conn.commit()
    conn.close()
    
    return activated_count

def check_scheduler_status():
    """Check if scheduler is running and will process the orders."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    print(f"\n\nSCHEDULER CHECK:")
    print("=" * 80)
    
    # Check scheduler settings
    cursor.execute("""
        SELECT key, value 
        FROM config 
        WHERE key IN ('PENDING_ORDERS_INTERVAL_MINUTES', 'ORDER_MODE')
    """)
    
    settings = cursor.fetchall()
    for setting in settings:
        print(f"{setting[0]}: {setting[1]}")
    
    # Check if there are any PENDING_ORDER consensus now
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM consensus 
        WHERE order_state = 'PENDING_ORDER'
    """)
    
    pending_count = cursor.fetchone()[0]
    print(f"PENDING_ORDER consensus records: {pending_count}")
    
    if pending_count > 0:
        print("\nThe scheduler should process these within the next minute")
        print("Orders will be submitted to IB when:")
        print("1. Scheduler runs the pending_orders task")
        print("2. activate_consensus_order() is called")
        print("3. IB gateway accepts the orders")
        print("4. Orders get IB Order IDs and status SUBMITTED")
    
    conn.close()

def main():
    print("ACTIVATE CONSENSUS TO TRIGGER IB ORDER SUBMISSION")
    print("=" * 80)
    
    # Activate consensus records
    activated = activate_consensus_for_submission()
    
    print(f"\n\nACTIVATED {activated} CONSENSUS RECORDS")
    
    # Check scheduler status
    check_scheduler_status()
    
    print(f"\n\nNEXT STEPS:")
    print("=" * 80)
    print("1. Wait up to 1 minute for scheduler to process PENDING_ORDER")
    print("2. Check if orders get IB Order IDs and status SUBMITTED")
    print("3. Monitor IB gateway connection")
    print("4. Orders should appear in IB TWS/Gateway")

if __name__ == "__main__":
    main()
