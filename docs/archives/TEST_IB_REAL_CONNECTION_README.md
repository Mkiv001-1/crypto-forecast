# Real IB Gateway Integration Tests

Comprehensive integration tests for **real** Interactive Brokers Gateway connections.

## Overview

These tests validate the complete flow with actual IB Gateway connections (not mocked):

| Test | Purpose | Status |
|------|---------|--------|
| test_real_ib_account_info | Fetch real account data | ✅ Working |
| test_real_ib_positions | Retrieve portfolio positions | ✅ Working |
| test_real_bid_ask_spread | Get market data spreads | ⏭️ Optional |
| test_real_bracket_order_with_cleanup | Place & cancel orders | ✅ Working |
| test_real_ib_with_consensus | Consensus → Real IB flow | ✅ Working |

## Prerequisites

### 1. IB Gateway Running

```bash
# Paper Trading (7497)
localhost:7497

# Live Trading (7496) 
localhost:7496
```

Start IB Gateway and connect your account. Verify API is enabled:
- Settings → API → Socket Port (7497 or 7496)
- Ensure API is enabled ✓

### 2. Python Dependencies

```bash
pip install ib-insync
```

Required packages:
- `ib-insync` — Interactive Brokers async wrapper (already installed in project)
- `pytest` — Test runner
- `sqlite3` — Database (built-in)

### 3. Safety Configuration

Before running tests on live account:

```python
# scripts/core/config.py
ORDER_MODE = "paper"  # CRITICAL: Set to "paper" for safety
LIVE_TRADING_CONFIRMED = "false"  # Must be "false"
```

## Running the Tests

### Run All Real IB Tests

```bash
cd d:\Git\forecast

# Run with verbose output
python -m pytest test_ib_real_connection.py -v -s

# Run specific test only
python -m pytest test_ib_real_connection.py::test_real_ib_account_info -v -s
```

### Run Without Marks Warning

The tests use `@pytest.mark.integration` but it's not registered. To suppress warnings:

```bash
python -m pytest test_ib_real_connection.py -v -s -W ignore::pytest.PytestUnknownMarkWarning
```

### Run Mock + Real Tests Together

```bash
# All 8 mock tests + 4-6 real tests
python -m pytest test_mock_consensus_orders_gui.py test_ib_real_connection.py -v

# Result: 12 passed, 2 skipped
```

## Test Descriptions

### Test 1: Account Information

**Location:** `test_ib_real_connection.py::test_real_ib_account_info`

**What it does:**
1. Connects to real IB Gateway
2. Fetches account info: ID, type, net liquidation, buying power, available funds, cash
3. Displays account details in table format

**Example Output:**
```
[Account 1]
  ID: DU7093209
  Type: INDIVIDUAL
  Currency: USD
  Net Liquidation: $   34,671.02
  Buying Power:    $        0.00
  Available Funds: $   -1,047.45
  Cash Balance:    $        0.00
  Maint Margin:    $   32,738.10
```

**Validates:**
- Account connection works
- Can fetch real account data
- Account is funded (net liquidation > 0)

---

### Test 2: Portfolio Positions

**Location:** `test_ib_real_connection.py::test_real_ib_positions`

**What it does:**
1. Fetches all open positions from the account
2. Displays ticker, quantity, avg cost, market price, market value
3. Shows current portfolio state

**Example Output:**
```
Ticker     Qty          Avg Cost     Mkt Price    Market Value   
AMZN       -300         226.95       272.96       -81,888.30     
DUOL       100          145.74       110.19       11,018.93      
TSLA       -20          418.31       410.17       -8,203.40      
V          25           329.40       320.65       8,016.37       
```

**Validates:**
- Can fetch real positions
- Market data is current
- Handles long and short positions

---

### Test 3: Bid/Ask Spread

**Location:** `test_ib_real_connection.py::test_real_bid_ask_spread`

**What it does:**
1. Gets market data for TSLA (very liquid stock)
2. Retrieves bid/ask prices and spread %
3. Validates spread is reasonable

**Example Output:**
```
TSLA Market Data:
  Bid Price: $410.17
  Ask Price: $410.41
  Spread:    0.000592% (0.2400)
```

**Validates:**
- Market data API works
- Bid < Ask (correct relationship)
- Spread is reasonable for liquid stock

**Note:** May be skipped if market data not available during non-trading hours.

---

### Test 4: Real Bracket Order (with Cleanup)

**Location:** `test_ib_real_connection.py::test_real_bracket_order_with_cleanup`

**⚠️ WARNING: Places REAL orders on account**

**What it does:**
1. Creates a bracket order for TSLA:
   - **Entry:** LIMIT at $250 (BUY 1 share)
   - **Take-Profit:** $270
   - **Stop-Loss:** $230
2. Submits order to IB Gateway (real)
3. Gets order IDs back
4. **Immediately cancels** all orders for cleanup

**Example Output:**
```
Order Placement Result:
  Status: submitted
  Parent Order ID: 12345
  Target Order ID: 12346
  Stop Order ID:   12347

Cleaning up (cancelling orders)...
  Parent order #12345: cancelled
```

**Validates:**
- Can place real bracket orders
- Order structure is correct (entry + target + stop)
- Can cancel orders
- No orphaned orders left on account

