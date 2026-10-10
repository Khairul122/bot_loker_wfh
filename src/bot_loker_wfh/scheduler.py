"""MVP scheduler for periodic job sourcing."""

from __future__ import annotations

import logging
from .database import Connection
import time
from collections.abc import Callable
from time import perf_counter

from .greenhouse import GreenhouseFetcher
from .indonesia_jobs import DeallsFetcher, KalibrrFetcher
from .lever import LeverFetcher
from .logging_utils import StructuredLogger, sanitize_error
from .remoteok import RemoteOKFetcher
from .remotive import RemotiveFetcher


MIN_INTERVAL_SECONDS = 5 * 60  # hard floor regardless of source
FetchFn = Callable[[], int]
IntervalSource = float | Callable[[], float]


class JobScheduler:
    def __init__(
        self,
        connection: Connection,
        *,
        fetchers: dict[str, FetchFn] | None = None,
        interval_hours: IntervalSource = 4,
        logger: logging.Logger | None = None,
        raise_on_error: bool = True,
    ) -> None:
        self.connection = connection
        self.fetchers = fetchers if fetchers is not None else _default_fetchers(connection)
        self._interval_hours = interval_hours
        self.raise_on_error = raise_on_error
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))

    def interval_seconds(self) -> int:
        hours = self._interval_hours() if callable(self._interval_hours) else self._interval_hours
        return max(int(float(hours) * 60 * 60), MIN_INTERVAL_SECONDS)

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
            time.sleep(self.interval_seconds())


def _default_fetchers(connection: Connection) -> dict[str, FetchFn]:
    return {
        "remoteok": RemoteOKFetcher(connection).fetch_and_store,
        "remotive": RemotiveFetcher(connection).fetch_and_store,
        "greenhouse": GreenhouseFetcher(connection).fetch_and_store,
        "lever": LeverFetcher(connection).fetch_and_store,
        "kalibrr": KalibrrFetcher(connection).fetch_and_store,
        "dealls": DeallsFetcher(connection).fetch_and_store,
    }

