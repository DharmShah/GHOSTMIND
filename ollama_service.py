import os
import sys
import time
import json
import shutil
import subprocess
import urllib.request
import urllib.error

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
REQUIRED_MODEL = "qwen2.5:3b"

def get_ollama_tags_url():
    host = OLLAMA_HOST.rstrip("/")
    return f"{host}/api/tags"

def is_ollama_running(timeout=2.0):
    """Check if the local Ollama API is responding."""
    url = get_ollama_tags_url()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PastelAI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True
    except Exception:
        return False
    return False

def get_installed_models(timeout=2.0):
    """Retrieve list of model names from local Ollama."""
    url = get_ollama_tags_url()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PastelAI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                names = []
                for m in models:
                    name = m.get("name") or m.get("model") or ""
                    if name:
                        names.append(name)
                return names
    except Exception:
        return []
    return []

def is_model_installed(target_model=REQUIRED_MODEL, timeout=2.0):
    """Check if target_model is available in local Ollama."""
    models = get_installed_models(timeout=timeout)
    # Check for direct match or tag variation e.g. "qwen2.5:3b" or "qwen2.5:3b:latest"
    target_clean = target_model.lower().strip()
    target_prefix = target_clean.split(":")[0]
    for m in models:
        m_lower = m.lower().strip()
        if m_lower == target_clean:
            return True
        if m_lower.startswith(f"{target_clean}:") or target_clean.startswith(f"{m_lower}:"):
            return True
        # Also check exact tag or base name if single tag
        if m_lower == f"{target_clean}:latest" or f"{m_lower}:latest" == target_clean:
            return True
    return False

def find_ollama_executable():
    """Find ollama.exe on the Windows system."""
    which_path = shutil.which("ollama")
    if which_path and os.path.exists(which_path):
        return which_path

    # Common Windows installation locations
    candidate_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Ollama\ollama.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            return path

    return None

def ensure_ollama_running(max_wait_seconds=8.0):
    """
    Ensure Ollama is running. If not, attempt to start the local service safely.
    Returns (running: bool, message: str).
    """
    if is_ollama_running(timeout=1.5):
        return True, "Ollama service is already running."

    exe_path = find_ollama_executable()
    if not exe_path:
        return False, (
            "Ollama was not found on your system. "
            "Please install Ollama from https://ollama.com and run 'ollama serve'."
        )

    # Attempt to start 'ollama serve' safely without a visible console window on Windows
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        subprocess.Popen(
            [exe_path, "serve"],
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True if sys.platform != "win32" else False
        )
    except Exception as e:
        return False, f"Failed to launch Ollama service automatically: {str(e)}"

    # Wait for Ollama service to become ready
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        time.sleep(0.5)
        if is_ollama_running(timeout=1.0):
            return True, "Ollama service started successfully."

    return False, (
        f"Ollama process was launched ({exe_path}) but failed to respond at "
        f"{OLLAMA_HOST} within {int(max_wait_seconds)} seconds."
    )

def check_system_readiness(target_model=REQUIRED_MODEL):
    """
    Full readiness check for the chatbot:
    1. Check/start Ollama
    2. Check if required model is installed locally
    """
    running, message = ensure_ollama_running()
    if not running:
        return {
            "ready": False,
            "ollama_running": False,
            "model_installed": False,
            "model_name": target_model,
            "error_type": "ollama_not_running",
            "message": message,
            "models_found": []
        }

    installed_models = get_installed_models()
    model_ok = is_model_installed(target_model)
    if not model_ok:
        return {
            "ready": False,
            "ollama_running": True,
            "model_installed": False,
            "model_name": target_model,
            "error_type": "model_missing",
            "message": (
                f"Model '{target_model}' is not installed locally in Ollama.\n"
                f"Please open your terminal or command prompt and run:\n"
                f"    ollama run {target_model}\n"
                f"Installed models found: {installed_models or 'None'}"
            ),
            "models_found": installed_models
        }

    return {
        "ready": True,
        "ollama_running": True,
        "model_installed": True,
        "model_name": target_model,
        "error_type": None,
        "message": f"Ollama is running with local model '{target_model}'.",
        "models_found": installed_models
    }

if __name__ == "__main__":
    result = check_system_readiness()
    print(json.dumps(result, indent=2))
