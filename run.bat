@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo                   GHOSTMIND - 1-Click Launcher
echo =====================================================================
echo.

:: 1. Check and Start Ollama Service Automatically
echo [*] Checking local Ollama service...
curl.exe -s --connect-timeout 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] Ollama is not running. Starting Ollama background service...
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" (
        start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    ) else if exist "%ProgramFiles%\Ollama\ollama app.exe" (
        start "" "%ProgramFiles%\Ollama\ollama app.exe"
    ) else (
        where ollama >nul 2>nul
        if !ERRORLEVEL! equ 0 (
            start /b "" ollama serve >nul 2>&1
        )
    )

    :: Wait up to 15 seconds for Ollama API to respond
    echo [*] Waiting for Ollama engine to initialize...
    for /l %%i in (1,1,15) do (
        curl.exe -s --connect-timeout 1 http://127.0.0.1:11434/api/tags >nul 2>&1
        if !ERRORLEVEL! equ 0 goto :ollama_online
        timeout /t 1 /nobreak >nul
    )
)

:ollama_online
curl.exe -s --connect-timeout 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [*] Ollama service is online.
    :: Check model qwen2.5:3b
    where ollama >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        ollama list 2>nul | findstr /i "qwen2.5:3b" >nul
        if !ERRORLEVEL! neq 0 (
            echo [*] Model 'qwen2.5:3b' not found. Downloading (one-time setup)...
            ollama pull qwen2.5:3b
        ) else (
            echo [*] Model 'qwen2.5:3b' is verified and ready.
        )
    )
) else (
    echo [!] Notice: Ollama did not respond. The app will attempt to start it during launch.
)

:: 2. Initialize Python environment
echo.
echo [*] Initializing Python environment...

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

:: 3. Ensure dependencies are installed
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

:: 4. Ensure icon exists
if not exist "app_icon.ico" (
    "!PYTHON_EXE!" generate_icon.py
)

:: 5. Launch desktop application
echo [*] Launching GHOSTMIND...
start "" "!PYTHON_EXE!" desktop_app.py
exit /b 0
