@echo off
chcp 65001 >nul
echo =========================================
echo  Forecast - Compress Database (VACUUM)
echo =========================================
echo.

if not exist "%~dp0.venv312\Scripts\python.exe" (
    echo Error: .venv312 not found.
    echo Run: py -3.12 -m venv .venv312
    pause
    exit /b 1
)

"%~dp0.venv312\Scripts\python.exe" "%~dp0scripts\tools\maintenance\vacuum_db.py" %*

echo.
pause
