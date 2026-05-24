# Consensus Evaluation Fields

## Описание
Добавление в таблицу `consensus` полей оценки, аналогичных тем, что используются при эвалюации индивидуальных прогнозов в таблице `logs`. Позволяет оценить точность консенсусного сигнала постфактум: когда данные за целевую дату появились, сравниваем предсказанные target/stop с фактическими ценами.

## Требования

### Функциональные
- Новые поля в `consensus`: `horizon_hours`, `eval_target_date`, `eval_status`, `actual_date`, `actual_open/close/high/low`, `entry_price_actual`, `target_hit`, `stop_hit`, `direction_correct`, `pnl_pct`, `r_multiple`
- Автоматический расчёт `horizon_hours` = медиана `timeframe_hours` методов, вошедших в консенсус
- `eval_target_date` = дата консенсуса + `horizon_hours`
- `eval_status`: `PENDING` → `EVALUATED` | `NO_DATA`
- Эвалюация запускается автоматически через scheduler и вручную через API / GUI
- GUI: новые колонки `Eval`, `Actual Close`, `Target Hit`, `Stop Hit`, `PnL%`; кнопка "Evaluate Now"; агрегированная статистика

### Нефункциональные
- Идемпотентная миграция схемы (ALTER TABLE IF NOT EXISTS)
- Не ломает существующие записи (все поля nullable или с DEFAULT)
- `entry_price_actual` — базовая цена для расчёта PnL. Приоритет: 1) `entry_limit_price` из консенсуса (соответствует реальной торговле), 2) close бара на дату консенсуса (fallback для исторических данных)

## Архитектурные решения

### Затрагиваемые модули
- `scripts/core/sqlite_manager.py` — ALTER TABLE + миграция
- `scripts/core/consensus.py` — вычислять `horizon_hours`, `eval_target_date`, `eval_status`
- `scripts/core/consensus_evaluator.py` — **новый файл**
- `scripts/core/scheduler.py` — новая задача `_scheduled_consensus_evaluate_task`
- `scripts/shared/models.py` — расширить `ConsensusRecord`
- `scripts/server/api.py` — `POST /consensus/evaluate`
- `scripts/client/gui_main.py` — расширить `ConsensusTab`

### Новые файлы
- `scripts/core/consensus_evaluator.py`
- `docs/features/consensus-evaluation.md` (этот файл)

## Логика evaluate_consensus_records
1. Выбрать записи `WHERE eval_status = 'PENDING' AND eval_target_date <= today`
2. Для каждой: загрузить `price_data` за `eval_target_date` (`fetch_actual_data`)
3. `entry_price_actual` = `entry_limit_price` из консенсуса (если есть), иначе close бара на дату консенсуса
4. Рассчитать `target_hit`, `stop_hit`, `direction_correct`, `pnl_pct`, `r_multiple`
5. Обновить запись, установить `eval_status = 'EVALUATED'`

## Тесты
- `test_evaluate_consensus_records_target_hit`
- `test_evaluate_consensus_records_stop_hit`
- `test_evaluate_consensus_records_no_data`
- `test_evaluate_consensus_records_pending_not_ready`

## Статус
Done
