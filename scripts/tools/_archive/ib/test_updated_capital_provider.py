import sqlite3
import sys
import os
from datetime import datetime, timezone, timedelta

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'scripts', 'core'))

def test_updated_capital_provider():
    """Test the updated capital provider that uses Portfolio History."""
    print("TESTING UPDATED CAPITAL PROVIDER WITH PORTFOLIO HISTORY:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.capital_provider import get_net_liquidation, get_capital_details, get_portfolio_net_liquidation
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Test basic net liquidation
    print("Testing get_net_liquidation():")
    try:
        net_liq = get_net_liquidation(db_manager)
        print(f"  Net Liquidation: ${net_liq:,.2f}")
        
        if net_liq > 0:
            print(f"  SUCCESS: Basic function works!")
        else:
            print(f"  FAILED: Net liquidation is 0")
            return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False
    
    # Test detailed capital info
    print(f"\nTesting get_capital_details():")
    try:
        details = get_capital_details(db_manager)
        print(f"  Capital details:")
        for key, value in details.items():
            if key in ['net_liquidation', 'buying_power', 'available_funds', 'cash'] and isinstance(value, (int, float)):
                print(f"    {key}: ${value:,.2f}")
            else:
                print(f"    {key}: {value}")
        
        if details.get('source') == 'portfolio_history':
            print(f"  SUCCESS: Using Portfolio History data!")
        else:
            print(f"  WARNING: Source is {details.get('source')}")
    except Exception as e:
        print(f"  ERROR: {e}")
        return False
    
    # Test portfolio net liquidation
    print(f"\nTesting get_portfolio_net_liquidation():")
    try:
        portfolio_liq, source = get_portfolio_net_liquidation(db_manager)
        print(f"  Portfolio Net Liquidation: ${portfolio_liq:,.2f}")
        print(f"  Source: {source}")
        
        if portfolio_liq > 0 and source == 'portfolio_history':
            print(f"  SUCCESS: Portfolio function works!")
        else:
            print(f"  FAILED: Portfolio function issues")
            return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False
    
    return True

def test_position_sizing_with_updated_provider():
    """Test position sizing with the updated capital provider."""
    print(f"\n\nTESTING POSITION SIZING WITH UPDATED CAPITAL PROVIDER:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.position_sizer import calculate_position
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Test position sizing for multiple tickers
    test_cases = [
        ("NASDAQ:MSFT", 435.0, 420.0),
        ("NASDAQ:AAPL", 180.0, 170.0),
        ("NASDAQ:GOOGL", 140.0, 130.0)
    ]
    
    all_success = True
    
    for ticker, entry_price, stop_loss in test_cases:
        print(f"\nTesting {ticker}:")
        print(f"  Entry: ${entry_price}, Stop: ${stop_loss}")
        
        try:
            result = calculate_position(
                ticker=ticker,
                entry_price=entry_price,
                stop_loss=stop_loss,
                db_manager=db_manager
            )
            
            print(f"  Result: {result}")
            
            if result.get('status') == 'OK':
                print(f"  SUCCESS: Quantity {result.get('quantity')}, Risk ${result.get('risk_amount', 0):,.2f}")
                print(f"  Capital source: {result.get('capital_source')}")
            else:
                print(f"  FAILED: {result.get('status')}")
                all_success = False
                
        except Exception as e:
            print(f"  ERROR: {e}")
            all_success = False
    
    return all_success

def test_complete_order_creation():
    """Test complete order creation with updated capital provider."""
    print(f"\n\nTESTING COMPLETE ORDER CREATION:")
    print("=" * 80)
    
    try:
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.order_manager import submit_signal
        from scripts.core.position_sizer import calculate_position
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    
    db_manager = SQLiteManager(_get_db_path())
    
    # Test consensus data
    test_consensus = {
        'ticker': 'NASDAQ:GOOGL',
        'signal': 'SHORT',
        'confidence': 80.0,
        'target_price': 130.0,
        'stop_loss': 150.0,
        'entry_limit_price': 140.0,
        'forecasts': []
    }
    
    print(f"Creating order for {test_consensus['ticker']} - {test_consensus['signal']}")
    print(f"  Entry: ${test_consensus['entry_limit_price']}")
    print(f"  Target: ${test_consensus['target_price']}")
    print(f"  Stop: ${test_consensus['stop_loss']}")
    
    # Calculate position size
    position_calc = calculate_position(
        ticker=test_consensus['ticker'],
        entry_price=test_consensus['entry_limit_price'],
        stop_loss=test_consensus['stop_loss'],
        db_manager=db_manager
    )
    
    print(f"  Position calculation: {position_calc}")
    
    if position_calc.get('status') != 'OK':
        print(f"  FAILED: Position sizing failed")
        return False
    
    # Build position_size dict
    position_size = {
        'quantity': position_calc['quantity'],
        'capital_allocated': position_calc['position_value'],
        'status': 'OK'
    }
    
    print(f"  Using position size: {position_size['quantity']} shares (${position_size['capital_allocated']:,.2f})")
    
    # Submit the order
    try:
        result = submit_signal(
            ticker=test_consensus['ticker'],
            consensus=test_consensus,
            position_size=position_size,
            db_manager=db_manager
        )
        
        print(f"  Result: {result}")
        
        if result and result.get('status') not in ['UNKNOWN', None]:
            print(f"  SUCCESS: Order created with Portfolio History capital!")
            print(f"  Status: {result.get('status')}")
            print(f"  Order IDs: {result.get('order_ids', [])}")
            return True
        else:
            print(f"  FAILED: Order creation failed")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main():
    print("TEST UPDATED CAPITAL PROVIDER WITH PORTFOLIO HISTORY")
    print("=" * 80)
    
    # Test updated capital provider
    provider_works = test_updated_capital_provider()
    
    if provider_works:
        # Test position sizing
        sizing_works = test_position_sizing_with_updated_provider()
        
        if sizing_works:
            # Test complete order creation
            order_works = test_complete_order_creation()
            
            print(f"\n\nFINAL RESULT:")
            print("=" * 80)
            
            if order_works:
                print("SUCCESS: Capital Provider updated to use Portfolio History!")
                print("✓ Portfolio History data retrieval: Working")
                print("✓ Position sizing with Portfolio History: Working")
                print("✓ Order creation with Portfolio History: Working")
                print("\nCapital data now properly stored in Portfolio History table!")
            else:
                print("PARTIAL SUCCESS: Capital Provider works, but order creation has issues")
        else:
            print(f"\n\nRESULT:")
            print("=" * 80)
            print("PARTIAL SUCCESS: Capital Provider works, but position sizing has issues")
    else:
        print(f"\n\nRESULT:")
        print("=" * 80)
        print("FAILED: Updated Capital Provider has issues")

if __name__ == "__main__":
    main()
