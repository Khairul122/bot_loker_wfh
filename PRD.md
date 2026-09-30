# PRD: Integrasi 9Router dan BrowserMCP untuk Bot Loker WFH

**Versi:** 3.0
**Tanggal:** 30 September 2026
**Pemilik Proyek:** Khairul
**Status:** Draft untuk pengembangan
**Dokumen sebelumnya:** PRD v2 (MVP) diarsipkan di `docs/PRD-v2-mvp.md`. Semua aturan v2 tentang eligibility, lifecycle status, idempotency, dan privasi tetap berlaku kecuali diubah di dokumen ini.

---

## 1. Ringkasan

Bot Loker WFH sudah berjalan. Bot mengambil lowongan remote, menyaring, membuat draft cover letter, meminta approval lewat Telegram, lalu membuka form Greenhouse atau Lever dengan Playwright.

PRD ini menambah dua kemampuan:

1. **LLM Gateway lewat 9Router.** Bot memanggil satu endpoint OpenAI-compatible milik 9Router. 9Router meneruskan request ke puluhan provider AI dan pindah otomatis ke model cadangan saat kuota habis atau provider error.
2. **Pengisian form lewat BrowserMCP.** Bot mengendalikan Chrome milik pengguna melalui server MCP BrowserMCP. LLM membaca struktur form, lalu bot mengisi field satu per satu. Bot tetap berhenti sebelum tombol Submit.

Hasil yang dituju: draft lamaran tidak bergantung pada satu API key, dan form dari ATS di luar Greenhouse dan Lever bisa terisi sebagian besar secara otomatis.

## 2. Kondisi Proyek Saat Ini

Analisis kode pada branch saat ini (Python 3.11, tanpa dependency runtime, SQLite, Telegram long polling).

| Area | File | Kondisi sekarang | Batasan |
|---|---|---|---|
| Provider LLM | `src/bot_loker_wfh/llm.py` | `AnthropicProvider` memanggil `api.anthropic.com/v1/messages` dengan `urllib`. Interface: callable `prompt -> str`. | Satu provider, satu model, tanpa fallback antar model. |
| Konfigurasi LLM | `config.py`, `.env.example` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`. | Tidak ada pilihan provider lain. |
| Draft cover letter | `drafts.py`, `cover_letter.py`, `prompt_builder.py` | LLM dipakai jika ada key. Jika gagal, bot memakai template deterministik. `applications.method` berisi `llm` atau `template`. | Model yang dipakai tidak tercatat. |
| Privasi prompt | `cv_profile.py` | `SafeCvProfile` menyaring email, telepon, alamat, NIK sebelum masuk prompt. | Sudah baik. Wajib dipertahankan. |
| Pengisian form | `form_assist.py` | Playwright membuka Chromium baru, mengisi field lewat selector tetap (`#first_name`, `input[name='email']`), mencocokkan `answers.json` berdasarkan label. | Hanya host Greenhouse dan Lever. Dropdown dan pertanyaan kustom tidak diisi. Browser baru, tanpa sesi login pengguna. |
| Pemicu form | `bot.py` (`_fill_form`), `__main__.py` (`fill-form`) | Telegram `/isi` menjalankan subprocess `fill-form` di mesin yang sama. | Butuh layar. Tidak jalan di VPS. |
| Submission | `submission.py` | `SubmissionService` punya guard compare-and-swap `APPROVED -> SUBMITTING` dan status `SUBMISSION_AMBIGUOUS`. | Belum dipakai di produksi. Keputusan NO-GO auto-submit di `docs/auto-submit-risk-assessment.md`. |
| Test | `tests/` | 29 file test, termasuk `test_form_assist.py` dan `test_cover_letter.py`. | Belum ada test untuk provider OpenAI-compatible atau klien MCP. |

Kesimpulan analisis: arsitektur sudah memisahkan provider LLM (callable) dan pengisi form (fungsi `fill_page`). Dua titik ini menjadi tempat integrasi. Perubahan tidak perlu menyentuh fetcher, eligibility, atau state machine.

## 3. Masalah yang Diselesaikan

**M1. Draft gagal saat satu provider bermasalah.** Jika Anthropic mengembalikan 429 atau 5xx, bot langsung jatuh ke template. Kualitas draft turun.

**M2. Biaya dan kuota terkunci pada satu akun.** Pengguna sudah punya langganan lain (Claude Code, Copilot, GLM, Kimi, tier gratis). Bot belum bisa memakainya.

**M3. Form di luar Greenhouse dan Lever tidak terisi.** Lowongan dari Ashby, Workable, SmartRecruiters, Kalibrr, dan halaman karier perusahaan harus diisi manual dari awal.

**M4. Field kustom tidak terisi.** Selector tetap tidak mengenali dropdown, radio button, dan pertanyaan terbuka seperti "Why do you want to join us?". Pengguna tetap mengisi 5 sampai 15 field per lamaran.

**M5. Browser Playwright tidak memakai sesi pengguna.** Form yang meminta login (misalnya Kalibrr atau Workable dengan akun kandidat) tidak bisa dibuka.

## 4. Tujuan

