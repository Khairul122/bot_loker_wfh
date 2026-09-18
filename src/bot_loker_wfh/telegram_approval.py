"""Idempotent Telegram approval and rejection handling."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .status_transitions import (
    InvalidTransitionError,
    TransitionActor,
    transition_application_status,
)
from .telegram_auth import TelegramAuth, TelegramRequest


@dataclass(frozen=True)
class ApprovalResult:
    success: bool
    message: str


class TelegramApprovalHandler:
    def __init__(self, connection: sqlite3.Connection, *, auth: TelegramAuth):
        self.connection = connection
        self.auth = auth

    def handle(self, request: TelegramRequest) -> ApprovalResult:
        decision = self.auth.authorize(request)
        if not decision.allowed:
            return ApprovalResult(False, decision.safe_response or "Unauthorized chat.")

        try:
            action, application_id, expected_status = _parse_callback(
                request.callback_data
            )
        except ValueError:
            return ApprovalResult(False, "Invalid approval request.")

        current_status = self._current_status(application_id)
        if current_status is None or current_status != expected_status:
            return ApprovalResult(False, "This approval request is no longer active.")

        target_status = {
            "approve": "APPROVED",
            "reject": "REJECTED_BY_USER",
        }[action]
        try:
            transition_application_status(
                self.connection,
                application_id=application_id,
                to_status=target_status,
                actor=TransitionActor.USER,
            )
        except InvalidTransitionError:
            return ApprovalResult(False, "This approval request is no longer active.")

        message = "Application approved." if action == "approve" else "Application rejected."
        return ApprovalResult(True, message)

    def _current_status(self, application_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()
        return row[0] if row else None


def _parse_callback(callback_data: str | None) -> tuple[str, str, str]:
    if not callback_data:
        raise ValueError("callback data is required")
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] not in {"approve", "reject"}:
        raise ValueError("invalid callback data")
    if not parts[1] or not parts[2]:
        raise ValueError("invalid callback data")
    return parts[0], parts[1], parts[2]

