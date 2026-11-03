@echo off
title Langdex Validator Miner
cd /d "%~dp0"

echo ========================================================
echo             LANGDEX PROTOCOL VALIDATOR MINER
echo ========================================================
echo Checking Python runtime environment...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3 is not installed or not in your PATH.
    echo Please install Python 3 from https://python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

python miner.py
