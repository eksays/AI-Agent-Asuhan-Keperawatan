# Upload Parsing Map

Phase 5 maps uploaded files as attacker-controlled bytes. This map was written before the parser implementation work so the mitigation is tied to the actual route boundaries found in the repository.

## Guidance Sources Inspected

Read-only inspection was performed for the requested repositories. No third-party scripts, hooks, installers, or plugin collections were executed.

| Source | Relevant Practice Adopted |
|---|---|
| `https://github.com/openai/skills` | Build a narrow, testable boundary around untrusted inputs; preserve explicit safety documentation. |
| `https://github.com/trailofbits/skills` | Bottom-up context building, insecure-default review, and hostile-input mapping before edits. |
| `https://github.com/OWASP/secure-agent-playbook` | Fail closed for untrusted files, apply deterministic validation before parsing, avoid unsafe defaults, and preserve auditable evidence. |

## Boundary Inventory

| Boundary ID | Route | Source File | Function | Accepted Input | Current Type Decision | Current Parser | Isolation Model | Timeout Behavior | Cleanup Behavior | Resource Limits | Network Possibility | Current Risk | Required Mitigation | Test Case | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| UPL-001 | `/analisis_multi` | `backend/api.py` | `analisis_multi` -> `extract_text` -> `_parse_doc` | `file_dokumen` uploaded through multipart form | Filename suffix dispatch: `.pdf`, `.docx`, `.txt`, `.md`, `.csv`, `.json` | `pdfplumber`/`PyPDF2`, `python-docx`, UTF-8 decode with ignore | `ThreadPoolExecutor` in process | `future.result(timeout=20)`; timed-out thread cannot be killed | No parser temp workspace; parser libraries operate in backend process memory | 10 MiB upload read limit; 30 PDF page slice only | Parser libraries run in main backend process and inherit full runtime; no explicit network deny | Extension spoofing, hostile PDF/DOCX parser hang, zip bomb, silent empty parse, and unsafe fallback to no document text | Bounded intake, content sniffing, DOCX ZIP validation, killable parser process, structured parser outcomes, cleanup guarantees, network-deny guard | `phase5_upload_security_test.py` hostile-file matrix | Mitigation pending at map creation |
| UPL-002 | `/analisis` | `backend/api.py` | `analisis` -> `extract_text` -> `_parse_doc` | `file_dokumen` uploaded through multipart form | Same filename suffix dispatch as UPL-001 | Same parser set as UPL-001 | Same thread boundary | Same non-killable timeout | Same as UPL-001 | Same as UPL-001 | Same as UPL-001 | Same risk surface as UPL-001, with fallback single-agent route | Same mitigation as UPL-001 | `phase5_upload_security_test.py` API route rejection tests | Mitigation pending at map creation |
| UPL-003 | `/analisis_multi` and `/analisis` | `backend/api.py` | route photo handling | `file_foto` uploaded through multipart form | Capability flag check, not parser dispatch | No image parser when disabled | Not applicable | Not applicable | Not applicable | 10 MiB upload size check | No provider call when capability disabled | UI may still submit photo, but backend must remain authoritative and unsupported by default | Preserve server-side `clinical_photo_analysis` unavailable response; do not add OCR or image analysis | Photo upload unsupported regression | Already fail-closed, preserve |
| UPL-004 | Frontend send path | `frontend/lib/api.ts` | `analisis` | `file_dokumen` and `file_foto` forwarded as `FormData` | Browser `File` object metadata only | No parsing in frontend | Not applicable | Not applicable | Browser-managed | Browser accept list is advisory only | None in frontend parser path | Frontend accept list includes `.doc`, `.md`, `.csv`; browser MIME/extension cannot be trusted | Keep backend authoritative; frontend redesign is out of Phase 5 scope | MIME mismatch does not override backend sniffing | Backend mitigation required |
| UPL-005 | Dashboard document picker | `frontend/components/dashboard.tsx` | hidden file input | `.pdf,.doc,.docx,.txt,.md,.csv` accept hint | Browser extension hint | No parsing in frontend | Not applicable | Not applicable | Not applicable | Not enforceable | None in frontend parser path | Accept hint can mislead, but server must reject unsupported files | Do not rely on accept list; backend rejects unsupported and mismatched content | Unsupported extension and fake content tests | Backend mitigation required |
| UPL-006 | Claude-style input picker/camera | `frontend/components/ui/claude-style-ai-input.tsx` | hidden file input and camera capture | `.pdf,.doc,.docx,.txt,.md,.csv` plus JPEG capture | Browser extension/MIME hint | No parsing in frontend | Not applicable | Not applicable | Not applicable | Not enforceable | None in frontend parser path | Photo upload remains unsupported server-side; frontend should not be trusted | Preserve backend photo rejection; no OCR/photo analysis | Photo upload unsupported test | Already fail-closed server-side, preserve |
| UPL-007 | Registry extraction utility | `backend/ekstraksi.py` | registry/OCR extraction script | Local registry PDFs, not clinical upload route | Static local source config | `pdfplumber`, external LLM wrapping | Script process only | Not part of API request timeout | Not part of API upload cleanup | Script-specific | External LLM use exists in utility path | Out of Phase 5 scope; modifying OCR quality or registry import would cross Phase 3/8 boundary | Read-only mapping only; keep non-authoritative | Existing Phase 3 governance tests | Out of scope |

