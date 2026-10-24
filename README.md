<p align="center">
  <img src="app_icon.png" width="120" height="120" alt="GHOSTMIND local AI assistant logo" style="border-radius: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.15);" />
</p>

<h1 align="center">GHOSTMIND</h1>

<p align="center">
  <strong>A Private, Offline-Capable AI Assistant for Windows</strong>
</p>

<p align="center">
  Run AI locally on your computer using Ollama and Qwen 2.5 3B — without cloud LLM API keys or per-token API costs.
</p>

<p align="center">
  <a href="#-quick-start-recommended">Quick Start</a> •
  <a href="#-features">Features</a> •
  <a href="#-why-use-a-local-ai-assistant">Why GHOSTMIND?</a> •
  <a href="#-how-ghostmind-works">How It Works</a> •
  <a href="#-technology-stack">Tech Stack</a> •
  <a href="#-troubleshooting">Troubleshooting</a>
</p>

<p align="center">
  <strong><em>You command. GHOSTMIND executes.</em></strong>
</p>

---

## ⚡ Quick Start (Recommended)

If you are new here, you only need to run **one command**. Open your terminal (PowerShell or Command Prompt) in the project folder and run:

```cmd
setup.bat
```
*(Or in PowerShell: `.\setup.bat`)*

### What this single command does automatically:
1. 🦙 **Checks & Sets Up Ollama**: Installs Ollama automatically if missing and downloads the local `qwen2.5:3b` model.
2. 🐍 **Creates Python Environment**: Builds an isolated `venv` and installs all pinned packages from `requirements.txt`.
3. 🖥️ **Creates Desktop Shortcut**: Places a branded `GHOSTMIND` shortcut with icon on your Windows Desktop.
4. ✨ **Launches the App**: Opens the desktop chatbot window ready to use!

---

## ❓ What Is GHOSTMIND?

**GHOSTMIND** is a personal AI assistant and Windows desktop chatbot built with **Python**, **FastAPI**, **LangChain**, and **Ollama** running the **Qwen 2.5 3B** language model.

It lets you chat with an AI directly on your own computer through a sleek desktop application instead of using a browser-based cloud chatbot. 

GHOSTMIND is designed for anyone who wants:
- 🔒 **Total Privacy**: Your conversations stay on your device and are never uploaded to cloud servers.
- ✈️ **Offline Capability**: Chat freely without an internet connection after the one-time model download.
- 💰 **Zero Cost**: No OpenAI or Anthropic API keys, no subscription tiers, and no per-token charges.
- 🚀 **Effortless Windows Setup**: One command sets up everything from scratch.

---

## ✨ Features

- **Local AI Inference**: Powered by Qwen 2.5 3B running locally through Ollama.
- **100% Privacy-Focused**: Prompts are processed entirely on your machine with zero data collection.
- **Zero API Keys**: No credit cards, billing accounts, or API keys required.
- **Full Offline Operation**: Works without an internet connection once the model is downloaded.
- **One-Command Installation**: Automated setup script (`setup.bat`) configures the whole app.
- **Native Windows Desktop Window**: Clean desktop app interface powered by Microsoft Edge WebView2 (via `pywebview`).
- **Auto-Healing Service**: Checks and starts the local Ollama background engine automatically.
- **Dynamic Port Conflict Handling**: Automatically finds the next free port if port 8000 is occupied.
- **Pre-Packaged Standalone Executable**: Includes a standalone `.exe` option that requires no Python setup.
- **Custom Desktop Branding**: Dedicated GHOSTMIND logo, Windows icon, and desktop shortcut.

---

## 💡 Why Use a Local AI Assistant?

| Feature | GHOSTMIND | Cloud AI Chatbots (ChatGPT / Claude) |
| :--- | :---: | :---: |
| **Runs on your computer** | **Yes** (100% Local) | No (Remote Cloud Servers) |
| **Requires Cloud API Keys** | **No** | Yes / Paid Subscription |
| **Chat data leaves your device** | **Never** | Yes (Sent to third-party servers) |
| **Works offline (without internet)** | **Yes** | No |
| **Per-token or monthly fees** | **$0 (Free forever)** | Monthly subscriptions / API billing |
| **Dedicated Windows Desktop App** | **Yes** | Web Browser Tab |
| **Python required for standalone .exe** | **No** (Self-contained) | N/A |

> *Note: An internet connection is only needed once during initial setup to download Ollama and the language model.*

---

## 📦 Installation Options

### Option 1: One-Command Installation (Recommended for New Users)
Clone or download this repository, open PowerShell or CMD in the project folder, and run:
```cmd
setup.bat
```
*(Or in PowerShell: `.\setup.bat`)*

The script will automatically detect/install Ollama, download `qwen2.5:3b`, set up the Python environment, create a desktop shortcut, and launch GHOSTMIND.

---

### Option 2: Run the Packaged Windows Executable (No Python Needed)
If using the compiled distribution, ensure Ollama is installed and run:

1. Install Ollama (one-line PowerShell):
   ```powershell
   winget install Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
   ```
2. Download the model:
   ```cmd
   ollama pull qwen2.5:3b
   ```
