@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo                GHOSTMIND - Windows Build Script
echo =====================================================================
echo.

:: 1. Check for Python executable
set "PYTHON_EXE="
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
    echo [1/5] Using existing virtual environment: !PYTHON_EXE!
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        echo [1/5] Python found in PATH. Creating virtual environment 'venv'...
        python -m venv venv
        if not exist "venv\Scripts\python.exe" (
            echo ERROR: Failed to create virtual environment.
            exit /b 1
        )
        set "PYTHON_EXE=venv\Scripts\python.exe"
    ) else (
        echo ERROR: Python is not installed or not in PATH.
        echo Please install Python 3.10+ from https://python.org
        exit /b 1
    )
)

:: 2. Upgrade pip and install requirements
echo.
echo [2/5] Installing and verifying required packages...
"!PYTHON_EXE!" -m pip install --upgrade pip
"!PYTHON_EXE!" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to install Python dependencies from requirements.txt.
    exit /b %ERRORLEVEL%
)

:: 3. Generate icon if missing
echo.
echo [3/5] Checking application icon assets...
if not exist "app_icon.ico" (
    echo Generating application icon from app_icon.png...
    "!PYTHON_EXE!" generate_icon.py
) else (
    echo Application icon found.
)

:: 4. Clean previous build artifacts (dist and build)
echo.
echo [4/5] Preparing build directories...
if exist "build\GHOSTMIND" rmdir /s /q "build\GHOSTMIND" >nul 2>nul

:: 5. Run PyInstaller using GhostMind.spec
echo.
echo [5/5] Compiling standalone executable with PyInstaller...
"!PYTHON_EXE!" -m PyInstaller GhostMind.spec --noconfirm
if %ERRORLEVEL% neq 0 (
    echo ERROR: PyInstaller build failed.
    exit /b %ERRORLEVEL%
)

echo.
echo =====================================================================
echo                      BUILD SUCCESSFUL!
echo =====================================================================
echo.
echo Executable location:
echo   %~dp0dist\GHOSTMIND\GHOSTMIND.exe
echo.
echo You can run the application by double-clicking GHOSTMIND.exe
echo or by running:
echo   start "" "%~dp0dist\GHOSTMIND\GHOSTMIND.exe"
echo.
pause
