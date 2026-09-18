"""Safe local entrypoint for the application scaffold."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from collections.abc import Sequence

from .config import Settings
from .database import initialize_database
from .remoteok import RemoteOKFetcher
from .remotive import RemotiveFetcher
from .scheduler import JobScheduler


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bot-loker-wfh service.")
    parser.add_argument("--version", action="version", version="0.1.0")
    parser.add_argument(
        "command",
        choices=(
            "start",
            "init-db",
            "fetch-remoteok",
            "fetch-remotive",
            "fetch-once",
            "run-scheduler",
        ),
        default="start",
        nargs="?",
        help="Command to run. Defaults to safe local startup.",
    )
    args = parser.parse_args(argv)

    settings = Settings.from_environment()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "init-db":
        database_path = initialize_database(settings.database_url)
        print(f"database initialized path={database_path}")
        return 0

    if args.command == "fetch-remoteok":
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            inserted_count = RemoteOKFetcher(connection).fetch_and_store()
        print(f"remoteok fetch complete inserted={inserted_count}")
        return 0

    if args.command == "fetch-remotive":
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            inserted_count = RemotiveFetcher(connection).fetch_and_store()
        print(f"remotive fetch complete inserted={inserted_count}")
        return 0

    if args.command == "fetch-once":
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            results = JobScheduler(connection).run_once()
        print(
            "fetch once complete "
            + " ".join(
                f"{source}_inserted={inserted}" for source, inserted in results.items()
            )
        )
        return 0

    if args.command == "run-scheduler":
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            JobScheduler(connection).run_forever()
        return 0

    print(
        "bot-loker-wfh started "
        f"environment={settings.environment} "
        f"external_jobs_enabled={str(settings.external_jobs_enabled).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