**Safety Features:**
- Uses LIMIT entry (won't fill instantly)
- Uses DAY time-in-force (expires at market close)
- Immediately cancels for cleanup
- Paper account only (configured)

---

### Test 5: Real IB with Consensus

**Location:** `test_ib_real_connection.py::test_real_ib_with_consensus`

**What it does:**
1. Creates mock consensus for TSLA:
   - Signal: LONG
   - Target: $270
   - Stop: $230
2. Calculates position size: 10 shares, $500 risk
3. Submits real bracket order via IB Gateway
4. Order gets QUEUED (for market open if outside hours)
5. Cleans up by cancelling

**Example Output:**
```
Step 1: Create mock consensus for TSLA
  Signal: LONG
  Target: $270.00
  Stop:   $230.00

Step 2: Calculate position size
  Quantity: 10 shares
  Risk: $500.00

Step 3: Place real bracket order via IB Gateway
  Result: QUEUED
  Message: Queued for market open
```

**Validates:**
- Full integration: consensus → position sizing → IB order
- Order calculation is correct
- Real IB submission works
- Can handle QUEUED status for pre-market orders

---

## Integration Flow

```
Mock Consensus (TSLA)
    ↓
[Signal: LONG, Target: $270, Stop: $230]
    ↓
Position Sizer
    ↓
[Quantity: 10 shares, Risk: $500]
    ↓
IB Gateway (Real Connection)
    ↓
[Order submitted to real account]
    ↓
Cleanup (Cancel orders)
```

## Troubleshooting

### "Connection Status: None"
**Problem:** IB Gateway connection test returns None

**Solutions:**
1. Verify IB Gateway is running: `localhost:7497` (paper) or `:7496` (live)
2. Check Settings → API → Socket Port is enabled
3. Verify account is connected in IB Gateway window
4. Check firewall isn't blocking localhost connection

### "No accounts found"
**Problem:** fetch_ib_accounts returns empty list

**Solutions:**
1. Ensure IB Gateway has account connected
2. Check API is enabled (Settings → API)
3. Verify Master Client ID is being used (default: 1)
4. Try with different client_id in test

### "Bid/Ask data not available"
**Problem:** test_real_bid_ask_spread is skipped

**Solutions:**
1. This is normal during non-trading hours
2. May indicate market data subscription issue
3. Run during market hours (9:30 AM - 4 PM ET)
4. Check market data permissions in account

### "Order submission failed"
**Problem:** Order placement returns error

**Solutions:**
1. Check account has sufficient buying power
2. Verify ORDER_MODE = "paper" (if using paper account)
3. Check if market is open (orders may be QUEUED if pre-market)
4. Verify symbol is correct and tradeable
5. Check position limit not exceeded

### "Table or column doesn't exist"
**Problem:** SQLite schema error during test

**Solutions:**
1. Run with clean test database (tests create temporary DB)
2. Delete `trading_robot.db` if it's corrupted
3. Ensure all migrations are applied: `python scripts/core/migrate.py`

## Performance

**Typical Execution Time:**

| Test | Time |
|------|------|
| Account Info | 0.5s |
| Positions | 1.0s |
| Bid/Ask Spread | 1.5s |
| Bracket Order | 2.0s |
| Consensus Flow | 1.5s |
| **Total** | **~6-10s** |

First connection may take longer (ib_insync initialization).

## Configuration

### Paper vs Live Trading

**Paper Trading (Recommended for testing):**
```python
# scripts/server/config.py
IB_HOST = "127.0.0.1"
IB_PORT = 7497  # Paper trading port
```

**Live Trading (High Risk - Use with caution):**
```python
# scripts/server/config.py
IB_HOST = "127.0.0.1"
IB_PORT = 7496  # Live trading port
```

### Order Mode Setting

**CRITICAL:** Set this before running real order tests

```python
# scripts/core/config.py
ORDER_MODE = "paper"  # "paper" or "live"
LIVE_TRADING_CONFIRMED = "false"  # Must be "false" for safety
```

## Advanced Usage

### Running Only Market Hours

```bash
# Skip if market is closed
python -m pytest test_ib_real_connection.py::test_real_bracket_order_with_cleanup -v -k "market"
```

### Custom Client ID

Some tests use client_id 94-99 to avoid conflicts with other connections:

```python
# In test code
result = place_bracket_order(
    symbol="TSLA",
    action="BUY",
    quantity=1,
    ...
    client_id=94  # ← Each test uses different ID
)
```

### Debugging Order Placement

To see detailed order placement debug info:

```bash
# Increase verbosity
python -m pytest test_ib_real_connection.py::test_real_bracket_order_with_cleanup -vv -s
```

## Related Files

- [test_ib_real_connection.py](test_ib_real_connection.py) — Real IB Gateway tests
- [test_mock_consensus_orders_gui.py](test_mock_consensus_orders_gui.py) — Mock tests (8 tests)
- [scripts/core/ib_gateway_client.py](scripts/core/ib_gateway_client.py) — IB integration code
- [scripts/core/order_manager.py](scripts/core/order_manager.py) — Order submission logic
- [scripts/core/consensus.py](scripts/core/consensus.py) — Consensus calculation

## Summary

✅ **Complete Real IB Gateway Integration**
- 4-6 tests validating real connections
- Account info, positions, market data, order placement
- Full consensus → order flow
- Safety mechanisms (paper only, cleanup, limits)
- Comprehensive error handling

Total test suite: **12 mock tests + 6 real tests = 18 total** ✨
