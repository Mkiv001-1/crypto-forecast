# GUI Consensus Tab

## Описание
Добавление отдельного таба Consensus в GUI клиент для отображения агрегированных сигналов из таблицы `consensus`. Таб позволяет просматривать историю консенсус-решений по тикерам с детализацией методов, confidence, уровней target/stop.

## Требования

### Функциональные
- Отображение таблицы консенсус-записей (date, ticker, signal, confidence, methods, target, stop)
- Фильтр по тикеру
- Панель деталей с rationale
- Кнопки Refresh и Search
- Цветовая индикация сигналов (LONG/SHORT/NEUTRAL)

### Нефункциональные
- Аналогичный UX с существующим Forecasts табом
- Быстрая загрузка (limit 100-500 записей)
- Интеграция с SetupWizard

## Архитектурные решения

### Затрагиваемые модули
- `scripts/client/gui_main.py` - новый класс `ConsensusTab`
- `scripts/client/api_client.py` - уже имеется `get_consensus()`
- `scripts/shared/models.py` - уже имеются `ConsensusRecord`, `ConsensusResponse`

### Новые файлы
- `docs/features/gui-consensus-tab.md` (этот файл)

### Новый API
- Нет (используется существующий `GET /consensus`)

## План реализации

1. Создать класс `ConsensusTab` в `gui_main.py`
2. Добавить таб в `MainWindow` между Forecasts и Tickers
3. Обновить `SetupWizard` для загрузки консенсуса
4. Проверить отображение и фильтрацию

## Тесты

### Unit тесты
- Нет (GUI тесты вне scope)

### Ручные тесты
- Открытие таба, проверка загрузки данных
- Фильтр по тикеру
- Обновление через Refresh
- Отображение деталей

## Статус
Done

## Реализация

### Выполненные изменения
1. Добавлен класс `ConsensusTab` в `gui_main.py` с таблицей и фильтрами
2. Колонки таблицы: Date, Ticker, Signal, Conf%, Methods Long, Methods Short, **Methods Neutral**, Target, Stop, **Entry**, Disagree
3. Добавлена цветовая индикация сигналов (LONG/SHORT/NEUTRAL)
4. Фильтр по тикеру и сигналу
5. Панель деталей с rationale, **всеми тремя группами методов** (Long/Short/Neutral), target/stop/entry levels
6. Индикатор разногласия моделей (⚠️ Disagree)
7. Интеграция в `MainWindow` (таб между Forecasts и Tickers)
8. Интеграция в `SetupWizard` и обновление фильтра тикеров

### Исправление бага: все сигналы были NEUTRAL
**Причина:** в `multi_model_forecaster.py` структура `all_forecasts` была вложенной: `{'model': ..., 'method': ..., 'forecast': {...}}`, а `calculate_consensus` ожидал плоскую структуру с `side`, `confidence` на верхнем уровне. Из-за этого `f.get("side", "NEUTRAL")` всегда возвращал "NEUTRAL".

**Исправление:** изменена структура `all_forecasts` на плоскую с полями `side`, `confidence`, `exit_target`, `stop_loss`, `entry_limit_price`, `entry_tif`, `take_profit_tif`, `stop_loss_tif`.

### Исправление бага: пустой stop_loss
**Причина:** в `recalculate_consensus.py` парсинг `exit_stop` использовал `nums[-1]` — последнее число (процент), вместо `nums[0]` — первое число (цена стопа).

**Исправление:** изменен парсинг на `nums[0]` для получения цены стоп-лосса.

### Пересчет консенсуса для существующих прогнозов
Создан скрипт `scripts/tools/recalculate_consensus.py` для пересчета консенсуса без повторного вызова AI:

```bash
# Для всех тикеров (последние 24 часа)
python scripts/tools/recalculate_consensus.py

# Для конкретного тикера
python scripts/tools/recalculate_consensus.py NASDAQ:NVDA
```

### Файлы изменены
- `scripts/client/gui_main.py` — новый класс `ConsensusTab`, добавлен в `MainWindow` и `_TabLoader`
- `scripts/shared/models.py` — добавлены поля `target_price`, `stop_loss`, `entry_limit_price`, `high_model_disagreement` в `ConsensusRecord`
- `scripts/core/multi_model_forecaster.py` — исправлена структура `all_forecasts` для корректной работы консенсуса
- `scripts/tools/recalculate_consensus.py` — новый скрипт для пересчета консенсуса
- `docs/features/gui-consensus-tab.md` — документация фичи