3. Launch GHOSTMIND directly:
   ```cmd
   dist\GHOSTMIND\GHOSTMIND.exe
   ```

---

### Option 3: Manual Run from Source
If you prefer running from Python source code:

```powershell
# 1. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install pinned dependencies
pip install -r requirements.txt

# 3. Pull the local model
ollama pull qwen2.5:3b

# 4. Launch the desktop app
python desktop_app.py
```

---

## 🔄 How GHOSTMIND Works

GHOSTMIND connects a lightweight desktop interface to a local FastAPI backend, which uses LangChain to communicate directly with Ollama.

```
┌─────────────────────────────────┐
│             User                │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   GHOSTMIND Desktop Window      │  (pywebview + HTML/CSS Interface)
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│        FastAPI Backend          │  (Local REST API on http://127.0.0.1:8000)
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│      LangChain Orchestrator     │  (Agent & Prompt Pipeline)
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│      Ollama Local Runtime       │  (Local Engine on http://127.0.0.1:11434)
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│       Qwen 2.5 3B Model         │  (Local Neural Weights on your Disk/GPU)
└────────────────┬────────────────┘
                 │
                 ▼
          Response Displayed
```

Every word generated stays entirely on your computer.

---

## 🛠️ Technology Stack

| Technology | Purpose |
| :--- | :--- |
| **Python** | Core application logic and service orchestration |
| **FastAPI** | High-performance asynchronous backend API |
| **LangChain** | LLM integration, prompt templates, and agent orchestration |
| **Ollama** | Local LLM runtime and inference engine |
| **Qwen 2.5 3B** | Fast, high-accuracy local language model |
| **HTML5 & CSS3** | Clean offline chatbot user interface |
| **pywebview** | Native Windows desktop application window (Edge WebView2) |
| **Uvicorn** | Embedded ASGI server |
| **PyInstaller** | Bundles the complete project into a standalone `.exe` |
| **Pillow** | Multi-resolution icon generation and asset processing |

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
├── desktop_app.py               <-- Desktop runner (Window lifecycle & server management)
├── main.py                      <-- FastAPI backend & LangChain agent
├── ollama_service.py            <-- Local Ollama service & model health checks
│
├── index.html                   <-- GHOSTMIND chatbot UI (Embedded logo & offline styling)
├── style.css                    <-- Standalone offline CSS
│
├── app_icon.png                 <-- Application logo (PNG format)
├── app_icon.ico                 <-- Windows application icon (ICO format)
├── generate_icon.py             <-- Script generating app_icon.ico from app_icon.png
│
├── requirements.txt             <-- Strictly pinned package dependencies
├── GhostMind.spec               <-- PyInstaller build specification
│
├── dist/
│   └── GHOSTMIND/
│       └── GHOSTMIND.exe        <-- Standalone Windows executable (No Python needed!)
│
└── README.md                    <-- Documentation
```

---

## 📦 Pinned Dependencies

All dependencies are strictly pinned in [requirements.txt](requirements.txt) to guarantee zero version conflicts during installation:

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

## 🔧 Troubleshooting

| Issue | Possible Cause | Solution |
| :--- | :--- | :--- |
| **"Ollama Offline" badge** | Local Ollama service is not running | Run `ollama serve` in a terminal or re-run `setup.bat`. |
| **"Model Missing" banner** | Qwen 2.5 3B has not been downloaded | Run `ollama pull qwen2.5:3b` in your terminal. |
| **Port Conflict** | Another program is using port 8000 | GHOSTMIND handles this automatically by scanning for the next free port (8001, 8002, etc.). |
| **Desktop Window Fails to Open** | Missing WebView2 runtime | GHOSTMIND automatically falls back to your default browser. You can also install the Microsoft Edge WebView2 runtime. |
| **Slow AI Responses** | High system load or CPU mode | Close heavy background apps. If you have an NVIDIA GPU, Ollama will automatically leverage GPU acceleration for faster speeds. |

---

## 🔒 Privacy and Offline Usage

- **Local Processing**: GHOSTMIND runs entirely on your hardware. Prompts are never sent to external servers, cloud providers, or third-party APIs.
- **Offline Ready**: Once Ollama and `qwen2.5:3b` are downloaded during setup, you can turn off Wi-Fi and use GHOSTMIND completely offline.
- **No Telemetry**: There is no tracking, telemetry, or analytics embedded in the application.

---

## 🔮 Future Possibilities

Potential future enhancements include:
- Natural-language desktop automation and task management
- Local document search and Retrieval-Augmented Generation (RAG)
- Local conversation history and persistent session memory
- Support for selecting other Ollama models (e.g., Llama 3, Mistral, Phi-3)
- Custom user-defined prompt templates and system instructions

---

## 🤝 Contributing

Suggestions, bug reports, and contributions are welcome! If you encounter an issue, please open an issue on GitHub with your Windows version and steps to reproduce.

---

<p align="center">
  <strong>GHOSTMIND — You command. GHOSTMIND executes.</strong>
</p>

<p align="center">
  <em>A local AI assistant for people who value privacy, control, and simplicity.</em>
</p>