| ID | Tujuan | Ukuran keberhasilan |
|---|---|---|
| G1 | Bot memakai model AI apa pun yang terdaftar di 9Router. | Model bisa diganti lewat `.env` atau `/model` tanpa ubah kode. |
| G2 | Draft cover letter tetap dibuat oleh LLM saat provider utama gagal. | Rasio draft `template` karena error LLM di bawah 5% per minggu. |
| G3 | Bot mengisi form di Chrome pengguna lewat BrowserMCP. | Minimal 80% field wajib (selain upload file dan CAPTCHA) terisi pada ATS yang didukung. |
| G4 | Pertanyaan kustom dijawab dari data yang sudah direview atau dari draft LLM yang ditandai. | Waktu isi form manual turun dari rata-rata 8 menit menjadi di bawah 3 menit per lamaran. |
| G5 | Keamanan dan privasi v2 tetap utuh. | Nol kejadian klik Submit otomatis. Nol data pribadi di prompt LLM dan log. |

## 5. Non-Tujuan

- Bot **tidak** menekan tombol Submit, Apply, atau Kirim. Keputusan NO-GO di `docs/auto-submit-risk-assessment.md` tetap berlaku.
- Bot **tidak** menyelesaikan atau menghindari CAPTCHA.
- Bot **tidak** mengotomasi LinkedIn Easy Apply atau Indeed Apply.
- Bot **tidak** menjalankan 9Router atau BrowserMCP di dalam container Docker VPS pada versi ini. Keduanya berjalan di laptop pengguna.
- Bot **tidak** mengirim data pribadi (nama, email, telepon, alamat, file CV) ke LLM.
- PRD ini tidak membangun dashboard web.

## 6. Pengguna dan Skenario

Pengguna tunggal: developer fullstack (Laravel, React, Flutter, NestJS, Python) yang mencari kerja remote internasional dan Indonesia. Pengguna menjalankan bot di laptop Windows atau Linux dengan Chrome terpasang.

**Skenario S1: Draft dengan fallback model.**
Pengguna menekan **Siapkan draft**. Bot mengirim prompt ke 9Router dengan model combo `loker-draft`. Model pertama kena rate limit. 9Router pindah ke model kedua. Draft masuk Telegram dengan label `llm:9router:glm/glm-5.1`.

**Skenario S2: Isi form Ashby lewat BrowserMCP.**
Pengguna menyetujui lamaran lalu menekan **Buka & isi form**. Chrome pengguna membuka tab baru ke `jobs.ashbyhq.com`. Bot membaca snapshot halaman, meminta LLM memetakan 14 field, lalu mengisi 11 field. Telegram menerima laporan: 11 terisi, 1 upload CV manual, 2 pertanyaan demografis dilewati. Pengguna mengecek, upload CV, menekan Submit, lalu mengetik `/dilamar <id>`.

**Skenario S3: 9Router mati.**
9Router tidak berjalan. Bot mencatat `llm_unreachable`, mencoba provider cadangan (Anthropic langsung jika key ada), lalu template. Telegram menampilkan peringatan satu kali per jam.

## 7. Gambaran Solusi

### 7.1 Diagram Komponen

```
Telegram  <-->  BotRunner (bot.py)
                   |
      +------------+-------------------+
      |                                |
 DraftService                    FormAgent (baru)
      |                                |
 LLMRouter (baru)  <-------------------+  (pemetaan field, jawaban kustom)
      |                                |
  +---+-----------+               McpBrowserClient (baru, stdio)
  |               |                    |
NineRouterProvider  AnthropicProvider  npx @browsermcp/mcp
  |                                    |
9Router :20128/v1                 Ekstensi BrowserMCP di Chrome pengguna
  |
Provider AI (Claude Code, Copilot, GLM, Kimi, tier gratis, dan lain-lain)
```

### 7.2 Prinsip Desain

1. **Interface lama tetap.** Provider LLM tetap callable `prompt -> str` agar `DraftService` dan test lama tidak berubah.
2. **LLM hanya merencanakan, kode yang mengeksekusi.** LLM mengembalikan rencana pengisian dalam JSON. Kode Python memvalidasi rencana, mengganti placeholder dengan data pribadi lokal, lalu memanggil tool BrowserMCP. LLM tidak pernah memanggil tool browser secara langsung.
3. **Data pribadi tidak keluar dari laptop.** LLM menerima label field dan menjawab dengan kunci seperti `{{applicant.email}}`. Nilai asli diisi oleh kode.
4. **Default aman.** Fitur baru mati secara default. Engine form lama (Playwright) tetap ada sebagai pilihan.
5. **Tanpa dependency wajib baru.** Klien 9Router memakai `urllib` seperti `llm.py`. Paket `mcp` masuk sebagai optional extra `[agent]`.

## 8. Fitur A: LLM Gateway lewat 9Router

### 8.1 Tentang 9Router

9Router adalah proxy AI open-source yang berjalan lokal. Setelah `npm install -g 9router` dan `9router`, dashboard terbuka di `http://localhost:20128/dashboard`. 9Router menyediakan endpoint OpenAI-compatible:

- `POST /v1/chat/completions`
- `GET /v1/models`

