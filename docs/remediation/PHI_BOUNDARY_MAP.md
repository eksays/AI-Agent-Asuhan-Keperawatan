# PHI Boundary Map

## Phase 1 Scope

Phase 1 covers outbound PHI containment for the active backend model, EBP, streaming, logging, session-memory, feedback-memory, and reviewed registry utility paths. Verification uses synthetic canaries and mocks only. External LLM, EBP, and Mermaid capabilities remain disabled by default.

## Tested Paths

| Path | Boundary | Phase 1 Control | Test Evidence |
|---|---|---|---|
| `/chat` | Browser JSON, session memory, LLM prompt, follow-up history | `SafeLLM`, `_external_safe_text`, `_browser_safe_text`, sanitized `SESI.add` | `test_chat_json_response_sanitizes_provider_output_and_memory`, `test_same_session_followup_history_reuse_does_not_reintroduce_raw_phi` |
| `/chat_stream` | Buffered browser stream, LLM prompt, session memory | Full output generated first, sanitized second, chunked third; direct `.stream()` disabled | `test_chat_stream_precomputes_then_emits_sanitized_chunks`, `test_chat_stream_buffers_split_identifier_fragments_before_chunking` |
| `/analisis` | Fallback analysis prompt, upload context, browser JSON | Safe wrapper and browser sanitizer | `test_analisis_fallback_json_response_sanitizes_uploaded_context` |
| `/analisis_multi` | Uploaded document context, medium/pro review input, browser JSON | Safe case text for orchestration and sanitized memory writes | `test_analisis_multi_json_response_sanitizes_uploaded_document_context`, `test_medium_and_pro_review_inputs_are_sanitized` |
| `/pathway` when explicitly mocked enabled | Mermaid JSON response, LLM prompt | Safe wrapper and browser sanitizer before `extract_mermaid` | `test_pathway_json_response_sanitizes_reachable_mocked_output` |
| Feedback memory | Feedback writes and correction recall | `memory.store_feedback` and `memory.recall_block` sanitize text | `test_feedback_correction_recall_is_sanitized_before_outbound_prompt` |
| EBP retrieval | Query generation and external search query | Local policy de-identifies first, then LLM query generation, then residual PHI check | `test_retrieve_context_deidentifies_llm_prompt_and_search_query`, `test_ebp_query_is_compact_bounded_and_clinically_meaningful` |
| Logs and local ledger | Console errors, incident warning, audit action/status | `sanitize_for_log` before print/write | `test_console_error_log_sanitizes_canary_text`, `test_incident_print_helpers_sanitize_path_text`, `test_audit_log_sanitizes_action_and_status_fields` |
| Registry utilities | `ekstraksi.py`, `scripts/populate_sdki.py` | Safe LLM wrapper, sanitized request body, sanitized errors | `test_ekstraksi_error_print_sanitizes_exception_text`, `test_population_script_*` |
| Owned backend source | Direct outbound primitive bypasses | Static allowlist scanner | `phase1_outbound_bypass_test.py` |

## Tested Synthetic Identifier Classes

- Patient names in labeled and embedded forms.
- NIK, BPJS, MRN/RM, slash-style MRN.
- Indonesian phone numbers including `+62`, dashed, and parenthesized `0812` forms.
- Email addresses.
- Address lines beginning with Indonesian address labels.
- Date of birth labels including Indonesian date text and ISO date.
- Family contact name and phone.
- History echoes, provider-response echoes, feedback text, correction text, and uploaded-document content.

## Preservation Checks

The policy was tested to preserve these clinical measurements and registry terms: `TD 120/80 mmHg`, `RR 28 x/menit`, `SpO2 92%`, `Suhu 38.5 C`, `Nadi 110 x/menit`, `GCS 15`, `Hb 10.2 g/dL`, `Glukosa 180 mg/dL`, `Na 138 mmol/L`, `K 4.1 mmol/L`, `BB 65 kg`, `TB 170 cm`, `D.0005`, `SDKI`, `SLKI`, `SIKI`, `NANDA`, `NOC`, and `NIC`.

## Known Limitations

- Regex detection is not complete PHI detection. It will miss some names without labels or titles, unusual identifiers, uncommon address forms, and spelling/OCR variants not covered by tests.
- Name matching uses heuristics and stop words to avoid swallowing clinical sentence text. This may still produce false positives or false negatives.
- The EBP concept query preserves clinically meaningful concepts but is not a formal PICO validator.
- Browser output sanitization is PHI containment only. It is not typed clinical schema validation.
- Existing upload parsing remains thread-based and extension-driven until Phase 5.
- Mermaid/SVG XSS hardening remains Phase 4 work.

## False Positive Risks

- Long numeric strings that are clinically meaningful but resemble identifiers may be redacted.
- Some uppercase or label-adjacent human-language tokens may be treated as names.
- Slash-separated identifiers are redacted conservatively when labeled as MRN/RM.

## False Negative Risks

- Unlabeled personal names in ordinary prose may pass if they do not use a title or patient/contact label.
- Addresses without known Indonesian address terms may pass.
- Non-Indonesian identifiers and uncommon insurance/record formats may pass.
- Images/OCR noise can bypass expected token shapes until Phase 5/10 work.

## Buffered Streaming Rationale

Direct provider token streaming can expose raw model output before sanitization. Phase 1 therefore generates the full provider output, applies browser sanitization to the full text, and only then emits chunks. This protects identifiers split across provider token boundaries.

## Not Compliance Certification

This is not HIPAA compliance, UU PDP compliance, clinical validation, or production readiness. It is a tested containment layer for a clinical sandbox. External capabilities remain disabled by default because later gates still require typed clinical schemas, registry quarantine, rendering hardening, upload isolation, authentication hardening, audit redesign, formal security review, formal privacy review, and clinical validation.

## Gate Status

Gate A remains unmet. Phase 1 closes the tested outbound PHI and buffered streaming controls, but Gate A also requires basic typed clinical schema validation, registry quarantine, Mermaid/SVG hardening, and upload limits/isolation.
