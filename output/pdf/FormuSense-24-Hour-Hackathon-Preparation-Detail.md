# FormuSense - 24-Hour Hackathon Preparation Detail

Dokumen ini adalah pegangan kerja untuk demo 24 jam. Fokusnya bukan membuat sistem produksi penuh, tetapi membuat alur yang terasa nyata: konsumen mendapat rekomendasi shade, memberi feedback, lalu data itu berubah menjadi insight R&D dan draft formula awal.

**FOTO / PROFIL -> 3 REKOMENDASI SHADE -> FEEDBACK -> UNMET DEMAND -> DRAFT FORMULA**

## Target demo

Dalam 5-7 menit, juri harus paham bahwa FormuSense bukan hanya website rekomendasi lipstik. Nilai utamanya adalah closed loop: data konsumen kembali ke R&D untuk menemukan shade yang belum terlayani dan memberi arah eksperimen formulasi.

## Ringkasan scope final

| Fitur utama | Tujuan | Status demo 24 jam |
| --- | --- | --- |
| Consumer Lip Profile Scan | Mengenali profil awal user dari foto/preferensi, lalu memberi ruang koreksi manual. | Work full untuk upload, preferensi, hasil profil, dan edit manual. AI vision boleh semi-work dengan fallback. |
| Personalized Shade Recommendation | Memberi 3 pilihan shade yang mudah dipahami: harian, energik, dan bold. | Work full untuk kartu rekomendasi. Scoring boleh rule-based; AI API cukup untuk narasi. |
| Consumer Feedback Loop | Mengubah pilihan/komentar konsumen menjadi sinyal data untuk R&D. | Work full. Minimal satu feedback user harus terlihat memengaruhi dashboard. |
| R&D Insight & Formula Draft | Menunjukkan unmet demand, consumer evidence, dan draft formula awal untuk review lab. | Work full untuk insight sederhana. Formula generator semi-work dari template/formula dasar. |

## Kategori implementasi

| Status | Dipakai untuk apa | Contoh di demo |
| --- | --- | --- |
| Work full | Harus bisa diklik, berubah state, dan terlihat jalan saat demo. | Upload foto, pilih preferensi, rekomendasi muncul, feedback terkirim, dashboard berubah. |
| Semi-work | Terlihat seperti fitur AI/data berjalan, tetapi boleh memakai API sederhana, aturan manual, atau data demo. | AI profile result, community affinity, chart preference, formula draft. |
| Tunda | Tidak masuk demo 24 jam karena memakan waktu atau klaimnya terlalu besar. | AR try-on, peta Indonesia, trend forecast 6-12 bulan, login, admin panel. |

## 1. Consumer Lip Profile Scan

**Harus work full**

- Consent penggunaan foto sebelum upload.
- Upload foto atau pilih sample photo untuk demo cadangan.
- Preferensi opsional: color family, intensity, finish, mood.
- Hasil profil: skin tone, undertone, lip pigmentation, visible dryness, two-toned appearance.
- Edit profile manual agar demo tetap aman kalau AI salah.

**Semi-work / fallback**

- AI/API membaca foto sebagai estimasi awal, bukan diagnosis.
- Kalau API gagal, sistem memakai preset profile berdasarkan sample user.
- Lighting indicator dan real camera guide cukup visual statis.

**Penjelasan technical**

- Frontend menyimpan image file sementara di browser/session.
- Request ke Vision API mengembalikan JSON profile sederhana.
- App tetap punya fallback JSON lokal: medium skin tone, warm undertone, medium-high lip pigmentation.
- Manual correction menimpa hasil AI dan dipakai untuk rekomendasi.

**Tanda siap demo**

- Consent modal muncul sebelum upload.
- Hasil profil tampil sebagai draft dan bisa diedit.
- Jangan klaim AI menentukan kesehatan bibir atau diagnosis dermatologis.

## 2. Personalized Shade Recommendation

**Harus work full**

- 3 rekomendasi shade: Daily Natural, Energized Vibe, Bold Statement.
- Setiap shade punya swatch, nama, finish, intensity, dan alasan singkat.
- User bisa klik shade untuk melihat detail dan memberi feedback.

