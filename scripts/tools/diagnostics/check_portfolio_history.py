import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


def check_portfolio_history_table():
    """Check Portfolio History table structure and data."""
    print("CHECKING PORTFOLIO HISTORY TABLE:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Get table schema
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='portfolio_history'")
    schema = cursor.fetchone()
    
    if schema:
        print("Portfolio History table schema:")
        print(schema[0])
        
        # Get column info
        cursor.execute("PRAGMA table_info(portfolio_history)")
        columns = cursor.fetchall()
        
        print(f"\n\nColumns ({len(columns)}):")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
        
        # Check for capital-related columns
        capital_columns = []
        for col in columns:
            col_name = col[1].lower()
            if any(keyword in col_name for keyword in ['capital', 'net', 'liquidation', 'equity', 'buying', 'available', 'cash']):
                capital_columns.append(col[1])
        
        print(f"\n\nCapital-related columns:")
        if capital_columns:
            for col in capital_columns:
                print(f"  {col}")
        else:
            print("  No capital-related columns found!")
        
        # Get sample data
        cursor.execute("SELECT COUNT(*) FROM portfolio_history")
        total_rows = cursor.fetchone()[0]
        print(f"\n\nTotal records: {total_rows}")
        
        if total_rows > 0:
            cursor.execute("""
                SELECT * FROM portfolio_history 
                ORDER BY timestamp DESC 
                LIMIT 3
            """)
            
            recent_data = cursor.fetchall()
            
            print(f"\n\nRecent records:")
            for i, row in enumerate(recent_data):
                print(f"  Record {i+1}:")
                for j, value in enumerate(row):
                    col_name = columns[j][1]
                    print(f"    {col_name}: {value}")
                print()
        
    else:
        print("No Portfolio History table found!")
    
    conn.close()

def check_accounts_table():
    """Compare with accounts table structure."""
    print(f"\n\nCHECKING ACCOUNTS TABLE FOR REFERENCE:")
    print("=" * 80)
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    # Get accounts table schema
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='accounts'")
    schema = cursor.fetchone()
    
    if schema:
        print("Accounts table schema:")
        print(schema[0])
        
        # Get column info
        cursor.execute("PRAGMA table_info(accounts)")
        columns = cursor.fetchall()
        
        print(f"\n\nCapital-related columns in accounts:")
        for col in columns:
            col_name = col[1].lower()
            if any(keyword in col_name for keyword in ['capital', 'net', 'liquidation', 'equity', 'buying', 'available', 'cash']):
                print(f"  {col_name} ({col[2]})")
    
    conn.close()

def main():
    print("CHECK PORTFOLIO HISTORY TABLE STRUCTURE")
    print("=" * 80)
    
    check_portfolio_history_table()
    check_accounts_table()

if __name__ == "__main__":
    main()
