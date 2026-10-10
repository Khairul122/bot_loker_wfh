"""Safe local entrypoint for the application scaffold."""

from __future__ import annotations

import argparse
import logging
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path

from .bot import BotRunner
from .config import Settings
from .cv_profile import load_profile
from . import database
from .database import initialize_database
from .drafts import DraftService
from .greenhouse import GreenhouseFetcher
from .indonesia_jobs import DeallsFetcher, KalibrrFetcher
from .leads import (
    FreelancerFetcher,
    LeadService,
    PeoplePerHourFetcher,
    ProjectsCoIdFetcher,
    TelegramChannelFetcher,
)
from .lever import LeverFetcher
from .llm import create_chat_llm, create_llm_from_settings
from . import office_desk
from .office_server import hunt_jobs, hunt_leads, serve as serve_office
from .github_portfolio import load_portfolio, sync_portfolio
from .lead_desk import draft_comment, draft_proposal
from .office_work import OfficeWork
from .pipeline import JobPipeline
from .remoteok import RemoteOKFetcher
from .remotive import RemotiveFetcher
from .retention import FilteredOutRetention
from .scheduler import JobScheduler
from .settings_store import get_scrape_interval_hours
from .telegram_client import TelegramClient


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bot-loker-wfh service.")
    parser.add_argument("--version", action="version", version="0.1.0")
    parser.add_argument("--ats", choices=("greenhouse", "lever"), help="ATS for add-company")
    parser.add_argument("--slug", help="ATS board slug for add-company")
    parser.add_argument("--name", help="Company display name for add-company / add-ats")
    parser.add_argument("--host", help="ATS host name for add-ats / set-ats-mode")
    parser.add_argument("--mode", choices=("auto_fill", "assist"), help="Mode for add-ats / set-ats-mode")
    parser.add_argument("--open-button", help="Open button label for add-ats")
    parser.add_argument("--application-id", help="Application ID for fill-form")
    parser.add_argument("--force-assist", action="store_true", help="Force assist mode for fill-form")
    parser.add_argument("--next-page", action="store_true", help="Fill next page for multi-page form")
    parser.add_argument("--lead-id", help="Lead ID for fill-lead")
    parser.add_argument("--github-user", help="GitHub username for sync-github (default: GITHUB_USERNAME)")
    parser.add_argument("--engine", choices=("browsermcp", "playwright"), default="browsermcp",
                        help="Browser for fill-lead: your Chrome (BrowserMCP) or Playwright MCP")
    parser.add_argument("--text", choices=("proposal", "comment"), default="proposal",
                        help="Which saved draft fill-lead types into the page")
    parser.add_argument(
        "--submit-bid",
        action="store_true",
        help="Allow final bid submission after typing SUBMIT at the CLI prompt",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port for the office command")
    parser.add_argument(
        "command",
        choices=(
            "start",
            "init-db",
            "fetch-remoteok",
            "fetch-remotive",
            "fetch-greenhouse",
            "fetch-lever",
            "fetch-kalibrr",
            "fetch-dealls",
            "fetch-leads",
            "fetch-once",
            "run-scheduler",
            "run-bot",
            "process-jobs",
            "add-company",
            "fill-form",
            "fill-lead",
            "draft-lead",
            "sync-github",
            "cleanup-retention",
            "check-llm",
            "check-browser",
            "add-ats",
            "set-ats-mode",
            "list-ats",
            "office",
        ),
        default="start",
        nargs="?",
        help="Command to run. Defaults to safe local startup.",
    )
    args = parser.parse_args(argv)

    settings = Settings.from_environment()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "init-db":
        initialize_database()
        print("database initialized (supabase postgres)")
        return 0

    if args.command == "fetch-remoteok":
        initialize_database()
        with database.session() as connection:
            inserted_count = RemoteOKFetcher(connection).fetch_and_store()
        print(f"remoteok fetch complete inserted={inserted_count}")
        return 0

    if args.command == "fetch-remotive":
        initialize_database()
        with database.session() as connection:
            inserted_count = RemotiveFetcher(connection).fetch_and_store()
        print(f"remotive fetch complete inserted={inserted_count}")
        return 0

    if args.command == "fetch-greenhouse":
        initialize_database()
        with database.session() as connection:
            inserted_count = GreenhouseFetcher(connection).fetch_and_store()
        print(f"greenhouse fetch complete inserted={inserted_count}")
        return 0

    if args.command == "fetch-lever":
        initialize_database()
        with database.session() as connection:
            inserted_count = LeverFetcher(connection).fetch_and_store()
        print(f"lever fetch complete inserted={inserted_count}")
        return 0

    if args.command in {"fetch-kalibrr", "fetch-dealls"}:
        fetcher_class = KalibrrFetcher if args.command == "fetch-kalibrr" else DeallsFetcher
        initialize_database()
        with database.session() as connection:
            inserted_count = fetcher_class(connection).fetch_and_store()
        print(f"{fetcher_class.source} fetch complete inserted={inserted_count}")
        return 0

    if args.command == "fetch-leads":
        initialize_database()
        profile = load_profile(settings.profile_path)
        with database.session() as connection:
            counts = _lead_service(connection, profile, settings).collect()
        print(
            "leads fetch complete "
            + " ".join(f"{source}_new={count}" for source, count in counts.items())
        )
        return 0

    if args.command == "fetch-once":
        initialize_database()
        with database.session() as connection:
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
        initialize_database()
        with database.session() as connection:
            JobScheduler(
                connection,
                interval_hours=lambda: get_scrape_interval_hours(connection),
            ).run_forever()
        return 0

    if args.command == "process-jobs":
        initialize_database()
        profile = load_profile(settings.profile_path)
        with database.session() as connection:
            counts = JobPipeline(connection, profile).process_discovered()
        print(
            "process complete "
            + " ".join(f"{key}={value}" for key, value in counts.items())
        )
        return 0

    if args.command == "add-company":
        if not (args.ats and args.slug and args.name):
            parser.error("add-company requires --ats, --slug, and --name")
        initialize_database()
        with database.session() as connection:
            connection.execute(
                "INSERT INTO companies_ats "
                "(id, company_name, ats_type, ats_slug) VALUES (?, ?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (str(uuid.uuid4()), args.name, args.ats, args.slug),
            )
            connection.commit()
        print(f"company registered ats={args.ats} slug={args.slug}")
        return 0

    if args.command == "run-bot":
        return _run_bot(settings)

    if args.command == "sync-github":
        username = args.github_user or settings.github_username
        if not username:
            parser.error("sync-github needs --github-user or GITHUB_USERNAME")
        data = sync_portfolio(username)
        print(f"github portfolio saved repos={len(data['repos'])} path=data/github_portfolio.json")
        return 0

    if args.command == "fill-lead":
        if not args.lead_id:
            parser.error("fill-lead requires --lead-id")
        return _fill_lead(
            settings,
            args.lead_id,
            args.engine,
            args.text,
            submit=getattr(args, "submit_bid", False),
        )

    if args.command == "draft-lead":
        if not args.lead_id:
            parser.error("draft-lead requires --lead-id")
        profile = load_profile(settings.profile_path)
        initialize_database()
        llm = create_llm_from_settings(settings, record_calls=True)
        portfolio = load_portfolio()
        with database.session() as connection:
            try:
                proposal = draft_proposal(connection, args.lead_id, profile, llm, portfolio=portfolio)
                comment = draft_comment(connection, args.lead_id, llm, portfolio=portfolio)
            except KeyError:
                print(f"lead not found id={args.lead_id}")
                return 1
        print(f"--- proposal ---\n{proposal}\n\n--- comment ---\n{comment}")
        return 0

    if args.command == "fill-form":
        if not args.application_id:
            parser.error("fill-form requires --application-id")
        return _fill_form(
            settings,
            args.application_id,
            force_assist=getattr(args, "force_assist", False),
            next_page=getattr(args, "next_page", False),
        )

    if args.command == "check-llm":
        from .llm import OpenAICompatibleProvider, LLMError
        prov = OpenAICompatibleProvider(
            settings.ninerouter_base_url,
            settings.ninerouter_api_key or "sk-dummy",
            settings.ninerouter_model or "LokerHouse",
        )
        try:
            models = prov.list_models()
            print(f"9Router terhubung. {len(models)} model tersedia.")
            test_res = prov.complete([{"role": "user", "content": "Tes satu kata."}])
            print(f"Uji model '{test_res.model}': {test_res.text[:50]}")
            return 0
        except LLMError as err:
            if err.code == "unauthorized":
                print("API key 9Router ditolak (401)")
                return 1
            print(f"9Router error: {err}")
            return 1
        except Exception as err:
            print(f"Koneksi 9Router gagal: {err}")
            return 1

    if args.command == "check-browser":
        import socket
        from .browser_mcp import McpBrowserClient

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        port_in_use = False
        try:
            sock.connect(("127.0.0.1", 9009))
            port_in_use = True
        except Exception:
            port_in_use = False
        finally:
            sock.close()

        if port_in_use:
            print("PERINGATAN: Port 9009 sudah digunakan (mungkin oleh instance BrowserMCP lain, Cursor, atau Claude Desktop).")

        client = McpBrowserClient(command=settings.browser_mcp_command)
        try:
            client.start()
            print(f"BrowserMCP berhasil start dengan perintah: {settings.browser_mcp_command}")
            client.stop()
            return 0
        except Exception as err:
            print(f"BrowserMCP gagal: {err}")
            return 1

    if args.command == "add-ats":
        if not (args.name and args.host):
            parser.error("add-ats requires --name and --host")
        initialize_database()
        with database.session() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO ats_registry (id, ats_name, host, mode, open_button_label) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    args.name,
                    args.host,
                    args.mode or "assist",
                    args.open_button,
                ),
            )
            connection.commit()
        print(f"ATS terdaftar: {args.name} ({args.host}) mode={args.mode or 'assist'}")
        return 0

    if args.command == "set-ats-mode":
        if not (args.host and args.mode):
            parser.error("set-ats-mode requires --host and --mode")
        initialize_database()
        with database.session() as connection:
            connection.execute(
                "UPDATE ats_registry SET mode = ? WHERE host = ?",
                (args.mode, args.host),
            )
            connection.commit()
        print(f"Mode ATS untuk {args.host} diubah menjadi {args.mode}")
        return 0

    if args.command == "list-ats":
        initialize_database()
        with database.session() as connection:
            rows = connection.execute(
                "SELECT ats_name, host, mode, open_button_label, active FROM ats_registry ORDER BY ats_name"
            ).fetchall()
        for r in rows:
            print(f"- {r[0]} | host: {r[1]} | mode: {r[2]} | open_button: {r[3] or '-'} | active: {bool(r[4])}")
        return 0

    if args.command == "office":
        profile = load_profile(settings.profile_path)
        initialize_database()
        llm = create_llm_from_settings(settings, record_calls=True)
        work = OfficeWork(
            hunters=_office_hunters(profile, settings),
            # Cora writes with the owner's standing instruction appended to every prompt
            draft_service_for=lambda connection: DraftService(
                connection, profile, llm=office_desk.instructed(llm, connection, "cora")
            ),
            proposal_writer=lambda connection, lead_id, mark_interested=True: draft_proposal(
                connection, lead_id, profile, office_desk.instructed(llm, connection, "cora"),
                portfolio=load_portfolio(), mark_interested=mark_interested,
            ),
            screener=_office_screener(profile),
            llm=create_chat_llm(settings, record_calls=True),  # Q&A needs seconds, not an agent run
            notify=_owner_notifier(settings),
            form_assist_enabled=settings.form_assist_enabled,
            # scrape interval lives in the DB so the owner can tune it live from the dashboard
            interval_seconds=lambda: _read_scrape_interval(),
            lock=threading.Lock(),
        )
        serve_office(work, args.port)
        return 0

    if args.command == "cleanup-retention":
        initialize_database()
        with database.session() as connection:
            deleted_count = FilteredOutRetention(connection).cleanup()
        print(f"retention cleanup complete deleted={deleted_count}")
        return 0

    print(
        "bot-loker-wfh started "
        f"environment={settings.environment} "
        f"external_jobs_enabled={str(settings.external_jobs_enabled).lower()}"
    )
    return 0


