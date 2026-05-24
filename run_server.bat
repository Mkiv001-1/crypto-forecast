@echo off
chcp 65001 >nul
echo =========================================
echo  Forecast Trading Robot - Server
echo =========================================
echo.

REM Use existing .venv312 (Python 3.12)
if not exist "%~dp0.venv312\Scripts\python.exe" (
    echo Error: .venv312 not found.
    echo Run: py -3.12 -m venv .venv312
    echo Then: .venv312\Scripts\python.exe -m pip install -r requirements_server.txt
    pause
    exit /b 1
)

REM Create INI from example if missing
if not exist "%~dp0scripts\server\ini\server_config.ini" (
    echo Creating server_config.ini from example...
    copy "%~dp0scripts\server\ini\server_config.ini.example" "%~dp0scripts\server\ini\server_config.ini" >nul
    echo.
    echo IMPORTANT: Edit scripts\server\ini\server_config.ini and set your API key!
    echo.
)

set PYTHONPATH=%~dp0
echo.
echo Starting server with Python 3.12...
echo Press Ctrl+C to stop.
echo.

"%~dp0.venv312\Scripts\python.exe" "%~dp0scripts\server\main.py" %*
pause
