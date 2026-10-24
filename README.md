<p align="center">
  <img src="app_icon.png" width="110" height="110" alt="Pastel AI Logo" style="border-radius: 22px;" />
</p>

<h1 align="center">Pastel AI - Local Desktop Chatbot</h1>

<p align="center">
  <strong>A standalone, 100% private Windows desktop chatbot powered by FastAPI, LangChain, and local Ollama (Qwen 2.5 3B).</strong>
</p>

<p align="center">
  <em>Zero cloud leaks • Zero API keys & costs • 100% Offline capability • Self-contained native desktop app</em>
</p>

---

## ⚡ Quick Start: Single Command Install & Run

Paste this **one command** in your terminal to automatically install all pinned requirements and launch the application:

```powershell
pip install -r requirements.txt && python desktop_app.py
```

> **Prefer 1-Click?** Just double-click or run:
> ```cmd
> run.bat
> ```
> *(Automatically creates virtual environment, installs pinned dependencies, checks the model, and launches the app).*

---

## 💻 Running on Another Laptop (One-Line Setup)

To run on any other Windows laptop, open PowerShell and paste this **single line**:

```powershell
winget install Ollama.Ollama -e --accept-source-agreements --accept-package-agreements && ollama run qwen2.5:3b && .\dist\PastelAI\PastelAI.exe
```

> **Self-Contained Executable**: `PastelAI.exe` includes Python and all libraries bundled inside. No Python installation or pip commands are required on the other laptop.

---

## 🌟 Advantages of Using This Application

| Advantage | Why It Matters |
| :--- | :--- |
| **100% Privacy & Data Security** | Every prompt and conversation stays strictly on your computer. Zero data is sent to external cloud servers, preventing data leaks. |
| **Zero API Keys & Zero Costs** | No OpenAI/Anthropic accounts, no tokens to purchase, no credit card required, and no subscription fees. |
| **100% Offline Capability** | Works seamlessly without an active internet connection. Ideal for travel, flights, and secure air-gapped workstations. |
| **Zero Python Setup for End Users** | The compiled `PastelAI.exe` contains its own isolated runtime. Users can double-click and chat without configuring Python or PATH. |
| **Zero Version Conflicts** | All Python dependencies in `requirements.txt` are pinned to exact verified versions, ensuring zero dependency crashes during installation. |
| **Self-Healing Backend & Auto-Port Management** | Automatically starts local Ollama service, auto-detects `qwen2.5:3b`, resolves port 8000 conflicts dynamically (8001, 8002, etc.), and shuts down cleanly upon exit. |
| **Native Desktop Experience** | Built using Microsoft Edge WebView2 for a smooth desktop window with instant load times and custom pastel aesthetics. |

---

## 📁 Clean Project Structure

```
PersonalAI/
│
├── app_icon.png                 <-- Application logo (PNG format)
├── app_icon.ico                 <-- Windows application icon (ICO format)
├── run.bat                      <-- 1-Click install & run launcher
├── build.bat                    <-- 1-Click PyInstaller executable builder
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
├── generate_icon.py             <-- Script generating app_icon.ico & app_icon.png
├── requirements.txt             <-- Strictly pinned package dependencies
├── PastelAI.spec                <-- PyInstaller build specification
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
| **"Ollama Offline" badge** | Ollama service is stopped. | The app starts `ollama serve` automatically. If Ollama is not installed, install it via `winget install Ollama.Ollama -e`. |
| **"Model Missing" banner** | `qwen2.5:3b` has not been downloaded yet. | Run `ollama run qwen2.5:3b` in your terminal to download the model. |
| **Port Conflict** | Port 8000 is used by another program. | Pastel AI handles this automatically by binding to the next open port (8001, 8002, etc.). |
| **Window fails to open** | Missing WebView2 runtime. | Pastel AI automatically falls back and opens the chat in your default web browser. |
