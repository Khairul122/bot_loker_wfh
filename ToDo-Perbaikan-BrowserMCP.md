# ToDo: Perbaikan Integrasi BrowserMCP

**Proyek:** Bot Loker WFH
**Basis kode:** `origin/main`, commit `c55d94c`
**Tanggal:** 30 September 2026
**Tujuan:** perintah `/isi <id>` membuka form di Chrome Anda lewat BrowserMCP, mengisi field dengan benar, lalu berhenti sebelum Submit.

---

## Ringkasan Masalah

Hasil uji klien proyek terhadap server asli `@browsermcp/mcp@0.1.3`:

| No | Masalah | Status bukti | File |
|---|---|---|---|
| 1 | `FORM_ENGINE` default `playwright`, belum ada di `.env.example` dan README | Terlihat di kode | `config.py`, `.env.example`, `README.md` |
| 2 | Respons `isError: true` dianggap sukses | Terbukti saat dijalankan | `browser_mcp.py` |
| 3 | Bot tidak menunggu ekstensi Chrome terhubung | Terbukti saat dijalankan | `browser_mcp.py`, `form_agent/agent.py` |
| 4 | Argumen wajib `element` tidak dikirim | Terbukti saat dijalankan | `form_agent/executor.py`, `form_agent/agent.py` |
| 5 | Parser snapshot menghasilkan 0 field | Terbukti saat dijalankan | `form_agent/extractor.py` |
| 6 | `npx` tidak ditemukan di Windows | Belum diuji di Windows | `browser_mcp.py` |
| 7 | Server dimatikan setiap sesi, port 9009 direbut | Terlihat di kode BrowserMCP | `form_agent/agent.py` |
| 8 | Tes hanya memakai klien palsu | Terlihat di kode | `tests/test_browser_mcp.py`, `tests/test_form_agent.py` |

Urutan kerja di bawah mengikuti prioritas. Kerjakan P0 dulu. Tanpa P0, BrowserMCP tidak akan pernah mengisi form.

---

## P0: Wajib Agar BrowserMCP Bisa Bekerja

### Task 1: Aktifkan engine BrowserMCP lewat konfigurasi

**File:** `.env`, `.env.example`, `README.md`

- [ ] Tambahkan ke `.env` lokal Anda:
  ```env
  FORM_ASSIST_ENABLED=true
  FORM_ENGINE=browsermcp
  BROWSER_MCP_COMMAND=npx -y @browsermcp/mcp@0.1.3
  ```
- [ ] Tambahkan semua variabel baru ke `.env.example` dengan komentar singkat: `FORM_ENGINE`, `BROWSER_MCP_COMMAND`, `FORM_MIN_CONFIDENCE`, `FORM_MAX_ACTIONS`, `FORM_MAX_TOOL_CALLS`, `FORM_TIMEOUT_SECONDS`, `FORM_AI_ANSWERS`, `LLM_PROVIDER`, `NINEROUTER_*`, `LLM_MODEL_*`.
- [ ] Tulis bagian README "Mengisi form dengan BrowserMCP": pasang Node.js 18+, pasang ekstensi BrowserMCP di Chrome, isi `.env`, jalankan `check-browser`, tekan Connect, lalu `/isi`.
- [ ] Saat `run-bot` start, cetak `form_engine=<nilai>` agar engine aktif terlihat di terminal.

**Selesai jika:**
- [ ] `python -m bot_loker_wfh` menampilkan `form_engine=browsermcp`.
- [ ] `/isi <id>` tidak lagi membuka Chromium baru dari Playwright.

---

### Task 2: Tangani `isError` dari server MCP

**File:** `src/bot_loker_wfh/browser_mcp.py`

- [ ] Di `call_tool()`, setelah menerima respons, periksa `result.get("isError")`.
- [ ] Jika `isError` bernilai `true`, ambil teks dari `result["content"][0]["text"]` lalu lempar `McpClientError` dengan teks itu.
- [ ] Buat subclass `McpNotConnectedError` jika teks mengandung `No connection to browser extension`.
- [ ] Tetap periksa kunci `error` untuk error level JSON-RPC.

