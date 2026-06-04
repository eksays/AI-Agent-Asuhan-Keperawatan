"""
Populate empty SDKI entries with the Anthropic Messages API.

Run once from the repository root or from backend/scripts:
    python backend/scripts/populate_sdki.py

Required environment:
    ANTHROPIC_API_KEY=<your key>

Optional environment:
    ANTHROPIC_MODEL=<model name>  (default: claude-3-5-sonnet-latest)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import textwrap
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request


API_BASE = os.environ.get("API_BASE", "https://ai.sumopod.com/v1")
API_KEY  = os.environ.get("API_KEY") or os.environ.get("SUMOPOD_API_KEY")
MODEL    = os.environ.get("MODEL", "deepseek-v4-flash")  # non-reasoning model, reliable JSON output
DEFAULT_MODEL = MODEL
DEFAULT_BATCH_SIZE = 3   # dikurangi dari 5 → 3 agar prompt+output tidak terpotong
DEFAULT_MAX_TOKENS = 4096
RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504}


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DEFAULT_SDKI_PATH = BACKEND_DIR / "data_terstruktur" / "SDKI.json"
DEFAULT_REPORT_PATH = BACKEND_DIR / "data_terstruktur" / "SDKI_population_report.json"

GEJALA_KEYS = ("subjektif", "objektif")


def load_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return data


def atomic_write_json(path: Path, payload: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp_path.replace(path)


def entry_has_definisi(entry: dict[str, Any]) -> bool:
    return bool(str(entry.get("definisi", "")).strip())


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _gejala_dict(value: Any) -> dict[str, list[str]]:
    source = value if isinstance(value, dict) else {}
    return {key: _as_list(source.get(key)) for key in GEJALA_KEYS}


def entry_is_complete_for_gate(entry: dict[str, Any]) -> bool:
    if not entry_has_definisi(entry):
        return False
    # Diagnosa "Risiko" tidak punya gejala mayor — cukup punya definisi + faktor_risiko
    is_risiko = str(entry.get("nama", "")).strip().lower().startswith("risiko")
    if is_risiko:
        return bool(_as_list(entry.get("faktor_risiko"))) or bool(_as_list(entry.get("penyebab")))
    mayor = _gejala_dict(entry.get("gejala_mayor"))
    has_gejala = bool(mayor["objektif"]) or bool(mayor["subjektif"])
    return has_gejala


def has_few_shot_detail(entry: dict[str, Any]) -> bool:
    if not entry_has_definisi(entry):
        return False
    if not _as_list(entry.get("penyebab")):
        return False
    mayor = _gejala_dict(entry.get("gejala_mayor"))
    minor = _gejala_dict(entry.get("gejala_minor"))
    return bool(mayor["subjektif"] or mayor["objektif"] or minor["subjektif"] or minor["objektif"])


def normalize_for_prompt(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "kode": str(entry.get("kode", "")).strip(),
        "nama": str(entry.get("nama", "")).strip(),
        "kategori": str(entry.get("kategori", "")).strip(),
        "subkategori": str(entry.get("subkategori", "")).strip(),
        "definisi": str(entry.get("definisi", "")).strip(),
        "penyebab": _as_list(entry.get("penyebab")),
        "gejala_mayor": _gejala_dict(entry.get("gejala_mayor")),
        "gejala_minor": _gejala_dict(entry.get("gejala_minor")),
    }


def pick_few_shot_examples(entries: list[dict[str, Any]], count: int = 7) -> list[dict[str, Any]]:
    detailed = [normalize_for_prompt(entry) for entry in entries if has_few_shot_detail(entry)]
    if len(detailed) >= count:
        return detailed[:count]

    filled = [normalize_for_prompt(entry) for entry in entries if entry_has_definisi(entry)]
    seen = {example["kode"] for example in detailed}
    for entry in filled:
        if entry["kode"] not in seen:
            detailed.append(entry)
            seen.add(entry["kode"])
        if len(detailed) >= count:
            break
    return detailed


def system_prompt() -> str:
    return textwrap.dedent(
        """
        Anda adalah spesialis terminologi keperawatan Indonesia.
        Tugas Anda melengkapi entri Standar Diagnosis Keperawatan Indonesia (SDKI)
        berdasarkan standar SDKI PPNI 2017/2022.

        Wajib:
        - Gunakan Bahasa Indonesia klinis yang baku dan ringkas.
        - Pertahankan kode, nama, kategori, dan subkategori persis seperti input.
        - Isi definisi, penyebab, gejala_mayor, dan gejala_minor sesuai standar SDKI.
        - KHUSUS diagnosa yang namanya diawali "Risiko": diagnosa ini TIDAK memiliki gejala_mayor/minor.
          Untuk diagnosa Risiko, kosongkan gejala_mayor dan gejala_minor, dan tambahkan field "faktor_risiko": ["..."]
          berisi minimal 3 faktor risiko klinis yang relevan.
        - Jangan menambahkan field di luar skema (kecuali faktor_risiko untuk diagnosa Risiko).
        - Jangan mengubah urutan entri.
        - Kembalikan hanya JSON valid, tanpa Markdown, tanpa komentar.
        """
    ).strip()


def user_prompt(examples: list[dict[str, Any]], batch: list[dict[str, Any]]) -> str:
    return textwrap.dedent(
        f"""
        Gunakan 7 contoh entri terisi berikut sebagai few-shot format dan gaya isi:
        {json.dumps(examples, ensure_ascii=False, indent=2)}

        Lengkapi entri SDKI kosong atau parsial berikut. Output harus berupa JSON
        array dengan jumlah item yang sama dan skema persis seperti ini:
        {{
          "kode": "D.XXXX",
          "nama": "...",
          "kategori": "...",
          "subkategori": "...",
          "definisi": "...",
          "penyebab": ["..."],
          "gejala_mayor": {{ "subjektif": ["..."], "objektif": ["..."] }},
          "gejala_minor": {{ "subjektif": ["..."], "objektif": ["..."] }}
        }}

        Entri yang harus dilengkapi:
        {json.dumps(batch, ensure_ascii=False, indent=2)}
        """
    ).strip()


def call_llm(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, model: str = MODEL, api_key: str = "", timeout: int = 120) -> str:
    _key = api_key or API_KEY or ""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Anda adalah spesialis terminologi keperawatan Indonesia. "
                    "Output HANYA valid JSON array. "
                    "Tidak ada teks sebelum atau sesudah JSON. "
                    "Tidak ada markdown fence. Tidak ada komentar. "
                    "Gunakan standar SDKI PPNI 2017/2022."
                )
            },
            {"role": "user", "content": prompt}
        ]
    }
    req = request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_key}"
        },
        method="POST"
    )
    with request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    msg = data["choices"][0]["message"]
    raw = msg.get("content") or msg.get("reasoning_content") or ""
    if not raw.strip():
        raise ValueError(f"Empty response from API: {data}")
    raw = raw.strip()
    # Strip markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"```\s*$", "", raw).strip()
    # Ekstrak JSON array — handles trailing text after closing bracket
    bracket_start = raw.find("[")
    bracket_end = raw.rfind("]")
    if bracket_start >= 0 and bracket_end > bracket_start:
        raw = raw[bracket_start:bracket_end + 1]
    return raw


def call_with_retries(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    timeout: int,
    attempts: int,
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return call_llm(user, max_tokens=max_tokens, model=model, api_key=api_key, timeout=timeout)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {exc.code}: {detail}")
            if exc.code not in RETRY_STATUSES or attempt == attempts:
                break
        except Exception as exc:  # network/parser errors are retryable for this one-shot job
            last_error = exc
            if attempt == attempts:
                break

        sleep_for = min(20, 2**attempt)
        print(f"[WARN] Batch call failed on attempt {attempt}; retrying in {sleep_for}s", file=sys.stderr)
        time.sleep(sleep_for)

    raise RuntimeError(f"API request failed after {attempts} attempts: {last_error}")


def parse_json_array(text: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end < start:
            raise
        parsed = json.loads(text[start : end + 1])

    if not isinstance(parsed, list):
        raise ValueError("Model output must be a JSON array")
    if not all(isinstance(item, dict) for item in parsed):
        raise ValueError("Every model output item must be a JSON object")
    return parsed


def normalize_generated(generated: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    definisi = str(generated.get("definisi", "")).strip()
    penyebab = _as_list(generated.get("penyebab"))
    gejala_mayor = _gejala_dict(generated.get("gejala_mayor"))
    gejala_minor = _gejala_dict(generated.get("gejala_minor"))

    if not definisi:
        raise ValueError(f"{original.get('kode')} missing definisi")
    if not penyebab:
        raise ValueError(f"{original.get('kode')} missing penyebab")
    # Diagnosa "Risiko" tidak memiliki gejala mayor/minor (SDKI standard)
    # Mereka hanya punya faktor_risiko — skip validasi gejala untuk kategori ini
    is_risiko = str(original.get("nama", "")).strip().lower().startswith("risiko")
    if not is_risiko and not gejala_mayor["objektif"] and not gejala_mayor["subjektif"]:
        raise ValueError(f"{original.get('kode')} missing gejala_mayor (both subjektif and objektif empty)")

    is_risiko = str(original.get("nama", "")).strip().lower().startswith("risiko")
    result = {
        "kode": str(original.get("kode", "")).strip(),
        "nama": str(original.get("nama", "")).strip(),
        "kategori": str(original.get("kategori", "")).strip(),
        "subkategori": str(original.get("subkategori", "")).strip(),
        "definisi": definisi,
        "penyebab": penyebab,
        "gejala_mayor": gejala_mayor,
        "gejala_minor": gejala_minor,
    }
    if is_risiko:
        # Ambil faktor_risiko dari generated output jika ada
        faktor = _as_list(generated.get("faktor_risiko"))
        if not faktor:
            # Fallback: gunakan penyebab sebagai faktor_risiko
            faktor = penyebab
        result["faktor_risiko"] = faktor
    return result


def align_and_validate(batch: list[dict[str, Any]], generated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(generated) != len(batch):
        raise ValueError(f"Expected {len(batch)} generated entries, got {len(generated)}")

    normalized: list[dict[str, Any]] = []
    used: set[int] = set()
    for original in batch:
        match_index: int | None = None
        original_code = str(original.get("kode", "")).strip()
        original_name = str(original.get("nama", "")).strip().lower()

        for idx, candidate in enumerate(generated):
            if idx in used:
                continue
            if str(candidate.get("kode", "")).strip() == original_code:
                match_index = idx
                break

        if match_index is None:
            for idx, candidate in enumerate(generated):
                if idx in used:
                    continue
                if str(candidate.get("nama", "")).strip().lower() == original_name:
                    match_index = idx
                    break

        if match_index is None:
            for idx in range(len(generated)):
                if idx not in used:
                    match_index = idx
                    break

        if match_index is None:
            raise ValueError(f"No generated match for {original_code}")

        used.add(match_index)
        normalized.append(normalize_generated(generated[match_index], original))

    return normalized


def fill_batch(
    *,
    examples: list[dict[str, Any]],
    batch: list[dict[str, Any]],
    api_key: str,
    model: str,
    max_tokens: int,
    timeout: int,
    attempts: int,
) -> list[dict[str, Any]]:
    normalized_batch = [normalize_for_prompt(entry) for entry in batch]
    response_text = call_with_retries(
        api_key=api_key,
        model=model,
        system=system_prompt(),
        user=user_prompt(examples, normalized_batch),
        max_tokens=max_tokens,
        timeout=timeout,
        attempts=attempts,
    )
    generated = parse_json_array(response_text)
    return align_and_validate(normalized_batch, generated)


def write_report(report_path: Path, report: dict[str, Any]) -> None:
    report["updated_at"] = datetime.now().isoformat(timespec="seconds")
    atomic_write_json(report_path, report)


def make_batches(items: list[tuple[int, dict[str, Any]]], batch_size: int) -> list[list[tuple[int, dict[str, Any]]]]:
    return [items[idx : idx + batch_size] for idx in range(0, len(items), batch_size)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Populate empty SDKI.json entries via Sumopod/OpenAI-compatible API.")
    parser.add_argument("--input", type=Path, default=DEFAULT_SDKI_PATH, help="Path to SDKI.json")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="Summary report path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Entries per API call")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="Max output tokens per API call")
    parser.add_argument("--timeout", type=int, default=90, help="HTTP timeout seconds per API call")
    parser.add_argument("--attempts", type=int, default=3, help="Retry attempts per batch")
    parser.add_argument("--limit", type=int, default=0, help="Optional max entries to process")
    parser.add_argument("--dry-run", action="store_true", help="Call API and validate output without writing SDKI.json")
    parser.add_argument("--no-backup", action="store_true", help="Do not create timestamped backup before first write")
    parser.add_argument("--repair-partial", action="store_true", help="Also refill rows with definisi but incomplete major objective signs")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop immediately when a batch fails")
    args = parser.parse_args()

    api_key = (os.environ.get("API_KEY") or os.environ.get("SUMOPOD_API_KEY") or "").strip()
    if not api_key:
        print("ERROR: API_KEY or SUMOPOD_API_KEY is required", file=sys.stderr)
        return 2
    if args.batch_size < 1:
        print("ERROR: --batch-size must be >= 1", file=sys.stderr)
        return 2

    sdk_path = args.input.resolve()
    report_path = args.report.resolve()
    entries = load_json(sdk_path)
    examples = pick_few_shot_examples(entries, 7)
    if len(examples) < 7:
        print(f"[WARN] Only {len(examples)} filled examples found; continuing with available examples", file=sys.stderr)

    if args.repair_partial:
        should_process = lambda entry: not entry_is_complete_for_gate(entry)
    else:
        should_process = lambda entry: not entry_has_definisi(entry)

    skipped = [normalize_for_prompt(entry) for entry in entries if not should_process(entry)]
    pending = [(idx, entry) for idx, entry in enumerate(entries) if should_process(entry)]
    if args.limit:
        pending = pending[: args.limit]

    report: dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(sdk_path),
        "model": args.model,
        "batch_size": args.batch_size,
        "dry_run": args.dry_run,
        "repair_partial": args.repair_partial,
        "total_entries": len(entries),
        "skipped_count": len(skipped),
        "skipped_codes": [entry["kode"] for entry in skipped],
        "pending_count": len(pending),
        "filled_count": 0,
        "filled_codes": [],
        "failed": [],
        "batches": [],
    }
    write_report(report_path, report)

    if not pending:
        print("No SDKI entries to populate.")
        return 0

    if not args.no_backup and not args.dry_run:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = sdk_path.with_name(f"{sdk_path.name}.bak-{stamp}")
        shutil.copy2(sdk_path, backup_path)
        report["backup"] = str(backup_path)
        write_report(report_path, report)

    batches = make_batches(pending, args.batch_size)
    print(f"Preparing to fill {len(pending)} entries in {len(batches)} batch(es).")

    for batch_number, indexed_batch in enumerate(batches, start=1):
        positions = [idx for idx, _ in indexed_batch]
        batch_entries = [entry for _, entry in indexed_batch]
        codes = [str(entry.get("kode", "")).strip() for entry in batch_entries]
        print(f"[BATCH {batch_number}/{len(batches)}] Filling: {', '.join(codes)}")

        try:
            filled_entries = fill_batch(
                examples=examples,
                batch=batch_entries,
                api_key=api_key,
                model=args.model,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                attempts=args.attempts,
            )
            if not args.dry_run:
                for idx, filled in zip(positions, filled_entries):
                    entries[idx] = filled
                atomic_write_json(sdk_path, entries)

            report["filled_count"] += len(filled_entries)
            report["filled_codes"].extend(entry["kode"] for entry in filled_entries)
            report["batches"].append({"batch": batch_number, "codes": codes, "status": "filled"})
            write_report(report_path, report)
        except Exception as exc:
            message = str(exc)
            print(f"[ERROR] Batch {batch_number} failed: {message}", file=sys.stderr)
            report["failed"].append({"batch": batch_number, "codes": codes, "error": message})
            report["batches"].append({"batch": batch_number, "codes": codes, "status": "failed"})
            write_report(report_path, report)
            if args.stop_on_error:
                return 1

    print(f"Done. Filled {report['filled_count']} entries; skipped {report['skipped_count']}; failed {len(report['failed'])} batch(es).")
    print(f"Report: {report_path}")
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())