def _office_screener(profile):
    """Sari scores the queue and Eli drops the ineligible rows; both counts reach the log."""

    def screen(connection):
        counts = JobPipeline(connection, profile).process_discovered()
        return {"matched": counts["candidate"], "filtered_out": counts["filtered_out"]}

    return screen


def _office_hunters(profile, settings: Settings) -> dict:
    """Real searches the 3D office can trigger, one per employee."""
    job_fetchers = {
        "remoteok": RemoteOKFetcher,
        "remotive": RemotiveFetcher,
        "greenhouse": GreenhouseFetcher,
        "lever": LeverFetcher,
        "kalibrr": KalibrrFetcher,
        "dealls": DeallsFetcher,
    }
    hunters = {
        source: (
            lambda connection, source=source, fetcher_class=fetcher_class: hunt_jobs(
                connection, source, fetcher_class(connection), JobPipeline(connection, profile)
            )
        )
        for source, fetcher_class in job_fetchers.items()
    }
    lead_fetchers = [FreelancerFetcher(), ProjectsCoIdFetcher(), PeoplePerHourFetcher()]  # global + Indonesia
    if settings.lead_telegram_channels:
        lead_fetchers.append(TelegramChannelFetcher(settings.lead_telegram_channels))
    for fetcher in lead_fetchers:
        hunters[fetcher.source] = (
            lambda connection, fetcher=fetcher: hunt_leads(
                connection, LeadService(connection, profile, fetchers=[fetcher]), fetcher.source
            )
        )
    return hunters


