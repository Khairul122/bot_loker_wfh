# ToDo: Bot Auto-Apply Kerja WFH Internasional

Dokumen ini mengubah `PRD.md` menjadi daftar kerja berurutan. Fokus awal adalah memperbaiki spesifikasi yang masih ambigu, lalu membangun MVP yang aman: sourcing lowongan, deduplication, eligibility, review Telegram, dan tracking manual. Auto-submit, LLM, embedding, dan dashboard ditunda sampai fondasi stabil.

## Prinsip Eksekusi

- [x] Kerjakan P0 sebelum menulis kode fitur utama.
- [x] Setiap task dianggap selesai hanya jika acceptance criteria dan verification terpenuhi.
- [x] Jangan implementasikan auto-submit sebelum ambiguity, idempotency, dan verifikasi submission selesai.
- [x] Jangan kirim data pribadi penuh ke LLM; gunakan ringkasan CV yang disanitasi.
- [x] Semua perubahan status harus melalui fungsi transisi terpusat.

---

## P0 — Perbaikan PRD Sebelum Coding

### Task 1: Pisahkan state machine `jobs` dan `applications`

**Deskripsi:** Perjelas status mana yang dimiliki lowongan dan mana yang dimiliki lamaran agar implementasi database, service, dan Telegram tidak saling bertentangan.

**Acceptance criteria:**
- [x] `jobs` hanya memiliki status seperti `DISCOVERED`, `CANDIDATE`, `FILTERED_OUT`.
- [x] `applications` memiliki status seperti `DRAFT_READY`, `PENDING_APPROVAL`, `APPROVED`, `SUBMITTING`, `SUBMITTED`, `SUBMIT_FAILED`, `SUBMISSION_AMBIGUOUS`, `INTERVIEW`, `OFFER`, `REJECTED_BY_COMPANY`, `NO_RESPONSE`, `WITHDRAWN`.
- [x] Tabel transisi dipisah untuk job lifecycle dan application lifecycle.

**Verification:**
- [x] Baca ulang `PRD.md` dan pastikan tidak ada kalimat yang menyebut satu lifecycle gabungan untuk job dan application.

**Dependencies:** None  
**Estimated scope:** S

### Task 2: Tetapkan strategi deduplication lintas sumber

**Deskripsi:** Perbaiki kontradiksi fingerprint yang saat ini menyertakan `source` tetapi diklaim mencegah duplikasi lintas sumber.

**Acceptance criteria:**
- [x] Ada `source_external_key` atau constraint setara untuk dedup per sumber.
- [x] Ada `canonical_fingerprint` untuk dedup lintas sumber tanpa memasukkan `source`.
- [x] Aturan normalisasi title, company, dan apply URL terdokumentasi.
- [x] Perilaku saat fingerprint mirip tetapi tidak identik ditentukan: auto-merge, simpan terpisah, atau review manual.

**Verification:**
- [x] Buat 5 contoh lowongan duplikat lintas sumber dan tulis expected result-nya di PRD atau dokumen test case.

**Dependencies:** None  
**Estimated scope:** S

### Task 3: Definisikan perilaku `SUBMISSION_AMBIGUOUS`

**Deskripsi:** Tambahkan status khusus untuk kondisi submit mungkin berhasil tetapi sistem tidak bisa memverifikasi karena crash, timeout, atau koneksi putus setelah tombol submit diklik.

**Acceptance criteria:**
- [x] `SUBMISSION_AMBIGUOUS` masuk ke lifecycle application.
- [x] Retry otomatis dilarang dari status `SUBMISSION_AMBIGUOUS`.
- [x] Pengguna harus melakukan verifikasi manual sebelum status berubah ke `SUBMITTED`, `SUBMIT_FAILED`, atau `APPROVED` untuk retry.
- [x] Acceptance criteria Fase 3 direvisi agar tidak menjanjikan hal yang tidak bisa dijamin oleh sistem setelah crash.

**Verification:**
- [x] Skenario crash setelah klik submit punya expected transition yang jelas.

**Dependencies:** Task 1  
**Estimated scope:** S

