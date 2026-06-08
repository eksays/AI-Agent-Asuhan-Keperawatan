import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = new URL('..', import.meta.url);
const rootPath = fileURLToPath(root);
const read = (path) => readFileSync(new URL(path, root), 'utf8');

const runnerSource = read('components/synthetic-lab-mermaid-runner.tsx');
const dashboardSource = read('components/dashboard.tsx');
const apiSource = read('lib/api.ts');
const mermaidSource = read('components/ui/mermaid.tsx');
const sanitizerSource = read('lib/svg-sanitize.ts');
const safeFixture = read('../backend/tests/fixtures/synthetic_lab/rendering/safe_pathway.json');
const maliciousFixture = read('../backend/tests/fixtures/synthetic_lab/rendering/malicious_pathway.json');

function collectSourceFiles(start) {
  const entries = readdirSync(start, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = join(start, entry.name);
    if (entry.isDirectory()) {
      if (['node_modules', '.next', 'tests'].includes(entry.name)) continue;
      files.push(...collectSourceFiles(full));
      continue;
    }
    if (/\.(?:js|mjs|ts|tsx)$/.test(entry.name)) files.push(relative(rootPath, full).replace(/\\/g, '/'));
  }
  return files;
}

test('synthetic Mermaid runner is visible only inside server-authoritative lab mode', () => {
  assert.match(dashboardSource, /SyntheticLabMermaidRunner/);
  assert.match(runnerSource, /capabilities\.synthetic_lab_enabled/);
  assert.match(runnerSource, /if \(!capabilities\.synthetic_lab_enabled\) return null/);
  assert.match(runnerSource, /capabilities\.synthetic_mermaid_enabled/);
  assert.match(runnerSource, /SYNTHETIC PROTOTYPE/);
  assert.match(runnerSource, /NOT FOR PATIENT CARE/);
  assert.match(runnerSource, /SANITIZED MERMAID FIXTURE/);
});

test('synthetic Mermaid runner calls guarded lab route with bearer and lab-session headers only', () => {
  assert.match(apiSource, /export async function createLabSession/);
  assert.match(apiSource, /`\$\{API_BASE\}\/lab\/session`/);
  assert.match(apiSource, /export async function runLabPathway/);
  assert.match(apiSource, /`\$\{API_BASE\}\/lab\/pathway`/);
  assert.match(apiSource, /Authorization:\s*`Bearer \$\{apiKey\}`/);
  assert.match(apiSource, /"X-Lab-Session-Id":\s*labSession\.labSessionId/);
  assert.match(apiSource, /"X-Lab-Session-Token":\s*labSession\.labSessionToken/);
  assert.match(apiSource, /body:\s*JSON\.stringify\(\{ fixture_id: fixtureId \}\)/);
  assert.doesNotMatch(apiSource, /\?api_key|session_token=|labSessionToken=/);
});

test('synthetic Mermaid runner is manifest-fixture only and supports safe plus malicious test fixtures', () => {
  assert.match(runnerSource, /SYN-MMD-SAFE-001/);
  assert.match(runnerSource, /SYN-MMD-MAL-001/);
  assert.match(safeFixture, /"fixture_id":\s*"SYN-MMD-SAFE-001"/);
  assert.match(maliciousFixture, /"fixture_id":\s*"SYN-MMD-MAL-001"/);
  assert.match(maliciousFixture, /javascript:|<script/i);
  assert.match(runnerSource, /lab_mermaid_fixture_rejected|fixture_status=/);
  assert.doesNotMatch(runnerSource, /<textarea|contentEditable|prompt\(|fileReader|mermaid_code|rawMermaid/i);
});

test('synthetic Mermaid runner uses existing sanitizer boundary and adds no raw HTML sink', () => {
  assert.match(runnerSource, /<Mermaid code=\{result\.mermaid\}/);
  assert.doesNotMatch(runnerSource, /dangerouslySetInnerHTML|innerHTML|insertAdjacentHTML|outerHTML|document\.write|eval\(|new Function\(/);
  assert.match(mermaidSource, /securityLevel:\s*"strict"/);
  assert.match(mermaidSource, /flowchart:\s*\{\s*htmlLabels:\s*false\s*\}/);
  assert.match(mermaidSource, /sanitizeMermaidSvg\(rendered\)/);
  assert.match(sanitizerSource, /foreignObject/);
  assert.match(sanitizerSource, /data:text\/html/);

  const files = [...collectSourceFiles(join(rootPath, 'components')), ...collectSourceFiles(join(rootPath, 'lib'))];
  const joined = files.map((file) => `\n/* ${file} */\n${read(file)}`).join('\n');
  assert.equal((joined.match(/dangerouslySetInnerHTML/g) || []).length, 1);
  assert.match(read('components/ui/mermaid.tsx'), /data-sanitizer-boundary=\{SVG_SANITIZER_BOUNDARY\}/);
});
