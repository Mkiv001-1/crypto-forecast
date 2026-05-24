
def get_net_liquidation_from_portfolio_history(db_manager) -> float:
    """
    Return NetLiquidation from portfolio_history table.
    
    This function replaces the old accounts-based approach with portfolio_history.
    """
    try:
        import sqlite3
        with sqlite3.connect(db_manager.db_file) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                """
                SELECT net_liquidation, timestamp 
                FROM portfolio_history 
                WHERE row_type = 'summary' 
                AND ticker = '__ACCOUNT_SUMMARY__'
                ORDER BY timestamp DESC 
                LIMIT 1
                """
            ).fetchone()
            
            if row and row["net_liquidation"]:
                net_liq = float(row["net_liquidation"])
                logger.debug(f"capital_provider: NetLiquidation={net_liq:,.2f} from portfolio_history (timestamp={row['timestamp']})")
                return net_liq
            else:
                logger.warning("capital_provider: No data found in portfolio_history")
                return 0.0
                
    except Exception as e:
        logger.error(f"capital_provider: portfolio_history read error: {e}")
        return 0.0
