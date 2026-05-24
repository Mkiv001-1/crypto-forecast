# Хранение API ключей Bybit (multi-account ready)

Убрать хардкод секретов из кода и обеспечить безопасное, расширяемое хранение ключей для demo/live/sub-счётов.

## Проблемы сейчас

- `DEFAULT_BYBIT_CONFIG` в `bybit_config.py` содержит реальные API ключи в открытом виде — они попадут в git
- Нет `.gitignore` — файлы с секретами могут утечь
- Нет поддержки нескольких аккаунтов/профилей

## Предлагаемая архитектура

### Уровни хранения (приоритет от высшего к низшему)

```
1. Environment variables          ← наивысший приоритет
2. secrets.ini (вне git)          ← локальные ключи разработчика
3. SQLite config table            ← runtime-переключение через UI
4. DEFAULT_BYBIT_CONFIG           ← только не-секретные дефолты (ключи — пустые)
```

### Структура `secrets.ini`

```ini
# scripts/server/ini/secrets.ini  — добавить в .gitignore
[bybit_demo]
api_key    = ваш_демо_ключ
api_secret = ваш_демо_секрет

[bybit_live]
api_key    = ваш_лайв_ключ
api_secret = ваш_лайв_секрет

# Суб-счёт (расширение в будущем)
# [bybit_sub1]
# api_key    = ...
# api_secret = ...
```

- Активный профиль задаётся через `BYBIT_ACTIVE_PROFILE` (env var или SQLite config)
- Значения по умолчанию: `demo` / `live`
- При отсутствии файла — fallback на env vars без ошибки

### Порядок загрузки ключей в `load_bybit_config()`

```
1. defaults (пустые BYBIT_API_KEY / BYBIT_API_SECRET)
2. SQLite config table  (торговые настройки + BYBIT_ACTIVE_PROFILE)
3. secrets.ini[активный профиль]   ← НОВОЕ
4. env vars                        ← по-прежнему выше всего
```

## Файлы к изменению

| Файл | Действие |
|---|---|
| `d:/Git/crypto-forecast/.gitignore` | Создать — исключить `secrets.ini`, `.env*`, `__pycache__/`, `.venv*/` |
| `scripts/core/bybit_config.py` | Убрать хардкод ключей из дефолтов; добавить `_load_secrets_ini()`; обновить `load_bybit_config()` |
| `scripts/server/ini/secrets.ini` | Создать локально (не в git) с реальными ключами |
| `scripts/server/ini/secrets.ini.example` | Создать шаблон (в git) без реальных ключей |

## GUI управление ключами

### Что есть сейчас
- `_KeysSubTab` («🔐 Keys») — показывает все SQLite config-ключи в таблице, включая `BYBIT_API_KEY` и `BYBIT_API_SECRET` в открытом виде
- `_BybitSettingsSubTab` («⚙️ Bybit Settings») — торговые настройки без полей для ключей
- `PUT /config/{key}` — уже существует, используется обоими sub-tab

### Предлагаемые изменения в GUI

**Вариант: расширить `_BybitSettingsSubTab`** (рекомендуется)

Добавить секцию «API Credentials» прямо в существующий «⚙️ Bybit Settings»:

```
┌─ API Credentials ──────────────────────────────────┐
│ Active Profile:  [demo ▼]  (demo / live / sub1 …)  │
│ API Key:         [••••••••••••••]  [👁 Show]        │
│ API Secret:      [••••••••••••••]  [👁 Show]        │
│                  [💾 Save to secrets.ini]            │
└─────────────────────────────────────────────────────┘
```

- Поля `QLineEdit` с `setEchoMode(Password)` — ключи не видны по умолчанию
- Кнопка «👁 Show» переключает видимость
- Кнопка «💾 Save» пишет в `secrets.ini` (не в SQLite и не в git)
- Выбор профиля меняет `BYBIT_ACTIVE_PROFILE` в SQLite через `PUT /config/{key}`
- При загрузке таба: читаем активный профиль из config, заполняем поля из `secrets.ini` (через новый API endpoint)

