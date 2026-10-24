<p align="center">
  <img src="app_icon.png" width="120" height="120" alt="GHOSTMIND Logo" style="border-radius: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.15);" />
</p>

<h1 align="center">GHOSTMIND - Local Desktop Chatbot</h1>

<p align="center">
  <strong>A standalone, 100% private Windows desktop chatbot powered by FastAPI, LangChain, and local Ollama (Qwen 2.5 3B).</strong>
</p>

<p align="center">
  <em>Zero cloud leaks • Zero API keys & costs • 100% Offline capability • Self-contained native desktop app</em>
</p>

---

## 🚀 One-Command Full Installation & Launch

Copy and paste this **single command** into your terminal (PowerShell or Command Prompt) inside the project folder:

```cmd
setup.bat
```

*(Or in PowerShell: `.\setup.bat`)*

### What this single command does completely automatically:
1. 🦙 **Ollama & Model**: Auto-detects Ollama (installs it automatically via Windows Package Manager if missing) and downloads the local `qwen2.5:3b` AI model.
2. 🐍 **Virtual Environment**: Automatically creates a fresh virtual environment (`venv`) and installs all pinned packages from `requirements.txt` with zero version conflicts.
3. 🖥️ **Desktop Shortcut**: Automatically creates a branded **GHOSTMIND** shortcut on your Windows Desktop with the custom app icon.
4. ✨ **Launches the App**: Opens the desktop chat window ready for offline conversation.

---

## 💻 Running on Another Laptop (One-Line Setup)

To set up and run GHOSTMIND on any other Windows laptop:

```powershell
winget install Ollama.Ollama -e --accept-source-agreements --accept-package-agreements && ollama run qwen2.5:3b && .\dist\GHOSTMIND\GHOSTMIND.exe
```

> **Self-Contained Executable**: `GHOSTMIND.exe` includes Python and all required libraries bundled inside. No Python installation or pip commands are required on the other laptop.

---

## 🌟 Advantages of Using This Application

| Advantage | Why It Matters |
| :--- | :--- |
| **100% Privacy & Data Security** | Every prompt and conversation stays strictly on your computer. Zero data is sent to external cloud servers, preventing data leaks. |
| **Zero API Keys & Zero Costs** | No OpenAI/Anthropic accounts, no tokens to purchase, no credit card required, and no subscription fees. |
| **100% Offline Capability** | Works seamlessly without an active internet connection. Ideal for travel, flights, and secure air-gapped workstations. |
| **Zero Python Setup for End Users** | The compiled `GHOSTMIND.exe` contains its own isolated runtime. Users can double-click and chat without configuring Python or PATH. |
| **Zero Version Conflicts** | All Python dependencies in `requirements.txt` are pinned to exact verified versions, ensuring zero dependency crashes during installation. |
| **Self-Healing Backend & Auto-Port Management** | Automatically starts local Ollama service, auto-detects `qwen2.5:3b`, resolves port 8000 conflicts dynamically (8001, 8002, etc.), and shuts down cleanly upon exit. |
| **Native Desktop Experience** | Built using Microsoft Edge WebView2 for a smooth desktop window with instant load times, branded taskbar icon, and modern UI. |

---

## 📁 Clean Project Structure

```
PersonalAI/
│
├── setup.bat                    <-- 🚀 1-Command full installer (Ollama + Venv + Shortcut + Launch)
├── run.bat                      <-- ⚡ Quick launcher
├── create_shortcut.bat          <-- 🖥️ Desktop shortcut creator
├── build.bat                    <-- 🔨 Standalone executable compiler
│
├── dist/
│   └── GHOSTMIND/
│       └── GHOSTMIND.exe        <-- Standalone Windows executable (No Python needed!)
│
├── app_icon.png                 <-- Application logo (PNG format)
├── app_icon.ico                 <-- Windows application icon (ICO format)
├── desktop_app.py               <-- Desktop runner (Uvicorn lifecycle & pywebview window)
├── main.py                      <-- FastAPI backend & LangChain agent
├── ollama_service.py            <-- Local Ollama service & model health checks
├── index.html                   <-- GHOSTMIND chatbot UI (embedded logo & offline styling)
├── style.css                    <-- Standalone offline CSS
├── generate_icon.py             <-- Script generating app_icon.ico from app_icon.png
├── requirements.txt             <-- Strictly pinned package dependencies
├── GhostMind.spec               <-- PyInstaller build specification
└── README.md                    <-- Documentation
```

---

## 📦 Pinned Dependencies

```txt
fastapi==0.162.0
uvicorn[standard]==0.54.0
langchain==1.4.7
langchain-core==1.7.0
langchain-ollama==1.1.0
langchain-google-genai==4.4.2
pydantic==2.14.1
python-dotenv==1.2.4
pywebview==6.2.1
pillow==13.0.0
pyinstaller==6.22.3
```

---

## 🛠️ Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **"Ollama Offline" badge** | Ollama service is stopped. | The app starts `ollama serve` automatically. If Ollama is not installed, run `setup.bat` or install via `winget install Ollama.Ollama -e`. |
| **"Model Missing" banner** | `qwen2.5:3b` has not been downloaded yet. | Run `ollama run qwen2.5:3b` in your terminal to download the model. |
| **Port Conflict** | Port 8000 is used by another program. | GHOSTMIND handles this automatically by binding to the next open port (8001, 8002, etc.). |
| **Window fails to open** | Missing WebView2 runtime. | GHOSTMIND automatically falls back and opens the chat in your default web browser. |
