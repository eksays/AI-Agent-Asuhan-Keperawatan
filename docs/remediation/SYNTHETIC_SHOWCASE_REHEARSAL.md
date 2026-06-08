# Synthetic Showcase Rehearsal

This rehearsal is for the `review/synthetic-integration-lab` review branch only.
It is an offline synthetic showcase, not patient-care software, not clinical
validation, not hospital readiness, and not production readiness.

```text
SYNTHETIC INTEGRATION LAB - DO NOT ENTER REAL PATIENT DATA.
NOT FOR PATIENT CARE.
OUTPUTS MAY BE MOCKED OR PROTOTYPE-ONLY.
```

Use placeholder-only local values. Do not use provider API keys, patient data,
hospital documents, runtime ledgers, audit exports, or ignored registry data.

## Checkout

```powershell
git fetch origin
git switch review/synthetic-integration-lab
git pull --ff-only
git rev-parse HEAD
```

Expected checkpoint after Sprint B approval:

```text
d9979f5594c040de56c69c91ceb7d65a62e9a8fe or a later reviewed Sprint C commit
```

## Placeholder Local Environment

Use a local shell for backend startup:

```powershell
$env:APP_MODE="clinical_sandbox"
$env:CDSS_API_KEYS="test-key"
$env:CDSS_SECRET_KEY="local-sandbox-secret-change-me"

$env:SYNTHETIC_LAB_MODE="true"
$env:SYNTHETIC_DATA_ONLY="true"
$env:SYNTHETIC_MULTI_AGENT="true"
$env:SYNTHETIC_RAG="true"
$env:SYNTHETIC_REGISTRY="true"
$env:SYNTHETIC_EBP="true"
$env:SYNTHETIC_MERMAID="true"
$env:SYNTHETIC_UPLOADS="true"
$env:SYNTHETIC_OCR_MOCK="true"
$env:SYNTHETIC_PHOTO_MOCK="true"
$env:SYNTHETIC_FEEDBACK_MEMORY="true"

$env:FEATURE_EXTERNAL_LLM="false"
$env:FEATURE_EBP_EXTERNAL_SEARCH="false"
$env:FEATURE_CLINICAL_PHOTO_ANALYSIS="false"
$env:FEATURE_MERMAID_PATHWAY_RENDERING="false"
$env:HARVEST_INTERVAL_SEC="0"
```

Do not set `AUDIT_LEDGER_HMAC_KEY` for ordinary UI rehearsal. For the ledger
verification rehearsal below, use a temporary path and temporary placeholder key
only, then remove the file.

## Start Local Services

Backend on loopback only:

```powershell
backend\venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Frontend on localhost only:

```powershell
npm --prefix frontend run dev -- --hostname localhost --port 3000
```

Open:

```text
http://localhost:3000
```

Use `test-key` as the placeholder API key in the UI. Do not enter patient text.
When the synthetic lab is enabled, the dashboard shows a synthetic-lab-only
Mermaid fixture runner. Use the safe fixture to confirm the existing sanitizer
renders a generated pathway, then use the malicious fixture test to confirm the
fixture is rejected safely or inert. Normal Mermaid capability remains disabled.

## Backend Route Rehearsal

Create a lab session:

```powershell
$headers = @{ Authorization = "Bearer test-key" }
$session = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/session -Headers $headers
$labHeaders = @{
  Authorization = "Bearer test-key"
  "X-Lab-Session-Id" = $session.lab_session_id
  "X-Lab-Session-Token" = $session.lab_session_token
}
```

Run representative synthetic-only fixtures:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/run -Headers $labHeaders -ContentType application/json -Body '{"fixture_id":"SYN-CASE-RESP-001"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/rag -Headers $labHeaders -ContentType application/json -Body '{"query":"respiratory oxygen monitoring"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/registry -Headers $labHeaders -ContentType application/json -Body '{"code":"SYN-D-001"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/ebp -Headers $labHeaders -ContentType application/json -Body '{}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/upload -Headers $labHeaders -ContentType application/json -Body '{"fixture_id":"SYN-UPLOAD-TXT-001"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/upload -Headers $labHeaders -ContentType application/json -Body '{"fixture_id":"SYN-UPLOAD-PDF-HOSTILE-001"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/upload -Headers $labHeaders -ContentType application/json -Body '{"fixture_id":"SYN-UPLOAD-DOCX-HOSTILE-001"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/pathway -Headers $labHeaders -ContentType application/json -Body '{"fixture_id":"SYN-MMD-SAFE-001"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/pathway -Headers $labHeaders -ContentType application/json -Body '{"fixture_id":"SYN-MMD-MAL-001"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/ocr -Headers $labHeaders -ContentType application/json -Body '{}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/photo -Headers $labHeaders -ContentType application/json -Body '{}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/lab/feedback -Headers $labHeaders -ContentType application/json -Body '{"feedback_id":"SYN-FB-001","rating":"up","note":"synthetic closure note"}'
```

For each successful response, inspect:

- `run_id`
- `trace.agent_stages`
- `retrieved_document_ids` and `retrieval_scores` where present
- `registry_authoritative=false`
- `clinical_use_allowed=false`
- `accepted_recommendations=false`
- `nurse_review_required=true`

## Kill-Switch Rehearsal

Stop the backend, set:

```powershell
$env:SYNTHETIC_LAB_MODE="false"
```

Unset every Sprint B feature flag or set it to `false`, then restart the
backend. Confirm every `/lab/*` path returns `synthetic_lab_disabled` and normal
routes keep their existing fail-closed behavior.

## Audit-Ledger Verification Rehearsal

Use a temp directory outside the repository or an ignored temp path. Example:

```powershell
$tmp = New-Item -ItemType Directory -Path ([System.IO.Path]::Combine($env:TEMP, "synthetic-ledger-" + [guid]::NewGuid()))
$ledger = Join-Path $tmp.FullName "audit.jsonl"
$key = "synthetic-lab-sprint-c-ledger-key-000000000000000000000000"
python backend/scripts/verify_audit_ledger.py --path $ledger --key $key --key-id lab-sprint-c-test
Remove-Item -LiteralPath $tmp.FullName -Recurse -Force
```

The Sprint C automated red-team suite creates a temporary ledger with all lab
event types, verifies it, tampers it, and confirms verification fails. Runtime
ledger files must never be staged.

## Required Local Checks

```powershell
backend\venv\Scripts\python.exe -m unittest backend.tests.synthetic_lab_foundation_test -v
backend\venv\Scripts\python.exe -m unittest backend.tests.synthetic_lab_core_features_test -v
backend\venv\Scripts\python.exe -m unittest backend.tests.synthetic_lab_red_team_test -v
backend\venv\Scripts\python.exe -m unittest discover -s backend\tests -p "*_test.py" -v
python -m compileall backend -q -x ".*(venv|__pycache__).*"
backend\venv\Scripts\bandit.exe -r backend -ll -x backend/env,backend/venv
node --test frontend\tests\synthetic-lab-red-team.test.mjs
node --test frontend\tests\synthetic-lab-mermaid-runner.test.mjs
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=moderate
```

Known residuals are recorded in
`docs/remediation/SYNTHETIC_SHOWCASE_LIMITATIONS.md`.
