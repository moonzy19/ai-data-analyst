# AI Data Analyst — Termux + Web MVP

Aplikasi analisis data sederhana berbasis Flask. Paket yang sama dapat dijalankan di Android/Termux atau di-host sebagai web service Python, misalnya di Render.

## Jalankan secara lokal di Android/Termux

```bash
pkg update && pkg upgrade
pkg install python unzip
termux-setup-storage
mkdir -p ~/ai-data-analyst
cd ~/ai-data-analyst
unzip ~/storage/downloads/AI_Data_Analyst_Web_Termux.zip
cd AI_Data_Analyst_Termux_MVP
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-termux.txt
python app.py
```

Buka Chrome dan kunjungi `http://127.0.0.1:5000`. Jika folder sudah ada dari versi terdahulu, ekstrak ZIP baru ke folder baru atau buat backup terlebih dahulu. Tekan `Ctrl+C` di Termux untuk menghentikan server.

## Deploy online ke Render

1. Ekstrak ZIP dan buat repository baru di GitHub. Unggah isi folder `AI_Data_Analyst_Termux_MVP` ke akar repository, termasuk `render.yaml`, `Procfile`, dan `requirements.txt` (untuk hosting). Jangan mengunggah ZIP-nya saja; unggah isi foldernya ke akar repository.
2. Buka https://dashboard.render.com/ dan masuk/daftar.
3. Pilih **New + → Blueprint** lalu sambungkan repository GitHub tersebut.
4. Pastikan Render mendeteksi `render.yaml`, kemudian pilih **Apply**. Konfigurasi akan memasang Flask/Gunicorn, membuat `SECRET_KEY`, mengaktifkan cookie secure, lalu menjalankan web service.
5. Tunggu status deploy menjadi **Live**, kemudian buka URL `https://ai-data-analyst.onrender.com` atau URL `onrender.com` yang diberikan dashboard (nama dapat berubah jika sudah dipakai).
6. Buka `/healthz` pada domain tersebut; hasil sehat berupa JSON berstatus `ok`. Kembali ke halaman utama lalu klik **Gunakan data demo**.

Jika Anda tidak menggunakan Blueprint, buat **New + → Web Service**, pilih repository, lalu gunakan:
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn --workers 1 --threads 4 app:app`
- Environment variable `SECRET_KEY`: isi dengan nilai acak yang panjang
- Environment variable `COOKIE_SECURE`: `true`

## Fitur saat ini

- Upload CSV UTF-8 (maksimal 12 MB; Excel perlu disimpan sebagai CSV dahulu).
- Pratinjau 50 baris pertama, statistik ringkas, grafik SVG responsif, dan laporan kualitas data.
- Deteksi anomali dengan z-score dan prediksi tren sederhana dengan regresi linear.
- Unduh hasil kualitas, anomali, serta prediksi ke CSV.
- Data demo dan contoh CSV.

## Batasan dan privasi

- Ini MVP untuk uji coba, **belum aplikasi produksi** dan belum memiliki akun/login.
- Dataset dipisahkan per sesi browser dan disimpan sementara di memori proses, bukan database. Data dapat hilang ketika service restart, tidur, atau deploy ulang. Satu worker disetel agar penyimpanan sesi dalam memori tetap konsisten.
- Jangan unggah data pribadi, keuangan, medis, atau rahasia ke situs publik ini. Siapa pun yang mengetahui URL dapat membuka aplikasinya, walaupun data dataset tiap sesi tidak dibagikan lewat kode ini.
- Render paket gratis dapat tidur setelah 15 menit tanpa lalu lintas; permintaan berikutnya dapat memerlukan sekitar satu menit untuk bangun. Sistem berkas paket gratis bersifat sementara. Lihat dokumentasi: https://render.com/docs/free
- Anomali z-score dan regresi linear hanya metode baseline. Validasi hasil sebelum dipakai untuk keputusan penting.

## Pemecahan masalah

- **Build gagal:** buka tab Logs pada Render dan cek baris error; pastikan `app.py`, `requirements.txt`, dan `render.yaml` ada di akar repository.
- **Aplikasi terbuka tetapi kosong:** klik `Gunakan data demo` atau unggah CSV yang memiliki header dan minimal satu baris data.
- **Health check gagal:** pastikan Start Command tepat `gunicorn --workers 1 --threads 4 app:app` dan path health check `/healthz`.
- **Server lokal Termux tidak bisa dibuka:** pastikan `python app.py` masih berjalan lalu buka `http://127.0.0.1:5000`.
