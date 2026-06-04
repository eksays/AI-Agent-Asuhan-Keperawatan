import urllib.request, json, sys

API_BASE = "https://ai.sumopod.com/v1"
API_KEY  = sys.argv[1]
MODEL    = "deepseek-v4-flash"

sample = {
    "kode": "D.0001",
    "nama": "Bersihan Jalan Napas Tidak Efektif",
    "kategori": "Fisiologis",
    "subkategori": "Respirasi",
    "definisi": "",
    "penyebab": [],
    "gejala_mayor": {"subjektif": [], "objektif": []},
    "gejala_minor": {"subjektif": [], "objektif": []}
}

prompt = (
    "Isi field kosong untuk diagnosa keperawatan SDKI berikut. "
    "Output HANYA JSON array berisi 1 object lengkap. "
    "Tidak ada teks lain, tidak ada markdown fence.\n\n"
    + json.dumps([sample], ensure_ascii=False)
)

payload = {
    "model": MODEL,
    "max_tokens": 2048,
    "temperature": 0.3,
    "messages": [
        {
            "role": "system",
            "content": (
                "Kamu adalah pakar keperawatan klinis Indonesia. "
                "Output HANYA valid JSON array. "
                "Tidak ada prosa, tidak ada markdown fence, tidak ada penjelasan. "
                "Gunakan standar SDKI PPNI 2017/2022."
            )
        },
        {"role": "user", "content": prompt}
    ]
}

req = urllib.request.Request(
    f"{API_BASE}/chat/completions",
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    },
    method="POST"
)

with urllib.request.urlopen(req, timeout=120) as r:
    data = json.loads(r.read())

msg = data["choices"][0]["message"]
raw = msg.get("content") or msg.get("reasoning_content") or ""

print("=== RAW OUTPUT ===")
print(repr(raw[:800]))
print()

raw = raw.strip()
if raw.startswith("```"):
    import re
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"```$", "", raw).strip()

try:
    parsed = json.loads(raw)
    print("=== PARSED OK ===")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"=== PARSE ERROR: {e} ===")
    print("Raw was:", raw[:500])