def _owner_notifier(settings: Settings):
    """Send text to every allowed Telegram chat, or None when Telegram is not configured."""
    if not settings.telegram_bot_token or not settings.telegram_allowed_chat_ids:
        return None
    client = TelegramClient(settings.telegram_bot_token)

    def notify(text: str) -> None:
        for chat_id in sorted(settings.telegram_allowed_chat_ids):
            client.send_text(chat_id, text)

    return notify


def _read_scrape_interval() -> float:
    with database.session() as connection:
        return get_scrape_interval_hours(connection) * 3600


def _lead_service(connection, profile, settings: Settings) -> LeadService:
    fetchers = [FreelancerFetcher(), ProjectsCoIdFetcher(), PeoplePerHourFetcher()]
    if settings.lead_telegram_channels:
        fetchers.append(TelegramChannelFetcher(settings.lead_telegram_channels))
    return LeadService(connection, profile, fetchers=fetchers)


def _fill_form(
    settings: Settings,
    application_id: str,
    force_assist: bool = False,
    next_page: bool = False,
) -> int:
    """Open the application form in a visible browser, fill it, never submit."""
    from .form_assist import (
        FormAssistError,
        load_answers,
        load_applicant,
        open_and_fill,
    )
    from .form_agent.agent import FormAgent
    from .llm import create_llm_from_settings

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

    initialize_database()
    connection = database.connect()
    try:
        if settings.form_engine == "browsermcp":
            router = create_llm_from_settings(settings, record_calls=True)
            agent = FormAgent(
                connection,
                router=router,
                browser_command=settings.browser_mcp_command,
                min_confidence=settings.form_min_confidence,
                max_actions=settings.form_max_actions,
                max_tool_calls=settings.form_max_tool_calls,
                timeout_seconds=settings.form_timeout_seconds,
                applicant_path=settings.applicant_path,
                answers_path=settings.answers_path,
                persist_reports=True,
                ai_answers=settings.form_ai_answers != "off",
            )
            page_num = 2 if next_page else 1
            report_text = agent.run_session(
                application_id, page_number=page_num, force_assist=force_assist
            )
            tell(report_text)
        else:
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
    except Exception as error:
        tell(f"Error pengisian form: {error}")
        return 1
    finally:
        connection.close()
    return 0


