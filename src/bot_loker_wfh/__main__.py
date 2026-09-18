"""Safe local entrypoint for the application scaffold."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from .backup import backup_database, restore_database
from .config import Settings
from .database import initialize_database
from .remoteok import RemoteOKFetcher
from .remotive import RemotiveFetcher
from .retention import FilteredOutRetention
from .scheduler import JobScheduler


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bot-loker-wfh service.")
    parser.add_argument("--version", action="version", version="0.1.0")
    parser.add_argument("--backup-path", help="Path for backup-db output")
    parser.add_argument("--restore-path", help="Path for restore-db input")
    parser.add_argument("--target-db", help="Target SQLite path for restore-db")
    parser.add_argument(
        "command",
        choices=(
            "start",
            "init-db",
            "fetch-remoteok",
            "fetch-remotive",
            "fetch-once",
            "run-scheduler",
            "cleanup-retention",
            "backup-db",
            "restore-db",
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

    if args.command == "cleanup-retention":
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            deleted_count = FilteredOutRetention(connection).cleanup()
        print(f"retention cleanup complete deleted={deleted_count}")
        return 0

    if args.command == "backup-db":
        database_path = initialize_database(settings.database_url)
        backup_path = Path(args.backup_path or "backups/app.sqlite")
        backup_database(database_path, backup_path)
        print(f"database backup complete path={backup_path}")
        return 0

    if args.command == "restore-db":
        if not args.restore_path:
            parser.error("restore-db requires --restore-path")
        target_path = Path(args.target_db) if args.target_db else None
        if target_path is None:
            from .database import sqlite_path_from_url

            target_path = sqlite_path_from_url(settings.database_url)
        restore_database(Path(args.restore_path), target_path)
        print(f"database restore complete path={target_path}")
        return 0

    print(
        "bot-loker-wfh started "
        f"environment={settings.environment} "
        f"external_jobs_enabled={str(settings.external_jobs_enabled).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
