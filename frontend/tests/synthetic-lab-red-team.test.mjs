import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const panelSource = readFileSync(new URL('../components/synthetic-lab-trace-panel.tsx', import.meta.url), 'utf8');
const mermaidRunnerSource = readFileSync(new URL('../components/synthetic-lab-mermaid-runner.tsx', import.meta.url), 'utf8');
const dashboardSource = readFileSync(new URL('../components/dashboard.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../lib/api.ts', import.meta.url), 'utf8');
const capabilitiesSource = readFileSync(new URL('../lib/capabilities.ts', import.meta.url), 'utf8');
const browserSecuritySource = readFileSync(new URL('./browser-security.test.mjs', import.meta.url), 'utf8');
const maliciousMermaidFixture = readFileSync(new URL('../../backend/tests/fixtures/synthetic_lab/rendering/malicious_pathway.json', import.meta.url), 'utf8');

const canaries = [
  'PHI-CANARY-NAME-ALPHA',
  'PHI-CANARY-MRN-000001',
  'PHI-CANARY-PHONE-080000000001',
  'PHI-CANARY-ADDRESS-ALPHA',
  'SECRET-CANARY-API-KEY',
  'SECRET-CANARY-SESSION-TOKEN',
  'SECRET-CANARY-OTP',
  'SECRET-CANARY-TOTP-SEED',
  'SECRET-CANARY-LEDGER-KEY',
];

test('synthetic lab UI sources contain no PHI or secret canary strings', () => {
  const joined = [panelSource, mermaidRunnerSource, dashboardSource, apiSource, capabilitiesSource].join('\n');
  for (const canary of canaries) assert.doesNotMatch(joined, new RegExp(canary));
});

test('trace panel renders only safe labels and conservative status metadata', () => {
  for (const label of ['REAL LOCAL PATH', 'SYNTHETIC PROTOTYPE', 'DETERMINISTIC MOCK', 'DISABLED', 'FORBIDDEN IN LAB']) {
    assert.match(panelSource, new RegExp(label));
  }
  for (const safeField of ['run_id', 'feature_label', 'agent_stages', 'stage_status', 'retrieved_document_ids', 'retrieval_scores']) {
    assert.match(panelSource, new RegExp(safeField));
  }
  for (const forbidden of [/raw prompt/i, /raw output/i, /uploaded text/i, /chain-of-thought/i, /filesystem path/i, /stack trace/i, /session token/i, /api key/i]) {
    assert.doesNotMatch(panelSource, forbidden);
  }
  assert.match(panelSource, /registry_authoritative=\{String\(trace\?\.registry_authoritative === true\)\}/);
  assert.match(panelSource, /clinical_use_allowed=\{String\(trace\?\.clinical_use_allowed === true\)\}/);
  assert.match(panelSource, /accepted_recommendations=\{String\(trace\?\.accepted_recommendations === true\)\}/);
  assert.match(panelSource, /nurse_review_required=\{String\(trace\?\.nurse_review_required !== false\)\}/);
});

test('banner is persistent, server-authoritative, and not backed by browser storage', () => {
  assert.match(dashboardSource, /capabilities\.synthetic_lab_enabled/);
  assert.match(dashboardSource, /SYNTHETIC INTEGRATION LAB/);
  assert.match(dashboardSource, /DO NOT ENTER REAL PATIENT DATA/);
  assert.match(dashboardSource, /NOT FOR PATIENT CARE/);
  assert.match(dashboardSource, /OUTPUTS MAY BE MOCKED OR PROTOTYPE-ONLY/);
  assert.match(dashboardSource, /closable=\{false\}/);
  assert.doesNotMatch([panelSource, mermaidRunnerSource, dashboardSource, apiSource, capabilitiesSource].join('\n'), /localStorage|sessionStorage/);
});

test('lab trace API uses bearer and lab-session headers without query-string secrets', () => {
  assert.match(apiSource, /Authorization:\s*`Bearer \$\{apiKey\}`/);
  assert.match(apiSource, /"X-Lab-Session-Id":\s*labSession\.labSessionId/);
  assert.match(apiSource, /"X-Lab-Session-Token":\s*labSession\.labSessionToken/);
  assert.doesNotMatch(apiSource, /\?api_key|session_token=|labSessionToken=/);
});

test('malicious Mermaid fixture remains covered by existing sanitizer tests', () => {
  assert.match(maliciousMermaidFixture, /javascript:|<script|onclick/i);
  assert.match(mermaidRunnerSource, /SYN-MMD-SAFE-001/);
  assert.match(mermaidRunnerSource, /SYN-MMD-MAL-001/);
  assert.match(mermaidRunnerSource, /<Mermaid code=\{result\.mermaid\}/);
  assert.match(browserSecuritySource, /SVG sanitizer strips or rejects executable SVG payloads/);
  assert.match(browserSecuritySource, /dangerous rendering sink scanner has only documented source matches/);
  assert.doesNotMatch(panelSource, /dangerouslySetInnerHTML|innerHTML/);
  assert.doesNotMatch(mermaidRunnerSource, /dangerouslySetInnerHTML|innerHTML/);
});

test('external provider and normal unsafe feature flags fail closed in frontend metadata', () => {
  assert.match(capabilitiesSource, /lab_external_provider_enabled:\s*false/);
  assert.match(capabilitiesSource, /external_llm:\s*\{ enabled:\s*false/);
  assert.match(capabilitiesSource, /ebp_external_search:\s*\{ enabled:\s*false/);
  assert.match(capabilitiesSource, /clinical_photo_analysis:\s*\{ enabled:\s*false/);
  assert.match(capabilitiesSource, /mermaid_pathway_rendering:\s*\{ enabled:\s*false/);
});
