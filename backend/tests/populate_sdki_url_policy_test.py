from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import populate_sdki  # noqa: E402


APPROVED_URL = "https://api.anthropic.com/v1/messages"


class PopulateSdkiUrlPolicyTests(unittest.TestCase):
    def test_approved_https_provider_url_allowed(self):
        self.assertEqual(populate_sdki.validate_anthropic_api_url(APPROVED_URL), APPROVED_URL)

    def test_rejected_outbound_urls(self):
        rejected = {
            "http approved host": "http://api.anthropic.com/v1/messages",
            "file URL": "file:///etc/passwd",
            "ftp approved host": "ftp://api.anthropic.com/v1/messages",
            "data URL": "data:text/plain,test",
            "localhost": "https://localhost/v1/messages",
            "loopback": "https://127.0.0.1/v1/messages",
            "evil host": "https://evil.example/v1/messages",
            "credentials": "https://user:password@api.anthropic.com/v1/messages",
            "empty URL": "",
            "malformed URL": "https://[::1",
            "custom scheme": "anthropic://api.anthropic.com/v1/messages",
        }
        for label, url in rejected.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    populate_sdki.validate_anthropic_api_url(url)

    def test_invalid_configured_url_is_rejected_before_urlopen(self):
        with mock.patch.object(populate_sdki, "API_URL", "file:///etc/passwd"), \
             mock.patch.object(populate_sdki.request, "urlopen") as fake_urlopen:
            with self.assertRaises(ValueError):
                populate_sdki.anthropic_messages(
                    api_key="test-key",
                    model="mock-model",
                    system="system",
                    user="user",
                    max_tokens=100,
                    timeout=1,
                )
        fake_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()