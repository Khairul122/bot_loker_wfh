# PRD: Bot Auto-Apply Kerja WFH Internasional

**Versi:** 2.0
**Tanggal:** 18 September 2026
**Pemilik Proyek:** Khairul
**Status:** Draft untuk pengembangan
**Riwayat Revisi:** v1.0 rilis awal. v2.0 menambahkan aturan eligibility, lifecycle status, skema data detail, mekanisme idempotent, privasi LLM, dan acceptance criteria per fase.

---

## 1. Latar Belakang

Mencari kerja remote internasional secara manual memakan waktu banyak. Setiap lowongan butuh riset perusahaan, penyesuaian CV, penulisan cover letter, dan pengisian form yang berbeda-beda di tiap platform. Proses ini lambat kalau dikerjakan satu per satu.

Sistem ini dibangun untuk mengotomasi sebagian besar proses tersebut. Bot mengambil lowongan dari sumber yang punya API resmi, menyaring lowongan yang relevan, membuat cover letter yang disesuaikan, dan mengisi form lamaran secara otomatis atau semi-otomatis dengan persetujuan pengguna.

## 2. Tujuan

Bot ini punya empat tujuan utama.

Pertama, mengurangi waktu yang dihabiskan untuk mencari dan menyaring lowongan remote yang cocok dengan skill pengguna.

Kedua, meningkatkan jumlah lamaran berkualitas yang terkirim per minggu tanpa menurunkan kualitas tiap lamaran.

Ketiga, mencatat histori lamaran secara terstruktur supaya tidak ada lowongan yang dilamar dua kali dan progres tiap lamaran bisa dipantau.

Keempat, menjaga proses tetap aman dari risiko pemblokiran akun di platform yang melarang otomasi, dan aman secara data pribadi.

## 3. Non-Tujuan

Bot ini tidak dirancang untuk mengotomasi penuh LinkedIn Easy Apply atau Indeed Apply, karena kedua platform tersebut melarang automation tools dalam kebijakan mereka dan berisiko memblokir akun pengguna secara permanen.

Bot ini tidak menjamin lowongan yang dilamar akan direspons atau menghasilkan interview. Tanggung jawab bot berhenti pada pengiriman lamaran yang relevan dan berkualitas.

Bot ini tidak melakukan negosiasi gaji atau komunikasi lanjutan dengan recruiter setelah lamaran terkirim.

Bot ini tidak menangani proses visa atau sponsorship kerja. Bot hanya menyaring lowongan berdasarkan indikasi kebutuhan otorisasi kerja yang tertulis di deskripsi lowongan.

## 4. Target Pengguna

Pengguna utama adalah pengguna tunggal, yaitu pemilik proyek sendiri, seorang developer dengan stack Laravel, Flutter, NestJS, React, dan Python, yang mencari kerja remote internasional di bidang software engineering.

Sistem dirancang untuk penggunaan personal terlebih dahulu. Kalau ke depan mau dikembangkan jadi produk untuk banyak pengguna, arsitektur perlu disesuaikan lagi di fase berikutnya, terutama di bagian skema data yang saat ini mengasumsikan satu pengguna per instance sistem.

## 5. Aturan Eligibility Lowongan

Sebuah lowongan hanya boleh masuk ke tahap personalisasi dan lamaran kalau memenuhi semua kriteria berikut. Kriteria ini dievaluasi berurutan, dan lowongan yang gagal di satu kriteria langsung ditandai `FILTERED_OUT` dengan alasan spesifik, tanpa perlu evaluasi kriteria berikutnya.

| No | Kriteria | Aturan | Aksi Jika Tidak Terpenuhi |
|---|---|---|---|
| 1 | Duplikasi | Kombinasi `source` + `external_id` belum pernah ada, dan `canonical_fingerprint` lowongan belum pernah ada di database | Ditolak, tidak diproses ulang, tidak dicatat sebagai row baru; detail aturan dedup ada di Bagian 8.1 |
| 2 | Tipe remote | Deskripsi mengandung indikasi remote penuh: "remote", "worldwide", "anywhere", "fully remote". Lowongan hybrid atau remote terbatas ke kota tertentu ditolak | Status `FILTERED_OUT`, alasan "not fully remote" |
| 3 | Batasan region/otorisasi kerja | Deskripsi tidak mengandung batasan yang mengecualikan pengguna, misalnya "must be based in US", "EU timezone only", "must have US work authorization" | Status `FILTERED_OUT`, alasan "region restricted" |
| 4 | Kecocokan role | Judul atau deskripsi mengandung minimal satu kata kunci dari daftar role yang dikonfigurasi pengguna, misalnya "backend", "full stack", "mobile developer" | Status `FILTERED_OUT`, alasan "role mismatch" |
| 5 | Kata kunci larangan | Deskripsi tidak mengandung kata kunci di exclusion list, misalnya "unpaid", "commission only", "equity only", "must relocate" | Status `FILTERED_OUT`, alasan "excluded keyword: [kata kunci]" |
| 6 | Company blocklist | Nama perusahaan tidak ada di tabel `company_blocklist` | Status `FILTERED_OUT`, alasan "company blocked" |
| 7 | Usia lowongan | Tanggal posting tidak lebih lama dari 14 hari sejak diambil sistem, supaya tidak melamar lowongan yang sudah basi | Status `FILTERED_OUT`, alasan "posting too old" |
| 8 | Skor relevansi | Skor kecocokan embedding antara deskripsi lowongan dan profil skill pengguna minimal 0.65 dari skala 0 sampai 1 | Status `FILTERED_OUT`, alasan "low relevance score: [nilai]" |