Autentikasi memakai API key dari dashboard dalam header `Authorization: Bearer <key>`. Nama model berformat `provider/model`, contoh `cc/claude-opus-4-7` atau `glm/glm-5.1`. Pengguna bisa membuat **combo**: daftar model berurutan yang dipakai bergantian saat kuota habis atau error.

### 8.2 Kebutuhan Fungsional

| ID | Kebutuhan | Prioritas |
|---|---|---|
| A-FR1 | Buat `OpenAICompatibleProvider` di `llm.py`. Kelas ini mengirim `messages` ke `{base_url}/chat/completions` dan mengembalikan `choices[0].message.content`. | P0 |
| A-FR2 | Provider menerima `base_url`, `api_key`, `model`, `max_tokens`, `temperature`, `timeout`. Tanpa library pihak ketiga. | P0 |
| A-FR3 | Tambah `LLM_PROVIDER` dengan nilai `template`, `anthropic`, atau `9router`. Nilai default `template` jika tidak ada key, sama seperti perilaku sekarang. | P0 |
| A-FR4 | Buat `LLMRouter` yang mencoba daftar provider berurutan: `9router` (model utama), `9router` (model cadangan di `NINEROUTER_FALLBACK_MODELS`), `anthropic` jika key ada. Template tetap ditangani `DraftService`. | P0 |
| A-FR5 | Error 401 dan 403 tidak di-retry dan langsung menandai provider `misconfigured`. Error 429, 5xx, dan timeout pindah ke model berikutnya. | P0 |
| A-FR6 | Catat provider dan model yang berhasil ke `applications.llm_provider` dan `applications.llm_model`. Nilai `method` menjadi `llm` atau `template` seperti sekarang. | P0 |
| A-FR7 | Command CLI `check-llm` memanggil `GET /v1/models`, mencetak jumlah model, dan mengirim satu prompt uji berisi 10 token. | P1 |
| A-FR8 | Telegram `/model` menampilkan provider aktif, model utama, dan status terakhir. `/model <nama>` mengganti model utama untuk sesi berjalan (tidak menulis ke `.env`). | P1 |
| A-FR9 | Routing per tugas: `LLM_MODEL_DRAFT` untuk cover letter, `LLM_MODEL_FORM` untuk pemetaan form, `LLM_MODEL_ANSWER` untuk jawaban pertanyaan terbuka. Jika kosong, semua memakai `NINEROUTER_MODEL`. | P1 |
| A-FR10 | Simpan metrik tiap panggilan di tabel `llm_calls`: tugas, provider, model, latensi, token, status, kode error. Isi prompt dan jawaban **tidak** disimpan. | P1 |
| A-FR11 | Mode `json` untuk tugas form: kirim `response_format: {"type": "json_object"}`. Jika model menolak parameter itu (HTTP 400), kirim ulang tanpa parameter dan parse JSON dari teks. | P1 |

### 8.3 Kontrak Request

```http
POST http://localhost:20128/v1/chat/completions
Authorization: Bearer <NINEROUTER_API_KEY>
Content-Type: application/json

{
  "model": "loker-draft",
  "messages": [
    {"role": "system", "content": "You write concise, truthful cover letters..."},
    {"role": "user", "content": "JOB DESCRIPTION: ...\n\nCANDIDATE SUMMARY: ..."}
  ],
  "max_tokens": 800,
  "temperature": 0.4,
  "stream": false
}
```

Isi `user` tetap berasal dari `build_cover_letter_prompt` dan `SafeCvProfile.to_summary()`. Tidak ada field baru yang masuk ke prompt.

### 8.4 Konfigurasi `.env` Baru

```env
# template | anthropic | 9router
LLM_PROVIDER=9router
NINEROUTER_BASE_URL=http://localhost:20128/v1
NINEROUTER_API_KEY=
# Nama model atau nama combo dari dashboard 9Router
NINEROUTER_MODEL=loker-draft
# Opsional, dipisah koma, dicoba berurutan jika model utama gagal
NINEROUTER_FALLBACK_MODELS=glm/glm-5.1,kr/claude-sonnet-4.5
LLM_TIMEOUT_SECONDS=60
LLM_MODEL_DRAFT=
LLM_MODEL_FORM=
LLM_MODEL_ANSWER=
```

Di Docker, `localhost` menunjuk ke container. Pengguna yang menjalankan bot di Docker dan 9Router di host memakai `http://host.docker.internal:20128/v1` dan menambah `extra_hosts` di `docker-compose.yml`.

### 8.5 Acceptance Criteria Fitur A

- [ ] Dengan `LLM_PROVIDER=9router` dan 9Router aktif, `/siapkan <job_id>` menghasilkan draft dengan `method=llm` dan `llm_provider=9router`.
- [ ] Jika model utama mengembalikan 429, draft dibuat oleh model cadangan pertama. Test memakai server HTTP palsu lokal.
- [ ] Jika 9Router mati dan Anthropic key kosong, draft memakai template dan log berisi `llm_fallback_to_template` dengan `error_code=network_error`.
- [ ] Error 401 tidak memicu retry. Test menghitung satu request saja.
- [ ] Log dan tabel `llm_calls` tidak berisi prompt, cover letter, atau API key. Test memeriksa isi log.
- [ ] Semua test lama di `test_cover_letter.py` dan `test_bot_pipeline.py` tetap lulus tanpa perubahan.