## Phase 5 Target State

The upload path target is:

```text
uploaded file
-> untrusted attacker-controlled bytes
-> bounded intake
-> deterministic content sniffing
-> strict type allowlist
-> killable isolated parser process
-> bounded sanitized text only
-> safe cleanup
```

The filename, extension, browser MIME type, Content-Type header, archive member name, and parser success are never authoritative by themselves.

## Implemented Phase 5 Controls

| Control | Implementation | Evidence |
|---|---|---|
| Content-derived sniffing | `backend/upload_security.py` dispatches only PDF signature, DOCX OOXML container members, or clean UTF-8 text. Filename and browser MIME are compatibility checks only. | `phase5_upload_security_test.py` covers valid PDF/DOCX/text, extension mismatch, MIME mismatch, fake PDF, fake DOCX, generic ZIP, image-as-PDF, and binary garbage. |
| DOCX container validation | DOCX validation rejects traversal, backslash traversal at member-normalization boundary, drive-letter paths, symlink-like entries, missing OOXML members, excessive entries, oversized expanded content, high compression ratio, nested archives, macro/active content, executable member types, and external relationships. | `test_docx_container_validation_rejects_hostile_members` and `test_docx_size_and_compression_limits_are_enforced`. |
| Killable parser process | Parsing runs in a spawned child process with a temporary workspace. Parent enforces wall-clock timeout, terminates the child, escalates to kill where available, and removes the workspace on success, rejection, crash, and timeout. | `test_hung_parser_process_is_terminated_and_workspace_removed` and workspace cleanup tests. |
| Parser child runtime guard | Child parser installs guards that block socket connections, `urllib.request.urlopen`, and subprocess command execution before parser libraries run. | `test_parser_child_network_and_command_execution_are_blocked`. |
| Structured parser outcomes | API returns `upload_status`, `accepted_upload=false`, and browser-safe messages for parser failures. Raw uploaded content, filesystem paths, and raw parser exceptions are not returned. | API integration tests reject hostile uploads before provider construction. |
| Photo analysis remains disabled | `file_foto` still returns the server-authoritative `clinical_photo_analysis` unavailable response when the feature is disabled. | Existing Phase 0B tests plus Phase 5 photo regression. |

## Phase 5 Closure Review Evidence

The closure review expanded verification without changing frontend design, registry governance, authentication/session controls, OCR quality pipelines, prompt behavior, or external capability defaults.

### Parser Process Lifecycle

The implemented parser lifecycle is:

```text
parent creates unique temporary workspace with cdss_upload_parse_ prefix
-> parent copies bounded upload bytes to upload.bin inside that workspace
-> parent starts spawned child process with a fixed parser worker entrypoint
-> child installs runtime guards and parses the copied file
-> parent waits with parser_timeout_sec wall-clock timeout
-> parent terminates the child on timeout
-> parent joins the child
-> parent kills the child if it is still alive and kill is available
-> parent joins again
-> parent closes and joins the result queue thread
-> parent deletes the temporary workspace
```

