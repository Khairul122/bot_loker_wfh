# Bot Loker WFH

Bot personal untuk membantu sourcing, filtering, review, dan tracking lowongan kerja remote internasional.

## Setup

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Dependency manager: `pip` using `pyproject.toml`. Runtime dependencies are intentionally empty in the scaffold. Development tests use `pytest` when installed; the smoke test also runs with Python's standard-library `unittest`.

Copy `.env.example` to `.env` and adjust values only when needed. External jobs are disabled by default so starting the application never calls a jobs API.

Telegram control is restricted by allowlisted chat IDs. Set `TELEGRAM_BOT_TOKEN` and comma-separated `TELEGRAM_ALLOWED_CHAT_IDS` in the environment before enabling Telegram handlers.

`TelegramNotificationService` builds review payloads without sending network requests. Candidate messages include the job summary and `Siapkan draft`; pending application messages include the draft materials plus `Setujui`/`Tolak` callbacks containing the application ID and expected `PENDING_APPROVAL` status.

`TelegramApprovalHandler` authenticates the callback chat before reading application data, verifies the expected status, and delegates the change to the centralized transition service. Replayed or stale callbacks return a safe message and do not create another history record.

`TelegramCommandHandler` supports `/lowongan`, `/status [application_id] [status]`, and `/laporan`. Commands require the same allowlisted chat ID and `/status` always uses the centralized transition service.

## Commands

Print the startup configuration (does not run the bot; use `run-bot` for that):

```powershell
python -m bot_loker_wfh
```

Initialize the SQLite schema from an empty database:

```powershell
python -m bot_loker_wfh init-db
```

Run a RemoteOK fetch manually. This is an explicit command and is never run by the normal application startup:

```powershell
python -m bot_loker_wfh fetch-remoteok
```

The fetcher stores `source=remoteok`, retries transient network failures with a bounded retry count, and relies on the source and canonical uniqueness constraints to make repeated fetches idempotent.

Run a Remotive fetch manually:

```powershell
python -m bot_loker_wfh fetch-remotive
```

The Remotive adapter reads its `jobs` payload, normalizes salary, tags, location, publication date, and apply URL, then uses the same deduplication constraints as the other sources.

Run all MVP fetchers once for development or manual operation:

```powershell
python -m bot_loker_wfh fetch-once
```

Run the periodic scheduler. The default interval is four hours and lower intervals are rejected by the scheduler:

```powershell
python -m bot_loker_wfh run-scheduler
```

Scheduler logs contain source names and inserted counts only; job descriptions, CV data, and cover letters must not be logged.

Structured events use JSON with an event name, generated `run_id`, source, status, duration, inserted count, and sanitized error code where applicable. The logger uses an allowlist and never serializes exception messages, request bodies, tokens, CVs, or cover letters.

## Operational Documentation for MVP

### Setup from Scratch

1. Clone the repository: `git clone <repository-url> && cd bot-loker-wfh`
2. Create a virtual environment: `python -m venv .venv`
3. Activate the virtual environment:
   - Windows: `.\.venv\Scripts\Activate.ps1`
   - Unix/macOS: `source .venv/bin/activate`
