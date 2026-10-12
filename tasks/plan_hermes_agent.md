# Implementation Plan: Rewrite LLM ke Hermes Agent

## Overview

Mengganti seluruh integrasi LLM/9Router dengan Hermes Agent resmi dari Nous Research melalui API Server lokalnya. Hermes menjadi mesin reasoning dan generasi teks, sedangkan aplikasi Bot Loker WFH tetap menjadi pemilik workflow, database, policy guard, approval, browser/form execution, Telegram, scheduler, dan pengiriman akhir.

Rencana ini tidak menjadikan Hermes sebagai operator bebas atas komputer. Profil Hermes khusus aplikasi akan berjalan di loopback, memakai bearer key, dan hanya diberi toolset minimum yang telah diverifikasi. Migrasi dilakukan bertahap dengan fallback sementara agar fitur yang sudah bekerja tidak putus sekaligus.

## Scope

### Termasuk

- Cover letter dan draft lamaran.
- Proposal, revisi proposal, komentar proyek, serta saran bid terms.
- Form mapping JSON dan jawaban pertanyaan terbuka.
- Office Q&A, employee instinct, dan rapat dinamis.
- Routing per tugas, retry, timeout, fallback template, observability, dan halaman Settings.
- Instalasi/deployment Hermes gateway sebagai service terpisah.
- Penghapusan konfigurasi dan implementasi 9Router setelah parity tercapai.

### Tidak termasuk

- Memindahkan state machine aplikasi/bid ke Hermes.
- Memberi Hermes hak untuk klik Submit, Apply, atau mengirim bid.
- Mengganti Supabase sebagai source of truth.
- Mengganti Telegram bot atau scheduler aplikasi dengan gateway/cron Hermes.
- Mengaktifkan terminal, file write, browser, cron, delegation, atau web search untuk profil Hermes produksi tanpa persetujuan terpisah.

## Current Integration Map

Lapisan LLM saat ini berpusat di `src/bot_loker_wfh/llm.py`:

- `OpenAICompatibleProvider` memanggil endpoint 9Router `/chat/completions` dan `/models`.
- `LLMRouter` menangani task routing, retry, fallback model, JSON validation, dan recording.
- `create_llm_from_settings` dipakai untuk draft, form, proposal, komentar, dan bid terms.
- `create_chat_llm` membuat jalur cepat Office Q&A.
- `meeting_runtime.py` membuat provider 9Router secara langsung dan harus dipindahkan ke factory yang sama.
- `office_server.py` dan `settings.js` mengandung UI/test endpoint yang spesifik terhadap 9Router.
- `llm_calls.py` menyimpan provider/model/status/latency/token usage.

Consumer yang harus dipertahankan perilakunya:

1. `DraftService` dan `CoverLetterGenerator`.
2. `lead_desk.draft_proposal`, revisi, komentar, dan pemilihan bid terms.
3. `FormPlanner.plan` dengan output JSON tervalidasi.
4. `FormPlanner.generate_answer` dengan batas fakta dan `NEEDS_USER`.
5. `office_desk.ask` dan `office_desk.instinct`.
6. `meeting_runtime.run_dynamic_meeting`.

## Target Architecture

```text
Bot Loker WFH
  |
  |-- domain workflow / approval / policy / persistence
  |
  `-- AgentRouter
        |-- HermesAgentClient
        |     `-- http://127.0.0.1:8642/v1/chat/completions
        |           `-- dedicated Hermes profile: loker-wfh
        |
        `-- Template fallback

Hermes profile loker-wfh
  |-- bearer authentication
  |-- loopback bind only
  |-- task route aliases: loker-draft, loker-form, loker-answer
  |-- no browser/terminal/file-write/cron/delegation tools
  `-- concurrency and turn limits
