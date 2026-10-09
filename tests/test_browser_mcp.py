"""Unit tests for McpBrowserClient security policy and tool filtering."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from bot_loker_wfh.browser_mcp import (
    McpBrowserClient,
    McpClientError,
    McpNotConnectedError,
)


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
            client.call_tool("browser_type", {"element": "input", "ref": "e1", "text": "test", "submit": True})

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

    def test_is_error_raises_mcp_not_connected_error(self):
        client = McpBrowserClient()
        mock_res = {
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": "No connection to browser extension"}],
            }
        }
        with patch.object(client, "_send_request", return_value=mock_res):
            with self.assertRaises(McpNotConnectedError):
                client.call_tool("browser_snapshot", {})

    def test_wait_for_extension_retry(self):
        client = McpBrowserClient()
        err_res = {
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": "No connection to browser extension"}],
            }
        }
        ok_res = {"result": {"content": [{"type": "text", "text": "Snapshot ok"}]}}

        with patch.object(client, "_send_request", side_effect=[err_res, ok_res]):
            success = client.wait_for_extension(timeout=5.0)
            self.assertTrue(success)

    def test_stop_kills_whole_process_tree(self):
        import os

        client = McpBrowserClient()
        proc = MagicMock()
        proc.pid = 4242
        client.process = proc

        with patch("bot_loker_wfh.browser_mcp.subprocess.run") as run:
            client.stop()

        if os.name == "nt":
            run.assert_called_once()
            self.assertIn("/T", run.call_args[0][0])
        else:
            run.assert_not_called()
        self.assertIsNone(client.process)
        proc.wait.assert_called_once()


class TargetArgumentTest(unittest.TestCase):
    def test_ref_is_sent_as_target_for_playwright_mcp(self):
        from bot_loker_wfh.browser_mcp import McpBrowserClient

        client = McpBrowserClient()
        client._ref_arg = "target"
        sent = []
        client._send_request = lambda method, params, timeout=None: sent.append(params) or {"result": {"content": []}}
        client.call_tool("browser_type", {"element": "Proposal", "ref": "e5", "text": "hi", "submit": True})
        self.assertEqual(sent[0]["arguments"], {"element": "Proposal", "target": "e5", "text": "hi", "submit": False})
