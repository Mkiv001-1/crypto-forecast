# News Intelligence & Fade-the-Reaction — итоговый план

**Версия:** 1.1  
**Дата:** 2026-05-24  
**Статус:** План к реализации (код не внедрён)

**Ревизия 1.1:** уточнения по ревью — price anchor (`fetched_at`), детерминированная кластеризация, калибровка порогов, TTL сетапов, владение полями `initial_move_direction` / `fade_direction`, LLM `narrative_ambiguity_score`.

> **Правило:** Код — источник истины. Этот документ описывает целевую архитектуру; при расхождении с репозиторием обновлять документ или код.

---

## Содержание

1. [Цель и философия](#1-цель-и-философия)
2. [Место в текущей системе](#2-место-в-текущей-системе)
3. [Архитектура](#3-архитектура)
4. [Источники данных](#4-источники-данных)
5. [Признаки и формулы](#5-признаки-и-формулы)
6. [Схема БД](#6-схема-бд)
7. [Модули и файлы](#7-модули-и-файлы)
8. [Scheduler](#8-scheduler)
9. [Pipeline и торговая логика](#9-pipeline-и-торговая-логика)
10. [Роль LLM](#10-роль-llm)
11. [Конфигурация](#11-конфигурация)
12. [MVP по фазам](#12-mvp-по-фазам)
13. [Исключения и риски](#13-исключения-и-риски)
14. [Дальнейшее развитие](#14-дальнейшее-развитие)
15. [Критерии готовности](#15-критерии-готовности)
16. [Ревизия 1.1 — ответ на критику плана](#16-ревизия-11--ответ-на-критику-плана)

---

## 1. Цель и философия

### 1.1 Что делаем

Отдельный модуль **news intelligence + fade reaction**, который:

- **не торгует сам** по заголовкам;
- **не заменяет** LLM-консенсус и meta-labeling;
- детектирует **крупные новостные события** и **перегиб цены**;
- даёт торговой системе компактные признаки для **фильтра и gate** сделок.

### 1.2 Базовый принцип: fade the reaction

Рынок торгует **ожидания**, а не текст новости. Сильный headline часто **добивает** уже начавшееся движение. Рабочая гипотеза:

| Факт | Действие |
|------|----------|
| Сильная новость + слабое движение цены | **Не сигнал** — игнорировать |
| Сильная новость + аномальное движение цены | Включить режим **наблюдения fade** |
| Импульс выдохся (reclaim, failure of continuation) | Разрешить **контртренд** по направлению fade |
| Consensus **догоняет** импульс новости | **Блокировать** вход |
| Consensus **совпадает** с fade_direction при READY | Разрешить / слегка увеличить size |

Новость — **маркер режима**, не entry engine. Направление fade = **против** первоначального импульса цены после события.

### 1.3 Чего не делаем

- Не строим `bullish_news_score → buy`.
- Не подмешиваем сырые headlines в промпты `forecast_engine`.
- Не дублируем `market_context.py` (BTC/ETH/funding для LLM остаётся отдельно).

---

## 2. Место в текущей системе

### 2.1 Существующий pipeline

```
FetchData → Indicator → Regime → TradingExposureGuard → Forecast → Consensus → MetaLabel → OrderActivation
```

См. [`scripts/core/pipeline/stages.py`](../scripts/core/pipeline/stages.py), [`docs/META_LABELING.md`](META_LABELING.md).

### 2.2 Целевой pipeline

```
FetchData → Indicator → Regime → TradingExposureGuard → Forecast → Consensus
    → FadeReactionStage → MetaLabelStage → OrderActivation
```

**Параллельно (фон):**

```
news_intelligence_update (3–4 ч)  → news_events, fade_context
fade_reaction_scan (15–30 мин)    → fade_setups (WATCHING → READY)
```

Forecast pipeline **не ходит** во внешние news API — только читает SQLite.

### 2.3 Переиспользуем

| Компонент | Использование |
|-----------|----------------|
| `scheduler.py` | Две новые interval-задачи |
| `sqlite_manager.py` | `_ensure_*_tables`, WAL |
| `bybit_data_loader.py` | Intraday 15m/1h для price shock |
| `price_data_intraday` | Хранение баров |
| `MetaLabelStage` | Паттерн shadow/enforce, persist в `consensus` |
| `PipelineContext` | Флаги `fade_order_blocked`, `fade_boost` |
| `secrets.ini` | API keys news-провайдеров |
| `circuit_breaker` / OpenRouter | Только опциональный LLM enrich |

---

## 3. Архитектура

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Фон: news_intelligence_update (каждые 3–4 ч)                           │
│  Marketaux + CryptoPanic → normalize → dedupe → classify → news_events  │
│                         → clusters → fade_context (per ticker)          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Фон: fade_reaction_scan (каждые 15–30 мин)                           │
│  fade_context + price_data_intraday (15m) → shock + exhaustion          │
│                         → fade_setups (WATCHING | READY | EXPIRED)      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Runtime: FadeReactionStage (на каждый тикер в forecast run)            │
│  consensus + active fade_setup → block chase / allow fade alignment     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Два контура обязательны:** новости обновляются редко; перегиб цены и exhaustion — часто.

---

## 4. Источники данных

### 4.1 Базовый стек (MVP)

| Источник | Роль | Примечание |
|----------|------|------------|
| **Marketaux** | Основная лента: macro, finance, crypto, entities | Free tier, один API на широкий фон |
| **CryptoPanic** | Crypto-агрегатор, coverage/sentiment слой | Дополнительный сигнал интенсивности |
| **Bybit** (уже в проекте) | Цены, intraday, funding | Реакция рынка — только отсюда |

### 4.2 Опционально

| Источник | Роль |
|----------|------|
| **Finnhub** | Кросс-проверка цен / macro context, не основной news feed |

### 4.3 Секреты

В `scripts/server/ini/secrets.ini` (не в git):

```ini
[news]
marketaux_api_key = ...
cryptopanic_api_key = ...
```

---

## 5. Признаки и формулы

### 5.1 Слои признаков

| Признак | Источник | Назначение |
|---------|----------|------------|
| `event_strength` | Новости (кластеры, источники) | Было ли крупное событие |
| `initial_move_direction` | Цена после price anchor | `UP` / `DOWN`; хранится в **`fade_context`**, дублируется в `fade_setups` только для audit |
| `reaction_strength` | Цена / ATR | Перегиб относительно нормы |
| `reversal_readiness` | Цена (exhaustion) | Готовность к откату |
| `fade_direction` | `compute_fade_direction()` | `SHORT` если импульс UP, иначе `LONG`; **только** в `fade_setups`, см. §6.4 |
| `fade_quality` | Композит | Качество сетапа для READY |

### 5.2 Event strength (без LLM)

```
event_strength = log(1 + weighted_cluster_count)
                 × source_tier_weight
                 × confirmation_bonus
```

- **weighted_cluster_count** — уникальные кластеры за 1–3 ч, не число перепечаток.
- **confirmation_bonus** — 1.0 / 1.2 / 1.4 при 1 / 2 / 3+ независимых источниках.
- **Cooldown:** повтор той же `cluster_id` за 2–3 ч почти не увеличивает score.

### 5.2.1 Кластеризация (фаза 1, детерминированный алгоритм)

Без LLM. Один и тот же набор статей при каждом запуске даёт **одинаковые** `cluster_id`.

**Шаг 0 — нормализация заголовка** (`dedupe.normalize_title`):

- lowercase, trim, collapse whitespace;
- удалить пунктуацию; опционально стоп-слова EN (`the`, `a`, `to`, …) — список **фиксированный** в коде.

**Шаг 1 — точный dedupe:** `external_id = sha256(url)`; дубликаты URL не создают новую запись.

**Шаг 2 — topic bucket** (из `classify.py`):

```
topic_bucket = "{category}:{sorted_matched_keywords[:5]}"
primary_symbol = первый символ из symbols_json или "MACRO"
```

**Шаг 3 — черновой cluster_id** (временное окно 3 ч, UTC):

```
hour_bucket = floorUTC(published_at, 3h)
draft_id = sha1(f"{topic_bucket}|{primary_symbol}|{hour_bucket}")[:16]
```

**Шаг 4 — слияние по схожести заголовков** (внутри того же `hour_bucket`):

- TF-IDF: `sklearn.feature_extraction.text.TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)` — параметры **не менять** без версии алгоритма;
- cosine similarity между нормализованными title;
- если similarity ≥ `NEWS_CLUSTER_TITLE_SIM` (default **0.75**) — объединить в cluster с **меньшим** `draft_id` (лексикографически);
- иначе оставить отдельные кластеры.

**Шаг 5 — подтверждение кластера:** `confirmation_bonus` = число **разных** полей `source` в кластере (не число статей).

Версия алгоритма сохраняется в config: `NEWS_CLUSTER_ALGO_VERSION=v1_char_tfidf` (для аудита при смене параметров).

### 5.3 Reaction strength (только цена) — price anchor

> **Уязвимое место (ревью):** `published_at` от API часто отстаёт от реальной публикации на 5–30 мин; к моменту fetch новость может уже быть в цене. **Не привязывать якорь к `published_at`.**

**Опорное время события для цены:**

```
t_event = fetched_at   # момент, когда система впервые увидела кластер
```

Дополнительно логировать (не для формулы, для калибровки):

```
publication_lag_min = (fetched_at - published_at) в минутах
```

**Price anchor (MVP, честный):**

```
t_anchor = open_time первого 15m-бара, у которого bar_open >= t_event (UTC)
anchor_close = open цены этого бара
# консервативно: не берём close бара «до новости», т.к. published_at ненадёжен
```

Если 15m-баров нет — fallback на первый **1h**-бар после `t_event`; если нет и его — не считать `reaction_strength` (setup остаётся `WATCHING`).

```
ret_window = (close_now - anchor_close) / anchor_close
reaction_strength = |ret_window| / max(atr_pct, ε)
```

- `atr_pct` — ATR(14) на 1h или 15m на момент расчёта / `anchor_close`.
- Порог MVP: `reaction_strength >= FADE_MIN_REACTION_Z` (default **2.0**).

**`initial_move_direction`** (одно место расчёта — `fade_reaction/scanner.py`):

```
если ret_window > +ε  → UP
если ret_window < -ε  → DOWN
иначе → NULL (нет импульса, fade не активируется)
```

`ε` — например 0.1% от `anchor_close`.

**`min_pause`:** отсчёт от `t_event` (`fetched_at` кластера), **не** от `published_at`.

### 5.4 Reversal readiness (MVP)

Минимальный набор:

| Компонент | Условие |
|-----------|---------|
| `min_pause` | ≥ `FADE_MIN_PAUSE_MINUTES` после `t_event` (`fetched_at`) |
| `continuation_failure` | N баров не обновили экстремум импульса |
| `reclaim` | Close вернулся внутрь диапазона до новости или за midpoint импульса |

Опционально позже: `wick_ratio`, `volume_climax`, post-news VWAP.

### 5.5 Fade quality и калибровка порогов

```
fade_quality = event_strength × reaction_strength × reversal_readiness
```

`status = READY` если `fade_quality >= FADE_MIN_QUALITY` и `reversal_readiness >= 0.6`.

Default `FADE_MIN_QUALITY = 1.5` — **стартовая гипотеза**, не откалиброванная на проде.

**Фаза 1 — обязательное логирование для калибровки:**

На **каждом** проходе `fade_reaction_scan`, для статусов `WATCHING` и `READY`, всегда писать в `fade_setups`:

- `event_strength`, `reaction_strength`, `reversal_readiness`, `fade_quality` (raw);
- `anchor_bar_open_at`, `anchor_close`, `publication_lag_min`;
- опционально JSON `calibration_json` с промежуточными флагами (`continuation_failure`, `reclaim`, …).

Так можно подобрать `FADE_MIN_QUALITY` / `FADE_MIN_REACTION_Z` по реальным событиям (ETF, hack, macro) **без** полноценного backtest на первой неделе.

**Жёсткое правило:** высокий `event_strength` при низком `reaction_strength` → **не fade** (шум без перегиба).

### 5.6 TTL сетапа (`expires_at`)

Правило заполнения — **одно место** (`fade_reaction/scanner.py` при создании setup):

```
expires_at = created_at + FADE_SETUP_TTL_HOURS   # default 12
```

На каждом scan:

```
если now_utc > expires_at → status = EXPIRED
```

Даже если сетап был `READY`, но reclaim не случился — после TTL **не блокировать** ордера. Иначе устаревший READY через сутки ложно режет входы.

Отдельно: structural shock → `COOLDOWN` с `FADE_COOLDOWN_HOURS` (может быть короче TTL сетапа).

### 5.7 Категории (keyword + API tags)

| Категория | Примеры ключей |
|-----------|----------------|
| `macro` | fed, rates, inflation, cpi, jobs, treasury |
| `crypto-structure` | etf, sec, regulation, exchange, custody |
| `crypto-stress` | hack, exploit, liquidation, depeg, insolvency |
| `risk-on` | approval, inflow, upgrade, partnership |
| `risk-off` | ban, lawsuit, outflow, delay, attack |

Теги `shock` (hack, depeg, SEC action, exchange outage) → **cooldown**, не контртренд в MVP.

---

## 6. Схема БД

Миграция: `_ensure_news_fade_tables(con)` в `sqlite_manager.py` (по аналогии с `_ensure_meta_label_tables`).

### 6.1 `news_events`

Очищенные события после dedupe.

```sql
CREATE TABLE IF NOT EXISTS news_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    source TEXT,
    title TEXT,
    url TEXT,
    symbols_json TEXT,
    category TEXT,
    event_tags_json TEXT,
    source_tier INTEGER DEFAULT 2,
    cluster_id TEXT,
    publication_lag_min REAL
);
CREATE INDEX IF NOT EXISTS idx_news_events_cluster ON news_events(cluster_id, published_at);
CREATE INDEX IF NOT EXISTS idx_news_events_published ON news_events(published_at);
```

### 6.2 `fade_context`

Агрегат «активное событие по тикеру» (читает pipeline и scanner).

```sql
CREATE TABLE IF NOT EXISTS fade_context (
    ticker TEXT NOT NULL,
    window_end TEXT NOT NULL,
    event_strength REAL DEFAULT 0,
    initial_move_direction TEXT,
    topic_summary TEXT,
    cluster_count INTEGER DEFAULT 0,
    shock_tags_json TEXT,
    cluster_fetched_at TEXT,
    PRIMARY KEY (ticker, window_end)
);
```

### 6.3 `fade_setups`

Живой сетап fade (обновляет `fade_reaction_scan`).

```sql
CREATE TABLE IF NOT EXISTS fade_setups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    status TEXT NOT NULL,
    fade_direction TEXT,
    initial_move_direction TEXT,
    event_strength REAL,
    reaction_strength REAL,
    reversal_readiness REAL,
    fade_quality REAL,
    news_cluster_id TEXT,
    anchor_bar_open_at TEXT,
    anchor_close REAL,
    publication_lag_min REAL,
    impulse_high REAL,
    impulse_low REAL,
    post_news_vwap REAL,
    calibration_json TEXT,
    created_at TEXT NOT NULL,
    ready_at TEXT,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fade_setups_ticker_status
    ON fade_setups(ticker, status);
```

### 6.4 Владение полями: `initial_move_direction` vs `fade_direction`

| Поле | Таблица | Кто пишет | Смысл |
|------|---------|-----------|--------|
| `initial_move_direction` | `fade_context` (канон) | `fade_reaction/scanner.py` | Фактический импульс цены после anchor: `UP` / `DOWN` |
| `initial_move_direction` | `fade_setups` (копия) | тот же scanner | Audit / JOIN без лишнего запроса; **не пересчитывать** в stage |
| `fade_direction` | `fade_setups` | **только** `compute_fade_direction(initial_move_direction)` | Торговое направление fade: `UP→SHORT`, `DOWN→LONG` |

```python
# scripts/core/fade_reaction/direction.py — единственное место инверсии
def compute_fade_direction(initial_move_direction: str) -> str | None:
    return {"UP": "SHORT", "DOWN": "LONG"}.get(initial_move_direction)
```

`FadeReactionStage` **не** инвертирует направление сам — читает `fade_direction` из `fade_setups` и при необходимости сверяет с `initial_move_direction` из той же строки.

### 6.5 Расширение `consensus` (audit)

```sql
-- migrate: ADD COLUMN IF NOT EXISTS
fade_decision TEXT,
fade_quality REAL,
fade_features_json TEXT
```

Значения `fade_decision`: `NONE` | `BLOCK_CHASE` | `ALLOW_FADE` | `COOLDOWN`.

---

## 7. Модули и файлы

```
scripts/core/news_intelligence/
    config.py              # NEWS_* из config table
    normalize.py           # единый формат события
    dedupe.py              # URL dedupe + cluster v1 (TF-IDF char, §5.2.1)
    cluster.py             # детерминированная кластеризация (опционально отдельно от dedupe)
    classify.py            # keywords + API tags
    aggregator.py          # event_strength, clusters → fade_context
    fetchers/
        marketaux.py
        cryptopanic.py
    job.py                 # entry point для scheduler
    llm_enrich.py          # опционально, фаза 3

scripts/core/fade_reaction/
    config.py              # FADE_* keys
    direction.py           # compute_fade_direction() — единственная инверсия
    price_shock.py         # anchor bar, reaction_strength
    exhaustion.py          # reversal_readiness
    scanner.py             # fade_setups, expires_at, calibration log
    stage.py               # FadeReactionStage
    job.py                 # entry point для scheduler

scripts/tools/news_fade/          # опционально
    backfill_news.py
    export_fade_dataset.py
```

**Не трогать:** `market_context.py` — только для LLM-промптов.

---

## 8. Scheduler

Добавить в [`scripts/core/scheduler.py`](../scripts/core/scheduler.py):

| Задача | Интервал по умолчанию | Sync-функция |
|--------|----------------------|--------------|
| `news_intelligence_update` | 240 мин | `_run_news_intelligence_sync` |
| `fade_reaction_scan` | 30 мин | `_run_fade_reaction_scan_sync` |

Регистрация: `_TASK_FACTORIES`, `_task_interval_specs`, `ensure_scheduled_tasks_catalog`.

При активном событии scanner может запрашивать **15m** бары (`bybit_data_loader`, interval `"15"`).

---

## 9. Pipeline и торговая логика

### 9.1 FadeReactionStage

Псевдокод:

```python
setup = db.get_active_fade_setup(ticker)  # status == READY, now < expires_at
if not setup:
    return

impulse = setup.initial_move_direction   # UP | DOWN (из fade_setups, см. §6.4)
fade_dir = setup.fade_direction          # уже compute_fade_direction(); не инвертировать здесь
signal = consensus["signal"].upper()

# Запрет догонять импульс (chase)
if impulse == "UP" and signal == "LONG":
    ctx.fade_order_blocked = True
if impulse == "DOWN" and signal == "SHORT":
    ctx.fade_order_blocked = True

# Разрешить контр-импульс
if signal == fade_dir and setup.fade_quality >= threshold:
    ctx.fade_allow_fade = True  # optional size boost

# Structural shock → глобальный cooldown
if has_shock_tag(setup, ["depeg", "exchange_hack", "etf_approval", ...]):
    ctx.fade_order_blocked = True
    # опционально: block ALL tickers на FADE_COOLDOWN_HOURS
```

### 9.2 OrderActivationStage

Добавить проверку рядом с `meta_order_blocked`:

```python
if getattr(ctx, "fade_order_blocked", False):
    return
```

### 9.3 PipelineContext

Новые поля:

- `fade_order_blocked: bool`
- `fade_boost: bool`
- `fade_decision: str`
- `fade_quality: float`

### 9.4 Режимы

| Режим | `FADE_REACTION_ENFORCE` | Поведение |
|-------|-------------------------|-----------|
| Shadow | `false` | Пишем `fade_*` в consensus, ордера не блокируем |
| Enforce | `true` | Блокируем chase, учитываем cooldown |

Аналогично [`META_LABEL_ENFORCE`](META_LABELING.md).

---

## 10. Роль LLM

### 10.1 MVP — без LLM

Классификация: keywords + теги API. Торговые решения: цена + правила.

### 10.2 Опционально (фаза 3) — лёгкий enrich

**Один вызов OpenRouter на новостной кластер** (не на каждую статью), после dedupe:

```json
{
  "primary_assets": ["BTC", "ETH"],
  "event_type": "regulation|hack|etf|macro|exchange|other",
  "is_structural_shock": false,
  "is_repeat_story": true,
  "narrative_ambiguity_score": 0.15,
  "affected_scope": "single_asset|crypto_sector|global_markets",
  "topic_label": "SEC delays ETF decision"
}
```

| LLM делает | LLM не делает |
|------------|----------------|
| Структура события, structural vs noise | `buy` / `sell` |
| Повтор темы vs новая тема | Замена price shock |
| Summary для GUI/audit | Вход в forecast prompt |

**`narrative_ambiguity_score`** (0.0–1.0, не `ambiguity`):

| Значение | Смысл |
|----------|--------|
| 0.0 | Однозначное событие, один доминирующий narrative |
| 0.5 | Смешанные заголовки, неясный итог |
| 1.0 | Противоречивые сигналы (одобрение + отказ, разные источники) |

Шкала фиксируется в промпте; при смене модели сравнивать только внутри одной `NEWS_LLM_MODEL_VERSION`. Высокий score → не увеличивать `event_strength`, опционально форсировать `WATCHING`.

При сбое LLM → fallback на rules-only (`circuit_breaker`).

### 10.3 Разделение контуров

```
Forecast LLM:  индикаторы → направление/уровни
News LLM:      кластер → метаданные события (опционально)
Fade:          цена + правила → READY / block chase
```

---

## 11. Конфигурация

Ключи в таблице `config` (defaults при миграции):

| Key | Default | Описание |
|-----|---------|----------|
| `NEWS_INTELLIGENCE_ENABLED` | `false` | Master switch ingestion |
| `NEWS_FETCH_INTERVAL_MINUTES` | `240` | Интервал fetch |
| `NEWS_SYMBOLS` | `` | CSV; пусто = тикеры из `settings` |
| `FADE_REACTION_ENABLED` | `false` | Scanner + stage |
| `FADE_REACTION_ENFORCE` | `false` | Shadow vs block |
| `FADE_SCAN_INTERVAL_MINUTES` | `30` | Интервал scanner |
| `FADE_MIN_EVENT_STRENGTH` | `1.0` | Порог события |
| `FADE_MIN_REACTION_Z` | `2.0` | Порог price shock |
| `FADE_MIN_QUALITY` | `1.5` | Порог READY |
| `FADE_MIN_PAUSE_MINUTES` | `20` | Пауза после spike |
| `FADE_COOLDOWN_HOURS` | `6` | После structural shock |
| `FADE_SIZE_BOOST_PCT` | `15` | Опциональный boost при ALLOW_FADE |
| `FADE_SETUP_TTL_HOURS` | `12` | `expires_at`; авто `EXPIRED` |
| `NEWS_CLUSTER_TITLE_SIM` | `0.75` | Порог cosine для слияния кластеров (§5.2.1) |
| `NEWS_CLUSTER_ALGO_VERSION` | `v1_char_tfidf` | Версия алгоритма кластеризации |
| `NEWS_LLM_ENRICH_ENABLED` | `false` | Опциональный LLM на кластер |
| `NEWS_LLM_MODEL_VERSION` | `` | Audit для `narrative_ambiguity_score` |

---

## 12. MVP по фазам

### Фаза 1 — Detection (1 вечер)

- [ ] `_ensure_news_fade_tables` (включая `publication_lag_min`, anchor-поля)
- [ ] `news_intelligence/`: Marketaux + CryptoPanic, dedupe + **кластеризация §5.2.1**
- [ ] Scheduler: `news_intelligence_update`
- [ ] `fade_context` по активным тикерам (`cluster_fetched_at` = `t_event`)
- [ ] `fade_reaction_scan`: писать `fade_setups` в `WATCHING` с **raw** множителями (калибровка)
- [ ] Price anchor по **первому 15m-бару после `fetched_at`** (§5.3)
- [ ] `compute_fade_direction()` только в `direction.py`
- [ ] Логирование / export для подбора порогов; опционально API/GUI: активные события

### Фаза 2 — Fade gate (1 вечер)

- [ ] `fade_reaction/`: price_shock, exhaustion, scanner, `expires_at` + TTL
- [ ] Scheduler: `fade_reaction_scan` (15m/1h)
- [ ] `FadeReactionStage` в `build_default_pipeline()` (shadow)
- [ ] Колонки `fade_*` в `consensus`
- [ ] `FADE_REACTION_ENFORCE=true`: block chase

### Фаза 3 — Улучшения

- [ ] `llm_enrich.py` на кластеры (`narrative_ambiguity_score`, §10.2)
- [ ] **`response-to-news`** — только здесь (нужны ретро-данные; не фаза 1–2)
- [ ] Rolling baseline интенсивности новостей
- [ ] OI / liquidations в exhaustion (если появится фид)
- [ ] Meta-label features: `fade_quality`, `consensus_aligns_impulse`
- [ ] GUI tab «News / Fade»

### Фаза 4 — Опционально

- [ ] Отдельная стратегия только по `fade_setups` (без LLM forecast)
- [ ] Backtest tool `scripts/tools/news_fade/`

---

## 13. Исключения и риски

### 13.1 Не искать fade

- Structural regime change (ETF approval, major hack, stablecoin depeg).
- FOMC, CPI и крупный macro без отдельной модели.
- Устойчивое расширение диапазона после новости без exhaustion.
- Первый вертикальный импульс (до `FADE_MIN_PAUSE_MINUTES`).
- Каскад ликвидаций в крипте — ждать подтверждения reclaim.

### 13.2 Риски

| Риск | Митигация |
|------|-----------|
| Перепечатки раздувают score | Кластеры + cooldown |
| LLM галлюцинирует категорию | Rules fallback, не в trading path |
| API rate limits | Один fetch / 4 ч, кэш в SQLite |
| Рассинхрон news vs price time | Anchor по `fetched_at` + 15m bar, лог `publication_lag_min` |
| Нестабильные кластеры | Фиксированный алгоритм §5.2.1 + `NEWS_CLUSTER_ALGO_VERSION` |
| Устаревший READY блокирует ордера | `FADE_SETUP_TTL_HOURS` → `EXPIRED` |
| Двойная инверсия UP/DOWN | Только `compute_fade_direction()` |
| Некалиброванные пороги | Raw log в `fade_setups` с фазы 1 |
| Конфликт consensus vs fade | Shadow → enforce постепенно |

---

## 14. Дальнейшее развитие

> **Не фаза 1:** `response-to-news` (сравнение знака «ожидаемой» реакции и фактического ret через 1–3 ч) — см. фазу 3; требует накопленных `news_events` + ценовых рядов.

- **Event memory:** режимы «ETF week», «SEC week» — отдельная таблица тем.
- **Whitelist/blacklist** источников.
- **Time decay:** новости старше 12–24 ч не влияют на score.
- **Finnhub** для macro cross-check.
- Документировать в [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md) §6 Scheduler после внедрения.

---

## 15. Критерии готовности

**MVP считается готовым, когда:**

1. Scheduler стабильно пишет `news_events` и `fade_context` без ручного запуска.
2. `fade_reaction_scan` переводит сетапы в `READY` только при `reaction_strength` + exhaustion.
3. `FadeReactionStage` в shadow логирует `fade_decision` для каждого LONG/SHORT консенсуса.
4. В enforce режиме блокируются входы «в сторону импульса» после READY-события.
5. Forecast pipeline **не** вызывает news API и **не** получает headlines в промпт.
6. Structural shock включает cooldown, а не автоматический контртренд.
7. Просроченные сетапы (`now > expires_at`) не влияют на `FadeReactionStage`.
8. Кластеризация воспроизводима при повторном прогоне того же JSON снапшота API.

---

## 16. Ревизия 1.1 — ответ на критику плана

| Замечание | Решение в плане |
|-----------|-----------------|
| `anchor_close` по `published_at` ненадёжен | Anchor = open первого 15m-бара после **`fetched_at`**; лог `publication_lag_min` |
| Кластеры не описаны | §5.2.1 — детерминированный v1: topic bucket + TF-IDF char merge |
| `FADE_MIN_QUALITY` не откалиброван | Фаза 1: raw множители в `fade_setups` даже в `WATCHING` |
| `expires_at` не определён | `FADE_SETUP_TTL_HOURS` (12), авто `EXPIRED` на scan |
| `initial_move_direction` vs `fade_direction` | §6.5 — канон в context, инверсия только в `compute_fade_direction()` |
| `response-to-news` рано | Явно только фаза 3 |
| `ambiguity` в LLM JSON | Переименовано в `narrative_ambiguity_score` 0.0–1.0 + версия модели |

---

## Связанные документы

- [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md) — общая архитектура
- [`META_LABELING.md`](META_LABELING.md) — ML gate поверх консенсуса
- [`REFACTOR_PLAN.md`](REFACTOR_PLAN.md) — статус рефакторинга