```

## Architecture Decisions

1. **Hermes diakses lewat API Server, bukan subprocess CLI.** API Server memiliki kontrak HTTP, bearer authentication, health/readiness endpoints, concurrency limit, dan format OpenAI-compatible. Subprocess CLI akan lebih sulit dibatalkan, dipantau, dan diuji.

2. **Aplikasi tetap menjadi orchestrator.** Hermes hanya menerima prompt dan mengembalikan hasil. Semua perubahan status, query database, form execution, serta keputusan submit tetap dilakukan kode deterministik.

3. **Dedicated Hermes profile.** Gunakan profile `loker-wfh` dengan API key berbeda dan state terpisah. Profile saja bukan sandbox, sehingga toolset tetap harus dibatasi dan deployment produksi sebaiknya memakai container/service account terbatas.

4. **Stateless pada fase pertama.** Jangan kirim `X-Hermes-Session-Key` untuk draft/form/proposal. Supabase employee memory tetap satu-satunya sumber lesson dan instruction. Ini mencegah memory Hermes mengontaminasi output deterministik atau menggandakan memory yang sudah ada.

5. **Task route aliases dikonfigurasi server-side.** Gunakan alias `loker-draft`, `loker-form`, dan `loker-answer`. Jangan bergantung pada field `model` biasa sebelum perilaku `model_routes`/`direct_model_requests` diverifikasi, karena Hermes dapat mengabaikan model tanpa provider atau konfigurasi routing.

6. **JSON divalidasi di aplikasi.** `json_mode=True` tetap menjadi kontrak internal, tetapi client tidak menganggap `response_format` pasti didukung. Output diparse dan divalidasi lokal; satu repair attempt boleh dilakukan tanpa menjalankan tool.

7. **Tidak ada silent fallback untuk tugas safety-critical.** Form mapping gagal → assist mode; jawaban ambigu → `NEEDS_USER`; meeting/Q&A boleh memakai fallback data mentah; draft boleh memakai template yang sudah ada.

8. **Dual-provider hanya sementara.** `LLM_PROVIDER=hermes|9router|template` dipakai selama canary. Setelah acceptance gate selesai, default menjadi `hermes`, lalu kode/config 9Router dihapus pada fase cleanup terpisah.

## Configuration Contract

Konfigurasi aplikasi yang direncanakan:

```dotenv
LLM_PROVIDER=hermes
HERMES_BASE_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=<secret>
HERMES_MODEL_DRAFT=loker-draft
HERMES_MODEL_FORM=loker-form
HERMES_MODEL_ANSWER=loker-answer
HERMES_TIMEOUT_SECONDS=90
HERMES_TASK_BUDGET_SECONDS=150
HERMES_MAX_RETRIES=1
```

Konfigurasi Hermes minimum:

- API server bind ke `127.0.0.1`.
- `API_SERVER_KEY` wajib dan berbeda dari credential provider/model.
- CORS tidak diaktifkan karena hanya backend Python yang memanggil Hermes.
- `max_concurrent_runs` dibatasi sesuai beban aplikasi.
- Toolset API server dibatasi; hasil aktual diverifikasi melalui `/v1/toolsets`.
- Health menggunakan `/health`; readiness menggunakan `/health/detailed` dengan bearer key.
- Model routing alias disimpan di profile Hermes, bukan di browser Office.

## Dependency Graph

```text
Hermes contract spike
  |
  +-- dedicated profile + security baseline
  |
  `-- HermesAgentClient
        |
        +-- AgentRouter + observability
        |     |
        |     +-- draft/proposal slice
        |     +-- form JSON slice
        |     +-- Office/meeting slice
        |
        +-- Settings + health UI
        |
        `-- deployment/service lifecycle
              |
              `-- canary, cutover, remove 9Router
```

## Task List

### Phase 0: Contract and Safety Spike

#### Task 1: Prove the Hermes API contract

**Description:** Jalankan Hermes profile uji dan dokumentasikan perilaku endpoint yang benar-benar dibutuhkan aplikasi: chat completion, model route alias, JSON output, timeout, 401, 429, 5xx, token usage, runtime provider/model, cancellation, dan health/readiness.

**Acceptance criteria:**
- [ ] Contract test membuktikan request teks, system message, dan route alias bekerja.
- [ ] Perilaku JSON, error, timeout, serta usage/runtime tercatat tanpa asumsi yang belum diuji.
- [ ] Tidak ada tool call pada profile uji yang dibatasi.

**Verification:**
- [ ] Tes integrasi lokal terhadap profile Hermes disposable lulus.
- [ ] `/v1/toolsets` tidak menunjukkan terminal, file write, browser, cron, atau delegation aktif.
- [ ] Request tanpa/salah bearer key menghasilkan 401.

**Dependencies:** None

**Files likely touched:**
- `tests/test_hermes_contract.py`
- `docs/HERMES_INTEGRATION.md`

**Estimated scope:** Small

#### Task 2: Define a hardened Hermes profile

**Description:** Buat konfigurasi referensi profile `loker-wfh` dengan loopback binding, key terpisah, concurrency cap, route aliases, turn limit, dan allowlist tool minimum. Jangan simpan secret nyata di repository.

