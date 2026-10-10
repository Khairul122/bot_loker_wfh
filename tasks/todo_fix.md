# TODO — Perbaikan Bug Fitur & Tampilan (step-by-step)

> Urutan = prioritas. Kerjakan satu per satu, test tiap step.

- [ ] **S1 — Settings crash (P1)** — `POST /settings` KeyError untuk key di luar DEFAULTS (llm_provider dkk) karena hanya catch ValueError. Fix: `except (KeyError, ValueError)` + allow any key ke .env.
- [ ] **S2 — Settings stale setelah save (P1)** — `Settings.from_environment` pakai `setdefault` jadi .env baru tak terbaca tanpa restart. Fix: override/reload env setelah save.
- [ ] **S3 — Dropdown tidak tersimpan (P2)** — `createSelect` hanya save kalau ada onChange. `form_engine`, `form_ai_answers`, `skill_*` tidak pernah persist. Fix: wire onchange default ke saveSetting.
- [ ] **S4 — Test Form Engine salah engine (P2)** — JS kirim `GET /form/test?engine=...` tapi server baca body. Fix: baca query param.
- [ ] **S5 — save_dotenv quirks (P2)** — komentar dipindah, baris kosong hilang, tidak bisa clear value, quote tidak di-escape. Fix: preserve order + allow empty + escape.
- [ ] **S6 — Bocor API key di /settings.json (P3)** — key plaintext ke browser. Fix: redact/mask di payload.
- [ ] **S7 — Cleanup minor** — import duplikat save_dotenv, `create_llm_from_settings` unused, `skill_*` dead code: rapikan/hapus.

Verifikasi tiap step: `py -3.12 -m compileall -q src` + manual curl/POST settings + cek panel browser.
