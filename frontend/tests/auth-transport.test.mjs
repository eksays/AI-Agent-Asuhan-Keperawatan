import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const apiSource = readFileSync(new URL('../lib/api.ts', import.meta.url), 'utf8');
const contextSource = readFileSync(new URL('../components/app-context.tsx', import.meta.url), 'utf8');
const directorSource = readFileSync(new URL('../app/director-dashboard/page.tsx', import.meta.url), 'utf8');
const joined = [apiSource, contextSource, directorSource].join('\n');

test('API key transport is Authorization-header only', () => {
  assert.doesNotMatch(joined, /api_key/);
  assert.doesNotMatch(joined, /append\(['"]api_key/);
  assert.match(apiSource, /Authorization/);
});

test('session and director secrets stay out of browser storage', () => {
  assert.doesNotMatch(joined, /localStorage/);
  assert.doesNotMatch(joined, /sessionStorage/);
  assert.match(joined, /X-Session-Token/);
});