**Acceptance criteria:**
- [ ] Profile dapat dibuat ulang dari dokumentasi/template tanpa secret ter-commit.
- [ ] Toolset efektif diverifikasi, bukan hanya diasumsikan dari file konfigurasi.
- [ ] Threat model menjelaskan batas profile, host process, container, dan credential.

**Verification:**
- [ ] `hermes doctor`/health dan readiness profile lulus.
- [ ] API tidak dapat diakses dari interface non-loopback pada konfigurasi lokal.
- [ ] Secret scan tidak menemukan `HERMES_API_KEY` nyata.

**Dependencies:** Task 1

**Files likely touched:**
- `deploy/hermes/config.example.yaml`
- `deploy/hermes/env.example`
- `docs/HERMES_INTEGRATION.md`

**Estimated scope:** Medium

### Checkpoint A: Contract and security

- [ ] Hermes version dan API contract dipin/dicatat.
- [ ] Profile efektif tidak memiliki tool berbahaya.
- [ ] Tidak ada perubahan pada workflow produksi.

### Phase 1: Provider Foundation

#### Task 3: Introduce the agent client interface

**Description:** Pisahkan kontrak aplikasi dari implementasi provider. Pertahankan bentuk `complete(task, messages, json_mode, ...)`, `LLMResult`, dan error terstruktur agar consumer tidak perlu berubah sekaligus.

**Acceptance criteria:**
- [ ] Protocol/interface mencakup text, JSON intent, task name, timeout, dan metadata.
- [ ] Existing 9Router serta template dapat hidup di belakang interface selama migrasi.
- [ ] Unit test memastikan consumer tidak bergantung pada class provider konkret.

**Verification:**
- [ ] Tes baru interface/router lulus.
- [ ] Seluruh tes LLM lama tetap lulus sebelum cutover.

**Dependencies:** Task 1

**Files likely touched:**
- `src/bot_loker_wfh/llm.py`
- `tests/test_ninerouter_llm.py`
- `tests/test_hermes_client.py`

**Estimated scope:** Medium

#### Task 4: Implement `HermesAgentClient`

**Description:** Implementasikan client HTTP Hermes dengan bearer auth, route alias, bounded timeout, error mapping, response parsing, JSON validation/repair, dan metadata runtime.

**Acceptance criteria:**
- [ ] 401, 403, 429, timeout, bad response, empty response, dan upstream failure dipetakan konsisten.
- [ ] Retry hanya terjadi untuk error yang aman dan masih di dalam task budget.
- [ ] Secret, prompt, CV, cover letter, atau response mentah tidak masuk log error.

**Verification:**
- [ ] Unit test memakai fake HTTP server untuk semua status dan response shape.
- [ ] Contract test terhadap Hermes lokal lulus.

**Dependencies:** Tasks 1 and 3

**Files likely touched:**
- `src/bot_loker_wfh/hermes_agent.py`
- `src/bot_loker_wfh/llm.py`
- `tests/test_hermes_client.py`

**Estimated scope:** Medium

#### Task 5: Extend configuration and call recording

**Description:** Tambahkan setting Hermes, validasi URL loopback/default aman, secret masking, route aliases, serta observability untuk runtime provider/model, latency, usage, dan error code.

**Acceptance criteria:**
- [ ] `Settings` menerima Hermes dan tetap mendukung `template` serta 9Router selama canary.
- [ ] API key tidak pernah dikirim kembali ke browser Office atau log.
- [ ] Recorder mencatat runtime Hermes tanpa menyimpan prompt/response sensitif.

**Verification:**
- [ ] Tes config, secret masking, settings store, dan recorder lulus.
- [ ] `.env.example` dan onboarding mencantumkan konfigurasi baru tanpa secret.

**Dependencies:** Task 4

**Files likely touched:**
- `src/bot_loker_wfh/config.py`
- `src/bot_loker_wfh/llm_calls.py`
- `.env.example`
- `tests/test_settings_store.py`
- `tests/test_hermes_client.py`

**Estimated scope:** Medium

### Checkpoint B: Provider foundation

- [ ] Hermes client lulus unit dan contract test.
- [ ] Template fallback masih bekerja tanpa Hermes.
- [ ] 9Router production behavior belum dihapus.
- [ ] Full test suite lulus.

### Phase 2: Vertical Feature Migration

#### Task 6: Migrate cover letters and freelance writing

**Description:** Migrasikan cover letter, proposal, revisi proposal, komentar proyek, serta bid-term suggestion ke AgentRouter/Hermes. Setiap task memakai system instruction terpisah dan route alias yang tepat.

