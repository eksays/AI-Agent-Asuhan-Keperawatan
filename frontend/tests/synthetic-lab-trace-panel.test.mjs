import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const capabilitiesSource = readFileSync(new URL('../lib/capabilities.ts', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../lib/api.ts', import.meta.url), 'utf8');
const panelSource = readFileSync(new URL('../components/synthetic-lab-trace-panel.tsx', import.meta.url), 'utf8');
const dashboardSource = readFileSync(new URL('../components/dashboard.tsx', import.meta.url), 'utf8');

const sprintBFlags = [
  'synthetic_multi_agent_enabled',
  'synthetic_rag_enabled',
  'synthetic_registry_enabled',
  'synthetic_ebp_enabled',
  'synthetic_mermaid_enabled',
  'synthetic_uploads_enabled',
  'synthetic_ocr_mock_enabled',
  'synthetic_photo_mock_enabled',
  'synthetic_feedback_memory_enabled',
];

test('Sprint B capability flags fail closed and normalize only explicit true values', () => {
  for (const flag of sprintBFlags) {
    assert.match(capabilitiesSource, new RegExp(`${flag}:\\s*false`));
    assert.match(capabilitiesSource, new RegExp(`${flag}:\\s*raw\\?\\.${flag} === true`));
  }
  assert.match(capabilitiesSource, /lab_external_provider_enabled:\s*false/);
  assert.match(capabilitiesSource, /lab_feature_activation_status:\s*"disabled"/);
});

test('trace API uses bearer auth and lab session headers only', () => {
  assert.match(apiSource, /export async function getLabTrace/);
  assert.match(apiSource, /\/lab\/trace\/\$\{encodeURIComponent\(runId\)\}/);
  assert.match(apiSource, /Authorization:\s*`Bearer \$\{apiKey\}`/);
  assert.match(apiSource, /"X-Lab-Session-Id":\s*labSession\.labSessionId/);
  assert.match(apiSource, /"X-Lab-Session-Token":\s*labSession\.labSessionToken/);
  assert.doesNotMatch(apiSource, /localStorage|sessionStorage/);
});

test('trace panel exposes safe labels and conservative clinical booleans', () => {
  for (const label of ['REAL LOCAL PATH', 'SYNTHETIC PROTOTYPE', 'DETERMINISTIC MOCK', 'DISABLED', 'FORBIDDEN IN LAB']) {
    assert.match(panelSource, new RegExp(label));
  }
  for (const field of ['run_id', 'feature_label', 'agent_stages', 'stage_status', 'retrieved_document_ids', 'retrieval_scores']) {
    assert.match(panelSource, new RegExp(field));
  }
  assert.match(panelSource, /registry_authoritative=\{String\(trace\?\.registry_authoritative === true\)\}/);
  assert.match(panelSource, /clinical_use_allowed=\{String\(trace\?\.clinical_use_allowed === true\)\}/);
  assert.match(panelSource, /accepted_recommendations=\{String\(trace\?\.accepted_recommendations === true\)\}/);
  assert.match(panelSource, /nurse_review_required=\{String\(trace\?\.nurse_review_required !== false\)\}/);
});

test('trace panel remains server-authoritative and avoids browser persistence or raw trace fields', () => {
  assert.match(panelSource, /capabilities\.synthetic_lab_enabled/);
  assert.match(dashboardSource, /SyntheticLabTracePanel/);
  assert.doesNotMatch(panelSource, /localStorage|sessionStorage/);
  assert.doesNotMatch(panelSource, /dangerouslySetInnerHTML|innerHTML/);
  assert.doesNotMatch(panelSource, /raw prompt|raw output|uploaded text|chain-of-thought|filesystem path|stack trace/i);
});
