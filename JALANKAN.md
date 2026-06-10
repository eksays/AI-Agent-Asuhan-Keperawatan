# CDSS AI Keperawatan - Cara Menjalankan

Status saat ini: clinical sandbox. Fitur yang belum terverifikasi dinonaktifkan secara default oleh backend. Saran AI wajib ditinjau perawat dan aplikasi ini tidak boleh dipakai untuk keputusan klinis mandiri.

Secara default, analisis LLM eksternal, pencarian EBP eksternal, analisis foto klinis, rendering Mermaid pathway, dan fondasi RAG Phase 9 dinonaktifkan. Phase 7 menambahkan audit ledger lokal berbasis HMAC. Kontrol autentikasi, sesi, MFA, rate limit, audit, dan RAG tetap kontrol sandbox lokal, bukan kontrol produksi terdistribusi.

Aplikasi terdiri dari dua bagian:

- backend/ - FastAPI (Python), port 8000
- frontend/ - Next.js (React 19), port 3000

## Cara tercepat
Klik dua kali `start-all.bat` di folder ini. Dua jendela terminal akan terbuka (backend + frontend). Setelah keduanya siap, buka browser ke http://localhost:3000. Network-host development access, such as `http://172.16.0.2:3000`, is not the default supported origin and may require an explicit development-only allowlist.

## Manual (dua terminal)

Terminal 1 - Backend:

```powershell
cd backend
$env:APP_MODE="clinical_sandbox"
$env:CDSS_API_KEYS="test-key"
$env:CDSS_SECRET_KEY="local-sandbox-secret-change-me"
# Opsional untuk audit ledger persisten lokal; jangan commit nilainya.
# $env:AUDIT_LEDGER_HMAC_KEY="isi-dengan-secret-kuat-operator-lokal"
# $env:AUDIT_LEDGER_KEY_ID="audit-ledger-local-v1"
# $env:AUDIT_LEDGER_PATH="backend\audit_ledger.jsonl"
# RAG Phase 9 P9-A default-off. Jangan aktifkan kecuali menjalankan uji sintetis lokal yang eksplisit.
# $env:RAG_RUNTIME_MODE="disabled"
python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```

Jika `python` tidak dikenali, pakai jalur lengkap instalasi Python lokal.

Terminal 2 - Frontend:

```powershell
cd frontend
npm install
npm run dev
```

## Instalasi dependency backend

```powershell
cd backend
pip install -r requirements.txt
```

## Cara pakai

1. Buka http://localhost:3000.
2. Isi nama lengkap dan API Key. Frontend mengirim kunci hanya melalui header `Authorization: Bearer <key>` dan tidak menyimpannya ke `localStorage` atau `sessionStorage`.
3. Klik Get Start untuk masuk ke Dashboard.
4. Ketik perintah di chatbox. Pilih kerangka 3S (SDKI/SLKI/SIKI) atau 3N (NANDA/NOC/NIC) lewat toggle di samping tombol Plus.

## Catatan keamanan Phase 6

- Backend menerbitkan `session_id` dan `session_token`; request berikutnya memakai header `X-Session-Token`.
- Token sesi disimpan browser-side di memori React saja, bukan storage persisten.
- `/director/enroll` memakai header `X-Director-Bootstrap`, bukan token query-string.
- TOTP direktur memiliki replay rejection dan lockout, tetapi state hilang saat proses backend restart.
- Rate limit berbasis memori cocok untuk sandbox lokal saja; kontrol pilot membutuhkan store bersama/durable.
- Browser-carried shared API key tetap terlihat oleh browser client; header-only hanya mencegah kebocoran lewat body, URL, cookie, dan browser storage.
- Shared API key bukan identitas user rumah sakit, bukan RBAC, bukan SSO/OAuth/OIDC.
- Enrollment MFA direktur default-off; provisioning lokal sandbox membutuhkan `DIRECTOR_ENROLLMENT_ENABLED=true` dan header `X-Director-Bootstrap`.
- `controlled_pilot` dan `production` menolak secret yang hilang, lemah, atau placeholder.

## Catatan keamanan Phase 7

- Audit ledger memakai event terstruktur, canonical JSON, dan HMAC-SHA256 chain.
- Tanpa `AUDIT_LEDGER_HMAC_KEY`, sandbox lokal memakai ledger in-memory ephemeral dan tidak membuat klaim persistensi.
- Jika `AUDIT_LEDGER_PATH` diaktifkan, gunakan `AUDIT_LEDGER_HMAC_KEY` kuat dan jangan commit ledger runtime.
- Ledger lokal bukan WORM, bukan immutable storage, bukan tanda tangan digital, dan bukan bukti compliance.
- Admin host yang memiliki file ledger dan key masih dapat menulis ulang histori; penghapusan record terakhir dapat menyisakan prefix yang tetap valid secara lokal tanpa checkpoint eksternal. Segment rotation tersedia, key rotation belum tersedia. Storage immutable eksternal tetap diperlukan sebelum klaim pilot/produksi.

## Catatan keamanan Phase 9 P9-A

- P9-A hanya menambahkan fondasi skema corpus RAG dan probe pgvector yang aman.
- RAG produk saat ini tetap prototipe leksikal; hybrid retrieval, embedding, vector retrieval, reranking, dan provider embedding eksternal belum diimplementasikan.
- `RAG_RUNTIME_MODE=disabled` dan semua flag RAG bernilai `false` secara default.
- `RAG_RUNTIME_MODE=synthetic_corpus_test` hanya untuk sandbox lokal dan mensyaratkan `REGISTRY_ACTIVATION_ENABLED=false`.
- Jangan ingest data pasien, PHI, corpus klinis berlisensi, atau isi SDKI/SLKI/SIKI/NANDA/NOC/NIC ke tabel RAG.
- Tabel active index release harus tetap kosong pada P9-A; tidak ada aktivasi index produk.

## Perilaku agen

- Menjalankan persis sesuai perintah.
- Clinical Pathway atau diagram hanya dibuat bila diminta eksplisit dan capability Mermaid tetap default-off.
- Output klinis tetap membutuhkan validasi schema/registry dan review perawat.
- Token API habis atau invalid menampilkan banner safe generic.

## Catatan

- `GET http://127.0.0.1:8000/docs` dapat dipakai untuk menguji API langsung.
- Basis pengetahuan lokal di `backend/data_terstruktur/` tetap non-authoritative dan tidak boleh diaktifkan hanya karena file ada.
- Registry resmi memerlukan provenance, lisensi, review klinis, release manifest, dan aktivasi eksplisit.
- Fondasi RAG resmi memerlukan governance corpus, review lisensi, benchmark retrieval, dan aktivasi eksplisit pada fase berikutnya; P9-A belum memenuhi itu.
- Koreksi/feedback lokal dapat memuat data sensitif; jangan commit file memori runtime.
