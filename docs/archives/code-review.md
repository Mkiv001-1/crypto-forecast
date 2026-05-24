# Code Review — forecast / Trading Robot

**Дата:** 2025-05-11  
**Охват:** `scripts/core/`, `scripts/server/`, `scripts/client/`, `scripts/shared/`  
**Статус:** Draft  
**Версия:** 2 (углублённая проверка логики работы)

---

## 1. Архитектурный обзор

```
[FastAPI + Scheduler]
        │
   [forecast_runner]
        ├── [data_loader]         → fetch price data (yfinance / alpha_vantage / finnhub)
        ├── [indicators]          → calculate technical indicators
        ├── [market_regime]       → detect_regime → select methods
        ├── [multi_model_forecaster]
        │       └── [forecast_engine] → build_prompt → call_ai_model → parse_json_response
        ├── [consensus]           → calculate_consensus → save_consensus
        └── [order_manager]       → activate_consensus_order → submit_signal → IB
                ↕
        [sqlite_manager]          (единый источник истины)
                ↕
        [consensus_evaluator]     → оценивает прошлые записи по price_data
```

---

## 2. Проблемы в логике работы

### 🔴 Критические (ломают поведение или данные)

---

#### 2.1 `_cfg_int` определена дважды в `order_manager.py`
**Файл:** `scripts/core/order_manager.py`, строки 63–68 и 78–82

```python
# Строка 63 — ПЕРВОЕ определение (никогда не выполнится)
def _cfg_int(db_manager, key: str, default: int) -> int:
    try:
        v = db_manager.get_config_value(key)
        return int(v) if v is not None else default
    except Exception:
        return default

# Строка 78 — ВТОРОЕ (перекрывает первое)
def _cfg_int(db_manager, key: str, default: int) -> int:
    try:
        return int(_cfg(db_manager, key, str(default)))
    except ValueError:
        return default
```

Первое определение недостижимо. Вторая версия вызывает `_cfg()` и конвертирует через `str(default)` — при отсутствии ключа вернёт `default` как строку, что сломает `max_open = _cfg_int(...)` если `_cfg` вернёт `None` и `str(None) = "None"` → `ValueError` → `return default`. В целом работает, но первое определение вводит в заблуждение при чтении.  
**Fix:** удалить строки 63–68.

---

#### 2.2 Утечка ticker lock при исключении в `submit_signal`
**Файл:** `scripts/core/order_manager.py`, строки 315–418

```python
_ticker_lock = _get_ticker_lock(ticker)
if not _ticker_lock.acquire(blocking=False):
    return ...
try:
    ...
    parent_db_id = _save_order(db_manager, order_row)
    if initial_status == "QUEUED":
        return {"status": "QUEUED", ...}   # ← lock НЕ освобождается здесь
finally:
    if _ticker_lock is not None:
        _ticker_lock.release()
        _ticker_lock = None                # ← зануление переменной внутри finally
```

**Проблема:** ранний `return {"status": "QUEUED"}` внутри `try`-блока не вызывает `_ticker_lock = None` до `finally` — это нормально. Но если `_ticker_lock.release()` сам бросит исключение (что не должно происходить со стандартным Lock, но возможно при ошибках аллокации), переменная останется в неконсистентном состоянии.

**Более серьёзная проблема:** код зануляет `_ticker_lock = None` в `finally`, но затем вне блока `try/finally` на строке 422 снова обращается к `ib_result` — там lock уже освобождён. Это корректно по задумке, но `_ticker_lock` — локальная переменная и после `finally` уже `None`. Ссылка на глобальный `_ticker_locks[ticker]` при следующем вызове восстановится из словаря — так что реальной утечки нет, если `release()` не бросит.

