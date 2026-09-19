"""Minimal Telegram Bot API client built on the standard library."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .telegram_notifications import TelegramMessage


API_BASE = "https://api.telegram.org"
MAX_TEXT_LENGTH = 4000


class TelegramError(RuntimeError):
    """Raised for API or network failures; never carries the bot token."""


class TelegramClient:
    def __init__(self, token: str, *, request_timeout: float = 40.0) -> None:
        if not token:
            raise ValueError("Telegram bot token is required")
        self._token = token
        self.request_timeout = request_timeout

    def get_updates(
        self, offset: int | None, *, timeout: int = 30
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload)

    def send_text(
        self,
        chat_id: int,
        text: str,
        keyboard: tuple[tuple[tuple[str, str], ...], ...] = (),
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:MAX_TEXT_LENGTH],
            "disable_web_page_preview": True,
        }
        if keyboard:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": label, "callback_data": data} for label, data in row]
                    for row in keyboard
                ]
            }
        self._call("sendMessage", payload)

    def send_message(self, message: TelegramMessage) -> None:
        self.send_text(
            message.chat_id,
            message.text,
            tuple(
                tuple((button.label, button.callback_data) for button in row)
                for row in message.inline_keyboard
            ),
        )

    def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        """Replace a message's text; omitting reply_markup also removes its buttons."""
        self._call(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text[:MAX_TEXT_LENGTH],
                "disable_web_page_preview": True,
            },
        )

    def answer_callback(self, callback_query_id: str, text: str = "") -> None:
        self._call(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text[:200]},
        )

    def _call(self, method: str, payload: dict[str, Any]) -> Any:
        request = Request(
            f"{API_BASE}/bot{self._token}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.request_timeout) as response:
                body = json.load(response)
        except (URLError, OSError, ValueError) as error:
            raise TelegramError(
                f"telegram {method} failed: {type(error).__name__}"
            ) from None
        if not body.get("ok"):
            raise TelegramError(f"telegram {method} rejected the request")
        return body.get("result")
