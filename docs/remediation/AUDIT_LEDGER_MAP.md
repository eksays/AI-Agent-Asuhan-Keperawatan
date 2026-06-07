# Audit Ledger Map

Phase 7 maps the current audit surface before implementation. This document is a safety map, not proof of compliance or immutable storage.

Adopted read-only guidance themes from the requested security resources: build structured context before changes, fail closed on insecure defaults, minimize sensitive data in logs, use keyed cryptographic integrity for tamper evidence, and keep storage claims honest. No third-party scripts were executed.

## Storage And Integrity Boundary

The previous backend ledger was a local newline-delimited file at `backend/audit_ledger.jsonl` with a plain SHA-256 chain embedded in `backend/api.py`. It sanitized legacy action/status strings but trusted unkeyed hashes and swallowed append failures. Phase 7 replaces this with a structured HMAC-chained local sandbox ledger and verification utility. This remains tamper-evident only, not WORM storage and not filesystem immutability.

## Audit Surface

| Boundary ID | Event producer | Route or subsystem | Previous ledger behavior | Current data fields | PHI exposure risk | Integrity model | Storage backend | Verification behavior | Retention behavior | Required mitigation | Test case | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AUD-001 | `audit_log` wrapper | Legacy calls in `backend/api.py` | Plain SHA-256 over timestamp/session/action/status | Session hash, action, status | Free-text action/status could carry unsafe text if caller regresses | Unkeyed hash chain | Local JSONL append | Startup recomputed hash; malformed lines failed late | No rotation; old file retained locally | Replace with structured allowlisted HMAC events | `valid append and verification`; `attacker recomputes plain SHA-256 chain` | Applied |
| AUD-002 | Authentication helper | API key protected routes | Auth failures returned safe HTTP payload but were not consistently ledgered | Status only | Raw API key/token must never be logged | None | N/A | N/A | N/A | Emit safe `authentication_failed` / `authentication_succeeded` events with credential fingerprint only | `raw API key absent`; API route tests | Applied |
| AUD-003 | Session memory | `/session`, `/reset`, `/delete_my_data`, session checks | Session create/reset/delete partly unledgered; delete used legacy action | Session id possible at call site | Raw session token and session id must not be stored | Legacy SHA-256 for explicit delete only | Local JSONL | Startup only | No rotation | Emit `session_created`, `session_reset`, `session_deleted`, `session_expired`, `session_token_invalid` with actor fingerprint | `session token absent`; API route tests | Applied |
| AUD-004 | Rate limiter | `_apply_rate_limit` | 429 response only | Route class, retry indicator | Client IP must be fingerprinted, not raw | None | N/A | N/A | N/A | Emit `rate_limited` with route class and safe retry bucket | `metadata bounds`; static scanner | Applied |
| AUD-005 | Director MFA | `/director/login` | Success logged as `DirectorLogin`; failures/replay/lockout not consistently ledgered | Legacy action/status | OTP/TOTP seed/director token must not be logged | Legacy SHA-256 on success only | Local JSONL | Startup only | No rotation | Emit MFA success/failure/replay/lock events with no OTP/seed/token | `OTP absent`; `TOTP seed absent` | Applied |
| AUD-006 | Director enrollment | `/director/enroll` | Not consistently ledgered | Authorization status only | Bootstrap secret and otpauth URI must not be logged | None | N/A | N/A | N/A | Emit enrollment attempt/success with safe status only | `bootstrap secret absent` | Applied |
| AUD-007 | Upload parser | `/analisis`, `/analisis_multi`, upload helper | Upload failures/success logged as legacy action/status | Parser status | Uploaded text/path/exception must not be logged | Legacy SHA-256 where called | Local JSONL | Startup only | No rotation | Emit upload rejection/timeout/crash events with parser status code only | `filesystem path absent`; parser API tests | Applied |
| AUD-008 | Outbound policy | `OutboundPolicyError`, SafeLLM boundary | Exceptions sanitized to console; not always ledgered | Generic error | Prompt/model output/patient narrative must not be logged | None | N/A | N/A | N/A | Emit `outbound_policy_blocked` with route class only | `raw prompt absent`; bypass scanner | Applied |
| AUD-009 | Clinical validator | Clinical abstention, registry unavailable/incomplete | API returned machine-readable abstention; not consistently ledgered | Clinical status, missing registry names | Patient evidence and model output must not be logged | None | N/A | N/A | N/A | Emit clinical abstention / registry status event with safe registry names only | Phase 2 regression plus audit canaries | Applied |
| AUD-010 | Capability gates | `_unavailable` | Safe JSON response only | Capability name | No PHI expected; avoid raw request text | None | N/A | N/A | N/A | Emit `capability_denied` with capability allowlist value | capability denied audit test | Applied |
| AUD-011 | Ledger verifier | Startup/CLI verification | Startup printed OK/tampered count; no structured failure event | Count only | Failure details must not echo raw record values | Plain hash verification | Local JSONL | Recompute hash chain | No export summary | Add CLI safe summary and `ledger_verification_failed` event on startup failure | CLI valid/tampered behavior | Applied |
| AUD-012 | Rotation/export | Local ledger files | No segment metadata or rotation | N/A | Export must be summary-only | None | Local JSONL | N/A | No defined segment policy | Add local segment metadata and cross-segment linkage; no deletion | rotation and cross-segment tests | Applied |