**Реальная логическая проблема:** `return {"status": "QUEUED"}` внутри `try` выполняется **внутри критической секции** (lock ещё удерживается), после чего `finally` освобождает lock. Это корректно. Но если `_save_order` бросит исключение, `finally` освободит lock — и исключение пробросится наверх без возврата результата. Caller в `run_trading_bot` не ожидает исключения от `process_ticker` — оно поймается там и тикер будет посчитан как ошибка. **Это приемлемо**, но вводит в заблуждение из-за сложности потока.

---

#### 2.3 `consensus.py`: `_DEFAULT_MIN_EXPECTED_R` определяется ВНУТРИ функции как локальная константа
**Файл:** `scripts/core/consensus.py`, строка 356

```python
def calculate_consensus(...):
    ...
    _DEFAULT_MIN_EXPECTED_R = 0.5   # ← локальная переменная, не константа модуля!
```

При этом `_DEFAULT_MAX_DEVIATION` и `_DEFAULT_DISAGREEMENT_THRESHOLD` — константы модуля (строки 20–21). `_DEFAULT_MIN_EXPECTED_R` переопределяется при каждом вызове внутри функции. Это не критично функционально, но семантически неправильно — не константа, а "переменная-константа" которую нельзя переопределить снаружи функции.  
**Fix:** вынести на уровень модуля, как остальные `_DEFAULT_*`.

---

#### 2.4 `consensus.py`: некорректное обнуление `included_in_consensus` при `high_disagreement`
**Файл:** `scripts/core/consensus.py`, строки 388–391

```python
# После блока expected_r (строка 388):
if high_disagreement and signal == "NEUTRAL" and expected_r is None:
    for link_data in forecast_link_data:
        link_data['included_in_consensus'] = 0
```

**Логическая ошибка:** условие `expected_r is None` выполнится только если у нас нет `med_entry` или `med_stop` (то есть нет уровней). Если disagreement сработал до блока expected_r (строки 314–325), то `signal` уже `"NEUTRAL"` и `expected_r` не вычисляется — условие `expected_r is None` истинно. **Но** если disagreement произошёл и `expected_r` уже был вычислен (что невозможно при `signal == "NEUTRAL"` на момент вычисления `expected_r` в строке 358), то блок не сработает.

Реальная проблема: в строках 330–332 (блок `confidence < CONFIDENCE_THRESHOLD`) уже обнуляются все `included_in_consensus = 0`. А в строках 368–372 (блок `expected_r`) тоже. Но для `high_disagreement` (строка 319–325) — отдельный блок с дополнительным условием `expected_r is None`, которое избыточно. Если `high_disagreement=True` и `signal="NEUTRAL"` уже установлены на строке 320, то в строке 358 условие `signal in ("LONG", "SHORT")` ложно → `expected_r` остаётся `None` → блок 388–391 сработает правильно.

**Итог:** функционально работает, но хрупко и трудночитаемо. Логика обнуления `included_in_consensus` разбросана по трём местам.

---

#### 2.5 `forecast_runner.py`: `run_trading_bot` создаёт `run_id` дважды
**Файл:** `scripts/core/forecast_runner.py`, строки 211–219

```python
if run_id is None:
    active_tickers = db_manager.get_settings()      # ← первый вызов get_settings
    run_id = db_manager.create_forecast_run('scheduler', len(active_tickers))

active_tickers = db_manager.get_settings()          # ← второй вызов get_settings
```

`get_settings()` вызывается дважды подряд. Между вызовами тикеры могут измениться (race condition в многопоточной среде, хотя маловероятно). Первый вызов используется для `tickers_planned` в `forecast_runs`, второй — для реального итерирования. Если тикеры изменились, `tickers_planned` будет неверным.  
**Fix:** сохранить результат первого вызова и переиспользовать.

---

#### 2.6 `scheduler.py`: двойное создание `run_id` — scheduler и `run_trading_bot` оба создают run
**Файл:** `scripts/core/scheduler.py`, строки 262–268 и `forecast_runner.py` строки 212–215

