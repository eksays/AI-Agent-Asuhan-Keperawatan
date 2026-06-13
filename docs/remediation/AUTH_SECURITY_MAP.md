# Auth Security Map

Phase 6 treats authentication, session ownership, MFA, rate limiting, CORS, and secret handling as separate security boundaries. This map was created before broad production-code edits and updated after the Phase 6 implementation.

## Guidance Sources Inspected

Read-only inspection was performed for the requested repositories. No third-party scripts, hooks, installers, or plugin collections were executed.

| Source | Relevant Practice Adopted |
|---|---|
| `https://github.com/openai/skills` | Keep security boundaries narrow, documented, and testable; do not execute untrusted skill content. |
| `https://github.com/trailofbits/skills` | Build audit context bottom-up, identify insecure defaults, and add regression tripwires for sensitive primitives. |
| `https://github.com/OWASP/secure-agent-playbook` | Fail closed on auth/session boundaries, avoid secrets in logs/browser responses, and separate API, web, SCA, and secrets checks. |

## Current Route Matrix

| Boundary ID | Route | Class | Authentication Requirement | Authorization Requirement | Session Ownership Behavior | Secret Source | Rate-Limit Class | MFA Behavior | Logging Behavior | Current Risk | Required Mitigation | Test Case | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AUTH-001 | `GET /` | Public metadata | None | None | None | None | PUBLIC | None | Aggregate request metrics only | Low metadata exposure | Keep public and secret-free | Root smoke | Mapped |
| AUTH-002 | `GET /capabilities` | Public metadata | None | None | None | None | PUBLIC | None | Aggregate request metrics only | Capability payload could expose config if mishandled | Keep secret-free capability response | `test_secret_config_fails_closed_for_pilot_and_production` | Applied |
| AUTH-003 | `GET /status` | Authenticated read | `Authorization: Bearer` only | Shared application principal | None | `CDSS_API_KEYS` | AUTH | None | Safe failure counter; no raw key logging | Legacy body/query key fallback risk | Header-only auth, constant-time compare, principal fingerprint | `test_header_only_api_key_transport` | Applied |
| AUTH-004 | `POST /session` | Authenticated mutation | `Authorization: Bearer` only | Shared application principal | Issues server `session_id` and `session_token`; stores only token digest | `CDSS_API_KEYS`, `CDSS_SECRET_KEY` pepper | AUTH | None | Aggregate metrics only | Anonymous session creation | Authenticated session issue with per-session token | `test_session_owner_token_delete_and_rotation` | Applied |
| AUTH-005 | `POST /chat` | Authenticated mutation | `Authorization: Bearer` only | Shared application principal plus capability gates | Principal-owned session plus `X-Session-Token` | Header API key only | CHAT | None | Session history stores sanitized text | Body API key and session ID possession risk | Header-only auth, owner+token session check, rate limit | Phase 6 scanner and prior clinical tests | Applied |
| AUTH-006 | `POST /chat_stream` | Authenticated mutation | `Authorization: Bearer` only | Shared application principal plus capability gates | Principal-owned session plus `X-Session-Token` | Header API key only | CHAT | None | Sanitized stream/history path | Streaming must fail before body for auth errors | Header-only auth before stream, owner+token check | Phase 6 scanner and prior stream tests | Applied |
| AUTH-007 | `POST /analisis` | Authenticated mutation | `Authorization: Bearer` only | Shared application principal plus upload/capability gates | Principal-owned session plus `X-Session-Token` | Header API key only | UPLOAD | None | Upload audit metadata only | Upload abuse and body-key risk | Header-only auth, owner+token session check, upload rate limit | Phase 5/6 tests | Applied |
| AUTH-008 | `POST /analisis_multi` | Authenticated mutation | `Authorization: Bearer` only | Shared application principal plus upload/capability gates | Principal-owned session plus `X-Session-Token` | Header API key only | UPLOAD | None | Upload/analysis audit metadata | Same as `/analisis` | Header-only auth, owner+token session check, upload rate limit | Phase 5/6 tests | Applied |
| AUTH-009 | `POST /pathway` | Unsupported/default-disabled feature | `Authorization: Bearer` only | Shared principal plus Mermaid/external-LLM capability gates | Principal-owned session plus `X-Session-Token` | Header API key only | CHAT | None | Metrics only | Mermaid must remain default-off | Auth/session gates plus capability disabled by default | Capability fallback tests | Applied |
| AUTH-010 | `GET /daftar/{buku}` | Authenticated read | `Authorization: Bearer` only | Shared application principal | Principal-owned session plus `X-Session-Token` | Header API key only | AUTH | None | Metrics only | Registry enumeration by session ID possession | Header auth and owner+token session check | Phase 6 scanner/runtime coverage | Applied |
| AUTH-011 | `GET /entri/{buku}/{kode}` | Authenticated read | `Authorization: Bearer` only | Shared application principal | Principal-owned session plus `X-Session-Token` | Header API key only | AUTH | None | Metrics only | Same as `/daftar` | Header auth and owner+token session check | Phase 6 scanner/runtime coverage | Applied |
| AUTH-012 | `POST /reset` | Authenticated mutation | `Authorization: Bearer` only | Shared application principal | Owner plus current `X-Session-Token`; reset rotates token | Header API key and session token | SESSION_MUTATION | None | Safe structured failure | Fake/stolen session reset | Reject fake/no-auth/wrong-owner/wrong-token; rotate valid token | `test_session_owner_token_delete_and_rotation` | Applied |
| AUTH-013 | `POST /delete_my_data` | Authenticated mutation | `Authorization: Bearer` only | Shared application principal | Owner plus current `X-Session-Token` | Header API key and session token | SESSION_MUTATION | None | Delete audit metadata | Deletion by session ID possession | Require auth principal plus session token | `test_session_owner_token_delete_and_rotation` | Applied |
| AUTH-014 | `POST /feedback` | Authenticated mutation | `Authorization: Bearer` only | Shared application principal | Owner plus current `X-Session-Token` | Header API key and session token | SESSION_MUTATION | None | Feedback audit metadata | Feedback poisoning by session ID possession | Require auth principal plus session token | Session rotation and old-token rejection test | Applied |
| AUTH-015 | `POST /director/login` | Privileged MFA action | TOTP code | Director token issued only after valid TOTP attempt | Director token only after MFA | `.director_totp` encrypted local file | MFA | Replay detection, per-principal/per-IP failures, lockout, `Retry-After` | Safe generic failures | TOTP replay/brute-force risk | Track accepted step, counters, lockout | `test_totp_replay_lockout_and_unlock` | Applied |
| AUTH-016 | `GET /director/enroll` | Privileged MFA setup | `X-Director-Bootstrap` header | Bootstrap secret compare | None | `DIRECTOR_BOOTSTRAP`, `.director_totp` | DIRECTOR_PRIVILEGED | None | Metrics only | Query bootstrap token exposure | Header-only bootstrap token, constant-time compare | Secret scanner/manual review | Applied |
| AUTH-017 | `GET /director/metrics` | Privileged MFA action | Director bearer token | Valid short-lived director token | Director token in memory only | In-memory director token | DIRECTOR_PRIVILEGED | TOTP login required first | Metrics only | Browser storage and no rate limit | Token kept in React state only; privileged route rate-limited | Frontend storage scanner | Applied |

