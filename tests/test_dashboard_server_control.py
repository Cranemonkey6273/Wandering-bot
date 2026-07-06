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
    def test_manual_channel_id_accepts_channel_mentions_and_wins_over_dropdown(self):
        channel_id, manual, error = dashboard.dashboard_channel_id_from_payload({
            "channel_id": "111111111111111111",
            "manual_channel_id": "<#222222222222222222>",
        })

        self.assertEqual("222222222222222222", channel_id)
        self.assertTrue(manual)
        self.assertEqual("", error)

    def test_manual_channel_id_rejects_non_discord_ids(self):
        channel_id, manual, error = dashboard.dashboard_channel_id_from_payload({
            "manual_channel_id": "livonia-killfeed",
        })

        self.assertEqual("", channel_id)
        self.assertFalse(manual)
        self.assertIn("channel ID", error)

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

    def test_missing_scenario_uploader_marks_event_failed_instead_of_waiting(self):
        old_provider = dashboard.CUSTOM_STATE_PROVIDER
        event = {
            "id": 37,
            "created_by": "dashboard",
            "enabled": True,
            "upload_status": "waiting_for_bot_upload",
            "status": "Native CE XML upload requested",
        }
        try:
            dashboard.CUSTOM_STATE_PROVIDER = None
            reason = dashboard.dashboard_runtime_scenario_uploader_error()

            changed = dashboard.mark_dashboard_scenario_upload_worker_unavailable([event], reason, 37)
        finally:
            dashboard.CUSTOM_STATE_PROVIDER = old_provider

        self.assertTrue(changed)
        self.assertEqual("failed", event["upload_status"])
        self.assertEqual("Bot worker unavailable", event["status"])
        self.assertIn("embedded bot runtime provider", event["upload_error"])
        self.assertGreaterEqual(event["upload_attempts"], 1)

    def test_retry_upload_reset_clears_stale_uploaded_metadata(self):
        event = {
            "id": 37,
            "upload_status": "uploaded",
            "native_ce_uploaded_at": "2026-07-01T18:29:00+00:00",
            "native_ce_events_path": "/dayzxb_missions/dayzOffline.chernarusplus/db/events.xml",
            "native_ce_spawns_path": "/dayzxb_missions/dayzOffline.chernarusplus/cfgeventspawns.xml",
            "native_ce_mission_folder": "dayzOffline.chernarusplus",
            "native_ce_managed_event_names": ["StaticWanderingBot_37_vehicle_spawn"],
            "native_ce_restart_required": True,
            "upload_error": "old error",
        }

        dashboard.reset_dashboard_scenario_upload_state(event)

        self.assertEqual("waiting_for_bot_upload", event["upload_status"])
        self.assertEqual(0, event["upload_attempts"])
        self.assertNotIn("native_ce_uploaded_at", event)
        self.assertNotIn("native_ce_events_path", event)
        self.assertNotIn("native_ce_spawns_path", event)
        self.assertNotIn("native_ce_mission_folder", event)
        self.assertNotIn("native_ce_managed_event_names", event)
        self.assertNotIn("native_ce_restart_required", event)
        self.assertNotIn("upload_error", event)

    def test_schedule_rejects_provider_without_scenario_uploader(self):
        old_provider = dashboard.CUSTOM_STATE_PROVIDER
        try:
            dashboard.CUSTOM_STATE_PROVIDER = lambda: {}

            self.assertFalse(dashboard.schedule_runtime_scenario_xml_upload("guild-1", 37))
            self.assertIn("did not expose", dashboard.dashboard_runtime_scenario_uploader_error())
        finally:
            dashboard.CUSTOM_STATE_PROVIDER = old_provider

    def test_runtime_scenario_upload_passes_event_id_to_bot_uploader(self):
        old_provider = dashboard.CUSTOM_STATE_PROVIDER
        calls = []

        def fake_uploader(guild_id, event_id):
            calls.append((guild_id, event_id))
            return {"ok": False, "built": {}, "messages": ["blocked for test"]}

        try:
            dashboard.CUSTOM_STATE_PROVIDER = lambda: {"scenario_xml_uploader": fake_uploader}

            result = dashboard.run_runtime_scenario_xml_upload("guild-1", 37)
        finally:
            dashboard.CUSTOM_STATE_PROVIDER = old_provider

        self.assertEqual({"ok": False, "built": {}, "messages": ["blocked for test"]}, result)
        self.assertEqual([("guild-1", 37)], calls)


if __name__ == "__main__":
    unittest.main()
