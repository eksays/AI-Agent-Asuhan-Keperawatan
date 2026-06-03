"""
================================================================
  EKSTRAKTOR BUKU 3S/3N  ->  DATA TERSTRUKTUR (JSON)
================================================================
Skrip ini membaca PDF buku (hasil OCR) dan mengubahnya menjadi
data JSON yang rapi dan terstruktur, dengan bantuan AI untuk
memperbaiki kesalahan OCR sekaligus menyusunnya.

CUKUP DIJALANKAN SEKALI per buku. Hasilnya disimpan ke folder
'data_terstruktur/' dan dipakai selamanya oleh backend.

CARA PAKAI:
  1. Pastikan file PDF ada di folder yang sama, nama sesuai
     KONFIG_BUKU di bawah.
  2. Isi API_KEY dan PROVIDER di bawah.
  3. Jalankan:  python ekstraksi.py

KEAMANAN:
  Jangan pernah commit/upload skrip ini ke GitHub atau share
  ke siapa pun dengan API_KEY masih terisi. Selalu kosongkan
  dulu sebelum bagikan.
================================================================
"""
import os
import re
import json
import time
import pdfplumber

# ============== KONFIGURASI (ISI BAGIAN INI) ==============
PROVIDER = "claude"          # pilih: "gemini" | "openai" | "claude"

# API key WAJIB dibaca dari environment variable — JANGAN pernah hardcode/tempel key di file ini.
#   Windows : set API_KEY_EKSTRAKSI=xxxxx
#   Linux/Mac: export API_KEY_EKSTRAKSI=xxxxx
API_KEY = os.environ.get("API_KEY_EKSTRAKSI", "")

# Buku yang mau diekstrak. Hapus tanda # untuk mengaktifkan buku berikutnya.
# "tipe" menentukan struktur JSON: diagnosis / luaran / intervensi
KONFIG_BUKU = {
    "SDKI":  {"file": "Pdf_Buku_SDKI_OCR.pdf",  "tipe": "diagnosis"},
    # "SLKI":  {"file": "Pdf_Buku_SLKI_OCR.pdf",  "tipe": "luaran"},
    # "SIKI":  {"file": "Pdf_Buku_SIKI_OCR.pdf",  "tipe": "intervensi"},
    # "NANDA": {"file": "Pdf_Buku_NANDA_OCR.pdf", "tipe": "diagnosis"},
    # "NIC":   {"file": "Pdf_Buku_NIC_OCR.pdf",   "tipe": "intervensi"},
    # "NOC":   {"file": "Pdf_Buku_NOC_OCR.pdf",   "tipe": "luaran"},
}

FOLDER_OUTPUT = "data_terstruktur"
# ==========================================================


# ---------- Koneksi ke LLM (tergantung provider) ----------
def panggil_llm(prompt):
    if PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        os.environ["GOOGLE_API_KEY"] = API_KEY
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    elif PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        os.environ["OPENAI_API_KEY"] = API_KEY
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    elif PROVIDER == "claude":
        from langchain_anthropic import ChatAnthropic
        os.environ["ANTHROPIC_API_KEY"] = API_KEY
        # Pakai Haiku 4.5: model terbaru Claude paling murah dan cepat,
        # cocok untuk task ekstraksi repetitif seperti ini.
        llm = ChatAnthropic(model="claude-haiku-4-5", temperature=0)
    else:
        raise ValueError("Provider tidak dikenal")
    return llm.invoke(prompt).content