Lowongan yang lolos semua kriteria berubah status menjadi `CANDIDATE`. Ambang batas di atas, seperti usia lowongan 14 hari dan skor 0.65, disimpan di tabel `filters` dan bisa diubah pengguna tanpa mengubah kode. Default role keywords mencakup `laravel`, `flutter`, `nestjs`, `react`, `python`, `backend`, `full stack`, dan `mobile developer`.

Pada MVP, data eligibility yang tidak cukup untuk mengambil keputusan deterministik, seperti `posted_at` atau `relevance_score` yang kosong/tidak valid, langsung diberi status `FILTERED_OUT` dengan reason code `posting date unavailable` atau `relevance score unavailable`. Status `REVIEW_REQUIRED` belum digunakan karena belum memiliki transisi pada lifecycle job; alur review manual untuk kasus ambigu dapat ditambahkan setelah MVP.

## 6. Ruang Lingkup Fitur

### 6.1 Pengambilan Lowongan (Job Sourcing)

Bot mengambil data lowongan dari sumber berikut secara berkala.

| Sumber | Jenis Akses | Catatan |
|---|---|---|
| RemoteOK | Public API, JSON, tanpa API key | Wajib mencantumkan atribusi sumber |
| Remotive | Public API, JSON, tanpa API key | Update lowongan tiap beberapa jam |
| We Work Remotely | RSS/scraping ringan | Format lebih terbatas, perlu parsing HTML |
| Greenhouse Job Board API | Public API per perusahaan | Satu integrasi berlaku untuk semua perusahaan yang pakai Greenhouse |
| Lever Postings API | Public API per perusahaan | Sama seperti Greenhouse, reusable antar perusahaan |

Daftar perusahaan target untuk Greenhouse dan Lever disimpan di tabel `companies_ats`, bisa ditambah manual seiring waktu.

### 6.2 Penyaringan dan Skoring

Lowongan disaring sesuai aturan di Bagian 5. Skor relevansi dihitung dengan membandingkan embedding deskripsi lowongan terhadap ringkasan skill dan pengalaman pengguna.

### 6.3 Personalisasi Lamaran

Mulai Fase 2, untuk tiap lowongan berstatus `CANDIDATE`, sistem membuat draft cover letter dan ringkasan CV yang disesuaikan dengan deskripsi lowongan menggunakan LLM API. Aturan penggunaan data untuk LLM diatur di Bagian 11.

Pada Fase 1, sistem tidak memanggil LLM. Pengguna menyiapkan cover letter dan CV summary secara manual menggunakan template lokal dan informasi lowongan yang dikirim Telegram. Application baru dibuat setelah kedua materi tersebut tersedia dan lolos validasi field wajib.

Draft ini menyertakan referensi konkret terhadap teknologi atau tanggung jawab yang disebut di deskripsi lowongan, bukan template generik yang sama untuk semua lamaran.

Bahasa cover letter otomatis mengikuti bahasa lowongan, default bahasa Inggris untuk lowongan internasional.

### 6.4 Review dan Persetujuan

Sebelum lamaran dikirim, sistem mengirim ringkasan lowongan beserta draft cover letter dan CV summary ke pengguna lewat bot Telegram, dengan status `PENDING_APPROVAL`. Pada Fase 1, draft tersebut adalah materi manual pengguna; pada Fase 2 dan seterusnya, draft dapat berasal dari LLM tetapi tetap wajib direview.

Pengguna bisa menyetujui, meminta revisi, atau menolak lamaran tersebut langsung dari chat Telegram. Mekanisme detail approval dijelaskan di Bagian 10.

Mode ini wajib aktif di awal penggunaan sistem. Mode auto-submit tanpa review manual hanya boleh diaktifkan setelah pengguna yakin kualitas draft konsisten baik, dan tetap dibatasi hanya untuk lowongan dari sumber yang formulirnya sudah diverifikasi aman diisi otomatis.

### 6.5 Pengiriman Lamaran

Untuk lowongan dari Greenhouse dan Lever, sistem mengisi form lamaran secara otomatis menggunakan Playwright, karena struktur form di kedua ATS ini konsisten antar perusahaan.

Untuk lowongan dari sumber lain yang formulirnya tidak konsisten atau butuh input custom, sistem memberikan link lowongan dan draft materi ke pengguna untuk dilamar manual.

Mekanisme submission wajib idempotent, dijelaskan detail di Bagian 10.

### 6.6 Pencatatan dan Tracking

Setiap perubahan status lamaran dicatat di tabel `application_status_history` sebagai audit trail lengkap. Detail skema ada di Bagian 8.

### 6.7 Laporan Berkala

Sistem mengirim ringkasan mingguan ke pengguna: jumlah lowongan ditemukan, jumlah yang lolos filter, jumlah yang dilamar, dan jumlah yang mendapat respons.

## 7. Lifecycle Status Job dan Lamaran

Job dan application memiliki state machine terpisah. Transisi di luar daftar masing-masing dianggap invalid dan harus ditolak oleh sistem, bukan diam-diam diizinkan.

### 7.1 Lifecycle Job

```text
DISCOVERED
   |
   v
[evaluasi eligibility, Bagian 5]
   |
   +--(gagal)--> FILTERED_OUT [terminal]
   |
   +--(lolos)--> CANDIDATE
```

