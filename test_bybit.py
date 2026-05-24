"""
Тест подключения к Bybit API.

Запуск:
    python test_bybit.py

Проверяет:
1. Конфигурация (API Key/Secret)
2. Подключение к API
3. Получение баланса
4. Получение тикера
5. Получение исторических данных
"""

import sys
import os

# Добавляем пути
project_root = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.join(project_root, "scripts")
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

def test_bybit_connection():
    """Тест базового подключения к Bybit."""
    print("=" * 60)
    print("Bybit Connection Test")
    print("=" * 60)
    
    # 1. Проверяем конфигурацию
    print("\n[1] Loading configuration...")
    try:
        from scripts.core.bybit_config import load_bybit_config, validate_api_credentials
        
        # Загружаем без db_manager (только env/defaults)
        config = load_bybit_config()
        
        print(f"  Demo mode: {config.demo}")
        print(f"  Default leverage: {config.default_leverage}x")
        print(f"  Order mode: {config.order_mode}")
        print(f"  API Key configured: {'Yes' if config.api_key else 'No'}")
        
        is_valid, error = validate_api_credentials(config)
        if not is_valid:
            print(f"\n  ❌ ERROR: {error}")
            print("\n  Пожалуйста, установите переменные окружения:")
            print("    set BYBIT_API_KEY=your_api_key")
            print("    set BYBIT_API_SECRET=your_api_secret")
            return False
        
        print(f"  ✅ API credentials valid")
        
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False
    
    # 2. Проверяем подключение
    print("\n[2] Testing API connection...")
    try:
        from scripts.core.bybit_client import BybitClient
        
        client = BybitClient(
            api_key=config.api_key,
            api_secret=config.api_secret,
            demo=config.demo
        )
        
        if client.test_connection():
            print(f"  ✅ Connection successful (demo={config.demo})")
        else:
            print(f"  ❌ Connection failed")
            return False
            
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False
    
    # 3. Проверяем баланс
    print("\n[3] Fetching wallet balance...")
    try:
        balance = client.get_wallet_balance("USDT")
        if balance:
            print(f"  Equity: {balance['equity']:.2f} USDT")
            print(f"  Available: {balance['available_balance']:.2f} USDT")
            print(f"  Unrealized PnL: {balance['unrealised_pnl']:.2f} USDT")
            print(f"  ✅ Balance retrieved")
        else:
            print(f"  ⚠️  No balance data")
            
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False
    
    # 4. Проверяем тикер
    print("\n[4] Fetching BTCUSDT ticker...")
    try:
        ticker = client.get_ticker("BTCUSDT")
        if ticker:
            print(f"  Last price: {ticker['last_price']:.2f}")
            print(f"  Bid: {ticker['bid']:.2f}")
            print(f"  Ask: {ticker['ask']:.2f}")
            print(f"  24h Volume: {ticker['volume_24h']:.2f}")
            print(f"  ✅ Ticker retrieved")
        else:
            print(f"  ⚠️  No ticker data")
            
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False
    
    # 5. Проверяем исторические данные
    print("\n[5] Fetching historical data (BTCUSDT, 7 days)...")
    try:
        klines = client.get_klines("BTCUSDT", interval="D", limit=7)
        if klines:
            print(f"  Loaded {len(klines)} daily candles")
            if len(klines) > 0:
                first = klines[0]
                last = klines[-1]
                print(f"  First: {first['datetime']} O:{first['open']:.2f} C:{first['close']:.2f}")
                print(f"  Last:  {last['datetime']} O:{last['open']:.2f} C:{last['close']:.2f}")
            print(f"  ✅ Historical data retrieved")
        else:
            print(f"  ⚠️  No historical data")
            
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False
    
    # 6. Проверяем инструменты
    print("\n[6] Fetching available instruments...")
    try:
        instruments = client.get_instruments()
        usdt_pairs = [i for i in instruments if i.get('quote_coin') == 'USDT']
        print(f"  Total USDT linear perpetuals: {len(usdt_pairs)}")
        print(f"  Top 5: {', '.join([i['symbol'] for i in usdt_pairs[:5]])}")
        print(f"  ✅ Instruments retrieved")
        
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
    print(f"\nYou can now start the server with:")
    print(f"  cd scripts\\server && python main.py")
    
    return True


def test_order_placement():
    """Тест размещения ордера (только для demo!)."""
    print("\n" + "=" * 60)
    print("Order Placement Test (DEMO ONLY)")
    print("=" * 60)
    
    from scripts.core.bybit_config import load_bybit_config
    config = load_bybit_config()
    
    if not config.demo:
        print("\n  ⚠️  WARNING: Not in demo mode!")
        print("  This test will place real orders with real money.")
        response = input("  Continue anyway? (yes/no): ")
        if response.lower() != "yes":
            print("  Cancelled.")
            return False
    
    from scripts.core.bybit_client import BybitClient
    
    client = BybitClient(
        api_key=config.api_key,
        api_secret=config.api_secret,
        demo=config.demo
    )
    
    # Устанавливаем плечо
    print("\n[1] Setting leverage to 3x for BTCUSDT...")
    try:
        client.set_leverage("BTCUSDT", 3)
        print("  ✅ Leverage set")
    except Exception as e:
        print(f"  ⚠️  {e}")
    
    # Размещаем маленький лимитный ордер далеко от текущей цены
    print("\n[2] Placing test order (limit at 50% below market)...")
    try:
        ticker = client.get_ticker("BTCUSDT")
        current_price = ticker['last_price']
        test_price = round(current_price * 0.5, 1)  # 50% ниже текущей цены
        
        order = client.place_order(
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            qty=0.001,  # Минимальный размер
            price=test_price,
            time_in_force="GTC"
        )
        
        if order:
            print(f"  Order ID: {order['order_id']}")
            print(f"  Link ID: {order['order_link_id']}")
            print(f"  Price: {test_price}")
            print(f"  ✅ Order placed")
            
            # Сразу отменяем
            print("\n[3] Cancelling test order...")
            cancelled = client.cancel_order("BTCUSDT", order_id=order['order_id'])
            if cancelled:
                print(f"  ✅ Order cancelled")
            else:
                print(f"  ⚠️  Failed to cancel")
        else:
            print(f"  ❌ Failed to place order")
            return False
            
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ Order test passed!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Bybit connection")
    parser.add_argument("--order", action="store_true", help="Also test order placement")
    args = parser.parse_args()
    
    # Базовый тест
    success = test_bybit_connection()
    
    if not success:
        print("\n❌ Connection test failed!")
        sys.exit(1)
    
    # Тест ордеров (опционально)
    if args.order:
        order_success = test_order_placement()
        if not order_success:
            print("\n❌ Order test failed!")
            sys.exit(1)
    
    print("\n✅ All tests completed successfully!")
    sys.exit(0)