## 9. Fitur B: Pengisian Form lewat BrowserMCP

### 9.1 Tentang BrowserMCP

BrowserMCP terdiri dari dua bagian:

1. **Server MCP** (`@browsermcp/mcp`, dijalankan dengan `npx @browsermcp/mcp@latest`). Server berkomunikasi lewat stdio.
2. **Ekstensi Chrome.** Pengguna menekan **Connect** pada tab yang ingin dikendalikan. Otomasi berjalan di profil Chrome asli pengguna, termasuk sesi login.

Tool yang tersedia:

| Tool | Fungsi | Dipakai bot |
|---|---|---|
| `browser_navigate` | Buka URL | Ya |
| `browser_snapshot` | Ambil accessibility snapshot halaman beserta `ref` tiap elemen | Ya |
| `browser_type` | Ketik teks ke elemen (`element`, `ref`, `text`, `submit`) | Ya, `submit` selalu `false` |
| `browser_select_option` | Pilih opsi dropdown | Ya |
| `browser_click` | Klik elemen | Terbatas: checkbox, radio, tombol "Apply" pembuka form, tab form |
| `browser_hover` | Hover elemen | Tidak |
| `browser_press_key` | Tekan tombol keyboard | Terbatas: `Tab`, `Escape`. `Enter` diblokir |
| `browser_wait` | Tunggu beberapa detik | Ya |
| `browser_go_back`, `browser_go_forward` | Navigasi riwayat | Tidak |
| `browser_screenshot` | Screenshot | Tidak (risiko data pribadi) |
| `browser_get_console_logs` | Log konsol | Tidak |

**Batasan penting:** BrowserMCP tidak punya tool upload file. Upload CV tetap dilakukan pengguna, atau lewat engine Playwright lama.

### 9.2 Alur Pengisian

```
/isi <application_id>
  1. Cek status APPROVED dan host target ada di registry (Bagian 9.5)
  2. Start McpBrowserClient (stdio) -> list_tools, verifikasi 8 tool wajib ada
  3. browser_navigate(url)
  4. browser_snapshot -> FormExtractor mengubah snapshot jadi daftar field:
       {ref, label, role, required, options, current_value}
  5. Klasifikasi field (Bagian 9.3)
  6. FormPlanner mengirim label dan opsi (tanpa data pribadi) ke LLM -> rencana JSON
  7. PolicyGuard memvalidasi rencana (Bagian 9.4)
  8. Executor mengganti placeholder dengan nilai lokal, lalu memanggil
       browser_type / browser_select_option / browser_click satu per satu
  9. browser_snapshot ulang -> verifikasi nilai tiap field
 10. Jika form multi-halaman: berhenti, laporkan, pengguna menekan Next sendiri,
       lalu /isi-lanjut <id> mengulang langkah 4 sampai 9
 11. Kirim FillReport ke Telegram. Tab tetap terbuka. Bot tidak submit.
```

### 9.3 Klasifikasi Field dan Sumber Nilai

| Kelas | Contoh label | Sumber nilai | Aksi |
|---|---|---|---|
| Identitas | First name, Email, Phone | `data/applicant.json` | Isi otomatis |
| Tautan | LinkedIn, GitHub, Portfolio | `data/applicant.json` | Isi otomatis |
| Jawaban tersimpan | Work authorization, Notice period | `data/answers.json` (format baru, Bagian 9.6) | Isi otomatis |
| Cover letter | Cover letter, Additional information | `applications.cover_letter` | Isi otomatis |
| Pertanyaan terbuka | "Why do you want to work here?" | Draft LLM dari deskripsi lowongan dan `SafeCvProfile` | Isi, tandai **Dijawab AI, wajib cek** |
| Sensitif | Gender, Race, Veteran, Disability, EEO | Tidak ada | Selalu dilewati |
| Legal dan persetujuan | Privacy consent, "I certify...", data processing | Tidak ada | Selalu dilewati, diserahkan ke pengguna |
| Gaji | Expected salary, Current salary | `answers.json` jika ada | Isi hanya jika jawaban ada. Tidak pernah dari LLM |
| Upload | Resume, CV | Tidak didukung BrowserMCP | Masuk daftar manual |
| CAPTCHA | hCaptcha, reCAPTCHA, Turnstile | Tidak ada | Berhenti dan laporkan |

Klasifikasi Sensitif, Legal, dan CAPTCHA memakai daftar kata kunci di kode, **bukan** LLM. LLM tidak bisa membatalkan klasifikasi ini.

### 9.4 Kontrak Rencana dari LLM dan PolicyGuard

LLM menerima daftar field seperti ini:

```json
{
  "job_title": "Senior Backend Engineer",
  "fields": [
    {"ref": "e12", "label": "Email", "role": "textbox", "required": true},
    {"ref": "e19", "label": "Years of experience with Python", "role": "combobox",
     "options": ["0-1", "2-4", "5+"], "required": true}
  ],
  "available_keys": ["applicant.first_name", "applicant.email", "answers.notice_period",
                     "profile.years_python", "application.cover_letter"]
}
```

LLM wajib mengembalikan JSON:

```json
{
  "actions": [
    {"ref": "e12", "action": "type", "value": "{{applicant.email}}", "confidence": 0.98},
    {"ref": "e19", "action": "select", "value": "5+", "source": "profile.years_python",
     "confidence": 0.8}
  ],
  "skipped": [{"ref": "e30", "reason": "needs_user"}]
}
```

PolicyGuard menolak aksi jika salah satu syarat berikut terpenuhi:

1. `ref` tidak ada di snapshot terakhir.
2. Aksi `click` mengarah ke elemen dengan nama yang cocok dengan pola submit: `submit`, `apply`, `send`, `kirim`, `lamar`, `finish`, `complete`, `confirm`. Pengecualian hanya untuk tombol pembuka form yang terdaftar di registry ATS.
3. Aksi `type` dengan `submit=true`, atau aksi `press_key` dengan `Enter`.
4. Field berkelas Sensitif, Legal, CAPTCHA, atau Upload.
5. `value` berisi teks bebas untuk field Identitas. Field Identitas hanya boleh berisi placeholder.
6. Nilai `select` tidak ada di daftar `options`.
7. `confidence` di bawah `FORM_MIN_CONFIDENCE` (default 0.7).
8. Jumlah tool call melewati `FORM_MAX_TOOL_CALLS` (default 60) atau durasi melewati `FORM_TIMEOUT_SECONDS` (default 300).

Aksi yang ditolak masuk daftar **Perlu Anda isi/pilih** di laporan Telegram.

### 9.5 Registry ATS

Registry menggantikan konstanta `GREENHOUSE_HOSTS` dan `LEVER_HOSTS`. Registry disimpan di tabel `ats_registry` agar bisa ditambah tanpa ubah kode.

| ATS | Host | Mode awal | Catatan |
|---|---|---|---|
| Greenhouse | `job-boards.greenhouse.io`, `boards.greenhouse.io` | `auto_fill` | Sudah diuji dengan Playwright |
| Lever | `jobs.lever.co`, `jobs.eu.lever.co` | `auto_fill` | Upload CV memicu parser yang menimpa field. Isi field setelah pengguna upload |
| Ashby | `jobs.ashbyhq.com` | `auto_fill` setelah uji dry-run 3 form | Form satu halaman |
| Workable | `apply.workable.com` | `auto_fill` setelah uji dry-run 3 form | Ada tombol "Apply" pembuka form |
| SmartRecruiters | `jobs.smartrecruiters.com` | `assist` | Form multi-halaman |
| Kalibrr | `www.kalibrr.com` | `assist` | Butuh login kandidat di Chrome pengguna |
| Host lain | apa saja | `assist` | Butuh konfirmasi `/isi <id> paksa` |

Mode `auto_fill` mengisi semua aksi yang lolos PolicyGuard. Mode `assist` hanya mengisi Identitas, Tautan, dan Cover letter, lalu melaporkan sisanya.

### 9.6 Format Baru `data/answers.json`

Format lama (label ke teks) tetap didukung. Format baru menambah tipe dan opsi:

```json
{
  "version": 2,
  "answers": [
    {"key": "work_authorization", "match": ["legally authorized", "work authorization"],
     "type": "choice", "value": "Yes"},
    {"key": "notice_period", "match": ["notice period", "start date"],
     "type": "text", "value": "2 weeks"},
    {"key": "years_python", "match": ["years of experience with python"],
     "type": "number", "value": "5"},
    {"key": "expected_salary", "match": ["expected salary", "salary expectation"],
     "type": "text", "value": "Negotiable"}
  ]
}
```

LLM hanya melihat `key` dan `type`. Nilai untuk kelas Gaji dan Legal tidak pernah dikirim ke LLM.

### 9.7 Kebutuhan Fungsional

| ID | Kebutuhan | Prioritas |
|---|---|---|
| B-FR1 | Buat `McpBrowserClient` di modul baru `browser_mcp.py`. Klien menjalankan `BROWSER_MCP_COMMAND` lewat stdio dan memanggil tool dengan timeout per panggilan. | P0 |
| B-FR2 | Saat start, klien memanggil `list_tools` dan gagal dengan pesan jelas jika tool wajib tidak ada. | P0 |
| B-FR3 | Jika ekstensi belum terhubung, kirim pesan Telegram: "Buka Chrome, klik ikon BrowserMCP, tekan Connect, lalu ulangi /isi." | P0 |
| B-FR4 | Buat `FormExtractor` yang mengubah snapshot menjadi daftar field. Parser diuji dengan minimal 6 fixture snapshot (2 Greenhouse, 2 Lever, 1 Ashby, 1 Workable). | P0 |
| B-FR5 | Buat `FormPlanner` yang memanggil `LLMRouter` dengan tugas `form` dan mengembalikan rencana tervalidasi skema. | P0 |
| B-FR6 | Buat `PolicyGuard` sesuai Bagian 9.4. Guard berupa fungsi murni dan diuji tanpa browser. | P0 |
| B-FR7 | Buat `Executor` yang menjalankan aksi, mengganti placeholder secara lokal, lalu memverifikasi nilai dengan snapshot ulang. | P0 |
| B-FR8 | Tambah `FORM_ENGINE` dengan nilai `playwright` (default, perilaku sekarang) atau `browsermcp`. | P0 |
| B-FR9 | `FillReport` ditambah daftar **Dijawab AI, wajib cek** dan **Dilewati (sensitif/legal)**. | P0 |
| B-FR10 | Tambah command Telegram `/isi-lanjut <id>` untuk halaman berikutnya pada form multi-halaman. | P1 |
| B-FR11 | Pertanyaan terbuka dijawab LLM maksimal 120 kata, dalam bahasa yang sama dengan pertanyaan, hanya dari deskripsi lowongan dan `SafeCvProfile`. | P1 |
| B-FR12 | Opsi `FORM_AI_ANSWERS=off` mematikan pengisian pertanyaan terbuka. Default `review`: diisi dan ditandai. | P1 |
| B-FR13 | Simpan ringkasan sesi di `form_sessions` dan status tiap field di `form_field_events` tanpa nilai field. | P1 |
| B-FR14 | Command CLI `check-browser` memeriksa `npx`, menjalankan server, dan melaporkan status koneksi ekstensi. | P2 |

