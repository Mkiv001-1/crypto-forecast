# Удаление IB/stock мёртвого кода

Убрать все нефункциональные Interactive Brokers и stock-специфичные артефакты, оставшиеся после миграции на Bybit.

---

## Найденные проблемы

### 1. `scripts/client/api_client.py` — IB-методы (dead code)
Методы, обращающиеся к несуществующим IB-эндпоинтам:
- `get_ib_portfolio_summary()`, `test_ib_connection()`, `get_ib_position_status()`, `get_ib_order_status()`
- `get_ib_configs/config/create/update/delete_ib_config()` → `/ib-config` CRUD
- `get_ib_transactions()`
- Импорт `IBConfigRecord`, `IBConfigResponse` из `scripts.shared.models`

### 2. `scripts/client/gui_main.py` — IB GUI-виджеты (dead code)
- `_load_summary_from_ib()` + вызов в `load()`
- Группа **"IB Gateway Connection"** в настройках (`IB_HOST`, `IB_PORT`, `IB_CLIENT_ID`, комментарий «7497 for TWS…»)
- Группа **"IB Order Types Reference"** (`orders_table`)
- Кнопки **"Sync with IB Gateway"** + log-строки «Connecting to IB Gateway…» (AccountsTab, PortfolioTab)
- `con_id_edit` + **"Live Position Status"** + `_on_live_position_status` (PortfolioTab)
- `ib_order_id_edit` + **"Live Order Status"** + `_on_live_order_status` (OrdersTab)
- `ib_ok` → переименовать в `bybit_ok` в HeartbeatTab (данные уже пишутся scheduler-ом как bybit_ok)

### 3. `scripts/core/sqlite_manager.py` — IB-артефакты в конфиге и схеме
- `_DEFAULT_CONFIG`: убрать `IB_GATEWAY_HOST/PORT/CLIENT_ID`; обновить descriptions у `IB_CAPITAL_FAILSAFE`, `PREFERRED_ACCOUNT_TYPE`, `MANUAL_CAPITAL_OVERRIDE`, `RISK_ACCOUNT_ID`, `CAPITAL_STALENESS_MINUTES`; убрать NYSE-подсказки из `ORDER_WINDOW_START/END`
- `broker DEFAULT 'ibkr'` в таблицах `accounts`, `portfolio` → `DEFAULT 'bybit'`
- `asset_type DEFAULT 'STK'` в `portfolio` → `DEFAULT 'CRYPTO'`
- `heartbeat_log.ib_ok` → `ALTER TABLE … RENAME COLUMN ib_ok TO bybit_ok` в migrate
- Дублирующие записи этих же ключей в блоке migrate внутри `sqlite_manager.py` — синхронизировать

### 4. `scripts/core/position_sizer.py` — импорт несуществующего `capital_provider`
- `from capital_provider import get_net_liquidation` / `get_portfolio_net_liquidation` — IB-era модуль, отсутствует в core/
- Заменить на эквиваленты из `bybit_capital_provider`; обновить docstring

### 5. `scripts/core/scheduler.py` — IB_GATEWAY ключи
- Проверить/убрать обращения к `IB_GATEWAY_HOST`, `IB_GATEWAY_PORT`, `IB_GATEWAY_CLIENT_ID`

---

## Шаги реализации

| # | Файл | Действие |
|---|------|----------|
| 1 | `api_client.py` | Удалить 9 IB-методов + импорт `IBConfigRecord/IBConfigResponse` |
| 2 | `gui_main.py` | Удалить IB-виджеты/методы (см. п.2); переименовать `ib_ok` → `bybit_ok`; кнопки Sync → «Sync with Bybit» |
| 3 | `sqlite_manager.py` | Обновить descriptions; `DEFAULT 'ibkr'` → `'bybit'`; `DEFAULT 'STK'` → `'CRYPTO'`; NYSE-подсказки убрать; добавить RENAME COLUMN в migrate |
| 4 | `position_sizer.py` | Заменить импорт `capital_provider` → `bybit_capital_provider`; обновить docstring |
| 5 | `scheduler.py` | Убрать IB_GATEWAY_* конфиг-ключи если используются |

### Не трогаем сейчас (риск миграции данных)
- Переименование таблиц `ib_gateway_log`, `ib_order_transactions`, `ib_order_types`
- Переименование полей `ib_order_id`, `ib_perm_id`, `ib_parent_id` в таблицах
- `position_sizer_backup.py`, `position_sizer_updated.py` — синхронизировать после основного
