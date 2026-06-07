import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const capabilitiesSource = readFileSync(new URL('../lib/capabilities.ts', import.meta.url), 'utf8');
const dashboardSource = readFileSync(new URL('../components/dashboard.tsx', import.meta.url), 'utf8');

test('synthetic lab capability metadata fails closed in the browser', () => {
  assert.match(capabilitiesSource, /synthetic_lab_enabled:\s*false/);
  assert.match(capabilitiesSource, /synthetic_data_only:\s*false/);
  assert.match(capabilitiesSource, /lab_external_provider_enabled:\s*false/);
  assert.match(capabilitiesSource, /lab_feature_activation_status:\s*"disabled"/);
  assert.match(capabilitiesSource, /raw\?\.synthetic_lab_enabled === true/);
  assert.match(capabilitiesSource, /raw\?\.synthetic_data_only === true/);
  assert.match(capabilitiesSource, /lab_external_provider_enabled:\s*false/);
});

test('synthetic lab banner is server-authoritative and non-closable', () => {
  assert.match(dashboardSource, /capabilities\.synthetic_lab_enabled/);
  assert.match(dashboardSource, /SYNTHETIC INTEGRATION LAB/);
  assert.match(dashboardSource, /DO NOT ENTER REAL PATIENT DATA/);
  assert.match(dashboardSource, /NOT FOR PATIENT CARE/);
  assert.match(dashboardSource, /OUTPUTS MAY BE MOCKED OR PROTOTYPE-ONLY/);
  assert.match(dashboardSource, /closable=\{false\}/);
  assert.doesNotMatch(dashboardSource, /process\.env\.SYNTHETIC/);
  assert.doesNotMatch(dashboardSource, /localStorage|sessionStorage/);
});
