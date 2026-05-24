# Execute Field for Methods & Providers

## Описание
Добавление поля `execute` (yes/no) в таблицы Methods и Providers для контроля выставления ордеров по прогнозам. Это позволит гибко управлять тем, прогнозы от каких методов и провайдеров должны приводить к реальным торговым операциям.

## Требования

### Функциональные
- Добавить поле `execute` в таблицу `methods` со значениями 'yes'/'no' (default 'yes')
- Добавить поле `execute` в таблицу `providers` со значениями 'yes'/'no' (default 'yes')
- При принятии решения о выставлении ордера проверять оба поля
- Ордер выставляется только если method.execute = 'yes' AND provider.execute = 'yes'
- Возможность динамически изменять значения через API

### Нефункциональные
- Обратная совместимость с существующими данными
- Минимальные изменения в производительности
- Логирование решений о пропуске ордеров из-за execute='no'

## Архитектурные решения

### Затрагиваемые модули
- `sqlite_manager.py` - миграция схемы БД
- `forecast_engine.py` - логика проверки execute перед созданием ордеров
- `consensus.py` - проверка execute при расчете консенсуса
- `api.py` - новые endpoints для управления полем execute

### Новые файлы
- Нет

### Изменения схемы БД
```sql
ALTER TABLE methods ADD COLUMN execute TEXT DEFAULT 'yes' CHECK (execute IN ('yes', 'no'));
ALTER TABLE providers ADD COLUMN execute TEXT DEFAULT 'yes' CHECK (execute IN ('yes', 'no'));
```

### Новые API endpoints
- `PUT /api/methods/{method_id}/execute` - обновить execute для метода
- `PUT /api/providers/{provider_id}/execute` - обновить execute для провайдера
- `GET /api/methods/{method_id}` - получить метод с полем execute
- `GET /api/providers/{provider_id}` - получить провайдера с полем execute

## План реализации

1. Создать миграцию БД для добавления поля execute
2. Обновить модели данных для включения поля execute
3. Модифицировать логику в forecast_engine.py для проверки execute
4. Обновить consensus.py для учета execute при расчете
5. Добавить API endpoints для управления execute
6. Обновить тесты для проверки новой функциональности
7. Добавить логирование решений о пропуске ордеров

## Тесты

### Unit тесты
- Тест миграции БД (поле добавляется, default='yes')
- Тест проверки execute в forecast_engine (yes+yes=execute, yes+no=skip, no+yes=skip, no+no=skip)
- Тест API endpoints (PUT/GET для execute)
- Тест консенсуса с учетом execute

### Интеграционные тесты
- Полный цикл: прогноз с execute='yes' → ордер
- Полный цикл: прогноз с execute='no' → ордер не создается
- Смешанный сценарий: несколько прогнозов с разными execute

## Статус
Done

## Реализация

### Выполненные изменения
1. **БД миграция** - добавлены поля execute в таблицы providers и method_config с default='yes' и CHECK constraint
2. **Логика order_manager.py** - добавлена функция _check_execute_flags() и guard-проверка в submit_signal()
3. **API endpoints** - добавлены 4 новых endpoints:
   - PUT /method-config/{method}/execute
   - PUT /providers/{provider}/execute  
   - GET /method-config/{method}
   - GET /providers/{provider}
4. **Тесты** - добавлено 6 unit тестов в test_core_logic.py, все проходят

### Проверка работы
- Все 31 тест проходят (включая 6 новых для execute)
- Ордер создается только если method.execute='yes' AND provider.execute='yes'
- При execute='no' возвращается статус SKIPPED_EXECUTE_DISABLED с понятным сообщением
- API endpoints позволяют динамически управлять execute флагами

### Пример использования API
```bash
# Отключить исполнение для метода momentum_trend
curl -X PUT "http://localhost:8000/method-config/momentum_trend/execute" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '"no"'

# Включить исполнение для провайдера claude-sonnet  
curl -X PUT "http://localhost:8000/providers/claude-sonnet/execute" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '"yes"'
```
