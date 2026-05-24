import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts', 'core'))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from sqlite_manager import SQLiteManager
from unified_logs_manager import get_forecasts_to_evaluate

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


db_file = _get_db_path()
em = SQLiteManager(db_file)

print("=" * 60)
print("Testing get_forecasts_to_evaluate")
print("=" * 60)

forecasts = get_forecasts_to_evaluate(em, days_back=30)

print(f"\nFound {len(forecasts)} forecasts to evaluate")
if forecasts:
    for f in forecasts:
        print(f"  - {f.get('id')}: {f.get('ticker')} on {f.get('forecast_date')} (created: {f.get('created_at')})")
