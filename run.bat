@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo                   Pastel AI - 1-Click Launcher
echo =====================================================================
echo.

:: Check if prebuilt executable exists
if exist "dist\PastelAI\PastelAI.exe" (
    echo [1/1] Launching Pastel AI Desktop Application...
    start "" "dist\PastelAI\PastelAI.exe"
    exit /b 0
)

:: Otherwise, run from source with automatic setup
echo Prebuilt executable not found. Starting from Python source...

:: 1. Find Python
set "PYTHON_EXE="
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        echo Creating virtual environment 'venv'...
        python -m venv venv
        set "PYTHON_EXE=venv\Scripts\python.exe"
    ) else (
        echo ERROR: Python is not installed or not in PATH.
        echo Please install Python 3.10+ from https://python.org
        pause
        exit /b 1
    )
)

:: 2. Ensure dependencies are installed
if not exist "venv\.deps_installed" (
    echo Installing required packages...
    "!PYTHON_EXE!" -m pip install -r requirements.txt
    if %ERRORLEVEL% equ 0 (
        type nul > "venv\.deps_installed"
    )
)

:: 3. Ensure icon exists
if not exist "app_icon.ico" (
    "!PYTHON_EXE!" generate_icon.py
)

:: 4. Run application
echo Launching Pastel AI...
"!PYTHON_EXE!" desktop_app.py