### Task 4: Perjelas aturan bisnis satu lamaran

**Deskripsi:** Putuskan apakah sistem mencegah duplicate application per lowongan, per perusahaan, atau per perusahaan dalam periode tertentu.

**Acceptance criteria:**
- [x] Aturan `one application per job` tertulis eksplisit; belum ada aturan `one application per company within N days` pada MVP.
- [x] Constraint database yang dibutuhkan ditentukan: `UNIQUE (job_id)` dan `UNIQUE (idempotency_key)`.
- [x] Perilaku untuk dua posisi berbeda di perusahaan yang sama dijelaskan: dua application boleh dibuat.

**Verification:**
- [x] Ada minimal 3 contoh: job sama, company sama posisi beda, dan variasi nama company untuk job sama.

**Dependencies:** Task 2  
**Estimated scope:** S

### Task 5: Perjelas alur MVP tanpa LLM

**Deskripsi:** Fase 1 belum memakai LLM tetapi lifecycle saat ini mengharuskan `DRAFT_READY`. Tentukan bagaimana draft manual dibuat dan kapan application dibuat.

**Acceptance criteria:**
- [x] Alur MVP dari `CANDIDATE` sampai `PENDING_APPROVAL` terdokumentasi.
- [x] Dijelaskan apakah Telegram mengirim lowongan saja atau juga draft cover letter manual.
- [x] `cover_letter` dan `cv_summary` wajib diisi pada MVP sebelum application dibuat.

**Verification:**
- [x] Acceptance criteria Fase 1 konsisten dengan alur MVP baru.

**Dependencies:** Task 1  
**Estimated scope:** S

### Checkpoint: PRD Build-Ready

- [x] Semua task P0 selesai.
- [x] `PRD.md` tidak memiliki konflik state, dedup, dan idempotency.
- [x] Scope MVP disetujui sebelum mulai implementasi.

---

## P1 — Fondasi MVP

### Task 6: Scaffold proyek Python

**Deskripsi:** Buat struktur proyek minimal untuk service fetcher, eligibility, database, Telegram bot, dan tests.

**Acceptance criteria:**
- [x] Ada struktur folder untuk `src`, `tests`, konfigurasi, dan migration/schema.
- [x] Dependency manager dipilih dan terdokumentasi.
- [x] Perintah test dan run lokal terdokumentasi.

**Verification:**
- [x] Test kosong/smoke test berjalan sukses.
- [x] Aplikasi bisa start tanpa menjalankan job eksternal.

**Dependencies:** Checkpoint PRD Build-Ready  
**Estimated scope:** M

### Task 7: Implementasi schema database MVP

**Deskripsi:** Buat schema untuk `jobs`, `applications`, `application_status_history`, `filters`, dan `company_blocklist` sesuai PRD yang sudah direvisi.

**Acceptance criteria:**
- [x] Unique constraint dedup per sumber dan canonical fingerprint tersedia.
- [x] `applications.job_id` unique jika aturan bisnis tetap satu application per job.
- [x] Timestamp disimpan timezone-aware atau memakai UTC secara konsisten.
- [x] Seed/default filter tersedia.

**Verification:**
- [x] Test constraint duplicate job dan duplicate application berjalan.
- [x] Migration/schema bisa dibuat dari database kosong.

**Dependencies:** Task 6  
**Estimated scope:** M

### Task 8: Implementasi status transition service

**Deskripsi:** Buat fungsi tunggal untuk mengubah status job dan application berdasarkan transition table.

**Acceptance criteria:**
- [x] Transisi valid diterima dan tercatat di `application_status_history` untuk application.
- [x] Transisi invalid ditolak dengan error yang jelas.
- [x] Tidak ada update status langsung di luar transition service.

**Verification:**
- [x] Unit test mencakup transisi valid, invalid, terminal state, dan manual correction policy.

**Dependencies:** Task 7  
**Estimated scope:** M

### Task 9: Implementasi fetcher RemoteOK

**Deskripsi:** Ambil lowongan dari RemoteOK, normalisasi ke model internal, lalu simpan tanpa duplikasi.

