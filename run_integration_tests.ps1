# Run integration tests with real Bybit Demo API
#
# Requirements:
#   - Set BYBIT_API_KEY and BYBIT_API_SECRET environment variables
#   - Demo account only (tests will fail if demo=False)
#
# Usage:
#   $env:BYBIT_API_KEY="your_demo_key"
#   $env:BYBIT_API_SECRET="your_demo_secret"
#   .\run_integration_tests.ps1

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Running Integration Tests with Bybit Demo API" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if (-not $env:BYBIT_API_KEY) {
    Write-Host "ERROR: BYBIT_API_KEY not set" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please set environment variables:" -ForegroundColor Yellow
    Write-Host '  $env:BYBIT_API_KEY="your_demo_api_key"' -ForegroundColor Yellow
    Write-Host '  $env:BYBIT_API_SECRET="your_demo_api_secret"' -ForegroundColor Yellow
    exit 1
}

if (-not $env:BYBIT_API_SECRET) {
    Write-Host "ERROR: BYBIT_API_SECRET not set" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please set environment variables:" -ForegroundColor Yellow
    Write-Host '  $env:BYBIT_API_KEY="your_demo_api_key"' -ForegroundColor Yellow
    Write-Host '  $env:BYBIT_API_SECRET="your_demo_api_secret"' -ForegroundColor Yellow
    exit 1
}

Write-Host "BYBIT_API_KEY is set" -ForegroundColor Green
Write-Host "Running tests..." -ForegroundColor Cyan
Write-Host ""

& .venv312\Scripts\python.exe -m pytest scripts/tests/test_integration_live_bybit.py -v -m integration --override-ini="addopts="

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "TESTS FAILED" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    exit 1
} else {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "ALL TESTS PASSED" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
}
