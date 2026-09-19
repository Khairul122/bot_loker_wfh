"""MVP scheduler for periodic job sourcing."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from time import perf_counter

from .greenhouse import GreenhouseFetcher
from .lever import LeverFetcher
from .logging_utils import StructuredLogger, sanitize_error
from .remoteok import RemoteOKFetcher
from .remotive import RemotiveFetcher


MIN_INTERVAL_SECONDS = 4 * 60 * 60
FetchFn = Callable[[], int]


class JobScheduler:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fetchers: dict[str, FetchFn] | None = None,
        interval_hours: float = 4,
        logger: logging.Logger | None = None,
        raise_on_error: bool = True,
    ) -> None:
        interval_seconds = int(interval_hours * 60 * 60)
        if interval_seconds < MIN_INTERVAL_SECONDS:
            raise ValueError("Scheduler interval must be at least four hours")
        self.connection = connection
        self.fetchers = fetchers if fetchers is not None else _default_fetchers(connection)
        self.interval_seconds = interval_seconds
        self.raise_on_error = raise_on_error
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))

    def run_once(self) -> dict[str, int]:
        results: dict[str, int] = {}
        for source, fetch in self.fetchers.items():
            started_at = perf_counter()
            try:
                inserted_count = fetch()
            except Exception as error:
                self.logger.error(
                    "fetch_failed",
                    source=source,
                    status="error",
                    duration_ms=int((perf_counter() - started_at) * 1000),
                    error_code=sanitize_error(error),
                )
                if self.raise_on_error:
                    raise
                continue
            results[source] = inserted_count
            self.logger.event(
                "fetch_complete",
                source=source,
                status="success",
                duration_ms=int((perf_counter() - started_at) * 1000),
                inserted_count=inserted_count,
            )
        return results

    def run_forever(self) -> None:
        while True:
            self.run_once()
            time.sleep(self.interval_seconds)


def _default_fetchers(connection: sqlite3.Connection) -> dict[str, FetchFn]:
    return {
        "remoteok": RemoteOKFetcher(connection).fetch_and_store,
        "remotive": RemotiveFetcher(connection).fetch_and_store,
        "greenhouse": GreenhouseFetcher(connection).fetch_and_store,
        "lever": LeverFetcher(connection).fetch_and_store,
    }

