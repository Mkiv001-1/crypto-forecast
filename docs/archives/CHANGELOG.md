# Changelog

Хронология изменений по сессиям разработки.
Формат: `## [ДАТА] Название сессии` → подразделы Added / Fixed / Changed / Debt.

---

## [2026-05-07] Trading Tab UX Consolidation

### Added
- Новый верхнеуровневый таб **Trading** в GUI с подвкладками **Trades** и **Orders**
- Новый `TradesTab` (read-only MVP): фильтры `ticker/status`, таблица сделок, цветовая индикация PnL
- Двусторонняя кросс-навигация между `Orders` и `Trades` по `ticker` + `ib_parent_id`
- Явные UI-состояния для пустой выборки и ошибок загрузки в обеих подвкладках
- Linked-mode индикаторы (`parent #...`) и кнопки `Reset Filters` в `Trades` и `Orders`
- `api_client.get_trades()` как удобная обертка над `GET /trades`

### Changed
- `OrdersTab` выровнен со схемой БД: колонка `Action` теперь читает поле `action` (вместо `side`), добавлена колонка `Role` из `order_role`
- `_TabLoader` теперь загружает `Trading` единым шагом вместо отдельного `Orders`

### Decisions
- `System Log` намеренно оставлен отдельной верхнеуровневой вкладкой (не переносится в `Trading`)
- Для MVP не менялись серверные API-контракты `/orders` и `/trades`

---

## [2026-05-07] Consensus Engine Improvements & Scheduler Workers

### Added
- **`model_stats` parameter in `calculate_consensus()`** — отдельный словарь точности по имени AI-модели (keyed by `providers.name`), имеет приоритет над `method_stats` для `ema_accuracy`. Загружается из таблицы `providers` в `forecast_runner.py` и `consensus_recalc.py`
- **`exit_successful` field** — сохраняется в таблицу `consensus` при оценке: `1` = target hit first, `0` = stop hit first, `NULL` = ни один не достигнут. Соответствующая колонка добавлена в миграцию `sqlite_manager.py`
- **`has_consensus` return value** — `process_ticker()` в `forecast_runner.py` теперь возвращает кортеж `(log_ids, has_consensus)` вместо только `log_ids`; `run_trading_bot()` обновлён для распаковки
- **`SCHEDULER_MAX_WORKERS` config key** — конфигурируемый размер thread pool планировщика (дефолт 4), добавлен в оба seed-листа `sqlite_manager.py`
- **Configurable thread pool** — `start_scheduler()` читает `SCHEDULER_MAX_WORKERS` из config; `stop_scheduler()` корректно завершает pool через `shutdown(wait=False, cancel_futures=True)`
- **GUI field for `SCHEDULER_MAX_WORKERS`** — QSpinBox (диапазон 1–16) в подвкладке IB Settings таба Settings
- **`test_integration_api.py`** — новый файл интеграционных тестов API; тест `test_api_config_scheduler_max_workers_roundtrip` проверяет GET/PUT/GET цикл для `/config`
- **9 новых unit-тестов** в `test_core_logic.py`:
  - `test_consensus_model_stats_overrides_method_stats_ema` — model_stats имеет приоритет
  - `test_consensus_model_stats_fallback_to_method_stats` — fallback если модель не в model_stats
  - `test_consensus_total_weight_accumulates_all_non_filtered` — все ненефильтрованные прогнозы в total_weight
  - `test_consensus_total_weight_not_counting_filtered` — отфильтрованные прогнозы исключены
  - `test_consensus_evaluator_exit_successful_persisted` — exit_successful=1 сохраняется в DB
  - `test_consensus_evaluator_exit_successful_stop_first` — exit_successful=0 для stop-first сценария
  - `test_scheduler_max_workers_default_is_4` — дефолтный пул 4 worker
  - `test_scheduler_max_workers_from_config` — пул читается из config

### Fixed
- **Bug: `exit_successful` не сохранялся** — `_evaluate_one()` вычислял поле но не передавал в `_save_eval()`. Исправлено: добавлен `exit_successful=exit_successful` в вызов `_save_eval()`
- **Bug: `exit_successful` отсутствовал в миграции** — добавлена запись `("consensus", "exit_successful", "INTEGER")` в список `_ADD_MISSING_COLUMNS` в `sqlite_manager.py`
- **Bug: `total_weight` не накапливался** — в старой версии `total_weight += weight` выполнялся до `continue` для filtered прогнозов; теперь накапливается только после проверки на фильтр
- **Bug: смешение `ema_accuracy` в `method_stats`** — `consensus_recalc.py` больше не добавляет `ema_accuracy` в `method_stats`; используется отдельный `model_stats` dict

### Changed
- **Confidence calibration** — теперь вычисляется для аналитики, но НЕ влияет на вес (raw confidence + ema_weight); устраняет двойной счёт (calibrated weight ≡ raw × ema_weight)
- **`_process_group()` в `consensus_recalc.py`** — строит `model_stats` из таблицы `providers` (идентично `forecast_runner.py`), передаёт в `calculate_consensus()`
- **`test_core_logic.py`: `_make_consensus_db`** — добавлена колонка `exit_successful` в тестовую схему

