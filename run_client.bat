@echo off
chcp 65001 >nul
echo =========================================
echo  Forecast Trading Robot - GUI Client
echo =========================================
echo.

REM Use existing .venv312 (Python 3.12)
if not exist "%~dp0.venv312\Scripts\python.exe" (
    echo Error: .venv312 not found.
    echo Run: py -3.12 -m venv .venv312
    echo Then: .venv312\Scripts\python.exe -m pip install -r requirements_client.txt
    pause
    exit /b 1
)

REM Create INI from example if missing
if not exist "%~dp0scripts\client\ini\client_config.ini" (
    echo Creating client_config.ini from example...
    copy "%~dp0scripts\client\ini\client_config.ini.example" "%~dp0scripts\client\ini\client_config.ini" >nul
    echo.
    echo IMPORTANT: Edit scripts\client\ini\client_config.ini and set server URL and API key!
    echo.
)

set PYTHONPATH=%~dp0
echo.
echo Starting GUI client with Python 3.12...
echo.

"%~dp0.venv312\Scripts\python.exe" "%~dp0scripts\client\main.py" %*