### 9.8 Konfigurasi `.env` Baru

```env
# playwright | browsermcp
FORM_ENGINE=browsermcp
BROWSER_MCP_COMMAND=npx -y @browsermcp/mcp@latest
FORM_MIN_CONFIDENCE=0.7
FORM_MAX_TOOL_CALLS=60
FORM_TIMEOUT_SECONDS=300
# off | review
FORM_AI_ANSWERS=review
```

`FORM_ASSIST_ENABLED=true` tetap wajib. Tanpa itu `/isi` menolak seperti sekarang.

### 9.9 Acceptance Criteria Fitur B

- [ ] Dengan `FORM_ENGINE=playwright`, semua test lama di `test_form_assist.py` lulus tanpa perubahan.
- [ ] Dengan `FORM_ENGINE=browsermcp`, form Greenhouse uji terisi minimal sebanyak field yang diisi engine Playwright (first name, last name, email, phone, cover letter, LinkedIn).
- [ ] Pada 3 form Ashby dan 3 form Workable dalam dry-run, minimal 80% field wajib non-upload terisi dengan benar.
- [ ] Test PolicyGuard membuktikan rencana berisi klik tombol "Submit application" ditolak.
- [ ] Test membuktikan `browser_type` tidak pernah dipanggil dengan `submit=true` dan `browser_press_key` tidak pernah dipanggil dengan `Enter`.
- [ ] Test memakai klien MCP palsu memastikan prompt ke LLM tidak berisi email, nomor telepon, atau nama dari `applicant.json`.
- [ ] Field Gender, Race, Veteran, dan Disability tidak pernah terisi di semua fixture.
- [ ] Jika snapshot mengandung iframe hCaptcha atau reCAPTCHA, laporan memuat "Ada CAPTCHA" dan tidak ada aksi setelah deteksi.
- [ ] Jika ekstensi belum Connect, pengguna menerima pesan B-FR3 dalam 20 detik.

## 10. Perubahan Data

Migrasi baru `migrations/002_llm_and_form_agent.sql`:

```sql
ALTER TABLE applications ADD COLUMN llm_provider TEXT;
ALTER TABLE applications ADD COLUMN llm_model TEXT;

CREATE TABLE IF NOT EXISTS llm_calls (
  id TEXT PRIMARY KEY,
  task TEXT NOT NULL,              -- draft | form | answer | health
  provider TEXT NOT NULL,          -- 9router | anthropic
  model TEXT NOT NULL,
  status TEXT NOT NULL,            -- success | error
  error_code TEXT,
  latency_ms INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  application_id TEXT REFERENCES applications(id),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS ats_registry (
  id TEXT PRIMARY KEY,
  ats_name TEXT NOT NULL,
  host TEXT NOT NULL UNIQUE,
  mode TEXT NOT NULL,              -- auto_fill | assist
  open_button_label TEXT,
  verified_at TEXT
);

CREATE TABLE IF NOT EXISTS form_sessions (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  engine TEXT NOT NULL,            -- playwright | browsermcp
  host TEXT NOT NULL,
  page_number INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL,            -- filled | partial | captcha | error | timeout
  filled_count INTEGER NOT NULL DEFAULT 0,
  manual_count INTEGER NOT NULL DEFAULT 0,
  ai_answer_count INTEGER NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS form_field_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES form_sessions(id),
  label TEXT NOT NULL,
  field_class TEXT NOT NULL,
  action TEXT NOT NULL,            -- filled | skipped | rejected | failed
  source TEXT,                     -- applicant | answers | cover_letter | llm
  reason TEXT
);
```

Tidak ada kolom yang menyimpan nilai field, isi prompt, atau jawaban LLM. Label field dipotong 80 karakter seperti `_UNFILLED_REQUIRED_JS` sekarang.

Status application tidak berubah. Pengisian form tidak mengubah status. Status berubah ke `SUBMITTED` hanya lewat `/dilamar`.

## 11. Dampak pada Kode