`jobs.status` hanya menggunakan `DISCOVERED`, `CANDIDATE`, dan `FILTERED_OUT`. Status `CANDIDATE` berarti lowongan lolos eligibility; status ini belum berarti pengguna sudah membuat atau menyetujui lamaran.

### 7.2 Lifecycle Application

Application dibuat untuk job berstatus `CANDIDATE` setelah materi lamaran siap diproses. Pada Fase 1, pengguna menekan aksi `Siapkan draft` pada notifikasi candidate, mengisi cover letter dan CV summary berdasarkan template lokal, lalu mengirimkannya kembali melalui alur Telegram. Sistem memvalidasi kedua field tersebut sebelum membuat application berstatus `DRAFT_READY`. Application tidak menggunakan status `DISCOVERED`, `CANDIDATE`, atau `FILTERED_OUT`.

```text
DRAFT_READY  (cover letter & CV summary sudah tersedia)
   |
   v
PENDING_APPROVAL  (dikirim ke Telegram)
   |
   +--(pengguna tolak)--> REJECTED_BY_USER [terminal]
   |
   +--(pengguna tarik)--> WITHDRAWN [terminal]
   |
   v
APPROVED
   |
   +--(pengguna tarik)--> WITHDRAWN [terminal]
   |
   v
SUBMITTING  (lock state, compare-and-swap dari APPROVED)
   |
   +--(gagal sebelum submit)--> SUBMIT_FAILED --> (retry manual) --> APPROVED
   |
   +--(hasil tidak dapat diverifikasi)--> SUBMISSION_AMBIGUOUS
   |
   v
SUBMITTED
   |
   +--> VIEWED (opsional, kalau ATS beri sinyal)
   |
   +--> INTERVIEW --> OFFER [terminal]
   |             \--> REJECTED_BY_COMPANY [terminal]
   |
   +--> REJECTED_BY_COMPANY [terminal]
   |
   +--> NO_RESPONSE [terminal, auto-set setelah 21 hari tanpa update]
   |
   +--(pengguna tarik lamaran)--> WITHDRAWN [terminal]
```

### 7.3 Tabel Transisi Job

| Dari | Ke | Trigger | Pemicu |
|---|---|---|---|
| DISCOVERED | CANDIDATE | Lolos semua kriteria eligibility | Sistem |
| DISCOVERED | FILTERED_OUT | Gagal salah satu kriteria eligibility | Sistem |

### 7.4 Tabel Transisi Application

| Dari | Ke | Trigger | Pemicu |
|---|---|---|---|
| DRAFT_READY | PENDING_APPROVAL | Notifikasi berisi draft manual atau draft LLM terkirim ke Telegram | Sistem |
| PENDING_APPROVAL | APPROVED | Pengguna klik approve | Pengguna |
| PENDING_APPROVAL | REJECTED_BY_USER | Pengguna klik reject | Pengguna |
| PENDING_APPROVAL / APPROVED | WITHDRAWN | Pengguna tarik lamaran sebelum submit | Pengguna |
| APPROVED | SUBMITTING | Worker submission mulai proses, compare-and-swap status | Sistem |
| SUBMITTING | SUBMITTED | Form berhasil terkirim dan terverifikasi | Sistem |
| SUBMITTING | SUBMIT_FAILED | Error terjadi sebelum tombol submit final diklik | Sistem |
| SUBMITTING | SUBMISSION_AMBIGUOUS | Tombol submit mungkin sudah diklik tetapi hasil belum terverifikasi | Sistem |
| SUBMIT_FAILED | APPROVED | Pengguna mengonfirmasi retry setelah verifikasi manual | Pengguna |
| SUBMISSION_AMBIGUOUS | SUBMITTED | Pengguna memverifikasi email, confirmation page, atau bukti submission lain | Pengguna |
| SUBMISSION_AMBIGUOUS | SUBMIT_FAILED | Pengguna memverifikasi bahwa submission tidak terjadi dan mengizinkan retry | Pengguna |
| SUBMISSION_AMBIGUOUS | APPROVED | Pengguna memverifikasi bahwa submission tidak terjadi dan memilih retry setelah review | Pengguna |
| SUBMITTED | VIEWED | Sinyal dari ATS bahwa lamaran dibuka recruiter | Sistem (kalau tersedia) |
| SUBMITTED / VIEWED | INTERVIEW | Update manual dari pengguna | Pengguna |
| SUBMITTED / VIEWED | REJECTED_BY_COMPANY | Update manual dari pengguna | Pengguna |
| SUBMITTED / VIEWED | NO_RESPONSE | Tidak ada update selama 21 hari sejak `submitted_at` | Sistem terjadwal |
| INTERVIEW | OFFER | Update manual dari pengguna | Pengguna |
| INTERVIEW | REJECTED_BY_COMPANY | Update manual dari pengguna | Pengguna |

Status `FILTERED_OUT` adalah terminal pada lifecycle job. Status `REJECTED_BY_USER`, `OFFER`, `REJECTED_BY_COMPANY`, `NO_RESPONSE`, dan `WITHDRAWN` adalah status terminal pada lifecycle application. `SUBMISSION_AMBIGUOUS` bukan status terminal karena harus diselesaikan melalui verifikasi pengguna, tetapi worker tidak boleh memproses submission dari status ini. Tidak ada transisi keluar dari status terminal, kecuali koreksi manual oleh pengguna lewat perintah database langsung untuk kasus human error, bukan lewat alur normal bot.