---
## [2026-05-05] GUI Consensus Tab + Bugfix

### Added
- Новый таб **Consensus** в GUI клиент (@`gui_main.py:531-825`) для отображения агрегированных сигналов
- Таблица консенсуса с колонками: Date, Ticker, Signal, Conf%, Methods Long/Short/Neutral, Target, Stop, Entry, Disagree
- Панель деталей с rationale и полной информацией о методах
- Цветовая индикация сигналов (LONG/SHORT/NEUTRAL)
- Фильтр по тикеру и сигналу
- Поля `target_price`, `stop_loss`, `entry_limit_price`, `high_model_disagreement` в `ConsensusRecord` (@`shared/models.py`)
- Скрипт `scripts/tools/recalculate_consensus.py` для пересчета консенсуса по существующим прогнозам без вызова AI

### Fixed
- **Критический баг:** все консенсус-сигналы были NEUTRAL из-за несовпадения структуры данных
- В `multi_model_forecaster.py:133-145` исправлена структура `all_forecasts` — теперь поля `side`, `confidence`, `exit_target`, `stop_loss` и TIF на верхнем уровне вместо вложенного `forecast`
- Исправлен парсинг `stop_loss` из `exit_stop` — теперь берётся первое число (цена), а не последнее (процент)

### Changed
- Таб **Tickers** переименован иконкой 📈 (было 🎯)
- `SetupWizard` теперь загружает и фильтры Consensus таба

---

## [2026-05-05] Инициализация журнала изменений

### Added
- Создан `docs/CHANGELOG.md` — журнал изменений по сессиям
- Создан `docs/ARCHITECTURE.md` — документ ключевых архитектурных решений

### Notes
- Система уже содержит: клиент-серверную архитектуру (FastAPI + PyQt6), SQLite хранилище, мульти-модельное AI-прогнозирование через OpenRouter, модуль оценки прогнозов (`actuals_evaluator.py`), унифицированный менеджер логов (`unified_logs_manager.py`)
- Предыдущая история изменений до этой даты не зафиксирована в данном файле — см. `git log` для полной истории

---

## [2026-05-05] IB Gateway integration improvements

### Added
- New `IBConfig` table and model for storing IB Gateway connection settings
- API endpoints for IB Config management: GET/POST/PUT/DELETE `/ib-config`
- `type` field (paper/live) to `AccountRecord` and `PositionRecord` models
- `type` parameter to sync endpoints for distinguishing paper/live trading
- Client methods for IB Config management in `api_client.py`

### Fixed
- asyncio event loop conflicts with ib_insync library
- TypeError in `_run_with_loop` wrapper function
- `avgCost` → `averageCost` attribute name in portfolio positions

---

## [2026-05-06] Consensus Evaluation Logging & Improvements

### Added
- **Consensus Evaluation Fields** — 14 новых полей в таблице `consensus`: `horizon_hours`, `eval_target_date`, `eval_status`, `actual_date`, `actual_open/close/high/low`, `entry_price_actual`, `target_hit`, `stop_hit`, `direction_correct`, `pnl_pct`, `r_multiple`
- **Consensus Evaluator** — новый модуль `consensus_evaluator.py` для оценки консенсус-прогнозов постфактум
- **Scheduled Evaluation** — задача `consensus_evaluate` в scheduler для автоматической оценки
- **API Endpoint** — `POST /consensus/evaluate` для ручного запуска оценки
- **GUI Improvements** — новые колонки Eval, Actual Close, Target Hit, Stop Hit, PnL% в ConsensusTab; кнопка "Evaluate Now" с детальным результатом; статистика (total/evaluated/win_rate/avg_pnl/pending)
- **Logging & Progress** — детальное логирование процесса оценки с прогрессом `[idx/total]`; статистика (evaluated/no_data/errors)
- **Default horizon_hours** — консенсус теперь всегда имеет `eval_target_date` (дефолт 24 часа)
- **Recalculate Consensus** — кнопка "🔄 Recalculate" для ретроспективного пересчета консенсуса по историческим прогнозам
- **Forecast Quality Improvements** — 5 улучшений: Forecast Run Tracking, Expected Value Filter, Confidence Calibration, "First Hit" Analysis, ATR Normalization (56 тестов проходят)

### Changed
- GUI: колонка "Eval Date" перемещена на позицию 1 (сразу после Date)
- Endpoint `/consensus/evaluate` теперь синхронный с детальным результатом

### Fixed
- SQL в `evaluate_consensus_records` корректно учитывает `eval_target_date <= now`
- Дефолтный `horizon_hours=24` когда нет данных в method_config

---

<!-- TEMPLATE для новых сессий:

## [YYYY-MM-DD] Краткое название задачи

### Added
- ...

### Fixed
- ...

### Changed
- ...

### Debt / TODO
- ...

-->