**Acceptance criteria:**
- [ ] Output hanya memakai fakta dari profile/job/project/GitHub yang diberikan.
- [ ] Draft kosong/invalid jatuh ke template atau mempertahankan draft lama sesuai perilaku sekarang.
- [ ] Approval dan submit flow tidak dapat dipicu oleh output Hermes.

**Verification:**
- [ ] Tes cover letter, lead desk, auto-bid, dan regression prompt injection lulus.
- [ ] E2E schema uji menghasilkan draft tetapi tidak mengirim lamaran/bid.

**Dependencies:** Task 5

**Files likely touched:**
- `src/bot_loker_wfh/drafts.py`
- `src/bot_loker_wfh/cover_letter.py`
- `src/bot_loker_wfh/lead_desk.py`
- `src/bot_loker_wfh/form_agent/bid_terms.py`
- `tests/test_hermes_workflows.py`

**Estimated scope:** Medium

#### Task 7: Migrate form planning and open answers

**Description:** Alihkan form mapping JSON dan jawaban terbuka ke Hermes, lalu pertahankan policy guard sebagai validator deterministik setelah model menghasilkan rencana.

**Acceptance criteria:**
- [ ] JSON invalid, action tidak dikenal, placeholder ilegal, protected field, dan submit action selalu ditolak atau turun ke assist mode.
- [ ] Personal data tidak dikirim ke Hermes; hanya candidate summary aman dan placeholder keys.
- [ ] `NEEDS_USER` tetap menjadi hasil default untuk pertanyaan sensitif/ambigu.

**Verification:**
- [ ] Tes form planner, policy, agent, prompt injection, dan malformed JSON lulus.
- [ ] Dry-run ATS populer tidak pernah menekan submit.

**Dependencies:** Task 5

**Files likely touched:**
- `src/bot_loker_wfh/form_agent/planner.py`
- `src/bot_loker_wfh/form_agent/policy.py`
- `tests/test_form_agent.py`
- `tests/test_form_assist.py`
- `tests/test_hermes_workflows.py`

**Estimated scope:** Medium

#### Task 8: Migrate Office Q&A, instinct, and meetings

**Description:** Hapus konstruksi provider langsung dari meeting runtime dan gunakan AgentRouter yang diinjeksi. Office Q&A/instinct/meeting tetap menerima fakta, instruction, skill, dan lesson dari Supabase.

**Acceptance criteria:**
- [ ] Tidak ada `OpenAICompatibleProvider` yang dibuat langsung di runtime fitur.
- [ ] Failure Hermes menghasilkan fallback plain facts/template, bukan HTTP 500.
- [ ] Memory Hermes tidak aktif diam-diam; Supabase tetap sumber lesson dan instruction.

**Verification:**
- [ ] Tes Office desk, meeting runtime, employee memory, dan fallback lulus.
- [ ] Rapat dummy selesai dan event tidak mengandung secret atau prompt internal.

**Dependencies:** Task 5

**Files likely touched:**
- `src/bot_loker_wfh/meeting_runtime.py`
- `src/bot_loker_wfh/office_desk.py`
- `src/bot_loker_wfh/office_work.py`
- `src/bot_loker_wfh/office_server.py`
- `tests/test_employee_memory_meeting_runtime.py`

**Estimated scope:** Medium

### Checkpoint C: Feature parity

- [ ] Draft, proposal, form JSON, answer, Q&A, instinct, dan meeting lulus dengan Hermes.
- [ ] Semua failure mode memiliki fallback eksplisit.
- [ ] Tidak ada aksi eksternal atau submit selama E2E.
- [ ] Full test suite lulus.

### Phase 3: Operations and UI

#### Task 9: Replace Office Settings and health checks

**Description:** Ubah panel “9Router & Model” menjadi “Hermes Agent”, tampilkan status gateway/readiness, route aliases, timeout, dan secret state. Browser tidak boleh memanggil Hermes langsung.

**Acceptance criteria:**
- [ ] UI tidak menampilkan atau mengembalikan API key mentah.
- [ ] Test connection memakai backend Office menuju Hermes health/readiness.
- [ ] Copy menjelaskan bahwa perubahan route/model diterapkan pada profile Hermes dan apakah restart diperlukan.

**Verification:**
- [ ] Tes endpoint Settings dan browser UI lulus.
- [ ] Keyboard, mobile, error, loading, dan disconnected states diverifikasi.