**Новый API endpoint (сервер)**

```
GET  /bybit-credentials           → {profile, api_key_masked}  (ключ маскируется!)
PUT  /bybit-credentials           → {profile, api_key, api_secret}  → пишет в secrets.ini
```

- `BYBIT_API_SECRET` **никогда не возвращается** клиенту — только подтверждение «настроен / не настроен»
- Маска: `ywht...ML7` (первые 4 + последние 3 символа)

### Что остаётся в `_KeysSubTab`
- `BYBIT_API_KEY` и `BYBIT_API_SECRET` убрать из SQLite config table (или отображать как `***`)
- `BYBIT_ACTIVE_PROFILE` — показывается как обычный редактируемый ключ

## Не меняется

- `server_config.ini` — не затрагивается
- SQLite config table — по-прежнему хранит торговые настройки
- `init_bybit_client()` / `BybitClient` — публичный интерфейс не меняется
- `BybitConfig` dataclass — поле `profile_name: str = "demo"` добавляется опционально

## Переработка таблицы Accounts

### Новая структура колонок

| Колонка | Источник | Пример |
|---|---|---|
| Profile | secrets.ini секция | `demo` / `live` / `sub1` |
| Mode | `BYBIT_DEMO` для профиля | `Demo` / `Live` |
| UID | Bybit API `get_account_info()` | `123456789` |
| Account Type | Bybit API | `UNIFIED` |
| Equity (USDT) | `get_wallet_balance()` | `$1 234.56` |
| Available (USDT) | `availableToWithdraw` | `$987.00` |
| Unrealized PnL | сумма по позициям | `+$12.34` |
| Positions | кол-во открытых позиций | `3` |
| Active | текущий `BYBIT_ACTIVE_PROFILE` | `✅` / `—` |
| Connected | ключи заданы + тест | `✅` / `❌` |
| Last Sync | `last_update` из БД | `17:01:23` |

### Логика строк

- Строка на каждую секцию `[bybit_*]` из `secrets.ini`
- Если профиль **не активен** или ключи не заданы → `Connected=❌`, финансовые поля пустые
- Если профиль **активен** (совпадает с `BYBIT_ACTIVE_PROFILE`) → подтягиваются балансы из БД (последний синк)
- `Sync with Bybit` синкает только **активный** профиль (текущий воркер)
- Двойной клик по неактивной строке → предложение переключить профиль

### Изменения кода

**`AccountRecord` (models.py)**
- Добавить поля: `profile: str`, `mode: str`, `uid: str`, `unrealized_pnl: float`, `positions_count: int`, `connected: bool`, `active: bool`
- Убрать: `broker`, `name`, `base_currency`, `maintenance_margin`, `type` (заменяются на `mode`)

**`GET /accounts` (api.py)**
- Дополнительно читать список профилей из `secrets.ini`
- Для каждого профиля: смотреть запись в БД accounts (если есть), проверять `connected` (ключи не пустые)
- Возвращать строку на профиль даже если нет записи в БД

**`bybit_account_sync.py`**
- `sync_account_data()` — добавить получение UID через `get_account_info()`
- Сохранять `unrealized_pnl`, `positions_count`, `uid` в таблицу accounts

**`AccountsTab` (gui_main.py)**
- Заменить 9 старых колонок на 11 новых (см. таблицу выше)
- Цветовая маркировка строки: зелёный фон = активный профиль
- `_update_summary()` — считать только по активному профилю
- Двойной клик → диалог переключения активного профиля

## Расширение на несколько аккаунтов (будущее)

- Каждый профиль — отдельная секция `[bybit_<name>]` в `secrets.ini`
- `BYBIT_ACTIVE_PROFILE` переключается через UI или env var
- При необходимости параллельной работы: `init_bybit_client(profile=...)` создаёт именованный клиент в dict вместо одного глобального
