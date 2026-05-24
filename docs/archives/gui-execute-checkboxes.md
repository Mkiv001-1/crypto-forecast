# GUI: Execute Checkboxes for Prompts & Providers Tabs

## Описание

Добавление чекбоксов "Execute" (вкл/выкл исполнение ордеров) в GUI табы **Prompts** и **Providers**. Это позволит оператору динамически управлять тем, по каким методам и от каких провайдеров создавать торговые ордера, без необходимости редактировать конфигурацию через API напрямую.

Поле `execute` уже существует в БД (статус `Done` в `execute-field-methods-providers.md`), но не имеет GUI-интерфейса для управления.

## Требования

### Функциональные

1. **Prompts Tab** — для каждого метода отображать чекбокс "Execute Orders":
   - Чекбокс показывает текущее значение `method_config.execute`
   - При изменении — сохраняется через API сразу или при нажатии "Save"
   - Визуальная индикация если `execute='no'` (например, зачеркивание или иконка)

2. **Providers Tab** — для AI-провайдеров добавить колонку "Execute Orders":
   - Отдельно от колонки "Active" (может быть активным для прогнозов, но не для ордеров)
   - Чекбокс в каждой строке таблицы AI Models
   - Сохранение при нажатии "Save All"

3. **Интеграция**:
   - Новые endpoints в `api.py` для получения/обновления `execute` для методов
   - Новые методы в `api_client.py` для GUI
   - Синхронизация состояния при загрузке табов

### Нефункциональные
- Минимальные изменения UI (не нарушать текущий layout)
- Быстрое сохранение (без задержек)
- Логирование изменений execute-флагов

## Архитектурные решения

### Затрагиваемые модули
- `scripts/client/gui_main.py` — обновление `PromptsTab` и `ProvidersTab`
- `scripts/client/api_client.py` — новые методы API
- `scripts/server/api.py` — новые endpoints для `method_config`

### Новые API endpoints
```
GET  /method-config/{method}           # получить полный config метода
PUT  /method-config/{method}/execute   # обновить execute (yes/no)
```

### Изменения в GUI

**PromptsTab**:
```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ Methods                               │ Editor                              │
│ ┌─────────────────────────────────┐ │                                     │
│ │ 📈 Momentum Trend        [✅ Ex]│ │                                     │
│ │ 🕯 Price Action          [❌ Ex]│ │  (execute=no - метод виден         │
│ │ 💪 Relative Strength     [✅ Ex]│ │   но ордера не создаются)           │
│ │ ⚡ Volatility Breakout   [✅ Ex]│ │                                     │
│ │ ↩ Mean Reversion         [✅ Ex]│ │                                     │
│ │ 📦 Volume Breakout       [✅ Ex]│ │                                     │
│ └─────────────────────────────────┘ │                                     │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

**ProvidersTab** (AI Models таблица):
```
| Active | Execute | Name        | Model                | Rate/min | Max Tokens |
|--------|---------|-------------|----------------------|----------|------------|
|   ✅   |   ✅    | claude      | anthropic/claude-... |    60    |    2000    |
|   ✅   |   ❌    | gpt4        | openai/gpt-4o        |    60    |    4000    |
```

## План реализации

1. **Backend API** — добавить endpoints для `method_config`
   - `GET /method-config/{method}` — получить полный конфиг метода
   - `PUT /method-config/{method}/execute` — обновить execute флаг

2. **API Client** — добавить методы в `ForecastApiClient`
   - `get_method_config(method)`
   - `update_method_execute(method, execute: bool/str)`
   - Обновить `get_providers()` для получения execute поля

3. **PromptsTab** — добавить чекбокс Execute
   - Добавить колонку/чекбокс в списке методов
   - Загрузка execute-значений при `load()`
   - Сохранение при изменении (или batch save)

4. **ProvidersTab** — добавить колонку Execute
   - Добавить 2-ю колонку в таблицу AI Models
   - Загрузка и сохранение execute-значений

5. **Тестирование**
   - Проверить загрузку/сохранение execute для методов
   - Проверить загрузку/сохранение execute для провайдеров
   - Проверить влияние на создание ордеров (order_manager)

## Тесты

### Unit тесты (GUI)
- Загрузка PromptsTab корректно отображает execute состояния
- Изменение execute в PromptsTab вызывает API
- Загрузка ProvidersTab отображает execute колонку
- Сохранение ProvidersTab передает execute значения

### Интеграционные тесты
- Полный цикл: изменение execute → API → БД → проверка в order_manager
- Проверка что order_manager корректно читает execute флаги

## Статус

Done

## Реализация

### Выполненные изменения

1. **API Client** (`scripts/client/api_client.py`):
   - `get_method_configs()` — получить все конфиги методов
   - `get_method_config(method)` — получить конфиг конкретного метода
   - `update_method_execute(method, execute)` — обновить execute флаг метода
   - `update_provider_execute(provider, execute)` — обновить execute флаг провайдера

2. **PromptsTab** (`scripts/client/gui_main.py`):
   - Добавлен чекбокс "Execute Orders" над списком методов
   - Загрузка execute-значений через `get_method_configs()`
   - Автоматическое сохранение при изменении чекбокса
   - Визуальная индикация состояния execute для выбранного метода

3. **ProvidersTab** (`scripts/client/gui_main.py`):
   - Добавлена колонка "Execute" в таблицу AI Models (между Active и Name)
   - Чекбокс в каждой строке для управления execute флагом
   - Сохранение execute флага через `update_provider_execute()` при нажатии "Save All"
   - Загрузка execute-значений из поля `provider.execute`

### Пример использования GUI

**Prompts Tab:**
1. Выбрать метод из списка слева
2. Установить/снять чекбокс "Execute Orders" 
3. Изменение сохраняется автоматически

**Providers Tab:**
1. Найти AI модель в таблице
2. Установить/снять чекбокс в колонке "Execute"
3. Нажать "Save All" для сохранения изменений

## Зависимости

- `execute-field-methods-providers.md` — базовая реализация execute полей (Done)
