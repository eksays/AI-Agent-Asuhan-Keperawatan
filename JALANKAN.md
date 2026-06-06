# CDSS AI Keperawatan — Cara Menjalankan

Status saat ini: **clinical sandbox**. Fitur yang belum terverifikasi dinonaktifkan secara default oleh backend. Saran AI wajib ditinjau perawat dan aplikasi ini tidak boleh dipakai untuk keputusan klinis mandiri.

Secara default, analisis LLM eksternal, pencarian EBP eksternal, analisis foto klinis, dan rendering Mermaid pathway dinonaktifkan sampai kontrol keamanan terkait diverifikasi.

Aplikasi terdiri dari dua bagian:

- **backend/** — FastAPI (Python), port **8000**
- **frontend/** — Next.js (React 19), port **3000**

## Cara tercepat
Klik dua kali **`start-all.bat`** di folder ini. Dua jendela terminal akan terbuka
(backend + frontend). Setelah keduanya siap, buka browser ke **http://localhost:3000**.

## Manual (dua terminal)
**Terminal 1 — Backend**
```
cd backend
python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```
(jika `python` tidak dikenali, pakai jalur lengkap, mis. `"E:\Program\Instalan\Python 3.12.8\python.exe"`)

**Terminal 2 — Frontend**
```
cd frontend
npm install   # cukup sekali
npm run dev
```

## Instalasi dependency backend (sekali saja)
```
cd backend
pip install -r requirements.txt
```

## Cara pakai
1. Buka http://localhost:3000 — muncul layar Welcome.
2. Isi **nama lengkap** dan **API Key**. Provider terdeteksi otomatis dari awalan key:
   `sk-ant-`→Claude, `AIza`→Gemini, `sk-or-`→OpenRouter, `gsk_`→Groq, `xai-`→Grok,
   `shpe/shopee/spc_`→ShopeeAI, `sk-`→OpenAI, lainnya→OpenRouter.
3. Klik **Get Start** → masuk ke Dashboard.
4. Ketik perintah di chatbox. Pilih kerangka **3S** (SDKI/SLKI/SIKI) atau **3N** (NANDA/NOC/NIC) lewat toggle di samping tombol Plus.

## Perilaku agen (Phase 3)
- Menjalankan **persis** sesuai perintah (mis. minta "diagnosis saja" → hanya diagnosis).
- Lampiran rekam medis tanpa perintah → otomatis **Asuhan Keperawatan standar** (Data → Diagnosis → Luaran → Intervensi) via *multi-agent swarm*.
- **Clinical Pathway / diagram hanya** dibuat bila diminta eksplisit (kata kunci: pathway, patofisiologi, alur, diagram).
- Output **tanpa emoji/simbol**, gaya rekam medis resmi, menyertakan kode standar.
- Membaca **seluruh riwayat** percakapan dalam satu sesi (SessionMemory).
- Jawaban mengalir **real-time** (streaming/typewriter).
- Token API habis/invalid → banner **"Token API Habis"**.

## Catatan
- `GET http://127.0.0.1:8000/docs` untuk menguji API langsung (Swagger).
- Basis pengetahuan terstruktur saat ini: **SDKI (152 entri)** di `backend/data_terstruktur/SDKI.json`.
  Tambahkan `SLKI.json`, `SIKI.json`, dst. dengan format yang sama untuk memperkaya retrieval.
- Koreksi dari tombol 👎 disimpan di `backend/feedback_memory.json` (RLHF) dan otomatis
  dipertimbangkan pada kasus serupa berikutnya.