```python
# В scheduler._run_forecast_sync():
run_id = db.create_forecast_run('scheduler', len(active_tickers))
run_trading_bot(db_manager=db, run_id=run_id)  # ← передаём run_id

# В run_trading_bot():
if run_id is None:                              # ← None-check, поэтому не создаст второй
    run_id = db_manager.create_forecast_run(...)
```

Здесь логика корректна — `run_trading_bot` пропускает создание если `run_id` передан. Но если `_run_forecast_sync` бросит исключение **до** вызова `run_trading_bot`, `run_id` создан в БД но никогда не будет завершён (нет `complete_forecast_run`). Блок `except` в `_run_forecast_sync` вызывает `db.complete_forecast_run(run_id, status='failed', ...)` только если исключение бросила `run_trading_bot`, но не если исключение случилось раньше (например, при `db.get_settings()`).  
**Fix:** обернуть весь `_run_forecast_sync` в `try/finally` с гарантированным `complete_forecast_run`.

---

#### 2.7 `consensus_evaluator.py`: `_evaluate_one_intraday` — `exit_successful` не сохраняется
**Файл:** `scripts/core/consensus_evaluator.py`, строки 253–255 и 274–290

```python
# Intraday path:
exit_successful = None
if signal in ("LONG", "SHORT"):
    exit_successful = 1 if first_hit == "target" else (0 if first_hit == "stop" else None)

_save_eval(
    ...
    # exit_successful НЕ передаётся в kwargs!
)
```

В `_evaluate_one_intraday` (строки 253–295) вычисляется `exit_successful`, но в вызове `_save_eval` оно **не передаётся** (сравни с `_evaluate_one` строки 512–529, где `exit_successful=exit_successful` есть). Поле в БД останется `NULL` для всех intraday-оценок.  
**Fix:** добавить `exit_successful=exit_successful` в вызов `_save_eval` на строке 274.

---

#### 2.8 `multi_model_forecaster.py`: rate-limit `break` пропускает все методы модели, но не переходит к следующей немедленно
**Файл:** `scripts/core/multi_model_forecaster.py`, строки 185–187

```python
except RateLimitError as e:
    logging.warning(f"⏭️ Skipping model '{model_name}' — rate limited ...")
    break  # skip remaining methods for this model, try next model
```

`break` выходит из цикла `for method in methods`, переходя к следующей итерации `for model_cfg in active_models`. Это корректно. Но `retry_after` из `RateLimitError` не используется — не ждём указанное время перед следующим запросом. Если следующая модель — тот же провайдер (OpenRouter), rate limit применяется и к ней.  
**Fix:** при `RateLimitError` делать `time.sleep(e.retry_after)` перед переходом к следующей модели.

---

### 🟠 Значимые (деградация функционала / технический долг)

---

#### 2.9 `consensus.py`: вес (`weight`) рассчитывается до проверки `is_filtered`, но добавляется к `total_weight` только после
**Файл:** `scripts/core/consensus.py`, строки 205–281

```python
weight = confidence * win_rate * ema_weight   # строка 214 — всегда вычисляется

if is_filtered:
    continue                                  # строка 278 — переходит к следующему

total_weight += weight                        # строка 281 — добавляется только если не filtered
```

Это **корректно**, но `forecast_link_data` сохраняет `final_weight` для filtered-прогнозов (строка 269) — это `weight` до фильтрации. При нулевом `win_rate` у метода вес будет 0, прогноз с `side=LONG` не прибавит к `weighted_long`, и если все LONG-прогнозы нулевые — `total_weight` тоже 0, результат `signal="NEUTRAL"`. Это **корректная** деградация, но не очевидна.

---

#### 2.10 `consensus_recalc._process_group` дублирует логику `forecast_runner.process_ticker`
**Файл:** `scripts/core/consensus_recalc.py`

