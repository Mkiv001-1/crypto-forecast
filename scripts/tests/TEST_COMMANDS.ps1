#!/usr/bin/env pwsh
# Test Commands Quick Reference
# Run from: d:\Git\forecast

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  FORECAST TRADING BOT - TEST SUITE QUICK REFERENCE" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Test suite locations (run from project root)
$testDir = "scripts/tests"
$mockTests = "$testDir/test_mock_consensus_orders_gui.py"
$realTests = "$testDir/test_ib_real_connection.py"

Write-Host "📍 TEST FILES:" -ForegroundColor Yellow
Write-Host "   Mock Tests (8 tests, 2.3s):   $mockTests"
Write-Host "   Real Tests (6 tests, 10s):    $realTests"
Write-Host ""

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  🚀 QUICK START COMMANDS" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""

# Command group 1: Run individual suites
Write-Host "1️⃣  RUN INDIVIDUAL TEST SUITES" -ForegroundColor White
Write-Host ""
Write-Host "   Mock Tests Only (Fast - 2.3 seconds):" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -v"
Write-Host ""
Write-Host "   Real Tests Only (IB Gateway needed - 10 seconds):" -ForegroundColor Cyan
Write-Host "   pytest $realTests -v"
Write-Host ""

# Command group 2: Run both
Write-Host "2️⃣  RUN COMPLETE TEST SUITE (Both)" -ForegroundColor White
Write-Host ""
Write-Host "   All tests (12 passed, 2 skipped):" -ForegroundColor Cyan
Write-Host "   pytest $mockTests $realTests -v"
Write-Host ""
Write-Host "   Or with quiet output:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests $realTests -q"
Write-Host ""

# Command group 3: Run specific tests
Write-Host "3️⃣  RUN SPECIFIC TESTS" -ForegroundColor White
Write-Host ""
Write-Host "   Mock: Test consensus creation" -ForegroundColor Cyan
Write-Host "   pytest $mockTests::test_mock_consensus_creation -v"
Write-Host ""
Write-Host "   Mock: Test orders from consensus" -ForegroundColor Cyan
Write-Host "   pytest $mockTests::test_orders_created_from_consensus -v"
Write-Host ""
Write-Host "   Mock: Test SHORT orders" -ForegroundColor Cyan
Write-Host "   pytest $mockTests::test_short_signal_creates_correct_orders -v"
Write-Host ""
Write-Host "   Real: Test account info" -ForegroundColor Cyan
Write-Host "   pytest $realTests::test_real_ib_account_info -v"
Write-Host ""
Write-Host "   Real: Test bracket order placement" -ForegroundColor Cyan
Write-Host "   pytest $realTests::test_real_bracket_order_with_cleanup -v"
Write-Host ""

# Command group 4: Verbose/Debug
Write-Host "4️⃣  VERBOSE & DEBUG MODES" -ForegroundColor White
Write-Host ""
Write-Host "   Very verbose with full output:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -vv -s"
Write-Host ""
Write-Host "   With full traceback on failure:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -v --tb=long"
Write-Host ""
Write-Host "   Stop at first failure:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -x"
Write-Host ""

# Command group 5: Filtering
Write-Host "5️⃣  FILTER & SELECT TESTS" -ForegroundColor White
Write-Host ""
Write-Host "   Run only CONSENSUS-related tests:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -k consensus -v"
Write-Host ""
Write-Host "   Run only ORDER-related tests:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -k order -v"
Write-Host ""
Write-Host "   Run only SHORT tests:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -k short -v"
Write-Host ""

# Command group 6: Performance
Write-Host "6️⃣  PERFORMANCE & TIMING" -ForegroundColor White
Write-Host ""
Write-Host "   Show slowest tests:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -v --durations=5"
Write-Host ""
Write-Host "   Show test names only (no output):" -ForegroundColor Cyan
Write-Host "   pytest $mockTests --collect-only"
Write-Host ""

# Command group 7: Reports
Write-Host "7️⃣  GENERATE REPORTS" -ForegroundColor White
Write-Host ""
Write-Host "   HTML report (opens in browser):" -ForegroundColor Cyan
Write-Host "   pytest $mockTests $realTests --html=report.html --self-contained-html"
Write-Host ""
Write-Host "   JSON report for CI/CD:" -ForegroundColor Cyan
Write-Host "   pytest $mockTests $realTests --json-report --json-report-file=report.json"
Write-Host ""

