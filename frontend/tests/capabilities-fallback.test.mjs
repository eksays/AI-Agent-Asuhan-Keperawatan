import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../lib/capabilities.ts", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

const requiredCapabilities = [
  "external_llm",
  "ebp_external_search",
  "clinical_photo_analysis",
  "mermaid_pathway_rendering",
  "sdki_authoritative_grounding",
  "slki",
  "siki",
  "nanda",
  "noc",
  "nic",
];

test("frontend fail-closed fallback disables unsafe capabilities", () => {
  assert.match(source, /FAIL_CLOSED_CAPABILITIES/);
  for (const key of requiredCapabilities) {
    const pattern = new RegExp(`${key}: \\{ enabled: false, reason:`);
    assert.match(source, pattern, `${key} must default disabled`);
  }
});

test("frontend fallback warns when capability metadata is unavailable", () => {
  assert.match(source, /metadata_unavailable: true/);
  assert.match(source, /unsafe features are disabled/i);
});

test("capabilities fetch failure returns fail-closed metadata", () => {
  assert.match(apiSource, /export async function getCapabilities/);
  assert.match(apiSource, /catch\s*\{\s*return FAIL_CLOSED_CAPABILITIES;\s*\}/);
});

test("normalization rejects missing or partial capability payloads", () => {
  assert.match(source, /enabled: incoming\?\.enabled === true/);
  assert.match(source, /metadata_unavailable: raw\?\.metadata_unavailable === true \|\| !raw/);
});
