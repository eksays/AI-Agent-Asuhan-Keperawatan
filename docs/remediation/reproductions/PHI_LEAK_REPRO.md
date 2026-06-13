# PHI Leak Reproduction Notes - Synthetic Canaries Only

These notes preserve Phase 1 reproduction context using synthetic canaries only. They must not be replaced with real patient data, real clinical uploads, real runtime logs, or local secrets.

## Synthetic Canary Payload

```text
Nama pasien: Budi Santoso
NIK: 3273010101990001
No. BPJS: 0001234567890
MRN: RM-2026-001928
Telepon: +62 812-3456-7890
Email: budi.patient@example.com
Alamat: Jalan Merdeka No. 12 Bandung
Tanggal lahir: 1 Januari 1990
```

## Reproduction Summary

1. Monkeypatch backend LLM/EBP dependencies so no external network request is made.
2. Create a backend session with `POST /session`.
3. Submit the synthetic canary to `/chat` with `agent=referensi` and capture the argument passed into the EBP retrieval boundary.
4. Submit a flash `/chat_stream` request using a dummy LLM that emits synthetic canary identifiers.
5. Build messages with the synthetic canary and call `agents.orchestrate_answer(..., human=<raw canary>, tier="medium")` using a dummy LLM to capture review-pass inputs.

## Observed Phase 0A Behavior

- EBP retrieval received raw synthetic canary fields before a de-identification policy boundary.
- Flash streaming returned raw synthetic canary fields to the browser before final output sanitization.
- The medium review pass reintroduced the raw synthetic canary through the `human` argument even after the first generated message was partially sanitized.
- The deterministic sanitizer left several synthetic identifier categories unsanitized.

## Phase 1 Closure Regression Status

- `backend.tests.phase1_outbound_policy_test` verifies no synthetic canary identifier reaches mocked external providers, EBP retrieval, browser JSON responses, buffered stream chunks, session history, feedback/correction recall, console logs, audit records, utility-script request bodies, or utility-script error output.
- `backend.tests.phase1_outbound_bypass_test` scans owned backend source and fails if new outbound execution primitives appear outside the reviewed allowlist.
- The original Phase 0A leak paths are mitigated for tested synthetic cases by `OutboundDataPolicy`, `SafeLLM`, de-identified EBP concept queries, sanitized memory writes, and buffered streaming.
- This does not prove perfect de-identification or compliance. Known limitations and untested paths are maintained in `docs/remediation/PHI_BOUNDARY_MAP.md`.