**Selesai jika:**
- [ ] Tes: respons `{"result": {"isError": true, "content": [...]}}` memicu `McpClientError`.
- [ ] Tes: teks "No connection to browser extension" memicu `McpNotConnectedError`.

---

### Task 3: Tunggu ekstensi Chrome terhubung

**File:** `src/bot_loker_wfh/browser_mcp.py`, `src/bot_loker_wfh/form_agent/agent.py`

- [ ] Kirim notifikasi `notifications/initialized` setelah `initialize`, sesuai spesifikasi MCP.
- [ ] Tambahkan metode `wait_for_extension(timeout=20)`: panggil `browser_snapshot` berulang tiap 1 detik sampai tidak ada `McpNotConnectedError`.
- [ ] Panggil `wait_for_extension()` di `FormAgent.run_session()` sebelum `browser_navigate`.
- [ ] Sebelum menunggu, kirim pesan Telegram:
  "Buka Chrome, klik ikon BrowserMCP, tekan Connect. Bot menunggu 20 detik."
- [ ] Jika waktu habis, kirim:
  "Ekstensi BrowserMCP belum terhubung. Tekan Connect di Chrome, lalu ulangi /isi <id>."
- [ ] Tambahkan env `FORM_CONNECT_TIMEOUT_SECONDS` (default 20).

**Selesai jika:**
- [ ] Tanpa Connect, pengguna menerima pesan panduan dalam 25 detik.
- [ ] Setelah Connect, `browser_navigate` membuka URL lowongan di tab yang terhubung.

---

### Task 4: Kirim argumen `element` di semua tool

**File:** `src/bot_loker_wfh/form_agent/executor.py`, `src/bot_loker_wfh/form_agent/agent.py`

- [ ] `browser_type`: kirim `{"element": field.label or field.role, "ref": ..., "text": ..., "submit": False}`.
- [ ] `browser_select_option`: kirim `{"element": ..., "ref": ..., "values": [...]}`.
- [ ] `browser_click` untuk checkbox: kirim `{"element": ..., "ref": ...}`.
- [ ] `browser_click` untuk tombol pembuka form di `agent.py`: kirim `{"element": open_button_label, "ref": ...}`.
- [ ] Di `McpBrowserClient.call_tool()`, tolak panggilan `browser_type`, `browser_click`, `browser_select_option` yang tidak punya `element` atau `ref`, sebelum dikirim ke server.
- [ ] Event di `executor.py` hanya dicatat `filled` jika `call_tool` tidak melempar error. Jika error, catat `failed` dengan kode error.

**Selesai jika:**
- [ ] Tes: setiap panggilan ke klien palsu berisi `element` dan `ref`.
- [ ] Tes: error dari tool menghasilkan event `failed`, bukan `filled`.

---

### Task 5: Tulis ulang parser snapshot

**File:** `src/bot_loker_wfh/form_agent/extractor.py`

Format asli BrowserMCP:

```
- Page URL: https://job-boards.greenhouse.io/acme/jobs/1
- Page Title: Apply
- Page Snapshot
```yaml
- textbox "First Name*" [ref=s1e12]
- combobox "Country" [ref=s1e20]:
  - option "Indonesia" [ref=s1e21]
- checkbox "I agree" [ref=s1e30]
- button "Submit application" [ref=s1e40]
```
```