4. Install dependencies: `python -m pip install -e ".[dev]"`
5. Copy environment template: `Copy Item .env.example .env`
6. Edit `.env` to set:
   - `TELEGRAM_BOT_TOKEN` (obtain from @BotFather on Telegram)
   - `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated list of your Telegram chat IDs)
   - `EXTERNAL_JOBS_ENABLED=true` to let the bot call the job APIs (leave `false` for safe local testing)
   - Optional: `ANTHROPIC_API_KEY` to draft cover letters with Claude (a template draft is used otherwise)
   - The `.env` file is loaded automatically; real environment variables take precedence
7. Create your safe CV profile: `Copy-Item resume/profile.example.json data/profile.json`, then edit skills, experience, and projects. Only these fields are ever used for drafts, and contact details are redacted.
8. Initialize the database: `python -m bot_loker_wfh init-db`
9. Register the company boards to watch (optional, adds Greenhouse/Lever jobs):
   ```powershell
   python -m bot_loker_wfh add-company --ats greenhouse --slug gitlab --name GitLab
   python -m bot_loker_wfh add-company --ats lever --slug binance --name Binance
   ```

### Running the Bot

```powershell
python -m bot_loker_wfh run-bot
```

`run-bot` is the single long-running process. It polls Telegram for commands and buttons and, when `EXTERNAL_JOBS_ENABLED=true`, runs a fetch cycle at start-up and every `FETCH_INTERVAL_HOURS` (minimum 4). Each cycle:

1. fetches RemoteOK, Remotive, the Indonesian boards Kalibrr and Dealls, and every registered Greenhouse/Lever board (one failing source does not stop the others),
2. scores each new job by how many of your profile skills it mentions and applies the eligibility filters,
3. sends up to 10 new `CANDIDATE` jobs to Telegram (best score first; the rest follow every 30 minutes).

The first cycle downloads every job description from Greenhouse boards and can take several minutes for large boards; later cycles skip jobs that are already stored.

Other one-off commands:

```powershell
python -m bot_loker_wfh fetch-once      # fetch all sources once
python -m bot_loker_wfh process-jobs    # score + filter DISCOVERED jobs
python -m bot_loker_wfh run-scheduler   # fetch only, no Telegram (needs EXTERNAL_JOBS_ENABLED=true)
python -m bot_loker_wfh fetch-remoteok  # also fetch-remotive / fetch-greenhouse / fetch-lever
python -m bot_loker_wfh fetch-kalibrr   # Indonesian remote jobs; also fetch-dealls
python -m bot_loker_wfh fetch-leads     # freelance leads (see below)
```

### Telegram Interaction

Applications are submitted **manually**: the bot prepares a draft and, after you approve it, gives you the apply link.

1. A candidate arrives with a **Siapkan draft** button (or `/siapkan <job_id>`).
2. The bot replies with the cover letter draft and **Setujui / Tolak** buttons (or `/setuju <id>` / `/tolak <id>`).
3. After approval, open the apply link, send the application yourself, then run `/dilamar <application_id>`.
4. Track the outcome with `/status <application_id> <INTERVIEW|OFFER|REJECTED_BY_COMPANY|NO_RESPONSE>`.

### Indonesian jobs

Kalibrr and Dealls are read through the public JSON their own websites use (no login, sequential requests with a delay, `robots.txt` respected). Only postings the board itself marks as remote/WFH are stored, so hybrid and on-site jobs never enter the bot. They then go through the same filters as every other source, including the 14-day posting age limit in the `filters` table. Indonesian remote developer jobs are scarce (Kalibrr had about 30 WFH postings and Dealls 13, mostly non-technical), so also register Indonesian companies' Greenhouse/Lever boards with `add-company`. LinkedIn is not used because its terms forbid automated access; JobStreet, Indeed, and Glints are skipped because they block detail pages or rely on unstable internal APIs.

### Freelance leads (`/lead`)

Besides jobs, the bot looks for **freelance projects that need a fullstack developer** and **chances to sell your source code**. Sources: Freelancer.com (public projects API), projects.co.id (Indonesian marketplace), and optionally public Telegram channels you list in `LEAD_TELEGRAM_CHANNELS` (comma-separated usernames, read through the public `t.me/s/<channel>` preview; private groups are not reachable).

- A lead is kept when it mentions your stack (Laravel, React, Flutter, NestJS, PHP, Python, ... plus the skills in `data/profile.json`) and is at most 3 days old.
- It is labelled **Proyek dicari developer**, or **Peluang jual source code** when someone wants to buy existing code (phrases such as "looking for source code", "ready made", "WTB", "cari source code"). A project that merely requires the source code as a deliverable is a normal project. The classification is keyword based, so expect some noise.
- Each lead arrives in Telegram (up to 5 per batch) with **Minat** and **Abaikan** buttons. `/lead` lists the ones you marked and the new ones. There is no application workflow: open the link and contact the client on the platform yourself.

### Semi-automatic form filling (`/isi`)

After you approve an application, tap **Buka & isi form** (or `/isi <application_id>`). The bot opens the real application form in a visible browser on your computer, fills what it can, and **stops**. You review, solve any CAPTCHA, click Submit yourself, then send `/dilamar <application_id>`. The bot never clicks Submit and never solves CAPTCHA.

Setup (once, on the computer that runs `run-bot`):

```powershell
python -m pip install -e ".[form]"
python -m playwright install chromium
Copy-Item resume/applicant.example.json data/applicant.json   # then edit: name, email, phone, resume_path, links
```

and set `FORM_ASSIST_ENABLED=true` in `.env`. Supported forms: Greenhouse (`job-boards.greenhouse.io`) and Lever (`jobs.lever.co`), i.e. jobs that came from your registered `add-company` boards. RemoteOK/Remotive links point to other sites and are not filled.

What gets filled: first/last/full name, email, phone, resume upload, cover letter (uploaded as a text file on Greenhouse, "Additional information" on Lever), and LinkedIn/GitHub/website when set. Everything else is listed in Telegram as **Perlu Anda isi/pilih** (dropdowns, work authorization, salary, etc.).

To pre-answer recurring text questions, create `data/answers.json` (see `resume/answers.example.json`): each key is part of the question label, and it is filled only when exactly one text field matches. Dropdowns and yes/no choices are never guessed.

Because it needs a screen, this feature does not work when the bot runs on a headless VPS; there it replies that the feature is off. Keep `FORM_ASSIST_ENABLED=false` in the server's `.env`.

Also available: `/lowongan` (candidates and pending drafts), `/fetch` (run a cycle now), `/laporan` (statistics), `/help`. IDs can be shortened to their first 8 characters.

### Deployment (VPS + Docker)

The bot is a single process that keeps a local SQLite file, so one small VPS (1 vCPU / 512 MB–1 GB RAM) is enough.

1. On the server, install Docker (with the Compose plugin) and clone the repository.
2. Copy the files that are not in git from your machine (`.env`, `data/profile.json`, and optionally `data/app.db` to keep your history):
   ```bash
   scp .env user@server:~/bot-loker-wfh/.env
   scp -r data user@server:~/bot-loker-wfh/data
   ```
3. Start it: `docker compose up -d --build`
4. Watch the logs: `docker compose logs -f bot`. Expect `bot running ...`, then a Telegram message "Bot aktif".
5. Update later: `git pull && docker compose up -d --build`.

Stop any locally running bot first: a Telegram token can be polled by only one process at a time.

Back up the database from the server:

```bash
docker compose exec bot python -m bot_loker_wfh backup-db --backup-path data/backups/app.sqlite
```

### Maintenance Operations

#### Backup the Database
```powershell
python -m bot_loker_wfh backup-db --backup-path backups/app.sqlite
```

#### Restore from Backup
```powershell
python -m bot_loker_wfh restore-db --restore-path backups/app.sqlite
```
To restore to a different location:
```powershell
python -m bot_loker_wfh restore-db --restore-path backups/app.sqlite --target-db data/restored.db
```

#### Run Retention Cleanup
```powershell
python -m bot_loker_wfh cleanup-retention
```
This deletes `FILTERED_OUT` jobs older than 90 days that have no associated application.

### Troubleshooting

#### "Unable to open database file" errors
Ensure the database file path in `DATABASE_URL` is accessible and the directory exists.
The init-db command will create directories automatically.

#### Telegram bot not responding
Verify:
1. `TELEGRAM_BOT_TOKEN` is correct in `.env`
2. Your chat ID is in `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated)
3. The bot is running (`python -m bot_loker_wfh run-bot`). Only one instance may poll a token at a time
4. You're sending commands to the bot, not to a group or channel (unless added there)

