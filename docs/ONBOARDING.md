# Onboarding Guide: Bot Loker WFH

## Ringkasan

Bot personal untuk mencari, menyaring, menilai, dan melacak lowongan kerja remote serta freelance lead. Telegram menjadi kontrol utama. SQLite menyimpan lowongan, kandidat, lamaran, draft, lead, event LLM, dan sesi pengisian form.

Batas penting: pengiriman lamaran produksi masih disabled. Bot hanya menyiapkan draft, membuka form, mengisi field yang aman, lalu berhenti sebelum submit.

## Tech stack

| Lapisan | Teknologi |
|---|---|
| Bahasa | Python >= 3.11 |
| Packaging | `setuptools`, `pyproject.toml` |
| Database | SQLite |
| Interface kontrol | Telegram Bot API |
| Browser automation | BrowserMCP atau Playwright MCP |
| LLM | Template, 9Router, OpenCode CLI, atau Anthropic |
| Office UI | Standard-library HTTP server + Three.js CDN |
| Test | pytest |
| Deployment | Docker Compose, satu service bot |

Runtime dependency sengaja kosong. Playwright hanya dipasang lewat extra `form`.

## Arsitektur

```text
External job boards / lead sources
        |
        v
Fetchers: RemoteOK, Remotive, Greenhouse, Lever, Kalibrr, Dealls,
         Freelancer, Projects.co.id, Telegram public channels
        |
        v
SQLite: jobs / leads / applications / history / filters
        |
        v
JobPipeline: skill scoring -> eligibility filters -> CANDIDATE/FILTERED_OUT
        |
        +--> DraftService + LLM provider -> application/proposal draft
        +--> TelegramNotificationService -> review and approval
        +--> FormAssist / BrowserMCP / Playwright MCP -> fill, never submit
        +--> Office server -> local 3D operational view
```

## Entry points

- `src/bot_loker_wfh/__main__.py` — CLI dispatcher dan command lifecycle.
- `src/bot_loker_wfh/bot.py` — long-running Telegram polling loop.
- `src/bot_loker_wfh/scheduler.py` — fetch cycle.
- `src/bot_loker_wfh/pipeline.py` — scoring dan eligibility processing.
- `src/bot_loker_wfh/database.py` — SQLite path resolution dan schema application.
- `src/bot_loker_wfh/migrations/` — SQL schema files.
- `src/bot_loker_wfh/form_agent/` — planner, policy, executor, classifier, extractor, report.
- `src/bot_loker_wfh/office_server.py` — local office UI server dan stats endpoint.
- `tests/` — unit dan integration-style tests berbasis SQLite/fakes.

## Directory map

| Path | Isi |
|---|---|
| `src/bot_loker_wfh/` | Package utama |
| `src/bot_loker_wfh/*_fetcher` | Adapter sumber lowongan/lead |
| `src/bot_loker_wfh/telegram_*` | Auth, command, approval, notification |
| `src/bot_loker_wfh/form_agent/` | Form analysis dan guarded browser actions |
| `src/bot_loker_wfh/office/` | Asset HTML/CSS/JS untuk kantor 3D |
| `src/bot_loker_wfh/migrations/` | Schema dan migration SQL |
| `tests/fixtures/` | Payload fixture sumber dan BrowserMCP |
| `data/` | Database, profile, portfolio, logs, browser state; jangan commit secret |
| `resume/` | Template profile/applicant/answers dan PDF resume |
| `docs/` | Operational docs dan design decisions |
| `scripts/` | Utility migration/export |
| `tmp/` | Script lokal sementara, bukan runtime core |

## Request lifecycle

### Job lifecycle

1. `run-bot` menjalankan `BotRunner.run_forever()`.
2. Scheduler memanggil fetcher aktif ketika interval tercapai.
3. Fetcher menormalisasi posting dan menyimpan data secara idempotent.
4. `JobPipeline.process_discovered()` mengambil job `DISCOVERED`.
5. `SkillCoverageScorer` menghitung relevance score.
6. `EligibilityEngine` menerapkan filter usia, lokasi, role, skill, dan aturan lain.
7. Job menjadi `CANDIDATE` atau `FILTERED_OUT`.
8. Candidate dikirim ke chat Telegram allowlist.

### Application lifecycle