- [ ] Jika input berupa dict dengan kunci `content`, gabungkan semua `content[i].text` lalu parse sebagai teks.
- [ ] Ambil hanya bagian di dalam blok ```` ```yaml ```` jika ada.
- [ ] Parse tiap baris dengan pola: `- <role> "<label>" [atribut] [ref=<ref>]`.
- [ ] Ambil `role` dari kata pertama, `label` dari teks dalam tanda kutip, `ref` dari `[ref=...]`.
- [ ] Tandai `required` jika label berakhir `*` atau ada atribut `[required]`. Hapus `*` dari label.
- [ ] Ambil `current_value` dari teks setelah titik dua di akhir baris, jika ada.
- [ ] Kumpulkan baris `option` di bawah `combobox` atau `listbox` sebagai `options` milik field induknya.
- [ ] Gabungkan `radio` dengan nama grup yang sama menjadi satu field dengan daftar opsi.
- [ ] Simpan `page_url` dari baris `Page URL` untuk deteksi pindah halaman.

**Selesai jika:**
- [ ] Contoh snapshot di atas menghasilkan 4 field dengan label, role, dan ref yang benar.
- [ ] `combobox "Country"` punya opsi `("Indonesia",)`.
- [ ] `First Name` bertanda `required=True`.

---

### Task 6: Perbaiki start `npx` di Windows

**File:** `src/bot_loker_wfh/browser_mcp.py`

- [ ] Pecah perintah dengan `shlex.split(self.command, posix=(os.name != "nt"))`.
- [ ] Cari path program dengan `shutil.which(args[0])`. Di Windows, `which("npx")` menemukan `npx.cmd`.
- [ ] Jika tidak ditemukan, lempar `McpClientError("Node.js/npx tidak ditemukan. Pasang Node.js 18+.")`.
- [ ] Baca `stderr` di thread terpisah agar buffer tidak penuh. Simpan 20 baris terakhir untuk pesan error, tanpa menulis ke log.
- [ ] Ganti `readline()` yang bisa menunggu tanpa batas dengan thread pembaca dan `queue.get(timeout=...)`.
- [ ] Beri timeout lebih panjang (60 detik) untuk `initialize` pertama, karena `npx -y` bisa sedang mengunduh paket.

**Selesai jika:**
- [ ] `python -m bot_loker_wfh check-browser` berhasil di Windows dan Linux.
- [ ] Server yang diam tidak membuat bot menunggu lebih dari timeout.

---

## P1: Stabilitas dan Pengalaman Pengguna

### Task 7: Jaga koneksi ekstensi tetap hidup

**File:** `src/bot_loker_wfh/form_agent/agent.py`, `src/bot_loker_wfh/bot.py`

- [ ] Pilih satu pendekatan:
  - [ ] **Opsi A (disarankan):** jalankan satu `McpBrowserClient` bersama selama `run-bot` hidup. Proses `fill-form` tidak lagi membuat server baru.
  - [ ] **Opsi B:** tetap satu server per sesi, tapi jangan panggil `client.stop()` sampai pengguna mengetik `/dilamar` atau 10 menit berlalu.
- [ ] Tulis di README: jangan jalankan BrowserMCP dari Claude Desktop atau Cursor bersamaan, karena keduanya memakai port 9009 dan saling mematikan.
- [ ] `check-browser` memeriksa apakah port 9009 sudah dipakai proses lain dan memberi peringatan.

**Selesai jika:**
- [ ] `/isi` lalu `/isilanjut` pada lamaran yang sama tidak meminta Connect ulang.

---

### Task 8: Kirim status proses ke Telegram

**File:** `src/bot_loker_wfh/bot.py`, `src/bot_loker_wfh/__main__.py`

- [ ] Jangan buang output subprocess `fill-form` ke `DEVNULL`. Arahkan ke `data/logs/fill-form.log` yang hanya berisi event terstruktur tanpa data pribadi.
- [ ] Kirim pesan bertahap: "Menyalakan BrowserMCP...", "Menunggu Connect...", "Membuka form...", "Mengisi 12 field...".
- [ ] Jika subprocess keluar dengan kode bukan 0 tanpa pesan, kirim "Pengisian form gagal. Lihat data/logs/fill-form.log."

**Selesai jika:**
- [ ] Setiap `/isi` selalu berakhir dengan satu pesan hasil, sukses atau gagal.

---

### Task 9: Verifikasi hasil isi

**File:** `src/bot_loker_wfh/form_agent/executor.py`

- [ ] Setelah semua aksi, ambil `browser_snapshot` ulang.
- [ ] Bandingkan `current_value` tiap field dengan nilai yang diketik.
- [ ] Field yang tidak cocok: coba sekali lagi, lalu tandai `verify_failed` dan masukkan ke daftar manual.
- [ ] Jika `Page URL` berubah di tengah eksekusi, hentikan sesi dengan status `navigation_changed`.

**Selesai jika:**
- [ ] Laporan Telegram hanya menyebut "Terisi" untuk field yang benar-benar terisi.

---

### Task 10: Perbaiki kebocoran konteks di perencana

**File:** `src/bot_loker_wfh/form_agent/agent.py`

- [ ] `candidate_summary` sekarang diisi `resolver.cover_letter`. Ganti dengan `SafeCvProfile.to_summary()` yang dimuat dari `PROFILE_PATH`.
- [ ] Pastikan `generate_answer()` juga memakai ringkasan profil, bukan cover letter.

**Selesai jika:**
- [ ] Tes: prompt ke LLM berisi ringkasan profil dan tidak berisi isi cover letter.

---

## P2: Pengujian dengan Format Asli

### Task 11: Fixture snapshot asli

**Folder:** `tests/fixtures/browsermcp/`

- [ ] Rekam snapshot asli dari 6 form: 2 Greenhouse, 2 Lever, 1 Ashby, 1 Workable. Hapus data pribadi sebelum disimpan.
- [ ] Simpan respons error asli: `no_connection.json`, `missing_element.json`.
- [ ] Tes `FormExtractor` memakai semua fixture ini.

### Task 12: Tes klien dengan server palsu yang meniru BrowserMCP

**File:** `tests/test_browser_mcp.py`

- [ ] Buat skrip Python kecil sebagai server MCP palsu lewat stdio yang:
  - menjawab `initialize` dan `tools/list`,
  - mengembalikan `isError: true` dengan teks "No connection" untuk N panggilan pertama,
  - menolak `browser_type` tanpa `element`,
  - mengembalikan snapshot dari fixture.
- [ ] Tes alur penuh `FormAgent.run_session()` terhadap server palsu ini.
- [ ] Hapus fallback `{"result": {}}` di `_send_request` saat proses tidak ada. Ganti dengan error. Klien palsu di tes memakai `custom_client`.

### Task 13: Uji manual end-to-end

- [ ] Jalankan `run-bot` di laptop dengan Chrome.
- [ ] Setujui satu lowongan Greenhouse, jalankan `/isi <id>`, tekan Connect.
- [ ] Catat: jumlah field terisi, field manual, waktu total, kesalahan isi.
- [ ] Ulangi untuk Lever, Ashby, Workable.
- [ ] Tulis hasil di `docs/browsermcp-dry-run.md`.
- [ ] Pastikan tidak ada satu pun form yang terkirim otomatis.

---

## Checklist Lingkungan Sebelum Tes

- [ ] Node.js 18+ terpasang: `node --version`
- [ ] `npx` bisa dipanggil: `npx --version`
- [ ] Ekstensi BrowserMCP terpasang di Chrome
- [ ] `.env` berisi `FORM_ASSIST_ENABLED=true` dan `FORM_ENGINE=browsermcp`
- [ ] `data/applicant.json` dan `data/answers.json` sudah diisi
- [ ] `run-bot` berjalan di laptop, bukan di VPS atau Docker
- [ ] Tidak ada instance bot lain yang memakai token Telegram yang sama
- [ ] Claude Desktop atau Cursor tidak sedang menjalankan BrowserMCP

---

## Definition of Done

- [ ] Task 1 sampai Task 6 selesai dan tesnya lulus.
- [ ] `python -m pytest` lulus tanpa jaringan dan tanpa Chrome.
- [ ] `/isi <id>` pada form Greenhouse mengisi minimal: First Name, Last Name, Email, Phone, LinkedIn, Cover letter.
- [ ] Tanpa Connect, pengguna menerima panduan, bukan laporan palsu "Terisi".
- [ ] Laporan Telegram hanya menyebut field yang benar-benar terisi.
- [ ] Bot tidak pernah menekan Submit.

---

## Estimasi

| Prioritas | Task | Estimasi |
|---|---|---|
| P0 | 1 sampai 6 | 2 sampai 3 hari |
| P1 | 7 sampai 10 | 1,5 sampai 2 hari |
| P2 | 11 sampai 13 | 1,5 hari |
| **Total** | | **5 sampai 6,5 hari kerja** |