## 8. Skema Data

Skema di bawah pakai notasi mirip SQL supaya jelas tipe data dan constraint-nya, walaupun implementasi akhir boleh pakai ORM.

### 8.1 Tabel `jobs`

```sql
CREATE TABLE jobs (
  id UUID PRIMARY KEY,
  source VARCHAR(50) NOT NULL,              -- 'remoteok' | 'remotive' | 'wwr' | 'greenhouse' | 'lever'
  external_id VARCHAR(255) NOT NULL,        -- id asli dari sumber
  source_external_key VARCHAR(320) NOT NULL, -- hash(source + ':' + external_id), untuk dedup per sumber
  canonical_fingerprint VARCHAR(64) NOT NULL,-- hash(normalized_title + normalized_company + normalized_apply_host_or_path), untuk dedup lintas sumber
  title VARCHAR(255) NOT NULL,
  company VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  location VARCHAR(255),
  salary_min INT,
  salary_max INT,
  currency VARCHAR(10),
  apply_url TEXT NOT NULL,
  posted_at TIMESTAMP,
  fetched_at TIMESTAMP NOT NULL DEFAULT now(),
  relevance_score DECIMAL(4,3),
  status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED',
  filtered_reason TEXT,
  UNIQUE (source, external_id),
  UNIQUE (source_external_key),
  UNIQUE (canonical_fingerprint)
);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_posted_at ON jobs(posted_at);
```

Constraint `UNIQUE (source, external_id)` dan `UNIQUE (source_external_key)` mencegah lowongan yang sama diambil dua kali dari sumber yang sama. Constraint `UNIQUE (canonical_fingerprint)` mencegah lowongan yang sama diambil ulang ketika muncul di sumber berbeda dengan `external_id` berbeda.

Normalisasi `canonical_fingerprint` dilakukan sebelum hashing dengan aturan berikut.

| Field | Aturan Normalisasi |
|---|---|
| `title` | lowercase, trim spasi, hapus punctuation umum, samakan sinonim umum seperti "sr" menjadi "senior", hapus suffix lokasi seperti "- remote" |
| `company` | lowercase, trim spasi, hapus suffix legal umum seperti "inc", "llc", "ltd", "pt", dan punctuation |
| `apply_url` | ambil host dan path utama tanpa query string, UTM, fragment, dan trailing slash; kalau URL ATS memuat job id stabil, job id tersebut dipertahankan |

`canonical_fingerprint` dihitung dari `normalized_title + '|' + normalized_company + '|' + normalized_apply_host_or_path`. `source` tidak boleh masuk ke `canonical_fingerprint`, karena kunci ini memang dipakai untuk dedup lintas sumber.

Jika `canonical_fingerprint` sama persis, sistem menganggap lowongan duplikat dan tidak membuat row `jobs` baru. Jika fingerprint tidak sama tetapi title dan company sangat mirip, sistem tidak melakukan auto-merge pada MVP; lowongan tetap disimpan sebagai row terpisah agar tidak membuang lowongan yang sebenarnya berbeda. Review manual untuk near-duplicate bisa ditambahkan di fase berikutnya.

Contoh expected result dedup:

| Kasus | Input | Expected Result |
|---|---|---|
| Fetch ulang sumber sama | RemoteOK `external_id=123` diambil dua kali | Run kedua tidak membuat row baru karena `source_external_key` sama |
| Duplikat lintas sumber | RemoteOK dan Remotive memuat `Backend Developer` di `Acme` dengan apply URL canonical sama | Hanya satu row `jobs` dibuat karena `canonical_fingerprint` sama |
| Job berbeda di perusahaan sama | `Backend Developer` dan `Mobile Developer` di `Acme` | Dua row dibuat karena normalized title berbeda |
| Judul mirip tapi URL beda | `Senior Backend Engineer` di `Acme` dengan apply URL Greenhouse berbeda | Dua row dibuat, karena fingerprint tidak sama dan MVP tidak auto-merge near-duplicate |
| Query tracking berbeda | URL sama dengan parameter `?utm_source=remoteok` dan `?utm_source=remotive` | Dianggap duplikat karena query tracking dihapus saat normalisasi |

### 8.2 Tabel `applications`

Aturan bisnis MVP adalah **satu application untuk satu job**. Dua job berbeda dari perusahaan yang sama tetap boleh memiliki application terpisah, karena posisi, deskripsi, pertanyaan form, dan materi lamaran bisa berbeda. Sistem tidak menerapkan batas satu application per perusahaan atau cooldown berbasis waktu pada MVP. Aturan tersebut dapat ditambahkan kemudian sebagai konfigurasi pengguna jika data pengalaman menunjukkan kebutuhan.

```sql
CREATE TABLE applications (
  id UUID PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES jobs(id),
  idempotency_key VARCHAR(64) NOT NULL,     -- hash(job_id + user_id)
  status VARCHAR(30) NOT NULL DEFAULT 'DRAFT_READY',
  cover_letter TEXT NOT NULL,
  cv_summary TEXT NOT NULL,
  method VARCHAR(20),                       -- 'auto' | 'manual'
  retry_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  approved_at TIMESTAMP,
  submitted_at TIMESTAMP,
  last_status_check_at TIMESTAMP,
  notes TEXT,
  UNIQUE (job_id),           -- satu job hanya boleh punya satu application
  UNIQUE (idempotency_key)
);
CREATE INDEX idx_applications_status ON applications(status);
```

