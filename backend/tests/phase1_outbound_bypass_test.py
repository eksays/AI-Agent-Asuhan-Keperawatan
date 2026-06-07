from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


BACKEND = Path(__file__).resolve().parents[1]

PATTERNS = {
    ".invoke(": re.compile(r"\.invoke\("),
    ".ainvoke(": re.compile(r"\.ainvoke\("),
    ".stream(": re.compile(r"\.stream\("),
    ".astream(": re.compile(r"\.astream\("),
    "requests.post(": re.compile(r"requests\.post\("),
    "requests.get(": re.compile(r"requests\.get\("),
    "httpx.": re.compile(r"httpx\."),
    "urllib.": re.compile(r"urllib\."),
    "request.urlopen(": re.compile(r"request\.urlopen\("),
    "ChatOpenAI(": re.compile(r"ChatOpenAI\("),
    "ChatAnthropic(": re.compile(r"ChatAnthropic\("),
    "ChatGoogleGenerativeAI(": re.compile(r"ChatGoogleGenerativeAI\("),
    "Anthropic(": re.compile(r"Anthropic\("),
}

# Approved Phase 1 outbound surfaces. Any new match outside this set must be
# reviewed and routed through outbound_policy or a documented de-identified
# utility boundary before the test is updated.
ALLOWLIST = {
    ("agents.py", 196, ".invoke("): "Injected LLM is expected to be SafeLLM from active API routes.",
    ("agents.py", 376, ".invoke("): "Injected LLM is expected to be SafeLLM from active API routes.",
    ("api.py", 528, "ChatAnthropic("): "Raw provider construction is private and wrapped by get_llm().",
    ("api.py", 528, "Anthropic("): "Substring match inside ChatAnthropic; same reviewed raw provider construction.",
    ("api.py", 531, "ChatGoogleGenerativeAI("): "Raw provider construction is private and wrapped by get_llm().",
    ("api.py", 538, "ChatOpenAI("): "Raw provider construction is private and wrapped by get_llm().",
    ("chaos_monkey.py", 13, "urllib."): "Local-only chaos tool for localhost smoke checks.",
    ("chaos_monkey.py", 20, "urllib."): "Local-only chaos tool for localhost smoke checks.",
    ("chaos_monkey.py", 21, "urllib."): "Local-only chaos tool for localhost smoke checks.",
    ("chaos_monkey.py", 24, "urllib."): "Local-only chaos tool for localhost smoke checks.",
    ("chaos_monkey.py", 24, "request.urlopen("): "Local-only chaos tool for localhost smoke checks.",
    ("chaos_monkey.py", 26, "urllib."): "Local-only chaos tool for localhost smoke checks.",
    ("chaos_monkey.py", 35, "urllib."): "Local-only chaos tool for localhost smoke checks.",
    ("chaos_monkey.py", 35, "request.urlopen("): "Local-only chaos tool for localhost smoke checks.",
    ("chaos_monkey.py", 37, "urllib."): "Local-only chaos tool for localhost smoke checks.",
    ("ebp.py", 17, "urllib."): "EBP connector module; retrieve_context de-identifies before external search.",
    ("ebp.py", 82, "urllib."): "EBP connector module; host allowlist and no redirects.",
    ("ebp.py", 87, "urllib."): "EBP connector module; host allowlist and no redirects.",
    ("ebp.py", 91, "urllib."): "EBP connector module; host allowlist and no redirects.",
    ("ebp.py", 94, "urllib."): "EBP connector module; host allowlist and no redirects.",
    ("ebp.py", 108, "urllib."): "EBP connector module; query derived from de-identified concepts.",
    ("ebp.py", 143, "urllib."): "EBP connector module; query derived from de-identified concepts.",
    ("ebp.py", 180, "urllib."): "EBP connector module; query derived from de-identified concepts.",
    ("ebp.py", 213, "urllib."): "EBP connector module; query derived from de-identified concepts.",
    ("ebp.py", 361, ".invoke("): "EBP query-generation LLM receives de-identified concept text.",
    ("ekstraksi.py", 59, "ChatGoogleGenerativeAI("): "Reviewed registry utility; invocation wrapped before use.",
    ("ekstraksi.py", 63, "ChatOpenAI("): "Reviewed registry utility; invocation wrapped before use.",
    ("ekstraksi.py", 69, "ChatAnthropic("): "Reviewed registry utility; invocation wrapped before use.",
    ("ekstraksi.py", 69, "Anthropic("): "Substring match inside ChatAnthropic; same reviewed registry utility construction.",
    ("ekstraksi.py", 72, ".invoke("): "Reviewed registry utility; uses wrap_llm(llm).invoke(...).",
    ("outbound_policy.py", 211, ".invoke("): "Central SafeLLM boundary invokes raw client after sanitization.",
    ("scripts/populate_sdki.py", 232, "request.urlopen("): "Reviewed registry utility; request body is sanitized before urlopen.",
    ("upload_security.py", 12, "urllib."): "Parser child runtime guard imports urllib only to block urlopen before parsing.",
    ("upload_security.py", 404, "urllib."): "Parser child runtime guard replaces urlopen with a blocker; no outbound request is made.",
    ("upload_security.py", 424, "httpx."): "Parser child runtime guard replaces httpx client request with a blocker; no outbound request is made.",
    ("upload_security.py", 425, "httpx."): "Parser child runtime guard replaces httpx async client request with a blocker; no outbound request is made.",
    ("upload_security.py", 426, "httpx."): "Parser child runtime guard replaces httpx.get with a blocker; no outbound request is made.",
    ("upload_security.py", 427, "httpx."): "Parser child runtime guard replaces httpx.post with a blocker; no outbound request is made.",
}


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for path in BACKEND.rglob("*.py"):
        rel_parts = set(path.relative_to(BACKEND).parts)
        if rel_parts & {"venv", "__pycache__", "tests"}:
            continue
        files.append(path)
    return files


class Phase1OutboundBypassTests(unittest.TestCase):
    def test_owned_backend_outbound_primitives_match_allowlist(self):
        matches: list[tuple[str, int, str, str]] = []
        for path in iter_source_files():
            rel = path.relative_to(BACKEND).as_posix()
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                for label, pattern in PATTERNS.items():
                    if pattern.search(line):
                        matches.append((rel, lineno, label, line.strip()))

        unexpected = [m for m in matches if (m[0], m[1], m[2]) not in ALLOWLIST]
        missing = [key for key in ALLOWLIST if key not in {(m[0], m[1], m[2]) for m in matches}]

        self.assertEqual([], unexpected, "Unexpected outbound primitive(s): " + repr(unexpected))
        self.assertEqual([], missing, "Allowlisted outbound primitive(s) no longer present: " + repr(missing))


if __name__ == "__main__":
    unittest.main()
