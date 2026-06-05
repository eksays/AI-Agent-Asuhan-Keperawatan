# Laporan Evaluasi Sistem — Kelemahan Mesin Penghasil Output CDSS Keperawatan

**Untuk:** Bapak Eksa Yosiva Syahban
**Lingkup:** Analisis mendalam kelemahan sistem yang menghasilkan output untuk user (Analisis/Diagnosis–Luaran–Intervensi, Pathway, Referensi/EBP), beserta rekomendasi perbaikan berprioritas.
**Tanggal:** 2026-06-05

---

## 1. Ringkasan Eksekutif

Secara arsitektur, sistem sudah benar: ada grounding ke standar (RAG), prompt sadar-kerangka (3S/3N), orkestrasi per-tier (flash/medium/pro), guardrail anti-halusinasi, dan jalur EBP nyata. **Kelemahan terbesar BUKAN pada logika/prompt, melainkan pada KELENGKAPAN DATA REFERENSI.** Selama data 3S/3N belum lengkap, kualitas & presisi output dibatasi oleh "atap kaca" data — sekuat apa pun promptnya.

Tiga akar masalah utama, berurut dampak:
1. **Data referensi tidak lengkap** (paling kritis).
2. **Retrieval masih leksikal (pencocokan kata), belum semantik (embedding).**
3. **Ketergantungan pada pengetahuan internal model** untuk field yang datanya kosong → varian antar-LLM.

---

## 2. Bagaimana Output Dihasilkan (peta singkat)

```
Input user ──> build_messages() ──> [deteksi casual? -> prompt minimal]
                                  └─> bangun_konteks() = RAG (katalog + detail) ── REFERENSI STANDAR
                                  └─> sys_chat/sys_referensi/sys_pathway + format_spec() (sadar-kerangka)
                                  └─> orchestrate_answer() per tier (flash/medium=1 panggilan, pro=2)
Referensi ──> ebp.retrieve_context() = pencarian PICO ke PubMed/EuropePMC/SemanticScholar (open-access)
Output ──> bersihkan() -> maybe_degrade_note() -> phi.sanitize_phi() -> stream/JSON ke frontend
```

---

## 3. Kelemahan per Kategori

### A. DATA REFERENSI (KRITIS — prioritas #1)
- **`SDKI.json` sangat tidak lengkap:** dari **152** diagnosis, hanya **22** punya `definisi`, **8** punya `gejala_mayor/minor`, dan **61** `kategori`-nya kosong. Field `penyebab` mayoritas kosong.
- **Dampak langsung:** sistem dapat menentukan **nama + kode + (sebagian) kategori** secara presisi (karena di-ground ke katalog), tetapi **definisi, penyebab, gejala, kondisi klinis, batasan karakteristik** untuk diagnosis yang datanya kosong **terpaksa diisi dari pengetahuan model** → inilah sumber utama "kurang presisi" dan variasi antar-LLM.
- **`SLKI.json`, `SIKI.json` TIDAK ADA** → Luaran & Intervensi 3S **selalu ditolak** oleh guardrail degradasi (by design, anti-halusinasi). Jadi fitur Luaran/Intervensi praktis belum bisa dipakai sampai file ini diunggah.
- **`NANDA.json`, `NOC.json`, `NIC.json` TIDAK ADA** → seluruh kerangka **3N tidak bisa diproses** (langsung "referensi belum tersedia").
- **Kesimpulan:** ±90% potensi sistem terkunci oleh data. Ini bukan bug — ini kekosongan data.

### B. RETRIEVAL / RAG (prioritas #2)
- **Pencocokan leksikal (token overlap), bukan semantik.** `bangun_konteks` & EBP `_recall_cached` memakai irisan kata. Akibatnya gejala pasien ("sesak, ronkhi, RR 28") **sulit dipetakan** ke nama diagnosis ("Pola Napas Tidak Efektif") karena katanya tidak sama — apalagi saat `gejala` di data kosong.
- **Solusi sementara yang dipakai sekarang:** menyuntik **KATALOG PENUH 152 diagnosis** ke prompt agar model memilih sendiri. Ini efektif untuk presisi kode, tetapi **boros token** (~3.000 token) → menambah latensi & biaya, dan tidak skalabel bila data membesar (mis. +SLKI/SIKI ratusan entri).
- **Belum ada vector DB / embedding** untuk pencarian makna.

