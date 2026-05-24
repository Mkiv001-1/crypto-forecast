# Manual Consensus Rerun Script

## Goal

Provide a standalone CLI tool to manually re-run consensus order activation without GUI/API clicks.

## Problem

- Scheduler processes only rows in `PENDING_ORDER` state.
- Historical rows with `order_state=''` or failed rows (`ORDER_SKIPPED`, `EXPIRED`) often need manual retry.
- Existing tools recalculate consensus data but do not re-run activation pipeline for selected consensus rows.

## Solution

Add `scripts/tools/rerun_consensus_activation.py` that:

1. Selects consensus rows with `LONG|SHORT` signal and `trade_id IS NULL`.
2. Supports filters by ticker, date, explicit IDs, and order states.
3. Runs `activate_consensus_order` for each selected row.
4. Prints summary counters by result status.
5. Supports `--dry-run` mode to inspect candidates safely.

## Default Safety

- Default `--limit=50` to avoid accidental bulk activation.
- Default mode includes only states most likely to require retry:
  - `''` (empty state)
  - `PENDING_ORDER`
  - `ORDER_SKIPPED`
  - `EXPIRED`

## Usage Examples

```bash
python scripts/tools/rerun_consensus_activation.py --dry-run
python scripts/tools/rerun_consensus_activation.py --limit 20
python scripts/tools/rerun_consensus_activation.py --ticker NASDAQ:TQQQ --all
python scripts/tools/rerun_consensus_activation.py --ids 205 206 207
python scripts/tools/rerun_consensus_activation.py --date-from 2026-05-11 --all
```

## Out of Scope

- No changes to consensus calculation logic.
- No changes to order lifecycle semantics.
- No schema changes.
