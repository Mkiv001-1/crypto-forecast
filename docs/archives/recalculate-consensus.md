# Recalculate Consensus — Ретроспективный пересчет консенсуса

## Описание
Скрипт и UI для создания/пересоздания консенсусных записей на основе исторических прогнозов из таблицы `logs`. 

Проблема: консенсус создается только при запуске `forecast_runner`, и он имеет дату текущего запуска. Прогнозы, созданные ранее (например, 29 апреля), не попадают в консенсус за их даты.

Решение: отдельный скрипт, который группирует прогнозы по тикерам и датам создания, рассчитывает консенсус для каждой группы и сохраняет с корректной датой.

## Требования

### Функциональные
1. Группировка прогнозов по: `created_at` (дата), `ticker`
2. Для каждой группы: вызов `calculate_consensus()`
3. Сохранение консенсуса с `date = created_at`
4. Корректный `eval_target_date = date + horizon_hours`
5. Дедупликация: если консенсус уже существует для (date, ticker) — обновить или пропустить
6. Кнопка "Recalculate Consensus" в GUI (ConsensusTab)
7. Прогресс и логирование операции

### Нефункциональные
- Не блокировать GUI при выполнении (async/threading)
- Показывать статистику: сколько создано/обновлено
- Безопасно: не удалять существующие оцененные консенсусы

## Архитектурные решения

### Алгоритм
1. Выбрать все прогнозы из `logs` за период
2. Сгруппировать по `substr(created_at, 1, 10)` + `ticker`
3. Для каждой группы:
   - Собрать методы/модели и их прогнозы
   - Вызвать `calculate_consensus()`
   - Установить `date = created_date`
   - Сохранить через `save_consensus()`
4. Логировать прогресс

### Дедупликация
- Если для (date, ticker) уже есть консенсус:
  - Если `eval_status = 'EVALUATED'` — пропустить (не трогать)
  - Иначе — обновить (перезаписать)

### UI
- Кнопка "🔄 Recalculate" в ConsensusTab рядом с "Evaluate Now"
- Confirmation dialog с предупреждением
- Progress bar или лог в реальном времени
- MessageBox с итогами

## План реализации

1. **core/consensus_recalc.py** — новый модуль с функцией `recalculate_consensus()`
2. **server/api.py** — endpoint `/consensus/recalculate` (синхронный, с логированием)
3. **client/api_client.py** — метод `recalculate_consensus()`
4. **client/gui_main.py** — кнопка "Recalculate" в ConsensusTab, обработчик `_on_recalculate_consensus()`
5. **Тесты** — проверить создание консенсуса для старых прогнозов

## Статус
Done

## Изменения

### 2026-05-06
- **core/consensus_recalc.py** — новый модуль:
  - `recalculate_consensus()` — основная функция группировки и пересчета
  - `_load_forecast_logs()` — загрузка прогнозов за период
  - `_process_group()` — расчет консенсуса для одной группы (date, ticker)
  - Дедупликация: пропускает EVALUATED, обновляет остальные
  - Использует дату создания прогноза как дату консенсуса
  
- **server/api.py**:
  - Новый endpoint `POST /consensus/recalculate`
  - Параметры: `date_from`, `date_to` (опциональные)
  - Возвращает статистику: created, updated, skipped, errors, total_groups

- **client/api_client.py**:
  - Новый метод `recalculate_consensus(date_from, date_to)`

- **client/gui_main.py**:
  - Новая кнопка "🔄 Recalculate" в ConsensusTab
  - Confirmation dialog с предупреждением
  - Метод `_on_recalculate_consensus()` с прогрессом и автообновлением
  - Показывает статистику в MessageBox

### Fix: original_run_id для сохранения связи с forecast_run_links

**Проблема:** При ретроспективном пересчёте создаётся новый `run_id` (тип `recalc`), но старые записи в `forecast_run_links` ссылаются на оригинальный `run_id`. Аналитические SQL-запросы, использующие `JOIN consensus c ON l.run_id = c.run_id`, возвращают пустой результат для пересчитанных консенсусов.

**Решение:** 
1. Добавлено поле `consensus.original_run_id` — ссылка на оригинальный запуск прогнозирования
2. При пересчёте `_process_group()` определяет `original_run_id` из полей `logs.run_id` исходных прогнозов
3. Если все прогнозы из одного run — сохраняем его `run_id` в `original_run_id`
4. Если прогнозы из разных run — `original_run_id` остаётся NULL (логируется warning)

**Использование в аналитике:**
```sql
-- JOIN с учётом recalc: используем original_run_id если есть, иначе run_id
SELECT method, AVG(c.direction_correct) as win_rate
FROM forecast_run_links l
JOIN consensus c ON l.run_id = COALESCE(c.original_run_id, c.run_id) AND l.ticker = c.ticker
WHERE c.eval_status = 'EVALUATED'
GROUP BY method;
```

**Файлы изменены:**
- `scripts/core/sqlite_manager.py` — добавлена миграция `consensus.original_run_id`
- `scripts/core/consensus.py` — `save_consensus()` принимает и сохраняет `original_run_id`
- `scripts/core/consensus_recalc.py` — `_process_group()` определяет и передаёт `original_run_id`
