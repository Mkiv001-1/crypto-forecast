"""Add con_id column to existing portfolio_history table."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.core.sqlite_manager import SQLiteManager
from scripts.server.config import get_db_path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_con_id_column():
    """Add con_id column to portfolio_history table if it doesn't exist."""
    db_path = Path(get_db_path())

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return False
    
    # Connect directly to check and add column
    import sqlite3
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Check if con_id column exists
            cursor.execute("PRAGMA table_info(portfolio_history)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "con_id" in columns:
                logger.info("con_id column already exists in portfolio_history")
                return True
            
            # Add the column
            cursor.execute("ALTER TABLE portfolio_history ADD COLUMN con_id INTEGER DEFAULT NULL")
            conn.commit()
            logger.info("Successfully added con_id column to portfolio_history")
            return True
            
    except Exception as e:
        logger.error(f"Error adding con_id column: {e}")
        return False


if __name__ == "__main__":
    success = add_con_id_column()
    sys.exit(0 if success else 1)