| File | Perubahan |
|---|---|
| `src/bot_loker_wfh/llm.py` | Tambah `OpenAICompatibleProvider`, `LLMRouter`, `LLMError` dengan kode error standar. |
| `src/bot_loker_wfh/config.py` | Tambah field Settings untuk Bagian 8.4 dan 9.8. |
| `src/bot_loker_wfh/__main__.py` | Pilih provider dari `LLM_PROVIDER`. Tambah `check-llm`, `check-browser`. `fill-form` memilih engine. |
| `src/bot_loker_wfh/drafts.py`, `cover_letter.py` | Simpan `llm_provider` dan `llm_model`. |
| `src/bot_loker_wfh/form_assist.py` | Pindahkan logika Playwright ke `form_engines/playwright_engine.py`. `ats_for_url` membaca `ats_registry`. |
| `src/bot_loker_wfh/browser_mcp.py` (baru) | `McpBrowserClient`. |
| `src/bot_loker_wfh/form_agent/` (baru) | `extractor.py`, `classifier.py`, `planner.py`, `policy.py`, `executor.py`. |
| `src/bot_loker_wfh/bot.py` | `/model`, `/isi-lanjut`, laporan baru. |
| `src/bot_loker_wfh/logging_utils.py` | Tambah field allowlist: `provider`, `model`, `engine`, `tool_calls`. |
| `pyproject.toml` | Extra baru `agent = ["mcp>=1.0"]`. |
| `.env.example`, `README.md` | Dokumentasi konfigurasi dan setup. |
| `tests/` | `test_llm_router.py`, `test_openai_provider.py`, `test_browser_mcp_client.py`, `test_form_policy.py`, `test_form_extractor.py`, `test_form_planner.py`, fixture snapshot. |

## 12. Kebutuhan Non-Fungsional

| Kategori | Kebutuhan |
|---|---|
| Performa | Draft cover letter lewat 9Router selesai di bawah 30 detik pada p95. Satu halaman form selesai diisi di bawah 90 detik pada p95. |
| Keandalan | Kegagalan 9Router atau BrowserMCP tidak menghentikan loop `run_forever`. Setiap error berakhir dengan pesan Telegram. |
| Keamanan | API key 9Router hanya dari `.env`. Tidak muncul di log, argumen command line, atau pesan Telegram. |
| Privasi | Prompt LLM hanya berisi deskripsi lowongan, `SafeCvProfile`, label field, opsi dropdown, dan nama kunci jawaban. |
| Keterlihatan | Semua event memakai `StructuredLogger` dengan `run_id`. Event baru: `llm_call`, `llm_fallback`, `form_session_start`, `form_action_rejected`, `form_session_end`. |
| Testabilitas | Semua test berjalan tanpa jaringan, tanpa 9Router, dan tanpa Chrome. Provider dan klien MCP bisa diganti objek palsu. |
| Kompatibilitas | Windows 10/11 dan Linux. Node.js 18 atau lebih baru untuk 9Router dan BrowserMCP. Python tetap 3.11. |

## 13. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| LLM mengarang jawaban (misalnya pengalaman palsu) | Lamaran tidak jujur | Pertanyaan terbuka hanya dari `SafeCvProfile`. Label **Dijawab AI, wajib cek**. Opsi `FORM_AI_ANSWERS=off`. |
| LLM menyuruh klik Submit | Lamaran terkirim tanpa review | PolicyGuard berbasis kode menolak pola submit. `Enter` dan `submit=true` diblokir di level klien. |
| Model di 9Router tidak mendukung JSON mode | Rencana form gagal di-parse | Retry tanpa `response_format`. Jika parse gagal dua kali, jatuh ke mode `assist`. |
| Provider gratis di 9Router mencatat prompt | Kebocoran konten | Prompt tidak berisi data pribadi. Pengguna memilih combo sendiri. README menjelaskan risiko ini. |
| Syarat layanan provider langganan (misalnya Claude Code, Copilot) melarang pemakaian lewat proxy | Akun provider diblokir | Pengguna bertanggung jawab memilih provider. README merekomendasikan provider berbasis API key resmi untuk pemakaian rutin. |
| Format snapshot BrowserMCP berubah antar versi | Extractor gagal | Kunci versi di `BROWSER_MCP_COMMAND` (misalnya `@browsermcp/mcp@0.1.3`). Fixture test per versi. |
| BrowserMCP bekerja di profil Chrome asli | Bot bisa menyentuh tab lain atau akun pengguna | Navigasi hanya ke host di registry. Tidak ada `go_back`, `screenshot`, atau `console_logs`. |
| Tidak ada tool upload file | CV tidak terlampir | Upload selalu masuk daftar manual. Engine Playwright tetap tersedia. |
| Form multi-halaman | Pengisian berhenti di halaman pertama | `/isi-lanjut`. Pengguna yang menekan Next. |
| Syarat layanan ATS | Risiko hukum | Keputusan NO-GO auto-submit tetap. Pengguna yang submit. Registry hanya berisi host yang sudah diuji. |

## 14. Rencana Fase dan Acceptance Criteria

### Fase 1: 9Router Provider (estimasi 3 sampai 4 hari)

Lingkup: A-FR1 sampai A-FR7, migrasi kolom `llm_provider` dan `llm_model`.

Selesai jika:
- [ ] Semua acceptance criteria Bagian 8.5 terpenuhi.
- [ ] `python -m bot_loker_wfh check-llm` berhasil pada 9Router lokal.
- [ ] README punya bagian "Menghubungkan 9Router".

