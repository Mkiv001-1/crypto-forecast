# Forecast Bracket Order Fields

Добавить поля в таблицу `logs` (forecast) для хранения параметров трех ордеров bracket-группы: вход (лимитный), тейк-профит, стоп-лосс.

## Требования

### Новые поля в таблице `logs`

| Поле | Тип | Описание | Значение по умолчанию |
|------|-----|----------|----------------------|
| `entry_order_type` | TEXT | Тип ордера на вход | 'LMT' |
| `entry_limit_price` | REAL | Цена лимитного входа | NULL |
| `entry_tif` | TEXT | Time-in-Force входа | 'DAY' |
| `target_price` | REAL | Цена тейк-профита (число) | NULL |
| `take_profit_tif` | TEXT | TIF тейк-профита | 'GTC' |
| `stop_loss_tif` | TEXT | TIF стоп-лосса | 'GTC' |

### Обновление промптов

Модифицировать `_PROMPT_FOOTER` в `forecast_engine.py` и шаблоны в `sqlite_manager.py`:

```json
{
    "confidence": число 0-100,
    "side": "LONG" | "SHORT" | "NEUTRAL",
    "entry_order_type": "LMT",
    "entry_limit_price": число (цена входа),
    "entry_tif": "DAY",
    "target_price": число (цена тейк-профита),
    "take_profit_tif": "GTC",
    "stop_loss": число (цена стоп-лосса),
    "stop_loss_tif": "GTC",
    "timeframe_hours": целое число,
    "rationale": "обоснование"
}
```

### Архитектурные решения

1. **Миграция БД** — добавить 6 новых колонок в таблицу `logs` через `ALTER TABLE`
2. **Промпты** — обновить `_PROMPT_FOOTER` и `_DEFAULT_PROMPT_TEMPLATES`
3. **Парсинг** — обновить `parse_json_response()` для извлечения новых полей
4. **Сохранение** — обновить `save_forecast_to_logs()` и `save_forecast()`
5. **Ордера** — обновить `order_manager.py` для использования новых полей

## План реализации

1. **DB Migration** — добавить колонки в `_CREATE_TABLES` и создать миграцию
2. **Промпты** — обновить `_PROMPT_FOOTER` в `forecast_engine.py`
3. **Шаблоны** — обновить `_DEFAULT_PROMPT_TEMPLATES` в `sqlite_manager.py`
4. **Парсинг** — обновить `parse_json_response()` для новых полей
5. **Сохранение** — обновить `save_forecast_to_logs()` в `unified_logs_manager.py`
6. **Ордера** — обновить `submit_signal()` в `order_manager.py`
7. **Тесты** — добавить тесты для новых полей

## Тесты

### Юнит-тесты (test_core_logic.py)

1. **test_parse_json_bracket_fields_full**
   - Парсинг JSON со всеми новыми полями (entry_order_type, entry_limit_price, entry_tif, target_price, take_profit_tif, stop_loss_tif)

2. **test_parse_json_bracket_defaults**
   - Проверка значений по умолчанию при отсутствии новых полей в JSON

3. **test_validate_signal_entry_price**
   - Проверка валидации entry_limit_price (должен быть между текущей ценой и стоп-лоссом для LONG)

4. **test_save_forecast_bracket_fields**
   - Сохранение прогноза с полными bracket-параметрами в БД

5. **test_order_manager_uses_entry_limit**
   - Проверка что order_manager использует entry_limit_price вместо рыночной цены

### Интеграционные тесты

1. **test_end_to_end_bracket_forecast**
   - Полный цикл: промпт → AI ответ с bracket-параметрами → парсинг → сохранение в БД → чтение консенсуса → создание ордеров

2. **test_db_migration_bracket_columns**
   - Проверка что новые колонки существуют и имеют правильные типы

## Статус

Done

## Выполненные изменения

### 1. DB Schema (sqlite_manager.py)
- Добавлены 6 колонок в таблицу `logs`:
  - `entry_order_type TEXT DEFAULT 'LMT'`
  - `entry_limit_price REAL`
  - `entry_tif TEXT DEFAULT 'DAY'`
  - `target_price REAL`
  - `take_profit_tif TEXT DEFAULT 'GTC'`
  - `stop_loss_tif TEXT DEFAULT 'GTC'`

### 2. Промпты (forecast_engine.py)
- Обновлен `_PROMPT_FOOTER` — теперь требует от AI bracket-параметры для всех трех ордеров
- Обновлен `parse_json_response()` — парсит entry_limit_price, target_price, устанавливает дефолты
- Обновлен `validate_signal_rr()` — проверяет entry_limit_price и target_price

### 3. Консенсус (consensus.py)
- Добавлен сбор entry_limit_price и медианное значение
- Добавлен сбор TIF полей (entry_tif, take_profit_tif, stop_loss_tif)
- Обновлен return для включения новых полей

### 4. Сохранение (unified_logs_manager.py)
- Обновлен `save_forecast_to_logs()` — гарантирует наличие bracket полей с дефолтами

### 5. Ордера (order_manager.py + ib_gateway_client.py)
- `order_manager.py`: использует entry_limit_price для LMT ордера, передает TIF
- `ib_gateway_client.py`: поддержка entry_price, entry_order_type, entry_tif, take_profit_tif, stop_loss_tif

### 6. Тесты (test_core_logic.py)
Добавлено 5 новых тестов:
- `test_parse_json_bracket_fields_full` — парсинг всех bracket полей
- `test_parse_json_bracket_defaults` — дефолтные значения
- `test_parse_json_target_price_fallback` — fallback из exit_target
- `test_validate_signal_entry_limit_price` — валидация entry_limit_price
- `test_validate_signal_entry_above_current_for_long` — проверка цены входа
- `test_validate_signal_entry_below_current_for_short` — проверка цены входа
- `test_consensus_bracket_fields` — консенсус с bracket полями