Karena `job_id` unique, sistem tidak bisa membuat dua record application untuk lowongan yang sama, walaupun ada dua proses yang berjalan bersamaan mencoba insert di waktu yang sama. Constraint ini menjadi jaring pengaman idempotency di level database, bukan cuma di level kode aplikasi. Record application hanya dibuat setelah job berstatus `CANDIDATE` dan `cover_letter` serta `cv_summary` tidak kosong, sehingga status job dan status application tidak saling menggantikan.

Contoh expected result aturan duplicate application:

| Kasus | Input | Expected Result |
|---|---|---|
| Job sama diproses dua kali | Dua worker membuat application untuk `job_id` yang sama | Hanya satu row dibuat; insert kedua ditolak oleh `UNIQUE (job_id)` dan worker mengambil row yang sudah ada |
| Perusahaan sama, posisi berbeda | `Backend Developer` dan `Mobile Developer` di perusahaan yang sama | Dua application boleh dibuat karena `job_id` berbeda |
| Company name berbeda, job sama | Dua proses menerima data untuk `job_id` yang sama dengan variasi penulisan nama perusahaan | Tetap satu application karena dedup application memakai `job_id`, bukan string nama perusahaan |

### 8.3 Tabel `submission_attempts`

```sql
CREATE TABLE submission_attempts (
  id UUID PRIMARY KEY,
  application_id UUID NOT NULL REFERENCES applications(id),
  attempt_number INT NOT NULL,
  result VARCHAR(20) NOT NULL,              -- 'success' | 'failed' | 'timeout' | 'ambiguous'
  error_message TEXT,
  attempted_at TIMESTAMP NOT NULL DEFAULT now(),
  UNIQUE (application_id, attempt_number)
);
```

Setiap percobaan submission, berhasil atau gagal, dicatat sebagai row baru dengan `attempt_number` incremental. Ini memberi jejak audit lengkap kalau ada kasus dispute atau debug.

### 8.4 Tabel `application_status_history`

```sql
CREATE TABLE application_status_history (
  id UUID PRIMARY KEY,
  application_id UUID NOT NULL REFERENCES applications(id),
  from_status VARCHAR(30),
  to_status VARCHAR(30) NOT NULL,
  changed_by VARCHAR(20) NOT NULL,          -- 'system' | 'user'
  changed_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_status_history_application ON application_status_history(application_id);
```

Tabel ini append-only. Tidak ada update atau delete terhadap row yang sudah ada, supaya histori transisi status tidak pernah hilang.

### 8.5 Tabel `filters`

```sql
CREATE TABLE filters (
  id UUID PRIMARY KEY,
  role_keywords TEXT[] NOT NULL,
  exclusion_keywords TEXT[] NOT NULL,
  min_relevance_score DECIMAL(4,3) NOT NULL DEFAULT 0.65,
  max_posting_age_days INT NOT NULL DEFAULT 14,
  no_response_after_days INT NOT NULL DEFAULT 21,
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### 8.6 Tabel `companies_ats`

```sql
CREATE TABLE companies_ats (
  id UUID PRIMARY KEY,
  company_name VARCHAR(255) NOT NULL,
  ats_type VARCHAR(20) NOT NULL,            -- 'greenhouse' | 'lever'
  ats_slug VARCHAR(255) NOT NULL,           -- identifier perusahaan di ATS tsb
  active BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (ats_type, ats_slug)
);
```

### 8.7 Tabel `company_blocklist`

```sql
CREATE TABLE company_blocklist (
  id UUID PRIMARY KEY,
  company_name VARCHAR(255) NOT NULL UNIQUE,
  reason TEXT,
  added_at TIMESTAMP NOT NULL DEFAULT now()
);
```

## 9. Arsitektur Sistem

### 9.1 Diagram Alur

```
[Job Sources: RemoteOK, Remotive, WWR, Greenhouse, Lever]
                |
                v
        [Scheduler / Cron Job]
                |
                v
        [Fetcher & Parser Service] --> tabel jobs (status DISCOVERED)
                |
                v
        [Eligibility Engine, Bagian 5]  <-- tabel filters, company_blocklist
                |
                v
        [Draft Preparation: template manual Fase 1 / LLM Fase 2]  --> tabel applications (status DRAFT_READY)
                |
                v
        [Telegram Bot: Review & Approval]  --> status PENDING_APPROVAL / APPROVED
                |
        +-------+-------+
        |               |
        v               v
[Auto-Submit via     [Manual Apply
 Playwright,          oleh pengguna]
 Bagian 10]
        |               |
        +-------+-------+
                v
        [application_status_history]
                |
                v
        [Laporan Mingguan]