**Semi-work / fallback**

- Community affinity pakai demo data.
- Hedonic/preference spectrum cukup bar chart kecil.
- Preview cukup swatch atau lip mockup, bukan AR sungguhan.

**Penjelasan technical**

- Dataset shade berupa JSON/CSV kecil berisi 20-30 shade.
- Scoring lebih baik dibuat rule-based agar stabil saat demo.
- AI API dipakai untuk membuat personal note, bukan menentukan semua keputusan.
- Output rekomendasi selalu berasal dari daftar shade yang sudah disiapkan.

**Tanda siap demo**

- 3 kartu shade selalu muncul setelah profile selesai.
- Energized Terracotta menjadi rekomendasi utama untuk sample user.
- Jika scoring gagal, fallback langsung memanggil 3 shade default.

## 3. Consumer Feedback Loop

**Harus work full**

- Feedback sebelum mencoba: love it, like it, not sure, not for me.
- Feedback setelah mencoba: too pale, just right, too dark; too dry, comfortable, too sticky; finish feedback; rating.
- Komentar opsional.
- Submit feedback harus terlihat masuk ke dashboard.

**Semi-work / fallback**

- Data agregat tetap boleh dummy.
- Minimal feedback user saat demo menambah satu signal di dashboard.
- Komentar bisa muncul sebagai anonymized evidence.

**Penjelasan technical**

- Feedback disimpan sebagai object: user_profile_id, shade_id, feedback_type, color_response, texture_response, finish_response, rating, comment.
- Bedakan color interest dari wear feedback agar klaim data tetap jujur.
- State lokal atau database ringan cukup untuk demo.

**Tanda siap demo**

- Setelah submit, tampil success state dan tombol menuju R&D dashboard.
- Di dashboard, tampil label '+1 new feedback signal' atau komentar terbaru.
- Tidak perlu login atau riwayat user.

## 4. R&D Insight & Formula Draft

**Harus work full**

- Dashboard overview sederhana: total interactions, shade searches, unmet opportunities, satisfaction.
- Unmet demand alert untuk Energized Terracotta.
- Consumer evidence: segment profile, complaints, komentar, preferred finish.
- Formula draft card berbasis formula dasar yang sudah dicek formulator.

**Semi-work / fallback**

- Chart pakai demo dataset statis plus satu feedback user.
- Formula generator cukup generate dari template saat tombol diklik.
- AI API boleh dipakai untuk menjelaskan alasan formula, bukan memberi formula final tanpa guardrail.

**Penjelasan technical**

- Aggregation membaca array demo_feedback dan feedback baru dari user.
- Opportunity dihitung sederhana: high interest + low portfolio match + repeated complaint.
- Formula draft berangkat dari base formula, total komposisi dijaga 100%, dan diberi label 'requires lab validation'.
- Jika belum ada formula dasar valid, tampilkan NEEDS_REFERENCE alih-alih mengarang takaran.

**Tanda siap demo**

- R&D dashboard tidak perlu 7 menu. Cukup Overview, Unmet Demand, Formula Lab.
- Tidak perlu peta Indonesia, trend forecast, costing bahan, atau simulation engine.
- Semua angka dummy diberi label demo/simulation.

## Data yang harus disiapkan

| Data | Isi minimal | Catatan penting |
| --- | --- | --- |
| Shade catalog | 20-30 shade. Kolom: shade_id, name, color_family, hex, undertone_fit, intensity, finish, portfolio_status, source. | Wajib ada swatch/warna. Produk jangan diciptakan AI saat demo; AI hanya memilih dari katalog. |
| Demo consumer profiles | 5-10 profile dummy: region, skin tone, undertone, lip pigmentation, preference. | Dipakai untuk grafik dan fallback jika AI foto gagal. |
| Demo feedback | 20-40 records. Pisahkan color interest dan wear feedback. | Label 'simulation' jika bukan data asli. |
| Base formula reference | 1 formula dasar atau template pigmen yang diperiksa anggota farmasi/formulator. | Kalau belum valid, jangan tampilkan angka komposisi detail. Tampilkan perlu referensi. |
| Portfolio comparison | Daftar shade yang sudah ada dan gap sederhana. | Cukup untuk membuktikan kenapa Energized Terracotta jadi opportunity. |

