# План рефакторинга кода

Живой документ. Обновляется перед каждой рефакторинг-сессией.

---

## Цель

Снизить технический долг, упростить тестирование и подготовить кодовую базу к добавлению новых фич (новые методы анализа, новые брокеры, ML-оптимизация весов).

---

## Текущие проблемы (по приоритету)

### P0 — Критично (блокирует разработку)

#### 1. `forecast_runner.py::process_ticker()` — God Object

**Проблема:** одна функция (~120 строк) отвечает за:
- загрузку данных,
- проверку staleness,
- расчёт индикаторов,
- определение режима рынка,
- генерацию прогнозов,
- консенсус,
- пост-обработку (EMA-веса, method_config),
- активацию ордера.

**Последствия:** невозможно протестировать стадию изолированно; изменение логики консенсуса требует чтения всего файла.

**Пример:**
```python
# forecast_runner.py:18-130 — process_ticker()
# 7 импортов внутри функции (ad-hoc), 4 try/except блока,
# прямой SQL для чтения method_config и providers
```

**Решение:** Pipeline-архитектура. Каждая стадия — отдельный callable с четким контрактом `input → output`.

```python
# Целевой API
pipeline = ForecastPipeline([
    FetchDataStage(),
    IndicatorStage(),
    RegimeStage(),
    ForecastStage(),
    ConsensusStage(),
    OrderActivationStage(),
])
result = pipeline.run(ticker, ctx)
```

---

#### 2. Дублирование `sys.path` манипуляций

**Проблема:** идентичный блок в 5 файлах:

- `scripts/core/forecast_runner.py`
- `scripts/server/robot.py`
- `scripts/server/api.py`
- `scripts/core/scheduler.py`
- `scripts/client/main.py`

**Пример:**
```python
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in [_PROJECT_ROOT, os.path.join(_PROJECT_ROOT, "scripts", "core")]:
    if p not in sys.path:
        sys.path.insert(0, p)
```

**Решение:**
1. Вариант A: `scripts/bootstrap.py` — единая функция `bootstrap_paths()`.
2. Вариант B (предпочтительный): убрать из кода, задать `PYTHONPATH` в `run_server.bat` / `run_client.bat` и в `scripts/server/main.py` через `sys.path` только в точке входа.

---

#### 3. Ad-hoc SQL вне `sqlite_manager.py`

**Проблема:** `forecast_runner.py` и `scheduler.py` выполняют прямые SQL-запросы, обходя инкапсуляцию хранилища.

**Примеры:**
```python
# forecast_runner.py:75-96 — чтение method_config и providers через pd.read_sql_query
# scheduler.py:61-76 — _upsert_task через sqlite3.connect
# scheduler.py:414-418 — expire_queued_orders через sqlite3.connect
```

**Решение:**
- Все CRUD-операции — только через методы `sqlite_manager.py`.
- Создать `TaskRepository`, `OrderRepository`, `ConsensusRepository` если `sqlite_manager.py` становится слишком большим (>1000 строк).

---

### P1 — Важно (замедляет разработку)

#### 4. Отсутствие Dependency Injection

**Проблема:** `db_manager` создаётся заново внутри функций, конфиг читается ad-hoc через `get_config_value()`.

**Пример:**
```python
# forecast_runner.py:200-209
db_manager = SQLiteManager(db_file)  # новый инстанс
# scheduler.py:262-263
db = SQLiteManager(_db_manager.db_file)  # дублирование
```

**Решение:** `AppContext` (или `Container`) — синглтон, инициализируемый в `main.py`/`lifespan` и передаваемый явно.

```python
@dataclass
class AppContext:
    db: SQLiteManager
    scheduler: Scheduler
    order_manager: OrderManager
    circuit_breaker: CircuitBreaker
```

---

#### 5. Перекрытие `robot.py` и `forecast_runner.py`

**Проблема:** `robot.py` — thin wrapper вокруг `forecast_runner.py` в background thread. Обе сущности запускают один и тот же код. `robot.py` добавляет status tracking и log capture, но это можно было бы сделать в `forecast_runner.py`.

