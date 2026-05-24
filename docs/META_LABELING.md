# Meta-Labeling

ML-фильтр поверх LLM consensus: оценивает `P(trade_profitable | features)` и отсекает слабые LONG/SHORT **до** постановки ордера.

Полный технический план: см. Cursor plan `meta-plan_criticism_review` или фазы ниже.

## Pipeline (runtime)

```
FetchData → Indicator → Regime → TradingExposureGuard → Forecast → Consensus → MetaLabel → OrderActivation
```

- **Consensus** — направление и уровни (LLM + веса).
- **MetaLabel** — торговое решение (ML); при REJECT ордер не ставится.
- **OrderActivation** — только при `AUTO_ORDER_SUBMISSION=true`, confidence ≥ threshold, `meta_decision=PASS`.

## Конфигурация

| Key | Default | Описание |
|-----|---------|----------|
| `META_LABEL_ENABLED` | `false` | Включить inference |
| `META_LABEL_ENFORCE` | `false` | `false` = shadow (логировать, не блокировать) |
| `META_LABEL_THRESHOLD` | `0.55` | Порог P для PASS |
| `META_MODEL_PATH` | `` | Путь к joblib-модели |
| `META_MODEL_VERSION` | `` | Версия для audit |
| `META_LABEL_MIN_EDGE_PCT` | `0.05` | Мин. net PnL % для label=1 |
| `META_DATASET_MODE` | `false` | Не skip forecast на exposure (сбор датасета) |
| `BYBIT_TAKER_FEE_PCT` | `0.055` | Taker % (одна сторона) |
| `BYBIT_MAKER_FEE_PCT` | `0.02` | Maker % |
| `META_LABEL_ASSUME_TAKER` | `true` | Консервативный расчёт издержек |

## Labels (обучение)

- **gross:** `consensus.pnl_pct` — движение цены entry→exit (как раньше).
- **net:** `consensus.net_pnl_pct` = gross − round-trip fees − estimated funding.
- **label_meta:** `1` если `net_pnl_pct >= META_LABEL_MIN_EDGE_PCT`, иначе `0`.

Расчёт: [`scripts/core/meta_label/net_pnl.py`](../scripts/core/meta_label/net_pnl.py).

## Dataset mode (без ордеров)

```
ORDER_MODE=disabled
AUTO_ORDER_SUBMISSION=false
META_DATASET_MODE=true
```

Консенсусы пишутся и оцениваются scheduler'ом; ордера не нужны для labels.

## Offline train

```bash
python scripts/tools/meta_label/export_dataset.py --db database/trading_robot.db
python scripts/tools/meta_label/train.py --input data/meta_label/train.csv
```

Артефакт: `models/meta_label/` (joblib bundle: model + scaler + feature_names).

## Файлы

| Модуль | Назначение |
|--------|------------|
| `scripts/core/meta_label/net_pnl.py` | Net PnL и label |
| `scripts/core/meta_label/features.py` | Feature vector |
| `scripts/core/meta_label/stage.py` | `MetaLabelStage` |
| `scripts/core/meta_label/perp_snapshot.py` | Funding / mark-index snapshot |
| `scripts/tools/meta_label/export_dataset.py` | Export для train |
| `scripts/tools/meta_label/train.py` | Обучение модели |
