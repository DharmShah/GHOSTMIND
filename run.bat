@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo                   GHOSTMIND - 1-Click Launcher
echo =====================================================================
echo.

:: 1. Check Ollama and Model automatically
where ollama >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [*] Checking local Ollama and Qwen 2.5 3B model...
    ollama list 2>nul | findstr /i "qwen2.5:3b" >nul
    if !ERRORLEVEL! neq 0 (
        echo [*] Pulling local model qwen2.5:3b (one-time download)...
        ollama pull qwen2.5:3b
    )
) else (
    echo [!] Notice: Ollama not found in PATH.
    echo     Install Ollama from https://ollama.com if you haven't already.
)

:: 2. Check if prebuilt executable exists
if exist "dist\GHOSTMIND\GHOSTMIND.exe" (
    echo [*] Launching GHOSTMIND Desktop Application...
    start "" "dist\GHOSTMIND\GHOSTMIND.exe"
    exit /b 0
)

:: 3. Otherwise, run from source with automatic setup
echo [*] Prebuilt executable not found. Initializing Python environment...

set "PYTHON_EXE="
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        echo [*] Creating virtual environment 'venv'...
        python -m venv venv
        set "PYTHON_EXE=venv\Scripts\python.exe"
    ) else (
        echo [ERROR] Python is not installed or not in PATH.
        echo Please install Python 3.10+ from https://python.org
        pause
        exit /b 1
    )
)

:: 4. Ensure pinned dependencies are installed
if not exist "venv\.deps_installed" (
    echo [*] Installing pinned requirements from requirements.txt...
    "!PYTHON_EXE!" -m pip install --upgrade pip
    "!PYTHON_EXE!" -m pip install -r requirements.txt
    if %ERRORLEVEL% equ 0 (
        type nul > "venv\.deps_installed"
    ) else (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

:: 5. Ensure icon exists
if not exist "app_icon.ico" (
    "!PYTHON_EXE!" generate_icon.py
)

:: 6. Launch desktop application
echo [*] Launching GHOSTMIND...
start "" "!PYTHON_EXE!" desktop_app.py
exit /b 0