**Acceptance criteria:**
- [x] Fetcher membaca data RemoteOK dan menyimpan job baru.
- [x] Fetch kedua dengan data sama tidak menambah row baru.
- [x] Error jaringan ditangani dengan retry terbatas.
- [x] Atribusi sumber RemoteOK disimpan.

**Verification:**
- [x] Test dengan fixture RemoteOK.
- [x] Manual run fetcher tidak membuat duplikasi.

**Dependencies:** Task 7  
**Estimated scope:** M

### Task 10: Implementasi fetcher Remotive

**Deskripsi:** Ambil lowongan dari Remotive, normalisasi ke model internal, lalu simpan tanpa duplikasi.

**Acceptance criteria:**
- [x] Fetcher membaca data Remotive dan menyimpan job baru.
- [x] Fetch kedua dengan data sama tidak menambah row baru.
- [x] Format salary, tags, location, dan apply URL dinormalisasi semampunya.

**Verification:**
- [x] Test dengan fixture Remotive.
- [x] Manual run fetcher tidak membuat duplikasi.

**Dependencies:** Task 7  
**Estimated scope:** M

### Task 11: Implementasi scheduler MVP

**Deskripsi:** Jalankan fetcher secara berkala dengan interval minimal empat jam dan tetap bisa dipicu manual untuk pengembangan.

**Acceptance criteria:**
- [x] Scheduler bisa menjalankan RemoteOK dan Remotive.
- [x] Interval default minimal empat jam.
- [x] Manual one-shot run tersedia.
- [x] Log hanya berisi metadata, bukan deskripsi lengkap atau data sensitif.

**Verification:**
- [x] Test konfigurasi interval.
- [x] Manual one-shot run berhasil.

**Dependencies:** Task 9, Task 10  
**Estimated scope:** S

### Checkpoint: Sourcing MVP

- [x] Database kosong bisa diisi dari fixture.
- [x] Fetch berulang tidak menghasilkan duplikasi.
- [x] Log tidak mencetak data pribadi atau cover letter.

---

## P1 — Eligibility dan Review Manual

### Task 12: Implementasi eligibility engine berbasis rule

**Deskripsi:** Evaluasi lowongan berdasarkan remote type, region restriction, role keyword, exclusion keyword, blocklist, posting age, dan rule unknown/review.

**Acceptance criteria:**
- [x] Rule dievaluasi berurutan sesuai PRD.
- [x] Job gagal diberi status `FILTERED_OUT` dan reason code.
- [x] Job lolos diberi status `CANDIDATE`.
- [x] Pada MVP, job dengan data tidak cukup diberi `FILTERED_OUT` dengan reason code eksplisit; `REVIEW_REQUIRED` ditunda karena belum ada di state machine.

**Verification:**
- [x] Unit test minimal 20 sample lowongan.
- [x] Test mencakup remote terbatas region, unpaid, old posting, blocklist, role mismatch, dan missing posted date.

**Dependencies:** Task 8  
**Estimated scope:** M

### Task 13: Implementasi konfigurasi filter

**Deskripsi:** Buat mekanisme membaca dan mengubah konfigurasi filter tanpa mengubah kode.

**Acceptance criteria:**
- [x] Role keywords, exclusion keywords, max posting age, dan threshold relevansi disimpan di database/config.
- [x] Default filter tersedia untuk stack Laravel, Flutter, NestJS, React, dan Python.
- [x] Perubahan filter memengaruhi eligibility run berikutnya.

**Verification:**
- [x] Test perubahan konfigurasi filter.
- [x] Manual update filter lalu jalankan eligibility terhadap sample job.

**Dependencies:** Task 12  
**Estimated scope:** S

### Task 14: Implementasi Telegram bot authentication

**Deskripsi:** Pastikan hanya pemilik bot yang bisa menjalankan command atau menekan tombol approval.

**Acceptance criteria:**
- [x] Bot hanya menerima command dari allowlisted `chat_id`.
- [x] Request dari chat lain ditolak tanpa membocorkan data.
- [x] Token bot diambil dari environment variable.