### Fase 2: Routing Tugas dan Observabilitas LLM (estimasi 2 hari)

Lingkup: A-FR8 sampai A-FR11, tabel `llm_calls`, `/laporan` menampilkan jumlah panggilan per model dan rasio fallback.

Selesai jika:
- [ ] `/model` menampilkan model aktif dan status terakhir.
- [ ] `/laporan` menampilkan rasio draft LLM dibanding template 7 hari terakhir.

### Fase 3: Klien BrowserMCP dan Pengisian Deterministik (estimasi 5 sampai 7 hari)

Lingkup: B-FR1 sampai B-FR4, B-FR6 sampai B-FR9, registry ATS, tanpa LLM. Field diisi hanya dari kelas Identitas, Tautan, Jawaban tersimpan, dan Cover letter berdasarkan kecocokan label.

Selesai jika:
- [ ] Hasil pada Greenhouse dan Lever setara engine Playwright.
- [ ] Semua test PolicyGuard lulus.
- [ ] Dry-run 3 Ashby dan 3 Workable tercatat di `docs/browsermcp-dry-run.md`.

### Fase 4: FormPlanner dengan LLM (estimasi 5 hari)

Lingkup: B-FR5, B-FR10 sampai B-FR13, format baru `answers.json`.

Selesai jika:
- [ ] Semua acceptance criteria Bagian 9.9 terpenuhi.
- [ ] Rata-rata waktu isi manual per lamaran di bawah 3 menit pada 10 lamaran nyata (dicatat pengguna).

### Fase 5: Hardening (estimasi 2 sampai 3 hari)

Lingkup: B-FR14, penguncian versi BrowserMCP, dokumentasi risiko di `docs/auto-submit-risk-assessment.md`, uji Windows.

Selesai jika:
- [ ] `check-browser` berjalan di Windows dan Linux.
- [ ] Dokumen risiko diperbarui dengan bagian BrowserMCP dan 9Router.

## 15. Metrik Keberhasilan

Diukur dari tabel `applications`, `llm_calls`, dan `form_sessions` selama 4 minggu setelah Fase 4.

| Metrik | Baseline sekarang | Target |
|---|---|---|
| Draft dibuat LLM (bukan template) | Tergantung ada tidaknya Anthropic key | 95% atau lebih |
| Draft jatuh ke template karena error LLM | Belum diukur | Di bawah 5% |
| Field wajib non-upload terisi otomatis | Hanya Greenhouse dan Lever, sekitar 6 field standar | 80% atau lebih pada ATS `auto_fill` |
| ATS yang didukung | 2 | 6 (4 `auto_fill`, 2 `assist`) |
| Waktu isi form manual per lamaran | Sekitar 8 menit (estimasi pengguna) | Di bawah 3 menit |
| Klik Submit oleh bot | 0 | 0 |
| Data pribadi di prompt atau log | 0 | 0 |

## 16. Pertanyaan Terbuka

1. Apakah bot tetap berjalan di VPS Docker? Jika ya, perlu mode worker lokal yang mengambil tugas form dari VPS. Usulan: tunda ke PRD berikutnya dan jalankan `run-bot` di laptop saat butuh `/isi`.
2. Model combo mana yang dipakai untuk tugas `form`? Tugas ini butuh model yang stabil mengeluarkan JSON. Usulan: uji 3 model di Fase 4 dan catat tingkat keberhasilan parse.
3. Apakah jawaban AI untuk pertanyaan terbuka perlu approval Telegram sebelum diketik? Usulan awal: tidak, cukup label **wajib cek** karena pengguna tetap review sebelum Submit.
4. Apakah Kalibrr dan Dealls perlu mode `auto_fill`? Keduanya butuh login. Usulan: tetap `assist` sampai ada 3 dry-run berhasil.
5. Apakah Playwright tetap dipakai untuk upload CV dalam mode hibrida? Keduanya tidak bisa berbagi tab yang sama tanpa CDP. Usulan: tidak, upload tetap manual.

## 17. Lampiran

### 17.1 Setup Pengguna (Ringkas)

```bash
# 9Router
npm install -g 9router
9router                      # dashboard di http://localhost:20128/dashboard
# Di dashboard: hubungkan provider, buat combo "loker-draft", buat API key

# BrowserMCP
# 1. Pasang ekstensi BrowserMCP di Chrome
# 2. Buka tab kosong, klik ikon ekstensi, tekan Connect

# Bot
python -m pip install -e ".[agent]"
python -m bot_loker_wfh check-llm
python -m bot_loker_wfh check-browser
python -m bot_loker_wfh run-bot
```

### 17.2 Referensi

- 9Router: https://github.com/decolua/9router
- BrowserMCP: https://browsermcp.io dan https://github.com/BrowserMCP/mcp
- Paket npm BrowserMCP: https://www.npmjs.com/package/@browsermcp/mcp
- Model Context Protocol Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Keputusan auto-submit: `docs/auto-submit-risk-assessment.md`
- PRD MVP: `docs/PRD-v2-mvp.md`

Semua referensi diakses 30 September 2026. Cek ulang nama tool, port, dan format model sebelum Fase 1 dan Fase 3 dimulai.
