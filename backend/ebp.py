"""
Agen EBP: pencarian + pembacaan jurnal NYATA dari BANYAK database kredibel, dengan memori bersama.

Sumber (semua gratis, tanpa API key) — dipilih karena KREDIBEL & terindeks ilmiah:
  - PubMed (NCBI E-utilities)          : biomedis/keperawatan, MEDLINE.
  - Europe PMC (EMBL-EBI REST)         : superset biomedis + open access + abstrak.
  - Semantic Scholar (Graph API)       : lintas-disiplin, abstrak, PDF open-access, jumlah sitasi.
Hasil dari ketiganya digabung + dedupe (DOI/PMID/judul), disaring KREDIBEL (punya DOI/PMID + jurnal +
abstrak agar bisa dibaca AI), diprioritaskan: open-access -> terbaru -> banyak disitasi.

Tahun berjenjang: 5 tahun terakhir -> 10 tahun terakhir -> tanpa batas. Bila benar-benar nihil -> jujur.

Memori bersama (ebp_memory.json): tiap artikel yang ditemukan disimpan & dibagikan ke semua user/sesi,
sehingga kasus serupa berikutnya makin cepat ("ingatan" kolektif).
"""
from __future__ import annotations
import os, re, json, time, threading, datetime, urllib.parse, urllib.request
try:
    from defusedxml.ElementTree import fromstring as _xml_fromstring   # parsing XML AMAN (anti XML-bomb / XXE)
except Exception:   # fallback bila defusedxml belum terpasang (sumber XML sudah dibatasi host allowlist)
    from xml.etree.ElementTree import fromstring as _xml_fromstring  # nosec
from concurrent.futures import ThreadPoolExecutor
from langchain_core.messages import SystemMessage, HumanMessage
import crypto_store
from config import CONFIG
from outbound_policy import DEFAULT_OUTBOUND_POLICY

_FILE = os.path.join(os.path.dirname(__file__), "ebp_memory.json")
_LOCK = threading.Lock()
_UA = {"User-Agent": "CDSS-Keperawatan/1.0 (EBP agent; mailto:cdss@local)"}
_TIMEOUT = 14
_PER_SRC = 10      # ambil per sumber (lebih banyak kandidat -> AI bisa rekomendasi >=3 yang relevan)
_MERGED_CAP = 12   # maksimal artikel yang diberikan ke AI untuk dibaca
_ABS_CAP = 1200
_NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_EUPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_S2 = "https://api.semanticscholar.org/graph/v1/paper/search"
_UNPAYWALL = "https://api.unpaywall.org/v2/"
_UNPAYWALL_EMAIL = CONFIG.unpaywall_email


# ----------------------------- util ------------------------------------------
def _year_now() -> int:
    return datetime.datetime.now().year


def _tok(s: str) -> set:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in (s or "")).split() if len(w) > 2}


def _year_int(a: dict) -> int:
    try:
        return int(re.findall(r"\d{4}", str(a.get("year") or ""))[0])
    except Exception:
        return 0


def _uid(a: dict) -> str:
    return (a.get("doi") or a.get("pmid") or (a.get("title") or "")[:80]).lower().strip()


