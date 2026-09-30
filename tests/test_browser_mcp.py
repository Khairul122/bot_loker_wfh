"""Unit tests for McpBrowserClient security policy and tool filtering."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from bot_loker_wfh.browser_mcp import McpBrowserClient, McpClientError


class TestBrowserMCP(unittest.TestCase):
    def test_forbidden_tool_rejected(self):
        client = McpBrowserClient()
        with self.assertRaises(McpClientError) as ctx:
            client.call_tool("browser_eval", {"code": "alert(1)"})
        self.assertIn("not in allowed tools", str(ctx.exception))

    def test_type_tool_forces_submit_false(self):
        client = McpBrowserClient()
        mock_send = MagicMock(return_value={"result": {"status": "ok"}})
        with patch.object(client, "_send_request", mock_send):
            client.call_tool("browser_type", {"ref": "e1", "text": "test", "submit": True})

        msg_params = mock_send.call_args[0][1]
        self.assertFalse(msg_params["arguments"]["submit"])

    def test_press_key_restricts_keys(self):
        client = McpBrowserClient()
        with self.assertRaises(McpClientError) as ctx:
            client.call_tool("browser_press_key", {"key": "Enter"})
        self.assertIn("not allowed", str(ctx.exception))

        mock_send = MagicMock(return_value={"result": {}})
        with patch.object(client, "_send_request", mock_send):
            client.call_tool("browser_press_key", {"key": "Tab"})
            mock_send.assert_called_once()

    def test_navigate_host_restriction(self):
        client = McpBrowserClient(allowed_hosts={"jobs.lever.co"})

        with self.assertRaises(McpClientError) as ctx:
            client.call_tool("browser_navigate", {"url": "https://phishing.site/form"})
        self.assertIn("forbidden", str(ctx.exception))

        mock_send = MagicMock(return_value={"result": {}})
        with patch.object(client, "_send_request", mock_send):
            client.call_tool("browser_navigate", {"url": "https://jobs.lever.co/company/job-1"})
            mock_send.assert_called_once()