## Honest Claims Boundary

- Local append-only API is not filesystem immutability.
- HMAC chain is not an asymmetric digital signature and does not provide non-repudiation.
- Host administrators with access to both ledger and key can rewrite history.
- Cross-process correctness is not claimed for Phase 7 unless a deployment uses a durable centralized ledger service.
- A locally valid prefix after final-record deletion may still verify; stronger tail-truncation resistance requires an external signed footer, externally persisted checkpoint, immutable archive, or attestation.
- The runtime ledger path is server-configured only; request data cannot choose the ledger path.
- Path normalization and direct symlink or non-file rejection do not make arbitrary paths safe or immutable storage.
- Allowed-root enforcement for persistent ledger storage remains a pre-pilot follow-up.
- External immutable archive or WORM-capable storage remains required before pilot, compliance, or production claims.

## Phase 7 Implementation Status

| Area | Status | Evidence | Remaining Limit |
|---|---|---|---|
| Structured event schema | Applied | `backend/audit_ledger.py` defines required record fields, event categories, actor fingerprinting, route class, security tags, and metadata. | Schema validity is operational evidence only, not compliance certification. |
| Canonical serialization | Applied | Records are serialized with sorted keys, compact separators, UTF-8, `allow_nan=False`, and `record_mac` excluded from authenticated bytes. | No floating-point metadata is accepted as authoritative; floats are filtered. |
| HMAC chain | Applied | Each record MAC uses HMAC-SHA256 over the canonical record including previous MAC link. | Key compromise permits history rewrite; this is not non-repudiation. |
| Local append backend | Applied | Local backend appends newline-delimited JSON, flushes, fsyncs, rejects direct symlink/non-file ledger paths where detectable, and verifies before persistent append. Closure tests prove mutated, reordered, deleted-middle, partial, malformed, or wrong-key ledgers block append without overwrite. | Local filesystem can still be altered by a host administrator. |
| Verification CLI | Applied | `backend/scripts/verify_audit_ledger.py` returns safe JSON summaries and non-zero status for tamper or missing key. | CLI verifies local segments only; no external immutable archive exists. |
| Rotation | Applied for local segments | `rotate_to()` preserves old segment content, assigns a new segment ID, and links the new segment to the previous terminal MAC; missing or tampered prior linkage fails in tests. | Key rotation is not implemented; no signed external retention manifest or deletion-prevention control exists. |
| API integration | Applied narrowly | Auth, session, rate-limit, MFA, director enrollment, upload legacy events, outbound policy blocks, clinical abstention, registry unavailable/incomplete, and capability denial emit safe events. Session reset/delete, director enrollment, and MFA privileged outcomes now fail closed when required audit append fails. | Historical plain-hash audit code was removed; non-critical sandbox telemetry may still degrade conservatively if audit append fails. |
