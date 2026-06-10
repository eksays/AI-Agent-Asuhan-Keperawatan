from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class P9BFixtureLoaderTests(unittest.TestCase):
    def _write_manifest(self, root: Path, entry: dict, content: str = 'synthetic generated text') -> None:
        rel = entry.get('relative_path', 'fixture.txt')
        if rel and not Path(rel).is_absolute() and '..' not in Path(rel).parts:
            (root / rel).write_text(content, encoding='utf-8')
        (root / 'manifest.json').write_text(json.dumps({'fixtures': [entry]}), encoding='utf-8')

    def _valid_entry(self, **updates) -> dict:
        entry = {
            'case_id': 'synthetic-loader-case',
            'title': 'Synthetic Loader Case',
            'relative_path': 'fixture.txt',
            'synthetic_only': True,
            'authority': False,
            'clinical_use_allowed': False,
            'provenance_status': 'synthetic_generated',
            'license_status': 'synthetic_only',
            'review_status': 'approved_for_synthetic_test',
            'language_code': 'id',
        }
        entry.update(updates)
        return entry

    def test_allowlisted_fixture_pack_loads(self):
        from rag_fixture_loader import default_fixture_root, fixture_case_ids, load_manifest

        fixtures = load_manifest(default_fixture_root())
        self.assertIn('synthetic-respiratory-observation', fixture_case_ids(fixtures))
        for fixture in fixtures:
            self.assertTrue(fixture.synthetic_only)
            self.assertFalse(fixture.authority)
            self.assertFalse(fixture.clinical_use_allowed)
            self.assertEqual(fixture.license_status, 'synthetic_only')

    def test_rejects_traversal_absolute_nonmanifest_and_symlink(self):
        from rag_fixture_loader import RagFixtureError, load_fixture_case, load_manifest

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest(root, self._valid_entry(relative_path='../escape.txt'))
            with self.assertRaises(RagFixtureError):
                load_manifest(root)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest(root, self._valid_entry(relative_path=str((root / 'absolute.txt').resolve())))
            with self.assertRaises(RagFixtureError):
                load_manifest(root)
        with self.assertRaises(RagFixtureError):
            load_fixture_case('synthetic-missing-case')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root.parent / ('outside-' + next(tempfile._get_candidate_names()))
            outside.write_text('synthetic outside text', encoding='utf-8')
            link = root / 'fixture.txt'
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError):
                outside.unlink(missing_ok=True)
                self.skipTest('symlink creation unavailable')
            try:
                (root / 'manifest.json').write_text(json.dumps({'fixtures': [self._valid_entry()]}), encoding='utf-8')
                with self.assertRaises(RagFixtureError):
                    load_manifest(root)
            finally:
                outside.unlink(missing_ok=True)

    def test_rejects_missing_synthetic_unknown_license_oversized_and_canary(self):
        from rag_fixture_loader import RagFixtureError, load_manifest

        cases = [
            (self._valid_entry(synthetic_only=False), 'synthetic generated text', 12000),
            (self._valid_entry(license_status='unknown'), 'synthetic generated text', 12000),
            (self._valid_entry(), 'x' * 200, 50),
            (self._valid_entry(), 'PHI_CANARY synthetic rejection marker', 12000),
        ]
        for entry, content, limit in cases:
            with self.subTest(entry=entry, limit=limit), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._write_manifest(root, entry, content)
                with self.assertRaises(RagFixtureError):
                    load_manifest(root, max_document_chars=limit)


class P9BChunkingTests(unittest.TestCase):
    def test_chunking_is_deterministic_with_stable_ids_and_hashes(self):
        from rag_chunking import ChunkingConfig, chunk_document

        text = '# Heading\n\nThis synthetic paragraph supports deterministic lexical chunking. ' * 4
        cfg = ChunkingConfig(target_words=45, overlap_words=5)
        first = chunk_document(text, document_id='SYN-P9B-DOC', source_version_id='SYN-P9B-VER', config=cfg)
        second = chunk_document(text, document_id='SYN-P9B-DOC', source_version_id='SYN-P9B-VER', config=cfg)
        self.assertEqual([chunk.chunk_id for chunk in first], [chunk.chunk_id for chunk in second])
        self.assertEqual([chunk.chunk_hash for chunk in first], [chunk.chunk_hash for chunk in second])

    def test_heading_list_table_overlap_and_duplicate_rules(self):
        from rag_chunking import ChunkingConfig, chunk_document

        text = '''# Root

## Steps
1. First synthetic step remains grouped.
2. Second synthetic step remains grouped.

## Rows
| key | value |
| row | synthetic |

## Long
alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega

## Duplicate
repeat duplicate text

## Duplicate Two
repeat duplicate text
'''
        chunks = chunk_document(text, document_id='SYN-P9B-DOC', source_version_id='SYN-P9B-VER', config=ChunkingConfig(target_words=12, overlap_words=3))
        paths = [chunk.section_path for chunk in chunks]
        self.assertIn('Root > Steps', paths)
        self.assertIn('Root > Rows', paths)
        self.assertEqual(len({chunk.chunk_hash for chunk in chunks}), len(chunks))
        long_chunks = [chunk for chunk in chunks if chunk.section_path == 'Root > Long']
        self.assertGreater(len(long_chunks), 1)
        self.assertLessEqual(max(chunk.word_count for chunk in long_chunks), 40)

    def test_normalization_and_control_character_rejection(self):
        from rag_chunking import RagChunkingError, normalize_text

        self.assertIn('ABC', normalize_text('\uFF21\uFF22\uFF23'))
        with self.assertRaises(RagChunkingError):
            normalize_text('unsafe\x01control')

    def test_no_external_tokenizer_or_provider_import(self):
        source = (ROOT / 'rag_chunking.py').read_text(encoding='utf-8').lower()
        for token in ('openai', 'anthropic', 'sentence_transformers', 'tiktoken', 'requests'):
            self.assertNotIn(token, source)


if __name__ == '__main__':
    unittest.main()
