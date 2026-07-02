from __future__ import annotations

import unittest
import importlib.util
import os
import sys
import types
from unittest.mock import patch

from tests._bot_loader import _install_runtime_dependency_stubs

_install_runtime_dependency_stubs()


def _install_flask_stub():
    flask = types.ModuleType("flask")

    class FakeFlask:
        def __init__(self, *_args, **_kwargs):
            self.secret_key = ""
            self.url_map = types.SimpleNamespace(iter_rules=lambda: [])

        def before_request(self, func=None, **_kwargs):
            return func if func else (lambda wrapped: wrapped)

        def after_request(self, func=None, **_kwargs):
            return func if func else (lambda wrapped: wrapped)

        def get(self, *_args, **_kwargs):
            return lambda wrapped: wrapped

        def post(self, *_args, **_kwargs):
            return lambda wrapped: wrapped

        def route(self, *_args, **_kwargs):
            return lambda wrapped: wrapped

        def response_class(self, *args, **kwargs):
            return (args, kwargs)

        def run(self, *_args, **_kwargs):
            return None

    class FakeResponse:
        pass

    flask.Flask = FakeFlask
    flask.Response = FakeResponse
    flask.g = types.SimpleNamespace()
    flask.jsonify = lambda *args, **kwargs: {"args": args, "kwargs": kwargs}
    flask.make_response = lambda value=None, *_args, **_kwargs: value
    flask.redirect = lambda value, *_args, **_kwargs: value
    flask.render_template_string = lambda *_args, **_kwargs: ""
    flask.request = types.SimpleNamespace(is_json=False, headers={}, cookies={}, args={}, form={}, json=None)
    flask.send_file = lambda *args, **kwargs: (args, kwargs)
    flask.stream_with_context = lambda value: value
    sys.modules.setdefault("flask", flask)


_install_flask_stub()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DASHBOARD_PATH = os.path.join(REPO_ROOT, "dashboard.py")
_SPEC = importlib.util.spec_from_file_location("dashboard_server_control_under_test", DASHBOARD_PATH)
dashboard = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = dashboard
_SPEC.loader.exec_module(dashboard)


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class DashboardServerControlTests(unittest.TestCase):
    def test_gameserver_action_posts_to_restart_and_stop_endpoints(self):
        calls = []

        def fake_post(url, headers=None, timeout=None):
            calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
            return FakeResponse(202, "accepted")

        config = {"nitrado_token": "token-123", "service_id": "svc-456"}

        with patch.object(dashboard.requests, "post", side_effect=fake_post):
            restart_ok, restart_message, restart_status = dashboard.dashboard_nitrado_gameserver_action(config, "restart")
            stop_ok, stop_message, stop_status = dashboard.dashboard_nitrado_gameserver_action(config, "stop")

        self.assertTrue(restart_ok)
        self.assertEqual(202, restart_status)
        self.assertIn("restart requested", restart_message)
        self.assertTrue(stop_ok)
        self.assertEqual(202, stop_status)
        self.assertIn("stop requested", stop_message)
        self.assertEqual(
            [
                "https://api.nitrado.net/services/svc-456/gameservers/restart",
                "https://api.nitrado.net/services/svc-456/gameservers/stop",
            ],
            [call["url"] for call in calls],
        )
        self.assertTrue(all(call["headers"].get("Authorization") == "Bearer token-123" for call in calls))
        self.assertTrue(all("Accept" not in call["headers"] for call in calls))
        self.assertTrue(all(call["timeout"] == 30 for call in calls))

    def test_gameserver_action_rejects_missing_credentials(self):
        ok, message, status = dashboard.dashboard_nitrado_gameserver_action({}, "restart")

        self.assertFalse(ok)
        self.assertIsNone(status)
        self.assertIn("token or service ID is missing", message)


if __name__ == "__main__":
    unittest.main()
