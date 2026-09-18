"""Telegram request authentication helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramRequest:
    chat_id: int
    text: str | None = None
    callback_data: str | None = None


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    safe_response: str | None = None


class TelegramAuth:
    def __init__(self, *, allowed_chat_ids: frozenset[int]):
        self.allowed_chat_ids = allowed_chat_ids

    def authorize(self, request: TelegramRequest) -> AuthDecision:
        if request.chat_id in self.allowed_chat_ids:
            return AuthDecision(allowed=True)
        return AuthDecision(allowed=False, safe_response="Unauthorized chat.")

