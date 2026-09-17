# LipXMatch — prototipe hackathon

Prototipe Django untuk alur konsumen (profil → persetujuan → preferensi → foto/isi manual → rekomendasi → feedback) dan dashboard R&D. Lima CSV tim di folder `data/` kini dipakai dalam alur utama; data lama di `data/formusense_demo/` tetap mendukung kartu peluang dan grafik lama. Tim tidak memiliki dataset Paragon. Semuanya diperlakukan sebagai **data demo**, bukan bukti permintaan pasar atau hasil uji laboratorium.

## Jalankan lokal

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Buka `http://127.0.0.1:8000/`. Django 5.2 atau 6 pada Python yang didukung dapat dipakai. Jalankan `python manage.py test` untuk memeriksa alur dasar.

## Akun dan batas akses

- **Konsumen:** buat akun di `/accounts/register/`, lalu masuk di `/accounts/consumer/login/`. Pendaftaran publik hanya memberi role `consumer`. Profil warna dan rekomendasi aktif berada di sesi; shade dan foto hasil yang dipilih untuk disimpan tersedia di `/my-profile/`.
- **R&D:** buat akun secara lokal dengan `python manage.py create_rd_user nama_pengguna`, lalu masukkan password ketika diminta. Masuk di `/accounts/rd/login/`. Tidak ada pendaftaran R&D dari website. Superuser Django juga dapat mengakses R&D.
- Pengunjung tanpa akun hanya melihat beranda dan penjelasan. Semua halaman profil, rekomendasi, feedback, dan dashboard R&D diperiksa role-nya di server untuk GET maupun POST. Akun dengan role salah mendapat 403. Keluar memakai tombol **Keluar**.
- Foto untuk coba shade disimpan sementara di `sessionStorage` dengan kunci per akun, dan dihapus oleh tombol keluar pada browser. Foto hasil yang disimpan secara terpisah melalui tombol **Simpan foto hasil ke profil** berada di database lokal, dibatasi delapan foto per akun, hanya dapat dibuka oleh pemilik akun, dan dapat dihapus dari profil.

Untuk demo dua sisi pada satu komputer, pakai dua jendela browser berbeda (misalnya jendela biasa dan incognito), masing-masing login sebagai konsumen dan R&D.

Tanpa pengaturan API, tombol **Gunakan profil demo** dan **Isi profil manual** tetap dapat membawa pengguna sampai rekomendasi. Rekomendasi memakai katalog 30 shade tim, nilai hedonik sintetis, dan review historis demo; feedback baru dari aplikasi disimpan di SQLite lokal.

## Coba alur lengkap dalam 3 menit

1. Buka halaman utama → **Buat akun konsumen** → isi profil singkat.
2. Untuk alur tanpa foto, pilih **Lanjut tanpa foto**, pilih preferensi, lalu **Gunakan profil demo**. Finish `Satin` memang belum ada dalam katalog 30 shade, sehingga halaman rekomendasi menandainya sebagai gap katalog demo dan menampilkan alternatif. Untuk alur kamera, pilih persetujuan foto, lalu **Buka kamera → Ambil foto → Analisis foto**. Unggah JPG/PNG juga tersedia.
3. Periksa/ubah profil, lalu lihat tiga shade dari katalog. Di halaman rekomendasi, coba shade pada foto. Kontur bibir terpasang otomatis bila terdeteksi; jika meleset, klik **Atur posisi bibir** untuk menandai empat titik secara manual. Angka minat komunitas tampil sebagai jumlah respons dengan ukuran sampel, bukan klaim akurasi.
4. Buka salah satu shade → beri feedback. Pilih **Terracotta** pada “warna yang masih dicari” agar permintaan baru dapat diamati.
5. Masuk dengan akun R&D di `/accounts/rd/login/` (gunakan jendela terpisah untuk mempertahankan sesi konsumen), lalu buka **Unmet Demand**. Di sana ada perbandingan finish katalog dengan preferensi hedonik dan feedback lokal, serta 100 kandidat gap dari CSV tim. Pilih salah satu gap untuk membuat draf komposisi dari 500 base formula. **Consumer Evidence** menampilkan ringkasan 300 review historis demo dan feedback lokal secara terpisah.

Form feedback membedakan minat berdasarkan gambar dari pengalaman setelah pemakaian. Rating dan keluhan tekstur hanya disimpan pada jenis pengalaman pemakaian, yang meminta pengguna menyatakan bahwa produk sudah dicoba. Feedback baru masuk dashboard R&D hanya setelah pengguna mencentang persetujuan penggunaan data demo.

## Analisis foto lokal dan AI text

