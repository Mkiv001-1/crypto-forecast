"""
Bybit WebSocket Client — real-time market data and private updates.

Потоки:
- Public: тикеры, стаканы, сделки (не требует аутентификации)
- Private: ордера, позиции, исполнения (требует аутентификации)

Bybit WebSocket URLs:
- Public Linear: wss://stream.bybit.com/v5/public/linear
- Private: wss://stream.bybit.com/v5/private
"""

import asyncio
import json
import logging
import time
from typing import Callable, Dict, Any, Optional, Set
from dataclasses import dataclass, field

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


@dataclass
class WSState:
    """Состояние WebSocket соединения."""
    connected: bool = False
    authenticated: bool = False
    last_ping: float = 0
    last_pong: float = 0
    subscriptions: Set[str] = field(default_factory=set)


class BybitWebSocketClient:
    """
    WebSocket клиент для Bybit.
    
    Поддерживает:
    - Подписка на тикеры (tickers)
    - Подписка на стаканы (orderbook)
    - Приватные обновления (ордера, позиции, исполнения)
    - Автоматический reconnect
    - Heartbeat/ping-pong
    """
    
    PUBLIC_WS_URL = "wss://stream.bybit.com/v5/public/linear"
    PRIVATE_WS_URL = "wss://stream.bybit.com/v5/private"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        ping_interval: int = 20,
        pong_timeout: int = 10,
        reconnect_delay: float = 5.0
    ):
        """
        Инициализация.
        
        Args:
            api_key: Требуется только для private потока
            api_secret: Требуется только для private потока
            ping_interval: Интервал пинга в секундах
            pong_timeout: Таймаут ожидания понга
            reconnect_delay: Задержка перед reconnect
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.ping_interval = ping_interval
        self.pong_timeout = pong_timeout
        self.reconnect_delay = reconnect_delay
        
        # WebSocket connections
        self._public_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._private_ws: Optional[websockets.WebSocketClientProtocol] = None
        
        # States
        self._public_state = WSState()
        self._private_state = WSState()
        
        # Callbacks
        self._ticker_callbacks: Dict[str, Callable] = {}
        self._orderbook_callbacks: Dict[str, Callable] = {}
        self._trade_callbacks: Dict[str, Callable] = {}
        self._private_callbacks: Dict[str, Callable] = {}
        
        # Tasks
        self._tasks: list = []
        self._running = False
        
        logger.info("BybitWebSocketClient initialized")
    
    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------
    
    async def connect(self, public: bool = True, private: bool = False):
        """
        Установить WebSocket соединения.
        
        Args:
            public: Подключиться к public потоку
            private: Подключиться к private потоку (требует api_key)
        """
        self._running = True
        
        if public:
            await self._connect_public()
        
        if private:
            if not self.api_key or not self.api_secret:
                raise ValueError("API key and secret required for private stream")
            await self._connect_private()
    
    async def _connect_public(self):
        """Подключиться к public WebSocket."""
        try:
            logger.info(f"Connecting to public WebSocket: {self.PUBLIC_WS_URL}")
            self._public_ws = await websockets.connect(self.PUBLIC_WS_URL)
            self._public_state.connected = True
            self._public_state.last_ping = time.time()
            
            # Start handler task
            task = asyncio.create_task(self._handle_public_messages())
            self._tasks.append(task)
            
            # Resubscribe to previous subscriptions
            if self._public_state.subscriptions:
                await self._subscribe_public(list(self._public_state.subscriptions))
            
            logger.info("Public WebSocket connected")
            
        except Exception as e:
            logger.error(f"Failed to connect to public WebSocket: {e}")
            self._public_state.connected = False
            raise
    
    async def _connect_private(self):
        """Подключиться к private WebSocket с аутентификацией."""
        try:
            logger.info(f"Connecting to private WebSocket: {self.PRIVATE_WS_URL}")
            self._private_ws = await websockets.connect(self.PRIVATE_WS_URL)
            
            # Аутентификация
            await self._authenticate_private()
            
            self._private_state.connected = True
            self._private_state.authenticated = True
            self._private_state.last_ping = time.time()
            
            # Start handler task
            task = asyncio.create_task(self._handle_private_messages())
            self._tasks.append(task)
            
            logger.info("Private WebSocket connected and authenticated")
            
        except Exception as e:
            logger.error(f"Failed to connect to private WebSocket: {e}")
            self._private_state.connected = False
            self._private_state.authenticated = False
            raise
    
    async def _authenticate_private(self):
        """Аутентификация на private WebSocket."""
        import hmac
        import hashlib
        
        expires = int((time.time() + 1) * 1000)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            f'GET/realtime{expires}'.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        auth_msg = {
            "op": "auth",
            "args": [self.api_key, expires, signature]
        }
        
        await self._private_ws.send(json.dumps(auth_msg))
        
        # Wait for auth response
        response = await self._private_ws.recv()
        data = json.loads(response)
        
        if data.get("success"):
            logger.info("WebSocket authentication successful")
        else:
            raise Exception(f"WebSocket authentication failed: {data}")
    
    async def disconnect(self):
        """Отключиться от всех WebSocket."""
        self._running = False
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        if self._public_ws:
            await self._public_ws.close()
            self._public_ws = None
        
        if self._private_ws:
            await self._private_ws.close()
            self._private_ws = None
        
        self._public_state.connected = False
        self._private_state.connected = False
        
        logger.info("WebSocket disconnected")
    
    # -------------------------------------------------------------------------
    # Message Handlers
    # -------------------------------------------------------------------------
    
    async def _handle_public_messages(self):
        """Обработчик сообщений public WebSocket."""
        while self._running and self._public_ws:
            try:
                message = await self._public_ws.recv()
                await self._process_public_message(message)
                
            except ConnectionClosed:
                logger.warning("Public WebSocket connection closed")
                self._public_state.connected = False
                if self._running:
                    await asyncio.sleep(self.reconnect_delay)
                    await self._connect_public()
            except Exception as e:
                logger.error(f"Error handling public message: {e}")
    
    async def _handle_private_messages(self):
        """Обработчик сообщений private WebSocket."""
        while self._running and self._private_ws:
            try:
                message = await self._private_ws.recv()
                await self._process_private_message(message)
                
            except ConnectionClosed:
                logger.warning("Private WebSocket connection closed")
                self._private_state.connected = False
                self._private_state.authenticated = False
                if self._running:
                    await asyncio.sleep(self.reconnect_delay)
                    await self._connect_private()
            except Exception as e:
                logger.error(f"Error handling private message: {e}")
    
    async def _process_public_message(self, message: str):
        """Обработать сообщение из public потока."""
        try:
            data = json.loads(message)
            
            # Ping-pong
            if data.get("op") == "pong":
                self._public_state.last_pong = time.time()
                return
            
            # Subscription response
            if "success" in data:
                if not data.get("success"):
                    logger.error(f"Subscription failed: {data}")
                return
            
            # Market data
            topic = data.get("topic", "")
            payload = data.get("data", {})
            
            if topic.startswith("tickers."):
                symbol = topic.replace("tickers.", "")
                if symbol in self._ticker_callbacks:
                    self._ticker_callbacks[symbol](payload)
            
            elif topic.startswith("orderbook."):
                symbol = topic.split(".")[-1]
                if symbol in self._orderbook_callbacks:
                    self._orderbook_callbacks[symbol](payload)
            
            elif topic.startswith("publicTrade."):
                symbol = topic.replace("publicTrade.", "")
                if symbol in self._trade_callbacks:
                    self._trade_callbacks[symbol](payload)
                    
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON received: {message[:100]}")
        except Exception as e:
            logger.error(f"Error processing public message: {e}")
    
    async def _process_private_message(self, message: str):
        """Обработать сообщение из private потока."""
        try:
            data = json.loads(message)
            
            # Ping-pong
            if data.get("op") == "pong":
                self._private_state.last_pong = time.time()
                return
            
            # Private topics
            topic = data.get("topic", "")
            payload = data.get("data", {})
            
            if topic == "order":
                self._notify_private("order", payload)
            elif topic == "position":
                self._notify_private("position", payload)
            elif topic == "execution":
                self._notify_private("execution", payload)
            elif topic == "wallet":
                self._notify_private("wallet", payload)
                    
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON received: {message[:100]}")
        except Exception as e:
            logger.error(f"Error processing private message: {e}")
    
    def _notify_private(self, event_type: str, data: Any):
        """Уведомить private callbacks."""
        if event_type in self._private_callbacks:
            try:
                self._private_callbacks[event_type](data)
            except Exception as e:
                logger.error(f"Error in private callback: {e}")
    
    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------
    
    async def subscribe_ticker(self, symbol: str, callback: Callable[[Dict], None]):
        """
        Подписаться на тикер обновления.
        
        Args:
            symbol: Торговая пара (например "BTCUSDT")
            callback: Функция(data) для обработки обновлений
        """
        topic = f"tickers.{symbol}"
        self._ticker_callbacks[symbol] = callback
        self._public_state.subscriptions.add(topic)
        
        if self._public_state.connected:
            await self._subscribe_public([topic])
    
    async def subscribe_orderbook(self, symbol: str, depth: int = 50, callback: Callable[[Dict], None] = None):
        """
        Подписаться на стакан ордеров.
        
        Args:
            symbol: Торговая пара
            depth: Глубина (1, 50, 200, 500)
            callback: Функция(data) для обработки обновлений
        """
        topic = f"orderbook.{depth}.{symbol}"
        self._orderbook_callbacks[symbol] = callback
        self._public_state.subscriptions.add(topic)
        
        if self._public_state.connected:
            await self._subscribe_public([topic])
    
    async def subscribe_trades(self, symbol: str, callback: Callable[[Dict], None]):
        """Подписаться на публичные сделки."""
        topic = f"publicTrade.{symbol}"
        self._trade_callbacks[symbol] = callback
        self._public_state.subscriptions.add(topic)
        
        if self._public_state.connected:
            await self._subscribe_public([topic])
    
    async def _subscribe_public(self, topics: list):
        """Отправить запрос подписки на public WebSocket."""
        if not self._public_ws:
            return
        
        msg = {
            "op": "subscribe",
            "args": [{"channel": t} for t in topics]
        }
        
        await self._public_ws.send(json.dumps(msg))
        logger.info(f"Subscribed to public topics: {topics}")
    
    def on_private(self, event_type: str, callback: Callable[[Dict], None]):
        """
        Зарегистрировать callback для private событий.
        
        Args:
            event_type: "order", "position", "execution", "wallet"
            callback: Функция(data) для обработки событий
        """
        self._private_callbacks[event_type] = callback
    
    async def _send_ping(self):
        """Отправить ping на оба соединения."""
        ping_msg = json.dumps({"op": "ping"})
        
        if self._public_ws and self._public_state.connected:
            try:
                await self._public_ws.send(ping_msg)
                self._public_state.last_ping = time.time()
            except Exception as e:
                logger.warning(f"Failed to send public ping: {e}")
        
        if self._private_ws and self._private_state.connected:
            try:
                await self._private_ws.send(ping_msg)
                self._private_state.last_ping = time.time()
            except Exception as e:
                logger.warning(f"Failed to send private ping: {e}")
    
    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------
    
    @property
    def is_public_connected(self) -> bool:
        """Public соединение активно."""
        return self._public_state.connected
    
    @property
    def is_private_connected(self) -> bool:
        """Private соединение активно и аутентифицировано."""
        return self._private_state.connected and self._private_state.authenticated
    
    def get_subscriptions(self) -> Set[str]:
        """Получить список активных подписок."""
        return self._public_state.subscriptions.copy()


# -----------------------------------------------------------------------------
# Helper functions for common use cases
# -----------------------------------------------------------------------------

async def create_ws_client(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    symbols: Optional[list] = None
) -> BybitWebSocketClient:
    """
    Создать и подключить WebSocket клиент с базовыми подписками.
    
    Args:
        api_key: Для private потока
        api_secret: Для private потока
        symbols: Список символов для подписки на tickers
    
    Returns:
        Подключенный клиент
    """
    client = BybitWebSocketClient(api_key, api_secret)
    
    # Connect
    await client.connect(
        public=True,
        private=bool(api_key and api_secret)
    )
    
    # Subscribe to tickers
    if symbols:
        for symbol in symbols:
            await client.subscribe_ticker(symbol, lambda d: logger.debug(f"Ticker {symbol}: {d}"))
    
    return client


# -----------------------------------------------------------------------------
# Sync wrapper for use in non-async contexts
# -----------------------------------------------------------------------------

class SyncBybitWSClient:
    """Синхронная обертка для WebSocket клиента."""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self._client: Optional[BybitWebSocketClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def connect(self, public: bool = True, private: bool = False):
        """Подключиться (блокирующий вызов)."""
        self._loop = asyncio.new_event_loop()
        self._client = BybitWebSocketClient(self.api_key, self.api_secret)
        self._loop.run_until_complete(self._client.connect(public, private))
        
        # Start background loop
        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        
        import threading
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
    
    def disconnect(self):
        """Отключиться."""
        if self._client and self._loop:
            future = asyncio.run_coroutine_threadsafe(self._client.disconnect(), self._loop)
            future.result(timeout=5)
        
        if self._loop:
            self._loop.stop()
    
    def subscribe_ticker(self, symbol: str, callback: Callable):
        """Подписаться на тикер."""
        if self._client and self._loop:
            future = asyncio.run_coroutine_threadsafe(
                self._client.subscribe_ticker(symbol, callback),
                self._loop
            )
            future.result(timeout=5)