## Contoh struktur data technical

| Object | Field penting | Dipakai di layar |
| --- | --- | --- |
| user_profile | profile_id, skin_tone, undertone, lip_pigmentation, lip_condition, preferences, source | Lip Profile, Recommendation |
| shade | shade_id, name, hex, family, undertone_fit, finish, intensity, affinity_score | Recommendation, Shade Detail |
| feedback | feedback_id, shade_id, profile_id, feedback_type, color_response, texture_response, finish_response, rating, comment | Feedback, R&D Evidence |
| opportunity | opportunity_id, target_shade, segment, demand_score, portfolio_match, complaints, recommended_finish | Unmet Demand, Product Opportunity |
| formula_draft | formula_id, target_shade, base_formula_id, pigment_adjustment, rationale, validation_status | Formula Lab |

## API dan AI: pakai secukupnya

| Kebutuhan | Pakai AI API untuk | Jangan bergantung penuh pada AI untuk |
| --- | --- | --- |
| Photo analysis | Membaca foto dan mengisi draft profile JSON. | Akurasi final undertone. Tetap beri edit manual. |
| Recommendation explanation | Membuat kalimat personal note yang halus dan mudah dipahami. | Memilih produk bebas dari luar katalog. |
| R&D summary | Meringkas consumer evidence menjadi development brief. | Mengklaim demand pasar nyata jika data masih simulasi. |
| Formula draft | Menjelaskan arah adjustment dari formula dasar. | Membuat formula final siap produksi tanpa review lab. |

## Rencana kerja 24 jam

| Waktu | Target output | PIC ideal |
| --- | --- | --- |
| 0-2 jam | Kunci scope, tentukan sample user utama, tulis dataset schema, bagi tugas. | Semua |
| 2-5 jam | Siapkan shade catalog, feedback dummy, base formula reference, dan copywriting demo. | Farmasi + data |
| 5-9 jam | Bangun consumer flow: consent, upload/sample photo, preferences, lip profile, edit manual. | Frontend + AI |
| 9-13 jam | Bangun recommendation dan feedback: 3 shade cards, detail drawer, submit feedback. | Frontend + data |
| 13-17 jam | Bangun R&D dashboard: overview, unmet demand, evidence, formula lab. | Frontend + data |
| 17-20 jam | Sambungkan alur end-to-end dan fallback: sample data, API failure, tombol reset demo. | Teknis |
| 20-22 jam | Polish UI, cek responsive desktop, rapikan teks, label simulation, consent copy. | UI/UX + semua |
| 22-24 jam | Latihan pitch, siapkan script demo, screenshot backup, dan mode tanpa internet/API. | Semua |

## Pembagian peran praktis

| Peran | Tugas besok | Output yang harus ada |
| --- | --- | --- |
| Leader/Business | Validasi istilah, siapkan shade families, cek base formula, pastikan klaim formula aman. | Katalog shade, formula reference, daftar uji lab yang perlu dilakukan. |
| UI/UX | Buat 6 screen utama, komponen card/chart, dan alur demo yang mulus. | Prototype visual consumer + R&D dashboard. |
| Frontend | Implementasi halaman, state, form, chart, dan navigasi demo. | Web app bisa diklik end-to-end. |
| AI/data | Siapkan JSON/CSV, rule scoring, API prompt, fallback response. | AI profile/recommendation tetap jalan meski API gagal. |
| Leader/Business | Susun narasi masalah, solusi, pembeda, dan batas validasi. | Script presentasi 5-7 menit. |

## Urutan demo yang disarankan

