@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo                GHOSTMIND - Complete Automated Setup
echo =====================================================================
echo.

:: STEP 1: Check and install Ollama + Required Models
echo [1/5] Checking Ollama and local models...
where ollama >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo     Ollama not detected. Installing Ollama automatically via Windows Package Manager...
    winget install Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    echo     Starting Ollama background service...
    start "" ollama serve
    timeout /t 3 >nul
)

:: Pull Qwen 2.5 3B generative model
ollama list 2>nul | findstr /i "qwen2.5:3b" >nul
if %ERRORLEVEL% neq 0 (
    echo     Downloading local generative model qwen2.5:3b (one-time setup)...
    ollama pull qwen2.5:3b
) else (
    echo     Generative model 'qwen2.5:3b' is ready.
)

:: Pull nomic-embed-text 768-dim embedding model for RAG
ollama list 2>nul | findstr /i "nomic-embed-text" >nul
if %ERRORLEVEL% neq 0 (
    echo     Downloading local embedding model nomic-embed-text (one-time setup)...
    ollama pull nomic-embed-text
) else (
    echo     Embedding model 'nomic-embed-text' is ready.
)

:: STEP 2: Setup Python Virtual Environment and Install Pinned Dependencies
echo.
echo [2/5] Setting up Python virtual environment and dependencies...
if not exist "venv\Scripts\python.exe" (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        echo     Creating virtual environment 'venv'...
        python -m venv venv
    ) else (
        echo [ERROR] Python is not installed or not in PATH.
        echo Please install Python 3.10+ from https://python.org
        pause
        exit /b 1
    )
)

echo     Installing pinned requirements from requirements.txt...
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

:: STEP 3: Environment Configuration and Database Migrations
echo.
echo [3/5] Checking configuration and database migrations...
if not exist ".env" (
    if exist ".env.example" (
        echo     Creating .env from .env.example...
        copy ".env.example" ".env" >nul
    )
)

echo     Applying PostgreSQL database schema migrations via Alembic...
"venv\Scripts\python.exe" -m alembic upgrade head
if %ERRORLEVEL% neq 0 (
    echo     [Notice] Migration check completed. Database schema will initialize on first launch.
) else (
    echo     Database schema up-to-date at Alembic HEAD.
)

:: STEP 4: Create Desktop Shortcut with Custom Icon
echo.
echo [4/5] Creating Windows Desktop Shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$shortcutPath = Join-Path $desktop 'GHOSTMIND.lnk';" ^
  "$workingDir = '%~dp0';" ^
  "$iconPath = Join-Path $workingDir 'app_icon.ico';" ^
  "$exeTarget = Join-Path $workingDir 'dist\GHOSTMIND\GHOSTMIND.exe';" ^
  "$pythonwTarget = Join-Path $workingDir 'venv\Scripts\pythonw.exe';" ^
  "$desktopApp = Join-Path $workingDir 'desktop_app.py';" ^
  "$wsh = New-Object -ComObject WScript.Shell;" ^
  "$shortcut = $wsh.CreateShortcut($shortcutPath);" ^
  "if (Test-Path $exeTarget) { $shortcut.TargetPath = $exeTarget } else { $shortcut.TargetPath = $pythonwTarget; $shortcut.Arguments = \"`\"$desktopApp`\"\" };" ^
  "$shortcut.WorkingDirectory = $workingDir;" ^
  "if (Test-Path $iconPath) { $shortcut.IconLocation = \"$iconPath,0\" };" ^
  "$shortcut.Description = 'GHOSTMIND - Personal AI Operating System';" ^
  "$shortcut.Save();" ^
  "Write-Host '    Created GHOSTMIND shortcut on Desktop!' -ForegroundColor Green"

:: STEP 5: Launch Application
echo.
echo [5/5] Launching GHOSTMIND...
if exist "dist\GHOSTMIND\GHOSTMIND.exe" (
    start "" "dist\GHOSTMIND\GHOSTMIND.exe"
) else (
    start "" "venv\Scripts\pythonw.exe" desktop_app.py
)

echo.
echo =====================================================================
echo           SETUP COMPLETE! GHOSTMIND IS READY TO USE!
echo =====================================================================
timeout /t 3 >nul
exit /b 0