Tests cover success cleanup, deterministic rejection cleanup, parser crash cleanup, single timeout cleanup, and 20 sequential timeout cleanups. The repeated-timeout test asserts all results are `parser_timeout`, child PIDs exit, no parser workspace remains, and `multiprocessing.active_children()` is empty in the parent process.

The child parses a parent-created copied file named `upload.bin`; it does not reopen a caller-controlled path. The workspace-probe test verifies the copied input exists inside a per-request `cdss_upload_parse_` workspace and is not a symlink. No arbitrary DOCX archive extraction is performed.

### Expanded Hostile-File Coverage

DOCX closure coverage includes traversal attempts with `../`, backslashes, absolute POSIX paths, Windows drive-letter paths, UNC-style paths, Unicode-normalized traversal variants, duplicate and case-insensitive duplicate members, encrypted ZIP members, excessive entry count, oversized total expansion, oversized single member, high compression ratio, nested archives, macro-bearing content, external relationships including mixed-case `TargetMode`, missing `[Content_Types].xml`, missing `word/document.xml`, and generic ZIP renamed as `.docx`.

PDF closure coverage includes valid minimal PDF acceptance, fake PDF rejection, malformed PDF crash-safe handling, encrypted PDF rejection, page-limit enforcement, and explicit rejection of policy-disallowed active-content markers such as embedded files and JavaScript/action markers. The marker check is deterministic containment before parser invocation; it is not a complete PDF security proof.

Plain-text closure coverage includes valid bounded UTF-8 acceptance, empty text rejection, binary garbage rejection, NUL-byte rejection, excessive control-character rejection, executable-signature rejection, oversized decoded text rejection, and invalid UTF-8 rejection. Oversized content is rejected; it is not silently truncated.

### Runtime Deny Boundary

The parser child runtime guard blocks `socket.socket.connect`, `socket.create_connection`, `socket.getaddrinfo`, `urllib.request.urlopen`, `requests` request helpers, `httpx` request helpers, `subprocess.run`, `subprocess.Popen`, `os.system`, and `shell=True` command execution attempts inside the child boundary. This guard does not create a kernel network namespace and does not replace host/container policy controls.

The owned-source bypass scanner now flags `ThreadPoolExecutor`, `future.result(timeout=`, filename suffix dispatch, `ZipFile.extractall`, shell execution, subprocess execution, `os.system`, `eval`, `exec`, and direct `compile` usage. The only allowed process creation for upload parsing is the parent-side killable parser-process boundary using a fixed worker entrypoint and no shell.

## Configured Limits

| Limit | Default |
|---|---:|
| Maximum upload bytes | 10 MiB |
| Maximum filename length | 180 characters |
| Maximum extracted characters | 50,000 characters |
| Maximum PDF pages | 30 pages |
| Maximum DOCX entries | 100 entries |
| Maximum DOCX total uncompressed bytes | 5 MiB |
| Maximum DOCX single-entry uncompressed bytes | 2 MiB |
| Maximum DOCX compression ratio | 100:1 |
| Parser wall-clock timeout | 20 seconds |
| Maximum parser result payload | 100 KiB |

The DOCX compression ratio default is intentionally above a normal `python-docx` generated document style part, while tests use stricter per-test configurations to prove zip-bomb rejection. Oversized inputs are rejected rather than silently truncated.

## Residual Isolation Limits

The Phase 5 parser boundary is a killable process boundary with deterministic intake limits and child runtime guards. It is not OS-level sandboxing, container isolation, or process-tree isolation. Portable hard CPU and memory quotas are not implemented, and child-created descendant processes would require stronger host controls even though the tested child guard blocks subprocess creation. Before any pilot or production claim, Linux container limits, Windows job-object limits, or equivalent host-level resource controls remain required. Gate A remains unmet until Phase 5 closure evidence is reviewed and all earlier gate evidence remains enforced.