#### No jobs appearing in `/lowongan`
Check:
1. The fetcher ran successfully (look for `fetch complete` logs)
2. Jobs passed eligibility filters (check `status=CANDIDATE` in database)
3. You haven't already applied to all available jobs

#### Logs contain unexpected information
All logs are structured JSON. Look for:
- `event`: indicates what happened (fetch_complete, transition_application, etc.)
- `status`: current status after the event
- `error_code`: standardized error code if applicable (never raw exception messages)
- No CV, cover letter, token, or personal data should ever appear in logs

### Viewing Logs Safely

All application logs are structured JSON containing only allowlisted metadata fields. To inspect logs without risking exposure of sensitive data:

```powershell
# View all log events for a specific run:
python -m bot_loker_wfh fetch-once 2>&1 | python -c "import sys, json; [print(json.dumps(json.loads(l), indent=2)) for l in sys.stdin if l.strip()]"

# Filter for errors only:
python -m bot_loker_wfh fetch-once 2>&1 | python -c "import sys, json; [print(l.strip()) for l in sys.stdin if l.strip() and json.loads(l).get('status') == 'error']"
```

Fields that will **never** appear in logs:
- `cover_letter`, `cv_summary`, `description` (job or application content)
- `token`, `password`, `secret` (credentials)
- Phone numbers, home addresses, dates of birth

If any of the above appear in a log line, it is a bug. Report and do not share the log file.

### Safety Features

- External job fetching is disabled by default (`EXTERNAL_JOBS_ENABLED=false`)
- Telegram commands are restricted to allowlisted chat IDs
- All status changes go through centralized transition service with validation
- Duplicate prevention at database level with unique constraints
- Structured logging never exposes sensitive data
- Backup command copies only the database file, never `.env` or credentials

### Next Steps for Production

To enable full automation:

1. Keep the `run-bot` process alive (Windows Task Scheduler, a VPS with systemd, or Docker) so it can poll 24/7
2. Auto-submit (Playwright) is intentionally not enabled; see `docs/auto-submit-risk-assessment.md`
3. Set up monitoring for the structured logs (e.g., via ELK stack or cloud logging)

## Support

For issues, check the logs first. The structured format makes it easy to search for specific events and error codes.


Run filtered-job retention cleanup manually or from a scheduled process:

```powershell
python -m bot_loker_wfh cleanup-retention
```

The cleanup deletes only `FILTERED_OUT` jobs older than 90 days that have no application. Active jobs and jobs referenced by applications are preserved.

Back up the local SQLite database. The backup command copies only the SQLite database file and does not include `.env` or credentials:

```powershell
python -m bot_loker_wfh backup-db --backup-path backups/app.sqlite
```

Restore a backup into the configured database path or an explicit target:

```powershell
python -m bot_loker_wfh restore-db --restore-path backups/app.sqlite
python -m bot_loker_wfh restore-db --restore-path backups/app.sqlite --target-db data/restored.db
```

Eligibility filters are stored in the `filters` table as JSON keyword lists and numeric thresholds. The default role list covers Laravel, Flutter, NestJS, React, Python, backend, full-stack, and mobile development; changing the row changes the next eligibility evaluation without a code change.

Status changes must go through the centralized transition service. It validates the job/application transition table and appends application changes to `application_status_history`; direct status updates are not part of the normal application flow.

Run the smoke tests without installing pytest:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Run the test suite after installing development dependencies:

```powershell
python -m pytest
```

