# FormuSense — prototipe hackathon

Prototipe Django yang bisa dijalankan untuk alur konsumen (profil → persetujuan → preferensi → foto/isi manual → rekomendasi → feedback) dan dashboard R&D. Data awal berasal dari `data/formusense_demo/`. Data tersebut adalah **simulasi**, bukan bukti permintaan pasar atau hasil uji laboratorium.

## Jalankan lokal

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Buka `http://127.0.0.1:8000/`. Django 5.2 atau 6 pada Python yang didukung dapat dipakai. Jalankan `python manage.py test` untuk memeriksa alur dasar.

Tanpa pengaturan API, tombol **Gunakan profil demo** dan **Isi profil manual** tetap dapat membawa pengguna sampai rekomendasi. CSV katalog dan feedback demo dibaca langsung; feedback yang dikirim melalui aplikasi disimpan di SQLite lokal.

## Coba alur lengkap dalam 3 menit

1. Buka halaman utama → **Mulai** → isi atau lewati profil singkat.
2. Untuk alur tanpa foto, pilih **Lanjut tanpa foto**, pilih preferensi `Terracotta` dan `Satin`, lalu **Gunakan profil demo**. Untuk alur kamera, pilih persetujuan foto, lalu **Buka kamera → Ambil foto → Analisis foto**. Unggah JPG/PNG juga tersedia. Layar pemrosesan muncul selama foto dikirim dan dianalisis.
3. Periksa/ubah profil, lalu lihat tiga shade dari katalog. Di halaman rekomendasi, coba shade pada foto. Kontur bibir terpasang otomatis bila terdeteksi; jika meleset, klik **Atur posisi bibir** untuk menandai empat titik secara manual. Angka minat komunitas tampil sebagai jumlah respons dengan ukuran sampel, bukan klaim akurasi.
4. Buka salah satu shade → beri feedback. Pilih **Terracotta** pada “warna yang masih dicari” agar permintaan baru dapat diamati.
5. Setelah mengirim, buka **R&D Preview** → **Unmet Demand**. Jumlah permintaan lokal untuk konsep terracotta bertambah. **Consumer Evidence** menampilkan komentar/keluhan; **Formula Lab** membuat brief dari peluang yang dipilih.

Form feedback membedakan minat berdasarkan gambar dari pengalaman setelah pemakaian. Rating dan keluhan tekstur hanya disimpan pada jenis pengalaman pemakaian, yang meminta pengguna menyatakan bahwa produk sudah dicoba. Feedback baru masuk dashboard R&D hanya setelah pengguna mencentang persetujuan penggunaan data demo.

## Analisis foto lokal dan AI text

Setelah persetujuan, foto dikirim ke server Django untuk dianalisis **secara lokal**. Model resmi MediaPipe Face Landmarker di `models/face_landmarker.task` mencari kontur bibir. OpenCV mengubah sampel warna pipi dan bibir menjadi CIELAB. Warna pipi dicocokkan ke 10 swatch referensi Monk dengan jarak CIELAB terdekat, lalu dipetakan ke lima kategori katalog. Ini hanya proksi pada foto kamera yang tidak dikalibrasi, bukan pengukuran/klasifikasi Monk yang tervalidasi. Kontras bibir-kulit dihitung dari selisih L*. Undertone hanya diberi label bila sinyal warna cukup kuat, selain itu `Belum yakin`. Semua kategori dapat dikoreksi. Foto tidak disimpan server dan tidak dikirim ke Sumopod. Sistem ini tidak mereplikasi metode k-means dari paper.