Построение `method_stats`, `model_stats`, вызов `calculate_consensus`, `save_consensus` скопированы с незначительными отличиями. При изменении логики в `forecast_runner` нужно синхронно обновлять `consensus_recalc`. Текущий код расходится: в `forecast_runner` `method_stats` строится через `get_forecast_statistics`, а в `consensus_recalc` — через прямые SQL-запросы к `forecast_logs`.  
**Fix:** выделить `build_method_and_model_stats(db_manager)` в отдельный хелпер.

---

#### 2.11 `order_manager.py`: `activate_consensus_order` использует `entry_limit_price or stop_loss or 0` как entry_price для position_sizer
**Файл:** `scripts/core/order_manager.py`, строка 952

```python
position = calculate_position(
    ticker=ticker,
    entry_price=row["entry_limit_price"] or row["stop_loss"] or 0,  # ← fallback на stop_loss
    stop_loss=row["stop_loss"],
    ...
)
```

Использование `stop_loss` как `entry_price` приведёт к тому, что `risk = |entry - stop|` будет равен 0 (они совпадают), и `position_sizer` вернёт `SKIPPED_ZERO_RISK`. Если `entry_limit_price = NULL` и `stop_loss` задан — ордер будет скипнут из-за некорректного entry_price.  
**Fix:** использовать текущую рыночную цену из последней записи `price_data` как fallback.

---

#### 2.12 `scheduler.py`: deprecated `asyncio.get_event_loop()` в async-функциях
**Файл:** `scripts/core/scheduler.py`, строки 288, 299, 319, 360, 403, 455

```python
loop = asyncio.get_event_loop()   # deprecated в Python 3.10+ в корутине
await loop.run_in_executor(...)
```

В Python 3.12 это вызывает `DeprecationWarning`, в Python 3.14 планируется к удалению.  
**Fix:** заменить на `asyncio.get_running_loop()`.

---

#### 2.13 `data_manager.py` — мёртвый код (Excel-слой)
**Файл:** `scripts/core/data_manager.py`

`DataManager` нигде не импортируется в рабочем коде. Присутствие вводит в заблуждение и создаёт риск случайного использования.  
**Fix:** пометить как deprecated или удалить.

---

#### 2.14 Жёстко закодированный маппинг model→provider в `_check_execute_flags`
**Файл:** `scripts/core/order_manager.py`, строки 222–233

```python
if "claude" in model_name.lower():
    providers.append("claude-sonnet")
elif "gpt" in model_name.lower():
    providers.append("gpt-4o")
```

Хрупкий эвристический маппинг. Новый провайдер (например, `llama` или `mistral`) будет молча пропущен без проверки execute-флага.  
**Fix:** хранить `provider_name` явно в записи консенсуса или читать маппинг из `providers` таблицы.

---

### 🟡 Незначительные / стиль

---

#### 2.15 `HealthResponse` в `models.py` содержит устаревшие поля
**Файл:** `scripts/shared/models.py`, строки 127–133

Поля `excel_file`, `excel_exists` — из старой Excel-архитектуры. API сейчас возвращает `db_file`, `db_exists`. Клиент десериализует неправильные значения.

---

#### 2.16 `forecast_runner.test_single_ticker` не возвращает статистику
**Файл:** `scripts/core/forecast_runner.py`, строки 278–279

```python
process_ticker(db_manager, ticker, run_id=run_id)
db_manager.complete_forecast_run(run_id, status='completed', tickers_processed=1)
# consensus_count не передаётся в complete_forecast_run!
```

`complete_forecast_run` вызывается с `tickers_processed=1` но без `consensus_count` — поле останется 0 в БД для тестовых запусков.

---

#### 2.17 `consensus.py`: TIF выбирается по первому значению, а не по большинству
**Файл:** `scripts/core/consensus.py`, строки 393–396

```python
entry_tif = entry_tif_values[0] if entry_tif_values else "DAY"
```