**Verification:**
- [x] Test handler authorized dan unauthorized.
- [x] Manual check dengan `chat_id` yang benar.

**Dependencies:** Task 6  
**Estimated scope:** S

### Task 15: Implementasi notifikasi lowongan candidate

**Deskripsi:** Kirim lowongan berstatus `CANDIDATE` ke Telegram untuk review manual.

**Acceptance criteria:**
- [x] Pesan berisi ringkasan lowongan, perusahaan, lokasi, source, apply URL, dan filter reason jika relevan.
- [x] Tombol approve/reject tersedia.
- [x] `callback_data` membawa `application_id` dan expected status untuk mencegah double click.

**Verification:**
- [x] Test payload Telegram.
- [x] Manual test satu candidate menerima pesan.

**Dependencies:** Task 12, Task 14  
**Estimated scope:** M

### Task 16: Implementasi approval/rejection Telegram

**Deskripsi:** Tombol Telegram mengubah status application secara idempotent dan menolak callback lama.

**Acceptance criteria:**
- [x] Approve mengubah status dari `PENDING_APPROVAL` ke `APPROVED`.
- [x] Reject mengubah status dari `PENDING_APPROVAL` ke `REJECTED_BY_USER`.
- [x] Double click atau callback status lama ditolak dengan pesan aman.
- [x] Semua perubahan tercatat di history.

**Verification:**
- [x] Unit test double callback.
- [x] Manual test approve dan reject.

**Dependencies:** Task 8, Task 15  
**Estimated scope:** M

### Task 17: Implementasi command Telegram MVP

**Deskripsi:** Tambahkan command dasar untuk melihat lowongan, status, dan laporan mingguan sederhana.

**Acceptance criteria:**
- [x] `/lowongan` menampilkan candidate/pending terbaru.
- [x] `/status [id] [status_baru]` melakukan transisi manual yang valid.
- [x] `/laporan` menampilkan jumlah ditemukan, lolos filter, dilamar, dan respons.

**Verification:**
- [x] Test command parser.
- [x] Manual check semua command.

**Dependencies:** Task 16  
**Estimated scope:** M

### Checkpoint: MVP Review Manual

- [x] Lowongan bisa diambil, difilter, dikirim ke Telegram, lalu disetujui/ditolak.
- [x] Semua status berubah melalui transition service.
- [x] Duplicate fetch dan duplicate approval tidak merusak data.

---

## P2 — Hardening MVP

### Task 18: Logging aman dan structured

**Deskripsi:** Buat logging yang cukup untuk debug tanpa mencetak CV, cover letter, prompt, atau data pribadi sensitif.

**Acceptance criteria:**
- [x] Log berisi event name, job/application ID, source, status, durasi, dan error code.
- [x] Log tidak berisi cover letter lengkap, CV lengkap, nomor telepon, alamat, atau tanggal lahir.
- [x] Error eksternal disanitasi sebelum ditulis.

**Verification:**
- [x] Audit manual log setelah satu run penuh.
- [x] Test sanitizer untuk field sensitif.

**Dependencies:** Task 11, Task 17  
**Estimated scope:** S

### Task 19: Retention data `FILTERED_OUT`

**Deskripsi:** Hapus atau arsipkan data lowongan filtered-out setelah 90 hari sesuai PRD.

**Acceptance criteria:**
- [x] Job `FILTERED_OUT` lebih tua dari 90 hari bisa dihapus/diarsipkan.
- [x] Job aktif dan application tidak ikut terhapus.
- [x] Job cleanup bisa dijalankan manual dan terjadwal.

**Verification:**
- [x] Test cleanup dengan data dummy bertanggal lama.

**Dependencies:** Task 7  
**Estimated scope:** S

### Task 20: Backup dan restore database lokal

**Deskripsi:** Tambahkan prosedur backup dan restore agar histori lamaran tidak hilang.

**Acceptance criteria:**
- [x] Ada command/script backup database.
- [x] Ada instruksi restore.
- [x] Backup tidak menyertakan credential `.env`.

