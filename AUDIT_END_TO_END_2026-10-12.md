# Audit End-to-End Bot Loker WFH — 12 Oktober 2026

## Kesimpulan

Proyek berfungsi dan fondasinya cukup matang: 331 tes lulus, modul dapat dikompilasi, Office 3D berhasil dijalankan, data uji melewati alur database → API → UI, rapat template selesai, papan proyek memuat data, dan approve lamaran dummy berhasil. Namun proyek **belum aman untuk dianggap production-ready** karena dua temuan kritis pada kontrol akses server lokal dan pengendalian trafik eksternal.

Audit menggunakan schema Supabase terisolasi `t_e2e_audit_20261012`, provider LLM `template`, `FORM_ASSIST_ENABLED=false`, dan `EXTERNAL_JOBS_ENABLED=false`. Tidak ada lamaran atau bid nyata yang dikirim.

## Temuan Prioritas

### CRITICAL-1 — Server Office menerima Origin WebSocket asing dan POST dapat dilewati lewat DNS rebinding

- `GET /ws` dengan `Origin: http://attacker.invalid` memperoleh `101 Switching Protocols`.
- POST ke loopback dengan `Host: evil.test:8766` dan Origin yang sama lolos pemeriksaan Origin; endpoint mengembalikan validasi bisnis `400 unknown_setting`, bukan `403 forbidden`.
- WebSocket tidak melakukan pemeriksaan Origin. Pemeriksaan POST mempercayai header `Host`, sehingga attacker yang mengendalikan DNS dapat membuat Origin dan Host tampak sama saat koneksi sebenarnya menuju loopback.
- Dampak: situs berbahaya berpotensi membaca event Office dan memicu endpoint lokal seperti pengaturan, auto mode, rapat, keputusan inbox, dan aksi lead.
- Lokasi utama: `src/bot_loker_wfh/office_server.py` sekitar baris 370–413 dan 516–527.

### CRITICAL-2 — `EXTERNAL_JOBS_ENABLED=false` tidak mencegah pengambilan lead eksternal

- Saat Office dibuka dengan flag tersebut bernilai false, preferensi auto mengaktifkan putaran kerja dan benar-benar memanggil Freelancer.com, Projects.co.id, serta PeoplePerHour.
- Bukti run terisolasi: 130 lead Freelancer, 3 Projects.co.id, dan 3 PeoplePerHour diambil melalui jaringan dan disimpan ke schema uji.
- `_office_hunters` hanya membatasi hunter lowongan kerja; hunter lead selalu didaftarkan. UI juga menyalakan auto saat `prefs.auto !== '0'`.
- Dampak: membuka UI dapat menghasilkan trafik eksternal dan mutasi database yang bertentangan dengan konfigurasi dan dokumentasi safety.
- Lokasi utama: `src/bot_loker_wfh/__main__.py` sekitar baris 429–447 dan `src/bot_loker_wfh/office/js/main.js` sekitar baris 64–73.

### HIGH-1 — Callback Telegram lead yang basi dapat mengubah kembali status terkunci

- Jalur `LeadService.set_status` menulis status tanpa memanggil `ensure_open`.
- Jalur Office yang lebih baru sudah mengunci `APPROVED`/`SUBMITTED`, tetapi callback lama dapat melewati invariant tersebut.
- Dampak: callback replay/stale dapat mengubah bid yang sedang dikirim atau sudah dikirim, bertentangan dengan klaim README bahwa callback basi tidak berefek.
- Lokasi utama: `src/bot_loker_wfh/leads.py` sekitar baris 603 dan `src/bot_loker_wfh/lead_desk.py` sekitar baris 26–39.

### HIGH-2 — Flag eksternal juga dapat dilewati melalui CLI sumber-spesifik

- Perintah `fetch-remoteok`, `fetch-remotive`, `fetch-greenhouse`, `fetch-lever`, `fetch-kalibrr`, `fetch-dealls`, dan `fetch-once` memanggil fetcher tanpa guard global yang konsisten.
- Dampak: operator dapat mengira flag global mematikan seluruh API eksternal, padahal beberapa entry point tetap aktif.
- Lokasi utama: `src/bot_loker_wfh/__main__.py` sekitar baris 115–165.

### HIGH-3 — Kredensial Supabase yang pernah terekspos belum tercatat sudah dirotasi

- Catatan proyek menyebut password Supabase pernah muncul pada traceback dan item rotasi masih terbuka.
- Ini bukan bukti bahwa credential saat ini bocor, tetapi sampai rotasi diverifikasi, credential lama harus dianggap terkompromi.
- Lokasi: `tasks/todo_analisis_2026-10-11.md` sekitar baris 14.

### MEDIUM-1 — Transisi status aplikasi tidak atomik

- Implementasi membaca status, memvalidasi di Python, lalu melakukan UPDATE tanpa kondisi `WHERE status = ?` atau lock baris.
- Dua worker dapat sama-sama lolos validasi berdasarkan status lama dan menghasilkan perubahan/history yang tidak konsisten.
- Bandingkan dengan klaim atomik pada alur bid yang sudah memakai conditional UPDATE.
- Lokasi: `src/bot_loker_wfh/status_transitions.py` sekitar baris 60–96.

### MEDIUM-2 — Startup Office lambat dan serial