При 3 прогнозах с `entry_tif = ["DAY", "GTC", "GTC"]` будет выбрано `"DAY"`, хотя большинство — `"GTC"`.  
**Fix:** использовать `statistics.mode(entry_tif_values)` или задокументировать намеренность.

---

#### 2.18 `evaluate_past_forecasts` в `forecast_runner.py` использует устаревший `unified_logs_manager`
**Файл:** `scripts/core/forecast_runner.py`, строки 16–16, 138–183

```python
from unified_logs_manager import get_forecasts_to_evaluate, update_forecast_with_actuals
```

`evaluate_past_forecasts` оценивает `logs`-записи через `unified_logs_manager`, тогда как новая архитектура оценивает `consensus`-записи через `consensus_evaluator`. Два параллельных пути оценки могут приводить к противоречивым данным.  
**Fix:** унифицировать: использовать только `consensus_evaluator.evaluate_consensus_records`.

---

#### 2.19 `circuit_breaker.py` — не интегрирован в основной flow
**Файл:** `scripts/core/circuit_breaker.py`

Модуль определён и читается только в `_heartbeat_task` (scheduler). В `forecast_engine.call_ai_model` или `multi_model_forecaster` не используется — circuit breaker не защищает от каскадного сбоя при недоступности OpenRouter.

---

## 3. Положительные стороны

- **Правильная архитектура трёх слоёв** — transport / domain / persistence
- **Per-ticker locking** в `submit_signal` — корректная защита от дублирования ордеров
- **First-hit analysis** в `_evaluate_one` — корректная обработка кейса "оба уровня в одном баре"
- **Overlap guard** в scheduler (`_task_running[name]`) — предотвращает наложение запусков
- **Graceful recovery** после рестарта: scheduler проверяет `last_run_at` и запускает задачу сразу если она просрочена
- **Horizon-based routing** в `_evaluate_one`: `horizon_hours < 24` → intraday, `>= 24` → daily bars
- **EMA accuracy** в консенсусе: веса моделей динамически корректируются по исторической точности
- **Forecast run tracking**: полная трассировка цикла `run → logs → links → consensus`

---

## 4. Сводная таблица приоритетов

| # | Файл | Проблема | Приоритет |
|---|------|----------|-----------|
| 1 | `consensus_evaluator.py:274` | `exit_successful` не передаётся в `_save_eval` (intraday) | 🔴 |
| 2 | `order_manager.py:63` | Дублирующий `_cfg_int` | 🔴 |
| 3 | `forecast_runner.py:219` | `get_settings()` вызывается дважды | 🔴 |
| 4 | `scheduler.py:255` | `run_id` может остаться незакрытым при исключении до `run_trading_bot` | 🔴 |
| 5 | `order_manager.py:952` | `stop_loss` как `entry_price` → `SKIPPED_ZERO_RISK` | 🟠 |
| 6 | `consensus_recalc.py` | Дублирование логики из `forecast_runner` | 🟠 |
| 7 | `multi_model_forecaster.py:185` | `retry_after` из `RateLimitError` игнорируется | 🟠 |
| 8 | `consensus.py:356` | `_DEFAULT_MIN_EXPECTED_R` — локальная переменная вместо константы | 🟠 |
| 9 | `scheduler.py:288+` | Deprecated `get_event_loop()` | 🟠 |
| 10 | `data_manager.py` | Мёртвый Excel-слой | 🟠 |
| 11 | `models.py:127` | `HealthResponse` с устаревшими полями | 🟡 |
| 12 | `forecast_runner.py:278` | `test_single_ticker` — consensus_count не сохраняется | 🟡 |
| 13 | `consensus.py:393` | TIF по первому значению, не по большинству | 🟡 |
| 14 | `forecast_runner.py:16` | Двойной путь оценки (`unified_logs_manager` vs `consensus_evaluator`) | 🟡 |
| 15 | `circuit_breaker.py` | Не интегрирован в AI-вызовы | 🟡 |