**Verification:**
- [x] Simulasi backup lalu restore ke database kosong.

**Dependencies:** Task 7  
**Estimated scope:** S

### Task 21: Dokumentasi operasional MVP

**Deskripsi:** Tulis panduan setup, konfigurasi env, menjalankan scheduler, menjalankan bot, dan troubleshooting umum.

**Acceptance criteria:**
- [x] Ada instruksi setup dari nol.
- [x] Semua environment variable terdokumentasi.
- [x] Ada panduan menjalankan test dan one-shot fetch.
- [x] Ada panduan melihat log tanpa membuka data sensitif.

**Verification:**
- [x] Ikuti dokumentasi dari clean checkout/environment dan pastikan aplikasi bisa start.

**Dependencies:** Task 18, Task 20  
**Estimated scope:** M

### Checkpoint: MVP Stabil

- [x] Semua test MVP pass.
- [x] Manual end-to-end flow selesai dari fetch sampai approval.
- [x] Backup dan restore sudah pernah diuji.
- [x] Dokumentasi setup bisa diikuti.

---

## P3 — Setelah MVP Stabil

### Task 22: Integrasi Greenhouse Job Board API

**Deskripsi:** Ambil job dari daftar perusahaan Greenhouse yang dikonfigurasi.

**Acceptance criteria:**
- [ ] `companies_ats` menyimpan `greenhouse` dan `ats_slug`.
- [ ] Fetch minimal 5 perusahaan dari fixture atau integration test terkendali.
- [ ] Job tersimpan dengan source dan external ID benar.

**Verification:**
- [ ] Test fixture Greenhouse.
- [ ] Manual integration test dengan perusahaan target.

**Dependencies:** Checkpoint MVP Stabil  
**Estimated scope:** M

### Task 23: Integrasi Lever Postings API

**Deskripsi:** Ambil job dari daftar perusahaan Lever yang dikonfigurasi.

**Acceptance criteria:**
- [ ] `companies_ats` menyimpan `lever` dan `ats_slug`.
- [ ] Fetch minimal 5 perusahaan dari fixture atau integration test terkendali.
- [ ] Job tersimpan dengan source dan external ID benar.

**Verification:**
- [ ] Test fixture Lever.
- [ ] Manual integration test dengan perusahaan target.

**Dependencies:** Checkpoint MVP Stabil  
**Estimated scope:** M

### Task 24: Ringkasan CV aman untuk LLM

**Deskripsi:** Buat profil skill dan pengalaman yang disanitasi agar personalisasi tidak mengirim data pribadi sensitif.

**Acceptance criteria:**
- [ ] Ringkasan CV tidak berisi alamat, nomor telepon, tanggal lahir, atau identitas sensitif yang tidak diperlukan.
- [ ] Ringkasan bisa diedit pengguna.
- [ ] Prompt builder hanya memakai deskripsi lowongan dan ringkasan CV aman.

**Verification:**
- [ ] Audit manual prompt untuk 5 lowongan.
- [ ] Test sanitizer field sensitif.

**Dependencies:** Checkpoint MVP Stabil  
**Estimated scope:** M

### Task 25: Generate cover letter dengan LLM

**Deskripsi:** Buat draft cover letter yang spesifik terhadap lowongan dan tetap perlu review manual.

**Acceptance criteria:**
- [ ] Cover letter menyebut teknologi/tanggung jawab spesifik dari job description.
- [ ] Output disimpan ke `applications.cover_letter`.
- [ ] Tidak ada prompt atau output lengkap tercetak di log.
- [ ] Kegagalan LLM tidak menghentikan fetch dan eligibility.

**Verification:**
- [ ] Review manual 10 cover letter dari 10 lowongan berbeda.
- [ ] Audit log setelah generate.

**Dependencies:** Task 24  
**Estimated scope:** M

### Task 26: Embedding relevance scoring

**Deskripsi:** Ganti atau lengkapi keyword matching dengan skor embedding antara job description dan profil skill.

