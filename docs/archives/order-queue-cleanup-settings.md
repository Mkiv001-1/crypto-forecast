# Order Queue and Cleanup Settings

## New Configuration Options

### QUEUE_DAY_ORDERS
- **Default**: `true`
- **Description**: Controls whether DAY orders are queued until market open
- **Values**: 
  - `true` - Queue DAY orders until market open (14:30 UTC)
  - `false` - Submit DAY orders immediately regardless of market hours
- **Usage**: When enabled, DAY orders placed outside market hours will have status `QUEUED` and will be submitted automatically when market opens

### FILLED_ORDERS_RETENTION_DAYS
- **Default**: `30`
- **Description**: Number of days to keep FILLED_ENTRY orders before automatic cleanup
- **Values**: Integer (1-365)
- **Usage**: Orders older than this setting will be automatically archived to status `ARCHIVED`

## Implementation Details

### Order Queue Logic
```python
# New logic in order_manager.py
if queue_day_orders and entry_tif == "DAY" and not _is_market_hours() and not allow_extended:
    initial_status = "QUEUED"
else:
    initial_status = "SUBMITTED"
```

### Cleanup Logic
- **QUEUED orders**: Expired after `ORDER_QUEUE_MAX_AGE_HOURS` (24h default)
- **FILLED_ENTRY orders**: Archived after `FILLED_ORDERS_RETENTION_DAYS` (30 days default)
- **Scheduler tasks**: 
  - `expire_queued_orders` - runs every 5 minutes
  - `expire_filled_orders` - runs daily (86400 seconds)

## Migration Notes

1. Existing `ALLOW_EXTENDED_HOURS = true` behavior is preserved
2. New settings default to sensible values:
   - Queue DAY orders by default (prevents immediate submission outside market hours)
   - Keep filled orders for 30 days (reasonable audit period)

## Configuration Examples

### Conservative Trading (queue everything)
```
QUEUE_DAY_ORDERS = true
ALLOW_EXTENDED_HOURS = false
FILLED_ORDERS_RETENTION_DAYS = 90
```

### Active Trading (immediate submission)
```
QUEUE_DAY_ORDERS = false
ALLOW_EXTENDED_HOURS = true
FILLED_ORDERS_RETENTION_DAYS = 7
```

### Market Hours Only
```
QUEUE_DAY_ORDERS = true
ALLOW_EXTENDED_HOURS = false
FILLED_ORDERS_RETENTION_DAYS = 30
```
