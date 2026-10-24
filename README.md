# 🌸 Pastel AI - Local Desktop Chatbot

A standalone Windows desktop chatbot application powered by **FastAPI**, **LangChain**, and **Ollama** running the local **Qwen 2.5 3B** (`qwen2.5:3b`) model.

Pastel AI is completely private, requires no external AI APIs, no API keys, and has zero external CDN dependencies. All inference runs locally on your machine.

---

## ⚡ Quick Start: Install & Run in a Single Command

No manual multi-step configuration needed. Copy and run the command below:

### Option 1: One-Click Launch (Recommended)
This command automatically checks your environment, installs any missing dependencies, and opens the desktop chatbot:

```cmd
run.bat
```
*(Or in PowerShell: `.\run.bat`)*

---

### Option 2: Run the Pre-Built Desktop Executable Directly
If the application is already compiled, double-click or run:

```cmd
dist\PastelAI\PastelAI.exe
```

---

### Option 3: Rebuild the Standalone Executable in a Single Command
To clean-install dependencies and build `PastelAI.exe`:

```cmd
build.bat
```

---

## 📋 One-Time Prerequisite

Before the first launch, make sure **Ollama** is installed with the local Qwen model:

1. Install Ollama from [https://ollama.com](https://ollama.com).
2. Download the local model (run once in your terminal):
   ```cmd
   ollama run qwen2.5:3b
   ```

*(Pastel AI will check for Ollama and `qwen2.5:3b` automatically on startup and show a status badge in the app).*

---

## ✨ Features

- **Double-Click Native Window**: Uses Microsoft Edge WebView2 via `pywebview` for a sleek desktop experience with an automatic fallback to your default browser.
- **100% Offline Frontend**: Bundled local CSS replacing all CDN scripts. Operates fully without an internet connection.
- **Auto-Managed Backend**: Launches FastAPI in the background and shuts it down cleanly when you close the window.
- **Automatic Port Conflict Resolution**: Automatically scans ports starting from 8000 and connects to the first free port.
- **Local AI Status Monitor**: Live indicators for Ollama health and `qwen2.5:3b` model readiness.
- **Custom Application Icon**: Branded with a custom pastel lavender icon (`app_icon.ico`).

---

## 📁 Clean Project Structure

```
LearningLangChain/
│
├── run.bat                      <-- ⚡ 1-Click install & run launcher
├── build.bat                    <-- 🔨 1-Click PyInstaller executable builder
│
├── dist/
│   └── PastelAI/
│       └── PastelAI.exe         <-- Standalone Windows executable (No Python needed!)
│
├── desktop_app.py               <-- Desktop runner (Uvicorn lifecycle & pywebview window)
├── main.py                      <-- FastAPI backend & LangChain agent
├── ollama_service.py            <-- Local Ollama service & model health checks
├── index.html                   <-- Pastel chatbot UI
├── style.css                    <-- Standalone offline CSS
├── generate_icon.py             <-- Script generating app_icon.ico
├── app_icon.ico                 <-- Windows application icon
├── requirements.txt             <-- Python package dependencies
├── PastelAI.spec                <-- PyInstaller build specification
└── README.md                    <-- Documentation
```

---

## 💻 Running on Another Laptop (Portability)

To move Pastel AI to another Windows laptop:

1. Copy the **`dist\PastelAI`** folder to the target laptop (via USB or zip).
2. Install Ollama on the target laptop from [ollama.com](https://ollama.com).
3. Open a terminal on the target laptop and run:
   ```cmd
   ollama run qwen2.5:3b
   ```
4. Double-click **`PastelAI.exe`**.

> **Note**: No Python installation or pip commands are required on the other laptop. The `PastelAI.exe` package is completely self-contained.

---

## 🛠️ Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **"Ollama Offline" badge** | Ollama is not installed or service is stopped. | The app attempts to start `ollama serve` automatically. If Ollama is not installed, install it from [ollama.com](https://ollama.com). |
| **"Model Missing" banner** | `qwen2.5:3b` has not been downloaded yet. | Run `ollama run qwen2.5:3b` in your terminal to download the model. |
| **Port Conflict** | Port 8000 is used by another program. | Pastel AI handles this automatically by finding the next open port (8001, 8002, etc.). |
| **Window fails to open** | Missing WebView2 runtime. | Pastel AI automatically falls back and opens the chat in your default web browser. |