**Acceptance criteria:**
- [ ] Model embedding dan versi dicatat.
- [ ] Skor disimpan di `jobs.relevance_score`.
- [ ] Threshold dapat diubah dari konfigurasi.
- [ ] Ada test ranking minimal 10 pasangan lowongan relevan vs tidak relevan.

**Verification:**
- [ ] Hasil ranking sesuai ekspektasi pada dataset evaluasi kecil.

**Dependencies:** Task 24  
**Estimated scope:** M

### Task 27: Riset legal dan teknis auto-submit

**Deskripsi:** Validasi apakah auto-submit lewat Playwright aman, legal, dan stabil untuk target Greenhouse/Lever sebelum implementasi.

**Acceptance criteria:**
- [ ] Ada daftar form target yang diizinkan untuk automation.
- [ ] Ada catatan risiko CAPTCHA, file upload, custom questions, dan ToS.
- [ ] Ada keputusan go/no-go untuk auto-submit.

**Verification:**
- [ ] Review manual dokumen risiko sebelum coding auto-submit.

**Dependencies:** Task 22, Task 23  
**Estimated scope:** S

### Task 28: Prototype auto-submit non-produksi

**Deskripsi:** Buat prototype Playwright pada form test atau target aman tanpa mengirim lamaran nyata.

**Acceptance criteria:**
- [ ] Prototype bisa mengisi form tanpa klik final submit di mode dry-run.
- [ ] Field mapping terdokumentasi.
- [ ] Error form menghasilkan fallback manual.

**Verification:**
- [ ] Dry-run pada minimal 3 Greenhouse dan 3 Lever target aman.

**Dependencies:** Task 27  
**Estimated scope:** M

### Task 29: Auto-submit production dengan guard idempotency

**Deskripsi:** Aktifkan submit nyata hanya setelah dry-run stabil dan guard idempotency lengkap.

**Acceptance criteria:**
- [ ] Submit hanya dimulai dari status `APPROVED` melalui compare-and-swap.
- [ ] Success, failed, timeout, dan ambiguous dicatat di `submission_attempts`.
- [ ] `SUBMISSION_AMBIGUOUS` tidak pernah retry otomatis.
- [ ] Confirmation page/email/reference disimpan jika tersedia.

**Verification:**
- [ ] Test crash simulation sebelum submit, saat submit, dan setelah submit.
- [ ] Manual production test terbatas dengan approval pengguna.

**Dependencies:** Task 28  
**Estimated scope:** M

---

## Open Questions

- [ ] Apakah aturan bisnis yang diinginkan adalah satu lamaran per job atau satu lamaran per perusahaan dalam periode tertentu?
- [ ] Apakah `We Work Remotely` tetap masuk MVP walaupun bukan API resmi penuh?
- [ ] Apakah lowongan dengan timezone restriction seperti `EU timezone only` selalu ditolak atau bisa masuk `REVIEW_REQUIRED`?
- [ ] Apakah MVP perlu menyimpan draft cover letter manual, atau cukup menyimpan link dan status apply manual?
- [ ] Provider LLM dan embedding mana yang dipakai untuk fase P3?
- [ ] Apakah deployment awal cukup lokal/laptop atau langsung VPS Docker?

## Definition of Done MVP

- [x] Fetch RemoteOK dan Remotive berjalan dari one-shot command dan scheduler.
- [x] Deduplication mencegah row duplicate dari source yang sama dan canonical duplicate lintas sumber sesuai aturan PRD.
- [x] Eligibility engine menghasilkan `CANDIDATE`, `FILTERED_OUT`, dan optional `REVIEW_REQUIRED` dengan reason code.
- [x] Telegram bot hanya menerima user terotorisasi.
- [x] Pengguna bisa approve/reject lowongan dari Telegram secara idempotent.
- [x] Application status history tercatat lengkap.
- [x] Laporan sederhana dapat ditampilkan dari Telegram.
- [x] Log tidak mengandung CV lengkap, cover letter lengkap, token, atau data pribadi sensitif.
- [x] Backup dan restore database sudah diuji minimal sekali.
