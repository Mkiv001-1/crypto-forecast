# Consensus Columns Consistency

## Описание
Приведение вкладки Consensus к консистентной и компактной структуре:
- таблица используется как обзорный список;
- результатные метрики переносятся в нижнюю панель деталей;
- нижняя панель перестраивается в 3 вертикальные колонки полей;
- добавляется фильтр по `Trade Status`.

## Требования

### Функциональные
- Добавить фильтр `Trade Status` в верхнюю панель: `ALL`, `traded`, `pending`, `skipped`, `expired`, `new`.
- Убрать из таблицы колонки:
  - `Dir`
  - `Target Hit`
  - `Stop Hit`
  - `First Hit`
  - `PnL %`
  - `R`
- Оставить таблицу в компактном виде (14 колонок):
  1. Date
  2. Eval Date
  3. Ticker
  4. Signal
  5. Conf %
  6. Target
  7. Stop
  8. Entry
  9. Eval Close
  10. Eval Status
  11. Disagree
  12. Trade ID
  13. Trade Status
  14. Action
- Перестроить нижнюю панель в 3 колонки полей.
- В нижней панели показывать:
  - Evaluation: `Eval Status`, `Actual Date`, `Eval Close`
  - Trade fact: `Actual Entry`, `Actual Stop`, `Actual Close`, `Trade ID`, `Trade Status`
  - Outcome metrics: `Direction`, `Target Hit`, `Stop Hit`, `First Hit`, `PnL %`, `R Multiple`

### Mapping полей
- `Eval Close` = `consensus.actual_close`
- `Actual Entry` = `trade.entry_price`, fallback `consensus.entry_price_actual`
- `Actual Stop` = `trade.exit_price`, только если `trade.close_reason == STOP_LOSS`
- `Actual Close` = `trade.exit_price`

### Placeholder rules
- Нет `trade_id` -> все trade-actual поля = `—`
- Сделка не закрыта -> `Actual Close` = `—`
- Закрытие не по stop -> `Actual Stop` = `—`

## Архитектурные решения

### API change (обратносуместимый)
Расширить `GET /trades` дополнительным фильтром `trade_id` для точечной подгрузки одной сделки в детали Consensus.

### Затрагиваемые файлы
- `scripts/client/gui_main.py`
- `scripts/client/api_client.py`
- `scripts/server/api.py`

## Тесты

### Ручные
- Фильтрация по `Trade Status` в сочетании с `Signal` и `Eval`.
- Проверка, что таблица содержит 14 колонок.
- Проверка, что удаленные из таблицы метрики отображаются внизу.
- Проверка сценариев: `no trade`, `open trade`, `stop-closed`, `target-closed`.

### Автотесты
- Smoke-тесты API/GUI не меняют детерминизм.
- При наличии тестов endpoint `/trades` — добавить кейс фильтрации по `trade_id`.

## Статус
In Progress