Setelah persetujuan, foto dikirim ke server Django untuk dianalisis **secara lokal**. Model resmi MediaPipe Face Landmarker di `services/models/face_landmarker.task` mencari kontur bibir. OpenCV mengubah sampel warna pipi dan bibir menjadi CIELAB. Warna pipi dicocokkan ke 10 swatch referensi Monk dengan jarak CIELAB terdekat, lalu dipetakan ke lima kategori katalog. Ini hanya proksi pada foto kamera yang tidak dikalibrasi, bukan pengukuran/klasifikasi Monk yang tervalidasi. Kontras bibir-kulit dihitung dari selisih L*. Undertone hanya diberi label bila sinyal warna cukup kuat, selain itu `Belum yakin`. Semua kategori dapat dikoreksi. Foto analisis tidak otomatis disimpan; penyimpanan foto hasil coba shade memerlukan tindakan terpisah dari pengguna. Jika pengguna secara terpisah mengizinkan AI cadangan dan analisis lokal gagal, foto dapat dikirim ke penyedia API vision; pilihan lokal saja tidak mengirim foto ke API. Sistem ini tidak mereplikasi metode k-means dari paper.

Model kontur berasal dari [panduan resmi MediaPipe](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python). File model yang disertakan diunduh dari [aset Face Landmarker resmi](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task); SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`. Nilai hex swatch mengikuti [tabel Monk di presentasi FDA](https://www.fda.gov/media/175828/download). Analisis lokal diuji pada foto contoh MediaPipe. Ketepatan kategori warna pada berbagai kamera, pencahayaan, dan warna kulit **belum diuji**; untuk demo, pakai hasil sebagai titik awal yang harus diperiksa pengguna.

`AI_API_KEY` di `.env` tetap opsional untuk personalisasi teks, ringkasan peluang R&D, dan alasan brief formulasi. Jika API gagal, teks berbasis aturan tetap muncul. Pemeringkatan shade, hitungan feedback, dan draf komposisi tetap menggunakan aturan serta data lokal. Alur scan mengutamakan analisis lokal; bila gagal, ia dapat mencoba vision API sebelum kembali ke input manual.

Kamera langsung memakai izin browser dan hanya muncul setelah persetujuan foto. Saat dipotret, browser membuat file JPEG sementara untuk formulir analisis; alur servernya sama dengan unggah foto. Akses kamera browser membutuhkan **HTTPS atau localhost**. Jika dibuka dari ponsel lewat alamat IP komputer dengan HTTP biasa, gunakan unggah foto atau siapkan HTTPS terlebih dahulu. Foto kamera tidak otomatis dikirim sebelum tombol **Analisis foto** ditekan.

Untuk fitur coba shade, browser menyimpan versi foto yang diperkecil di `sessionStorage` tab yang sama ketika formulir analisis dikirim. Server hanya menyimpan koordinat kontur dan kategori profil dalam sesi, bukan foto analisis. Foto sementara hilang ketika sesi tab browser berakhir; tombol **Hapus foto** menghapusnya lebih awal. Pengguna dapat memilih menyimpan foto hasil yang sudah diberi shade ke profil; gambar diperkecil dan disimpan privat di SQLite lokal sampai dihapus dari profil. Kontur MediaPipe dipakai untuk menaruh warna pada area bibir, sambil menghindari bukaan mulut. Jika kontur tidak ada atau meleset, pengguna menandai empat titik secara manual. Overlay warna di kanvas tetap **simulasi visual**, bukan prediksi warna produk yang terkalibrasi.

Halaman rekomendasi memuat tiga contoh swatch lipstik yang dipilih menurut kedekatan RGB dari **191 baris lipstik** dalam dataset publik Capstone Colors. Contoh tersebut untuk mencoba warna saja; tidak ikut menentukan tiga rekomendasi. Tiga rekomendasi berasal dari katalog 30 shade tim, dengan skor profil/preferensi dan bobot kecil dari 600 penilaian hedonik sintetis serta 300 review demo. Dashboard lama masih menampilkan 5.000 penilaian hedonik sintetis, 500 shade sintetis, dan 200 formula dari jalur eksperimen terpisah; ID seri `S`/`F` tidak digabung dengan CSV tim maupun katalog lama `SHD`. Foundation The Pudding dan formulasi shampoo Nature/Figshare juga tetap referensi terpisah.

Untuk mengecek alur analisis foto pada 30 potret sintetis di `data/pseudo-labels-tone/`, jalankan `python manage.py audit_pseudo_labels`. Hasil per gambar disimpan di `output/pseudo_label_smoke_test.csv`, dengan metadata/pseudo-label sumber dan hasil aplikasi pada kolom terpisah. Ini hanya uji pengembangan: tidak memakai AI API, tidak melatih model, tidak mengubah rekomendasi konsumen, dan tidak menghasilkan skor akurasi pada foto nyata. Metadata undertone sumber bahkan tidak digunakan dalam prompt pembuat gambarnya.

Setelah mengubah `.env`, **restart server**, lalu jalankan `python manage.py check_ai` untuk melihat apakah key diterima dan ID model ada di daftar API. Perintah ini tidak mencetak key dan tidak mengirim foto. Pemeriksaan ini relevan untuk fitur teks dan AI vision cadangan jika pengguna mengizinkannya.

```powershell
$env:AI_BASE_URL="https://ai.sumopod.com/v1"
$env:AI_API_KEY="isi-kunci-di-komputer-sendiri"
$env:AI_TEXT_MODEL="nama-model-text-yang-tersedia"
python manage.py runserver
```

## Peta kode

| Lokasi | Tugas |
| --- | --- |
| `accounts/` | Pendaftaran, login, role, dan pembatasan akses konsumen/R&D |
| `consumer/` | Alur konsumen, form, feedback, shade tersimpan, dan foto hasil privat |
| `research/` | Halaman dashboard R&D |
| `services/data.py` | Pembaca CSV demo |
| `services/team_data.py` | Adapter lima CSV tim, ringkasan hedonik/review, gap finish, dan draf komposisi dari base formula |
| `services/recommendation.py` | Pemeringkatan shade berbasis aturan |
| `services/local_vision.py` | MediaPipe kontur wajah/bibir, pencocokan swatch Monk, dan perkiraan warna lokal berbasis CIELAB |
| `services/ai_client.py` | Adapter API text dan vision cadangan yang hanya dipakai setelah izin foto untuk AI diberikan |
| `services/formula_lab.py` | Pembuat brief arah formulasi dan rencana validasi lab |
| `services/analytics.py` | Hitungan minat, keluhan, spektrum, dan peluang dari demo + feedback lokal |
| `services/dataset_insights.py` | Ringkasan sumber publik/sintetis dan contoh swatch lipstik publik |
| `static/js/tryon.js` | Pratinjau shade di foto pada kanvas browser, dengan kontur otomatis atau posisi manual |
| `static/js/camera.js` | Ambil/unggah foto, pratinjau, dan layar loading selama proses |
| `templates/`, `static/` | UI awal yang dapat diganti sesuai mockup |

## Batas demo yang penting

- Tiga rekomendasi baru memakai katalog 30 shade tim (`001`–`030`). Katalog `SHD` lama tetap ada untuk peluang demo lama; `SHD009 Energized Terracotta` tetap konsep, bukan produk tersedia. Status 30 shade tim dalam portofolio nyata belum diverifikasi.
- Angka komunitas dan KPI memakai data sintetis yang dilabeli jelas. Feedback baru yang masuk aplikasi dihitung terpisah sebagai sinyal lokal. Tiga target peluang tetap berasal dari CSV demo; hitungan permintaan lokal dan keluhan terkait diperbarui saat feedback masuk.
- Formula Lab untuk 100 gap tim menghitung draf persentase baru sebagai rata-rata berbobot tiga base formula terdekat. Ini **bukan model terlatih atau prediksi performa**; jika finish target tidak ada di base formula, halaman menandainya. Jalur `OPP001` lama masih memakai angka draf lama. Semua komposisi, keamanan, warna, stabilitas, dan uji kesukaan tetap perlu diverifikasi formulator/lab.
- Analisis foto mengestimasi penampilan yang terlihat. Aplikasi tidak menilai kesehatan bibir atau melakukan diagnosis.
- Analisis lokal dapat menampilkan “belum yakin” jika atribut warna tidak bisa diperkirakan dari gambar; pengguna bisa mengoreksi seluruh hasilnya. Kategori undertone/kontras masih heuristik demo tanpa evaluasi akurasi.
- Pratinjau shade memakai warna swatch di layar. Hasil di bibir asli dipengaruhi pencahayaan, warna dasar bibir, formula, dan perangkat layar; demo ini belum mengukurnya.

## Langkah implementasi berikutnya

1. Ganti HTML/CSS awal dengan desain Claude yang telah dipilih; rute dan data halaman sudah tersedia.
2. Uji dengan beberapa foto berizin dalam kondisi cahaya dan warna kulit beragam untuk mengukur konsistensi hasil; foto contoh MediaPipe baru memverifikasi alur teknis, bukan akurasi kosmetik.
3. Rapikan katalog menjadi shade yang benar-benar tersedia dan konsep R&D; verifikasi informasi produk.
4. Tetapkan kebijakan retensi/penghapusan data dan tinjau keamanan deployment sebelum aplikasi dipakai di luar demo lokal.