def _access_url(a: dict) -> str:
    if a.get("oa_url"):
        return a["oa_url"]
    if a.get("doi"):
        return "https://doi.org/" + a["doi"]
    if a.get("pmid"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/"
    return ""


def _credible(a: dict) -> bool:
    """Kredibel, OPEN-ACCESS (full-text gratis), & dapat dibaca: DOI/PMID + jurnal + abstrak + akses gratis."""
    return bool(a.get("title") and (a.get("doi") or a.get("pmid")) and a.get("journal")
                and a.get("open_access") and len((a.get("abstract") or "").strip()) >= 40)


_ALLOWED_HOSTS = {"eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk", "api.semanticscholar.org", "api.unpaywall.org"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):   # tolak SEMUA auto-redirect (anti-SSRF via redirect)
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _http(url: str) -> bytes:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host not in _ALLOWED_HOSTS:          # ALLOWLIST: hanya host tepercaya (anti-SSRF) — S1
        raise ValueError(f"host tidak diizinkan: {host}")
    req = urllib.request.Request(url, headers=_UA)
    with _opener.open(req, timeout=_TIMEOUT) as r:  # noqa: S310 (host sudah di-allowlist + tanpa redirect)
        return r.read()


def _http_json(url: str) -> dict:
    return json.loads(_http(url).decode("utf-8", "ignore"))


def _unpaywall_url(doi: str) -> str:
    """Cari lokasi OPEN-ACCESS terbaik untuk sebuah DOI via Unpaywall (gratis). Kosong bila tidak ada versi gratis."""
    if not doi:
        return ""
    try:
        d = _http_json(f"{_UNPAYWALL}{urllib.parse.quote(doi)}?email={urllib.parse.quote(_UNPAYWALL_EMAIL)}")
    except Exception:
        return ""
    if not d.get("is_oa"):
        return ""
    loc = d.get("best_oa_location") or {}
    return (loc.get("url_for_pdf") or loc.get("url") or "").strip()


# ----------------------------- PubMed ----------------------------------------
def _text(el) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def _authors_pubmed(art) -> list:
    """Daftar penulis 'NamaBelakang Inisial' dari XML PubMed (untuk Daftar Pustaka APA 7)."""
    names = []
    for au in art.findall(".//AuthorList/Author"):
        last = (au.findtext("LastName") or "").strip()
        ini = (au.findtext("Initials") or "").strip()
        if last:
            names.append((last + " " + ini).strip())
        else:
            coll = (au.findtext("CollectiveName") or "").strip()
            if coll:
                names.append(coll)
    return names[:25]


def _pubmed(query: str, mn, mx, n: int) -> list:
    try:
        params = {"db": "pubmed", "retmode": "json", "sort": "relevance", "retmax": str(n),
                  "term": query.strip() + ' AND "free full text"[sb]'}   # WAJIB full-text gratis
        if mn and mx:
            params.update({"mindate": str(mn), "maxdate": str(mx), "datetype": "pdat"})
        ids = _http_json(f"{_NCBI}/esearch.fcgi?" + urllib.parse.urlencode(params)).get("esearchresult", {}).get("idlist", []) or []
        if not ids:
            return []
        root = _xml_fromstring(_http(f"{_NCBI}/efetch.fcgi?db=pubmed&retmode=xml&rettype=abstract&id={','.join(ids)}"))  # nosec B314
        out = []
        for art in root.findall(".//PubmedArticle"):
            pmid = (art.findtext(".//PMID") or "").strip()
            doi, pmcid = "", ""
            for aid in art.findall(".//ArticleIdList/ArticleId"):
                t = (aid.get("IdType") or "").lower()
                if t == "doi":
                    doi = (aid.text or "").strip().lower()
                elif t == "pmc":
                    pmcid = (aid.text or "").strip()
            a = {"pmid": pmid, "doi": doi, "pmcid": pmcid,
                 "title": _text(art.find(".//ArticleTitle")),
                 "abstract": " ".join(_text(x) for x in art.findall(".//Abstract/AbstractText")).strip()[:_ABS_CAP],
                 "journal": (art.findtext(".//Journal/Title") or "").strip(),
                 "year": (art.findtext(".//JournalIssue/PubDate/Year") or art.findtext(".//PubDate/Year") or "").strip(),
                 "authors": _authors_pubmed(art),
                 "volume": (art.findtext(".//JournalIssue/Volume") or "").strip(),
                 "issue": (art.findtext(".//JournalIssue/Issue") or "").strip(),
                 "pages": (art.findtext(".//Pagination/MedlinePgn") or art.findtext(".//MedlinePgn") or "").strip(),
                 "oa_url": (f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/" if pmcid else ""),
                 "open_access": True, "citations": 0, "source": "PubMed"}   # sudah disaring free full text[sb]
            out.append(a)
        return out
    except Exception:
        return []


# ----------------------------- Europe PMC ------------------------------------
def _europepmc(query: str, mn, mx, n: int) -> list:
    try:
        q = query.strip() + " AND (OPEN_ACCESS:y)"   # WAJIB open-access (full-text gratis)
        if mn and mx:
            q += f" AND (PUB_YEAR:[{mn} TO {mx}])"
        url = f"{_EUPMC}?" + urllib.parse.urlencode({"query": q, "format": "json", "resultType": "core", "pageSize": str(n)})
        res = _http_json(url).get("resultList", {}).get("result", []) or []
        out = []
        for r in res:
            oa_url = ""
            for u in (((r.get("fullTextUrlList") or {}).get("fullTextUrl")) or []):
                if (u.get("availability") or "").lower().startswith("open") or (u.get("documentStyle") in ("html", "pdf")):
                    oa_url = u.get("url") or oa_url
            ji = r.get("journalInfo") or {}
            journal = (ji.get("journal") or {}).get("title") or r.get("journalTitle") or r.get("source") or ""
            au_str = (r.get("authorString") or "").strip().rstrip(".")
            authors = [x.strip() for x in au_str.split(",") if x.strip()][:25] if au_str else []
            out.append({"pmid": (r.get("pmid") or "").strip(), "doi": (r.get("doi") or "").strip().lower(),
                        "pmcid": (r.get("pmcid") or "").strip(),
                        "title": (r.get("title") or "").strip(),
                        "abstract": (r.get("abstractText") or "").strip()[:_ABS_CAP],
                        "journal": journal.strip(), "year": str(r.get("pubYear") or "").strip(),
                        "authors": authors, "volume": str(ji.get("volume") or "").strip(),
                        "issue": str(ji.get("issue") or "").strip(), "pages": (r.get("pageInfo") or "").strip(),
                        "oa_url": oa_url, "open_access": (r.get("isOpenAccess") == "Y" or bool(oa_url)),
                        "citations": int(r.get("citedByCount") or 0), "source": "Europe PMC"})
        return out
    except Exception:
        return []


# ----------------------------- Semantic Scholar ------------------------------
def _semanticscholar(query: str, mn, mx, n: int) -> list:
    try:
        params = {"query": query.strip(), "limit": str(min(n, 20)),
                  "fields": "title,abstract,year,venue,externalIds,openAccessPdf,citationCount,authors"}
        if mn and mx:
            params["year"] = f"{mn}-{mx}"
        res = _http_json(f"{_S2}?" + urllib.parse.urlencode(params)).get("data", []) or []
        out = []
        for r in res:
            ext = r.get("externalIds") or {}
            oa = (r.get("openAccessPdf") or {}).get("url") or ""
            if not oa:
                continue   # WAJIB open-access (full-text gratis) — lewati yang tidak punya PDF gratis
            authors = [au.get("name", "").strip() for au in (r.get("authors") or []) if au.get("name")][:25]
            out.append({"pmid": str(ext.get("PubMed") or "").strip(), "doi": str(ext.get("DOI") or "").strip().lower(),
                        "title": (r.get("title") or "").strip(), "abstract": (r.get("abstract") or "").strip()[:_ABS_CAP],
                        "journal": (r.get("venue") or "").strip(), "year": str(r.get("year") or "").strip(),
                        "authors": authors, "volume": "", "issue": "", "pages": "",
                        "oa_url": oa, "open_access": bool(oa), "citations": int(r.get("citationCount") or 0),
                        "source": "Semantic Scholar"})
        return out
    except Exception:
        return []


# ----------------------------- agregasi --------------------------------------
def _search_all(query: str, mn, mx, n: int) -> list:
    """Jalankan semua sumber paralel, gabung + dedupe + saring kredibel. Tautan dipastikan di _ensure_access."""
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(fn, query, mn, mx, n) for fn in (_pubmed, _europepmc, _semanticscholar)]
        results = []
        for f in futs:
            try:
                results.extend(f.result() or [])
            except Exception:
                pass
    merged: dict[str, dict] = {}
    for a in results:
        if not _credible(a):
            continue
        uid = _uid(a)
        if not uid:
            continue
        ex_a = merged.get(uid)
        if not ex_a:
            merged[uid] = a
        else:  # gabungkan info terbaik antar sumber (utamakan yang sudah punya tautan akses)
            ex_a["pmcid"] = ex_a.get("pmcid") or a.get("pmcid")
            ex_a["oa_url"] = ex_a.get("oa_url") or a.get("oa_url")
            ex_a["doi"] = ex_a.get("doi") or a.get("doi")
            ex_a["pmid"] = ex_a.get("pmid") or a.get("pmid")
            ex_a["authors"] = ex_a.get("authors") or a.get("authors")
            ex_a["volume"] = ex_a.get("volume") or a.get("volume")
            ex_a["issue"] = ex_a.get("issue") or a.get("issue")
            ex_a["pages"] = ex_a.get("pages") or a.get("pages")
            ex_a["citations"] = max(ex_a.get("citations", 0), a.get("citations", 0))
            if a.get("source") and a["source"] not in (ex_a.get("source") or ""):
                ex_a["source"] = (ex_a.get("source") or "") + "+" + a["source"]
            if len(a.get("abstract") or "") > len(ex_a.get("abstract") or ""):
                ex_a["abstract"] = a["abstract"]
    arts = list(merged.values())
    # yang sudah punya tautan langsung (PMC/OA) didahulukan -> resolusi Unpaywall lebih sedikit
    arts.sort(key=lambda a: (bool(a.get("pmcid") or a.get("oa_url")), _year_int(a), a.get("citations", 0)), reverse=True)
    return arts


def _ensure_access(arts: list) -> list:
    """Pastikan SETIAP artikel punya tautan FULL-TEXT GRATIS yang nyata & bisa dibuka user.
    Prioritas: PMC -> tautan OA dari sumber -> resolusi Unpaywall (DOI). Yang tak punya tautan gratis DIBUANG."""
    out = []
    for a in arts[: _MERGED_CAP + 8]:   # batasi resolusi Unpaywall ke kandidat teratas
        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{a['pmcid']}/" if a.get("pmcid") else ""
        if not url:
            url = a.get("oa_url") or ""
        if not url and a.get("doi"):
            url = _unpaywall_url(a["doi"])
        if url:
            a["oa_url"] = url
            a["url"] = url
            a["open_access"] = True
            out.append(a)
        if len(out) >= _MERGED_CAP:
            break
    return out


def search_tiered(query: str, n: int = _PER_SRC):
    """Berjenjang: 5 thn -> 10 thn -> tanpa batas. Tiap artikel DIJAMIN punya tautan full-text gratis. -> (artikel, tier)."""
    y = _year_now()
    for mn, mx, label in [(y - 5, y, "5 tahun terakhir"), (y - 10, y, "10 tahun terakhir"), (None, None, "tanpa batas tahun")]:
        arts = _ensure_access(_search_all(query, mn, mx, n))
        if arts:
            arts.sort(key=lambda a: (_year_int(a), a.get("citations", 0)), reverse=True)   # rekomendasi: PALING BARU lebih dulu
            for a in arts:
                a["tier"] = label
            return arts, label
    return [], ""


# ----------------------------- memori bersama --------------------------------
def _load() -> list:
    return crypto_store.decrypt_load(_FILE, [])   # TERENKRIPSI at-rest


def _save(items: list):
    crypto_store.encrypt_save(_FILE, items)       # TERENKRIPSI at-rest


def _recall_cached(text: str, k: int) -> list:
    q = _tok(text)
    if not q:
        return []
    scored = []
    for it in _load():
        t = _tok((it.get("title") or "") + " " + (it.get("abstract") or "") + " " + " ".join(it.get("terms", [])))
        sc = len(q & t)
        if sc:
            scored.append((sc, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:k]]


def _store(arts: list, terms_text: str):
    if not arts:
        return
    with _LOCK:
        items = _load()
        by_id = {_uid(it): it for it in items if _uid(it)}
        qterms = list(_tok(terms_text))[:16]
        for a in arts:
            uid = _uid(a)
            ex = by_id.get(uid)
            if ex:
                ex["terms"] = list({*ex.get("terms", []), *qterms})[:60]
                ex["hits"] = int(ex.get("hits", 1)) + 1
            else:
                a2 = dict(a); a2["terms"] = qterms; a2["hits"] = 1; a2["ts"] = time.time()
                items.append(a2); by_id[uid] = a2
        if len(items) > 6000:
            items = sorted(items, key=lambda x: x.get("ts", 0))[-6000:]
        _save(items)


# ----------------------------- jembatan ke LLM -------------------------------
def _english_query(llm, case: str) -> str:
    """Susun kueri Bahasa Inggris TERSTRUKTUR berbasis PICO (personal & spesifik pada kasus) namun tidak terlalu sempit."""
    sys = ("Anda pustakawan medis ahli EBP. Dari kasus klinis (Bahasa Indonesia) berikut, lakukan analisis PICO secara "
           "internal: P (population/problem pasien), I (intervention/topik keperawatan inti), C (comparison — boleh "
           "diabaikan), O (outcome yang diharapkan). Lalu susun SATU baris kueri pencarian Bahasa Inggris yang "
           "menggabungkan konsep P dan I (boleh + O): bentuk (konsep1 OR sinonim OR sinonim) AND (konsep2 OR sinonim OR "
           "sinonim), MAKSIMAL 3 konsep ber-AND agar hasil tidak nihil. Sertakan BANYAK sinonim (2-4 per konsep, termasuk "
           "istilah MeSH umum) dengan OR agar menjangkau SEBANYAK mungkin jurnal relevan. "
           "Keluarkan HANYA kuerinya — tanpa label P/I/C/O, tanpa tanda kutip, tanpa field tag seperti [tiab]/[mesh], "
           "tanpa penjelasan.")
    r = llm.invoke([SystemMessage(content=sys), HumanMessage(content=case[:2000])])
    lines = [ln for ln in (getattr(r, "content", "") or "").strip().splitlines() if ln.strip()]
    q = (lines[-1] if lines else "").strip()                      # ambil baris kuerinya (abaikan baris analisis bila ada)
    q = re.sub(r"^\s*(query|kueri|search)\s*[:\-]\s*", "", q, flags=re.I)
    q = re.sub(r"\[[^\]]*\]", "", q).replace('"', "").strip()
    return q[:240] or case[:200]


def _broaden(q: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z]{4,}", q or "") if w.upper() not in {"AND", "OR", "NOT", "WITH", "FROM", "THAT", "THIS"}]
    return " ".join(words[:3])


def retrieve(english_query: str, recall_text: str = "", k: int = _PER_SRC):
    """Cari lintas-database berjenjang + recall memori bersama. -> (artikel, tier)."""
    live, tier = search_tiered(english_query, k)
    if not live:                                   # kueri terlalu sempit -> coba lebih luas
        broad = _broaden(english_query)
        if broad and broad.lower() != (english_query or "").lower():
            live, tier = search_tiered(broad, k)
    _store(live, ((recall_text or "") + " " + english_query).strip())
    merged: dict[str, dict] = {}
    for a in live:
        if _uid(a):
            merged[_uid(a)] = a
    cached_added = 0
    for a in _recall_cached(recall_text or english_query, k):
        a["url"] = a.get("url") or _access_url(a)
        uid = _uid(a)
        if uid and uid not in merged:
            merged[uid] = a
            cached_added += 1
    if cached_added:
        try:
            import metrics
            metrics.record_cache_hit(cached_added)   # jurnal dari cache bersama (hemat panggilan API) -> metrik CFO
        except Exception:
            pass
    return list(merged.values())[:_MERGED_CAP], tier


def _apa_bits(a: dict) -> str:
    """Ringkas data sitasi (penulis/volume/nomor/halaman/DOI) untuk penyusunan Daftar Pustaka APA 7 oleh AI."""
    parts = []
    au = a.get("authors")
    if au:
        au_str = "; ".join(au) if isinstance(au, list) else str(au)
        parts.append("Penulis: " + au_str[:320])
    if a.get("volume"):
        parts.append("Volume: " + str(a["volume"]))
    if a.get("issue"):
        parts.append("Nomor: " + str(a["issue"]))
    if a.get("pages"):
        parts.append("Halaman: " + str(a["pages"]))
    if a.get("doi"):
        parts.append("DOI: " + str(a["doi"]))
    return "; ".join(parts) if parts else "(penulis/volume tidak tersedia di sumber)"


def retrieve_context(llm, case: str) -> str:
    """Susun query (EN) -> cari lintas-database (PubMed/Europe PMC/Semantic Scholar) berjenjang -> blok konteks NYATA."""
    safe_case = DEFAULT_OUTBOUND_POLICY.deidentified_concept_query(case)
    try:
        q = _english_query(llm, safe_case.text) or safe_case.text
    except Exception:
        q = safe_case.text
    q = DEFAULT_OUTBOUND_POLICY.sanitize_for_external_provider(q).text
    arts, tier = retrieve(q, safe_case.text)
    if not arts:
        return ("\n\nHASIL PENCARIAN JURNAL: KOSONG. Sudah dicari di beberapa database kredibel (PubMed, Europe PMC, "
                "Semantic Scholar) dengan syarat OPEN-ACCESS/FULL-TEXT GRATIS, berjenjang (5 tahun, 10 tahun, lalu tanpa "
                "batas tahun), namun tidak ada hasil (kemungkinan tanpa koneksi internet atau memang belum ada bukti "
                "open-access yang sesuai). Beri tahu perawat dengan JUJUR bahwa TIDAK ADA jurnal open-access yang "
                "mendukung untuk kasus ini, dan tawarkan kata kunci alternatif. DILARANG KERAS mengarang jurnal.")
    head = (f"\n\nDAFTAR JURNAL NYATA dari DATABASE KREDIBEL (kueri: \"{q}\"; rentang tahun: {tier or 'tanpa batas'}; "
            "DIURUTKAN dari yang PALING BARU). Sumber: PubMed / Europe PMC / Semantic Scholar. SEMUA jurnal di bawah "
            "OPEN-ACCESS / FULL-TEXT GRATIS — dapat diakses & dibaca penuh oleh AI maupun perawat. Anda WAJIB HANYA "
            "memakai jurnal dari daftar ini (judul/DOI/URL/penulis PERSIS; DILARANG mengarang atau mengubah). Baca tiap "
            "abstrak, bandingkan, lalu pilih yang BENAR-BENAR RELEVAN dengan kasus DAN paling BARU; ringkas isinya. Jurnal "
            "yang TIDAK relevan dengan kasus JANGAN dimasukkan. Field 'SITASI' tiap jurnal (penulis/volume/nomor/halaman/"
            "DOI) WAJIB dipakai untuk menyusun Daftar Pustaka APA 7 di akhir jawaban — pakai PERSIS, JANGAN mengarang penulis/tahun/DOI.")
    blocks = [head]
    for i, a in enumerate(arts, 1):
        oa = " [OA]" if a.get("open_access") else ""
        cit = f", {a['citations']} sitasi" if a.get("citations") else ""
        blocks.append(f"[{i}] {a['title']} ({a.get('journal','')} {a.get('year','')}{cit}){oa} — sumber: {a.get('source','')}\n"
                      f"    SITASI: {_apa_bits(a)}\n    URL: {a.get('url','')}\n    ABSTRAK: {a.get('abstract') or '(abstrak tidak tersedia)'}")
    return "\n".join(blocks)


def stats() -> dict:
    return {"ebp_jurnal_tersimpan": len(_load())}
