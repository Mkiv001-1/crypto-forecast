# Документация проекта

Индекс документов по фичам, архитектуре и планированию.

---

## Архитектура и планирование

| Документ | Описание |
|----------|----------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Общая архитектура, ключевые решения, таблицы SQLite, бизнес-логика, технический долг |
| [`REFACTOR_PLAN.md`](REFACTOR_PLAN.md) | План рефакторинга: проблемы, этапы, риски, критерии успеха |
| [`../README.md`](../README.md) | Основная документация: установка, запуск, API, workflow |
| [`CHANGELOG.md`](CHANGELOG.md) | Журнал изменений по сессиям |
| [`README_TEST_SUITE.md`](README_TEST_SUITE.md) | Документация тестового набора |

---

## Feature-документы

### Консенсус и оценка

| Документ | Статус | Описание |
|----------|--------|----------|
| [`consensus-evaluation.md`](consensus-evaluation.md) | ✅ Done | Поля оценки консенсуса (target_hit, stop_hit, pnl_pct, r_multiple) |
| [`consensus-evaluate-logging.md`](consensus-evaluate-logging.md) | ✅ Done | Логирование процесса оценки консенсуса |
| [`recalculate-consensus.md`](recalculate-consensus.md) | ✅ Done | Ретроспективный пересчёт консенсуса с новыми весами |
| [`forced-recalculation-button.md`](forced-recalculation-button.md) | ✅ Done | GUI-кнопка принудительного пересчёта консенсуса |
| [`gui-consensus-tab.md`](gui-consensus-tab.md) | ✅ Done | Вкладка консенсуса в GUI |

### Прогнозирование

| Документ | Статус | Описание |
|----------|--------|----------|
| [`forecast-quality-improvements.md`](forecast-quality-improvements.md) | ✅ Done | Улучшения качества прогнозов (R/R-фильтр, bracket-поля, TIF) |
| [`forecast-run-tracking.md`](forecast-run-tracking.md) | ✅ Done | Аудит запусков прогнозирования (forecast_runs, forecast_run_links) |
| [`forecast-bracket-order-fields.md`](forecast-bracket-order-fields.md) | ✅ Done | Bracket-поля в прогнозах (entry_limit_price, stop_loss, TIF) |
| [`price-data-staleness-check.md`](price-data-staleness-check.md) | ✅ Done | Проверка устаревания price_data перед генерацией прогнозов |

### Ордера и исполнение

| Документ | Статус | Описание |
|----------|--------|----------|
| [`order-submission-integration.md`](order-submission-integration.md) | ✅ Done | Интеграция выставления ордеров (авто + ручной) |
| [`order-race-condition-fix.md`](order-race-condition-fix.md) | ✅ Done | Исправление race condition при одновременной отправке ордеров |
| [`gui-trading-tab.md`](gui-trading-tab.md) | ✅ Done | Вкладка торговли в GUI |

### Конфигурация методов и провайдеров

| Документ | Статус | Описание |
|----------|--------|----------|
| [`method-new-button.md`](method-new-button.md) | ✅ Done | Кнопка добавления нового метода анализа |
| [`execute-field-methods-providers.md`](execute-field-methods-providers.md) | ✅ Done | Поле `execute` для методов и провайдеров |
| [`gui-execute-checkboxes.md`](gui-execute-checkboxes.md) | ✅ Done | Чекбоксы execute в GUI |

---

## Как добавлять новые документы

1. Создать файл в `docs/features/` с именем `feature-name.md`
2. Использовать шаблон:
   ```markdown
   # Название фичи

   ## Статус
   Draft / In Progress / Done

   ## Описание
   ...

   ## Архитектурные решения
   ### Затрагиваемые модули
   - `scripts/core/xxx.py` — что меняется
   ### Новые файлы
   - `scripts/core/xxx.py`

   ## Тесты
   - `test_xxx()`

   ## Статус
   Done
   ```
3. Добавить ссылку в этот индекс (`docs/README.md`)

---

## Соглашения по документации

- **Живые документы:** `ARCHITECTURE.md` и `REFACTOR_PLAN.md` обновляются при каждом значимом изменении.
- **Feature-документы:** создаются перед реализацией фичи, замораживаются после статуса `Done`.
- **Код первичен:** если документация противоречит коду — приоритет у кода; документацию исправить.