**Решение:**
- **Вариант A:** объединить. `forecast_runner.py` предоставляет `run_async()` + `run_sync()` + status events.
- **Вариант B:** сделать `robot.py` чистым FastAPI-адаптером (только HTTP-интерфейс), а логику вынести в `forecast_runner.py`.

---

#### 6. Отсутствие type hints в core-модулях

**Проблема:** `consensus.py`, `actuals_evaluator.py`, `data_loader.py`, `indicators.py` — функции без аннотаций типов. Это усложняет рефакторинг и поиск ошибок.

**Решение:** Постепенное добавление type hints. Начать с публичных функций (тех, что вызываются из других модулей).

---

#### 7. Смешение sync/async в `scheduler.py`

**Проблема:** `scheduler.py` использует `asyncio` + `ThreadPoolExecutor` для запуска sync-кода. Это создаёт сложность при отладке (стек-трейсы через thread boundaries).

**Решение:**
- Перевести blocking-операции (IB API, yfinance) на `asyncio.to_thread()`.
- Или сделать scheduler полностью sync с `APScheduler`/`schedule` библиотекой (меньше кода, проще отладка).

---

### P2 — Желательно (улучшение качества)

#### 8. `config.py` — legacy constants

**Проблема:** `scripts/core/config.py` содержит константы, которые дублируют значения в SQLite `config`. Источник истины неочевиден.

**Решение:** Удалить `config.py`, перенести все значения в `_DEFAULT_CONFIG` в `sqlite_manager.py`. Константы `CONFIDENCE_THRESHOLD` и т.д. — читать из БД при старте.

---

#### 9. Отсутствие фиксации зависимостей версий

**Проблема:** `requirements_server.txt` и `requirements_client.txt` могут содержать незакреплённые версии.

**Решение:** `pip freeze > requirements_lock.txt` для воспроизводимости.

---

## Поэтапный план рефакторинга

### Этап 1: Инфраструктура (1-2 дня)

**Цель:** убрать дублирование и создать фундамент для дальнейшего рефакторинга.

- [ ] **1.1** Создать `scripts/bootstrap.py` — единая инициализация `sys.path`.
- [ ] **1.2** Обновить `run_server.bat`, `run_client.bat` — добавить `set PYTHONPATH=%~dp0`.
- [ ] **1.3** Убрать `sys.path` манипуляции из `forecast_runner.py`, `robot.py`, `scheduler.py`, `api.py`, `client/main.py`.
- [ ] **1.4** Создать `AppContext` (`scripts/core/context.py`) с DI-контейнером.
- [ ] **1.5** Добавить `pyproject.toml` / `setup.cfg` для типизации (mypy, black, isort).

### Этап 2: Хранилище (2-3 дня)

**Цель:** инкапсуляция всех SQL-запросов.

- [ ] **2.1** Вынести ad-hoc SQL из `forecast_runner.py` в `sqlite_manager.py`:
  - `get_method_config_timeframes()`
  - `get_provider_ema_accuracies()`
  - `get_latest_forecast_log_id()`
- [ ] **2.2** Вынести ad-hoc SQL из `scheduler.py` в `sqlite_manager.py`:
  - `upsert_scheduled_task()`
  - `increment_task_counters()`
  - `expire_queued_orders()`
  - `get_pending_consensus_orders()`
- [ ] **2.3** (Опционально) Создать `repositories/` пакет если `sqlite_manager.py` > 1000 строк.

### Этап 3: Pipeline (3-4 дня)

**Цель:** декомпозиция `process_ticker()`.

- [ ] **3.1** Создать `scripts/core/pipeline.py` с базовым классом `PipelineStage`.
- [ ] **3.2** Выделить стадии:
  - `FetchDataStage`
  - `IndicatorStage`
  - `RegimeStage`
  - `ForecastStage`
  - `ConsensusStage`
  - `OrderActivationStage`
- [ ] **3.3** Переписать `process_ticker()` как `pipeline.run(ticker, ctx)`.
- [ ] **3.4** Обновить тесты: `test_core_logic.py` — тестировать каждую стадию изолированно.

### Этап 4: Типизация и качество (2 дня)

**Цель:** повысить читаемость и найти скрытые баги.

