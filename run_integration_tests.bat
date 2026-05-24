@echo off
chcp 65001 >nul
REM Run integration tests with real Bybit Demo API
REM 
REM Requirements:
REM   - Set BYBIT_API_KEY and BYBIT_API_SECRET environment variables
REM   - Demo account only (tests will fail if demo=False)
REM
REM Usage:
REM   set BYBIT_API_KEY=your_demo_key
REM   set BYBIT_API_SECRET=your_demo_secret
REM   run_integration_tests.bat

echo ============================================
echo Running Integration Tests with Bybit Demo API
echo ============================================
echo.

if "%BYBIT_API_KEY%"=="" (
    echo ERROR: BYBIT_API_KEY not set
    echo.
    echo Please set environment variables:
    echo   set BYBIT_API_KEY=your_demo_api_key
    echo   set BYBIT_API_SECRET=your_demo_api_secret
    exit /b 1
)

if "%BYBIT_API_SECRET%"=="" (
    echo ERROR: BYBIT_API_SECRET not set
    echo.
    echo Please set environment variables:
    echo   set BYBIT_API_KEY=your_demo_api_key
    echo   set BYBIT_API_SECRET=your_demo_api_secret
    exit /b 1
)

echo BYBIT_API_KEY is set
echo Running tests...
echo.

.venv312\Scripts\python.exe -m pytest scripts/tests/test_integration_live_bybit.py -v -m integration --override-ini="addopts="

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================
    echo TESTS FAILED
    echo ============================================
    exit /b 1
) else (
    echo.
    echo ============================================
    echo ALL TESTS PASSED
    echo ============================================
)
