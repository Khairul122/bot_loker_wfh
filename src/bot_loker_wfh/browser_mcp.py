"""BrowserMCP client with safety guards enforcing strict execution policies."""

from __future__ import annotations

import json
import subprocess
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


class McpClientError(RuntimeError):
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

    def start(self) -> None:
        if self.process is not None:
            return
        args = self.command.split()
        try:
            self.process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as err:
            raise McpClientError(f"Failed to start MCP process: {err}") from err

        # Perform JSON-RPC initialize handshakes if process is active
        init_res = self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bot-loker-wfh", "version": "0.1.0"},
            },
        )
        if not init_res:
            raise McpClientError("MCP server failed to initialize")

    def stop(self) -> None:
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                pass
            self.process = None

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        if name not in ALLOWED_TOOLS:
            raise McpClientError(f"Tool {name} is not in allowed tools list")

        if self.tool_call_count >= self.max_tool_calls:
            raise McpClientError("Maximum tool call limit reached")

        self.tool_call_count += 1

        # Enforce safety constraints
        sanitized_args = dict(args)

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
            raise McpClientError(f"MCP tool error: {res['error']}")

        return res.get("result", {})

    def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.process or not self.process.stdin or not self.process.stdout:
            # Fallback mock/fake mode for offline tests
            return {"result": {}}

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
            raise McpClientError(f"Writing to MCP stdin failed: {err}") from err

        start_time = time.monotonic()
        while True:
            if time.monotonic() - start_time > 15.0:
                raise McpClientError("MCP request timeout")
            line = self.process.stdout.readline()
            if not line:
                raise McpClientError("MCP process stdout closed unexpectedly")
            try:
                res = json.loads(line)
                if isinstance(res, dict) and res.get("id") == req_id:
                    return res
            except Exception:
                continue