# Command group 8: IB Gateway specific
Write-Host "8️⃣  IB GATEWAY SETUP (Before Real Tests)" -ForegroundColor White
Write-Host ""
Write-Host "   Install ib-insync dependency:" -ForegroundColor Cyan
Write-Host "   pip install ib-insync"
Write-Host ""
Write-Host "   Check IB Gateway connection:" -ForegroundColor Cyan
Write-Host "   python -c 'from ib_gateway_client import test_ib_connection; print(test_ib_connection())'​"
Write-Host ""
Write-Host "   Verify ib_insync installed:" -ForegroundColor Cyan
Write-Host "   python -c 'from ib_insync import *; print(f\"ib_insync version: {__version__}\")'​"
Write-Host ""

# Command group 9: Watch mode (requires pytest-watch)
Write-Host "9️⃣  WATCH MODE (Auto-rerun on file change)" -ForegroundColor White
Write-Host ""
Write-Host "   Install first time:" -ForegroundColor Cyan
Write-Host "   pip install pytest-watch"
Write-Host ""
Write-Host "   Auto-rerun mock tests on changes:" -ForegroundColor Cyan
Write-Host "   ptw $mockTests -v"
Write-Host ""
Write-Host "   Auto-rerun on failure:" -ForegroundColor Cyan
Write-Host "   ptw $mockTests -v -x"
Write-Host ""

# Command group 10: CI/CD pipeline
Write-Host "🔟 CI/CD PIPELINE" -ForegroundColor White
Write-Host ""
Write-Host "   Stage 1: Fast unit tests (2.3 seconds)" -ForegroundColor Cyan
Write-Host "   pytest $mockTests -q --tb=short"
Write-Host ""
Write-Host "   Stage 2: Integration tests (10 seconds, requires IB)" -ForegroundColor Cyan
Write-Host "   pytest $realTests -q --tb=short"
Write-Host ""
Write-Host "   Stage 3: Full validation (12.3 seconds)" -ForegroundColor Cyan
Write-Host "   pytest $mockTests $realTests -q"
Write-Host ""

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  📚 DOCUMENTATION FILES" -ForegroundColor Yellow
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host ""
Write-Host "   Complete documentation:" -ForegroundColor Cyan
Write-Host "   • INTEGRATION_TEST_SUITE.md       ← Start here"
Write-Host "   • TEST_MOCK_CONSENSUS_README.md   ← Mock test details"
Write-Host "   • TEST_IB_REAL_CONNECTION_README.md ← Real test details"
Write-Host ""

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ EXPECTED RESULTS" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "   Mock tests:  8 passed  in 2.30s" -ForegroundColor Green
Write-Host "   Real tests:  4 passed, 2 skipped in ~10s" -ForegroundColor Green
Write-Host "   Combined:    12 passed, 2 skipped in 18.12s" -ForegroundColor Green
Write-Host ""

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  🎯 WORKFLOW EXAMPLE" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Development Cycle:" -ForegroundColor White
Write-Host "   1. Make code changes" -ForegroundColor Gray
Write-Host "   2. pytest $mockTests -v          (2 seconds)" -ForegroundColor Cyan
Write-Host "   3. If all green → commit & push" -ForegroundColor Gray
Write-Host "   4. On release → pytest $realTests -v  (10 seconds)" -ForegroundColor Cyan
Write-Host "   5. Deploy with confidence ✨" -ForegroundColor Green
Write-Host ""

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  💡 TIPS & TRICKS" -ForegroundColor Magenta
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host ""
Write-Host "   • Use -k flag to filter by test name: pytest -k consensus"
Write-Host "   • Use -x flag to stop on first failure: pytest -x"
Write-Host "   • Use -v for verbose output (shows individual tests)"
Write-Host "   • Use -q for quiet output (shows only summary)"
Write-Host "   • Use -s to see print() output: pytest -s"
Write-Host "   • Use --co to see which tests will run: pytest --co"
Write-Host ""

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  Ready to test? Try this:" -ForegroundColor Yellow
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host ""
Write-Host "   pytest test_mock_consensus_orders_gui.py -v" -ForegroundColor Green
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Gray
