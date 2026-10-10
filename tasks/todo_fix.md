# TODO — Perbaikan Bug Fitur & Tampilan (step-by-step)

> Urutan = prioritas. Kerjakan satu per satu, test tiap step.

- [x] **S1 — Settings crash (P1)** — `POST /settings` KeyError untuk key di luar DEFAULTS. Fix: allowlist + `if key in DEFAULTS: set_setting` (workdir-fixed, verified). Commit `office_server.py` ALLOWED_SETTINGS.
- [x] **S2 — Settings stale setelah save (P1)** — `setdefault` bikin .env baru tak terbaca. Fix: `save_dotenv` sync `os.environ` langsung (verified via tempfile roundtrip).
- [x] **S3 — Dropdown tidak tersimpan (P2)** — `createSelect` auto-save + dedup `form_engine` id, hapus `skill_*` dead UI (verified `settings.js`).
- [x] **S4 — Test Form Engine salah engine (P2)** — server baca `?engine=` query, bukan body (verified `office_server.py:337-338`).
- [x] **S5 — save_dotenv quirks (P2)** — preserve order/komentar/blank line, escape `"`, allow empty clear (verified roundtrip).
- [x] **S6 — Bocor API key di /settings.json (P3)** — `_mask()` + hint, kosongkan `value` (verified `office_server.py:52-57,160-163`). Frontend hint placeholder active.
- [x] **S7 — Cleanup minor** — hapus `create_llm_from_settings` unused import + duplikat `save_dotenv` + `skill_*` UI mati. Done.

Verifikasi tiap step: `py -3.12 -m compileall -q src` + manual curl/POST settings + cek panel browser.