## Target Phase 6 Contracts

| Area | Contract | Phase 6 Status |
|---|---|---|
| API key transport | Backend accepts only `Authorization: Bearer <api-key>`. Form, JSON, query, and cookie keys are rejected or ignored safely. | Applied and tested. |
| Principal | Server derives `principal_id` and `credential_fingerprint` from a one-way keyed digest; raw keys are never owner IDs or log values. Shared application key is not hospital user identity. | Applied and documented. |
| Session ownership | Authenticated application principal plus server-issued `session_token` is required for protected session reuse and mutation. Server stores only a token digest. | Applied and tested. |
| Session lifecycle | In-memory sessions get absolute TTL, idle timeout, last access, max-session bound, cleanup, expiry rejection, and token rotation after reset. | Applied and tested. |
| MFA | Director TOTP tracks accepted time steps, rejects replay, rate limits invalid attempts, applies temporary lockout with `Retry-After`, and never logs seeds or OTP codes. | Applied and tested with synthetic seed. |
| Rate limit | In-memory bounded limiter applies route-class, per-IP, and per-principal limits with TTL cleanup and no raw API keys or PHI in keys. | Applied and tested. |
| Client IP | Direct peer address is used by default; forwarded headers are ignored unless trusted proxy configuration is explicit. | Applied and tested. |
| CORS | Wildcard production origins and credentials-with-wildcard are rejected; local sandbox origins remain narrow. `X-Session-Token` is explicitly allowed. | Applied and tested. |
| Secrets | Required secrets fail closed in controlled pilot/production; placeholders and weak values are rejected; local files remain gitignored and local-only. | Applied and tested. |

## Known Residuals

Phase 6 remains an in-memory sandbox control set unless a later phase adds durable distributed session, MFA replay, rate-limit, identity-provider, and secret-management storage. Shared API key authentication is not hospital user identity, RBAC, SSO, OAuth, OIDC, compliance proof, hospital readiness, controlled-pilot readiness, or production readiness. Gate A remains unmet.
## Development-Origin Boundary Note

| Scenario | Classification | Evidence | Policy |
|---|---|---|---|
| `http://localhost:3000` in clean Incognito | Supported local-development origin | Application shell rendered normally; no blank page reproduced. | Default local development should use `localhost` or `127.0.0.1`. |
| `http://172.16.0.2:3000` | Local development-origin configuration issue | Next.js development resources were blocked cross-origin by default. | Do not add wildcard origins. Add development-only `allowedDevOrigins` only if network-host development access is explicitly required. |
| Hydration warning with body attributes | Browser-extension artifact | Warning was absent in Incognito. | Do not classify as application startup regression unless reproduced on `localhost` in clean Incognito/Guest profile. |

This is localhost smoke evidence only. It is not full browser-rendered QA and does not change production CORS or CSP policy.

## Browser-Carried Credential Limitation

A browser-carried shared API key is visible to the browser client. Header-only transport prevents leakage through FormData, URL parameters, cookies, and browser storage, but it does not make the key a confidential server-side credential. This mechanism is a local clinical-sandbox containment control only. It is not hospital user identity, RBAC, SSO, OAuth/OIDC, or production-grade authentication. A real identity provider or server-side mediation pattern remains required before controlled-pilot claims.

Director enrollment is local-sandbox provisioning only unless a formally approved provisioning workflow is implemented later. `/director/enroll` is disabled by default, accepts bootstrap only through `X-Director-Bootstrap`, is rate-limited, requires `DIRECTOR_ENROLLMENT_ENABLED=true` in `clinical_sandbox`, and rejects repeat enrollment after a seed exists.
