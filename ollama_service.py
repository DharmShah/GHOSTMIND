import os
import sys
import time
import json
import shutil
import subprocess
import urllib.request
import urllib.error

# Resolve Ollama host and model from environment or defaults
OLLAMA_HOST = (
    os.environ.get("OLLAMA_BASE_URL")
    or os.environ.get("OLLAMA_HOST")
    or "http://127.0.0.1:11434"
).rstrip("/")

REQUIRED_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")


def get_ollama_tags_url():
    return f"{OLLAMA_HOST}/api/tags"


def is_ollama_running(timeout=2.0):
    """Check if the local Ollama API is responding with HTTP 200."""
    url = get_ollama_tags_url()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GhostMind/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True
    except Exception:
        return False
    return False


def is_ollama_process_running():
    """Check if an ollama process is already running in the OS process table."""
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq ollama.exe"],
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            ).decode("utf-8", errors="ignore")
            if "ollama.exe" in output.lower():
                return True
            output_app = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq ollama app.exe"],
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            ).decode("utf-8", errors="ignore")
            if "ollama app.exe" in output_app.lower():
                return True
        except Exception:
            pass
    return False


def find_ollama_app():
    """Find the official Windows Ollama desktop app (ollama app.exe)."""
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama app.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Ollama\ollama app.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama app.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def find_ollama_executable():
    """Find ollama.exe CLI on the system."""
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


def get_installed_models(timeout=3.0):
    """Retrieve list of model names from local Ollama."""
    url = get_ollama_tags_url()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GhostMind/2.0"})
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


def is_model_installed(target_model=REQUIRED_MODEL, timeout=3.0):
    """Check if target_model is available in local Ollama."""
    models = get_installed_models(timeout=timeout)
    target_clean = target_model.lower().strip()
    for m in models:
        m_lower = m.lower().strip()
        if m_lower == target_clean:
            return True
        if m_lower.startswith(f"{target_clean}:") or target_clean.startswith(f"{m_lower}:"):
            return True
        if m_lower == f"{target_clean}:latest" or f"{m_lower}:latest" == target_clean:
            return True
    return False


def pull_model(model_name=REQUIRED_MODEL, timeout=300.0):
    """Pull the specified model via Ollama REST API or CLI."""
    # Try REST API first
    url = f"{OLLAMA_HOST}/api/pull"
    payload = json.dumps({"name": model_name, "stream": False}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "GhostMind/2.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass

    # Fallback to CLI
    exe_path = find_ollama_executable()
    if exe_path:
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
            res = subprocess.run(
                [exe_path, "pull", model_name],
                timeout=timeout,
                creationflags=creation_flags,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return res.returncode == 0
        except Exception:
            pass
    return False


def ensure_ollama_running(max_wait_seconds=25.0):
    """
    Ensure Ollama is running. If not, automatically launch the local service and wait
    until it is ready to respond.
    Returns (running: bool, message: str).
    """
    # 1. Quick check: Is Ollama already responding?
    if is_ollama_running(timeout=1.5):
        return True, "Ollama service is already running."

    # 2. Check if an Ollama process is already in memory and initializing
    process_already_starting = is_ollama_process_running()

    if not process_already_starting:
        # 3. Locate Ollama executable: Prefer desktop app on Windows, fallback to CLI
        app_path = find_ollama_app()
        cli_path = find_ollama_executable()

        if not app_path and not cli_path:
            return False, (
                "Ollama was not found on your system. "
                "Please install Ollama from https://ollama.com to enable AI features."
            )

        try:
            if sys.platform == "win32":
                # DETACHED_PROCESS (0x00000008) + CREATE_NO_WINDOW (0x08000000)
                # Ensures Ollama stays running independently of Python process
                creation_flags = 0x08000000 | 0x00000008
                if app_path:
                    # Windows desktop app starts the background daemon and tray icon
                    subprocess.Popen(
                        [app_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        close_fds=True
                    )
                else:
                    subprocess.Popen(
                        [cli_path, "serve"],
                        creationflags=creation_flags,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        close_fds=True
                    )
            else:
                subprocess.Popen(
                    [cli_path or "ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True
                )
        except Exception as e:
            return False, f"Failed to launch Ollama service automatically: {str(e)}"

    # 4. Wait for Ollama service to become ready and respond on OLLAMA_HOST
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        time.sleep(0.5)
        if is_ollama_running(timeout=1.0):
            return True, "Ollama service started successfully."

    return False, (
        f"Ollama was launched but failed to respond at "
        f"{OLLAMA_HOST} within {int(max_wait_seconds)} seconds."
    )


def check_system_readiness(target_model=REQUIRED_MODEL):
    """
    Full readiness check for the chatbot:
    1. Check/start Ollama (auto-start if offline)
    2. Check if required model is installed locally
    """
    running, message = ensure_ollama_running(max_wait_seconds=20.0)
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

    installed_models = get_installed_models(timeout=3.0)
    model_ok = is_model_installed(target_model, timeout=3.0)

    if not model_ok:
        return {
            "ready": False,
            "ollama_running": True,
            "model_installed": False,
            "model_name": target_model,
            "error_type": "model_missing",
            "message": (
                f"Model '{target_model}' is not installed locally in Ollama.\n"
                f"Please run 'ollama run {target_model}' or click Install to download it.\n"
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