Model kontur berasal dari [panduan resmi MediaPipe](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python). File model yang disertakan diunduh dari [aset Face Landmarker resmi](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task); SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`. Nilai hex swatch mengikuti [tabel Monk di presentasi FDA](https://www.fda.gov/media/175828/download). Analisis lokal diuji pada foto contoh MediaPipe. Ketepatan kategori warna pada berbagai kamera, pencahayaan, dan warna kulit **belum diuji**; untuk demo, pakai hasil sebagai titik awal yang harus diperiksa pengguna.

`AI_API_KEY` di `.env` tetap opsional untuk **teks**: catatan rekomendasi, ringkasan peluang R&D, dan alasan brief formulasi. Jika API gagal, teks berbasis aturan tetap muncul. Pemeringkatan shade, hitungan feedback, dan arah formula tetap menggunakan aturan serta data lokal. Adapter vision Sumopod lama masih ada di `services/ai_client.py` sebagai kode terpisah, tetapi alur scan sekarang tidak memanggilnya.

Kamera langsung memakai izin browser dan hanya muncul setelah persetujuan foto. Saat dipotret, browser membuat file JPEG sementara untuk formulir analisis; alur servernya sama dengan unggah foto. Akses kamera browser membutuhkan **HTTPS atau localhost**. Jika dibuka dari ponsel lewat alamat IP komputer dengan HTTP biasa, gunakan unggah foto atau siapkan HTTPS terlebih dahulu. Foto kamera tidak otomatis dikirim sebelum tombol **Analisis foto** ditekan.

Untuk fitur coba shade, browser menyimpan versi foto yang diperkecil di `sessionStorage` tab yang sama ketika formulir analisis dikirim. Server hanya menyimpan koordinat kontur dan kategori profil dalam sesi, bukan foto. Foto otomatis hilang ketika sesi tab browser berakhir; tombol **Hapus foto** menghapusnya lebih awal. Kontur MediaPipe dipakai untuk menaruh warna pada area bibir, sambil menghindari bukaan mulut. Jika kontur tidak ada atau meleset, pengguna menandai empat titik secara manual. Overlay warna di kanvas tetap **simulasi visual**, bukan prediksi warna produk yang terkalibrasi.

Halaman rekomendasi memuat tiga contoh swatch lipstik yang dipilih menurut kedekatan RGB dari **191 baris lipstik** dalam dataset publik Capstone Colors. Contoh tersebut untuk mencoba warna saja; tidak ikut menentukan tiga rekomendasi, tidak membuktikan kecocokan undertone, dan ketersediaan produk belum diverifikasi. Dashboard R&D kini menghitung langsung ringkasan **5.000 penilaian hedonik sintetis**, **500 shade sintetis**, serta **200 formula dan keluaran prediksi sintetis**. ID seri `S`/`F` ini tidak dicampur dengan katalog demo `SHD`. Dataset foundation The Pudding dan formulasi shampoo Nature/Figshare ditampilkan sebagai referensi terpisah, bukan masukan rekomendasi lipstik.

Setelah mengubah `.env`, **restart server**, lalu jalankan `python manage.py check_ai` untuk melihat apakah key diterima dan ID model ada di daftar API. Perintah ini tidak mencetak key dan tidak mengirim foto. Pemeriksaan ini hanya relevan untuk fitur teks AI.

```powershell
$env:AI_BASE_URL="https://ai.sumopod.com/v1"
$env:AI_API_KEY="isi-kunci-di-komputer-sendiri"
$env:AI_TEXT_MODEL="nama-model-text-yang-tersedia"
python manage.py runserver
```

## Peta kode

| Lokasi | Tugas |
| --- | --- |
| `consumer/` | Alur konsumen, form, dan penyimpanan feedback |
| `research/` | Halaman dashboard R&D |
| `services/data.py` | Pembaca CSV demo |
| `services/recommendation.py` | Pemeringkatan shade berbasis aturan |
| `services/local_vision.py` | MediaPipe kontur wajah/bibir, pencocokan swatch Monk, dan perkiraan warna lokal berbasis CIELAB |
| `services/ai_client.py` | Adapter API text; adapter vision lama tidak dipakai alur scan |
| `services/formula_lab.py` | Pembuat brief arah formulasi dan rencana validasi lab |
| `services/analytics.py` | Hitungan minat, keluhan, spektrum, dan peluang dari demo + feedback lokal |
| `services/dataset_insights.py` | Ringkasan sumber publik/sintetis dan contoh swatch lipstik publik |
| `static/js/tryon.js` | Pratinjau shade di foto pada kanvas browser, dengan kontur otomatis atau posisi manual |
| `static/js/camera.js` | Ambil/unggah foto, pratinjau, dan layar loading selama proses |
| `templates/`, `static/` | UI awal yang dapat diganti sesuai mockup |

## Batas demo yang penting

- `portfolio_status=opportunity` adalah **konsep R&D** dan sengaja dikecualikan dari tiga rekomendasi produk. Contohnya `SHD009 Energized Terracotta`. Mockup lama menampilkannya sebagai rekomendasi katalog; data katalog justru menandainya sebagai peluang produk baru. Tim perlu memilih status yang benar sebelum demo final.
- Angka komunitas dan KPI memakai data sintetis yang dilabeli jelas. Feedback baru yang masuk aplikasi dihitung terpisah sebagai sinyal lokal. Tiga target peluang tetap berasal dari CSV demo; hitungan permintaan lokal dan keluhan terkait diperbarui saat feedback masuk.
- Tombol Formula Lab menghasilkan brief arah pigmen, basis, dan rencana uji dari target peluang serta feedback saat itu. Contoh angka komposisi untuk `OPP001` berasal dari CSV sintetis yang sudah ada; tombol ini **tidak** menghitung persentase formula baru. Komposisi, keamanan, warna, stabilitas, dan uji kesukaan perlu diverifikasi formulator/lab.
- Analisis foto mengestimasi penampilan yang terlihat. Aplikasi tidak menilai kesehatan bibir atau melakukan diagnosis.
- Analisis lokal dapat menampilkan “belum yakin” jika atribut warna tidak bisa diperkirakan dari gambar; pengguna bisa mengoreksi seluruh hasilnya. Kategori undertone/kontras masih heuristik demo tanpa evaluasi akurasi.
- Pratinjau shade memakai warna swatch di layar. Hasil di bibir asli dipengaruhi pencahayaan, warna dasar bibir, formula, dan perangkat layar; demo ini belum mengukurnya.

## Langkah implementasi berikutnya

1. Ganti HTML/CSS awal dengan desain Claude yang telah dipilih; rute dan data halaman sudah tersedia.
2. Uji dengan beberapa foto berizin dalam kondisi cahaya dan warna kulit beragam untuk mengukur konsistensi hasil; foto contoh MediaPipe baru memverifikasi alur teknis, bukan akurasi kosmetik.
3. Rapikan katalog menjadi shade yang benar-benar tersedia dan konsep R&D; verifikasi informasi produk.
4. Tambahkan autentikasi R&D dan kebijakan retensi/penghapusan data sebelum aplikasi dipakai di luar demo lokal.