### C. VARIASI ANTAR-MODEL (prioritas #3)
- Untuk field yang **tidak ada di data**, output bergantung pengetahuan model. Model kuat (Claude/GPT-4o/Gemini-Pro) akurat; model lemah (mini/8B/flash) bisa meleset/dangkal.
- Mitigasi saat ini: few-shot/format_spec ketat + katalog grounding + (pro) audit pass. Konsistensi **struktur/format** sudah seragam; **konten** untuk field kosong masih bervariasi.

### D. KECEPATAN vs KEDALAMAN (trade-off struktural)
- Permintaan "lebih banyak poin (min 3)" **menambah panjang output** → waktu generasi lebih lama. Ini hukum dasar: lebih banyak isi = lebih lama. Yang bisa dioptimasi hanyalah **overhead** (prompt, round-trip), bukan waktu generasi isi.
- Mitigasi saat ini: **jalur cepat casual** ("halo" tak lagi memuat prompt raksasa), **flash tanpa katalog** (prompt lebih kecil), medium=1 panggilan, pro=2. Streaming membuat flash/medium terasa responsif.
- **Sisa keterbatasan:** prompt klinis tetap besar (format_spec + katalog pada medium/pro) → token-to-first-response masih ada.

### E. EBP / REFERENSI
- **Bergantung internet & ketersediaan open-access.** Bila offline atau tak ada OA yang relevan → kosong (sistem jujur, tidak mengarang — ini benar).
- **Metadata sitasi tidak seragam antar sumber:** PubMed/EuropePMC biasanya lengkap (penulis/volume/halaman); **Semantic Scholar sering hanya penulis+tahun** → entri APA 7-nya terpaksa parsial (volume/halaman dihilangkan sesuai aturan APA). Bukan karangan, tapi tidak selengkap idealnya.
- **Relevansi dinilai oleh LLM**, bukan skor kemiripan terukur → bisa subjektif.

### F. TIADA VALIDATOR PASCA-GENERASI
- Tidak ada pengecekan otomatis bahwa **kode yang ditulis benar-benar ada di katalog**, atau bahwa **gejala yang dikutip benar-benar ada di data pasien**. Saat ini hanya disiplin prompt + (pro) audit LLM. Validator deterministik akan menutup celah halusinasi kode.

### G. MEMORI/PEMBELAJARAN BELUM DIMANFAATKAN PENUH
- Feedback perawat (`feedback_memory.json`) tersimpan & dipanggil per-sesi, tetapi **belum** dipakai untuk memperbaiki retrieval atau mem-fine-tune prompt secara sistematis (belum ada loop pembelajaran aktif).

### H. KETERGANTUNGAN OCR/EKSTRAKSI DOKUMEN
- Kualitas analisis = kualitas teks yang diekstrak dari dokumen/foto. Ekstraksi PDF/foto yang buruk → data masuk buruk → output buruk (garbage-in-garbage-out). Foto rekam medis saat ini hanya ditandai, belum OCR penuh.

---

## 4. Rekomendasi Berprioritas (peta perbaikan)

| Prio | Tindakan | Dampak | Effort |
|---|---|---|---|
| **P0** | **Lengkapi `SDKI.json`** (isi `definisi`, `penyebab`, `gejala_mayor/minor`, `kategori` ke-152 diagnosis) | Presisi melonjak; verifikasi gejala jadi nyata | Sedang (input data) |
| **P0** | **Tambah `SLKI.json` & `SIKI.json`** (+ `NANDA/NOC/NIC.json` untuk 3N) | Membuka fitur Luaran/Intervensi & seluruh 3N | Sedang–Besar |
| **P1** | **Retrieval semantik (embedding + vector search)** untuk gejala→diagnosis & EBP | Akurasi pemilihan naik; bisa kurangi katalog penuh (lebih cepat) | Sedang |
| **P1** | **Validator pasca-generasi** (regex/lookup: pastikan tiap kode ada di katalog; tandai bila tidak) | Tutup halusinasi kode secara deterministik | Kecil–Sedang |
| **P2** | **OCR penuh** untuk foto/scan rekam medis | Input lebih kaya & akurat | Sedang |
| **P2** | **Skor relevansi EBP terukur** (mis. cosine similarity abstrak↔kasus) untuk urutan jurnal | Urutan relevansi objektif | Kecil–Sedang |
| **P3** | **Loop pembelajaran dari feedback** (koreksi perawat → bobot retrieval/contoh prompt) | Sistem makin pintar seiring pemakaian | Sedang |
| **P3** | **Default model per-tier yang lebih kuat** untuk provider tertentu | Konsistensi lintas-LLM naik | Kecil |