- [ ] **4.1** Добавить type hints в `consensus.py`, `actuals_evaluator.py`, `forecast_engine.py`.
- [ ] **4.2** Запустить `mypy scripts/core/` — исправить ошибки.
- [ ] **4.3** Запустить `pytest` — убедиться, что ничего не сломалось.
- [ ] **4.4** Удалить `scripts/core/config.py`, перенести константы в БД.

### Этап 5: Унификация runner (1 день)

**Цель:** устранить дублирование между `robot.py` и `forecast_runner.py`.

- [ ] **5.1** Перенести status tracking и log capture из `robot.py` в `forecast_runner.py`.
- [ ] **5.2** Сделать `robot.py` тонким адаптером (только thread spawn + HTTP response).
- [ ] **5.3** Обновить `api.py` — использовать новый `RobotRunner`.

### Этап 6: Scheduler (2-3 дня)

**Цель:** упростить async-слой.

- [ ] **6.1** Заменить ручной `ThreadPoolExecutor` + `asyncio` на `asyncio.to_thread()` для blocking-операций.
- [ ] **6.2** Или (альтернатива) — перейти на `APScheduler` для sync-кода.
- [ ] **6.3** Убрать `_run_forecast_sync`, `_run_evaluate_sync` — вызывать `forecast_runner.run_trading_bot()` напрямую.

---

## Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Регресс в логике консенсуса | Средняя | Высокое | Сначала написать интеграционные тесты на `process_ticker()` до рефакторинга. Зафиксировать поведение. |
| Поломка scheduler при async-изменениях | Средняя | Среднее | Тестировать на paper-режиме без ордеров. Использовать `pytest-asyncio`. |
| IB Gateway disconnect при рефакторинге `order_manager.py` | Низкая | Высокое | Не трогать `ib_gateway_client.py` до завершения остальных этапов. |
| Увеличение время разработки | Высокая | Среднее | Рефакторинг делать **только** между торговыми сессиями (вечер/выходные). Не смешивать с фичами. |

---

## Критерии успеха

1. **`mypy scripts/core/`** — 0 ошибок (цель на Этап 4).
2. **`pytest test_core_logic.py`** — 100% pass (контрольный тест перед каждым этапом).
3. **`process_ticker()`** — не более 20 строк (вызов pipeline).
4. **Отсутствие `sys.path.insert` в `scripts/core/`** — только в `bootstrap.py` и `main.py`.
5. **Отсутствие прямого SQL вне `sqlite_manager.py`** — все запросы через методы класса.
6. **Test coverage > 60%** для `scripts/core/` (цель после Этапа 3).

---

## Список файлов, подлежащих рефакторингу

### Высокий приоритет (Этапы 1-3)
- `scripts/core/forecast_runner.py` — God Object → Pipeline
- `scripts/core/scheduler.py` — ad-hoc SQL, async complexity
- `scripts/server/robot.py` — объединить с forecast_runner
- `scripts/core/sqlite_manager.py` — расширить методы (вместо ad-hoc SQL)

### Средний приоритет (Этапы 4-5)
- `scripts/core/consensus.py` — type hints
- `scripts/core/actuals_evaluator.py` — type hints
- `scripts/core/forecast_engine.py` — type hints
- `scripts/core/config.py` — удалить
- `scripts/server/api.py` — убрать sys.path

### Низкий приоритет (Этап 6)
- `scripts/core/data_loader.py` — type hints, async wrapping
- `scripts/core/indicators.py` — type hints
- `scripts/core/order_manager.py` — разбить на модули (validation, submission, tracking)

---

## Что НЕ трогать (стабильные модули)

| Модуль | Причина |
|--------|---------|
| `ib_gateway_client.py` | Внешний API (IB), сложно тестировать без реального счёта. Рефакторинг только при смене брокера. |
| `circuit_breaker.py` | Простой, покрыт тестами, не имеет зависимостей. |
| `model_performance_tracker.py` | Небольшой, изолированный. |
| `market_regime.py` | Стабильная логика, покрыта тестами. |
| `single_instance.py` | Простой, работает. |

---

## Связь с документацией

- Обновлять `ARCHITECTURE.md` после каждого этапа.
- Создавать feature-документы в `docs/features/` только для новых фич, не для рефакторинга.
- `docs/REFACTOR_PLAN.md` — единая точка входа для рефакторинг-сессий.
