import os
import sys
import json
import uuid
import shutil
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import httpx

from mcp.security import validate_stdio_command, validate_remote_url

logger = logging.getLogger("ghostmind.mcp.transports")

class BaseTransport(ABC):
    """Abstract base transport for Model Context Protocol communication."""

    @abstractmethod
    async def start(self) -> None:
        """Starts the transport connection or process."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stops the transport connection and cleans up resources."""
        pass

    @abstractmethod
    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Dict[str, Any]:
        """Sends a JSON-RPC 2.0 request and awaits the corresponding response."""
        pass

    @abstractmethod
    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Sends a JSON-RPC 2.0 notification (no response expected)."""
        pass

    @abstractmethod
    def is_alive(self) -> bool:
        """Returns True if the transport is actively connected."""
        pass


class StdioTransport(BaseTransport):
    """
    Subprocess stdio transport communicating via newline-delimited JSON-RPC 2.0.
    Optimized for Windows process lifecycle and non-blocking asynchronous IO.
    """

    def __init__(self, command: str, args: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None):
        if not validate_stdio_command(command, args):
            raise ValueError(f"Security validation failed for stdio command: {command} {args}")

        self.command = command
        self.args = args
        self.env = env or {}
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
        self._is_running = False

    async def start(self) -> None:
        if self._is_running:
            return

        # Prepare environment
        process_env = os.environ.copy()
        process_env.update(self.env)
        # Suppress interactive prompts in node/npm
        process_env["CI"] = "true"
        process_env["PYTHONUNBUFFERED"] = "1"

        # Resolve command executable on host OS (especially Windows .cmd / .bat / sys.executable)
        executable = self.command
        if executable.lower() in ("python", "python3"):
            executable = sys.executable
        else:
            resolved = shutil.which(executable)
            if resolved:
                executable = resolved
            elif sys.platform == "win32":
                for ext in (".cmd", ".exe", ".bat"):
                    candidate = shutil.which(executable + ext)
                    if candidate:
                        executable = candidate
                        break

        try:
            self.process = await asyncio.create_subprocess_exec(
                executable,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
                cwd=self.cwd
            )
            self._is_running = True
            self._read_task = asyncio.create_task(self._reader_loop())
            logger.info(f"Stdio transport started for: {self.command}")
        except Exception as e:
            self._is_running = False
            logger.error(f"Failed to start stdio process: {e}")
            raise RuntimeError(f"Could not spawn MCP process '{self.command}': {e}")

    async def _reader_loop(self) -> None:
        """Reads newline-delimited JSON-RPC lines from stdout."""
        assert self.process and self.process.stdout is not None
        while self._is_running:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="ignore").strip()
                if not decoded:
                    continue

                try:
                    message = json.loads(decoded)
                    msg_id = str(message.get("id"))
                    if msg_id in self._pending_requests:
                        fut = self._pending_requests.pop(msg_id)
                        if not fut.done():
                            if "error" in message:
                                fut.set_exception(RuntimeError(message["error"].get("message", "MCP Error")))
                            else:
                                fut.set_result(message.get("result", {}))
                except json.JSONDecodeError:
                    logger.debug(f"Stdio non-json log: {decoded}")
            except Exception as e:
                logger.warning(f"Error in stdio reader loop: {e}")
                break
        self._is_running = False

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Dict[str, Any]:
        if not self._is_running or not self.process or not self.process.stdin:
            raise RuntimeError("Stdio transport is not running.")

        req_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }
        line = json.dumps(payload) + "\n"

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_requests[req_id] = fut

        try:
            self.process.stdin.write(line.encode("utf-8"))
            await self.process.stdin.drain()
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise TimeoutError(f"MCP request '{method}' timed out after {timeout}s")
        except Exception:
            self._pending_requests.pop(req_id, None)
            raise

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        if not self._is_running or not self.process or not self.process.stdin:
            return
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        line = json.dumps(payload) + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

    async def stop(self) -> None:
        self._is_running = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()

        for fut in self._pending_requests.values():
            if not fut.done():
                fut.set_exception(RuntimeError("Transport closed"))
        self._pending_requests.clear()

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def is_alive(self) -> bool:
        return self._is_running and self.process is not None and self.process.returncode is None


class HttpSseTransport(BaseTransport):
    """
    Remote MCP Transport using Server-Sent Events (SSE) and HTTP POST.
    Includes SSRF protection and connection health verification.
    """

    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        if not validate_remote_url(url, allow_local_dev=True):
            raise ValueError(f"Security validation failed for remote MCP URL: {url}")

        self.url = url
        self.headers = headers or {}
        self.client: Optional[httpx.AsyncClient] = None
        self._is_running = False
        self._endpoint_url: Optional[str] = None

    async def start(self) -> None:
        if self._is_running:
            return

        self.client = httpx.AsyncClient(headers=self.headers, timeout=30.0)
        self._is_running = True
        self._endpoint_url = self.url.rstrip("/") + "/messages"
        logger.info(f"HTTP/SSE transport initialized for: {self.url}")

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Dict[str, Any]:
        if not self._is_running or not self.client:
            raise RuntimeError("HTTP transport is not connected.")

        req_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }

        try:
            target_url = self._endpoint_url or self.url
            resp = await self.client.post(target_url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "MCP Remote Error"))
            return data.get("result", {})
        except httpx.TimeoutException:
            raise TimeoutError(f"HTTP request to '{self.url}' timed out after {timeout}s")
        except Exception as e:
            raise RuntimeError(f"HTTP MCP error on '{method}': {e}")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        if not self._is_running or not self.client:
            return
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        try:
            target_url = self._endpoint_url or self.url
            await self.client.post(target_url, json=payload, timeout=5.0)
        except Exception as e:
            logger.warning(f"Failed to send notification to '{self.url}': {e}")

    async def stop(self) -> None:
        self._is_running = False
        if self.client:
            await self.client.aclose()
            self.client = None

    def is_alive(self) -> bool:
        return self._is_running and self.client is not None