```

### 9.2 Komponen dan Tech Stack

| Komponen | Teknologi | Alasan Pemilihan |
|---|---|---|
| Bahasa utama | Python | Ekosistem automation, scraping, dan LLM SDK paling lengkap |
| Browser automation | Playwright | Stabil untuk form dinamis, bisa headless di server |
| Scheduler | APScheduler atau Celery + Redis | Menjalankan fetch dan proses apply secara berkala |
| Database | PostgreSQL (produksi) atau SQLite (versi ringan) | Menyimpan histori lamaran dan konfigurasi filter, mendukung constraint unique untuk idempotency |
| LLM Provider | Claude API | Membuat cover letter dan ringkasan CV yang disesuaikan |
| Notifikasi dan kontrol | Bot Telegram (python-telegram-bot) | Review cepat lewat chat, tidak perlu buka dashboard tiap saat |
| Dashboard opsional | NestJS + React | Untuk versi lanjutan, menampilkan statistik dan histori lamaran |
| Deployment | VPS kecil dengan Docker | Berjalan terus-menerus tanpa tergantung laptop pengguna menyala |
| Logging dan monitoring | Log file terstruktur, opsional integrasi Sentry | Memudahkan debug kalau ada form yang gagal terisi, tanpa mencetak data sensitif |

## 10. Mekanisme Approval dan Submission yang Idempotent

Bagian ini mendefinisikan aturan supaya tidak ada application yang diproses atau dikirim dua kali untuk job yang sama, baik karena bug, race condition, maupun retry setelah error. Dua job berbeda dari perusahaan yang sama bukan duplicate menurut aturan MVP dan boleh diproses terpisah.

### 10.1 Idempotency Key

Setiap application punya `idempotency_key` yang dihitung dari hash `job_id` ditambah identitas pengguna, dibuat sekali saat record application pertama kali dibuat setelah job berstatus `CANDIDATE` dan application berstatus `DRAFT_READY`. Key ini tidak pernah berubah sepanjang lifecycle application tersebut, dan disimpan sebagai kolom unique di database. Karena MVP adalah single-user, identitas pengguna tetap disimpan dalam formula agar model data tidak mengunci evolusi multi-user di masa depan.

### 10.2 Guard Sebelum Submission

Sebelum proses submission dijalankan, sistem wajib memverifikasi status application saat ini persis `APPROVED`. Kalau status bukan `APPROVED`, misalnya karena sudah `SUBMITTING` atau `SUBMITTED` dari proses lain, submission dibatalkan tanpa error, dianggap sudah tertangani.

### 10.3 Compare-and-Swap saat Mulai Submission

Perubahan status dari `APPROVED` ke `SUBMITTING` dilakukan dalam satu statement update atomik: `UPDATE applications SET status = 'SUBMITTING' WHERE id = ? AND status = 'APPROVED'`. Kalau jumlah row yang terupdate nol, berarti proses lain sudah mengambil lamaran ini duluan, dan proses saat ini berhenti tanpa lanjut submit. Mekanisme ini mencegah dua worker mengisi form yang sama secara bersamaan.

### 10.4 Pencatatan Setiap Percobaan

Setiap kali proses submission dijalankan, baik berhasil maupun gagal, dicatat sebagai row baru di `submission_attempts` dengan `attempt_number` yang naik. Attempt kedua untuk application yang sama tidak boleh dimulai kalau attempt sebelumnya berstatus `success`.

### 10.5 Penanganan Kegagalan Ambigu

Kalau koneksi terputus setelah tombol submit diklik tetapi sebelum sistem sempat memverifikasi halaman konfirmasi, hasil dicatat sebagai `ambiguous`, bukan `failed`. Status application diset `SUBMISSION_AMBIGUOUS` dan sistem mengirim notifikasi kepada pengguna untuk memeriksa email konfirmasi, confirmation page, atau bukti submission lain secara manual.

Tidak ada retry otomatis dari `SUBMISSION_AMBIGUOUS`, termasuk setelah worker restart atau server crash. Pengguna wajib memilih salah satu hasil berikut melalui alur verifikasi:

1. Jika ada bukti lamaran sudah terkirim, ubah status menjadi `SUBMITTED` dan simpan catatan/reference submission jika tersedia.
2. Jika terbukti lamaran belum terkirim dan pengguna mengizinkan percobaan ulang, ubah status menjadi `APPROVED`, lalu worker boleh memulai submission baru melalui compare-and-swap.
3. Jika submission belum bisa dipastikan, status tetap `SUBMISSION_AMBIGUOUS` dan worker tidak melakukan apa pun.

Retry otomatis hanya diizinkan untuk kegagalan yang jelas terjadi sebelum tombol submit diklik, misalnya gagal memuat halaman form. Sistem tidak dapat menjamin bahwa restart setelah tombol submit diklik tidak menghasilkan duplicate submission; jaminan yang diwajibkan adalah tidak melakukan retry otomatis pada hasil yang ambigu.

### 10.6 Idempotency di Sisi Telegram

Setiap tombol approve atau reject di Telegram membawa `callback_data` berisi `application_id` beserta status yang diharapkan saat tombol dibuat, misalnya `PENDING_APPROVAL`. Kalau pengguna menekan tombol yang sama dua kali, atau menekan tombol dari pesan lama setelah status sudah berubah, permintaan kedua ditolak karena status di database sudah tidak cocok dengan status yang diharapkan pada `callback_data`.

## 11. Privasi Data dan Penggunaan LLM

Data yang dikirim ke LLM provider dibatasi hanya deskripsi lowongan dan ringkasan poin pengalaman kerja, skill, dan proyek dari pengguna. Data pribadi sensitif seperti alamat rumah, nomor telepon, dan tanggal lahir tidak pernah disertakan dalam prompt.

Ringkasan CV yang dipakai untuk personalisasi disimpan sebagai field terpisah dari dokumen CV asli, berisi hanya poin yang relevan untuk pencocokan kerja.

Prompt ke LLM tidak menyertakan riwayat lamaran ke perusahaan lain, supaya tidak ada informasi yang bocor antar proses atau antar lowongan.

Pengguna disarankan mengaktifkan pengaturan di akun LLM provider yang menyatakan data API tidak dipakai untuk melatih model, sebelum sistem dipakai secara rutin.

Log aplikasi tidak boleh mencetak isi cover letter lengkap atau isi CV dalam bentuk plaintext yang gampang diakses. Log cukup mencatat metadata seperti `job_id`, status, dan waktu kejadian.

Data CV, ringkasan skill, dan hasil generate LLM disimpan di database dengan akses terbatas hanya untuk pengguna sistem, idealnya lewat koneksi yang terenkripsi dan kredensial yang tidak dibagikan.

Data lowongan berstatus `FILTERED_OUT` dihapus otomatis setelah 90 hari untuk mengurangi penyimpanan data yang tidak lagi diperlukan.

## 12. Kebutuhan Non-Fungsional

Sistem harus bisa memproses minimal 200 lowongan baru per hari tanpa penurunan performa berarti.

Waktu antar pengambilan lowongan diatur minimal empat jam sekali, supaya tidak membebani API sumber data dan tetap dalam batas wajar penggunaan.

Kredensial API dan token bot disimpan di environment variable, tidak pernah ditulis langsung di kode.

Sistem harus punya mekanisme retry otomatis untuk kegagalan jaringan sementara pada tahap fetch, dengan batasan retry hanya untuk kegagalan sebelum submission final, sesuai Bagian 10.5.

Semua data pribadi pengguna disimpan lokal di server milik pengguna sendiri, tidak dikirim ke pihak ketiga selain LLM provider untuk keperluan generate teks, sesuai batasan di Bagian 11.

## 13. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Akun terblokir karena automation di platform yang melarang | Kehilangan akses ke LinkedIn atau Indeed | Tidak mengotomasi platform tersebut, fokus ke sumber dengan API resmi |
| Cover letter generik terdeteksi recruiter | Tingkat respons rendah, reputasi menurun | Review manual di awal, validasi kualitas sebelum aktifkan auto-submit |
| Form ATS berubah struktur | Bot gagal isi form otomatis | Logging error jelas, fallback ke notifikasi manual saat submit gagal |
| Submission dobel untuk job yang sama | Terlihat tidak profesional, berpotensi diskualifikasi | Idempotency key, unique constraint di `job_id`, compare-and-swap status, Bagian 10 |
| Rate limit dari API sumber lowongan | Data lowongan tidak update tepat waktu | Interval fetch wajar, cache hasil fetch terakhir |
| Kebocoran data pribadi lewat prompt LLM | Data sensitif tersimpan di pihak ketiga | Batasan data yang dikirim ke LLM, sesuai Bagian 11 |
| Status lamaran tidak konsisten karena race condition | Laporan salah, keputusan approval keliru | Guard status dan compare-and-swap, Bagian 10.2 dan 10.3 |

## 14. Rencana Pengembangan dan Acceptance Criteria

### Fase 1: MVP (target 1-2 minggu)

Cakupan: fetcher RemoteOK dan Remotive, eligibility engine dasar berbasis keyword, tabel `jobs` dan `applications` dengan constraint unique, bot Telegram untuk notifikasi, penyiapan draft manual, dan approval manual, penyimpanan di SQLite. Belum ada auto-submit maupun LLM. Cover letter dan CV summary wajib diisi pengguna melalui template lokal sebelum application dibuat.

Acceptance criteria:

Sistem berhasil fetch minimal 50 lowongan baru dari RemoteOK dan Remotive dalam satu kali run scheduler, tanpa error dan tanpa duplikat berdasarkan `source_external_key` maupun `canonical_fingerprint`.

Fetch yang dijalankan dua kali berturut-turut terhadap sumber yang sama tidak menghasilkan row baru di tabel `jobs` untuk lowongan yang sudah ada, dibuktikan lewat query count sebelum dan sesudah.

Eligibility engine memisahkan status `CANDIDATE` dan `FILTERED_OUT` sesuai kriteria Bagian 5, diverifikasi manual terhadap minimal 20 sample lowongan dengan hasil yang sesuai ekspektasi.

Bot Telegram mengirim notifikasi candidate dengan aksi `Siapkan draft`. Setelah pengguna mengirim cover letter dan CV summary yang tidak kosong, sistem membuat application `DRAFT_READY`, mengirim materi untuk review, lalu mengubahnya ke `PENDING_APPROVAL`. Tombol approve/reject berhasil mengubah status application sesuai tabel transisi Bagian 7.4.

Percobaan insert dua application dengan `job_id` yang sama menghasilkan error constraint, bukan dua row baru. Percobaan membuat application dengan `cover_letter` atau `cv_summary` kosong ditolak oleh validasi aplikasi.

Job berbeda dari perusahaan yang sama dapat memiliki dua application, sedangkan dua proses untuk job yang sama hanya menghasilkan satu application.

### Fase 2: Personalisasi dan Integrasi ATS (target 2-3 minggu setelah Fase 1)

Cakupan: integrasi Greenhouse dan Lever API, LLM untuk generate cover letter dan ringkasan CV otomatis, skoring relevansi berbasis embedding menggantikan keyword sederhana, penerapan batasan privasi data di Bagian 11.

Acceptance criteria:

Sistem berhasil generate cover letter untuk minimal 10 lowongan berbeda, dan hasil perbandingan manual menunjukkan tiap cover letter mengandung referensi spesifik ke lowongan masing-masing, bukan template yang sama diulang.

Integrasi Greenhouse dan Lever berhasil mengambil data lowongan dari minimal 5 perusahaan berbeda per masing-masing ATS, tersimpan dengan `ats_type` dan `ats_slug` yang benar di tabel `companies_ats`.

Skor relevansi embedding terbukti mengurutkan dengan benar lewat pengujian: lowongan yang jelas relevan terhadap profil pengguna mendapat skor lebih tinggi dibanding lowongan yang jelas tidak relevan, diuji dengan minimal 10 pasang perbandingan.

Audit manual terhadap log file setelah satu siklus penuh berjalan tidak menemukan isi cover letter atau isi CV tercetak dalam bentuk plaintext.

### Fase 3: Auto-Submit dan Dashboard (target setelah Fase 2 stabil)

Cakupan: auto-submit form lewat Playwright untuk ATS yang sudah diverifikasi aman, dashboard NestJS dan React untuk statistik dan histori lamaran, migrasi database dari SQLite ke PostgreSQL, job terjadwal untuk transisi status `NO_RESPONSE`.

Acceptance criteria:

Auto-submit berhasil mengisi dan mengirim form di minimal 3 perusahaan Greenhouse dan 3 perusahaan Lever secara berurutan, dengan tiap application berakhir di status `SUBMITTED` dan tepat satu row `success` di `submission_attempts`.

Simulasi crash setelah tombol submit diklik, diikuti restart proses, menghasilkan status `SUBMISSION_AMBIGUOUS`, tidak melakukan retry otomatis, dan mengirim notifikasi verifikasi kepada pengguna. Submission kedua hanya boleh dimulai setelah pengguna memverifikasi submission belum terjadi dan mengubah status sesuai tabel transisi Bagian 7.4.

Data statistik yang ditampilkan dashboard cocok dengan hasil query langsung ke database, diverifikasi dengan membandingkan angka di dashboard dan hasil query untuk minimal tiga metrik: total dilamar, total interview, total respons.

Job terjadwal berhasil mengubah status application menjadi `NO_RESPONSE` tepat setelah 21 hari sejak `submitted_at` tanpa update manual, diuji dengan data `submitted_at` yang dimundurkan secara sengaja untuk simulasi.

## 15. Metrik Keberhasilan

Jumlah lowongan relevan yang ditemukan per minggu meningkat dibanding pencarian manual.

Waktu yang dihabiskan pengguna untuk proses apply per lowongan turun signifikan, dari yang tadinya bisa 20-30 menit manual menjadi di bawah 5 menit dengan review lewat Telegram.

Tingkat respons dari perusahaan tidak menurun dibanding rata-rata lamaran manual pengguna sebelumnya, untuk memastikan otomasi tidak menurunkan kualitas.

Tidak ada insiden pemblokiran akun di platform manapun, dan tidak ada insiden submission dobel untuk job yang sama, selama sistem berjalan.

## 16. Panduan Pengembangan

Setiap fitur dikerjakan dengan checklist to-do sebelum dianggap selesai: implementasi fungsi utama, penanganan error, logging tanpa data sensitif, dan pengujian manual dengan minimal lima lowongan nyata.

Kode mengikuti standar clean code: satu fungsi satu tanggung jawab, penamaan variabel jelas, tidak ada nilai hardcoded untuk kredensial atau konfigurasi yang bisa berubah.

Setiap perubahan status wajib lewat fungsi transisi terpusat yang memvalidasi tabel transisi job di Bagian 7.3 atau tabel transisi application di Bagian 7.4, tidak boleh ada update status langsung dari tempat lain di kode.

Setiap integrasi API baru didokumentasikan di file terpisah, mencatat endpoint yang dipakai, format response, dan batasan penggunaan.

---

**Lampiran A: Contoh Struktur Data Lowongan dari RemoteOK**

```json
{
  "id": "123456",
  "company": "Nama Perusahaan",
  "position": "Backend Developer",
  "description": "Deskripsi lowongan...",
  "location": "Worldwide",
  "tags": ["python", "remote", "backend"],
  "apply_url": "https://remoteok.com/l/123456"
}
```

**Lampiran B: Contoh Perintah Bot Telegram**

`/lowongan` menampilkan daftar lowongan berstatus `CANDIDATE` serta application berstatus `DRAFT_READY` atau `PENDING_APPROVAL` hari ini.

`/siapkan [job_id]` memulai penyiapan draft manual untuk job `CANDIDATE` dan mengirim template cover letter serta CV summary kepada pengguna.

`/draft [job_id]` menerima atau memperbarui cover letter dan CV summary manual. Application hanya dibuat atau dipindahkan ke `DRAFT_READY` jika kedua field tidak kosong.

`/setuju [id]` mengubah status application dari `PENDING_APPROVAL` ke `APPROVED`.

`/tolak [id]` mengubah status ke `REJECTED_BY_USER`.

`/status [id] [status_baru]` mengubah status lamaran secara manual, dicatat sebagai `changed_by = 'user'` di `application_status_history`.

`/laporan` menampilkan ringkasan statistik minggu berjalan.

**Lampiran C: Contoh Alasan Eligibility yang Tercatat**

```json
{
  "job_id": "uuid-lowongan",
  "status": "FILTERED_OUT",
  "filtered_reason": "excluded keyword: unpaid"
}
```
