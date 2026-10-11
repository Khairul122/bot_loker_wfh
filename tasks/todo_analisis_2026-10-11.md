# Tindak lanjut analisis proyek — 11 Oktober 2026

- [x] Pastikan `office/js/data/stats.js` masuk Git dan paket distribusi; sempitkan aturan `.gitignore` untuk data pribadi di akar proyek.
- [x] Pastikan auto-bid yang gagal mengambil klaim tidak mengubah klaim milik proses lain; uji saat dua proses bersaing.
- [x] Terapkan `EXTERNAL_JOBS_ENABLED=false` pada pencarian manual dan otomatis dari kantor 3D.
- [x] Ganti sintaks SQLite pada perintah `add-ats` dengan upsert PostgreSQL dan uji jalur CLI.
- [x] Sertakan berkas skill karyawan dalam image Docker dan paket Python; uji instalasi bersih.
- [x] Jadikan `LLM_PROVIDER=template` mode offline yang benar-benar mematikan panggilan LLM, tanpa mengubah fallback nilai provider lama.
- [x] Samarkan pesan gagal koneksi database agar kredensial tidak muncul di traceback.
- [x] Jalankan tes regresi, seluruh suite (331 lulus), pemeriksaan paket, dan tinjau diff akhir.

Tindakan akun yang masih diperlukan:

- [ ] Rotasi password database Supabase yang sempat terlihat di traceback tes sebelumnya, lalu perbarui kredensial lokal dan server. Jangan simpan nilainya di Git.
