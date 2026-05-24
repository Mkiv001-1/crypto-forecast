# Price Data Staleness Check

## Описание
Добавление проверки сталости данных `price_data` перед запуском прогнозирования. Аналогично существующей проверке `CAPITAL_STALENESS_MINUTES` для капитала из IB, но для рыночных данных из yfinance/других провайдеров.

## Проблема
Прогноз запускается от `indicators`, которые рассчитываются из `price_data`. Если загрузка данных через yfinance тихо упала (rate limit, сетевая ошибка), следующий цикл прогнозирования запустится с устаревшими данными без предупреждения — новый прогноз будет сгенерирован поверх вчерашних цен.

## Требования

### Функциональные
- Новый конфигурационный параметр `PRICE_STALENESS_HOURS` (дефолт: 6 часов)
- Проверка `MAX(date)` в `price_data` перед запуском `indicators.py`
- Если дата устарела более чем на `PRICE_STALENESS_HOURS` — пропускать тикер с предупреждением в лог
- Проверка работает в `process_ticker()` перед вызовом `calculate_indicators()`

### Нефункциональные
- Проверка не должна ломать существующий поток (graceful degradation)
- Логирование с уровнем WARNING при пропуске тикера
- Конфигурация через таблицу `config` (как `CAPITAL_STALENESS_MINUTES`)

## Архитектурные решения

### Затрагиваемые модули
- `scripts/core/sqlite_manager.py` — добавить `PRICE_STALENESS_HOURS` в `_DEFAULT_CONFIG`
- `scripts/core/forecast_runner.py` — добавить вызов проверки в `process_ticker()`
- `scripts/core/data_manager.py` — новая функция `check_price_data_staleness()` (или в `sqlite_manager.py`)

### Новые файлы
- `docs/features/price-data-staleness-check.md` (этот файл)

## Логика проверки
1. Получить значение `PRICE_STALENESS_HOURS` из конфига
2. Для тикера выполнить запрос: `SELECT MAX(date) FROM price_data WHERE ticker = ?`
3. Сравнить разницу между `MAX(date)` и `datetime.now()`
4. Если разница > `PRICE_STALENESS_HOURS`:
   - Залогировать `WARNING: Price data for {ticker} is stale (last update: {date}), skipping forecast`
   - Вернуть `None`/`False` из `process_ticker` — пропустить тикер
5. Если данные свежие или отсутствуют (новый тикер) — продолжить нормально

## Тесты
- Тест с данными свежими (в пределах порога) — прогноз запускается
- Тест с устаревшими данными (за порогом) — прогноз пропускается, лог WARNING
- Тест при отсутствии данных — прогноз продолжается (fallback на загрузку)

## Статус
Done

## Реализация
- `scripts/core/sqlite_manager.py`:
  - Добавлен `PRICE_STALENESS_HOURS` в `_DEFAULT_CONFIG` (дефолт: 6 часов)
  - Добавлен метод `check_price_data_staleness(ticker)` — возвращает `(is_stale, last_date, hours_diff)`
- `scripts/core/forecast_runner.py`:
  - В `process_ticker()` добавлена проверка сталости сразу после `save_price_data()`
  - При устаревших данных — лог WARNING и `ValueError`, тикер пропускается
