# Улучшения качества прогнозов и консенсуса

Пять алгоритмических улучшений для повышения качества прогнозов и более точной оценки результатов.

## 1. Сохранение весов (Forecast Run Tracking) ✅

**Статус:** Реализовано

**Описание:** Каждый запуск прогнозирования получает уникальный `run_id`. Все прогнозы и консенсус линкуются к этому ID с полным snapshot весов.

**Таблицы:**
- `forecast_runs` — мета-информация о запуске
- `forecast_run_links` — individual прогнозы с весами

**Веса сохраняются:**
- `raw_confidence` — исходный confidence от модели (0-100)
- `calibrated_confidence` — скорректированный confidence
- `calibration_factor` — коэффициент калибровки
- `win_rate` — исторический win rate метода
- `ema_accuracy` — EMA accuracy модели
- `final_weight` = calibrated_confidence × win_rate × ema_accuracy

**API:**
- `GET /forecast-runs` — список запусков с агрегацией
- `GET /forecast-runs/{id}` — детали + все прогнозы с весами

---

## 2. Expected Value Filter ✅

**Статус:** Реализовано

**Описание:** Фильтр отсеивает сигналы с низким ожидаемым результатом.

**Формула:**
```
expected_r = (confidence / 100) × (reward / risk)
```

**Порог:** `expected_r < 0.5` → сигнал превращается в NEUTRAL

**Пример:**
- 70% confidence × R/R = 3.0 → expected_r = 2.1 → **LONG** ✅
- 60% confidence × R/R = 0.3 → expected_r = 0.18 → **NEUTRAL** ❌

**Расположение:** `consensus.py:calculate_consensus()`

---

## 3. Confidence Calibration ✅

**Статус:** Реализовано

**Описание:** Корректировка confidence на основе исторической точности модели.

**Формула:**
```python
calibration_factor = ema_accuracy / 0.5  # baseline 50%
# Ограничение: 0.5 ... 1.5

calibrated_confidence = raw_confidence × calibration_factor
```

**Примеры:**
- Переуверенная модель (ema_accuracy=0.4): 80% → 64%
- Недоуверенная модель (ema_accuracy=0.7): 60% → 84%

**Расположение:** `consensus.py:calculate_consensus()`

---

## 4. "Первым сработал" анализ ✅

**Статус:** Реализовано

**Описание:** Определение что сработало раньше — target или stop — когда оба уровня достигнуты в один день.

**Логика:**
```python
# Расстояние от open до target и stop
dist_to_target = abs(target - open)
dist_to_stop = abs(stop - open)

# Уровень ближе к open сработал первым
if dist_to_target < dist_to_stop:
    first_hit = "target"  # Прибыль
elif dist_to_stop < dist_to_target:
    first_hit = "stop"    # Убыток
else:
    first_hit = "stop"    # Неоднозначно → консервативно stop
```

**Применение:**
- Intraday анализ без минутных данных
- Консервативная оценка: при неоднозначности → stop

**Поле в БД:** `consensus.first_hit` (TEXT: 'target' | 'stop' | NULL)

**Расположение:** `consensus_evaluator.py:_evaluate_one()`

---

## 5. ATR Нормализация R-multiple ✅

**Статус:** Реализовано

**Описание:** Нормализация R-multiple на ATR для сравнения сигналов across тикеров с разной волатильностью.

**Проблема:**
- NVDA: R=2.0 при ATR=5% — обычный сигнал
- SPY: R=2.0 при ATR=1% — отличный сигнал

**Формула нормализации:**
```python
normalized_r = r_multiple / (atr_pct × 100)

# Пример:
# R=2.0, ATR=5% → normalized = 0.4
# R=2.0, ATR=1% → normalized = 2.0
```

**Интерпретация:**
- `normalized_r > 1.0` — сигнал лучше среднего для данной волатильности
- `normalized_r < 1.0` — сигнал хуже среднего

**Функции:**
- `calculate_atr(df, period=14)` — расчёт ATR
- `normalize_r_multiple(r_multiple, atr, entry_price)` — нормализация

**Поля в БД:**
- `forecast_run_links.atr_14` — ATR на момент прогноза
- `forecast_run_links.r_multiple` — R-multiple прогноза

**Расположение:**
- `consensus.py:calculate_atr()`
- `consensus.py:normalize_r_multiple()`

---

## SQL запросы для аналитики

### Win rate по методам с нормализацией (с учётом recalc)
```sql
SELECT 
    l.method,
    AVG(c.direction_correct) as win_rate,
    AVG(l.normalized_r) as avg_normalized_r,
    COUNT(*) as count
FROM forecast_run_links l
JOIN consensus c ON l.run_id = COALESCE(c.original_run_id, c.run_id) AND l.ticker = c.ticker
WHERE c.eval_status = 'EVALUATED'
GROUP BY l.method
ORDER BY avg_normalized_r DESC;
```

### "Первым сработал" статистика
```sql
SELECT 
    first_hit,
    COUNT(*),
    AVG(pnl_pct) as avg_pnl,
    AVG(CASE WHEN direction_correct=1 THEN 1 ELSE 0 END) as win_rate
FROM consensus
WHERE eval_status = 'EVALUATED' 
  AND first_hit IS NOT NULL
GROUP BY first_hit;
```

### Калибровка: ожидаемый vs фактический win rate (с учётом recalc)
```sql
SELECT 
    CASE 
        WHEN calibrated_confidence >= 80 THEN '80-100'
        WHEN calibrated_confidence >= 60 THEN '60-79'
        ELSE '<60'
    END as conf_bucket,
    AVG(c.direction_correct) as actual_win_rate,
    AVG(l.calibrated_confidence) as expected_win_rate,
    COUNT(*) as count
FROM forecast_run_links l
JOIN consensus c ON l.run_id = COALESCE(c.original_run_id, c.run_id) AND l.ticker = c.ticker
WHERE c.eval_status = 'EVALUATED'
GROUP BY conf_bucket;
```

---

## Тесты

Все 5 улучшений покрыты тестами в `test_core_logic.py`:
- `test_consensus_expected_value_filter`
- `test_consensus_confidence_calibration`
- `test_calculate_atr_basic`
- `test_normalize_r_multiple`
- `test_consensus_with_atr_in_link_data`
- `test_first_hit_analysis_target_first`

**Итого:** 56 тестов, все проходят ✅

---

## Статус

**Готово:** 5/5 улучшений реализованы ✅