**Dependencies:** Tasks 5 and 8

**Files likely touched:**
- `src/bot_loker_wfh/office_server.py`
- `src/bot_loker_wfh/office/js/ui/settings.js`
- `src/bot_loker_wfh/office/css/office.css`
- `tests/test_office_server.py`
- `tests/test_office_http.py`

**Estimated scope:** Medium

#### Task 10: Add service lifecycle and deployment wiring

**Description:** Tambahkan cara menjalankan Hermes gateway bersama bot untuk Windows development dan Docker/production, termasuk startup order, readiness, restart policy, dan graceful degradation.

**Acceptance criteria:**
- [ ] Bot dapat start saat Hermes belum siap dan menampilkan degraded state tanpa crash loop.
- [ ] Deployment memulai Hermes sebelum canary traffic, dengan healthcheck dan restart policy.
- [ ] Secret Hermes tidak masuk image, compose file, atau log.

**Verification:**
- [ ] Cold start, Hermes restart, wrong key, dan unavailable gateway diuji.
- [ ] Deployment smoke test lulus dalam environment terisolasi.

**Dependencies:** Tasks 2, 5, and 9

**Files likely touched:**
- `docker-compose.yml`
- `Dockerfile`
- `deploy/hermes/config.example.yaml`
- `docs/ONBOARDING.md`
- `tests/test_smoke.py`

**Estimated scope:** Medium

### Phase 4: Canary, Cutover, and Removal

#### Task 11: Run quality and safety canary

**Description:** Bandingkan Hermes dan 9Router pada corpus fixture yang sama tanpa mengirim output ke platform. Ukur validity, factuality, latency, fallback rate, cost metadata, dan policy violations.

**Acceptance criteria:**
- [ ] Corpus mencakup cover letter, proposal Indonesia/Inggris, form JSON, Q&A, instinct, dan meeting.
- [ ] Tidak ada personal data nyata atau submit eksternal dalam canary.
- [ ] Cutover hanya dilakukan jika threshold kualitas dan safety terpenuhi.

**Verification:**
- [ ] Laporan canary tersimpan tanpa prompt/response sensitif.
- [ ] Human review dilakukan pada sampel output yang sudah disanitasi.
- [ ] Rollback ke `template` atau 9Router dibuktikan bekerja.

**Dependencies:** Tasks 6–10

**Files likely touched:**
- `tests/fixtures/hermes/`
- `tests/test_hermes_quality.py`
- `docs/HERMES_CANARY_REPORT.md`

**Estimated scope:** Medium

#### Task 12: Cut over and remove 9Router

**Description:** Jadikan Hermes default, hapus factory/provider/config/UI 9Router, migrasikan dokumentasi, dan pertahankan `template` sebagai fallback offline aman.

**Acceptance criteria:**
- [ ] Tidak ada runtime reference ke 9Router atau variabel `NINEROUTER_*`.
- [ ] `LLM_PROVIDER=hermes` menjadi default; `template` tetap didukung.
- [ ] Rollback release dilakukan melalui artifact/version sebelumnya, bukan dead code provider lama.

**Verification:**
- [ ] Search repository tidak menemukan reference 9Router yang bukan catatan migrasi.
- [ ] Full test suite, compile, CLI smoke, Office browser audit, dan Docker smoke lulus.
- [ ] E2E dummy menghasilkan semua jenis output tanpa submit eksternal.

**Dependencies:** Task 11 and explicit owner approval for cutover

**Files likely touched:**
- `src/bot_loker_wfh/llm.py`
- `src/bot_loker_wfh/config.py`
- `src/bot_loker_wfh/__main__.py`
- `README.md`
- `docs/ONBOARDING.md`

**Estimated scope:** Medium

### Checkpoint D: Complete

- [ ] Hermes adalah satu-satunya agent backend produksi.
- [ ] Template fallback offline masih tersedia.
- [ ] Tidak ada Hermes tool yang dapat mengubah file, menjalankan terminal/browser, atau mengirim sesuatu.
- [ ] Semua 331+ regression tests dan tes Hermes baru lulus.
- [ ] Tidak ada secret, CV, cover letter, atau provider error text di log.
- [ ] Owner menyetujui laporan canary dan cutover.

## Quality Gates

### Functional

- Semua consumer LLM lama memiliki tes parity di Hermes.
- JSON output divalidasi sebelum dipakai.
- Failure Hermes tidak mengubah status domain secara parsial.
- Template/assist fallback diuji, bukan hanya tersedia di kode.

