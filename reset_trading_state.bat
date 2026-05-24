@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=%SCRIPT_DIR%.venv312\Scripts\python.exe"
set "RESET_SCRIPT=%SCRIPT_DIR%scripts\tools\reset_trading_state.py"
set "FINAL_ARGS=%*"
set "INTERACTIVE_MODE=0"

echo =========================================
echo  Forecast Trading Robot - Trading Reset
echo =========================================
echo.
echo Removes: forecasts, consensus, orders/trades (DB + Bybit)
echo Keeps: settings, accounts, price data, Bybit journals
echo.

REM Use existing .venv312 (Python 3.12)
if not exist "%PYTHON_EXE%" (
    echo Error: .venv312 not found.
    echo Run: py -3.12 -m venv .venv312
    echo Then: .venv312\Scripts\python.exe -m pip install -r requirements_server.txt
    goto :END_WITH_PAUSE_ERROR
)

if not exist "%RESET_SCRIPT%" (
    echo Error: reset script not found: %RESET_SCRIPT%
    goto :END_WITH_PAUSE_ERROR
)

if "%~1"=="" (
    set "INTERACTIVE_MODE=1"
    call :SHOW_MENU
    if errorlevel 1 goto :END_WITH_PAUSE_ERROR
)

echo Running reset tool with args: %FINAL_ARGS%
echo.
"%PYTHON_EXE%" "%RESET_SCRIPT%" %FINAL_ARGS%
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% EQU 0 (
    echo Reset finished successfully.
) else (
    echo Reset finished with errors. Exit code: %EXIT_CODE%
)

if "%INTERACTIVE_MODE%"=="1" pause
exit /b %EXIT_CODE%

:SHOW_MENU
echo Select reset mode:
echo   [1] Dry-run (preview Bybit + DB counts)
echo   [2] Full reset (cancel Bybit orders, close positions, clear DB)
echo   [3] DB only (forecasts/consensus/orders/trades — no Bybit)
echo   [4] Bybit only (cancel orders, close positions — no DB)
echo   [5] Custom args
echo   [Q] Cancel
echo.
set "CHOICE="
set /p "CHOICE=Enter choice: "

if /I "%CHOICE%"=="1" (
    set "FINAL_ARGS=--dry-run"
    exit /b 0
)
if /I "%CHOICE%"=="2" (
    call :CONFIRM_DESTRUCTIVE "FULL reset (Bybit + DB)"
    if errorlevel 1 exit /b 1
    set "FINAL_ARGS="
    exit /b 0
)
if /I "%CHOICE%"=="3" (
    call :CONFIRM_DESTRUCTIVE "DB-only reset"
    if errorlevel 1 exit /b 1
    set "FINAL_ARGS=--db-only"
    exit /b 0
)
if /I "%CHOICE%"=="4" (
    call :CONFIRM_DESTRUCTIVE "Bybit-only reset"
    if errorlevel 1 exit /b 1
    set "FINAL_ARGS=--bybit-only"
    exit /b 0
)
if /I "%CHOICE%"=="5" (
    set "CUSTOM_ARGS="
    set /p "CUSTOM_ARGS=Enter custom args for reset_trading_state.py: "
    set "FINAL_ARGS=%CUSTOM_ARGS%"
    exit /b 0
)
if /I "%CHOICE%"=="Q" exit /b 1

echo Invalid choice.
echo.
goto :SHOW_MENU

:CONFIRM_DESTRUCTIVE
set "CONFIRM_TEXT=%~1"
echo.
echo WARNING: %CONFIRM_TEXT% will change live state.
echo Stop the API server before continuing.
set "CONFIRM_VALUE="
set /p "CONFIRM_VALUE=Type YES to continue: "
if /I not "%CONFIRM_VALUE%"=="YES" (
    echo Cancelled.
    exit /b 1
)
exit /b 0

:END_WITH_PAUSE_ERROR
pause
exit /b 1
