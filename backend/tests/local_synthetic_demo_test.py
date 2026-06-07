from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import config  # noqa: E402


class LocalSyntheticDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def setUp(self):
        api.RATE_LIMITER.clear()

    def _demo_config(self, **overrides):
        env = {
            'APP_MODE': 'clinical_sandbox',
            'CDSS_API_KEYS': 'test-key',
            'CDSS_SECRET_KEY': 'local-sandbox-secret-change-me',
            'LOCAL_SYNTHETIC_DEMO': 'true',
            'LOCAL_SYNTHETIC_MOCK_PROVIDER': 'true',
            'FEATURE_EXTERNAL_LLM': 'false',
            'FEATURE_EBP_EXTERNAL_SEARCH': 'false',
            'FEATURE_CLINICAL_PHOTO_ANALYSIS': 'false',
            'FEATURE_MERMAID_PATHWAY_RENDERING': 'false',
            'HARVEST_INTERVAL_SEC': '0',
        }
        env.update(overrides)
        return config.load_config(env)

    def _session(self):
        headers = {'Authorization': 'Bearer test-key'}
        data = self.client.post('/session', headers=headers).json()
        headers['X-Session-Token'] = data['session_token']
        return data['session_id'], headers

    def test_demo_flags_absent_preserves_fail_closed_defaults(self):
        cfg = config.load_config({})
        caps = config.build_capabilities(cfg)['capabilities']
        self.assertFalse(caps['local_synthetic_demo']['enabled'])
        self.assertFalse(caps['external_llm']['enabled'])
        self.assertFalse(caps['ebp_external_search']['enabled'])
        self.assertFalse(caps['clinical_photo_analysis']['enabled'])
        self.assertFalse(caps['mermaid_pathway_rendering']['enabled'])
        self.assertFalse(caps['sdki_authoritative_grounding']['enabled'])
        self.assertEqual(cfg.harvest_interval_sec, 0)

    def test_demo_requires_clinical_sandbox_and_mock_provider(self):
        cfg = self._demo_config()
        caps = config.build_capabilities(cfg)['capabilities']
        self.assertTrue(caps['local_synthetic_demo']['enabled'])
        self.assertFalse(caps['external_llm']['enabled'])
        self.assertFalse(caps['ebp_external_search']['enabled'])
        self.assertFalse(caps['clinical_photo_analysis']['enabled'])
        self.assertFalse(caps['mermaid_pathway_rendering']['enabled'])
        self.assertIn('DO NOT ENTER REAL PATIENT DATA', caps['local_synthetic_demo']['reason'])

        no_mock = self._demo_config(LOCAL_SYNTHETIC_MOCK_PROVIDER='false')
        self.assertFalse(config.build_capabilities(no_mock)['capabilities']['local_synthetic_demo']['enabled'])

    def test_demo_flags_rejected_outside_clinical_sandbox(self):
        with self.assertRaises(RuntimeError):
            config.load_config({
                'APP_MODE': 'controlled_pilot',
                'CDSS_API_KEYS': 'strong-api-key-value-12345',
                'CDSS_SECRET_KEY': 'strong-secret-key-value-123456789012345',
                'DIRECTOR_BOOTSTRAP': 'strong-bootstrap-value-12345',
                'LOCAL_SYNTHETIC_DEMO': 'true',
                'LOCAL_SYNTHETIC_MOCK_PROVIDER': 'true',
            })
        production = {name: 'true' for name in config.PRODUCTION_PREREQUISITES}
        production.update({
            'APP_MODE': 'production',
            'CDSS_API_KEYS': 'strong-api-key-value-12345',
            'CDSS_SECRET_KEY': 'strong-secret-key-value-123456789012345',
            'DIRECTOR_BOOTSTRAP': 'strong-bootstrap-value-12345',
            'LOCAL_SYNTHETIC_DEMO': 'true',
            'LOCAL_SYNTHETIC_MOCK_PROVIDER': 'true',
        })
        with self.assertRaises(RuntimeError):
            config.load_config(production)

    def test_sandbox_mock_chat_and_stream_do_not_call_provider(self):
        cfg = self._demo_config()
        with mock.patch.object(api, 'CONFIG', cfg), mock.patch.object(api, 'get_llm', side_effect=AssertionError('real provider called')):
            sid, headers = self._session()
            payload = {
                'provider': 'openai',
                'model': 'dummy',
                'framework': '3S',
                'session_id': sid,
                'tier': 'flash',
                'agent': 'analisis',
                'pertanyaan': 'halo',
            }
            chat = self.client.post('/chat', data=payload, headers=headers)
            self.assertEqual(chat.status_code, 200)
            self.assertIn(api.SYNTHETIC_DEMO_LABEL, chat.json()['jawaban'])

            stream_sid, stream_headers = self._session()
            payload['session_id'] = stream_sid
            stream = self.client.post('/chat_stream', data=payload, headers=stream_headers)
            self.assertEqual(stream.status_code, 200)
            self.assertIn(api.SYNTHETIC_DEMO_LABEL, stream.text)

    def test_care_plan_without_approved_registry_still_abstains_before_mock(self):
        cfg = self._demo_config()
        with mock.patch.object(api, 'CONFIG', cfg), mock.patch.object(api, 'get_llm', side_effect=AssertionError('real provider called')):
            sid, headers = self._session()
            response = self.client.post(
                '/chat',
                data={
                    'provider': 'openai',
                    'model': 'dummy',
                    'framework': '3S',
                    'session_id': sid,
                    'tier': 'medium',
                    'agent': 'analisis',
                    'pertanyaan': 'Susun diagnosis, luaran, dan intervensi keperawatan lengkap.',
                },
                headers=headers,
            )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(body['clinical_status'], {'registry_unavailable', 'registry_incomplete'})
        self.assertFalse(body['accepted_recommendations'])
        self.assertTrue(body['nurse_review_required'])
        self.assertNotIn(api.SYNTHETIC_DEMO_LABEL, body['jawaban'])

    def test_disabled_features_stay_disabled_in_demo(self):
        cfg = self._demo_config()
        with mock.patch.object(api, 'CONFIG', cfg), mock.patch.object(api, 'get_llm', side_effect=AssertionError('real provider called')):
            sid, headers = self._session()
            base = {'provider': 'openai', 'model': 'dummy', 'framework': '3S', 'session_id': sid, 'tier': 'medium'}
            referensi = self.client.post('/chat', data={**base, 'agent': 'referensi', 'pertanyaan': 'carikan jurnal EBP'}, headers=headers)
            pathway = self.client.post('/pathway', data={**base, 'gejala': 'buat pathway'}, headers=headers)
            photo = self.client.post('/analisis_multi', data={**base, 'agent': 'analisis', 'gejala': 'uji foto'}, files={'file_foto': ('synthetic.jpg', b'\xff\xd8\xff\xd9', 'image/jpeg')}, headers=headers)

        self.assertEqual(referensi.status_code, 503)
        self.assertEqual(referensi.json()['capability'], 'ebp_external_search')
        self.assertEqual(pathway.status_code, 503)
        self.assertEqual(pathway.json()['capability'], 'mermaid_pathway_rendering')
        self.assertEqual(photo.status_code, 503)
        self.assertEqual(photo.json()['capability'], 'clinical_photo_analysis')

    def test_header_only_auth_remains_required_in_demo(self):
        cfg = self._demo_config()
        with mock.patch.object(api, 'CONFIG', cfg):
            self.assertEqual(self.client.post('/session', data={'api_key': 'test-key'}).status_code, 401)
            self.assertEqual(self.client.post('/session?api_key=test-key').status_code, 401)
            self.assertEqual(self.client.post('/session', headers={'Authorization': 'Bearer test-key'}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
