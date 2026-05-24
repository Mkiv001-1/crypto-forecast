# Forecast Run Tracking

Добавление полного аудита весов методов в каждом консенсусе через связующие таблицы `forecast_runs` и `forecast_run_links`.

## Описание

Каждый запуск прогнозирования (forecast run) получает уникальный ID. Все прогнозы и консенсус линкуются к этому ID с полным snapshot весов (confidence × win_rate × ema_accuracy).

Это позволяет постфактум анализировать:
- Какие методы/модели давали лучшие веса
- Корреляция confidence vs фактический результат
- Влияние anomaly filter на итоговый консенсус

## Схема БД

### forecast_runs — мета-информация о запуске
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Auto-increment ID |
| started_at | TEXT | Время начала |
| completed_at | TEXT | Время завершения |
| trigger_type | TEXT | 'scheduler' \| 'manual' \| 'recalc' |
| tickers_planned | INTEGER | Запланировано тикеров |
| tickers_processed | INTEGER | Обработано тикеров |
| consensus_count | INTEGER | Создано консенсусов |
| status | TEXT | 'running' \| 'completed' \| 'failed' |
| error_message | TEXT | Ошибка если failed |

### forecast_run_links — individual прогнозы с весами
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Auto-increment |
| run_id | INTEGER FK | Ссылка на forecast_runs |
| log_id | TEXT FK | Ссылка на logs |
| ticker | TEXT | Тикер |
| method | TEXT | Метод анализа |
| model | TEXT | Модель ИИ |
| signal | TEXT | 'LONG' \| 'SHORT' \| 'NEUTRAL' |
| raw_confidence | REAL | Confidence из прогноза (0-100) |
| win_rate | REAL | Исторический win_rate метода |
| ema_accuracy | REAL | EMA accuracy модели |
| final_weight | REAL | raw_confidence × win_rate × ema_accuracy |
| target_price | REAL | Цель |
| stop_loss | REAL | Стоп |
| included_in_consensus | INTEGER | 1 если вошёл в консенсус, 0 если отфильтрован |

### Миграция существующих таблиц
```sql
ALTER TABLE logs ADD COLUMN run_id INTEGER REFERENCES forecast_runs(id);
ALTER TABLE consensus ADD COLUMN run_id INTEGER REFERENCES forecast_runs(id);
ALTER TABLE consensus ADD COLUMN original_run_id INTEGER REFERENCES forecast_runs(id);
```

**Поле `original_run_id`** — используется при ретроспективном пересчёте консенсуса (`recalc`). Когда консенсус пересчитывается, создаётся новый `run_id` (тип `recalc`), но `original_run_id` сохраняет ссылку на исходный запуск прогнозирования. Это позволяет аналитическим SQL-запросам JOIN'ить с оригинальными `forecast_run_links`.

## Архитектура

### Поток данных

```
scheduler / manual / recalc
    ↓
create_forecast_run(trigger_type, tickers_planned) → run_id
    ↓
generate_multi_model_forecasts(run_id)
    ↓
foreach forecast:
    save_forecast_to_logs() → log_id
    link_forecast_to_run(run_id, log_id, ...weights...)
    ↓
calculate_consensus(run_id, log_ids)
    ↓
save_consensus(run_id)
    ↓
complete_forecast_run(run_id, status, stats)
```

### Методы SQLiteManager

- `create_forecast_run(trigger_type, tickers_planned) → int` — создаёт run
- `complete_forecast_run(run_id, status, tickers_processed, consensus_count, error_message)` — завершает
- `link_forecast_to_run(run_id, log_id, ticker, method, model, signal, raw_confidence, win_rate, ema_accuracy, final_weight, target_price, stop_loss, included_in_consensus)` — линкует прогноз
- `get_forecast_run(run_id) → dict` — run + агрегированные stats
- `get_forecast_run_links(run_id, ticker=None) → DataFrame` — все прогнозы run
- `get_forecast_runs(limit) → DataFrame` — список runs с агрегацией

### API Endpoints

- `GET /forecast-runs?limit=50` — список запусков с stats
- `GET /forecast-runs/{id}` — детали run + все links + consensus

## Аналитика

### Win rate по методам (с учётом recalc)
```sql
-- Для консенсусов после recalc: используем COALESCE для JOIN по original_run_id или run_id
SELECT method, AVG(c.direction_correct) as win_rate, COUNT(*)
FROM forecast_run_links l
JOIN consensus c ON l.run_id = COALESCE(c.original_run_id, c.run_id) AND l.ticker = c.ticker
WHERE c.eval_status = 'EVALUATED'
GROUP BY method;
```

### Корреляция confidence vs результат (с учётом recalc)
```sql
SELECT 
    CASE 
        WHEN raw_confidence >= 80 THEN '80-100'
        WHEN raw_confidence >= 60 THEN '60-79'
        ELSE '<60'
    END as conf_bucket,
    AVG(c.direction_correct) as actual_win_rate,
    COUNT(*)
FROM forecast_run_links l
JOIN consensus c ON l.run_id = COALESCE(c.original_run_id, c.run_id) AND l.ticker = c.ticker
WHERE c.eval_status = 'EVALUATED'
GROUP BY conf_bucket;
```

### Impact отфильтрованных прогнозов
```sql
SELECT included_in_consensus, COUNT(*), AVG(final_weight)
FROM forecast_run_links
WHERE run_id IN (SELECT id FROM forecast_runs WHERE trigger_type='scheduler')
GROUP BY included_in_consensus;
```

## Обработка ретроспективного пересчёта (recalc)

При ретроспективном пересчёте консенсуса через `recalculate_consensus()`:
1. Создаётся новый `run_id` с `trigger_type='recalc'`
2. Новые записи в `forecast_run_links` создаются с этим новым `run_id`
3. Поле `consensus.original_run_id` сохраняет `run_id` исходных прогнозов (если все из одного run)
4. Если прогнозы из разных run — `original_run_id` остаётся NULL

Для аналитики, которая должна работать с пересчитанными консенсусами, используйте JOIN через `COALESCE(c.original_run_id, c.run_id)`.

## Файлы изменены

1. `scripts/core/sqlite_manager.py` — таблицы + методы
2. `scripts/core/scheduler.py` — создание run_id
3. `scripts/core/forecast_runner.py` — проброс run_id
4. `scripts/core/multi_model_forecaster.py` — сохранение links
5. `scripts/core/consensus.py` — расчёт + сохранение весов
6. `scripts/core/consensus_recalc.py` — run для recalc
7. `scripts/server/api.py` — endpoints
8. `scripts/shared/models.py` — Pydantic модели
9. `test_core_logic.py` — тесты

## Статус

Done
