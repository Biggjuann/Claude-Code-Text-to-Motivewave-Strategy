@echo off
echo ===============================================
echo Magic Line Strategy Optimizer
echo ===============================================
echo.

cd /d "%~dp0"

set PYTHON_PATH=C:\Users\jung_\AppData\Local\Programs\Python\Python312\python.exe

REM Check if Python is available
if not exist "%PYTHON_PATH%" (
    echo Python not found at: %PYTHON_PATH%
    echo Please update PYTHON_PATH in this script
    pause
    exit /b 1
)

REM Check for command argument
if "%1"=="" (
    echo Running optimizer menu...
    "%PYTHON_PATH%" optimizer.py
) else (
    echo Running: optimizer.py %1
    "%PYTHON_PATH%" optimizer.py %1
)

echo.
pause
