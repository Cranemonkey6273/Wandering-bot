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
    def test_android_fingerprint_normalizer_accepts_plain_and_coloned_sha256(self):
        raw = "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
        expected = (
            "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:"
            "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"
        )

        self.assertEqual(expected, dashboard.normalize_android_sha256_fingerprint(raw))
        self.assertEqual(expected, dashboard.normalize_android_sha256_fingerprint(expected))
        self.assertEqual("", dashboard.normalize_android_sha256_fingerprint("not-a-fingerprint"))

    def test_android_assetlinks_statement_uses_app_id_and_fingerprints(self):
        fingerprint = (
            "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:"
            "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"
        )

        statements = dashboard.android_assetlinks_statements([fingerprint])

        self.assertEqual(1, len(statements))
        statement = statements[0]
        self.assertEqual(["delegate_permission/common.handle_all_urls"], statement["relation"])
        self.assertEqual("android_app", statement["target"]["namespace"])
        self.assertEqual("com.dayzwanderingbot.app", statement["target"]["package_name"])
        self.assertEqual([fingerprint], statement["target"]["sha256_cert_fingerprints"])

    def test_dashboard_feature_allowed_uses_tier_when_features_missing(self):
        plans = list(dashboard.default_billing_plan_map().values())
        config = {"dashboard": {"enabled": True, "tier": "dashboard_ultimate", "plan_status": "lifetime"}}

        with patch.object(dashboard, "dashboard_billing_plans", return_value=plans):
            self.assertTrue(dashboard.dashboard_feature_allowed(config, "pve_quests"))
            self.assertTrue(dashboard.dashboard_feature_allowed(config, "xml_workshop"))
            self.assertTrue(dashboard.dashboard_feature_allowed(config, "ai_agent"))

    def test_dashboard_feature_allowed_uses_plan_for_missing_feature_keys(self):
        plans = list(dashboard.default_billing_plan_map().values())
        config = {
            "dashboard": {
                "enabled": True,
                "tier": "dashboard",
                "plan_status": "subscription",
                "features": {"leaderboards": True},
            }
        }

        with patch.object(dashboard, "dashboard_billing_plans", return_value=plans):
            self.assertTrue(dashboard.dashboard_feature_allowed(config, "pve_quests"))
            self.assertTrue(dashboard.dashboard_feature_allowed(config, "shop"))

    def test_dashboard_feature_allowed_preserves_manual_denies(self):
        plans = list(dashboard.default_billing_plan_map().values())
        config = {
            "dashboard": {
                "enabled": True,
                "tier": "dashboard_ultimate",
                "plan_status": "lifetime",
                "features": {"pve_quests": False},
            }
        }

        with patch.object(dashboard, "dashboard_billing_plans", return_value=plans):
            self.assertFalse(dashboard.dashboard_feature_allowed(config, "pve_quests"))
            self.assertTrue(dashboard.dashboard_feature_allowed(config, "xml_workshop"))

    def test_owner_tier_resolves_to_full_feature_access(self):
        plans = list(dashboard.default_billing_plan_map().values())
        config = {"dashboard": {"enabled": True, "tier": "owner", "plan_status": "lifetime"}}

        with patch.object(dashboard, "dashboard_billing_plans", return_value=plans):
            self.assertTrue(dashboard.dashboard_feature_allowed(config, "pve_quests"))
            self.assertTrue(dashboard.dashboard_feature_allowed(config, "ai_agent"))

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

    def test_live_feed_selection_accepts_repeated_form_values(self):
        selected = dashboard.dashboard_live_feed_selected_keys(["building", "placed_feed", "bad-key"], [])

        self.assertEqual(["building", "placed_feed"], selected)

    def test_live_feed_rows_filter_by_server_selected_keys(self):
        store = {
            "guild-1": [
                {"id": "one", "feed_key": "building", "event_type": "build", "player": "Builder", "summary": "built wall", "occurred_at": "2026-07-06T10:00:00+00:00"},
                {"id": "two", "feed_key": "killfeed", "event_type": "kill", "player": "Killer", "summary": "kill event", "occurred_at": "2026-07-06T10:01:00+00:00"},
                {"id": "three", "feed_key": "placed_feed", "event_type": "placed", "player": "Builder", "summary": "placed tent", "occurred_at": "2026-07-06T10:02:00+00:00"},
            ],
            "guild-2": [
                {"id": "other", "feed_key": "building", "event_type": "build", "player": "Other", "summary": "other server", "occurred_at": "2026-07-06T10:03:00+00:00"},
            ],
        }
        config = {"dashboard_live_feed_keys": ["building", "placed_feed"]}

        rows = dashboard.dashboard_live_feed_rows(config, store, "guild-1", limit=10)

        self.assertEqual(["placed_feed", "building"], [row["feed_key"] for row in rows])
        self.assertEqual(["placed tent", "built wall"], [row["summary"] for row in rows])

    def test_server_profile_rows_use_profile_runtime_ids(self):
        config = {
            "nitrado_token": "shared-token",
            "server_profiles": {
                "cherno": {
                    "profile_name": "Cherno",
                    "service_id": "111",
                    "server_map": "chernarus",
                    "channels": {"building": "123456789012345678"},
                    "dashboard_live_feed_keys": ["building"],
                },
                "livo": {
                    "profile_name": "Livo",
                    "service_id": "222",
                    "server_map": "livonia",
                    "channels": {"placed_feed": "223456789012345678"},
                    "dashboard_live_feed_keys": ["placed_feed"],
                },
            },
        }
        store = {
            "guild-1:cherno": [
                {"id": "one", "feed_key": "building", "event_type": "build", "player": "Builder", "summary": "cherno build", "occurred_at": "2026-07-06T10:00:00+00:00"},
            ],
            "guild-1:livo": [
                {"id": "two", "feed_key": "placed_feed", "event_type": "placed", "player": "Builder", "summary": "livo placed", "occurred_at": "2026-07-06T10:01:00+00:00"},
            ],
        }

        with patch.object(dashboard, "discord_guild_channels", return_value=[]):
            rows = dashboard.dashboard_server_profile_rows(config, "guild-1", store, True)

        self.assertEqual(["cherno", "livo"], [row["id"] for row in rows])
        self.assertEqual(["guild-1:cherno", "guild-1:livo"], [row["runtime_id"] for row in rows])
        self.assertEqual(["cherno build"], [row["summary"] for row in rows[0]["dashboard_live_feed_rows"]])
        self.assertEqual(["livo placed"], [row["summary"] for row in rows[1]["dashboard_live_feed_rows"]])
        self.assertEqual("shared", rows[0]["token_status"])
        self.assertEqual(1, rows[0]["configured_channel_count"])
        self.assertEqual(1, rows[0]["available_channel_count"])

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
