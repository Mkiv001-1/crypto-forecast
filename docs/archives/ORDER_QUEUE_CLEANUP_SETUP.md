# Настройка очереди и очистки ордеров

## Проблема
- Ордера со статусом "FILLED_ENTRY" остаются в системе indefinitely
- Ордера DAY не попадают в очередь из-за `ALLOW_EXTENDED_HOURS = true`

## Решение
Добавлены две новые настройки:

### 1. QUEUE_DAY_ORDERS (по умолчанию: true)
- **true**: DAY ордера ставятся в очередь до открытия рынка
- **false**: DAY ордера отправляются немедленно

### 2. FILLED_ORDERS_RETENTION_DAYS (по умолчанию: 30)
- Количество дней хранения исполненных ордеров
- Старше этого периода - архивируются в статус "ARCHIVED"

## Как применить настройки

### Вариант 1: Консервативная торговля
```sql
UPDATE config SET value = 'true' WHERE key = 'QUEUE_DAY_ORDERS';
UPDATE config SET value = '90' WHERE key = 'FILLED_ORDERS_RETENTION_DAYS';
UPDATE config SET value = 'false' WHERE key = 'ALLOW_EXTENDED_HOURS';
```

### Вариант 2: Активная торговля (текущее поведение)
```sql
UPDATE config SET value = 'false' WHERE key = 'QUEUE_DAY_ORDERS';
UPDATE config SET value = '7' WHERE key = 'FILLED_ORDERS_RETENTION_DAYS';
UPDATE config SET value = 'true' WHERE key = 'ALLOW_EXTENDED_HOURS';
```

### Вариант 3: Только рыночные часы
```sql
UPDATE config SET value = 'true' WHERE key = 'QUEUE_DAY_ORDERS';
UPDATE config SET value = '30' WHERE key = 'FILLED_ORDERS_RETENTION_DAYS';
UPDATE config SET value = 'false' WHERE key = 'ALLOW_EXTENDED_HOURS';
```

## Автоматическая очистка

### Планировщик
- `expire_queued_orders` - каждые 5 минут
- `expire_filled_orders` - ежедневно (раз в 24 часа)

### Статусы ордеров
- `QUEUED` → `EXPIRED` (через 24 часа)
- `FILLED_ENTRY` → `ARCHIVED` (через 30 дней)

## Проверка работы

```sql
-- Проверить настройки
SELECT key, value FROM config WHERE key IN ('QUEUE_DAY_ORDERS', 'FILLED_ORDERS_RETENTION_DAYS');

-- Проверить ордера в очереди
SELECT COUNT(*) FROM orders WHERE status = 'QUEUED';

-- Проверить архивные ордера
SELECT COUNT(*) FROM orders WHERE status = 'ARCHIVED';
```

## Перезапуск системы
После изменения настроек перезапустите сервер для применения:
```bash
# Остановить сервер
# Запустить сервер заново
```

## Результат
- DAY ордера будут корректно ставиться в очередь (если включено)
- Исполненные ордера будут автоматически очищаться через месяц
- Система не будет засоряться старыми записями