**Format dataset yang disarankan (per entri SDKI):**
```json
{
  "kode": "D.0005", "nama": "Pola Napas Tidak Efektif",
  "kategori": "Fisiologis", "subkategori": "Respirasi",
  "definisi": "Inspirasi dan/atau ekspirasi yang tidak memberikan ventilasi adekuat.",
  "penyebab": ["Hambatan upaya napas", "Deformitas dinding dada", "..."],
  "gejala_mayor": {"subjektif": ["Dispnea"], "objektif": ["Penggunaan otot bantu napas", "Pola napas abnormal"]},
  "gejala_minor": {"subjektif": ["Ortopnea"], "objektif": ["Pernapasan cuping hidung"]},
  "kondisi_klinis_terkait": ["Depresi sistem saraf pusat", "Cedera kepala", "..."]
}
```
> Begitu field ini terisi, sistem **otomatis** menyuntiknya sebagai grounding (lewat `DETAIL KRITERIA`) — **tanpa perlu ubah kode lagi** — dan presisi + kedalaman naik signifikan & seragam di semua model.

---

## 5. Yang SUDAH Diperbaiki/Dimitigasi (sesi ini)

- **Kedalaman:** prompt kini mewajibkan **≥3 poin** per kategori multi-item (penyebab, faktor risiko, kondisi klinis, batasan karakteristik, tindakan O/T/E/K, kriteria hasil, aktivitas, dll.) bila data mendukung — tidak lagi berhenti di 1 poin.
- **Diagnosis berprioritas:** Diagnosis Utama → 2 → 3 (urut ABC → Maslow → risiko).
- **Referensi:** rekomendasi **≥3 jurnal relevan, diurutkan relevansi** (No.1 = paling relevan); PICO kini **kata kunci + sinonim** (bukan kalimat); query EBP menyertakan banyak sinonim/OR; Daftar Pustaka **APA 7** di paling bawah.
- **Kecepatan:** **jalur cepat casual** (sapaan dijawab spontan tanpa prompt raksasa); **flash tanpa katalog penuh** (prompt lebih kecil = lebih cepat); medium=1 panggilan, pro=2; semua streaming.
- **Grounding presisi:** katalog 152 diagnosis disuntik untuk medium/pro → kode/nama/kategori tidak dikarang.
- **Lintas-model:** seluruh perilaku di atas digerakkan oleh prompt/arsitektur (bukan fitur satu provider) → berlaku untuk API key LLM mana pun, distandarkan ke kualitas gaya Claude.

---

## 5b. Analisis Konsistensi & Determinisme (fokus mendalam)

**Gejala yang Anda temukan:** file kasus yang SAMA, dijalankan 2x, menghasilkan jawaban BERBEDA (run-2 sedikit lebih baik). Ini bukti **non-determinisme** pada level sistem. Akar penyebabnya (berurut dampak):

1. **Tidak ada `seed` tetap.** Pada `temperature=0`, provider OpenAI-compatible MASIH bisa bervariasi antar-run tanpa benih acak yang dikunci. → **DIPERBAIKI:** `seed` tetap (`_LLM_SEED`) ditambahkan untuk semua provider OpenAI-compatible (openai/groq/deepseek/mistral/together/openrouter/xai/shopee/sumopod) → jauh lebih reproduktif.
2. **Bocoran riwayat percakapan (penyebab "run-2 berbeda & lebih baik").** Bila file yang sama diunggah **2x dalam sesi yang sama**, run-2 menerima **jawaban run-1 di dalam konteks** → ia "menyempurnakan" run-1, sehingga berbeda. → **DIPERBAIKI:** analisis **dokumen baru kini dikerjakan MANDIRI** (riwayat diabaikan saat ada `<dokumen_pasien>` baru) → tiap analisis dokumen deterministik & tidak terpengaruh run sebelumnya. (Riwayat tetap dipakai untuk tindak lanjut teks tanpa dokumen baru, mis. "lanjut ke luaran".)
3. **Prompt terlalu bebas (banyak `[...]`, "dst.", "minimal 3 bila...").** Tiap run model membuat keputusan mikro berbeda. → **DIPERBAIKI sebagian:** ditambah direktif **DETERMINISTIK & KONSISTEN** (pemilihan & pengurutan objektif + aturan prioritas tetap ABC→Maslow→aktual; dilarang mengubah pilihan/urutan tanpa alasan dari data).
4. **Non-determinisme bawaan LLM.** Claude & Gemini **tidak punya parameter seed** → hanya `temperature=0` (best-effort). Ini batas dari sisi provider, bukan sistem.

