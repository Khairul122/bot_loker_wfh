"""Safe local entrypoint for the application scaffold."""

from __future__ import annotations

import argparse
import logging
import sqlite3
import uuid
from collections.abc import Sequence
from pathlib import Path

from .backup import backup_database, restore_database
from .bot import BotRunner
from .config import Settings
from .cv_profile import load_profile
from .database import initialize_database
from .drafts import DraftService
from .greenhouse import GreenhouseFetcher
from .lever import LeverFetcher
from .llm import AnthropicProvider
from .pipeline import JobPipeline
from .remoteok import RemoteOKFetcher
from .remotive import RemotiveFetcher
from .retention import FilteredOutRetention
from .scheduler import JobScheduler
from .telegram_client import TelegramClient


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bot-loker-wfh service.")
    parser.add_argument("--version", action="version", version="0.1.0")
    parser.add_argument("--backup-path", help="Path for backup-db output")
    parser.add_argument("--restore-path", help="Path for restore-db input")
    parser.add_argument("--target-db", help="Target SQLite path for restore-db")
    parser.add_argument("--ats", choices=("greenhouse", "lever"), help="ATS for add-company")
    parser.add_argument("--slug", help="ATS board slug for add-company")
    parser.add_argument("--name", help="Company display name for add-company")
    parser.add_argument("--application-id", help="Application ID for fill-form")
    parser.add_argument(
        "command",
        choices=(
            "start",
            "init-db",
            "fetch-remoteok",
            "fetch-remotive",
            "fetch-greenhouse",
            "fetch-lever",
            "fetch-once",
            "run-scheduler",
            "run-bot",
            "process-jobs",
            "add-company",
            "fill-form",
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

    if args.command == "fetch-greenhouse":
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            inserted_count = GreenhouseFetcher(connection).fetch_and_store()
        print(f"greenhouse fetch complete inserted={inserted_count}")
        return 0

    if args.command == "fetch-lever":
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            inserted_count = LeverFetcher(connection).fetch_and_store()
        print(f"lever fetch complete inserted={inserted_count}")
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
        if not settings.external_jobs_enabled:
            print("EXTERNAL_JOBS_ENABLED is false; scheduler not started")
            return 1
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            JobScheduler(connection).run_forever()
        return 0

    if args.command == "process-jobs":
        database_path = initialize_database(settings.database_url)
        profile = load_profile(settings.profile_path)
        with sqlite3.connect(database_path) as connection:
            counts = JobPipeline(connection, profile).process_discovered()
        print(
            "process complete "
            + " ".join(f"{key}={value}" for key, value in counts.items())
        )
        return 0

    if args.command == "add-company":
        if not (args.ats and args.slug and args.name):
            parser.error("add-company requires --ats, --slug, and --name")
        database_path = initialize_database(settings.database_url)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO companies_ats "
                "(id, company_name, ats_type, ats_slug) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), args.name, args.ats, args.slug),
            )
            connection.commit()
        print(f"company registered ats={args.ats} slug={args.slug}")
        return 0

    if args.command == "run-bot":
        return _run_bot(settings)

    if args.command == "fill-form":
        if not args.application_id:
            parser.error("fill-form requires --application-id")
        return _fill_form(settings, args.application_id)

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


def _fill_form(settings: Settings, application_id: str) -> int:
    """Open the application form in a visible browser, fill it, never submit."""
    from .form_assist import (
        FormAssistError,
        load_answers,
        load_applicant,
        open_and_fill,
    )

    client = (
        TelegramClient(settings.telegram_bot_token)
        if settings.telegram_bot_token
        else None
    )

    def tell(text: str) -> None:
        print(text, flush=True)
        if client is None:
            return
        for chat_id in sorted(settings.telegram_allowed_chat_ids):
            try:
                client.send_text(chat_id, text)
            except Exception:
                pass

    database_path = initialize_database(settings.database_url)
    connection = sqlite3.connect(database_path)
    try:
        applicant = load_applicant(settings.applicant_path)
        answers = load_answers(settings.answers_path)
        open_and_fill(
            connection,
            application_id,
            applicant,
            answers,
            on_ready=lambda report: tell(
                report.to_text().replace("<id>", application_id)
            ),
        )
    except FormAssistError as error:
        tell(f"Gagal membuka form: {error}")
        return 1
    finally:
        connection.close()
    return 0


def _run_bot(settings: Settings) -> int:
    if not settings.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN is not set")
        return 1
    if not settings.telegram_allowed_chat_ids:
        print("TELEGRAM_ALLOWED_CHAT_IDS is not set")
        return 1
    try:
        profile = load_profile(settings.profile_path)
    except FileNotFoundError as error:
        print(error)
        return 1
    if not profile.skills:
        print("Profile has no skills; edit " + settings.profile_path)
        return 1

    database_path = initialize_database(settings.database_url)
    llm = (
        AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
        if settings.anthropic_api_key
        else None
    )
    connection = sqlite3.connect(database_path)
    scheduler = (
        JobScheduler(
            connection,
            interval_hours=settings.fetch_interval_hours,
            raise_on_error=False,
        )
        if settings.external_jobs_enabled
        else None
    )
    runner = BotRunner(
        connection,
        client=TelegramClient(settings.telegram_bot_token),
        allowed_chat_ids=settings.telegram_allowed_chat_ids,
        draft_service=DraftService(connection, profile, llm=llm),
        form_assist_enabled=settings.form_assist_enabled,
        pipeline=JobPipeline(connection, profile),
        scheduler=scheduler,
        interval_seconds=int(settings.fetch_interval_hours * 3600),
    )
    print(
        "bot running "
        f"external_jobs_enabled={str(settings.external_jobs_enabled).lower()} "
        f"llm={'anthropic' if llm else 'template'}"
    )
    try:
        runner.run_forever()
    except KeyboardInterrupt:
        print("bot stopped")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

