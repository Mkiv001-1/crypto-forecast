# Feature: кнопка "New" в Methods (PromptsTab)

## Описание
Добавить кнопку **New** в левую панель списка методов (PromptsTab), чтобы пользователь мог создать произвольный новый метод прогнозирования. При нажатии открывается диалог с полями: имя метода, timeframe_hours, trigger, execute. Метод добавляется в `method_config`, пустой промпт — в `prompt_templates`, и список обновляется.

## Требования

### Функциональные
- Кнопка "➕ New" под списком методов (перед stretch).
- Диалог: method name (строка, snake_case), timeframe_hours (int, default 24), trigger (combo: both/time/price_level), execute (checkbox, default yes).
- Валидация: имя не пустое, snake_case, не дублирует существующий.
- POST /method-config — серверный эндпоинт создания.
- Пустой промпт-шаблон создаётся автоматически на сервере.
- После создания — перезагрузка списка и выбор нового метода.

### Нефункциональные
- Константа `METHODS` в gui_main.py больше НЕ жёстко кодирует список — берём из API.
- `_METHOD_LABELS` остаётся для красивых имён (fallback = сам method name).

## Архитектурные решения
- **api.py**: `POST /method-config` — вставляет в `method_config` + `prompt_templates`.
- **api_client.py**: `create_method(...)`.
- **gui_main.py**: `NewMethodDialog`, кнопка в `PromptsTab._build_ui`, обновление `method_list` из API (не из METHODS).

## План реализации
1. Серверный эндпоинт `POST /method-config`.
2. Клиентский метод `api_client.create_method()`.
3. Диалог `NewMethodDialog` в gui_main.py.
4. Кнопка "New" и динамическая загрузка списка из API.

## Тесты
- Ручное тестирование через GUI (unit test опционально).

## Статус
In Progress
