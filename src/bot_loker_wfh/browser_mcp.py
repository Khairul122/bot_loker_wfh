"""BrowserMCP client with safety guards enforcing strict execution policies."""

from __future__ import annotations

import collections
import atexit
import json
import os
import queue
import signal
import shlex
import shutil
import subprocess
import threading
import time
from typing import Any
from urllib.parse import urlparse

ALLOWED_TOOLS = frozenset(
    {
        "browser_navigate",
        "browser_snapshot",
        "browser_type",
        "browser_select_option",
        "browser_click",
        "browser_wait",
        "browser_press_key",
    }
)
ALLOWED_KEYS = frozenset({"Tab", "Escape"})
ELEMENT_REQUIRING_TOOLS = frozenset(
    {"browser_type", "browser_click", "browser_select_option"}
)


def _tie_lifetime_to_parent(proc: "subprocess.Popen[str]") -> "Any | None":
    """Windows: kill the MCP tree when this process dies (e.g. terminal closed).

    ``atexit`` does not run when a console window is closed, so a Job Object with
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE is the only reliable way to reap npx->node.
    Best-effort: any failure just falls back to stop()/atexit.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_ulonglong)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC_LIMIT),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return
        info = EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle)))
        return job
    except Exception:
        return None


class McpClientError(RuntimeError):
    pass


class McpNotConnectedError(McpClientError):
    pass


class McpBrowserClient:
    """Client for controlling Chrome via @browsermcp/mcp server."""

    def __init__(
        self,
        command: str = "npx -y @browsermcp/mcp@0.1.3",
        *,
        allowed_hosts: set[str] | None = None,
        max_tool_calls: int = 80,
        timeout: float = 300.0,
    ):
        self.command = command
        self.allowed_hosts = allowed_hosts or set()
        self.max_tool_calls = max_tool_calls
        self.timeout = timeout
        self.tool_call_count = 0
        self.process: subprocess.Popen[str] | None = None
        self._request_id = 0
        self._stdout_queue: queue.Queue[str] = queue.Queue()
        self._stderr_buffer: collections.deque[str] = collections.deque(maxlen=20)
        self._threads: list[threading.Thread] = []
        self._job_handle: Any | None = None
        # Playwright MCP >= 0.0.7x calls the element argument "target"; BrowserMCP calls it "ref".
        self._ref_arg = "ref"
        # Last-resort cleanup if the process exits without an explicit stop().
        atexit.register(self.stop)

    def start(self) -> None:
        if self.process is not None:
            return

        # shlex parsing for Windows vs POSIX
        args = shlex.split(self.command, posix=(os.name != "nt"))
        if not args:
            raise McpClientError("Command BrowserMCP kosong")

        executable = shutil.which(args[0])
        if not executable:
            raise McpClientError(
                f"Node.js/npx tidak ditemukan ('{args[0]}'). Pasang Node.js 18+."
            )
        args[0] = executable

        try:
            self.process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                # New session/group so stop() can kill the whole npx->node tree.
                start_new_session=(os.name != "nt"),
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
            )
        except Exception as err:
            raise McpClientError(f"Failed to start MCP process: {err}") from err

        self._job_handle = _tie_lifetime_to_parent(self.process)

        # Background reader threads for stdout and stderr to prevent deadlocks
        stdout_t = threading.Thread(target=self._read_stdout, daemon=True)
        stderr_t = threading.Thread(target=self._read_stderr, daemon=True)
        stdout_t.start()
        stderr_t.start()
        self._threads.extend([stdout_t, stderr_t])

        # Perform JSON-RPC initialize handshakes with up to 60s timeout
        init_res = self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bot-loker-wfh", "version": "0.1.0"},
            },
            timeout=60.0,
        )
        if not init_res:
            raise McpClientError("MCP server failed to initialize")

        # Send notifications/initialized per MCP specification
        self._send_notification("notifications/initialized", {})
        try:
            tools = self._send_request("tools/list", {}).get("result", {}).get("tools", [])
            props = next(
                (t.get("inputSchema", {}).get("properties", {}) for t in tools if t.get("name") == "browser_type"),
                {},
            )
            if "target" in props and "ref" not in props:
                self._ref_arg = "target"
        except Exception:
            pass  # keep "ref"

    def _read_stdout(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self._stdout_queue.put(line)

    def _read_stderr(self) -> None:
        if not self.process or not self.process.stderr:
            return
        for line in self.process.stderr:
            self._stderr_buffer.append(line.rstrip())

    def stop(self) -> None:
        if not self.process:
            return
        proc = self.process
        self.process = None
        # npx spawns the MCP server as a child; killing only the parent leaves node
        # (and the browser it drives) running after the terminal is closed.
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def wait_for_extension(self, timeout: float = 20.0) -> bool:
        """Poll browser_snapshot repeatedly until Chrome extension is connected."""
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            try:
                res = self.call_tool("browser_snapshot", {})
                if res is not None:
                    return True
            except McpNotConnectedError:
                time.sleep(1.0)
            except Exception as err:
                if "No connection to browser extension" in str(err):
                    time.sleep(1.0)
                else:
                    raise
        raise McpNotConnectedError(
            "Ekstensi BrowserMCP belum terhubung setelah menunggu."
        )

    def peek_snapshot(self) -> str | None:
        """Read-only snapshot text for waiting loops; not counted against max_tool_calls."""
        try:
            res = self._send_request("tools/call", {"name": "browser_snapshot", "arguments": {}})
        except Exception:
            return None
        payload = res.get("result", {})
        if "error" in res or not isinstance(payload, dict) or payload.get("isError"):
            return None
        return " ".join(
            item.get("text", "") for item in payload.get("content", []) if isinstance(item, dict)
        )

    def hold_open(self, max_seconds: float, poll_seconds: float = 3.0) -> None:
        """Keep the server alive until the owner closes the page they were reviewing.

        In Playwright extension mode, closing the reviewed tab makes the extension
        reopen its relay tab (``chrome-extension://.../connect.html``). That page is
        a valid snapshot (no error), so an error-only check never fires and the relay
        keeps reopening the tab. Seeing the relay page means the real page is gone, so
        stop the server: the relay drops and the extension stops reopening the tab.
        """
        deadline = time.time() + max_seconds
        while time.time() < deadline:
            time.sleep(poll_seconds)
            try:
                res = self._send_request("tools/call", {"name": "browser_snapshot", "arguments": {}})
            except Exception:
                self.stop()
                return
            payload = res.get("result", {})
            if "error" in res or (isinstance(payload, dict) and payload.get("isError")):
                self.stop()
                return
            text = " ".join(
                item.get("text", "")
                for item in payload.get("content", [])
                if isinstance(item, dict)
            )
            # The extension relay page only shows once the reviewed page is closed.
            if "chrome-extension://" in text and "/connect.html" in text:
                self.stop()
                return

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        if name not in ALLOWED_TOOLS:
            raise McpClientError(f"Tool {name} is not in allowed tools list")

        if self.tool_call_count >= self.max_tool_calls:
            raise McpClientError("Maximum tool call limit reached")

        # Enforce element and ref requirement for targeting tools
        if name in ELEMENT_REQUIRING_TOOLS:
            if not args.get("element") or not args.get("ref"):
                raise McpClientError(
                    f"Tool {name} requires 'element' and 'ref' arguments"
                )

        self.tool_call_count += 1
        sanitized_args = dict(args)

        if name in ELEMENT_REQUIRING_TOOLS and self._ref_arg != "ref":
            sanitized_args[self._ref_arg] = sanitized_args.pop("ref")

        if name == "browser_type":
            sanitized_args["submit"] = False  # Always force submit=False

        elif name == "browser_press_key":
            key = str(sanitized_args.get("key", ""))
            if key not in ALLOWED_KEYS:
                raise McpClientError(f"Key '{key}' is not allowed via press_key")

        elif name == "browser_navigate":
            url = str(sanitized_args.get("url", ""))
            host = urlparse(url).netloc
            if self.allowed_hosts and host not in self.allowed_hosts:
                raise McpClientError(f"Navigation to host '{host}' is forbidden")

        res = self._send_request(
            "tools/call",
            {"name": name, "arguments": sanitized_args},
        )

        if "error" in res:
            err_msg = res["error"].get("message", str(res["error"]))
            raise McpClientError(f"MCP tool error: {err_msg}")

        result_payload = res.get("result", {})
        if isinstance(result_payload, dict) and result_payload.get("isError"):
            content_list = result_payload.get("content", [])
            err_text = ""
            if content_list and isinstance(content_list, list):
                first_item = content_list[0]
                if isinstance(first_item, dict):
                    err_text = first_item.get("text", "")
            if not err_text:
                err_text = "BrowserMCP returned isError without text"

            if "no connection to browser extension" in err_text.lower():
                raise McpNotConnectedError(err_text)
            raise McpClientError(err_text)

        return result_payload

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            return
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        json_line = json.dumps(msg) + "\n"
        try:
            self.process.stdin.write(json_line)
            self.process.stdin.flush()
        except Exception:
            pass

    def _send_request(
        self, method: str, params: dict[str, Any], timeout: float | None = None
    ) -> dict[str, Any]:
        if not self.process or not self.process.stdin:
            raise McpClientError("MCP process not running")

        self._request_id += 1
        req_id = self._request_id
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        json_line = json.dumps(msg) + "\n"

        try:
            self.process.stdin.write(json_line)
            self.process.stdin.flush()
        except Exception as err:
            recent_err = " | ".join(list(self._stderr_buffer)[-5:])
            raise McpClientError(
                f"Writing to MCP stdin failed: {err}. Stderr: {recent_err}"
            ) from err

        wait_timeout = timeout or self.timeout
        start_time = time.monotonic()

        while True:
            elapsed = time.monotonic() - start_time
            remaining = wait_timeout - elapsed
            if remaining <= 0:
                recent_err = " | ".join(list(self._stderr_buffer)[-5:])
                raise McpClientError(f"MCP request timeout. Stderr: {recent_err}")

            try:
                line = self._stdout_queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if self.process.poll() is not None:
                    recent_err = " | ".join(list(self._stderr_buffer)[-5:])
                    raise McpClientError(
                        f"MCP process terminated unexpectedly (code {self.process.returncode}). Stderr: {recent_err}"
                    )
                continue

            try:
                res = json.loads(line)
                if isinstance(res, dict) and res.get("id") == req_id:
                    return res
            except Exception:
                continue
