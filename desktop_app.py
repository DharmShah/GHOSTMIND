import os
import sys
import time
import socket
import threading
import traceback
import webbrowser
import urllib.request
import multiprocessing

# Required for PyInstaller Windows builds
multiprocessing.freeze_support()

# Define log file location
EXE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
LOG_FILE = os.path.join(EXE_DIR, "pastel_ai.log")

class LoggerWriter:
    def __init__(self, filepath):
        self.filepath = filepath
    def write(self, s):
        if not s or s == "\n":
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {s.rstrip()}\n")
        except Exception:
            pass
    def flush(self):
        pass

# Ensure stdout and stderr never fail in windowed (console=False) mode
if sys.stdout is None:
    sys.stdout = LoggerWriter(LOG_FILE)
if sys.stderr is None:
    sys.stderr = LoggerWriter(LOG_FILE)

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    try:
        print(formatted)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
            f.flush()
    except Exception:
        pass

# Global exception catcher
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    err = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log(f"CRITICAL UNCAUGHT EXCEPTION:\n{err}")

sys.excepthook = handle_exception
threading.excepthook = lambda args: log(f"THREAD EXCEPTION in {args.thread.name}:\n{args.exc_type}: {args.exc_value}")

import uvicorn
import ollama_service
from main import app, get_resource_path


def find_available_port(preferred_port=8000, max_attempts=50):
    """Find an available port starting from preferred_port without conflict."""
    for port in range(preferred_port, preferred_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    # Fallback to random available port from OS
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class UvicornServer(threading.Thread):
    """Threaded Uvicorn server that can be shut down cleanly."""
    def __init__(self, fastapi_app, host="127.0.0.1", port=8000):
        super().__init__(daemon=True, name="UvicornServerThread")
        self.host = host
        self.port = port
        self.config = uvicorn.Config(
            app=fastapi_app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None  # Critical for windowed frozen PyInstaller
        )
        self.server = uvicorn.Server(self.config)

    def run(self):
        log("UvicornServer thread running...")
        try:
            self.server.run()
            log("UvicornServer finished run loop.")
        except Exception as e:
            log(f"UvicornServer error: {e}\n{traceback.format_exc()}")

    def stop(self):
        log("Stopping UvicornServer...")
        self.server.should_exit = True


def wait_for_server(url, max_seconds=10.0):
    """Poll the backend server until it responds or times out."""
    start = time.time()
    attempt = 0
    while time.time() - start < max_seconds:
        attempt += 1
        try:
            with urllib.request.urlopen(f"{url}/status", timeout=1.0) as resp:
                if resp.status == 200:
                    log(f"Server responded successfully on attempt {attempt}.")
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    log("=" * 60)
    log("      Pastel AI Desktop Chatbot (Qwen 2.5 3B)")
    log("=" * 60)

    # 1. Check and start local Ollama service safely
    log("[1/4] Checking local Ollama service...")
    try:
        running, msg = ollama_service.ensure_ollama_running(max_wait_seconds=6.0)
        if running:
            log(f"      OK: {msg}")
        else:
            log(f"      WARNING: {msg}")
    except Exception as e:
        log(f"      Ollama service check exception: {e}")

    # 2. Check if required model is available
    log("[2/4] Verifying local model 'qwen2.5:3b'...")
    try:
        model_ready = ollama_service.is_model_installed("qwen2.5:3b")
        if model_ready:
            log("      OK: 'qwen2.5:3b' is installed locally.")
        else:
            log("      WARNING: Model 'qwen2.5:3b' is not installed locally.")
            log("      (Chatbot will display a guidance banner to run 'ollama run qwen2.5:3b')")
    except Exception as e:
        log(f"      Model check exception: {e}")

    # 3. Find an available port and start FastAPI server
    port = find_available_port(8000)
    log(f"[3/4] Starting backend on http://127.0.0.1:{port}...")
    server = UvicornServer(fastapi_app=app, host="127.0.0.1", port=port)
    server.start()

    app_url = f"http://127.0.0.1:{port}"
    log(f"Waiting for backend to become ready at {app_url}...")
    if not wait_for_server(app_url, max_seconds=12.0):
        log("      ERROR: Server failed to start in time.")
        sys.exit(1)
    log("      Backend is online and ready.")

    # 4. Open Desktop Window (pywebview) with fallback to default browser
    log("[4/4] Launching desktop user interface...")
    icon_path = get_resource_path("app_icon.ico")
    if not os.path.exists(icon_path):
        icon_path = get_resource_path("app_icon.png")
    if not os.path.exists(icon_path):
        icon_path = None

    use_pywebview = True
    try:
        import webview
    except ImportError:
        use_pywebview = False

    if use_pywebview:
        try:
            log("Creating pywebview window...")
            window = webview.create_window(
                title="Pastel AI - Local Chatbot",
                url=app_url,
                width=1040,
                height=880,
                min_size=(640, 520),
                text_select=True,
                confirm_close=False
            )

            def on_closed():
                log("\n[Shutdown] Window closed by user. Terminating backend cleanly...")
                server.stop()

            window.events.closed += on_closed

            # Start webview event loop (blocks until window is closed)
            log("Starting pywebview event loop...")
            webview.start(icon=icon_path if icon_path and os.path.exists(icon_path) else None)

            # Ensure server stops cleanly
            server.stop()
            log("[Shutdown] Completed successfully.")
            return

        except Exception as e:
            log(f"      pywebview encountered an issue ({e}). Falling back to browser...")

    # Fallback: Default Browser
    log(f"      Opening in default browser at {app_url}...")
    webbrowser.open(app_url)
    log("\nPastel AI is running. Press Ctrl+C in this terminal to shut down.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("\n[Shutdown] Shutting down backend...")
        server.stop()
        log("[Shutdown] Done.")


if __name__ == "__main__":
    main()