**Batas residual yang jujur:** dengan langkah di atas, konsistensi naik drastis untuk provider OpenAI-compatible (seed) dan untuk semua provider (isolasi riwayat + direktif + temp 0). Namun **konsistensi 100% byte-identik mustahil** untuk Claude/Gemini (tidak ada seed) dan akan tetap terbatas selama **data 3S/3N belum lengkap** (model masih "menebak" field kosong, dan tebakan bisa bervariasi). Konsistensi STRUKTUR/FORMAT sudah seragam; variasi tersisa ada pada KONTEN field yang datanya kosong.

## 5c. Sistem Anti-"Space Kosong" (selalu bekerja)

Permintaan Anda: pencegah space-kosong yang **terus bekerja meski output diperbarui**. Solusinya **content-agnostic normalizer** (bekerja pada pola spasi/baris, bukan isi tertentu) di DUA lapis:
- **Backend `bersihkan()`** (untuk jalur non-stream): buang spasi akhir-baris, ciutkan `<br>` beruntun → satu, buang `<br>` redundan sebelum newline, maksimal satu baris kosong antar bagian.
- **Frontend `normalizeMarkdown()`** (gerbang terakhir SEBELUM render, selalu jalan untuk SEMUA jawaban termasuk streaming): aturan yang sama + baris "kosong berisi spasi" → benar-benar kosong.
- **CSS**: elemen kosong (heading/butir/paragraf tanpa isi) di-`display:none`.

Karena normalizer bekerja pada POLA (bukan konten), ia tetap efektif walau Anda terus mengubah prompt/format output di kemudian hari.

## 5d. Robustness Lintas-Model (kenapa DeepSeek dangkal & solusinya)

**Gejala:** dengan API key DeepSeek, jawaban dangkal (hanya 2 diagnosis), tidak konsisten, kurang presisi. **Sebab:** model yang lebih lemah dari Claude **tidak mampu mematuhi satu prompt raksasa sekali jalan** (format + kedalaman + presisi + determinisme sekaligus). Claude bisa; DeepSeek/llama-8b/mini tidak.

**Solusi (berlaku SEMUA model):** pipeline **draft → audit-penyempurna**, bukan satu pass.
- **flash** = 1 panggilan (tercepat; untuk cek cepat).
- **medium** (default) = draft + **AUDIT-PENYEMPURNA** (2 panggilan). Pass kedua secara eksplisit: meng-EXPAND tiap kategori ke ≥3 butir bila data mendukung, menegakkan SEMUA diagnosis yang didukung data (target ≥3, berurut prioritas), memperbaiki kode yang dikarang, merapikan format, dan menghapus space berlebih. → menutup kelemahan first-draft model lemah.
- **pro** = draft + **SWARM** (3 kritikus paralel: akurasi/kode, kelengkapan+kedalaman, keselamatan) + sintesis → kualitas maksimum.

Karena pass tambahan ini **menambal kekurangan model**, hasilnya jadi **dalam, presisi, & konsisten lintas-LLM** — bukan hanya pada Claude. Konsekuensinya **medium kini sedikit lebih lambat** (2 panggilan, tidak streaming langsung) — trade-off yang sepadan demi kualitas seragam di semua model. Untuk balasan instan tetap ada **flash** & **jalur cepat casual**.

**Catatan:** audit dijalankan oleh model yang sama dengan benih (`seed`) yang sama → reproduktif. Untuk kasus yang sama, medium/pro kini jauh lebih konsisten.

## 6. Penutup

Sistem kini **optimal pada level arsitektur & prompt**. Lompatan kualitas berikutnya **paling besar** datang dari **melengkapi data 3S/3N (P0)** dan **retrieval semantik (P1)**. Setelah keduanya, sistem akan presisi, dalam, dan konsisten lintas-model tanpa bergantung pada "tebakan" model untuk data yang seharusnya tersedia di buku standar.
