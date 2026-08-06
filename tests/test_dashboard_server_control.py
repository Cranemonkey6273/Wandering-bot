from __future__ import annotations

import unittest
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import zipfile
import xml.etree.ElementTree as ET
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
    def test_dayz_profile_id_rename_preserves_profile_and_rewrites_references(self):
        configs = {
            "guild-1": {
                "server_profiles": {
                    "cherno": {"server_map": "chernarus"},
                    "livo": {
                        "profile_name": "Wandering Around Livo",
                        "server_map": "livonia",
                        "service_id": "1234567",
                        "nitrado_token": "secret-token",
                        "channels": {"killfeed": "9988"},
                        "scenario_events": [{"id": 8, "server_profile_id": "livo"}],
                    },
                },
                "dayz_scenario_profile_id": "livo",
            }
        }
        payload = {
            "guild_id": "guild-1",
            "action": "rename",
            "profile_id": "livo",
            "new_profile_id": "sakhal",
            "profile_name": "Wandering Around Sakhal",
            "server_map": "sakhal",
        }

        with (
            patch.object(dashboard, "require_admin", return_value=(payload, None)),
            patch.object(dashboard, "current_auth", return_value={"kind": "guild"}),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "write_json_file"),
            patch.object(dashboard, "write_split_guild_configs"),
            patch.object(
                dashboard,
                "dashboard_migrate_server_profile_runtime_state",
                return_value={"ok": True, "warnings": [], "migrated_files": ["player_audit.json"]},
            ) as migrate,
            patch.object(dashboard, "sync_runtime_store"),
            patch.object(dashboard, "dashboard_api_response", side_effect=lambda _raw, data, *_args: data),
        ):
            response = dashboard.api_dayz_server_profile()

        profiles = configs["guild-1"]["server_profiles"]
        self.assertNotIn("livo", profiles)
        self.assertIn("sakhal", profiles)
        sakhal = profiles["sakhal"]
        self.assertEqual("Wandering Around Sakhal", sakhal["profile_name"])
        self.assertEqual("sakhal", sakhal["server_map"])
        self.assertEqual("1234567", sakhal["service_id"])
        self.assertEqual("secret-token", sakhal["nitrado_token"])
        self.assertEqual("9988", sakhal["channels"]["killfeed"])
        self.assertEqual("sakhal", sakhal["scenario_events"][0]["server_profile_id"])
        self.assertEqual("sakhal", configs["guild-1"]["dayz_scenario_profile_id"])
        self.assertEqual("guild-1:sakhal", response["runtime_id"])
        migrate.assert_called_once_with("guild-1", "livo", "sakhal")

    def test_profile_runtime_migration_moves_files_and_live_dedupe_state(self):
        original_data_root = dashboard.DATA_ROOT
        original_provider = dashboard.CUSTOM_STATE_PROVIDER
        with tempfile.TemporaryDirectory() as temp_root:
            try:
                dashboard.DATA_ROOT = temp_root
                dashboard.write_json_file(
                    "dashboard_live_feeds.json",
                    {"guild-1:livo": [{"summary": "connected"}]},
                )
                dashboard.write_json_file(
                    "processed_adm_events.json",
                    {"guild-1:livo": ["fingerprint-a"]},
                )
                dashboard.write_json_file(
                    "delivery_queue.json",
                    [{"guild_id": "guild-1:livo", "server_profile_id": "livo"}],
                )
                live_dedupe = {"guild-1:livo": {"fingerprint-a": None}}
                live_delivery = [{"guild_id": "guild-1:livo", "server_profile_id": "livo"}]
                dashboard.CUSTOM_STATE_PROVIDER = lambda: {
                    "server_profile_runtime_state": {
                        "processed_adm_events": live_dedupe,
                        "delivery_queue": live_delivery,
                    }
                }

                result = dashboard.dashboard_migrate_server_profile_runtime_state("guild-1", "livo", "sakhal")

                feeds = dashboard.read_json_file("dashboard_live_feeds.json", {})
                dedupe = dashboard.read_json_file("processed_adm_events.json", {})
                delivery = dashboard.read_json_file("delivery_queue.json", [])
                self.assertNotIn("guild-1:livo", feeds)
                self.assertEqual("connected", feeds["guild-1:sakhal"][0]["summary"])
                self.assertEqual(["fingerprint-a"], dedupe["guild-1:sakhal"])
                self.assertEqual("guild-1:sakhal", delivery[0]["guild_id"])
                self.assertEqual("sakhal", delivery[0]["server_profile_id"])
                self.assertIn("guild-1:sakhal", live_dedupe)
                self.assertNotIn("guild-1:livo", live_dedupe)
                self.assertEqual("guild-1:sakhal", live_delivery[0]["guild_id"])
                self.assertEqual("sakhal", live_delivery[0]["server_profile_id"])
                self.assertFalse(result["warnings"])
            finally:
                dashboard.DATA_ROOT = original_data_root
                dashboard.CUSTOM_STATE_PROVIDER = original_provider

    def test_profile_rename_control_is_collapsed_into_profile_actions(self):
        template = dashboard.PAGE_TEMPLATE
        self.assertIn("Rename profile ID", template)
        self.assertIn('name="action" value="rename"', template)
        self.assertIn('name="new_profile_id"', template)
        self.assertIn("Rename and migrate", template)

    def test_player_loadout_export_uses_official_dayz_spawn_gear_structure(self):
        payload = dashboard.build_player_loadout_json({
            "name": "QA Survivor",
            "items": [
                {"item": "M4A1", "quantity": 2, "quantity_percent": -1, "slot": "Left Shoulder"},
                {"item": "Mag_STANAG_30Rnd", "quantity": 2, "quantity_percent": 100, "attachment_for": "M4A1"},
                {"item": "M4_MPBttstck", "quantity": 1, "quantity_percent": -1, "attachment_for": "M4A1"},
                {"item": "BandageDressing", "quantity": 3, "quantity_percent": -1, "slot": ""},
            ],
        })

        shoulder = next(row for row in payload["attachmentSlotItemSets"] if row["slotName"] == "shoulderL")
        weapon = shoulder["discreteItemSets"][0]
        self.assertEqual("M4A1", weapon["itemType"])
        self.assertEqual(1, weapon["spawnWeight"])
        self.assertNotIn("attachmentFor", weapon)
        self.assertEqual(
            ["Mag_STANAG_30Rnd", "M4_MPBttstck"],
            [row["itemType"] for row in weapon["complexChildrenTypes"]],
        )
        self.assertTrue(all("spawnWeight" not in row for row in weapon["complexChildrenTypes"]))

        cargo = payload["discreteUnsortedItemSets"][0]
        self.assertEqual("QA Survivor Cargo", cargo["name"])
        self.assertEqual(
            ["BandageDressing", "BandageDressing", "BandageDressing", "M4A1", "Mag_STANAG_30Rnd"],
            [row["itemType"] for row in cargo["complexChildrenTypes"]],
        )

    def test_xml_workshop_legacy_state_only_falls_back_to_matching_map_profile(self):
        base_config = {
            "server_map": "chernarus",
            "xml_workshop": {"settings": {"notes": "Cherno-only legacy draft"}},
        }
        cherno_profile = {"server_map": "chernarus"}
        livonia_profile = {"server_map": "livonia"}

        self.assertEqual(
            "Cherno-only legacy draft",
            dashboard.dashboard_xml_workshop_for_profile(base_config, cherno_profile, "cherno")["settings"]["notes"],
        )
        self.assertEqual({}, dashboard.dashboard_xml_workshop_for_profile(base_config, livonia_profile, "livo"))

        copied = dashboard.dashboard_prepare_xml_workshop_for_profile(base_config, cherno_profile, "cherno")
        isolated = dashboard.dashboard_prepare_xml_workshop_for_profile(base_config, livonia_profile, "livo")

        self.assertEqual("Cherno-only legacy draft", copied["settings"]["notes"])
        self.assertEqual({}, isolated)
        self.assertIsNot(base_config["xml_workshop"], cherno_profile["xml_workshop"])

    def test_xml_workshop_save_writes_only_the_selected_profile(self):
        configs = {
            "guild-1": {
                "server_map": "chernarus",
                "xml_workshop": {"settings": {"notes": "Cherno legacy draft"}},
                "server_profiles": {
                    "cherno": {"server_map": "chernarus"},
                    "livo": {"server_map": "livonia"},
                },
            }
        }
        payload = {
            "guild_id": "guild-1",
            "server_profile_id": "livo",
            "recipe_kind": "settings",
            "default_damage": "pristine",
            "quantity_mode": "vanilla",
            "notes": "Livonia-only rules",
        }

        with (
            patch.object(dashboard, "require_admin", return_value=(payload, None)),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "save_store"),
            patch.object(dashboard, "sync_runtime_store"),
            patch.object(dashboard, "wants_json_response", return_value=True),
        ):
            dashboard.api_xml_workshop()

        base_workshop = configs["guild-1"]["xml_workshop"]
        livonia_workshop = configs["guild-1"]["server_profiles"]["livo"]["xml_workshop"]
        self.assertEqual("Cherno legacy draft", base_workshop["settings"]["notes"])
        self.assertEqual("Livonia-only rules", livonia_workshop["settings"]["notes"])
        self.assertNotIn("xml_workshop", configs["guild-1"]["server_profiles"]["cherno"])

    def test_player_loadout_recipe_is_saved_and_removed_only_on_selected_profile(self):
        configs = {
            "guild-1": {
                "server_map": "chernarus",
                "xml_workshop": {"recipes": {"players": [{"id": "cherno_loadout", "name": "Cherno loadout"}]}},
                "server_profiles": {
                    "cherno": {"server_map": "chernarus"},
                    "livo": {"server_map": "livonia"},
                },
            }
        }
        save_payload = {
            "guild_id": "guild-1",
            "server_profile_id": "livo",
            "recipe_kind": "player_loadout",
            "recipe_name": "Livonia QA Loadout",
            "custom_path": "./custom/Livonia_QA_Loadout.json",
            "items": "BallisticHelmet, 1, -1, pristine, Head",
        }

        with (
            patch.object(dashboard, "require_admin", return_value=(save_payload, None)),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "save_store"),
            patch.object(dashboard, "sync_runtime_store"),
            patch.object(dashboard, "wants_json_response", return_value=True),
        ):
            dashboard.api_xml_workshop()

        livo_workshop = configs["guild-1"]["server_profiles"]["livo"]["xml_workshop"]
        livo_recipes = livo_workshop["recipes"]["players"]
        self.assertEqual(["Livonia QA Loadout"], [row["name"] for row in livo_recipes])
        self.assertEqual("BallisticHelmet", livo_recipes[0]["items"][0]["item"])
        self.assertEqual(["Cherno loadout"], [row["name"] for row in configs["guild-1"]["xml_workshop"]["recipes"]["players"]])

        delete_payload = {
            "guild_id": "guild-1",
            "server_profile_id": "livo",
            "recipe_kind": "player_loadout",
            "recipe_id": "livonia_qa_loadout",
            "action": "delete",
        }
        with (
            patch.object(dashboard, "require_admin", return_value=(delete_payload, None)),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "save_store"),
            patch.object(dashboard, "sync_runtime_store"),
            patch.object(dashboard, "wants_json_response", return_value=True),
        ):
            dashboard.api_xml_workshop_recipe_action()

        self.assertEqual([], livo_workshop["recipes"]["players"])
        self.assertEqual(["Cherno loadout"], [row["name"] for row in configs["guild-1"]["xml_workshop"]["recipes"]["players"]])

    def test_heatmap_summary_reads_the_profile_runtime_key(self):
        heatmap = {
            "guild-1": {"NWAF": 99},
            "guild-1:livo": {"Nadbor": 4, "__modes__": {"pvp": {"Nadbor": 4}}},
        }

        summary = dashboard.heatmap_summary(heatmap, "guild-1:livo")

        self.assertEqual(4, summary["total"])
        self.assertEqual("Nadbor", summary["modes"]["pvp"][0]["name"])
        self.assertNotIn("NWAF", [row["name"] for row in summary["modes"]["pvp"]])

    def test_profile_selection_is_preserved_for_xml_and_heatmap_navigation(self):
        template = dashboard.PAGE_TEMPLATE

        self.assertIn('/admin?section=heatmaps{{ server_qs }}{{ profile_qs }}', template)
        self.assertIn('/admin?section=xml-workshop{{ server_qs }}{{ profile_qs }}', template)
        self.assertIn('name="server_profile_id" value="{{ selected_dayz_profile_id if selected_dayz_profile else \'\' }}"', template)
        self.assertIn('selected_audit_total = selected_dayz_profile.player_audit_total', template)

    def test_legacy_xml_and_loadout_redirects_keep_the_selected_profile(self):
        args = {"section": "dayz-converter", "guild_id": "guild-1", "server_profile_id": "livo", "token": "safe-token"}
        redirect_path = dashboard.dashboard_xml_workshop_redirect_path("admin", "loot", args, "xml-workshop")
        loadout_path = dashboard.dashboard_xml_workshop_redirect_path("admin", "player-loadout", args, "player-loadout-builder")

        self.assertIn("server_profile_id=livo", redirect_path)
        self.assertIn("guild_id=guild-1", redirect_path)
        self.assertIn("xml_tool=loot", redirect_path)
        self.assertTrue(redirect_path.endswith("#xml-workshop"))
        self.assertIn("xml_tool=player-loadout", loadout_path)
        self.assertTrue(loadout_path.endswith("#player-loadout-builder"))

    def test_live_server_actions_require_selected_server_confirmation(self):
        payload = {"guild_id": "guild-1", "server_action": "restart"}
        configs = {"guild-1": {"channels": {}}}

        with (
            patch.object(dashboard, "require_admin", return_value=(payload, None)),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "dashboard_nitrado_gameserver_action") as action,
        ):
            response, status = dashboard.api_server_control()

        self.assertEqual(400, status)
        self.assertIn("confirmation", response["args"][0]["error"].lower())
        action.assert_not_called()
        self.assertIn('name="server_action_confirmed" value="true" required', dashboard.PAGE_TEMPLATE)

    def test_live_event_queue_requires_selected_server_confirmation(self):
        payload = {"guild_id": "guild-1", "event_type": "airdrop"}

        with patch.object(dashboard, "require_admin", return_value=(payload, None)):
            response, status = dashboard.api_scenario_event()

        self.assertEqual(400, status)
        self.assertIn("confirmation", response["args"][0]["error"].lower())
        self.assertIn('name="confirmed_profile" value="true" required', dashboard.PAGE_TEMPLATE)

    def test_mummy_preset_queues_custom_mummy_castle_horde_range(self):
        configs = {"guild-1": {"channels": {}}}
        profile = {"server_map": "chernarus", "scenario_events": []}
        payload = {
            "guild_id": "guild-1",
            "server_profile_id": "cherno",
            "confirmed_profile": True,
            "event_type": "zombie_horde",
            "spawn_preset": "mummy_zombie",
            # These are what an unrefreshed form may still carry. The preset
            # must retain its safe Mummy defaults until the UI JavaScript has
            # replaced them.
            "count": "1",
            "zombie_min_count": "1",
            "zombie_max_count": "1",
            "radius": "85",
            "permanent": "true",
            "batch_locations": "Altar Castle, 1420, 9300\nZub Castle, 6535, 5625\nDevil's Castle, 6895, 11430\nBlack Castle, 10220, 12030",
        }

        with (
            patch.object(dashboard, "require_admin", return_value=(payload, None)),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "dashboard_target_config_for_profile", return_value=(profile, "guild-1:cherno", "")),
            patch.object(dashboard, "save_store"),
            patch.object(dashboard, "sync_runtime_store"),
            patch.object(dashboard, "dashboard_runtime_scenario_uploader_error", return_value=""),
            patch.object(dashboard, "schedule_runtime_scenario_xml_upload", return_value=True),
            patch.object(dashboard, "wants_json_response", return_value=True),
        ):
            response = dashboard.api_scenario_event()

        body = response["args"][0]
        self.assertTrue(body["ok"])
        self.assertEqual(4, body["created_count"])
        self.assertEqual(4, len(profile["scenario_events"]))
        self.assertEqual(
            {(1420, 9300), (6535, 5625), (6895, 11430), (10220, 12030)},
            {(event["x"], event["z"]) for event in profile["scenario_events"]},
        )
        self.assertTrue(all(event["class_name"] == "ZmbM_Mummy" for event in profile["scenario_events"]))
        self.assertTrue(all(event["preset"] == "mummy_zombie" for event in profile["scenario_events"]))
        self.assertTrue(all(event["count"] == 7 for event in profile["scenario_events"]))
        self.assertTrue(all(event["zombie_min_count"] == 3 and event["zombie_max_count"] == 10 for event in profile["scenario_events"]))
        self.assertTrue(all(event["permanent"] for event in profile["scenario_events"]))

    def test_native_event_delete_starts_guarded_cleanup_immediately(self):
        configs = {"guild-1": {}}
        profile = {"scenario_events": [{"id": 37, "created_by": "dashboard", "native_ce_uploaded_at": "2026-08-03T10:00:00+00:00"}]}
        payload = {"guild_id": "guild-1", "server_profile_id": "livo", "event_id": "37", "action": "delete"}

        with (
            patch.object(dashboard, "require_admin", return_value=(payload, None)),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "dashboard_target_config_for_profile", return_value=(profile, "guild-1:livo", "")),
            patch.object(dashboard, "mark_scenario_event_deleted"),
            patch.object(dashboard, "scenario_event_has_confirmed_native_upload", return_value=True),
            patch.object(dashboard, "dashboard_runtime_scenario_uploader_error", return_value=""),
            patch.object(dashboard, "schedule_runtime_scenario_xml_upload", return_value=True) as schedule,
            patch.object(dashboard, "save_store"),
            patch.object(dashboard, "sync_runtime_store"),
            patch.object(dashboard, "wants_json_response", return_value=True),
        ):
            response = dashboard.api_scenario_event_action()

        self.assertEqual([], profile["scenario_events"])
        self.assertTrue(profile["scenario_events_cleanup_pending"])
        schedule.assert_called_once_with("guild-1:livo", 37, removed=True)
        body = response["args"][0]
        self.assertTrue(body["cleanup_queued"])
        self.assertTrue(body["cleanup_started"])

    def test_uploaded_event_retry_is_a_noop_and_keeps_confirmed_metadata(self):
        configs = {"guild-1": {}}
        event = {
            "id": 36,
            "created_by": "dashboard",
            "upload_status": "uploaded",
            "status": "XML uploaded to Nitrado; restart once",
            "native_ce_uploaded_at": "2026-08-04T15:54:00+00:00",
            "native_ce_events_path": "/mission/db/events.xml",
        }
        profile = {"scenario_events": [event]}
        payload = {"guild_id": "guild-1", "server_profile_id": "cherno", "event_id": "36", "action": "upload"}

        with (
            patch.object(dashboard, "require_admin", return_value=(payload, None)),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "dashboard_target_config_for_profile", return_value=(profile, "guild-1:cherno", "")),
            patch.object(dashboard, "schedule_runtime_scenario_xml_upload") as schedule,
            patch.object(dashboard, "save_store") as save,
            patch.object(dashboard, "sync_runtime_store") as sync,
            patch.object(dashboard, "wants_json_response", return_value=True),
        ):
            response = dashboard.api_scenario_event_action()

        body = response["args"][0]
        self.assertTrue(body["ok"])
        self.assertTrue(body["already_uploaded"])
        self.assertFalse(body["upload_started"])
        self.assertIn("RPT tracker", body["note"])
        self.assertEqual("uploaded", event["upload_status"])
        self.assertEqual("2026-08-04T15:54:00+00:00", event["native_ce_uploaded_at"])
        schedule.assert_not_called()
        save.assert_not_called()
        sync.assert_not_called()

    def test_targeted_upload_failure_does_not_poison_unrelated_dashboard_events(self):
        configs = {"guild-1": {}}
        target = {
            "id": 34,
            "created_by": "dashboard",
            "upload_status": "waiting_for_bot_upload",
            "status": "Retry queued",
        }
        unrelated = {
            "id": 32,
            "created_by": "dashboard",
            "upload_status": "waiting_for_bot_upload",
            "status": "Waiting for bot upload",
        }
        profile = {"scenario_events": [unrelated, target]}
        result = {
            "ok": False,
            "built": {},
            "messages": [
                "Dashboard event 34 is not pending upload (status: XML uploaded to Nitrado; upload_status: uploaded)."
            ],
        }

        with (
            patch.object(dashboard, "run_runtime_scenario_xml_upload", return_value=result),
            patch.object(dashboard, "load_store", return_value=configs),
            patch.object(dashboard, "dashboard_target_config_for_runtime", return_value=(profile, "guild-1:cherno", "")),
            patch.object(dashboard, "save_store"),
            patch.object(dashboard, "sync_runtime_store"),
        ):
            dashboard.apply_runtime_scenario_xml_upload("guild-1:cherno", 34)

        self.assertEqual("failed", target["upload_status"])
        self.assertIn("Dashboard event 34", target["upload_error"])
        self.assertEqual("waiting_for_bot_upload", unrelated["upload_status"])
        self.assertEqual("Waiting for bot upload", unrelated["status"])

    def test_legacy_zones_are_copied_into_matching_server_profile_once(self):
        base_config = {
            "server_map": "chernarus",
            "radar_zones": [
                {"id": "nwaf", "name": "North West Airfield", "x": 7500, "z": 7500},
            ],
        }
        profile_config = {"server_map": "chernarus"}

        copied = dashboard.dashboard_copy_legacy_zones_to_profile_if_needed(
            base_config,
            profile_config,
            "chernarus",
        )
        copied_again = dashboard.dashboard_copy_legacy_zones_to_profile_if_needed(
            base_config,
            profile_config,
            "chernarus",
        )

        self.assertTrue(copied)
        self.assertFalse(copied_again)
        self.assertEqual("North West Airfield", profile_config["radar_zones"][0]["name"])
        self.assertEqual("North West Airfield", base_config["radar_zones"][0]["name"])
        self.assertIn("legacy_zones_restored_at", profile_config)

    def test_legacy_zones_are_not_copied_to_different_map_profile(self):
        base_config = {
            "server_map": "chernarus",
            "radar_zones": [
                {"id": "nwaf", "name": "North West Airfield", "x": 7500, "z": 7500},
            ],
        }
        profile_config = {"server_map": "livonia"}

        copied = dashboard.dashboard_copy_legacy_zones_to_profile_if_needed(
            base_config,
            profile_config,
            "livonia",
        )

        self.assertFalse(copied)
        self.assertNotIn("radar_zones", profile_config)

    def test_mobile_app_welcome_explains_install_setup_and_password_reset(self):
        template = dashboard.APP_WELCOME_TEMPLATE

        self.assertIn("Add Wandering Bot to Discord", template)
        self.assertIn("/setup", template)
        self.assertIn("Nitrado service ID", template)
        self.assertIn("/admstatus", template)
        self.assertIn('href="/setup-guide"', template)
        self.assertIn('href="/setup-guide/download"', template)
        self.assertIn("/dashboardcredentials reset:true", template)
        self.assertIn('name="return_to"', template)
        self.assertIn('name="app_source"', template)
        self.assertIn("color-scheme: light", template)
        self.assertIn("--bg: #eef3ef", template)
        self.assertNotIn("color-scheme: dark", template)
        self.assertNotIn("existing password can be displayed", template.lower())

    def test_signed_out_mobile_app_uses_app_welcome_instead_of_website_login(self):
        with (
            patch.object(dashboard, "current_auth", return_value=None),
            patch.object(dashboard, "current_agent_account_auth", return_value=None),
            patch.object(dashboard, "mobile_app_welcome", return_value="app-welcome") as welcome,
        ):
            response = dashboard.mobile_app()

        self.assertEqual("app-welcome", response)
        welcome.assert_called_once_with()

    def test_safe_dashboard_return_allows_app_but_rejects_external_targets(self):
        self.assertEqual("/app", dashboard.safe_dashboard_return("/app", "/login"))
        self.assertEqual(
            "/app?source=native_android",
            dashboard.safe_dashboard_return("/app?source=native_android", "/login"),
        )
        self.assertEqual("/login", dashboard.safe_dashboard_return("https://example.com/app", "/login"))
        self.assertEqual("/login", dashboard.safe_dashboard_return("/application", "/login"))

    def test_mobile_app_view_normalizer_limits_routes_to_finished_views(self):
        self.assertEqual("home", dashboard.normalize_mobile_app_view(None))
        self.assertEqual("feeds", dashboard.normalize_mobile_app_view(" FEEDS "))
        self.assertEqual("events", dashboard.normalize_mobile_app_view("events"))
        self.assertEqual("economy", dashboard.normalize_mobile_app_view("economy"))
        self.assertEqual("control", dashboard.normalize_mobile_app_view("control"))
        self.assertEqual("help", dashboard.normalize_mobile_app_view("help"))
        self.assertEqual("home", dashboard.normalize_mobile_app_view("xml-workshop"))

    def test_mobile_app_template_is_a_focused_mobile_command_hub(self):
        template = dashboard.APP_DASHBOARD_TEMPLATE

        for label in ("Home", "Feeds", "Events", "Economy", "Control", "Guides"):
            self.assertIn(f">{label}</a>", template)
        self.assertIn("DayZ field guide", template)
        self.assertIn("Airdrop builder", template)
        self.assertIn("Live from latest RPT", template)
        self.assertIn('action="/api/admin/scenario-event"', template)
        self.assertIn('action="/api/admin/scenario-event-action"', template)
        self.assertIn('name="server_profile_id"', template)
        self.assertIn('name="saved_location"', template)
        self.assertIn('name="spawn_preset"', template)
        self.assertIn("types.xml", template)
        self.assertIn("events.xml", template)
        self.assertIn("event name</code> must be identical", template)
        self.assertIn("cfgspawnabletypes.xml", template)
        self.assertIn("playerRestrictedAreaFiles", template)
        self.assertIn("Loot in buildings is a chain", template)
        self.assertIn("Common XML and JSON mistakes", template)
        self.assertIn("Build anywhere: learn the settings", template)
        self.assertIn("Stamina: boosted or unlimited", template)
        preset_titles = {str(item.get("title") or "") for item in dashboard.DAYZ_PRESET_FILES}
        self.assertIn("Complete pristine vehicles", preset_titles)
        self.assertIn("Builder trucks with supplies", preset_titles)
        self.assertIn("{% if group.name != 'Gameplay' %}", template)
        self.assertIn("cannot set the exact fuel-tank or radiator-water level", template)
        self.assertIn("mapgroupproto", template)
        self.assertIn("mapgrouppos", template)
        self.assertIn('name="vehicle_reset_schedule_enabled"', template)
        self.assertIn("Quick app walkthrough", template)
        self.assertIn('data-tour-open', template)
        self.assertIn('data-app-tour', template)
        self.assertIn('data-app-review-form', template)
        self.assertIn('action="/api/reviews"', template)
        self.assertIn("Rate on Google Play", template)
        self.assertIn("How the app protects server access", template)
        self.assertIn("Nitrado tokens, Discord credentials, billing secrets", template)
        self.assertNotIn('href="{{ dashboard_path }}', template)
        self.assertNotIn('/admin?section=', template)
        self.assertNotIn("Player Loadout", template)
        self.assertNotIn("XML Workshop", template)

    def test_android_play_store_url_tracks_configured_package_id(self):
        self.assertTrue(dashboard.ANDROID_PLAY_STORE_URL.startswith("https://"))
        self.assertIn("play.google.com", dashboard.ANDROID_PLAY_STORE_URL)

    def test_vehicle_presets_are_map_specific_complete_and_preserve_unrelated_records(self):
        for map_key in ("chernarus", "livonia", "sakhal"):
            result = dashboard.build_dayz_preset_file(map_key, "spawnabletypes_complete_vehicles")
            root = ET.fromstring(result["content"])
            self.assertEqual("cfgspawnabletypes.xml", result["target_path"])
            self.assertIsNotNone(root.find("./type[@name='Barrel_Blue']/hoarder"))
            vehicle = root.find("./type[@name='OffroadHatchback']")
            self.assertIsNotNone(vehicle)
            self.assertEqual("0.0", vehicle.find("damage").get("min"))
            self.assertEqual("0.0", vehicle.find("damage").get("max"))
            for attachments in vehicle.findall("attachments"):
                self.assertEqual("1.00", attachments.get("chance"))
                for item in attachments.findall("item"):
                    self.assertEqual("1.00", item.get("chance"))

    def test_zone_radius_limits_cover_each_supported_map(self):
        self.assertEqual(12000, dashboard.zone_radius_limit_for_map("chernarus"))
        self.assertEqual(10000, dashboard.zone_radius_limit_for_map("livonia"))
        self.assertEqual(12000, dashboard.zone_radius_limit_for_map("sakhal"))

    def test_builder_truck_preset_adds_supplies_only_to_covered_trucks(self):
        result = dashboard.build_dayz_preset_file("chernarus", "spawnabletypes_builder_trucks")
        root = ET.fromstring(result["content"])
        truck = root.find("./type[@name='Truck_01_Covered']")
        truck_items = [item.get("name") for item in truck.findall("./cargo/item")]
        for expected in (
            "WoodenLog",
            "WoodenPlank",
            "MetalPlate",
            "WoodenCrate",
            "Barrel_Green",
            "CanisterGasoline",
            "Canteen",
        ):
            self.assertIn(expected, truck_items)
        car = root.find("./type[@name='OffroadHatchback']")
        self.assertEqual([], car.findall("./cargo"))

    def test_mobile_scenario_tracker_rows_are_profile_scoped_and_newest_first(self):
        tracker = {
            "guild:livo": {
                "events": [
                    {"id": "older", "type": "Wolf", "x": 1, "z": 2, "first_seen_ts": 100, "last_seen_ts": 110},
                    {
                        "id": "newer",
                        "type": "ContaminatedArea_Dynamic",
                        "x": 3,
                        "z": 4,
                        "first_seen_ts": 180,
                        "last_seen_ts": 195,
                    },
                ]
            }
        }

        rows = dashboard.mobile_scenario_tracker_rows(tracker, "guild:livo", now_ts=200)

        self.assertEqual(["newer", "older"], [row["id"] for row in rows])
        self.assertEqual("just now", rows[0]["last_seen_label"])
        self.assertEqual(3, rows[0]["x"])
        self.assertEqual([], dashboard.mobile_scenario_tracker_rows(tracker, "guild:cherno", now_ts=200))

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

    def test_ai_agent_dashboard_access_is_limited_to_ultimate(self):
        ultimate_config = {
            "guild-ultimate": {
                "dashboard": {"tier": "dashboard_ultimate", "plan_status": "subscription"}
            }
        }
        basic_config = {
            "guild-basic": {
                "dashboard": {"tier": "dashboard", "plan_status": "subscription"}
            }
        }
        auth = {"kind": "guild", "guild_id": "guild-ultimate", "label": "Ultimate server"}

        with patch.object(dashboard, "load_store", return_value=ultimate_config):
            access = dashboard.ai_agent_access_for_auth(auth, {})
        self.assertTrue(access["allowed"])
        self.assertEqual("ultimate", access["role"])

        with patch.object(dashboard, "load_store", return_value=basic_config):
            access = dashboard.ai_agent_access_for_auth({**auth, "guild_id": "guild-basic"}, {})
        self.assertFalse(access["allowed"])
        self.assertEqual("ultimate_required", access["status"])

    def test_dayz_ai_capability_matching_covers_events_and_mod_safety(self):
        event_capabilities = dashboard.ai_agent_dayz_capabilities_for_request(
            "Create a vehicle airdrop and infected horde event",
            "cfgeventspawns.xml",
        )
        titles = {item["title"] for item in event_capabilities}
        self.assertIn("Events, object spawns and vehicles", titles)

        mod_capabilities = dashboard.ai_agent_dayz_capabilities_for_request("Set up an NPC airstrike mod")
        mod_safety = next(item["safety"] for item in mod_capabilities if item["id"] == "mod_integrations")
        self.assertIn("exact mod", mod_safety)

        self.assertEqual("init.c", dashboard.ai_agent_dayz_target_path("init.c"))
        self.assertEqual("custom/objectspawner.json", dashboard.ai_agent_dayz_target_path("objectspawner.json"))
        self.assertEqual("custom/NoLogoutArea.json", dashboard.ai_agent_dayz_target_path("./custom/NoLogoutArea.json"))
        self.assertEqual("", dashboard.ai_agent_dayz_target_path("../custom/NoLogoutArea.json"))

    def test_ai_agent_uses_verified_event_name_guidance_for_linked_ce_files(self):
        reply = dashboard.ai_agent_verified_dayz_event_link_reply(
            "Explain what must match between events.xml and cfgeventspawns.xml for an airdrop."
        )

        self.assertIn('<event name="...">', reply)
        self.assertIn("must be identical in both files", reply)
        self.assertIn("case-sensitive", reply)
        self.assertNotIn("<id>", reply.lower())

    def test_verified_dayz_answer_never_starts_an_unrelated_sandbox_job(self):
        task = {"llm_status": "verified_dayz_reference"}

        self.assertFalse(
            dashboard.ai_agent_should_queue_chat_auto_job(
                task,
                "What must match between events.xml and cfgeventspawns.xml?",
                continued=True,
            )
        )
        self.assertTrue(
            dashboard.ai_agent_should_queue_chat_auto_job({}, "Please inspect this project", continued=False)
        )

    def test_ai_agent_workspaces_only_return_the_selected_conversation(self):
        state = {
            "runs": [{"id": "run-one", "task_ids": ["task-one"], "job_ids": [], "approval_ids": []}, {"id": "run-two", "task_ids": ["task-two"], "job_ids": [], "approval_ids": []}],
            "tasks": [{"id": "task-one", "run_id": "run-one"}, {"id": "task-two", "run_id": "run-two"}],
            "sandbox_jobs": [],
            "approvals": [],
            "chat_messages": [{"id": "message-one", "run_id": "run-one"}, {"id": "message-two", "run_id": "run-two"}],
        }

        workspace = dashboard.ai_agent_state_for_run(state, "run-two")

        self.assertEqual("run-two", workspace["selected_run"]["id"])
        self.assertEqual(["task-two"], [item["id"] for item in workspace["tasks"]])
        self.assertEqual(["message-two"], [item["id"] for item in workspace["chat_messages"]])

    def test_credit_checkout_url_adds_only_a_nonsecret_reference(self):
        url = dashboard.agent_credit_checkout_url(
            "https://buy.stripe.com/example?utm_source=dashboard",
            "credit-reference-123",
            "player@example.com",
        )

        self.assertIn("client_reference_id=credit-reference-123", url)
        self.assertIn("prefilled_email=player%40example.com", url)
        self.assertNotIn("sk_", url)

    def test_ultimate_dashboard_gets_a_durable_credit_account(self):
        store = {"accounts": {}, "ledger": [], "credit_checkouts": []}
        auth = {"kind": "guild", "guild_id": "guild-ultimate", "label": "Ultimate server"}

        with patch.object(dashboard, "load_store", return_value=store), patch.object(dashboard, "save_store"):
            account = dashboard.agent_credit_account_for_auth(auth, create=True)

        self.assertIsNotNone(account)
        self.assertEqual("dashboard_ultimate", account["subscription_tier"])
        self.assertEqual(dashboard.AGENT_ULTIMATE_INCLUDED_CREDITS, account["credits"])
        self.assertEqual(1, len(store["ledger"]))

    def test_owner_credit_rows_identify_dashboard_ultimate_accounts(self):
        store = {
            "accounts": {
                "dashboard-qa": {
                    "id": "dashboard-qa",
                    "name": "QA Discord",
                    "email": "",
                    "account_kind": "dashboard_ultimate",
                    "guild_id": "1491521072275788040",
                    "credits": 45,
                    "permissions": {"read": True, "edit": True},
                }
            }
        }
        with patch.object(dashboard, "load_agent_accounts", return_value=store):
            rows = dashboard.agent_account_rows()

        self.assertEqual(1, len(rows))
        self.assertEqual("dashboard_ultimate", rows[0]["account_kind"])
        self.assertEqual("1491521072275788040", rows[0]["guild_id"])
        self.assertEqual(45, rows[0]["credits"])
        self.assertIn("/api/owner/agent-credit-adjustment", dashboard.PAGE_TEMPLATE)

    def test_owner_can_auditably_adjust_existing_dashboard_ai_credits(self):
        payload = {
            "account_id": "dashboard-qa",
            "credit_adjustment": "200",
            "reason": "Extended AI Sandbox QA testing",
        }
        store = {
            "accounts": {
                "dashboard-qa": {
                    "id": "dashboard-qa",
                    "name": "QA Discord",
                    "account_kind": "dashboard_ultimate",
                    "guild_id": "1491521072275788040",
                    "credits": 45,
                }
            }
        }
        with (
            patch.object(dashboard, "require_owner_payload", return_value=(payload, None)),
            patch.object(dashboard, "load_agent_accounts", return_value=store),
            patch.object(dashboard, "agent_adjust_credits", return_value=(True, "", 245)) as adjust,
            patch.object(dashboard, "current_auth", return_value={"kind": "owner"}),
            patch.object(dashboard, "dashboard_audit_actor", return_value="Primary Owner"),
            patch.object(dashboard, "load_ai_agent_state", return_value={}),
            patch.object(dashboard, "ai_agent_activity") as activity,
            patch.object(dashboard, "save_ai_agent_state"),
            patch.object(dashboard, "dashboard_api_response", side_effect=lambda _raw, body, *_args: body),
        ):
            response = dashboard.api_owner_agent_credit_adjustment()

        self.assertTrue(response["ok"])
        self.assertEqual(245, response["credits"])
        adjust.assert_called_once_with(
            "dashboard-qa",
            200,
            "Extended AI Sandbox QA testing",
            "Primary Owner",
            {
                "account_kind": "dashboard_ultimate",
                "guild_id": "1491521072275788040",
                "owner_adjustment": True,
            },
        )
        self.assertIn("+200 credit(s), balance 245", activity.call_args.args[2])

    def test_checkout_target_records_selection_before_any_external_payment(self):
        plan = {"id": "dashboard", "name": "Wandering Bot Basic", "payment_url": "https://payments.example/checkout"}

        target, external = dashboard.dashboard_checkout_target_for_plan(plan)

        self.assertEqual("/checkout/dashboard", target)
        self.assertFalse(external)

    def test_billing_plan_selection_keeps_plan_and_source_without_payment_data(self):
        saves = {}
        fake_request = types.SimpleNamespace(
            args={"source": "Google Ads"},
            referrer="https://www.google.com/search?q=wandering+bot",
        )

        def fake_save(key, value):
            saves[key] = value

        with (
            patch.object(dashboard, "request", fake_request),
            patch.object(dashboard, "current_auth", return_value=None),
            patch.object(dashboard, "load_store", return_value=[]),
            patch.object(dashboard, "save_store", side_effect=fake_save),
        ):
            event = dashboard.record_billing_plan_selection(
                {"id": "dashboard_ai", "name": "Wandering Bot Pro", "price_text": "£12/month", "payment_url": "https://secret.example"}
            )

        self.assertEqual("dashboard_ai", event["plan_id"])
        self.assertEqual("google-ads", event["source"])
        self.assertEqual("checkout_started", event["status"])
        self.assertNotIn("payment_url", event)
        self.assertEqual(event, saves["billing_plan_selections"][0])
        self.assertNotIn("billing_plan_selection_queue", saves)

    def test_public_checkout_link_preserves_the_acquisition_source(self):
        fake_request = types.SimpleNamespace(
            args={},
            referrer="https://www.google.com/search?q=wandering+bot",
        )

        with patch.object(dashboard, "request", fake_request):
            url = dashboard.billing_plan_selection_url("dashboard")

        self.assertEqual("/checkout/dashboard?source=www.google.com", url)

    def test_public_checkout_link_carries_a_safe_promotion_code_to_stripe(self):
        fake_request = types.SimpleNamespace(args={"promo": "WELCOME20"}, referrer="")

        with patch.object(dashboard, "request", fake_request):
            internal_url = dashboard.billing_plan_selection_url("dashboard_ai")

        stripe_url = dashboard.billing_plan_checkout_url(
            "https://buy.stripe.com/example?locale=en",
            "billing-reference-123",
            promotion_code="WELCOME20",
        )
        self.assertEqual("/checkout/dashboard_ai?promo=WELCOME20", internal_url)
        self.assertIn("client_reference_id=billing-reference-123", stripe_url)
        self.assertIn("prefilled_promo_code=WELCOME20", stripe_url)
        self.assertNotIn("prefilled_promo_code", dashboard.billing_plan_checkout_url(
            "https://buy.stripe.com/example", "billing-reference-123", promotion_code="NO-DASHES"
        ))

    def test_public_setup_guide_is_available_before_login_and_downloadable(self):
        guide = dashboard.PUBLIC_SEO_GUIDES["wandering-bot-setup"]
        download = dashboard.public_setup_guide_download_text()

        self.assertEqual("/setup-guide", guide["path"])
        self.assertIn("Read the setup guide", dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertIn('href="/setup-guide/download"', dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertIn("Nitrado service ID and API token", dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertIn("WANDERING BOT SETUP GUIDE", download)
        self.assertIn("run /setup", download)
        self.assertIn("Never post Nitrado API tokens", download)

    def test_dayz_server_files_guide_is_searchable_and_uses_real_content_dates(self):
        guide = dashboard.PUBLIC_SEO_GUIDES["dayz-server-files-explained"]
        rendered = {}

        def fake_render(_template, **kwargs):
            rendered.update(kwargs)
            return "guide"

        with (
            patch.object(dashboard, "DASHBOARD_PUBLIC_URL", "https://dayzwanderingbot.com"),
            patch.object(dashboard, "load_review_rows", return_value=[]),
            patch.object(dashboard, "render_template_string", side_effect=fake_render),
        ):
            self.assertEqual("guide", dashboard.public_landing_page(guide_key="dayz-server-files-explained"))

        article = next(node for node in rendered["structured_data"]["@graph"] if node["@type"] == "Article")
        self.assertEqual("/guides/dayz-server-files-explained", guide["path"])
        self.assertIn("events.xml", guide["description"])
        self.assertEqual("2026-08-02", article["datePublished"])
        self.assertEqual("2026-08-02", article["dateModified"])

        with (
            patch.object(dashboard, "DASHBOARD_PUBLIC_URL", "https://dayzwanderingbot.com"),
            patch.object(dashboard, "Response", side_effect=lambda body, **_kwargs: body),
        ):
            sitemap = dashboard.sitemap_xml()

        self.assertIn("https://dayzwanderingbot.com/guides/dayz-server-files-explained", sitemap)
        self.assertIn("<lastmod>2026-08-02</lastmod>", sitemap)
        self.assertIn("<loc>https://dayzwanderingbot.com/privacy</loc><changefreq>", sitemap)

    def test_public_pages_cover_the_early_search_console_queries(self):
        status_guide = dashboard.PUBLIC_SEO_GUIDES["dayz-server-status-discord-bot"]
        features_guide = dashboard.PUBLIC_SEO_GUIDES["dayz-discord-server-features"]
        nitrado_page = dashboard.PUBLIC_SEO_PAGES["dayz-nitrado-server-tools"]
        airdrop_page = dashboard.PUBLIC_SEO_PAGES["dayz-console-airdrop-events"]

        self.assertEqual("/guides/dayz-server-status-discord-bot", status_guide["path"])
        self.assertIn("dayz server status discord bot", status_guide["title"].lower())
        self.assertIn("/admstatus", " ".join(body for _title, body in status_guide["sections"]))
        self.assertEqual("/guides/dayz-discord-server-features", features_guide["path"])
        self.assertIn("DayZ types booster", features_guide["keywords"])
        self.assertIn("Automatic Discord translation", " ".join(title for title, _body in features_guide["sections"]))
        self.assertIn("DayZ Nitrado Bot", nitrado_page["title"])
        self.assertIn("DayZ Airdrop", airdrop_page["title"])

    def test_public_seo_metadata_stays_concise_and_new_guides_are_linked(self):
        guide_keys = {
            "dayz-types-xml-loot-balancing",
            "dayz-custom-events-xml-files",
            "dayz-custom-json-cfggameplay",
            "dayz-discord-translation-bot",
            "dayz-safe-zones-radar",
        }

        for key, page in {**dashboard.PUBLIC_SEO_PAGES, **dashboard.PUBLIC_SEO_GUIDES}.items():
            self.assertLessEqual(len(page["title"]), 60, key)
            self.assertLessEqual(len(page["description"]), 160, key)

        for key in guide_keys:
            guide = dashboard.PUBLIC_SEO_GUIDES[key]
            self.assertTrue(guide["path"].startswith("/guides/"), key)
            self.assertGreaterEqual(len(guide["sections"]), 5, key)
            self.assertGreaterEqual(len(guide["faqs"]), 3, key)
            self.assertEqual("2026-08-05", guide["updated_at"])

        related = dashboard.public_related_pages([
            "dayz-custom-events-xml-files",
            "dayz-server-files-explained",
        ])
        self.assertEqual(2, len(related))
        self.assertEqual(
            "/guides/dayz-custom-events-xml-files",
            related[0]["path"],
        )

        with (
            patch.object(dashboard, "DASHBOARD_PUBLIC_URL", "https://dayzwanderingbot.com"),
            patch.object(dashboard, "Response", side_effect=lambda body, **_kwargs: body),
        ):
            sitemap = dashboard.sitemap_xml()

        for key in guide_keys:
            self.assertIn(
                f"https://dayzwanderingbot.com{dashboard.PUBLIC_SEO_GUIDES[key]['path']}",
                sitemap,
            )

    def test_player_audit_rows_keep_only_last_24_hours_and_show_last_seen(self):
        now = dashboard.datetime.now(dashboard.UTC)
        store = {
            "guild-1": [
                {"id": "old", "player": "OldPlayer", "event_type": "connect", "summary": "old", "occurred_at": (now - dashboard.timedelta(hours=25)).isoformat()},
                {"id": "join", "player": "Crane", "event_type": "connect", "summary": "Crane connected", "occurred_at": (now - dashboard.timedelta(minutes=10)).isoformat()},
                {"id": "build", "player": "Crane", "event_type": "build", "summary": "Crane build activity", "coords": "100,0,200", "occurred_at": now.isoformat()},
            ]
        }

        rows = dashboard.dashboard_player_audit_events_for_guild(store, "guild-1")
        players = dashboard.dashboard_player_audit_players(rows, ["CRANE"])

        self.assertEqual(["build", "connect"], [row["event_type"] for row in rows])
        self.assertEqual("Crane", players[0]["player"])
        self.assertTrue(players[0]["online"])
        self.assertEqual(2, players[0]["actions"])
        self.assertEqual(1, players[0]["locations"])
        self.assertIn("Player Audit", dashboard.PAGE_TEMPLATE)
        self.assertIn("not continuous GPS tracking", dashboard.PAGE_TEMPLATE)

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

    def test_manual_feature_checkboxes_override_owner_tier(self):
        config = {
            "dashboard": {
                "enabled": True,
                "tier": "owner",
                "plan_status": "lifetime",
                "feature_mode": "manual",
                "features": {
                    "leaderboards": True,
                    "economy": True,
                    "heatmaps": True,
                    "safe_zones": False,
                    "ai_agent": False,
                },
            }
        }

        self.assertTrue(dashboard.dashboard_feature_allowed(config, "heatmaps"))
        self.assertFalse(dashboard.dashboard_feature_allowed(config, "safe_zones"))
        self.assertFalse(dashboard.dashboard_feature_allowed(config, "ai_agent"))

    def test_guild_access_save_records_manual_checkbox_mode(self):
        saved = {}
        payload = {
            "guild_id": "1149812840564277350",
            "enabled": "true",
            "plan_preset": "",
            "tier": "owner",
            "plan_status": "lifetime",
            "features_present": "true",
            "feature_leaderboards": "on",
            "feature_economy": "on",
            "feature_heatmaps": "on",
            "feature_pve_quests": "on",
            "feature_server_rules": "on",
        }

        def fake_save(name, data):
            saved[name] = data

        with (
            patch.object(dashboard, "current_auth", return_value={"kind": "owner"}),
            patch.object(dashboard, "request_payload", return_value=payload),
            patch.object(dashboard, "load_store", return_value={}),
            patch.object(dashboard, "save_store", side_effect=fake_save),
            patch.object(dashboard, "dashboard_api_response", side_effect=lambda _payload, body, *_args: body),
        ):
            response = dashboard.api_guild_access()

        access = saved["guild_configs"]["1149812840564277350"]["dashboard"]
        self.assertTrue(response["ok"])
        self.assertEqual("manual", access["feature_mode"])
        self.assertEqual("owner", access["tier"])
        self.assertEqual("lifetime", access["plan_status"])
        self.assertTrue(access["features"]["heatmaps"])
        self.assertFalse(access["features"]["safe_zones"])
        self.assertTrue(dashboard.dashboard_feature_allowed({"dashboard": access}, "heatmaps"))
        self.assertFalse(dashboard.dashboard_feature_allowed({"dashboard": access}, "safe_zones"))

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

    def test_schedule_starts_an_upload_thread_immediately(self):
        old_provider = dashboard.CUSTOM_STATE_PROVIDER
        started = []

        class FakeThread:
            def __init__(self, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon

            def start(self):
                started.append((self.name, self.daemon))

        try:
            dashboard.CUSTOM_STATE_PROVIDER = lambda: {"scenario_xml_uploader": lambda *_args: {"ok": True}}
            with patch.object(dashboard, "Thread", FakeThread):
                self.assertTrue(dashboard.schedule_runtime_scenario_xml_upload("guild-1", 37))
        finally:
            dashboard.CUSTOM_STATE_PROVIDER = old_provider

        self.assertEqual([("scenario-upload-guild-1-37", True)], started)

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

    def test_public_pricing_shows_all_enabled_tiers_and_uses_configured_checkout(self):
        plans = list(dashboard.default_billing_plan_map().values())

        with patch.object(dashboard, "dashboard_billing_plans", return_value=plans):
            public_plans = {plan["id"]: plan for plan in dashboard.public_billing_plans_for_homepage()}

        self.assertEqual({"free_bot", "dashboard", "dashboard_ai", "dashboard_ultimate"}, set(public_plans))
        self.assertIn("Private /setup guidance and ADM connection checks", public_plans["free_bot"]["public_features"])
        self.assertIn("Activate and control supported server tools, gameplay and DayZ file work from your phone", public_plans["dashboard_ultimate"]["public_features"])
        self.assertIn("Android and Apple companion application — coming soon", public_plans["dashboard_ultimate"]["public_features"])
        self.assertIn("DayZ files", public_plans["dashboard_ultimate"]["public_ai_agent_summary"])
        self.assertEqual("Add Wandering Bot", public_plans["free_bot"]["public_cta"])
        self.assertEqual("Buy now", public_plans["dashboard"]["public_cta"])
        self.assertEqual("Buy now", public_plans["dashboard_ai"]["public_cta"])
        self.assertEqual("Buy now", public_plans["dashboard_ultimate"]["public_cta"])
        self.assertEqual("", public_plans["free_bot"]["payment_url"])
        self.assertEqual("https://buy.stripe.com/aFaaER9TH6Qf6TY5pNbEA03", public_plans["dashboard"]["payment_url"])
        self.assertEqual("https://buy.stripe.com/cNidR3aXL6Qf5PU7xVbEA04", public_plans["dashboard_ai"]["payment_url"])
        self.assertEqual("https://buy.stripe.com/3cI00daXL5Mb4LQaK7bEA05", public_plans["dashboard_ultimate"]["payment_url"])
        self.assertEqual("Price shown at checkout", public_plans["dashboard_ultimate"]["public_price_text"])

    def test_saved_free_billing_plan_keeps_its_checkout_url(self):
        saved = {
            "billing_plans": {
                "free_bot": {"payment_url": "https://buy.stripe.com/aFa6oB5Dr3E35PU7xVbEA02"},
            },
        }

        with patch.object(dashboard, "load_store", return_value=saved):
            plans = {plan["id"]: plan for plan in dashboard.dashboard_billing_plans()}

        self.assertEqual("https://buy.stripe.com/aFa6oB5Dr3E35PU7xVbEA02", plans["free_bot"]["payment_url"])

    def test_billing_checkout_url_carries_only_a_nonsecret_stripe_reference(self):
        url = dashboard.billing_plan_checkout_url(
            "https://buy.stripe.com/basic?utm_source=website",
            "billing-abc123456789",
        )

        self.assertIn("client_reference_id=billing-abc123456789", url)
        self.assertIn("utm_source=website", url)
        self.assertNotIn("claim_token", url)
        self.assertNotIn("sk_", url)

    def test_signed_billing_payment_activates_only_the_matching_plan_link(self):
        plan = {
            "id": "dashboard",
            "name": "Wandering Bot Basic",
            "payment_url": "https://buy.stripe.com/basic",
            "features": {"leaderboards": True, "server_control": True},
        }
        purchase = {
            "id": "billing-abc123456789",
            "claim_token": "A" * 32,
            "plan_id": "dashboard",
            "plan_name": "Wandering Bot Basic",
            "price_text": "€5.99 / month",
            "payment_link_id": "plink_basic",
            "status": "checkout_started",
            "guild_id": "guild-1",
            "created_at": "2026-08-02T10:00:00+00:00",
        }
        stores = {
            "billing_plan_purchases": [purchase],
            "guild_configs": {"guild-1": {"guild_name": "Test server", "dashboard": {"enabled": False, "plan_status": "none"}}},
            "billing_plan_selection_queue": [],
        }

        def load(name, default):
            return stores.get(name, default)

        def save(name, value):
            stores[name] = value

        session = {
            "id": "cs_paid_123",
            "payment_link": "plink_basic",
            "subscription": "sub_123",
            "customer": "cus_123",
            "customer_details": {"email": "buyer@example.com"},
        }
        with (
            patch.object(dashboard, "load_store", side_effect=load),
            patch.object(dashboard, "save_store", side_effect=save),
            patch.object(dashboard, "dashboard_plan_by_id", return_value=plan),
        ):
            fulfilled, message, result = dashboard.billing_fulfil_plan_checkout(purchase["id"], session, "evt_123")

        self.assertTrue(fulfilled, message)
        self.assertEqual("activated", result["status"])
        access = stores["guild_configs"]["guild-1"]["dashboard"]
        self.assertTrue(access["enabled"])
        self.assertEqual("dashboard", access["tier"])
        self.assertEqual("subscription", access["plan_status"])
        self.assertTrue(access["features"]["server_control"])
        self.assertFalse(access["features"]["ai_agent"])
        self.assertEqual("cs_paid_123", result["stripe_session_id"])
        self.assertEqual("plan_activated", stores["billing_plan_selection_queue"][0]["status"])

    def test_billing_payment_rejects_a_different_stripe_payment_link(self):
        purchase = {
            "id": "billing-abc123456789",
            "plan_id": "dashboard_ultimate",
            "payment_link_id": "plink_ultimate",
            "status": "checkout_started",
        }
        with patch.object(dashboard, "load_store", return_value=[purchase]):
            fulfilled, message, _result = dashboard.billing_fulfil_plan_checkout(
                purchase["id"],
                {"id": "cs_paid_123", "payment_link": "plink_basic"},
                "evt_123",
            )

        self.assertFalse(fulfilled)
        self.assertIn("did not match", message)

    def test_free_plan_checkout_goes_directly_to_the_bot_invite(self):
        free_plan = dashboard.default_billing_plan_map()["free_bot"]

        with patch.object(dashboard, "dashboard_plan_by_id", return_value=free_plan), patch.object(dashboard, "record_billing_plan_selection") as record_selection:
            destination = dashboard.public_checkout("free_bot")

        self.assertEqual(dashboard.dashboard_bot_invite_url(), destination)
        record_selection.assert_not_called()

    def test_onboarding_emoji_picker_includes_the_selected_servers_custom_emoji(self):
        server_emoji = {
            "value": "<:cherno:123456789012345678>",
            "label": ":cherno: (this server)",
            "name": "cherno",
        }

        with patch.object(dashboard, "discord_guild_emojis", return_value=[server_emoji]) as load_emojis:
            options = dashboard.dashboard_onboarding_emoji_options("guild-1")

        self.assertIn("✅", [option["value"] for option in options])
        self.assertIn(server_emoji, options)
        load_emojis.assert_called_once_with("guild-1")
        self.assertEqual("<:cherno:123456789012345678>", dashboard.normalize_dashboard_onboarding_emoji(server_emoji["value"]))

    def test_dayz_file_workbench_normalizes_a_types_fragment_as_a_merge_patch(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "types.xml",
                "dayz_map": "Chernarus",
                "dayz_source_mode": "fragment",
                "dayz_file_source": '<type name="AKM"><nominal>4</nominal></type>',
            },
            "Make AKM more common without replacing the economy.",
        )
        draft, error = dashboard.ai_agent_normalize_dayz_draft(
            {
                "target_path": "db/types.xml",
                "kind": "patch",
                "content": '<types><type name="AKM"><nominal>8</nominal><lifetime>14400</lifetime><restock>1800</restock><min>4</min><quantmin>-1</quantmin><quantmax>-1</quantmax><cost>100</cost><flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0" /></type></types>',
                "summary": "Increase AKM nominal only.",
            },
            context,
        )

        self.assertEqual("db/types.xml", context["target_path"])
        self.assertTrue(context["allows_merge_patch"])
        self.assertEqual("", error)
        self.assertEqual("patch", draft["kind"])
        self.assertTrue(draft["merge_required"])

    def test_dayz_full_draft_requires_complete_current_file_and_preserves_existing_types(self):
        current = '<types><type name="AKM" /><type name="M4A1" /></types>'
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "db/types.xml",
                "dayz_source_mode": "complete",
                "dayz_file_source": current,
            },
            "Make the AKM more common.",
        )
        draft, error = dashboard.ai_agent_normalize_dayz_draft(
            {"kind": "full_file", "content": '<types><type name="AKM" /></types>'},
            context,
        )

        self.assertIsNone(draft)
        self.assertIn("removes existing records", error)

    def test_dayz_agent_can_create_a_recognised_custom_json_file_without_a_vanilla_base(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "./pra/NoLogoutArea.json",
                "dayz_map": "sakhal",
            },
            "Create a small protected bunker area that moves players to a safe position.",
        )
        content = (
            '{"areaName":"NoLogoutArea","PRABoxes":[[[27,5.2,11],[108,0,0],[2570,15.22,5963.8]]],'
            '"safePositions3D":[[2575.12,15.25,5954.31]]}'
        )
        draft, error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "pra/NoLogoutArea.json", "kind": "full_file", "content": content},
            context,
        )

        self.assertEqual("pra/NoLogoutArea.json", context["target_path"])
        self.assertTrue(context["is_custom_json"])
        self.assertIn("restricted area", " ".join(context["knowledge"]["known_schemas"]))
        self.assertIn("custom/ or pra/ JSON", context["format_guide"])
        self.assertEqual("player_restricted_area", context["dependency_plan"]["workflow"])
        self.assertEqual(
            ["pra/NoLogoutArea.json", "cfggameplay.json"],
            [item["path"] for item in context["dependency_plan"]["files"]],
        )
        self.assertEqual("", error)
        self.assertEqual("restricted_area", draft["custom_json_schema"])

    def test_dayz_context_supplies_map_group_dependency_plan_to_the_model(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "mapgrouppos.xml",
                "dayz_map": "livonia",
            },
            "Place a new loot-bearing static building with working loot points.",
        )
        model_context = dashboard.ai_agent_dayz_context_for_model(context)
        plan = model_context["dependency_plan"]
        files = {item["path"]: item for item in plan["files"]}

        self.assertEqual("map_group_placement", plan["workflow"])
        self.assertEqual("changed", files["mapgrouppos.xml"]["action"])
        self.assertEqual("changed", files["mapgroupproto.xml"]["action"])
        self.assertEqual("conditional", files["cfglimitsdefinition.xml"]["action"])

    def test_dayz_file_plan_and_template_include_the_specialist_workbench(self):
        plan = dashboard.ai_agent_plan_from_objective(
            "Make the weather drier but retain storms.",
            "dayz_files",
            {"read": True, "edit": True, "execute": False, "deploy": False},
            {"god_mode_enabled": False},
        )

        self.assertTrue(any(step["agent"] == "DayZ File Specialist" for step in plan["steps"]))
        self.assertIn('value="dayz_files"', dashboard.PAGE_TEMPLATE)
        self.assertIn('name="dayz_file_target"', dashboard.PAGE_TEMPLATE)
        self.assertIn('name="dayz_custom_target_path"', dashboard.PAGE_TEMPLATE)
        self.assertIn("DayZ File Drafts", dashboard.PAGE_TEMPLATE)

    def test_dayz_task_state_hides_pasted_file_and_download_content(self):
        task = {
            "id": "ai-1",
            "dayz_context": {
                "target_path": "db/types.xml",
                "source_text": "private current file",
                "source_excerpt": "private",
                "reference": {"content": "private vanilla file", "preview": "private"},
            },
            "dayz_draft": {"id": "dayz-draft-1", "content": "private draft", "target_path": "db/types.xml"},
        }

        public = dashboard.ai_agent_public_task(task)

        self.assertNotIn("source_text", public["dayz_context"])
        self.assertNotIn("source_excerpt", public["dayz_context"])
        self.assertNotIn("content", public["dayz_context"]["reference"])
        self.assertNotIn("preview", public["dayz_context"]["reference"])
        self.assertNotIn("content", public["dayz_draft"])
        self.assertEqual("private current file", task["dayz_context"]["source_text"])
        self.assertEqual("private draft", task["dayz_draft"]["content"])

    def test_dayz_workbench_offers_validated_bundled_weather_presets(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "cfgweather.xml",
                "dayz_map": "livonia",
                "dayz_reference_mode": "preset",
                "dayz_preset_id": "cfgweather_dry",
            },
            "Give me a mostly dry weather file.",
        )
        content, download_name, error = dashboard.ai_agent_dayz_reference_content(context)

        self.assertEqual("passed", context["reference"]["validation"])
        self.assertEqual("", error)
        self.assertIn("cfgweather_dry", download_name)
        self.assertTrue(content.startswith("<?xml") or content.startswith("<weather"))
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text("cfgweather.xml", content))

    def test_dayz_agent_can_make_a_complete_custom_weather_draft_from_a_validated_base(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "cfgweather.xml",
                "dayz_map": "chernarus",
                "dayz_reference_mode": "preset",
                "dayz_preset_id": "cfgweather_sunny_storms",
            },
            "Create a mainly sunny weather file with occasional rain and thunderstorms.",
        )
        content, _download_name, reference_error = dashboard.ai_agent_dayz_reference_content(context)
        draft, draft_error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "cfgweather.xml", "kind": "full_file", "content": content, "summary": "Sunny with occasional storms."},
            context,
        )
        root = ET.fromstring(content)

        self.assertEqual("", reference_error)
        self.assertEqual("", draft_error)
        self.assertEqual("full_file", draft["kind"])
        self.assertTrue(context["reference_base_available"])
        self.assertEqual("0.75", root.find("overcast/limits").get("max"))
        self.assertEqual("0.25", root.find("storm").get("density"))
        self.assertIn("<weather>", dashboard.ai_agent_dayz_format_guide("cfgweather.xml"))

        built_in = dashboard.ai_agent_builtin_dayz_draft(
            {"dayz_context": context},
            "Produce a mostly sunny weather file with partial rain and thunderstorms.",
        )
        self.assertIsNotNone(built_in)
        self.assertEqual("full_file", built_in["kind"])
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text("cfgweather.xml", built_in["content"]))

    def test_dayz_agent_builds_a_valid_complete_types_boost_draft_without_model_truncation(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "edit_file",
                "dayz_file_target": "db/types.xml",
                "dayz_map": "livonia",
                "dayz_source_mode": "complete",
                "dayz_reference_mode": "vanilla",
            },
            "Create a complete types.xml with weapons and ammo and military clothing boosted 200%, with crap clothing minimal.",
        )
        draft = dashboard.ai_agent_builtin_dayz_draft(
            {"dayz_context": context},
            "Create a complete types.xml with weapons and ammo and military clothing boosted 200%, with crap clothing minimal.",
        )
        vanilla_root = ET.fromstring(dashboard.load_dayz_reference_text("livonia", "db", "types.xml"))
        draft_root = ET.fromstring(draft["content"])

        def values(root, name):
            node = next(item for item in root.findall("type") if item.get("name") == name)
            return int(node.findtext("nominal", "0")), int(node.findtext("min", "0"))

        weapon = next(item.get("name") for item in vanilla_root.findall("type") if item.find("category[@name='weapons']") is not None and int(item.findtext("nominal", "0")) > 0)
        ammunition = next(item.get("name") for item in vanilla_root.findall("type") if item.get("name", "").startswith("Ammo_") and int(item.findtext("nominal", "0")) > 0)
        military_clothes = next(item.get("name") for item in vanilla_root.findall("type") if item.find("category[@name='clothes']") is not None and item.find("usage[@name='Military']") is not None and int(item.findtext("nominal", "0")) > 0)
        common_clothes = next(item.get("name") for item in vanilla_root.findall("type") if item.find("category[@name='clothes']") is not None and item.find("usage[@name='Military']") is None and int(item.findtext("nominal", "0")) > 1)
        unchanged_food = next(item.get("name") for item in vanilla_root.findall("type") if item.find("category[@name='food']") is not None)

        self.assertIsNotNone(draft)
        self.assertGreater(len(draft["content"]), 800_000)
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text("db/types.xml", draft["content"]))
        for name in (weapon, ammunition, military_clothes):
            before_nominal, before_min = values(vanilla_root, name)
            self.assertEqual((before_nominal * 2, before_min * 2), values(draft_root, name))
        self.assertEqual((1, 1), values(draft_root, common_clothes))
        self.assertEqual(values(vanilla_root, unchanged_food), values(draft_root, unchanged_food))
        self.assertIn("Zero-nominal vanilla records remain disabled", draft["summary"])

    def test_dayz_invalid_complete_xml_can_be_repaired_without_replacing_unrelated_records(self):
        malformed = (
            '<events><event name="VehicleQA"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>3600</lifetime><restock>0</restock><saferadius>0</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>100</cleanupradius>'
            '<flags deletable="1" init_random="0" remove_damaged="1"/><position>fixed</position>'
            '<limit>mixed</limit><active>1</active><children><child lootmax="0" lootmin="0" '
            'max="1" min="1" type="OffroadHatchback"></children></event></events>'
        )
        repaired = malformed.replace('type="OffroadHatchback"></children>', 'type="OffroadHatchback"/></children>')
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "fix_error",
                "dayz_file_target": "db/events.xml",
                "dayz_map": "chernarus",
                "dayz_source_mode": "complete",
                "dayz_file_source": malformed,
            },
            "Fix the mismatched child tag and preserve everything else.",
        )

        draft, error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "db/events.xml", "kind": "full_file", "content": repaired}, context,
        )

        self.assertFalse(context["source_validation"]["ok"])
        self.assertEqual("", error)
        self.assertEqual("full_file", draft["kind"])
        self.assertIn('event name="VehicleQA"', draft["content"])

    def test_dayz_invalid_complete_json_can_be_repaired_without_a_vanilla_substitution(self):
        malformed = '{"WorldsData":{"objectSpawnersArr":["./custom/Base.json",],"lightingConfig":1}}'
        repaired = '{"WorldsData":{"objectSpawnersArr":["./custom/Base.json"],"lightingConfig":1}}'
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "fix_error",
                "dayz_file_target": "cfggameplay.json",
                "dayz_map": "chernarus",
                "dayz_source_mode": "complete",
                "dayz_file_source": malformed,
            },
            "Remove the trailing comma only.",
        )

        draft, error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "cfggameplay.json", "kind": "full_file", "content": repaired}, context,
        )

        self.assertEqual("", error)
        self.assertEqual(["./custom/Base.json"], json.loads(draft["content"])["WorldsData"]["objectSpawnersArr"])

    def test_dayz_new_sakhal_messages_file_does_not_require_a_nonexistent_vanilla_file(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "create_file",
                "dayz_file_target": "db/messages.xml",
                "dayz_map": "sakhal",
            },
            "Create an on-screen welcome message.",
        )
        content = '<messages><message><delay>1</delay><repeat>30</repeat><onconnect>1</onconnect><text>Welcome.</text></message></messages>'

        draft, error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "db/messages.xml", "kind": "full_file", "content": content}, context,
        )

        self.assertEqual("", error)
        self.assertEqual("full_file", draft["kind"])

    def test_dayz_animal_territory_draft_must_use_the_selected_maps_real_zone_name(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "env/bear_territories.xml",
                "dayz_map": "chernarus",
                "dayz_source_mode": "fragment",
                "dayz_file_source": '<zone name="Graze" smin="0" smax="0" dmin="1" dmax="2" x="1" z="2" r="60"/>',
            },
            "Add one bear zone.",
        )
        bad = '<territory-type><territory color="1"><zone name="BearPack" smin="0" smax="0" dmin="1" dmax="2" x="1" z="2" r="60"/></territory></territory-type>'
        good = bad.replace("BearPack", "Graze")

        bad_draft, bad_error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "env/bear_territories.xml", "kind": "patch", "content": bad}, context,
        )
        good_draft, good_error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "env/bear_territories.xml", "kind": "patch", "content": good}, context,
        )

        self.assertIsNone(bad_draft)
        self.assertIn("unknown zone", bad_error)
        self.assertEqual("", good_error)
        self.assertIsNotNone(good_draft)

    def test_dayz_selected_large_spawnabletypes_preset_bypasses_model_truncation(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "cfgspawnabletypes.xml",
                "dayz_map": "chernarus",
                "dayz_reference_mode": "preset",
                "dayz_preset_id": "spawnabletypes_builder_trucks",
            },
            "Create the complete selected builder-truck cfgspawnabletypes preset.",
        )

        draft = dashboard.ai_agent_builtin_dayz_draft(
            {"dayz_context": context}, "Create the complete selected builder-truck cfgspawnabletypes preset."
        )

        self.assertIsNotNone(draft)
        self.assertGreater(len(draft["content"]), 90_000)
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text(draft["target_path"], draft["content"]))

    def test_dayz_objectspawner_and_sakhal_effect_area_are_built_from_exact_input(self):
        object_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "custom/QA_CastleCamp.json",
                "dayz_map": "chernarus",
            },
            "Create ObjectSpawner placements.",
        )
        object_prompt = (
            "Create ObjectSpawner JSON: Land_TentA_Big at [6500,125,7000] with ypr [135,0,0] "
            "and Land_Campfire at [6504,125,7002] with ypr [0,0,0]."
        )
        object_draft = dashboard.ai_agent_builtin_dayz_draft({"dayz_context": object_context}, object_prompt)
        objects = json.loads(object_draft["content"])["Objects"]

        self.assertEqual("Land_TentA_Big", objects[0]["name"])
        self.assertEqual([6500.0, 125.0, 7000.0], objects[0]["pos"])
        self.assertEqual([135.0, 0.0, 0.0], objects[0]["ypr"])
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text(object_draft["target_path"], object_draft["content"]))

        effect_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "custom/QA_Geyser.json",
                "dayz_map": "sakhal",
            },
            "Create an effect area.",
        )
        effect_prompt = "Create an effect area named QAGeyser, Type GeyserArea, position [5000,0,5000], radius 3."
        effect_draft = dashboard.ai_agent_builtin_dayz_draft({"dayz_context": effect_context}, effect_prompt)
        effect = json.loads(effect_draft["content"])["Areas"][0]

        self.assertEqual("GeyserTrigger", effect["TriggerType"])
        self.assertEqual([5000.0, 0.0, 5000.0], effect["Data"]["Pos"])
        self.assertIn("EffectInterval", effect["Data"])
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text(effect_draft["target_path"], effect_draft["content"]))

    def test_dayz_semantic_validator_blocks_out_of_map_geometry_and_wrong_map_effect_types(self):
        object_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "custom/OutsideMap.json",
                "dayz_map": "chernarus",
            },
            "Create ObjectSpawner JSON outside the map.",
        )
        object_content = json.dumps({
            "Objects": [{"name": "Land_TentA_Big", "pos": [16000, 0, 16000], "ypr": [0, 0, 0]}]
        })
        object_draft, object_error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "custom/OutsideMap.json", "kind": "full_file", "content": object_content}, object_context,
        )

        self.assertIsNone(object_draft)
        self.assertIn("outside the selected chernarus bounds", object_error)

        spawn_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "cfgeventspawns.xml",
                "dayz_map": "chernarus",
                "dayz_source_mode": "fragment",
                "dayz_file_source": '<event name="VehicleQA"><pos x="16000" z="16000" a="0.000000"/></event>',
            },
            "Add a positioned event outside the map.",
        )
        spawn_content = '<eventposdef><event name="VehicleQA"><pos x="16000" z="16000" a="0.000000"/></event></eventposdef>'
        spawn_draft, spawn_error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "cfgeventspawns.xml", "kind": "patch", "content": spawn_content}, spawn_context,
        )

        self.assertIsNone(spawn_draft)
        self.assertIn("outside the selected chernarus bounds", spawn_error)

        effect_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "custom/WrongMapGeyser.json",
                "dayz_map": "chernarus",
            },
            "Create a GeyserArea on Chernarus.",
        )
        effect_content = json.dumps({
            "Areas": [{
                "AreaName": "WrongMapGeyser",
                "Type": "GeyserArea",
                "TriggerType": "GeyserTrigger",
                "Data": {"Pos": [5000, 0, 5000], "Radius": 2},
            }]
        })
        effect_draft, effect_error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "custom/WrongMapGeyser.json", "kind": "full_file", "content": effect_content}, effect_context,
        )

        self.assertIsNone(effect_draft)
        self.assertIn("does not exist in the selected chernarus vanilla schema", effect_error)

    def test_dayz_semantic_validator_checks_core_xml_record_shapes(self):
        context = {"map": "chernarus"}
        valid_types = (
            '<types><type name="M4A1"><nominal>10</nominal><lifetime>28800</lifetime>'
            '<restock>0</restock><min>5</min><quantmin>-1</quantmin><quantmax>-1</quantmax>'
            '<cost>100</cost><flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" '
            'count_in_player="0" crafted="0" deloot="0"/><category name="weapons"/></type></types>'
        )
        invalid_types = valid_types.replace('<nominal>10</nominal>', '')
        valid_events = (
            '<events><event name="VehicleQA"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>3888000</lifetime><restock>0</restock><saferadius>100</saferadius>'
            '<distanceradius>50</distanceradius><cleanupradius>100</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="1"/><position>fixed</position>'
            '<limit>custom</limit><active>1</active><children><child lootmax="0" lootmin="0" '
            'max="1" min="1" type="OffroadHatchback"/></children></event></events>'
        )
        invalid_events = valid_events.replace(
            '<children><child lootmax="0" lootmin="0" max="1" min="1" type="OffroadHatchback"/></children>', ''
        )
        valid_spawnable = (
            '<spawnabletypes><type name="M4A1"><attachments chance="1.0"><item name="M4_CarryHandleOptic" '
            'chance="1.0"/></attachments><cargo chance="1.0"><item name="Mag_STANAG_30Rnd" '
            'quantmin="100" quantmax="100"/></cargo></type></spawnabletypes>'
        )
        invalid_spawnable = valid_spawnable.replace('chance="1.0"/>', 'chance="150"/>', 1)

        self.assertEqual((True, ""), dashboard.ai_agent_validate_dayz_draft_semantics("db/types.xml", valid_types, context))
        self.assertIn("missing <nominal>", dashboard.ai_agent_validate_dayz_draft_semantics("db/types.xml", invalid_types, context)[1])
        self.assertIn(
            "<min> cannot be higher",
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "db/types.xml", valid_types.replace("<min>5</min>", "<min>11</min>"), context
            )[1],
        )
        self.assertIn(
            "0 <= quantmin",
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "db/types.xml",
                valid_types.replace("<quantmin>-1</quantmin><quantmax>-1</quantmax>", "<quantmin>80</quantmin><quantmax>20</quantmax>"),
                context,
            )[1],
        )
        self.assertEqual((True, ""), dashboard.ai_agent_validate_dayz_draft_semantics("db/events.xml", valid_events, context))
        self.assertIn("missing <children>", dashboard.ai_agent_validate_dayz_draft_semantics("db/events.xml", invalid_events, context)[1])
        self.assertIn(
            "<active> must be 0 or 1",
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "db/events.xml", valid_events.replace("<active>1</active>", "<active>2</active>"), context
            )[1],
        )
        self.assertIn(
            "lootmin cannot exceed lootmax",
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "db/events.xml", valid_events.replace('lootmax="0" lootmin="0"', 'lootmax="0" lootmin="1"'), context
            )[1],
        )
        self.assertEqual((True, ""), dashboard.ai_agent_validate_dayz_draft_semantics("cfgspawnabletypes.xml", valid_spawnable, context))
        self.assertIn("between 0 and 100", dashboard.ai_agent_validate_dayz_draft_semantics("cfgspawnabletypes.xml", invalid_spawnable, context)[1])
        full_mag_context = {
            "map": "chernarus",
            "objective": "Add Mag_STANAG_30Rnd and make the magazine 100% full.",
        }
        self.assertEqual(
            (True, ""),
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgspawnabletypes.xml", valid_spawnable, full_mag_context
            ),
        )
        not_full = valid_spawnable.replace('quantmin="100" quantmax="100"', 'quantmin="1" quantmax="1"')
        self.assertIn(
            'quantmin="100"',
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgspawnabletypes.xml", not_full, full_mag_context
            )[1],
        )

        self.assertEqual(
            (True, ""),
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "mapgrouppos.xml",
                '<map><group name="Land_Test" pos="5000 25 6000" rpy="0 0 90"/></map>',
                context,
            ),
        )
        self.assertIn(
            "outside the selected chernarus bounds",
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "mapgrouppos.xml",
                '<map><group name="Land_Test" pos="18000 25 6000" rpy="0 0 90"/></map>',
                context,
            )[1],
        )

    def test_dayz_cfgeconomycore_patch_uses_official_ce_file_shape(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "cfgeconomycore.xml",
                "dayz_map": "chernarus",
                "dayz_source_mode": "fragment",
                "dayz_file_source": '<ce folder="custom"><file name="qa_types.xml" type="types"/></ce>',
            },
            "Add a custom types include without replacing the current file.",
        )
        valid_content = '<economycore><ce folder="custom"><file name="qa_types.xml" type="types"/></ce></economycore>'
        invalid_content = '<economycore><include folder="custom" type="types"/></economycore>'

        valid_draft, valid_error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "cfgeconomycore.xml", "kind": "patch", "content": valid_content}, context,
        )
        invalid_draft, invalid_error = dashboard.ai_agent_normalize_dayz_draft(
            {"target_path": "cfgeconomycore.xml", "kind": "patch", "content": invalid_content}, context,
        )

        self.assertIsNotNone(valid_draft, valid_error)
        self.assertTrue(valid_draft["merge_required"])
        self.assertIsNone(invalid_draft)
        self.assertIn("not an <include> element", invalid_error)

    def test_dayz_limit_definition_files_keep_definitions_and_user_aliases_separate(self):
        context = {"map": "chernarus"}
        valid_definitions = (
            '<lists><categories><category name="CastleLoot"/></categories>'
            '<tags><tag name="shelves"/></tags><usageflags><usage name="Town"/></usageflags>'
            '<valueflags><value name="Tier1"/></valueflags></lists>'
        )
        invalid_definitions = valid_definitions.replace(
            '<category name="CastleLoot"/>', '<usage name="CastleLoot"/>'
        )
        valid_user_alias = (
            '<lists><usageflags><user name="Settlements"><usage name="Town"/>'
            '<usage name="Village"/></user></usageflags></lists>'
        )
        invalid_user_category = (
            '<lists><categories><user name="Castle"><category name="CastleLoot"/>'
            '</user></categories></lists>'
        )
        undefined_user_usage = (
            '<lists><usageflags><user name="Castle"><usage name="CastleLoot"/>'
            '</user></usageflags></lists>'
        )

        self.assertEqual(
            (True, ""),
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfglimitsdefinition.xml", valid_definitions, context
            ),
        )
        self.assertIn(
            "must contain only named <category>",
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfglimitsdefinition.xml", invalid_definitions, context
            )[1],
        )
        self.assertEqual(
            (True, ""),
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfglimitsdefinitionuser.xml", valid_user_alias, context
            ),
        )
        self.assertIn(
            "belongs in cfglimitsdefinition.xml",
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfglimitsdefinitionuser.xml", invalid_user_category, context
            )[1],
        )
        self.assertIn(
            "references undefined usage CastleLoot",
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfglimitsdefinitionuser.xml", undefined_user_usage, context
            )[1],
        )

    def test_dayz_auxiliary_xml_semantics_reject_common_model_mistakes(self):
        context = {"map": "chernarus"}
        valid_ignore = '<ignore><type name="OffroadHatchback"/><type name="Sedan_02"/></ignore>'
        duplicate_ignore = '<ignore><type name="OffroadHatchback"/><type name="OffroadHatchback"/></ignore>'
        valid_presets = (
            '<randompresets><cargo name="QAAmmo" chance="0.5">'
            '<item name="Mag_STANAG_30Rnd" chance="1"/></cargo></randompresets>'
        )
        percentage_presets = valid_presets.replace('chance="0.5"', 'chance="50"')
        invalid_environment = (
            '<env><territories><territory type="Herd" name="Bear" behavior="BlissBearGroupBeh">'
            '<file path="env/bear_territories.xml"/></territory></territories></env>'
        )
        valid_spawnpoints = (
            '<playerspawnpoints><fresh><spawn_params><min_dist_infected>30</min_dist_infected></spawn_params>'
            '<generator_params><grid_density>4</grid_density></generator_params><group_params>'
            '<enablegroups>true</enablegroups><groups_as_regular>true</groups_as_regular>'
            '<lifetime>120</lifetime><counter>2</counter></group_params><generator_posbubbles>'
            '<group name="Coast"><pos x="5000" z="3000"/></group></generator_posbubbles>'
            '</fresh></playerspawnpoints>'
        )
        invalid_spawnpoints = valid_spawnpoints.replace(
            '<enablegroups>true</enablegroups>', '<enablegroups>sometimes</enablegroups>'
        )

        self.assertEqual(
            (True, ""), dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgignorelist.xml", valid_ignore, context
            )
        )
        self.assertIn(
            "duplicate named record", dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgignorelist.xml", duplicate_ignore, context
            )[1]
        )
        self.assertEqual(
            (True, ""), dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgrandompresets.xml", valid_presets, context
            )
        )
        self.assertIn(
            "between 0 and 1", dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgrandompresets.xml", percentage_presets, context
            )[1]
        )
        self.assertIn(
            "file usable", dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgenvironment.xml", invalid_environment, context
            )[1]
        )
        self.assertEqual(
            (True, ""), dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgplayerspawnpoints.xml", valid_spawnpoints, context
            )
        )
        self.assertIn(
            "must be true/false", dashboard.ai_agent_validate_dayz_draft_semantics(
                "cfgplayerspawnpoints.xml", invalid_spawnpoints, context
            )[1]
        )

        valid_cluster_placement = (
            '<map><group name="PearTree2" pos="5000 25 6000" a="90.000000"/></map>'
        )
        invalid_cluster_placement = valid_cluster_placement.replace('a="90.000000"', 'a="east"')
        invalid_cluster_prototype = (
            '<prototype><clusters><export name="PathD10"/></clusters>'
            '<cluster name="Tree" lootmax="2"><container name="branch">'
            '<point pos="0 0 0"/></container></cluster></prototype>'
        )
        self.assertEqual(
            (True, ""), dashboard.ai_agent_validate_dayz_draft_semantics(
                "mapgroupcluster.xml", valid_cluster_placement, context
            )
        )
        self.assertIn(
            "rotation a must be numeric", dashboard.ai_agent_validate_dayz_draft_semantics(
                "mapgroupcluster.xml", invalid_cluster_placement, context
            )[1]
        )
        self.assertIn(
            "missing shape", dashboard.ai_agent_validate_dayz_draft_semantics(
                "mapclusterproto.xml", invalid_cluster_prototype, context
            )[1]
        )

    def test_dayz_custom_non_sakhal_effect_type_is_structurally_allowed(self):
        content = json.dumps({
            "Areas": [{
                "AreaName": "QAStaticSmoke",
                "Type": "ContaminatedArea_Static",
                "TriggerType": "EffectTrigger",
                "Data": {"Pos": [5000, 0, 5000], "Radius": 25},
            }]
        })

        self.assertEqual(
            (True, ""),
            dashboard.ai_agent_validate_dayz_draft_semantics(
                "custom/QAStaticSmoke.json", content, {"map": "chernarus"}
            ),
        )

    def test_dayz_spawn_gear_draft_rejects_unverified_new_classnames_but_preserves_existing_mod_classes(self):
        def preset(item_type):
            return json.dumps({
                "name": "QA Mod Survivor",
                "spawnWeight": 1,
                "characterTypes": [],
                "attachmentSlotItemSets": [{
                    "slotName": "Body",
                    "discreteItemSets": [{"itemType": item_type, "spawnWeight": 1, "quickBarSlot": -1}],
                }],
                "discreteUnsortedItemSets": [],
            })

        new_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "custom/QAModGear.json",
                "dayz_map": "livonia",
            },
            "Create spawn gear using ImaginaryModJacket.",
        )
        blocked_draft, blocked_error = dashboard.ai_agent_normalize_dayz_draft(
            {
                "target_path": "custom/QAModGear.json",
                "kind": "full_file",
                "content": preset("ImaginaryModJacket"),
            },
            new_context,
        )
        self.assertIsNone(blocked_draft)
        self.assertIn("not found in the selected map/version", blocked_error)

        existing_source = preset("ImaginaryModJacket")
        existing_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "custom/QAModGear.json",
                "dayz_map": "livonia",
                "dayz_source_mode": "complete",
                "dayz_file_source": existing_source,
            },
            "Validate the supplied existing modded spawn gear without changing its classname.",
        )
        preserved_draft, preserved_error = dashboard.ai_agent_normalize_dayz_draft(
            {
                "target_path": "custom/QAModGear.json",
                "kind": "full_file",
                "content": existing_source,
            },
            existing_context,
        )
        self.assertIsNotNone(preserved_draft, preserved_error)

    def test_dayz_semantic_validator_accepts_bundled_vanilla_core_files_for_every_map(self):
        references = (
            ("db/types.xml", ("db", "types.xml")),
            ("db/events.xml", ("db", "events.xml")),
            ("cfgspawnabletypes.xml", ("cfgspawnabletypes.xml",)),
            ("cfgeventspawns.xml", ("cfgeventspawns.xml",)),
            ("cfgeventgroups.xml", ("cfgeventgroups.xml",)),
            ("mapgrouppos.xml", ("mapgrouppos.xml",)),
            ("mapgroupproto.xml", ("mapgroupproto.xml",)),
            ("db/globals.xml", ("db", "globals.xml")),
            ("db/economy.xml", ("db", "economy.xml")),
            ("db/messages.xml", ("db", "messages.xml")),
            ("cfgeconomycore.xml", ("cfgeconomycore.xml",)),
            ("cfglimitsdefinition.xml", ("cfglimitsdefinition.xml",)),
            ("cfglimitsdefinitionuser.xml", ("cfglimitsdefinitionuser.xml",)),
            ("cfgrandompresets.xml", ("cfgrandompresets.xml",)),
            ("cfgignorelist.xml", ("cfgignorelist.xml",)),
            ("cfgplayerspawnpoints.xml", ("cfgplayerspawnpoints.xml",)),
            ("cfgenvironment.xml", ("cfgenvironment.xml",)),
            ("mapclusterproto.xml", ("mapclusterproto.xml",)),
            ("mapgroupcluster.xml", ("mapgroupcluster.xml",)),
            ("mapgroupcluster01.xml", ("mapgroupcluster01.xml",)),
            ("mapgroupdirt.xml", ("mapgroupdirt.xml",)),
            ("env/zombie_territories.xml", ("env", "zombie_territories.xml")),
            ("env/bear_territories.xml", ("env", "bear_territories.xml")),
        )
        for map_key in ("chernarus", "livonia", "sakhal"):
            for target_path, parts in references:
                content = dashboard.load_dayz_reference_text(map_key, *parts)
                if not content.strip():
                    continue
                with self.subTest(map=map_key, target=target_path):
                    self.assertEqual(
                        (True, ""),
                        dashboard.ai_agent_validate_dayz_draft_semantics(
                            target_path, content, {"map": map_key}
                        ),
                    )

    def test_ai_agent_only_charges_completed_answers(self):
        for status in ("deterministic_dayz_draft", "verified_dayz_reference"):
            with self.subTest(status=status):
                self.assertTrue(dashboard.ai_agent_answer_is_chargeable({"llm_status": status}))
        self.assertTrue(dashboard.ai_agent_answer_is_chargeable({"llm_status": "ok"}))
        self.assertFalse(dashboard.ai_agent_answer_is_chargeable({
            "llm_status": "ok",
            "dayz_context": {"support_mode": "fix_error"},
        }))
        self.assertFalse(dashboard.ai_agent_answer_is_chargeable({
            "llm_status": "ok",
            "objective": "Draft a complete validated cfgEffectArea.json file for offline review.",
            "dayz_context": {"enabled": True, "support_mode": "ask"},
        }))
        self.assertFalse(dashboard.ai_agent_answer_is_chargeable({
            "llm_status": "ok",
            "dayz_context": {"support_mode": "edit_file"},
            "dayz_draft_error": "invalid XML",
        }))
        self.assertTrue(dashboard.ai_agent_answer_is_chargeable({
            "llm_status": "ok",
            "dayz_context": {"support_mode": "edit_file"},
            "dayz_draft": {"id": "draft-qa", "target_path": "db/types.xml", "content": "<types/>"},
        }))
        self.assertFalse(dashboard.ai_agent_answer_is_chargeable({
            "llm_status": "ok",
            "dayz_context": {
                "support_mode": "create_file",
                "scenario": {"error": "The selected vehicle preset conflicts with the requested class."},
            },
        }))
        for status in ("failed", "not_configured", "dayz_input_required", ""):
            with self.subTest(status=status):
                self.assertFalse(dashboard.ai_agent_answer_is_chargeable({"llm_status": status}))
        self.assertFalse(dashboard.ai_agent_answer_is_chargeable(None))

    def test_plain_english_dayz_file_request_infers_protected_target_and_reference(self):
        context = dashboard.ai_agent_dayz_file_context(
            {"dayz_reference_mode": "none"},
            "Draft only: create a complete validated cfgEffectArea.json for a contaminated gas zone.",
        )

        self.assertEqual("cfgeffectarea.json", context["target_path"])
        self.assertTrue(context["target_inferred"])
        self.assertEqual("vanilla", context["reference"]["mode"])
        self.assertTrue(context["reference_base_available"])
        self.assertTrue(dashboard.ai_agent_dayz_request_requires_draft(context, context["objective"]))

    def test_draft_only_nitrado_wording_does_not_request_live_action_approval(self):
        objective = "Draft only; do not upload or change Nitrado. Create a validated cfgEffectArea.json file."
        plan = dashboard.ai_agent_plan_from_objective(objective, "auto", {"execute": False, "deploy": False}, {})

        self.assertEqual([], plan["approvals"])

    def test_ai_agent_chat_does_not_charge_when_model_answer_failed(self):
        auth = {"kind": "guild", "guild_id": "guild-qa"}
        access = {"label": "QA owner", "subject_key": "guild:guild-qa"}
        state = {}
        run = {"id": "run-qa"}
        task = {"id": "task-qa", "steps": [], "llm_status": "planned"}

        def failed_reply(*_args, **_kwargs):
            task["llm_status"] = "failed"
            task["llm_error"] = "OpenAI timeout"
            return "The model request failed; no completed answer was produced."

        with (
            patch.object(dashboard, "require_ai_agent_permission", return_value=(auth, access, state, None)),
            patch.object(dashboard, "request_payload", return_value={"prompt": "Create a complete DayZ file draft"}),
            patch.object(dashboard, "agent_credit_account_for_auth", return_value={"credits": 12}),
            patch.object(dashboard, "ai_agent_resolve_run_for_prompt", return_value=(run, False)),
            patch.object(dashboard, "ai_agent_chat_message", side_effect=[{"id": "user"}, {"id": "assistant"}]),
            patch.object(dashboard, "ai_agent_run_context_summary", return_value={}),
            patch.object(dashboard, "ai_agent_create_task_record", return_value=(task, None, "", 200)),
            patch.object(dashboard, "ai_agent_llm_reply_for_task", side_effect=failed_reply),
            patch.object(dashboard, "ai_agent_should_queue_chat_auto_job", return_value=False),
            patch.object(dashboard, "agent_charge_for_prompt") as charge,
            patch.object(dashboard, "agent_credit_balance_for_auth", return_value=12),
            patch.object(dashboard, "save_ai_agent_state"),
            patch.object(dashboard, "dashboard_api_response", side_effect=lambda _raw, body, *_args: body),
        ):
            response = dashboard.api_ai_agent_chat()

        charge.assert_not_called()
        self.assertTrue(response["ok"])
        self.assertEqual(12, response["credits_remaining"])

    def test_dayz_new_geometry_requests_stop_before_the_model_when_coordinates_are_missing(self):
        restricted_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "pra/QA_Bunker.json",
                "dayz_map": "sakhal",
            },
            "Create a restricted area with two boxes and six safe positions.",
        )
        underground_context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_custom_target_path": "custom/QA_Underground.json",
                "dayz_map": "sakhal",
            },
            "Create an underground trigger and breadcrumbs.",
        )

        restricted = dashboard.ai_agent_custom_json_missing_input(
            {"dayz_context": restricted_context}, "Create a restricted area with two boxes and six safe positions."
        )
        underground = dashboard.ai_agent_custom_json_missing_input(
            {"dayz_context": underground_context}, "Create an underground trigger and breadcrumbs."
        )

        self.assertIn("exact restricted-area geometry", restricted)
        self.assertIn("exact underground trigger geometry", underground)

    def test_dayz_vehicle_event_preserves_requested_rotation(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "db/events.xml",
                "dayz_map": "livonia",
                "dayz_scenario_type": "vehicle_spawn",
                "dayz_scenario_preset": "ada",
                "dayz_scenario_name": "QA Rotated Ada",
                "dayz_scenario_x": "5000",
                "dayz_scenario_z": "5000",
                "dayz_scenario_angle": "135.25",
            },
            "Prepare a rotated vehicle spawn event for offline review.",
        )

        drafts = dashboard.ai_agent_builtin_vehicle_event_drafts({"dayz_context": context})
        spawn_draft = next(item for item in drafts if item["target_path"] == "cfgeventspawns.xml")
        event_name = spawn_draft["scenario_event_name"]
        pos = ET.fromstring(spawn_draft["content"]).find(f"./event[@name='{event_name}']/pos")

        self.assertEqual(135.25, context["scenario"]["angle"])
        self.assertEqual("135.250000", pos.get("a"))

    def test_dayz_natural_language_profile_accepts_ordinary_non_military_clothing(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "db/types.xml",
                "dayz_map": "livonia",
                "dayz_reference_mode": "vanilla",
            },
            "Boost weapons, ammo and military clothing 200%; make ordinary non-Military clothing minimal.",
        )

        self.assertTrue(
            dashboard.ai_agent_types_boost_profile_requested(
                context, "Boost weapons, ammo and military clothing 200%; make ordinary non-Military clothing minimal."
            )
        )

    def test_dayz_agent_builds_matching_complete_vehicle_event_review_pair(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "edit_file",
                "dayz_file_target": "db/events.xml",
                "dayz_map": "livonia",
                "dayz_source_mode": "complete",
                "dayz_reference_mode": "vanilla",
                "dayz_scenario_type": "vehicle_spawn",
                "dayz_scenario_preset": "ada",
                "dayz_scenario_name": "QA Personal Ada",
                "dayz_scenario_x": "5000",
                "dayz_scenario_y": "0",
                "dayz_scenario_z": "5000",
                "dayz_scenario_radius": "30",
                "dayz_scenario_count": "1",
                "dayz_scenario_guild_id": "guild-1",
                "dayz_scenario_profile_id": "livo",
            },
            "Prepare a complete personal Ada vehicle spawn event for review only.",
        )
        drafts = dashboard.ai_agent_builtin_vehicle_event_drafts({"dayz_context": context})
        by_path = {draft["target_path"]: draft for draft in drafts}
        events_root = ET.fromstring(by_path["db/events.xml"]["content"])
        spawns_root = ET.fromstring(by_path["cfgeventspawns.xml"]["content"])
        event_name = by_path["db/events.xml"]["scenario_event_name"]
        event_node = events_root.find(f"./event[@name='{event_name}']")
        spawn_node = spawns_root.find(f"./event[@name='{event_name}']")
        event_package = by_path["db/events.xml"]["event_package"]

        self.assertEqual({"db/events.xml", "cfgeventspawns.xml"}, set(by_path))
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text("db/events.xml", by_path["db/events.xml"]["content"]))
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text("cfgeventspawns.xml", by_path["cfgeventspawns.xml"]["content"]))
        self.assertEqual(
            {"db/events.xml", "cfgeventspawns.xml", "cfgeventgroups.xml", "mapgroupproto.xml"},
            set(event_package["core_files"]),
        )
        self.assertEqual(["db/events.xml", "cfgeventspawns.xml"], event_package["changed_files"])
        self.assertEqual(["cfgeventgroups.xml", "mapgroupproto.xml"], event_package["preserved_files"])
        self.assertTrue(all(item["valid"] for item in event_package["checks"]))
        self.assertEqual(event_name, event_package["linked_event_name"])
        self.assertEqual("OffroadHatchback", event_node.find("./children/child").get("type"))
        self.assertEqual("mixed", event_node.findtext("limit"))
        self.assertEqual("5000", spawn_node.find("pos").get("x"))
        self.assertEqual("5000", spawn_node.find("pos").get("z"))
        self.assertEqual("0.000000", spawn_node.find("pos").get("a"))
        self.assertEqual(2, len(dashboard.ai_agent_dayz_draft_summaries({"tasks": [{"id": "qa", "dayz_drafts": drafts}]})))
        public = dashboard.ai_agent_public_task({"dayz_drafts": drafts})
        self.assertTrue(all("content" not in item for item in public["dayz_drafts"]))

    def test_builtin_dayz_draft_matrix_validates_across_supported_maps(self):
        maps = ("chernarus", "livonia", "sakhal")
        for map_key in maps:
            weather_context = dashboard.ai_agent_dayz_file_context(
                {
                    "project_type": "dayz_files",
                    "dayz_file_target": "cfgweather.xml",
                    "dayz_map": map_key,
                    "dayz_reference_mode": "preset",
                    "dayz_preset_id": "cfgweather_sunny_storms",
                },
                "Produce a mostly sunny weather file with partial rain and thunderstorms.",
            )
            weather_draft = dashboard.ai_agent_builtin_dayz_draft(
                {"dayz_context": weather_context},
                "Produce a mostly sunny weather file with partial rain and thunderstorms.",
            )
            self.assertIsNotNone(weather_draft, map_key)
            self.assertEqual((True, ""), dashboard.validate_dayz_upload_text("cfgweather.xml", weather_draft["content"]))

            for profile in ("full survivor", "medic", "scout"):
                loadout_context = dashboard.ai_agent_dayz_file_context(
                    {
                        "project_type": "dayz_files",
                        "dayz_file_target": "custom/spawnGearPreset.json",
                        "dayz_map": map_key,
                    },
                    f"Create a fully equipped {profile} fresh-spawn loadout.",
                )
                loadout_draft = dashboard.ai_agent_builtin_dayz_draft(
                    {"dayz_context": loadout_context},
                    f"Create a fully equipped {profile} fresh-spawn loadout with an M4A1.",
                )
                self.assertIsNotNone(loadout_draft, f"{map_key} {profile}")
                self.assertEqual(
                    (True, ""),
                    dashboard.validate_dayz_upload_text("custom/spawnGearPreset.json", loadout_draft["content"]),
                )

            for preset_id in dashboard.SCENARIO_VEHICLE_PRESETS:
                payload = {
                    "project_type": "dayz_files",
                    "dayz_file_target": "db/events.xml",
                    "dayz_map": map_key,
                    "dayz_scenario_type": "vehicle_spawn",
                    "dayz_scenario_preset": preset_id,
                    "dayz_scenario_name": f"QA {preset_id} {map_key}",
                    "dayz_scenario_x": "5000",
                    "dayz_scenario_z": "5000",
                    "dayz_scenario_guild_id": "qa",
                    "dayz_scenario_profile_id": "qa",
                }
                if preset_id == "custom_vehicle":
                    payload["dayz_scenario_class"] = "OffroadHatchback"
                context = dashboard.ai_agent_dayz_file_context(payload, "Create a personal vehicle spawn event for offline review.")
                drafts = dashboard.ai_agent_builtin_vehicle_event_drafts({"dayz_context": context})
                self.assertEqual(2, len(drafts), f"{map_key} {preset_id}")
                by_path = {draft["target_path"]: draft for draft in drafts}
                for target_path, draft in by_path.items():
                    self.assertEqual((True, ""), dashboard.validate_dayz_upload_text(target_path, draft["content"]))
                event_name = by_path["db/events.xml"]["scenario_event_name"]
                event_root = ET.fromstring(by_path["db/events.xml"]["content"])
                spawns_root = ET.fromstring(by_path["cfgeventspawns.xml"]["content"])
                self.assertIsNotNone(event_root.find(f"./event[@name='{event_name}']"))
                self.assertIsNotNone(spawns_root.find(f"./event[@name='{event_name}']"))
                self.assertTrue(all(check["valid"] for check in by_path["db/events.xml"]["event_package"]["checks"]))

    def test_vehicle_scenario_is_not_reduced_to_plain_event_link_guidance(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_file_target": "db/events.xml",
                "dayz_map": "livonia",
                "dayz_scenario_type": "vehicle_spawn",
                "dayz_scenario_preset": "ada",
                "dayz_scenario_name": "QA Linked Ada",
                "dayz_scenario_x": "7000",
                "dayz_scenario_y": "0",
                "dayz_scenario_z": "9000",
                "dayz_scenario_guild_id": "guild-1",
                "dayz_scenario_profile_id": "livo",
            },
            "Generate matching events.xml and cfgeventspawns.xml records for a linked vehicle event.",
        )
        task = {"id": "qa-vehicle", "dayz_context": context, "project_type": "dayz_files"}

        reply = dashboard.ai_agent_llm_reply_for_task(
            {}, {}, {"label": "QA owner"}, {}, task, None,
            "Generate matching events.xml and cfgeventspawns.xml records for this linked vehicle event.",
            False,
        )

        self.assertEqual("deterministic_dayz_draft", task["llm_status"])
        self.assertEqual({"db/events.xml", "cfgeventspawns.xml"}, {item["target_path"] for item in task["dayz_drafts"]})
        self.assertIn("Four-core-file CE audit passed", reply)

    def test_event_position_edit_is_not_reduced_to_plain_event_link_guidance(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "edit_file",
                "dayz_file_target": "cfgeventspawns.xml",
                "dayz_map": "livonia",
                "dayz_source_mode": "fragment",
                "dayz_file_source": (
                    '<eventposdef><event name="VehicleQA_NorthConvoy">'
                    '<pos x="7000" z="9000" a="0.000000"/>'
                    "</event></eventposdef>"
                ),
            },
            "Add three matching CE positions for VehicleQA_NorthConvoy in cfgeventspawns.xml.",
        )
        task = {"id": "qa-spawn-points", "dayz_context": context, "project_type": "dayz_files"}

        with patch.object(dashboard, "ai_agent_llm_is_configured", return_value=False):
            reply = dashboard.ai_agent_llm_reply_for_task(
                {}, {}, {"label": "QA owner"}, {}, task, None,
                "Add matching positions in cfgeventspawns.xml; the event name must match events.xml.",
                False,
            )

        self.assertEqual("not_configured", task["llm_status"])
        self.assertIn("merge-only reference section", reply)
        self.assertNotEqual("Verified DayZ CE event-name linkage guidance.", task.get("summary"))

    def test_full_survivor_spawn_gear_draft_is_complete_and_uses_livonia_classes(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "edit_file",
                "dayz_file_target": "custom/spawnGearPreset.json",
                "dayz_map": "livonia",
                "dayz_source_mode": "complete",
                "dayz_reference_mode": "none",
            },
            "Create a fully equipped full survivor fresh-spawn loadout with an M4A1.",
        )
        draft = dashboard.ai_agent_builtin_dayz_draft(
            {"dayz_context": context},
            "Create a fully equipped full survivor fresh-spawn loadout with an M4A1, food, medical gear and navigation.",
        )

        self.assertIsNotNone(draft)
        self.assertEqual("custom/spawnGearPreset.json", draft["target_path"])
        self.assertEqual("spawning_gear", draft["custom_json_schema"])
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text(draft["target_path"], draft["content"]))
        payload = json.loads(draft["content"])
        self.assertEqual("Wandering Bot Full Survivor", payload["name"])
        vanilla_names = {
            node.get("name")
            for node in ET.fromstring(dashboard.load_dayz_reference_text("livonia", "db", "types.xml")).findall("type")
        }
        self.assertTrue(set(dashboard.iter_player_loadout_classnames(payload)).issubset(vanilla_names))

        def item_with_class(value, class_name):
            if isinstance(value, dict):
                if value.get("itemType") == class_name:
                    return value
                for child in value.values():
                    found = item_with_class(child, class_name)
                    if found:
                        return found
            if isinstance(value, list):
                for child in value:
                    found = item_with_class(child, class_name)
                    if found:
                        return found
            return None

        self.assertEqual(1, item_with_class(payload, "M4A1")["quickBarSlot"])
        self.assertEqual(2, item_with_class(payload, "FNX45")["quickBarSlot"])
        self.assertEqual(5, item_with_class(payload, "Canteen")["quickBarSlot"])
        self.assertIn("PlayerData.spawnGearPresetFiles", draft["cfggameplay_reference"])
        self.assertIn("./custom/spawnGearPreset.json", draft["cfggameplay_reference"])

        medic_draft = dashboard.ai_agent_builtin_dayz_draft(
            {"dayz_context": context},
            "Create a fully equipped medic fresh-spawn loadout with a full medical kit.",
        )
        medic_payload = json.loads(medic_draft["content"])
        self.assertEqual("Wandering Bot Field Medic", medic_payload["name"])
        self.assertIsNotNone(item_with_class(medic_payload, "BloodBagIV"))
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text(medic_draft["target_path"], medic_draft["content"]))

        scout_draft = dashboard.ai_agent_builtin_dayz_draft(
            {"dayz_context": context},
            "Create a fully equipped scout fresh-spawn loadout with navigation and survival tools.",
        )
        scout_payload = json.loads(scout_draft["content"])
        self.assertEqual("Wandering Bot Field Scout", scout_payload["name"])
        self.assertEqual(7, item_with_class(scout_payload, "Binoculars")["quickBarSlot"])
        self.assertEqual((True, ""), dashboard.validate_dayz_upload_text(scout_draft["target_path"], scout_draft["content"]))

    def test_invalid_model_dayz_json_is_never_reported_as_a_saved_draft(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "edit_file",
                "dayz_file_target": "custom/spawnGearPreset.json",
                "dayz_map": "livonia",
                "dayz_source_mode": "complete",
            },
            "Create a simple starter gear preset.",
        )
        task = {"id": "qa-invalid-spawn-gear", "dayz_context": context, "project_type": "dayz_files"}
        model_reply = {
            "reply": "Created a complete starter loadout.",
            "dayz_draft": {
                "target_path": "custom/spawnGearPreset.json",
                "kind": "full_file",
                "content": json.dumps({"starterItems": ["BandageDressing"]}),
                "summary": "Invalid test draft",
            },
        }
        with patch.object(dashboard, "ai_agent_llm_is_configured", return_value=True), patch.object(
            dashboard, "ai_agent_llm_json", return_value=(True, model_reply, "")
        ):
            reply = dashboard.ai_agent_llm_reply_for_task(
                {}, {}, {"label": "QA owner"}, {}, task, None,
                "Create a simple starter gear preset.", False,
            )

        self.assertNotIn("dayz_draft", task)
        self.assertIn("failed the protected validator", reply)
        self.assertNotIn("Created a complete starter loadout", reply)

    def test_model_plan_without_requested_file_is_incomplete_and_not_chargeable(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "fix_error",
                "dayz_file_target": "cfgrandompresets.xml",
                "dayz_map": "chernarus",
                "dayz_source_mode": "complete",
                "dayz_file_source": (
                    '<randompresets><cargo name="Broken" chance="2.5">'
                    '<item name="TunaCan" chance="1"/></randompresets>'
                ),
            },
            "Repair the malformed complete cfgrandompresets.xml and return a validated file.",
        )
        task = {
            "id": "qa-missing-repair-draft",
            "dayz_context": context,
            "project_type": "dayz_files",
            "steps": [],
            "suggested_commands": [],
        }
        model_reply = {
            "reply": "I repaired the XML and it is ready for review.",
            "summary": "Repair complete.",
            "next_action": "Approve the repaired file.",
        }

        with patch.object(dashboard, "ai_agent_llm_is_configured", return_value=True), patch.object(
            dashboard, "ai_agent_llm_json", return_value=(True, model_reply, "")
        ):
            reply = dashboard.ai_agent_llm_reply_for_task(
                {}, {}, {"label": "QA owner"}, {}, task, None,
                "Repair the malformed complete cfgrandompresets.xml and return a validated file.", False,
            )

        self.assertEqual("incomplete", task["llm_status"])
        self.assertNotIn("dayz_draft", task)
        self.assertFalse(dashboard.ai_agent_answer_is_chargeable(task))
        self.assertIn("No usable DayZ draft", reply)
        self.assertIn("no DayZ file draft", reply)
        self.assertNotIn("I repaired the XML", reply)

    def test_model_gets_one_guarded_retry_to_supply_an_omitted_repair_draft(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "fix_error",
                "dayz_file_target": "cfgrandompresets.xml",
                "dayz_map": "chernarus",
                "dayz_source_mode": "complete",
                "dayz_file_source": (
                    '<randompresets><cargo name="Broken" chance="2.5">'
                    '<item name="TunaCan" chance="1"/></randompresets>'
                ),
            },
            "Repair the malformed complete cfgrandompresets.xml.",
        )
        task = {
            "id": "qa-repair-retry",
            "dayz_context": context,
            "project_type": "dayz_files",
            "steps": [],
            "suggested_commands": [],
        }
        first_reply = {"reply": "The repair is ready.", "summary": "Repair complete."}
        retry_reply = {
            "reply": "Prepared the corrected complete XML draft.",
            "dayz_draft": {
                "target_path": "cfgrandompresets.xml",
                "kind": "full_file",
                "content": (
                    '<randompresets><cargo name="Broken" chance="1">'
                    '<item name="TunaCan" chance="1"/></cargo></randompresets>'
                ),
                "summary": "Closed the cargo record and supplied valid probabilities.",
            },
        }

        with patch.object(dashboard, "ai_agent_llm_is_configured", return_value=True), patch.object(
            dashboard, "ai_agent_llm_json",
            side_effect=[(True, first_reply, ""), (True, retry_reply, "")],
        ) as model_call:
            reply = dashboard.ai_agent_llm_reply_for_task(
                {}, {}, {"label": "QA owner"}, {}, task, None,
                "Repair the malformed complete cfgrandompresets.xml.", False,
            )

        self.assertEqual(2, model_call.call_count)
        self.assertEqual("ok", task["llm_status"])
        self.assertEqual("passed", task["dayz_draft"]["validation"])
        self.assertTrue(dashboard.ai_agent_answer_is_chargeable(task))
        self.assertIn("DayZ draft ready for download", reply)
        retry_payload = model_call.call_args_list[1].args[1]
        self.assertIn("omitted", retry_payload["draft_retry"]["reason"])

    def test_model_objectspawner_draft_is_saved_only_after_protected_validation(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "create_file",
                "dayz_custom_target_path": "custom/QA_AirdropScene.json",
                "dayz_map": "chernarus",
                "dayz_source_mode": "complete",
                "dayz_file_source": json.dumps({
                    "Objects": [{
                        "name": "Land_Roadblock_WoodenCrate",
                        "pos": [5000.0, 200.0, 5000.0],
                        "ypr": [0.0, 0.0, 0.0],
                    }]
                }),
            },
            "Create ObjectSpawner JSON: Land_Roadblock_WoodenCrate at [5000,200,5000] with ypr [0,0,0].",
        )
        task = {
            "id": "qa-airdrop-scene",
            "project_type": "dayz_files",
            "dayz_context": context,
            "steps": [],
            "suggested_commands": [],
        }
        model_reply = {
            "reply": "Prepared an offline ObjectSpawner draft.",
            "summary": "Static ObjectSpawner scene for review.",
            "dayz_draft": {
                "target_path": "custom/QA_AirdropScene.json",
                "kind": "full_file",
                "content": json.dumps({
                    "Objects": [
                        {
                            "name": "Land_Roadblock_WoodenCrate",
                            "pos": [5000.0, 200.0, 5000.0],
                            "ypr": [0.0, 0.0, 0.0],
                        }
                    ]
                }),
                "summary": "Validated static airdrop scene; add its path to WorldsData.objectSpawnersArr.",
            },
        }

        with patch.object(dashboard, "ai_agent_llm_is_configured", return_value=True), patch.object(
            dashboard, "ai_agent_llm_json", return_value=(True, model_reply, "")
        ):
            reply = dashboard.ai_agent_llm_reply_for_task(
                {}, {}, {"label": "QA owner"}, {}, task, None,
                "Create ObjectSpawner JSON: Land_Roadblock_WoodenCrate at [5000,200,5000] with ypr [0,0,0].", False,
            )

        self.assertEqual("ok", task["llm_status"])
        self.assertEqual("custom/QA_AirdropScene.json", task["dayz_draft"]["target_path"])
        self.assertEqual("objectspawner", task["dayz_draft"]["custom_json_schema"])
        self.assertEqual("passed", task["dayz_draft"]["validation"])
        self.assertIn("DayZ draft ready for download", reply)

    def test_model_linked_event_package_requires_matching_names_and_valid_selected_map_class(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "edit_file",
                "dayz_file_target": "db/events.xml",
                "dayz_map": "chernarus",
            },
            "Create a custom vehicle event and matching event spawn at 5000 5000.",
        )
        event_patch = (
            '<events><event name="VehicleQAPackage"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>3888000</lifetime><restock>0</restock><saferadius>500</saferadius>'
            '<distanceradius>500</distanceradius><cleanupradius>200</cleanupradius>'
            '<flags deletable="1" init_random="0" remove_damaged="1"/><position>fixed</position>'
            '<limit>mixed</limit><active>1</active><children><child lootmax="0" lootmin="0" '
            'max="1" min="1" type="OffroadHatchback"/></children></event></events>'
        )
        spawn_patch = (
            '<eventposdef><event name="VehicleQAPackage"><pos x="5000" z="5000" '
            'a="135.000000"/></event></eventposdef>'
        )
        data = {
            "dayz_drafts": [
                {"target_path": "db/events.xml", "kind": "patch", "content": event_patch},
                {"target_path": "cfgeventspawns.xml", "kind": "patch", "content": spawn_patch},
            ]
        }

        drafts, error = dashboard.ai_agent_normalize_dayz_draft_package(data, context)

        self.assertEqual("", error)
        self.assertEqual({"db/events.xml", "cfgeventspawns.xml"}, {item["target_path"] for item in drafts})

        mismatched = copy.deepcopy(data)
        mismatched["dayz_drafts"][1]["content"] = spawn_patch.replace("VehicleQAPackage", "VehicleWrongName")
        mismatch_drafts, mismatch_error = dashboard.ai_agent_normalize_dayz_draft_package(mismatched, context)
        self.assertEqual([], mismatch_drafts)
        self.assertIn("do not match exactly", mismatch_error)

        unknown = copy.deepcopy(data)
        unknown["dayz_drafts"][0]["content"] = event_patch.replace("OffroadHatchback", "DefinitelyNotAVanillaClass")
        unknown_drafts, unknown_error = dashboard.ai_agent_normalize_dayz_draft_package(unknown, context)
        self.assertEqual([], unknown_drafts)
        self.assertIn("not present", unknown_error)

        missing_child = copy.deepcopy(data)
        missing_child["dayz_drafts"][0]["content"] = event_patch.replace(
            '<child lootmax="0" lootmin="0" max="1" min="1" type="OffroadHatchback"/>', ''
        )
        missing_child_drafts, missing_child_error = dashboard.ai_agent_normalize_dayz_draft_package(missing_child, context)
        self.assertEqual([], missing_child_drafts)
        self.assertIn("needs at least one", missing_child_error)

        missing_position = copy.deepcopy(data)
        missing_position["dayz_drafts"][1]["content"] = spawn_patch.replace(
            '<pos x="5000" z="5000" a="135.000000"/>', ''
        )
        missing_position_drafts, missing_position_error = dashboard.ai_agent_normalize_dayz_draft_package(missing_position, context)
        self.assertEqual([], missing_position_drafts)
        self.assertIn("needs at least one <pos>", missing_position_error)

    def test_linked_map_group_package_requires_matching_placement_and_prototype_names(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "edit_file",
                "dayz_file_target": "mapgrouppos.xml",
                "dayz_map": "chernarus",
            },
            "Place a new loot-bearing static building and define its matching loot prototype.",
        )
        placement = (
            '<map><group name="QACastleLoot" pos="5000 25 6000" rpy="0 0 90"/></map>'
        )
        prototype = (
            '<prototype><group name="QACastleLoot" lootmax="1"><container name="loot" lootmax="1">'
            '<point pos="0 0 0"/></container></group></prototype>'
        )
        package = {
            "dayz_drafts": [
                {"target_path": "mapgrouppos.xml", "kind": "patch", "content": placement},
                {"target_path": "mapgroupproto.xml", "kind": "patch", "content": prototype},
            ]
        }

        drafts, error = dashboard.ai_agent_normalize_dayz_draft_package(package, context)
        self.assertEqual("", error)
        self.assertEqual({"mapgrouppos.xml", "mapgroupproto.xml"}, {item["target_path"] for item in drafts})

        mismatched = copy.deepcopy(package)
        mismatched["dayz_drafts"][1]["content"] = prototype.replace("QACastleLoot", "QAWrongPrototype")
        mismatch_drafts, mismatch_error = dashboard.ai_agent_normalize_dayz_draft_package(mismatched, context)
        self.assertEqual([], mismatch_drafts)
        self.assertIn("do not have matching mapgroupproto.xml prototypes", mismatch_error)

    def test_invalid_model_dayz_xml_is_never_reported_as_a_saved_draft(self):
        context = dashboard.ai_agent_dayz_file_context(
            {
                "project_type": "dayz_files",
                "dayz_support_mode": "edit_file",
                "dayz_file_target": "db/messages.xml",
                "dayz_map": "chernarus",
                "dayz_reference_mode": "vanilla",
            },
            "Create a concise on-screen server message file.",
        )
        task = {"id": "qa-invalid-messages", "project_type": "dayz_files", "dayz_context": context, "steps": [], "suggested_commands": []}
        model_reply = {
            "reply": "Created a server message file.",
            "dayz_draft": {
                "target_path": "db/messages.xml",
                "kind": "full_file",
                "content": "<messages><message></messages>",
                "summary": "Invalid test messages draft",
            },
        }

        with patch.object(dashboard, "ai_agent_llm_is_configured", return_value=True), patch.object(
            dashboard, "ai_agent_llm_json", return_value=(True, model_reply, "")
        ):
            reply = dashboard.ai_agent_llm_reply_for_task(
                {}, {}, {"label": "QA owner"}, {}, task, None,
                "Create a concise on-screen server message file.", False,
            )

        self.assertNotIn("dayz_draft", task)
        self.assertIn("failed the protected validator", reply)
        self.assertNotIn("Created a server message file", reply)

    def test_dayz_event_plan_identifies_the_linked_ce_files_and_validates_coordinates(self):
        scenario = dashboard.ai_agent_dayz_scenario_from_payload(
            {
                "dayz_scenario_type": "vehicle_spawn",
                "dayz_scenario_preset": "m3s",
                "dayz_scenario_name": "Trader Truck",
                "dayz_scenario_x": "4481",
                "dayz_scenario_z": "10355",
                "dayz_scenario_radius": "10",
                "dayz_scenario_guild_id": "guild-1",
                "dayz_scenario_profile_id": "cherno",
            },
            "chernarus",
        )
        invalid = dashboard.ai_agent_dayz_scenario_from_payload(
            {"dayz_scenario_type": "airdrop", "dayz_scenario_x": "999999", "dayz_scenario_z": "10"},
            "chernarus",
        )
        conflicting_vehicle = dashboard.ai_agent_dayz_scenario_from_payload(
            {
                "dayz_scenario_type": "vehicle_spawn",
                "dayz_scenario_preset": "ada",
                "dayz_scenario_class": "Hatchback_02",
                "dayz_scenario_x": "4481",
                "dayz_scenario_z": "10355",
            },
            "chernarus",
        )

        self.assertEqual("vehicle_spawn", scenario["event_type"])
        self.assertIn("db/events.xml", scenario["files"])
        self.assertEqual(
            ["db/events.xml", "cfgeventspawns.xml", "cfgeventgroups.xml", "mapgroupproto.xml"],
            scenario["core_files"],
        )
        self.assertEqual(["db/events.xml", "cfgeventspawns.xml"], scenario["changed_files"])
        self.assertEqual(["cfgeventgroups.xml", "mapgroupproto.xml"], scenario["preserved_files"])
        self.assertEqual("checked", scenario["file_plan"][2]["action"])
        self.assertIn("no group= reference", scenario["file_plan"][2]["role"])
        self.assertIn("cfgspawnabletypes.xml", scenario["files"])
        self.assertTrue(scenario["can_apply"])
        self.assertIn("map bounds", invalid["error"])
        self.assertIn("preset uses OffroadHatchback", conflicting_vehicle["error"])
        self.assertIn("supplied classname is Hatchback_02", conflicting_vehicle["error"])
        self.assertIn('name="dayz_error_text"', dashboard.PAGE_TEMPLATE)
        self.assertIn('name="dayz_scenario_type"', dashboard.PAGE_TEMPLATE)
        self.assertIn("AI can be wrong", dashboard.PAGE_TEMPLATE)

    def test_gas_zone_plan_includes_effect_dependencies_and_keeps_ce_group_files_safe(self):
        scenario = dashboard.ai_agent_dayz_scenario_from_payload(
            {
                "dayz_scenario_type": "gas_zone",
                "dayz_scenario_preset": "gas_temp",
                "dayz_scenario_name": "QA South Gas",
                "dayz_scenario_x": "7000",
                "dayz_scenario_y": "0",
                "dayz_scenario_z": "9000",
                "dayz_scenario_radius": "125",
                "dayz_scenario_count": "1",
                "dayz_scenario_guild_id": "guild-1",
                "dayz_scenario_profile_id": "livo",
            },
            "livonia",
        )

        self.assertEqual("gas_zone", scenario["event_type"])
        self.assertEqual("ContaminatedArea_Dynamic", scenario["class_name"])
        self.assertEqual(125, scenario["radius"])
        self.assertEqual(["db/events.xml", "cfgeventspawns.xml"], scenario["changed_files"])
        self.assertEqual(["cfgeventgroups.xml", "mapgroupproto.xml"], scenario["preserved_files"])
        self.assertTrue({"cfgareaeffects.xml", "cfgeffectarea.json"}.issubset(set(scenario["files"])))
        self.assertTrue(scenario["can_apply"])

    def test_ai_agent_dayz_targets_cover_standard_dayz_support_files(self):
        targets = {target for target, _label in dashboard.AI_AGENT_DAYZ_TARGETS}
        self.assertTrue({
            "cfgplayerspawnpoints.xml",
            "cfgignorelist.xml",
            "cfglimitsdefinition.xml",
            "cfglimitsdefinitionuser.xml",
            "cfgrandompresets.xml",
            "cfgundergroundtriggers.json",
            "env/zombie_territories.xml",
            "env/bear_territories.xml",
        }.issubset(targets))

    def test_versioned_owner_reference_overlay_keeps_bundled_files_and_can_be_activated(self):
        class UploadedZip:
            filename = "dayzOffline.chernarusplus-1.29.163451.zip"

            def __init__(self, payload):
                self.payload = payload

            def read(self, _limit=None):
                return self.payload

        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("release/dayzOffline.chernarusplus/db/types.xml", "<?xml version='1.0'?><types><type name='NewHotfixWeapon'/></types>")
            archive.writestr("release/dayzOffline.chernarusplus/cfggameplay.json", '{"version": 119}')
            archive.writestr("release/dayzOffline.chernarusplus/areaflags.map", b"binary-map-data")

        original_data_root = dashboard.DATA_ROOT
        original_library_folder = dashboard.DAYZ_REFERENCE_LIBRARY_FOLDER
        with tempfile.TemporaryDirectory() as temp_root:
            try:
                dashboard.DATA_ROOT = temp_root
                dashboard.DAYZ_REFERENCE_LIBRARY_FOLDER = os.path.join(temp_root, "reference-library")
                release = dashboard.store_dayz_reference_archive(
                    "chernarus", "1.29.163451", UploadedZip(archive_bytes.getvalue()), "official hotfix"
                )
                self.assertEqual("1.29.163451", release["version"])
                self.assertEqual(2, release["file_count"])
                self.assertEqual(1, release["ignored_file_count"])

                library = dashboard.load_dayz_reference_library()
                entry = library["maps"].setdefault("chernarus", {"active_release_id": "", "releases": []})
                entry["releases"].append(release)
                entry["active_release_id"] = release["id"]
                dashboard.save_dayz_reference_library(library)

                self.assertEqual("1.29.163451", dashboard.dayz_reference_version_for_map("chernarus"))
                self.assertIn("NewHotfixWeapon", dashboard.load_dayz_reference_text("chernarus", "db", "types.xml"))
                self.assertTrue(os.path.exists(os.path.join(
                    dashboard.DAYZ_REFERENCE_LIBRARY_FOLDER,
                    "chernarus",
                    release["id"],
                    "dayzOffline.chernarusplus",
                    "db",
                    "types.xml",
                )))
            finally:
                dashboard.DATA_ROOT = original_data_root
                dashboard.DAYZ_REFERENCE_LIBRARY_FOLDER = original_library_folder

    def test_public_setup_guide_uses_the_support_discord_invite(self):
        self.assertTrue(dashboard.SUPPORT_DISCORD_URL)
        self.assertIn(dashboard.SUPPORT_DISCORD_URL, dashboard.public_setup_guide_download_text())

    def test_public_homepage_has_discord_and_email_support_routes(self):
        self.assertIn("Join support Discord", dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertIn("mailto:{{ support_email }}", dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertIn("Android + iPhone App", dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertIn("Activate, monitor and control your server from your phone", dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertIn("Let your community speak its own language", dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertIn("Stripe promotion codes and discounts", dashboard.PAGE_TEMPLATE)
        self.assertTrue(dashboard.PUBLIC_SUPPORT_EMAIL)

    def test_pro_plan_includes_automatic_translation_and_anonymised_examples(self):
        plans = {plan["id"]: plan for plan in dashboard.default_billing_plan_map().values()}
        public_plans = {plan["id"]: plan for plan in dashboard.public_billing_plans_for_homepage()}

        self.assertEqual("€11.99 / month", plans["dashboard_ai"]["price_text"])
        self.assertTrue(plans["dashboard_ai"]["features"]["translation"])
        self.assertTrue(plans["dashboard_ultimate"]["features"]["translation"])
        self.assertIn("Automatic Discord translation in the same channel or a dedicated translation channel", public_plans["dashboard_ai"]["public_features"])
        self.assertEqual("Translation included", public_plans["dashboard_ai"]["public_badge"])
        self.assertEqual(2, len(dashboard.public_translation_preview_items()))


if __name__ == "__main__":
    unittest.main()
