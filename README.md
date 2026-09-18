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

## Commands

Run the application:

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