- Loader baru hilang setelah kira-kira 30 detik pada run audit.
- Boot menunggu `loadStats`, `restorePositions`, dan `loadPrefs` secara berurutan sebelum merender aplikasi; panel board memerlukan hingga sekitar 10 detik untuk selesai memuat.
- Dampak: UI tampak macet dan rentan terhadap satu dependency lambat.
- Lokasi: `src/bot_loker_wfh/office/js/main.js` sekitar baris 64–76.

### MEDIUM-3 — File orkestrasi terlalu besar dan memusatkan banyak tanggung jawab

- `office_server.py` sekitar 828 baris, `__main__.py` sekitar 706 baris, dan `leads.py` sekitar 651 baris.
- Ini bukan bug langsung, tetapi meningkatkan risiko regression pada routing, CLI, integrasi eksternal, dan state machine.

### LOW-1 — UX penyimpanan pengaturan tidak konsisten

- Penyimpanan satu field memberi tahu bahwa restart dibutuhkan; tombol Simpan Semua hanya menyatakan data tersimpan di Supabase.
- `onchange` juga menyimpan field satu per satu, sehingga konsep dirty/batch-save membingungkan.
- Lokasi: `src/bot_loker_wfh/office/js/ui/settings.js` sekitar baris 327–363.

## Audit Fitur

| Area | Hasil | Bukti/cakupan |
|---|---|---|
| Database & migrasi | PASS | Schema uji dapat dibuat/dipakai; CRUD lintas jobs, applications, leads, reports berjalan. |
| Fetcher lowongan | PASS bersyarat | Parser dan penyimpanan tercakup tes; live vendor tidak dipanggil dalam audit aman. Guard global memiliki celah. |
| Screening & scoring | PASS | Data dummy masuk ke status kandidat/filter dan tampil pada statistik. |
| Draft cover letter | PASS | Jalur template/offline dan inbox terisi; provider 9Router nyata tidak diuji. |
| Approval lamaran | PASS | Klik approve untuk aplikasi dummy berhasil menjadi aksi server; tidak membuka atau submit situs eksternal. |
| Form assist | PASS bersyarat | Policy/tes tersedia; BrowserMCP nyata dan submit akhir sengaja tidak dijalankan. |
| Lead freelance | PASS dengan risiko | Papan memuat, filter/status/draf tampil; fetch live justru membuktikan pelanggaran flag eksternal. |
| Pengiriman bid | PASS bersyarat | Guard host, claim atomik, dan tes tersedia; bid nyata tidak dikirim. |
| Auto-bid | Tidak dieksekusi | Sengaja tidak mengirim bid nyata; konfigurasi dan jalur kode ditinjau. |
| Telegram | PASS bersyarat | Allowlist dan alur diuji oleh suite; token/chat nyata tidak dipakai. Celah callback lead ditemukan. |
| GitHub portfolio | PASS bersyarat | Modul/tes ditinjau; sinkronisasi akun nyata tidak dijalankan. |
| Meeting | PASS | POST meeting lokal dengan dua peserta selesai memakai provider template. |
| Reports, ratings, instructions | PASS | Endpoint/UI dan data schema uji tampil. |
| Office 3D | PASS fungsional | Desktop/tablet/mobile, tema, panel, keyboard, responsive, dan populated state diuji; temuan aksesibilitas terpisah. |
| CLI | PASS | Parser/help memuat seluruh entry point tanpa error. |
| Retention/deployment | PASS bersyarat | Ditinjau melalui kode dan tes; Docker production tidak dideploy. |

## Audit Tampilan dan Aksesibilitas

Detail bernomor ada di `anti-slop/audit-001-2026-10-12.md`. Ringkasannya:

- Identitas visual 3D kuat dan spesifik; desktop terlihat matang dan bukan dashboard generik.
- Pada mobile 390 px, lima aksi utama berada di luar sisi kiri dan tidak dapat digulir kembali.
- Dialog tidak memindahkan atau menahan fokus; Tab langsung masuk ke kontrol belakang overlay.
- 18 kontrol terlihat memiliki target sentuh di bawah 44×44 px.
- Tiga kombinasi warna gagal WCAG AA: 4.34:1, 3.68:1, dan 2.54:1.
- Tab pengaturan, label form, landmark utama, dan sebagian semantik dialog belum lengkap.
- `prefers-reduced-motion` tidak menghentikan motion aplikasi.
- Tidak ditemukan horizontal page overflow pada 768, 390, atau 320 px; tema terang dan gelap sama-sama berfungsi.

## Verifikasi yang Dijalankan

- `python -m pytest -q -n 8` → **331 passed** dalam 149.19 detik.
- `python -m compileall -q src` → **PASS**.
- Playwright Chromium 153: desktop 1440×900, tablet 768×1024, mobile 390×844, narrow 320×700, tema malam, semua panel utama, tab setting, navigasi keyboard, dan state populated.
- Endpoint lokal: meeting 200, invalid setting 400, approve aplikasi dummy berhasil, board selesai memuat.
- Probe keamanan manual: DNS-rebinding-shaped POST dan cross-Origin WebSocket.
- Kontras dihitung memakai checker `antislop-human`, bukan penilaian visual.

## Batas Audit

“100%” di sini berarti seluruh komponen, entry point, test suite, UI utama, dan alur lokal diperiksa. Audit tidak melakukan tindakan yang dapat merugikan akun eksternal: tidak men-submit lamaran, tidak mengirim bid, tidak mengirim Telegram nyata, tidak memakai token vendor produksi, dan tidak melakukan deployment production. Oleh karena itu integrasi vendor akhir berstatus **PASS bersyarat**, bukan tervalidasi live sampai titik submit.