### Safety

- Agent tidak mempunyai akses submit atau kredensial platform kerja.
- API Server hanya loopback/internal network dan selalu memakai bearer auth.
- Toolset aktual diperiksa saat startup atau health check.
- Prompt injection dari job description, form label, dan project description memiliki regression tests.
- Idempotency dan approval tetap ditegakkan oleh aplikasi.

### Observability

- Setiap call mencatat task, provider/runtime model, latency, usage, attempt, status, dan safe error code.
- Tidak merekam prompt, response, CV, cover letter, API key, atau raw provider error.
- Readiness membedakan gateway hidup dari model/provider benar-benar siap.

### Performance

- Route `answer` mempunyai budget lebih pendek daripada draft/form.
- Concurrency dibatasi pada Hermes dan aplikasi.
- 429 memakai bounded backoff; tidak ada retry storm.
- Office tetap responsif ketika Hermes lambat atau restart.

## Rollout Strategy

1. **Development:** Hermes hanya dipakai contract/integration tests.
2. **Shadow:** request disalin ke Hermes tetapi output Hermes tidak disimpan atau dikirim; data sensitif memakai fixture/sanitized corpus.
3. **Canary:** Hermes aktif untuk Office Q&A/meeting terlebih dahulu karena memiliki fallback aman.
4. **Draft canary:** cover letter/proposal Hermes masuk approval queue, tidak pernah auto-submit.
5. **Form canary:** form JSON aktif setelah policy regression pass; failure selalu assist mode.
6. **Full cutover:** semua task memakai Hermes; 9Router masih tersedia satu release sebagai rollback.
7. **Removal:** hapus 9Router setelah metrik dan human review disetujui.

## Rollback Strategy

- Sebelum Task 12: ubah `LLM_PROVIDER=9router` atau `template`, restart service, dan hentikan traffic Hermes.
- Setelah Task 12: rollback ke release artifact/tag sebelumnya; database tidak memerlukan rollback karena schema domain tidak berubah kecuali observability migration yang bersifat additive.
- Semua pending approval tetap berada di Supabase dan tidak boleh diproses ulang otomatis saat provider berganti.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Hermes API server membawa toolset luas | Critical | Dedicated profile, explicit platform toolsets, disable terminal/file/browser/web/cron/delegation, verify `/v1/toolsets`, container isolation. |
| Output agent lebih nondeterministik dari chat completion biasa | High | Stateless calls, narrow prompts, local validators, one bounded repair, deterministic fallback. |
| Model alias diabaikan | High | Server-side `model_routes`, contract test runtime metadata, do not trust request `model` alone. |
| Memory ganda Hermes + Supabase | High | Disable Hermes long-term memory in phase one; inject Supabase lesson explicitly. |
| Latency agent menghambat Office | High | Separate task budgets, concurrency cap, fast fallback, no synchronous tool use. |
| Prompt injection dari lowongan/form | High | Treat external text as data, no tools, deterministic policy validation, adversarial fixtures. |
| Retry menghasilkan biaya/duplikasi | Medium | One retry max, task deadline, call id/idempotency, no domain writes until validated result. |
| Hermes update mengubah API/tool defaults | Medium | Pin release, run contract suite before update, verify effective toolsets after upgrade. |
| API key bocor melalui Office Settings/log | High | Masking, backend-only requests, no browser CORS, secret scanning. |
| Big-bang removal memutus fitur | High | Vertical migration, canary, one-release fallback, explicit cutover gate. |

## Open Questions for Implementation Approval

1. Provider/model di balik Hermes akan memakai Nous Portal, OpenRouter, model lokal, atau endpoint lain?
2. Deployment target utama: Windows native, Docker lokal, atau VPS?
3. Apakah Hermes memory/skills ingin dipakai pada fase lanjutan, atau Supabase harus tetap menjadi satu-satunya memory permanen?
4. Berapa batas latency dan biaya yang dapat diterima untuk draft, form, dan Office Q&A?
5. Setelah cutover, apakah 9Router langsung dihapus atau dipertahankan satu release sebagai rollback? Rencana ini merekomendasikan satu release.

## Definition of Done

Migrasi selesai hanya jika Hermes memproses semua use case LLM dengan kualitas yang disetujui, toolset efektif aman, observability tersedia, seluruh test suite lulus, E2E dummy tidak melakukan submit, fallback terbukti, deployment dapat restart bersih, dan referensi runtime 9Router sudah dihapus setelah cutover approval.

