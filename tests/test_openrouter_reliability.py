import io
import json
import os
import socket
import unittest
import urllib.error
from unittest import mock

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LEGACY_CHAT_DB_ENABLED"] = "false"
os.environ["USE_OPENROUTER_CHAT"] = "true"
os.environ["OPENROUTER_API_KEY"] = "test-key"

from ml import openrouter_responder


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class OpenRouterReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.analysis = {
            "language": "en",
            "intent": "general_query",
            "sentiment": "neutral",
            "topic": "general",
            "message_topic": "joke_fun",
            "response_style": "light_conversational",
        }

    def test_openrouter_timeout_returns_none_with_reason(self):
        with mock.patch.object(openrouter_responder, "URL_OPEN", side_effect=socket.timeout("timed out")):
            with mock.patch("ml.openrouter_responder.time.sleep", return_value=None):
                response = openrouter_responder.generate_openrouter_response("tell me a joke", self.analysis)
        self.assertIsNone(response)
        status = openrouter_responder.openrouter_status()
        self.assertEqual(status["last_fallback_reason"], "timeout")
        self.assertIn("timeout", status["last_error"].lower())

    def test_openrouter_empty_response_is_rejected(self):
        fake = _FakeResponse({"choices": [{"message": {"content": "   "}}]})
        with mock.patch.object(openrouter_responder, "URL_OPEN", return_value=fake):
            response = openrouter_responder.generate_openrouter_response("hello", self.analysis)
        self.assertIsNone(response)
        status = openrouter_responder.openrouter_status()
        self.assertEqual(status["last_fallback_reason"], "malformed_or_empty_response")

    def test_openrouter_rate_limit_sets_http_reason(self):
        error = urllib.error.HTTPError(
            openrouter_responder._LAST_REQUEST_URL,
            429,
            "Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"rate limit"}'),
        )
        with mock.patch.object(openrouter_responder, "URL_OPEN", side_effect=error):
            with mock.patch("ml.openrouter_responder.time.sleep", return_value=None):
                response = openrouter_responder.generate_openrouter_response("hi", self.analysis)
        self.assertIsNone(response)
        status = openrouter_responder.openrouter_status()
        self.assertEqual(status["last_status_code"], 429)
        self.assertEqual(status["last_fallback_reason"], "http_429")

    def test_openrouter_recovers_after_retry(self):
        calls = {"count": 0}

        def _side_effect(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise socket.timeout("timed out")
            return _FakeResponse({"choices": [{"message": {"content": "Here is a joke for you."}}]})

        with mock.patch.object(openrouter_responder, "URL_OPEN", side_effect=_side_effect):
            with mock.patch("ml.openrouter_responder.time.sleep", return_value=None):
                response = openrouter_responder.generate_openrouter_response("tell me a joke", self.analysis)
        self.assertEqual(response, "Here is a joke for you.")
        status = openrouter_responder.openrouter_status()
        self.assertEqual(status["last_status_code"], 200)


if __name__ == "__main__":
    unittest.main()