| Menit | Yang ditunjukkan | Kalimat inti |
| --- | --- | --- |
| 0:00-0:45 | Problem dan konsep closed loop. | Memilih shade susah bagi konsumen; bagi R&D, feedback konsumen sering terlambat masuk ke formulasi. |
| 0:45-2:00 | Consumer upload/preference -> lip profile. | AI memberi estimasi awal, tetapi user bisa mengoreksi agar rekomendasi tidak terasa memaksa. |
| 2:00-3:15 | 3 shade recommendation. | Sistem memilih shade dari katalog, lalu menjelaskan alasannya berdasarkan profil dan preferensi. |
| 3:15-4:00 | Feedback submit. | Feedback dibedakan antara minat warna dan pengalaman setelah mencoba produk. |
| 4:00-5:30 | R&D dashboard dan unmet demand. | Feedback yang terkumpul berubah menjadi sinyal kebutuhan shade baru. |
| 5:30-6:30 | Formula draft. | AI membantu membuat draft arah formula untuk review lab, bukan menggantikan formulator. |
| 6:30-7:00 | Closing. | Nilai bisnisnya: R&D menjadi lebih cepat, lebih data-driven, dan tetap tervalidasi secara farmasi. |

## Fallback plan

| Jika masalah terjadi | Fallback saat demo | Yang dikatakan ke juri |
| --- | --- | --- |
| AI photo API gagal | Pakai tombol 'Use demo profile' atau hasil preset otomatis. | Prototype ini mendukung API AI, tetapi demo tetap menjaga alur dengan fallback profile agar evaluasi tidak bergantung pada koneksi. |
| Foto user buruk/gelap | Tampilkan warning ringan dan izinkan edit manual. | Foto memberi estimasi awal; user correction tetap menjadi bagian desain karena lighting memengaruhi hasil. |
| Recommendation scoring bug | Panggil 3 shade default dari katalog. | Untuk prototype, rekomendasi berasal dari katalog terkurasi dan bisa dikembangkan dengan scoring lebih kaya. |
| Feedback tidak tersambung realtime | Tampilkan success state dan dashboard dengan demo aggregate. | Data demo menunjukkan bentuk insight yang akan muncul saat feedback terkumpul. |
| Formula reference belum siap | Tampilkan development brief tanpa angka komposisi detail. | Kami sengaja tidak mengarang formula final tanpa referensi dan validasi formulator. |
| Internet mati | Mode offline: sample photo, static profile, static dashboard, static formula draft. | Core journey tetap bisa dibuktikan walau AI API tidak aktif. |

## Fitur yang dihilangkan dari demo 24 jam

| Fitur | Alasan ditunda | Bisa disebut sebagai next step? |
| --- | --- | --- |
| Login, My Profile, Saved Shades | Tidak membantu membuktikan closed-loop R&D. | Ya, untuk personalisasi jangka panjang. |
| Real AR try-on | Butuh computer vision/face tracking yang makan waktu dan rawan error. | Ya, sebagai enhancement experience. |
| Indonesian map / national shade atlas | Klaim terlalu besar jika data masih dummy. | Ya, jika sudah ada data lokasi dan consent. |
| Trend forecast 6-12 bulan | Butuh data historis yang valid. | Ya, setelah dataset nyata terkumpul. |
| Full feedback explorer | Terlalu banyak UI dashboard untuk 24 jam. | Ya, untuk tim R&D setelah MVP. |
| Formula simulation dan stability prediction | Butuh model/formula data valid serta uji lab. | Ya, tetapi harus dikembangkan bersama formulator. |
| Admin panel dan mass import | Tidak terlihat bernilai saat pitch. | Ya, untuk production. |

## Checklist sebelum presentasi

| Area | Checklist |
| --- | --- |
| Data | Shade catalog siap; angka dummy diberi label simulation; feedback user demo bisa masuk; formula reference jelas. |
| UI | 6 screen utama rapi di desktop 1440 x 900; teks tidak kepanjangan; tombol utama jelas; loading state ada. |
| AI | API prompt siap; response JSON ada; fallback lokal ada; tidak ada klaim diagnosis/produksi final. |
| R&D | Unmet demand mudah dipahami; consumer evidence terlihat; formula draft diberi label lab validation. |
| Pitch | Tim bisa menjelaskan work full vs semi-work; tahu kenapa fitur besar seperti AR/map/trend forecast ditunda. |

## Kalimat aman

Prototype ini menunjukkan alur closed-loop dari konsumen ke R&D. Untuk hackathon, AI analysis dan formula draft dibangun dengan API, aturan sederhana, dan demo dataset. Keputusan formulasi tetap membutuhkan validasi formulator dan uji laboratorium.
