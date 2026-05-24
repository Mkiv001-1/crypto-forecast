"""
Recalculate consensus for existing forecasts in logs table.

Usage:
    python scripts/tools/recalculate_consensus.py [ticker]
    
Examples:
    python scripts/tools/recalculate_consensus.py           # All tickers
    python scripts/tools/recalculate_consensus.py NASDAQ:NVDA  # Specific ticker
"""

import sys
import os
import logging

# Add project root to path
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from core.sqlite_manager import SQLiteManager
from core.consensus import calculate_consensus, save_consensus
from core.unified_logs_manager import get_forecast_statistics

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def get_forecasts_for_consensus(db_manager, ticker: str = None):
    """
    Get forecasts from logs table in the format expected by calculate_consensus.
    
    Returns list of dicts with: model, method, side, confidence, exit_target, stop_loss, entry_limit_price
    """
    import sqlite3
    
    sql = """
        SELECT 
            ticker,
            method,
            model,
            side,
            confidence,
            exit_target,
            exit_stop,
            stop_loss,
            entry_price,
            created_at
        FROM logs
        WHERE status = 'NEW'
    """
    params = []
    
    if ticker:
        sql += " AND ticker = ?"
        params.append(ticker)
    
    # Get all forecasts (sorted by date, newest first)
    sql += " ORDER BY created_at DESC"
    sql += " LIMIT 5000"  # Safety limit to avoid memory issues
    
    forecasts_by_ticker = {}
    
    with sqlite3.connect(db_manager.db_file) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
    
    for row in rows:
        t = row['ticker']
        if t not in forecasts_by_ticker:
            forecasts_by_ticker[t] = []
        
        # Parse target price from exit_target (TEXT like "$150 (+5%)")
        exit_target = row['exit_target']
        target_price = None
        if exit_target:
            import re
            nums = re.findall(r'[\d.]+', str(exit_target))
            if nums:
                try:
                    target_price = float(nums[-1])
                except:
                    pass
        
        # Parse stop loss from stop_loss column or fallback to exit_stop text
        stop_loss = row['stop_loss']
        if not stop_loss and row['exit_stop']:
            import re
            nums = re.findall(r'[\d.]+', str(row['exit_stop']))
            if nums:
                try:
                    entry = row['entry_price'] or 0
                    if len(nums) >= 2:
                        # Format: "195.00 (-2.8%)" - first is price
                        stop_loss = float(nums[0])
                    elif len(nums) == 1 and entry > 0:
                        # Format: "2.8%" (only percentage) - calculate from entry
                        pct = float(nums[0])
                        # For LONG: stop below entry; for SHORT: stop above entry
                        side = str(row['side'] or 'NEUTRAL').upper()
                        if side == 'LONG':
                            stop_loss = round(entry * (1 - pct/100), 2)
                        elif side == 'SHORT':
                            stop_loss = round(entry * (1 + pct/100), 2)
                    else:
                        stop_loss = float(nums[0])
                except:
                    pass
        
        forecasts_by_ticker[t].append({
            'model': row['model'],
            'method': row['method'],
            'side': row['side'] or 'NEUTRAL',
            'confidence': row['confidence'] or 50,
            'exit_target': exit_target,
            'stop_loss': stop_loss,
            'entry_limit_price': row['entry_price'],
            'entry_tif': 'GTC',
            'take_profit_tif': 'GTC',
            'stop_loss_tif': 'GTC',
        })
    
    return forecasts_by_ticker


def recalculate_consensus(db_manager, ticker: str = None):
    """Recalculate and save consensus for all or specific ticker."""
    
    # Get forecast statistics for method weights
    stats = get_forecast_statistics(db_manager, days_back=30)
    accuracy = stats.get("accuracy", {})
    method_stats = {
        m: {"win_rate": accuracy.get(m, 50.0) / 100.0}
        for m in stats.get("methods", {})
    }

    # Enrich method_stats with timeframe_hours from method_config
    try:
        import pandas as pd
        import sqlite3
        with sqlite3.connect(db_manager.db_file) as _con:
            _mc = pd.read_sql_query("SELECT method, timeframe_hours FROM method_config WHERE active=1", _con)
        for _, row in _mc.iterrows():
            m = row["method"]
            if m not in method_stats:
                method_stats[m] = {}
            method_stats[m]["timeframe_hours"] = int(row["timeframe_hours"])
    except Exception as _e:
        logger.warning(f"recalculate_consensus: could not load method_config timeframe_hours: {_e}")
    
    # Get forecasts grouped by ticker
    forecasts_by_ticker = get_forecasts_for_consensus(db_manager, ticker)
    
    if not forecasts_by_ticker:
        logger.warning("No forecasts found")
        return
    
    logger.info(f"Found forecasts for {len(forecasts_by_ticker)} ticker(s)")
    
    for t, forecasts in forecasts_by_ticker.items():
        logger.info(f"\n📊 {t}: {len(forecasts)} forecasts")
        
        # Show breakdown
        longs = [f for f in forecasts if f['side'].upper() == 'LONG']
        shorts = [f for f in forecasts if f['side'].upper() == 'SHORT']
        neutrals = [f for f in forecasts if f['side'].upper() == 'NEUTRAL']
        logger.info(f"   LONG: {len(longs)}, SHORT: {len(shorts)}, NEUTRAL: {len(neutrals)}")
        
        # Calculate consensus
        cons = calculate_consensus(forecasts, method_stats)
        
        logger.info(f"   → Consensus: {cons['signal']} {cons['confidence']:.1f}%")
        logger.info(f"   → Target: {cons.get('target_price')}, Stop: {cons.get('stop_loss')}")
        
        # Save to consensus table
        success = save_consensus(db_manager, t, cons, method_stats=method_stats)
        if success:
            logger.info(f"   ✅ Saved to consensus table")
        else:
            logger.error(f"   ❌ Failed to save")
    
    logger.info(f"\n✅ Done! Recalculated consensus for {len(forecasts_by_ticker)} ticker(s)")


if __name__ == "__main__":
    import os
    from scripts.server.config import get_db_path
    
    db_file = get_db_path()
    db_manager = SQLiteManager(db_file)
    
    ticker = sys.argv[1] if len(sys.argv) > 1 else None
    
    if ticker:
        logger.info(f"Recalculating consensus for: {ticker}")
    else:
        logger.info("Recalculating consensus for ALL tickers (all forecasts)")
    
    recalculate_consensus(db_manager, ticker)
