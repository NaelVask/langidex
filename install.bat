@echo off
title Langdex Setup and Dependency Installer
cd /d "%~dp0"

echo ========================================================
echo          LANGDEX VALIDATOR SETUP AND INSTALLER
echo ========================================================
echo Installing required protocol libraries...

pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements. Please ensure pip is installed.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo [SUCCESS] Dependencies installed successfully!
echo You can now double-click StartMiner.bat to start mining DEK.
echo ========================================================
pause