# How long a Playwright MCP browser stays open for the owner to review and submit.
PLAYWRIGHT_REVIEW_SECONDS = 30 * 60


def _fill_lead(
    settings: Settings,
    lead_id: str,
    engine: str,
    text: str = "proposal",
    *,
    submit: bool = False,
) -> int:
    """Fill bid form; final submit requires --submit-bid and SUBMIT confirmation."""
    from .form_agent.agent import FormAgent

    initialize_database()
    connection = database.connect()
    try:
        agent = FormAgent(
            connection,
            router=create_llm_from_settings(settings, record_calls=True),
            browser_command=(
                settings.playwright_mcp_command if engine == "playwright" else settings.browser_mcp_command
            ),
            min_confidence=settings.form_min_confidence,
            max_actions=settings.form_max_actions,
            max_tool_calls=settings.form_max_tool_calls,
            timeout_seconds=settings.form_timeout_seconds,
            applicant_path=settings.applicant_path,
            answers_path=settings.answers_path,
            persist_reports=True,
            ai_answers=settings.form_ai_answers != "off",
        )
        keep_open = 0 if submit else PLAYWRIGHT_REVIEW_SECONDS if engine == "playwright" else 0

        def confirm_submit(label: str) -> bool:
            print(
                f"Akan klik tombol final: {label!r}. "
                "Periksa semua field. Ketik SUBMIT untuk kirim bid: ",
                end="",
                flush=True,
            )
            return input().strip() == "SUBMIT"

        print(
            agent.run_lead_session(
                lead_id,
                keep_open_seconds=keep_open,
                text=text,
                submit=submit,
                confirm_submit=confirm_submit if submit else None,
            ),
            flush=True,
        )
    except Exception as error:
        print(f"Error pengisian form proyek: {error}", flush=True)
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

    initialize_database()
    llm = create_llm_from_settings(settings, record_calls=True)
    connection = database.connect()

    def scrape_interval_hours() -> float:
        return get_scrape_interval_hours(connection)

    scheduler = (
        JobScheduler(
            connection,
            interval_hours=scrape_interval_hours,
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
        lead_service=_lead_service(connection, profile, settings),
        pipeline=JobPipeline(connection, profile),
        scheduler=scheduler,
        interval_seconds=lambda: get_scrape_interval_hours(connection) * 3600,
    )
    print(
        "bot running "
        f"external_jobs_enabled={str(settings.external_jobs_enabled).lower()} "
        f"llm={settings.llm_provider} "
        f"form_engine={settings.form_engine}"
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