1. User meminta draft lewat Telegram atau CLI.
2. `DraftService` membuat cover letter memakai provider terkonfigurasi atau template.
3. User menyetujui/menolak draft.
4. Approval memakai centralized status transition dan status guard.
5. User membuka link atau form assist.
6. Form agent mengisi field berconfidence tinggi dan melaporkan field manual.
7. User review, selesaikan CAPTCHA, dan submit sendiri.
8. User menandai aplikasi `dilamar`, lalu memperbarui outcome.

### Security boundaries

- Telegram command/callback dibatasi `TELEGRAM_ALLOWED_CHAT_IDS`.
- External job API disabled default.
- Form assist disabled default.
- Form agent tidak menekan Submit dan tidak menyelesaikan CAPTCHA.
- Callback stale/replayed ditolak melalui expected status.
- Structured logs menyimpan event metadata, bukan CV, cover letter, token, request body, atau provider message.
- Submission service production masih NO-GO; fake submitter dipakai untuk test.

## Commands utama

```powershell
python -m bot_loker_wfh                 # tampilkan startup config
python -m bot_loker_wfh init-db         # buat/update schema
python -m bot_loker_wfh fetch-once      # fetch semua source sekali
python -m bot_loker_wfh process-jobs    # score + filter DISCOVERED jobs
python -m bot_loker_wfh run-bot         # Telegram + periodic cycle
python -m bot_loker_wfh run-scheduler   # fetch-only scheduler
python -m bot_loker_wfh office --port 8765
python -m bot_loker_wfh check-llm
python -m bot_loker_wfh check-browser
python -m bot_loker_wfh backup-db --backup-path backups/app.sqlite
python -m bot_loker_wfh restore-db --restore-path backups/app.sqlite
python -m bot_loker_wfh cleanup-retention
```

Source-specific command tersedia: `fetch-remoteok`, `fetch-remotive`, `fetch-greenhouse`, `fetch-lever`, `fetch-kalibrr`, `fetch-dealls`, dan `fetch-leads`.

## Setup lokal

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m bot_loker_wfh init-db
```

Untuk form assist:

```powershell
python -m pip install -e ".[form]"
python -m playwright install chromium
Copy-Item resume/applicant.example.json data/applicant.json
python -m bot_loker_wfh check-browser
```

Aktifkan `EXTERNAL_JOBS_ENABLED=true` hanya ketika API external memang boleh dipanggil. Set `FORM_ASSIST_ENABLED=true` hanya pada komputer dengan browser profile yang benar.

## Konvensi kode

- Python modules memakai `snake_case`.
- Class memakai `PascalCase`, function/variable memakai `snake_case`.
- Dependency di-inject pada service yang perlu diuji, terutama client, clock, sleep, spawn, logger, dan submitter.
- SQLite connection biasanya dibuat di entrypoint lalu diteruskan ke service.
- Status application berubah melalui centralized transition service, bukan update bebas dari handler.
- Fetcher melakukan normalisasi dan deduplikasi sebelum penyimpanan.
- Error eksternal dipetakan ke error code tersanitasi sebelum masuk log.
- Test memakai SQLite/fake dependency agar tidak perlu network nyata.

## Where to look

| Kebutuhan | Lokasi |
|---|---|
| Tambah job source | Fetcher terkait + `scheduler.py` + fixture/test |
| Ubah filter | `filters.py`, `eligibility.py`, migration/settings tests |
| Ubah status lamaran | `status_transitions.py` dan test transisi |
| Ubah command Telegram | `telegram_commands.py`, `bot.py`, test Telegram |
| Ubah draft | `drafts.py`, `cover_letter.py`, `llm.py`, `prompt_builder.py` |
| Ubah form safety | `form_agent/policy.py`, `executor.py`, `browser_mcp.py` |
| Ubah schema | migration baru, `database.py`, database schema test |
| Ubah office UI | `office_server.py`, `office/`, office tests |
| Ubah deployment | `Dockerfile`, `docker-compose.yml`, `.env.example` |

## Verification

Install dev extra lalu jalankan:

```powershell
python -m pytest -q
```

Saat analisa ini dijalankan, `pytest` belum tersedia pada interpreter aktif, sehingga test suite belum diverifikasi. Jangan anggap perubahan lulus hanya karena import atau CLI berhasil.
