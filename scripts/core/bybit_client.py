"""
Bybit REST API Client — клиент для торговли на Bybit (Demo/Live).

Поддерживает:
- Linear Perpetual (USDT-Margined) контракты
- Исторические данные (kline/candles)
- Размещение ордеров (Limit, Market)
- Управление позициями
- Получение баланса

Endpoints (pybit, testnet never used):
- Live:  https://api.bybit.com
- Demo:  https://api-demo.bybit.com  (Demo Trading on bybit.com, not testnet.bybit.com)
"""

import logging
import time
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from pybit.unified_trading import HTTP

from scripts.core.bybit_instrument import format_bybit_decimal, normalize_order_params

logger = logging.getLogger(__name__)

# Bybit: requested leverage already matches position setting (not a failure).
_LEVERAGE_UNCHANGED_RETCODE = 110043


def _is_leverage_unchanged(*, ret_code: Optional[int] = None, message: str = "") -> bool:
    if ret_code == _LEVERAGE_UNCHANGED_RETCODE:
        return True
    text = message.lower()
    return "110043" in message or "leverage not modified" in text


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Parse Bybit numeric fields; API may return '' for zero/unset values."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class BybitClient:
    """Клиент для работы с Bybit Unified Trading API v5."""
    
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        demo: bool = True,
        recv_window: int = 60000,
        max_retries: int = 3
    ):
        """
        Инициализация клиента.

        Args:
            api_key: API Key из Bybit (опционально — для market data не нужен)
            api_secret: API Secret из Bybit (опционально)
            demo: True = Demo Trading на bybit.com (api-demo.bybit.com), False = live
            recv_window: Окно получения в мс (default 60000, Bybit max)
            max_retries: Максимальное количество retry при ошибках
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.demo = demo
        self.recv_window = recv_window
        self.max_retries = max_retries

        # Unified Trading API v5. Demo = api-demo.bybit.com (bybit.com Demo Trading).
        # testnet.bybit.com is never used in this project.
        session_kwargs = {
            "recv_window": recv_window,
            "max_retries": max_retries,
            "demo": demo,
            "testnet": False,
        }
        if api_key and api_secret:
            session_kwargs["api_key"] = api_key
            session_kwargs["api_secret"] = api_secret
        self.session = HTTP(**session_kwargs)

        logger.info(f"BybitClient initialized (demo={demo}, auth={bool(api_key and api_secret)})")

    def log_time_skew_warning(self, threshold_ms: int = 5000) -> None:
        """Log a warning if local clock differs from Bybit server time."""
        try:
            resp = self.session.get_server_time()
            if resp.get("retCode") != 0:
                return
            # Top-level `time` is server ms; timeNano is full unix ns (not sub-second fraction).
            if resp.get("time") is not None:
                server_ms = int(resp["time"])
            else:
                result = resp.get("result", {})
                time_nano = int(result.get("timeNano", 0) or 0)
                if time_nano > 1_000_000_000_000:
                    server_ms = time_nano // 1_000_000
                else:
                    server_ms = int(result.get("timeSecond", 0) or 0) * 1000 + time_nano // 1_000_000
            local_ms = int(time.time() * 1000)
            skew_ms = abs(local_ms - server_ms)
            if skew_ms > threshold_ms:
                logger.warning(
                    "Bybit time skew: local clock differs from exchange by %d ms "
                    "(recv_window=%d). Sync Windows time: "
                    "'net start w32time' then 'w32tm /resync' (as Administrator).",
                    skew_ms,
                    self.recv_window,
                )
        except Exception as e:
            logger.debug("Could not check Bybit server time: %s", e)

    # -------------------------------------------------------------------------
    # Account & Balance
    # -------------------------------------------------------------------------
    
    def get_wallet_balance(self, coin: str = "USDT") -> Optional[Dict[str, Any]]:
        """
        Получить баланс кошелька для указанной монеты.
        
        Returns:
            Dict с полями: equity, available_balance, wallet_balance, unrealised_pnl
        """
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED",
                coin=coin
            )
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return None
            
            result = response.get("result", {})
            coin_list = result.get("list", [])
            
            if not coin_list:
                return None
            
            # Находим нужную монету
            for coin_data in coin_list[0].get("coin", []):
                if coin_data.get("coin") == coin:
                    return {
                        "coin": coin,
                        "equity": _safe_float(coin_data.get("equity")),
                        "wallet_balance": _safe_float(coin_data.get("walletBalance")),
                        "available_balance": _safe_float(
                            coin_data.get("availableToWithdraw")
                            or coin_data.get("availableBalance")
                        ),
                        "unrealised_pnl": _safe_float(coin_data.get("unrealisedPnl")),
                        "cum_realised_pnl": _safe_float(coin_data.get("cumRealisedPnl")),
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching wallet balance: {e}")
            return None

    def get_unified_wallet(self) -> Optional[Dict[str, Any]]:
        """
        Получить сводку UNIFIED Trading аккаунта (totalEquity, totalPerpUPL, все монеты).

        Соответствует блоку «Unified Trading» в интерфейсе Bybit.
        """
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED")

            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return None

            coin_list = response.get("result", {}).get("list", [])
            if not coin_list:
                return None

            account = coin_list[0]
            coins = []
            for coin_data in account.get("coin", []):
                coins.append({
                    "coin": coin_data.get("coin", ""),
                    "equity": _safe_float(coin_data.get("equity")),
                    "wallet_balance": _safe_float(coin_data.get("walletBalance")),
                    "usd_value": _safe_float(coin_data.get("usdValue")),
                    "unrealised_pnl": _safe_float(coin_data.get("unrealisedPnl")),
                    "available_balance": _safe_float(
                        coin_data.get("availableToWithdraw")
                        or coin_data.get("availableBalance")
                    ),
                    "bonus": _safe_float(coin_data.get("bonus")),
                })

            coins.sort(key=lambda c: c.get("usd_value", 0), reverse=True)

            return {
                "account_type": account.get("accountType", "UNIFIED"),
                "total_equity": _safe_float(account.get("totalEquity")),
                "total_wallet_balance": _safe_float(account.get("totalWalletBalance")),
                "total_available_balance": _safe_float(account.get("totalAvailableBalance")),
                "total_perp_upl": _safe_float(account.get("totalPerpUPL")),
                "total_initial_margin": _safe_float(account.get("totalInitialMargin")),
                "total_maintenance_margin": _safe_float(account.get("totalMaintenanceMargin")),
                "coins": coins,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error fetching unified wallet: {e}")
            return None
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Получить информацию об аккаунте."""
        try:
            response = self.session.get_account_info()
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return None
            
            return response.get("result", {})
            
        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            return None
    
    # -------------------------------------------------------------------------
    # Positions
    # -------------------------------------------------------------------------
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получить открытые позиции.
        
        Args:
            symbol: Опционально — фильтр по символу (например "BTCUSDT")
        
        Returns:
            Список позиций с полями: symbol, side, size, entry_price, leverage, unrealised_pnl
        """
        try:
            params = {
                "category": "linear",
                "settleCoin": "USDT"
            }
            if symbol:
                params["symbol"] = symbol
            
            response = self.session.get_positions(**params)
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return []
            
            result = response.get("result", {})
            positions = result.get("list", [])
            
            formatted = []
            for pos in positions:
                # Фильтруем только ненулевые позиции
                size = float(pos.get("size", 0))
                if size == 0:
                    continue
                
                formatted.append({
                    "symbol": pos.get("symbol"),
                    "side": pos.get("side"),  # Buy или Sell
                    "size": size,
                    "entry_price": float(pos.get("avgPrice", 0)),
                    "mark_price": float(pos.get("markPrice", 0)),
                    "leverage": float(pos.get("leverage", 1)),
                    "unrealised_pnl": float(pos.get("unrealisedPnl", 0)),
                    "realised_pnl": float(pos.get("cumRealisedPnl", 0)),
                    "position_value": float(pos.get("positionValue", 0)),
                    "liq_price": float(pos.get("liqPrice", 0)) if pos.get("liqPrice") else None,
                    "take_profit": float(pos.get("takeProfit", 0)) if pos.get("takeProfit") else None,
                    "stop_loss": float(pos.get("stopLoss", 0)) if pos.get("stopLoss") else None
                })
            
            return formatted
            
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Получить позицию по конкретному символу."""
        positions = self.get_positions(symbol=symbol)
        return positions[0] if positions else None
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Установить плечо для символа.
        
        Args:
            symbol: Торговая пара (например "BTCUSDT")
            leverage: Плечо (1-100 для linear perpetual)
        
        Returns:
            True если успешно
        """
        try:
            response = self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
            
            ret_code = response.get("retCode")
            if ret_code != 0:
                ret_msg = response.get("retMsg") or ""
                if _is_leverage_unchanged(ret_code=ret_code, message=ret_msg):
                    logger.debug(f"Leverage for {symbol} already {leverage}x")
                    return True
                logger.error(f"Bybit API error setting leverage: {ret_msg}")
                return False
            
            logger.info(f"Leverage for {symbol} set to {leverage}x")
            return True
            
        except Exception as e:
            if _is_leverage_unchanged(message=str(e)):
                logger.debug(f"Leverage for {symbol} already {leverage}x")
                return True
            logger.error(f"Error setting leverage: {e}")
            return False
    
    # -------------------------------------------------------------------------
    # Market Data
    # -------------------------------------------------------------------------
    
    def get_klines(
        self,
        symbol: str,
        interval: str = "60",
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить исторические свечи (klines/candles).
        
        Args:
            symbol: Торговая пара (например "BTCUSDT")
            interval: Интервал — 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, M, W
            limit: Количество свечей (max 1000)
            start_time: Начальное время в мс (опционально)
            end_time: Конечное время в мс (опционально)
        
        Returns:
            Список свечей с полями: datetime, open, high, low, close, volume
        """
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": min(limit, 1000)
            }
            
            if start_time:
                params["start"] = start_time
            if end_time:
                params["end"] = end_time
            
            response = self.session.get_kline(**params)
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return []
            
            result = response.get("result", {})
            klines = result.get("list", [])
            
            # Bybit возвращает: [timestamp, open, high, low, close, volume, turnover]
            formatted = []
            for k in reversed(klines):  # От старых к новым
                timestamp_ms = int(k[0])
                dt = datetime.fromtimestamp(timestamp_ms / 1000)
                
                formatted.append({
                    "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "timestamp_ms": timestamp_ms,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "turnover": float(k[6])
                })
            
            return formatted
            
        except Exception as e:
            logger.error(f"Error fetching klines for {symbol}: {e}")
            return []
    
    def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Получить текущие цены тикера.
        
        Returns:
            Dict с полями: last_price, bid, ask, mark_price, index_price, volume_24h
        """
        try:
            response = self.session.get_tickers(
                category="linear",
                symbol=symbol
            )
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return None
            
            result = response.get("result", {})
            tickers = result.get("list", [])
            
            if not tickers:
                return None
            
            ticker = tickers[0]
            
            return {
                "symbol": ticker.get("symbol"),
                "last_price": float(ticker.get("lastPrice", 0)),
                "bid": float(ticker.get("bid1Price", 0)),
                "ask": float(ticker.get("ask1Price", 0)),
                "mark_price": float(ticker.get("markPrice", 0)),
                "index_price": float(ticker.get("indexPrice", 0)),
                "volume_24h": float(ticker.get("volume24h", 0)),
                "turnover_24h": float(ticker.get("turnover24h", 0)),
                "funding_rate": float(ticker.get("fundingRate", 0)) if ticker.get("fundingRate") else None,
                "next_funding_time": ticker.get("nextFundingTime")
            }
            
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None
    
    def get_orderbook(self, symbol: str, limit: int = 25) -> Optional[Dict[str, Any]]:
        """
        Получить стакан ордеров.
        
        Args:
            symbol: Торговая пара
            limit: Глубина стакана (1, 25, 50, 100, 200, 500)
        
        Returns:
            Dict с полями: bids, asks (списки [price, size])
        """
        try:
            response = self.session.get_orderbook(
                category="linear",
                symbol=symbol,
                limit=limit
            )
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return None
            
            result = response.get("result", {})
            
            return {
                "symbol": result.get("s"),
                "bids": [[float(b[0]), float(b[1])] for b in result.get("b", [])],  # [price, size]
                "asks": [[float(a[0]), float(a[1])] for a in result.get("a", [])],  # [price, size]
                "timestamp": result.get("ts")
            }
            
        except Exception as e:
            logger.error(f"Error fetching orderbook for {symbol}: {e}")
            return None
    
    def get_instruments(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получить информацию о торговых инструментах.
        
        Returns:
            Список инструментов с min/max order sizes, price precision и т.д.
        """
        try:
            params = {"category": "linear"}
            if symbol:
                params["symbol"] = symbol
            
            response = self.session.get_instruments_info(**params)
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return []
            
            result = response.get("result", {})
            instruments = result.get("list", [])
            
            formatted = []
            for inst in instruments:
                lot_size = inst.get("lotSizeFilter", {})
                price_filter = inst.get("priceFilter", {})
                
                formatted.append({
                    "symbol": inst.get("symbol"),
                    "status": inst.get("status"),
                    "base_coin": inst.get("baseCoin"),
                    "quote_coin": inst.get("quoteCoin"),
                    "contract_type": inst.get("contractType"),
                    "min_order_qty": float(lot_size.get("minOrderQty", 0)),
                    "max_order_qty": float(lot_size.get("maxOrderQty", 0)),
                    "qty_step": float(lot_size.get("qtyStep", 0)),
                    "min_price": float(price_filter.get("minPrice", 0)),
                    "max_price": float(price_filter.get("maxPrice", 0)),
                    "tick_size": float(price_filter.get("tickSize", 0))
                })
            
            return formatted
            
        except Exception as e:
            logger.error(f"Error fetching instruments: {e}")
            return []
    
    # -------------------------------------------------------------------------
    # Trading - Orders
    # -------------------------------------------------------------------------
    
    def place_order(
        self,
        symbol: str,
        side: str,  # "Buy" или "Sell"
        order_type: str,  # "Market" или "Limit"
        qty: float,
        price: Optional[float] = None,
        time_in_force: str = "GTC",  # GTC, IOC, FOK
        reduce_only: bool = False,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        sl_trigger_by: str = "LastPrice",
        tp_trigger_by: str = "LastPrice",
        order_link_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Разместить ордер.
        
        Args:
            symbol: Торговая пара
            side: "Buy" или "Sell"
            order_type: "Market" или "Limit"
            qty: Количество (в контрактах/монетах)
            price: Цена (только для Limit)
            time_in_force: GTC (Good Till Cancel), IOC (Immediate or Cancel), FOK (Fill or Kill)
            reduce_only: Только для уменьшения позиции
            stop_loss: Цена стоп-лосса
            take_profit: Цена тейк-профита
            sl_trigger_by: Триггер для SL (LastPrice, IndexPrice, MarkPrice)
            tp_trigger_by: Триггер для TP
            order_link_id: Кастомный ID для отслеживания
        
        Returns:
            Dict с order_id и другими полями
        """
        try:
            qty_step = tick_size = 0.0
            instruments = self.get_instruments(symbol=symbol)
            if instruments:
                inst = instruments[0]
                qty_step = inst.get("qty_step") or 0.0
                tick_size = inst.get("tick_size") or 0.0
                try:
                    qty, price, stop_loss, take_profit = normalize_order_params(
                        qty,
                        qty_step=qty_step,
                        min_order_qty=inst.get("min_order_qty") or 0.0,
                        max_order_qty=inst.get("max_order_qty") or 0.0,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        entry_price=price,
                        tick_size=tick_size,
                    )
                except ValueError as e:
                    logger.error(f"Order qty invalid for {symbol}: {e}")
                    return None

            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": format_bybit_decimal(qty, qty_step) if qty_step > 0 else str(qty),
                "timeInForce": time_in_force,
                "reduceOnly": reduce_only
            }
            
            if order_type == "Limit" and price is not None:
                params["price"] = (
                    format_bybit_decimal(price, tick_size) if tick_size > 0 else str(price)
                )
            
            if stop_loss is not None:
                params["stopLoss"] = (
                    format_bybit_decimal(stop_loss, tick_size) if tick_size > 0 else str(stop_loss)
                )
                params["slTriggerBy"] = sl_trigger_by
            
            if take_profit is not None:
                params["takeProfit"] = (
                    format_bybit_decimal(take_profit, tick_size) if tick_size > 0 else str(take_profit)
                )
                params["tpTriggerBy"] = tp_trigger_by
            
            if order_link_id:
                params["orderLinkId"] = order_link_id
            
            response = self.session.place_order(**params)
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error placing order: {response.get('retMsg')}")
                return None
            
            result = response.get("result", {})
            
            return {
                "order_id": result.get("orderId"),
                "order_link_id": result.get("orderLinkId"),
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "qty": qty,
                "price": price
            }
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def place_bracket_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: Optional[float] = None,
        stop_loss: float = None,
        take_profit: float = None,
        order_type: str = "Limit",
        time_in_force: str = "GTC",
        order_link_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Разместить bracket ордер (entry + TP + SL).
        
        Для Bybit это один ордер с attached TP/SL.
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            price=entry_price,
            time_in_force=time_in_force,
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_link_id=order_link_id
        )
    
    def cancel_order(self, symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None) -> bool:
        """
        Отменить ордер.
        
        Args:
            symbol: Торговая пара
            order_id: ID ордера из Bybit
            order_link_id: Кастомный ID (альтернатива order_id)
        
        Returns:
            True если успешно
        """
        try:
            params = {
                "category": "linear",
                "symbol": symbol
            }
            
            if order_id:
                params["orderId"] = order_id
            elif order_link_id:
                params["orderLinkId"] = order_link_id
            else:
                logger.error("Either order_id or order_link_id must be provided")
                return False
            
            response = self.session.cancel_order(**params)
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error canceling order: {response.get('retMsg')}")
                return False
            
            logger.info(f"Order canceled: {order_id or order_link_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return False
    
    def cancel_all_orders(self, symbol: Optional[str] = None, settle_coin: str = "USDT") -> bool:
        """Отменить все открытые ордера."""
        try:
            params: Dict[str, Any] = {"category": "linear"}
            if symbol:
                params["symbol"] = symbol
            else:
                params["settleCoin"] = settle_coin

            response = self.session.cancel_all_orders(**params)
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return False
            
            logger.info(f"All orders canceled for {symbol or 'all symbols'}")
            return True
            
        except Exception as e:
            logger.error(f"Error canceling all orders: {e}")
            return False
    
    @staticmethod
    def _format_order_record(order: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Bybit order JSON to snake_case fields used by sync code."""
        return {
            "order_id": order.get("orderId"),
            "order_link_id": order.get("orderLinkId"),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "order_type": order.get("orderType"),
            "price": _safe_float(order.get("price")),
            "qty": _safe_float(order.get("qty")),
            "leaves_qty": _safe_float(order.get("leavesQty")),
            "cum_exec_qty": _safe_float(order.get("cumExecQty")),
            "cum_exec_value": _safe_float(order.get("cumExecValue")),
            "status": order.get("orderStatus"),
            "time_in_force": order.get("timeInForce"),
            "created_time": order.get("createdTime"),
            "updated_time": order.get("updatedTime"),
            "stop_loss": _safe_float(order.get("stopLoss")) if order.get("stopLoss") else None,
            "take_profit": _safe_float(order.get("takeProfit")) if order.get("takeProfit") else None,
            "reduce_only": order.get("reduceOnly", False),
        }

    def _order_query_params(
        self,
        *,
        symbol: Optional[str],
        order_id: Optional[str],
        order_link_id: Optional[str],
        settle_coin: str = "USDT",
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"category": "linear"}
        if symbol:
            params["symbol"] = symbol
        else:
            # Bybit v5 requires symbol, settleCoin, or baseCoin for linear open orders.
            params["settleCoin"] = settle_coin
        if order_id:
            params["orderId"] = order_id
        elif order_link_id:
            params["orderLinkId"] = order_link_id
        return params

    def get_open_orders(
        self,
        symbol: Optional[str] = None,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получить открытые ордера.
        
        Returns:
            Список ордеров с полями: order_id, symbol, side, order_type, price, qty, status
        """
        try:
            params = self._order_query_params(
                symbol=symbol, order_id=order_id, order_link_id=order_link_id
            )
            response = self.session.get_open_orders(**params)
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return []
            
            result = response.get("result", {})
            orders = result.get("list", [])
            return [self._format_order_record(order) for order in orders]
            
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []
    
    def get_order_history(
        self,
        symbol: Optional[str] = None,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Получить историю ордеров."""
        try:
            params = self._order_query_params(
                symbol=symbol, order_id=order_id, order_link_id=order_link_id
            )
            params["limit"] = min(limit, 50)
            
            response = self.session.get_order_history(**params)
            
            if response.get("retCode") != 0:
                logger.error(f"Bybit API error: {response.get('retMsg')}")
                return []
            
            result = response.get("result", {})
            orders = result.get("list", [])
            return [self._format_order_record(order) for order in orders]
            
        except Exception as e:
            logger.error(f"Error fetching order history: {e}")
            return []
    
    def get_transaction_log(
        self,
        *,
        account_type: str = "UNIFIED",
        category: Optional[str] = None,
        currency: Optional[str] = None,
        base_coin: Optional[str] = None,
        trans_type: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch Bybit UTA transaction log page (GET /v5/account/transaction-log).

        Returns:
            {"list": [...], "nextPageCursor": "..."} or empty list on error.
        """
        try:
            params: Dict[str, Any] = {
                "accountType": account_type,
                "limit": min(max(limit, 1), 50),
            }
            if category:
                params["category"] = category
            if currency:
                params["currency"] = currency.upper()
            if base_coin:
                params["baseCoin"] = base_coin.upper()
            if trans_type:
                params["type"] = trans_type
            if start_time is not None:
                params["startTime"] = int(start_time)
            if end_time is not None:
                params["endTime"] = int(end_time)
            if cursor:
                params["cursor"] = cursor

            response = self.session.get_transaction_log(**params)
            if response.get("retCode") != 0:
                logger.error(
                    "Bybit transaction log error: %s",
                    response.get("retMsg"),
                )
                return {"list": [], "nextPageCursor": ""}

            result = response.get("result") or {}
            return {
                "list": result.get("list") or [],
                "nextPageCursor": result.get("nextPageCursor") or "",
            }
        except Exception as e:
            logger.error("Error fetching transaction log: %s", e)
            return {"list": [], "nextPageCursor": ""}

    # -------------------------------------------------------------------------
    # Close Position
    # -------------------------------------------------------------------------
    
    def close_position_market(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Закрыть позицию по рыночной цене.
        
        Returns:
            Dict с результатом ордера или None
        """
        # Сначала получаем позицию
        position = self.get_position(symbol)
        if not position:
            logger.warning(f"No position to close for {symbol}")
            return None
        
        side = position["side"]
        qty = position["size"]
        
        # Противоположная сторона для закрытия
        close_side = "Sell" if side == "Buy" else "Buy"
        
        return self.place_order(
            symbol=symbol,
            side=close_side,
            order_type="Market",
            qty=qty,
            reduce_only=True
        )
    
    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------
    
    def get_server_time(self) -> Optional[int]:
        """Получить серверное время Bybit (в мс)."""
        try:
            response = self.session.get_server_time()
            if response.get("retCode") == 0:
                return response.get("result", {}).get("timeSecond")
            return None
        except Exception as e:
            logger.error(f"Error fetching server time: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Проверить подключение к API."""
        try:
            # Пробуем получить баланс как тест
            balance = self.get_wallet_balance("USDT")
            if balance is not None:
                logger.info("Bybit API connection test: OK")
                return True
            return False
        except Exception as e:
            logger.error(f"Bybit API connection test failed: {e}")
            return False


# -----------------------------------------------------------------------------
# Singleton instance for worker pattern (similar to ib_worker)
# -----------------------------------------------------------------------------

_bybit_client: Optional[BybitClient] = None


def init_bybit_client(
    api_key: str = "",
    api_secret: str = "",
    demo: bool = True,
    recv_window: int = 60000,
) -> BybitClient:
    """Инициализировать глобальный клиент (market data works without credentials)."""
    global _bybit_client
    _bybit_client = BybitClient(api_key, api_secret, demo, recv_window=recv_window)
    return _bybit_client


def get_bybit_client() -> Optional[BybitClient]:
    """Получить глобальный клиент."""
    return _bybit_client


def close_bybit_client():
    """Закрыть клиент."""
    global _bybit_client
    _bybit_client = None
