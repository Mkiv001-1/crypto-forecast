# Unified Activity Window

## Status
In Progress

## Goal
Заменить разрозненные popup-уведомления для длительных операций на единое окно активности.

Новая UX-модель:
- При запуске длительной операции открывается Activity Window с детальным логом шагов.
- Кнопка Close скрывает окно, но не отменяет процесс.
- Процесс продолжает выполняться в фоне.
- По завершении UI получает обновление состояния и данных.

## Scope (Phase P0)
- scripts/client/activity_runtime.py
  - общий рантайм фоновых задач (QThread + signals)
  - статус задачи: running/success/error
  - поток событий лога в UI
- scripts/client/activity_dialog.py
  - стандартный диалог показа активности
  - детальный лог с timestamp
  - поведение Close -> continue in background
- scripts/client/gui_main.py
  - интеграция через MainWindow ActivityManager
  - замена popup-финализаций для P0 операций:
    - Consensus: Evaluate Now, Recalculate
    - Accounts: Sync with IB Gateway
    - Portfolio: Sync with IB Gateway
    - Trading: Sync Orders

## Scope (Phase P1)
- scripts/client/gui_main.py
  - Providers: Update Catalog
  - Consensus: Place Trade (after confirmation)
  - Orders: Cancel Selected (batch cancel with per-order log)

## Non-Goals (MVP)
- server-side streaming логов
- изменение серверных API-контрактов
- изменение схемы БД

## UX Contract
1. Run
   - операция запускается через общий helper.
   - окно активности открывается modeless, UI остается интерактивным.
2. Logging
   - лог содержит шаги и итог, формат: [HH:MM:SS] [LEVEL] message.
   - уровни: INFO, WARN, ERROR.
3. Close behavior
   - если статус running: окно закрывается, задача продолжает работу в фоне.
   - если статус success/error: окно закрывается обычным образом.
4. Completion
   - на success/error обновляются соответствующие виджеты вкладки.
   - кнопки запуска возвращаются в исходное состояние в on_finished.

## Risks
- Не все операции могут давать granular log без серверной поддержки.
  В MVP используется клиентский этапный лог (start/request/refresh/done/error).
- Повторный запуск той же операции во время running должен быть заблокирован.

## Verification
1. Запустить каждую P0 операцию и убедиться, что открывается Activity Window.
2. Нажать Close во время выполнения и проверить, что операция завершается в фоне.
3. Проверить обновление таблиц/labels после успеха.
4. Спровоцировать ошибку (например, неверный host/port) и убедиться, что ошибка видна в activity log.