# ---------- Template prompt per tipe buku ----------
def buat_prompt(tipe, teks_halaman):
    if tipe == "diagnosis":
        skema = """[
  {
    "kode": "D.xxxx",
    "nama": "...",
    "kategori": "...",
    "subkategori": "...",
    "definisi": "...",
    "penyebab": ["..."],
    "gejala_mayor": {"subjektif": ["..."], "objektif": ["..."]},
    "gejala_minor": {"subjektif": ["..."], "objektif": ["..."]}
  }
]"""
    elif tipe == "luaran":
        skema = """[
  {
    "kode": "L.xxxxx",
    "nama": "...",
    "definisi": "...",
    "ekspektasi": "...",
    "kriteria_hasil": ["..."]
  }
]"""
    else:  # intervensi
        skema = """[
  {
    "kode": "I.xxxxx",
    "nama": "...",
    "definisi": "...",
    "tindakan": {"observasi": ["..."], "terapeutik": ["..."], "edukasi": ["..."], "kolaborasi": ["..."]}
  }
]"""

    return f"""Teks berikut adalah hasil OCR buku standar keperawatan yang RUSAK/berantakan.
Tugasmu:
1. Perbaiki kesalahan OCR berdasarkan pengetahuan medis (contoh: "Dasfinisi"->"Definisi", "D10002"->"D.0002").
2. Identifikasi SETIAP entri lengkap di halaman ini dan susun jadi array JSON.
3. Jika sebuah entri terpotong (tidak lengkap di halaman ini), LEWATI saja.
4. Jika tidak ada entri lengkap sama sekali, jawab dengan array kosong: []

Format JSON (array, bisa berisi beberapa entri):
{skema}

Jawab HANYA dengan JSON valid, tanpa penjelasan, tanpa markdown.

TEKS OCR:
{teks_halaman}
"""


def bersihkan_json(teks):
    """Ambil array JSON dari respons, buang markdown fence kalau ada."""
    teks = teks.strip()
    teks = re.sub(r"^```(json)?", "", teks).strip()
    teks = re.sub(r"```$", "", teks).strip()
    # cari array pertama
    awal = teks.find("[")
    akhir = teks.rfind("]")
    if awal != -1 and akhir != -1:
        teks = teks[awal:akhir + 1]
    try:
        return json.loads(teks)
    except Exception:
        return []


def ekstrak_buku(nama, file_pdf, tipe):
    print(f"\n{'='*55}\nMengekstrak {nama} dari {file_pdf}\n{'='*55}")
    if not os.path.exists(file_pdf):
        print(f"  [LEWAT] File {file_pdf} tidak ditemukan.")
        return

    semua_entri = []
    with pdfplumber.open(file_pdf) as pdf:
        total = len(pdf.pages)
        for i, halaman in enumerate(pdf.pages):
            teks = halaman.extract_text() or ""
            if len(teks.strip()) < 50:
                continue  # halaman kosong / sampul
            try:
                hasil = panggil_llm(buat_prompt(tipe, teks))
                entri = bersihkan_json(hasil)
                if entri:
                    semua_entri.extend(entri)
                    print(f"  Hal {i+1}/{total}: +{len(entri)} entri (total {len(semua_entri)})")
                else:
                    print(f"  Hal {i+1}/{total}: -")
            except Exception as e:
                print(f"  Hal {i+1}/{total}: ERROR {e}")
                time.sleep(3)  # jeda kalau kena rate limit
            time.sleep(0.5)    # sopan ke API

    # Buang duplikat berdasarkan kode
    unik = {}
    for e in semua_entri:
        kode = e.get("kode", "").strip()
        if kode and kode not in unik:
            unik[kode] = e
    final = list(unik.values())

    os.makedirs(FOLDER_OUTPUT, exist_ok=True)
    out_path = os.path.join(FOLDER_OUTPUT, f"{nama}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\n  SELESAI: {len(final)} entri unik disimpan ke {out_path}")


if __name__ == "__main__":
    if not API_KEY:
        print("!! Set environment variable API_KEY_EKSTRAKSI dulu (JANGAN hardcode key di file ini).")
    else:
        for nama, konf in KONFIG_BUKU.items():
            ekstrak_buku(nama, konf["file"], konf["tipe"])
        print("\nSemua selesai. Cek folder 'data_terstruktur/'.")