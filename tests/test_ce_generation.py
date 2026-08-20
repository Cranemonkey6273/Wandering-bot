"""Regression tests for the Wandering-bot DayZ native CE XML generator.

These cover the two root-cause fixes made in response to the production RPT
symptom: WanderingBot event definitions appeared in the live RPT but DayZ
never produced any spawn lines for them.

Root cause 1 ? events.xml ``<children>`` was non-empty for events that
referenced an entry in ``cfgeventgroups.xml`` through a ``<pos group="...">``
attribute in ``cfgeventspawns.xml``. Vanilla DayZ Livonia events such as
``StaticMilitaryConvoy`` keep ``<children/>`` empty in that pattern, and DayZ
silently refuses to instantiate the event when both spawn paths are populated.

Root cause 2 ? ``cfgeventspawns.xml`` ``<pos>`` entries included a ``y``
attribute. Vanilla DayZ Livonia ``cfgeventspawns.xml`` only carries ``x``,
``z`` and ``a``; the engine samples terrain height itself. Forcing ``y=0``
makes vehicles and static crates fail to spawn on Livonia terrain.
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class DeliveryCoordinateTests(unittest.TestCase):
    def test_new_shop_delivery_uses_dayz_x_y_z_order(self):
        xml_text = bot.build_delivery_xml(
            [{"item": "NailBox", "x": "123", "y": "0", "z": "456"}],
            [],
        )

        self.assertIn('name="NailBox" pos="123.0 0.0 456.0"', xml_text)

    def test_legacy_shop_delivery_treats_old_y_field_as_horizontal_z(self):
        xml_text = bot.build_delivery_xml(
            [{"item": "NailBox", "x": "123", "y": "456"}],
            [],
        )

        self.assertIn('name="NailBox" pos="123.0 0.0 456.0"', xml_text)

    def test_delivery_bridge_grounds_zero_height_to_terrain(self):
        self.assertIn("SurfaceY(pos[0], pos[2])", bot.WANDERING_DELIVERY_BRIDGE_CODE)

    def test_delivery_bridge_preserves_explicit_height(self):
        xml_text = bot.build_delivery_xml(
            [{"item": "NailBox", "x": "123", "y": "42.5", "z": "456"}],
            [],
        )

        self.assertIn('name="NailBox" pos="123.0 42.5 456.0"', xml_text)

    def test_delivery_xml_has_stable_one_shot_batch_id(self):
        items = [{"item": "NailBox", "x": "123", "y": "0", "z": "456"}]
        batch_id = bot.delivery_batch_id(items, [], generation_key="2026-08-12T12:00:00+00:00")
        first = bot.build_delivery_xml(items, [], batch_id=batch_id)
        second = bot.build_delivery_xml(items, [], batch_id=batch_id)

        self.assertEqual(first.splitlines()[0], second.splitlines()[0])
        self.assertRegex(first.splitlines()[0], r'^<objects batch_id="[a-f0-9]{32}">$')
        later_batch = bot.delivery_batch_id(items, [], generation_key="2026-08-12T16:00:00+00:00")
        self.assertNotEqual(batch_id, later_batch)

    def test_delivery_bridge_skips_and_records_completed_batch(self):
        bridge = bot.WANDERING_DELIVERY_BRIDGE_CODE

        self.assertIn("WANDERING BOT BRIDGE v6", bridge)
        self.assertIn('$profile:WanderingBotLastDeliveryBatch.txt', bridge)
        self.assertIn('completedBatch == batchId', bridge)
        self.assertIn('OpenFile(completedBatchPath, FileMode.WRITE)', bridge)

    def test_old_delivery_bridge_version_is_not_considered_safe(self):
        old = {
            "server_platform": "pc",
            "dayz_delivery_bridge": {
                "installed_at": "2026-08-01T00:00:00+00:00",
                "bridge_version": bot.WANDERING_DELIVERY_BRIDGE_VERSION - 1,
            },
        }
        current = {
            "server_platform": "pc",
            "dayz_delivery_bridge": {
                "installed_at": "2026-08-01T00:00:00+00:00",
                "bridge_version": bot.WANDERING_DELIVERY_BRIDGE_VERSION,
            },
        }

        self.assertFalse(bot.delivery_bridge_runtime_supported(old))
        self.assertTrue(bot.delivery_bridge_runtime_supported(current))


class ShopDeliveryRoutingTests(unittest.TestCase):
    def test_shop_bundle_expansion_has_a_safe_precharge_limit(self):
        allowed = {"Hacksaw": bot.MAX_SHOP_DELIVERY_ITEMS_PER_ORDER}
        oversized = {"Hacksaw": bot.MAX_SHOP_DELIVERY_ITEMS_PER_ORDER + 1}

        self.assertEqual("", bot.shop_delivery_size_error(allowed))
        self.assertIn("safe maximum", bot.shop_delivery_size_error(oversized))

    def test_single_server_autocomplete_returns_only_server(self):
        class Guild:
            id = 987654321

        class Interaction:
            guild = Guild()

        config = {
            "server_name": "Odyssey",
            "server_map": "chernarus",
            "server_platform": "xbox",
        }
        class Choice:
            def __init__(self, name, value):
                self.name = name
                self.value = value

        bot.guild_configs[str(Guild.id)] = config
        try:
            with patch.object(bot.app_commands, "Choice", Choice):
                choices = asyncio.run(bot.server_profile_autocomplete(Interaction(), ""))
        finally:
            bot.guild_configs.pop(str(Guild.id), None)

        self.assertEqual(1, len(choices))
        self.assertIn("Odyssey", choices[0].name)
        self.assertTrue(choices[0].value)

    def test_console_ground_shop_delivery_builds_one_time_item_event(self):
        config = {}
        created = bot.create_console_shop_delivery_events(
            config,
            {"Hacksaw": 3},
            8194,
            9092,
            "order-1",
            "Player",
            "123",
        )

        self.assertEqual(1, len(created))
        event = created[0]
        self.assertEqual("shop_delivery", event["event_type"])
        self.assertEqual(1, event["remaining_restarts"])
        self.assertEqual("native_xml_only", event["delivery_route"])

        records, warnings = bot.console_ce_records_for_event(event)
        self.assertFalse(warnings)
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertTrue(record["name"].startswith("ItemWanderingBot_"))
        self.assertEqual(3, record["nominal"])
        self.assertEqual(3, record["min_count"])
        self.assertEqual(3, record["max_count"])
        self.assertEqual("Hacksaw", record["child_records"][0]["type"])
        self.assertEqual(3, record["child_records"][0]["count"])
        self.assertEqual(3, len(record["spawn_positions"]))
        self.assertEqual(3, len({
            (position["x"], position["z"])
            for position in record["spawn_positions"]
        }))

        spawns = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(
            spawns,
            record["name"],
            record["x"],
            record["z"],
            y=record.get("y"),
        )
        position = spawns.find("event/pos")
        self.assertIsNotNone(position)
        self.assertNotIn("y", position.attrib)

    def test_console_lumber_pile_delivery_uses_separate_ce_positions(self):
        config = {}
        created = bot.create_console_shop_delivery_events(
            config,
            {"PileOfWoodenPlanks": 4},
            8194,
            9092,
            "order-lumber",
            "Player",
            "123",
        )

        records, warnings = bot.console_ce_records_for_event(created[0])
        self.assertFalse(warnings)
        record = records[0]
        self.assertEqual(4, record["nominal"])
        self.assertEqual(4, record["child_records"][0]["max"])
        self.assertEqual(4, len(record["spawn_positions"]))
        self.assertEqual(4.0, record["spawn_positions"][1]["x"] - record["spawn_positions"][0]["x"])

        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record["class_name"],
            record["count"],
            record["lifetime"],
            nominal=record["nominal"],
            min_count=record["min_count"],
            max_count=record["max_count"],
            limit_type=record["limit_type"],
            child_records=record["child_records"],
        )
        event_node = events_root.find("event")
        self.assertEqual("4", event_node.findtext("nominal"))
        self.assertEqual("4", event_node.find("children/child").get("max"))

        spawns_root = ET.Element("eventposdef")
        for index, position in enumerate(record["spawn_positions"]):
            bot.add_console_ce_event_spawn(
                spawns_root,
                record["name"],
                position["x"],
                position["z"],
                angle=position["angle"],
                count=record["count"],
                radius=record["radius"],
                clear_existing=index == 0,
            )
        positions = spawns_root.findall("event/pos")
        self.assertEqual(4, len(positions))
        self.assertEqual(4, len({
            (position.get("x"), position.get("z"))
            for position in positions
        }))

    def test_shop_delivery_merge_does_not_read_or_rebuild_unrelated_map_group_xml(self):
        config = {
            "scenario_events": [{
                "id": 9,
                "event_type": "airdrop",
                "name": "Existing airdrop",
                "class_name": "Wreck_Mi8_Crashed",
                "created_by": "dashboard",
                "enabled": True,
                "upload_status": "uploaded",
            }],
        }
        shop_event = bot.create_console_shop_delivery_events(
            config,
            {"WoodenPlank": 2},
            3749,
            12953,
            "paid-order-1",
            "Player",
            "123",
        )[0]
        requested_sources = []

        def source(_config, _guild_id, key, _default_path=""):
            requested_sources.append(key)
            if key == "events_path":
                return "<events><event name=\"ExistingAirDrop\"><nominal>1</nominal></event></events>", "/mission/db/events.xml", "events live"
            if key == "spawns_path":
                return "<eventposdef><event name=\"ExistingAirDrop\"><pos x=\"1\" z=\"2\" a=\"0\" /></event></eventposdef>", "/mission/cfgeventspawns.xml", "spawns live"
            raise AssertionError(f"shop delivery must not read unrelated source {key}")

        with patch.object(bot, "download_console_ce_source", side_effect=source):
            built = bot.build_console_ce_event_files(
                "guild-1",
                config,
                scenario_events_override=[shop_event],
                preserve_existing=True,
            )

        self.assertEqual(["events_path", "spawns_path"], requested_sources)
        self.assertIn('name="ExistingAirDrop"', built["events_text"])
        self.assertIn('name="ItemWanderingBot_', built["events_text"])
        self.assertFalse(built["mapgroupproto_text"])

    def test_failed_paid_shop_delivery_stays_eligible_for_worker_retry(self):
        event = {
            "id": 11,
            "created_by": "shop_delivery",
            "event_type": "shop_delivery",
            "delivery_route": "native_xml_only",
            "shop_order_id": "paid-order-retry",
            "upload_status": "failed",
            "upload_attempts": 1,
            "enabled": True,
        }

        self.assertEqual([event], bot.pending_dashboard_scenario_xml_events({"scenario_events": [event]}))

    def test_pending_paid_shop_delivery_moves_from_hidden_base_to_matching_profile(self):
        event = {
            "id": 12,
            "created_by": "shop_delivery",
            "event_type": "shop_delivery",
            "delivery_route": "native_xml_only",
            "shop_order_id": "paid-order-profile",
            "upload_status": "failed",
            "upload_attempts": 1,
        }
        config = {
            "server_map": "chernarus",
            "scenario_events": [event],
            "server_profiles": {
                "cherno": {"server_map": "chernarus"},
                "livo": {"server_map": "livonia"},
            },
        }

        self.assertTrue(bot.migrate_base_dashboard_scenario_events_to_matching_profile(config))
        self.assertEqual([], config["scenario_events"])
        migrated = config["server_profiles"]["cherno"]["scenario_events"]
        self.assertEqual("paid-order-profile", migrated[0]["shop_order_id"])
        self.assertEqual("waiting_for_bot_upload", migrated[0]["upload_status"])
        self.assertEqual(0, migrated[0]["upload_attempts"])

    def test_completed_native_shop_delivery_requests_xml_cleanup(self):
        config = {
            "scenario_events": [{
                "id": 1,
                "event_type": "shop_delivery",
                "enabled": True,
                "permanent": False,
                "remaining_restarts": 1,
                "native_ce_uploaded_at": "2026-08-11T12:00:00+00:00",
            }]
        }

        self.assertTrue(bot.mark_one_time_scenario_events_uploaded(config, require_native_upload=True))
        self.assertEqual([], config["scenario_events"])
        self.assertTrue(config["scenario_events_cleanup_pending"])
        self.assertTrue(config["scenario_events_native_ce_cleanup_requested_at"])

    def test_completed_paid_console_delivery_queues_two_file_cleanup_not_generic_cleanup(self):
        config = {
            "scenario_events": [{
                "id": 2,
                "created_by": "shop_delivery",
                "event_type": "shop_delivery",
                "delivery_route": "native_xml_only",
                "shop_order_id": "paid-order-cleanup",
                "enabled": True,
                "permanent": False,
                "remaining_restarts": 1,
                "native_ce_uploaded_at": "2026-08-11T12:00:00+00:00",
                "native_ce_events_path": "/mission/db/events.xml",
                "native_ce_spawns_path": "/mission/cfgeventspawns.xml",
                "native_ce_managed_event_names": ["ItemWanderingBot_2_paid_order_cleanup"],
            }]
        }

        self.assertTrue(bot.mark_one_time_scenario_events_uploaded(config, require_native_upload=True))
        self.assertEqual([], config["scenario_events"])
        self.assertNotIn("scenario_events_cleanup_pending", config)
        queued = config["console_shop_delivery_ce_cleanup"]
        self.assertEqual(["ItemWanderingBot_2_paid_order_cleanup"], queued[0]["managed_event_names"])

    def test_paid_console_delivery_cleanup_uses_only_the_two_saved_ce_files(self):
        config = {
            "console_shop_delivery_ce_cleanup": [{
                "event_id": "2",
                "managed_event_names": ["ItemWanderingBot_2_paid_order_cleanup"],
                "events_path": "/mission/db/events.xml",
                "spawns_path": "/mission/cfgeventspawns.xml",
            }]
        }
        with patch.object(bot, "upload_console_ce_event_files", return_value=(True, {
            "events_path": "/mission/db/events.xml",
            "spawns_path": "/mission/cfgeventspawns.xml",
        }, [])) as upload:
            changed = asyncio.run(bot.process_console_paid_shop_delivery_cleanup("guild-1", config))

        self.assertTrue(changed)
        self.assertEqual([], config["console_shop_delivery_ce_cleanup"])
        self.assertEqual(
            ["guild-1", config, "/mission/db/events.xml", "/mission/cfgeventspawns.xml", "", False],
            list(upload.call_args.args),
        )
        self.assertEqual([], upload.call_args.kwargs["scenario_events_override"])
        self.assertTrue(upload.call_args.kwargs["preserve_existing"])
        self.assertEqual(["ItemWanderingBot_2_paid_order_cleanup"], upload.call_args.kwargs["remove_managed_event_names"])

    def test_paid_console_delivery_cleanup_preserves_unowned_ce_records(self):
        requested_sources = []

        def source(_config, _guild_id, key, _default_path=""):
            requested_sources.append(key)
            if key == "events_path":
                return (
                    '<events><event name="CommunityAirDrop" /><event name="ItemWanderingBot_2_paid_order_cleanup" /></events>',
                    "/mission/db/events.xml",
                    "events live",
                )
            if key == "spawns_path":
                return (
                    '<eventposdef><event name="CommunityAirDrop"><pos x="1" z="2" /></event>'
                    '<event name="ItemWanderingBot_2_paid_order_cleanup"><pos x="3" z="4" /></event></eventposdef>',
                    "/mission/cfgeventspawns.xml",
                    "spawns live",
                )
            raise AssertionError(f"shop cleanup must not read unrelated source {key}")

        with patch.object(bot, "download_console_ce_source", side_effect=source):
            built = bot.build_console_ce_event_files(
                "guild-1",
                {},
                scenario_events_override=[],
                preserve_existing=True,
                remove_managed_event_names=["ItemWanderingBot_2_paid_order_cleanup"],
            )

        self.assertEqual(["events_path", "spawns_path"], requested_sources)
        self.assertIn('name="CommunityAirDrop"', built["events_text"])
        self.assertNotIn('name="ItemWanderingBot_2_paid_order_cleanup"', built["events_text"])
        self.assertIn('name="CommunityAirDrop"', built["spawns_text"])
        self.assertNotIn('name="ItemWanderingBot_2_paid_order_cleanup"', built["spawns_text"])
        self.assertFalse(built["mapgroupproto_text"])

    def test_failed_generic_cleanup_is_paused_after_one_attempt(self):
        config = {
            "scenario_events": [],
            "scenario_events_cleanup_pending": True,
            "scenario_events_native_ce_cleanup_requested_at": "2026-08-11T12:00:00+00:00",
        }
        with patch.object(bot, "upload_console_ce_event_files", return_value=(False, {}, ["Nitrado temporary failure"])) as upload:
            self.assertTrue(asyncio.run(bot.process_dashboard_scenario_xml_upload("guild-1", config)))
            self.assertFalse(asyncio.run(bot.process_dashboard_scenario_xml_upload("guild-1", config)))

        self.assertEqual(1, upload.call_count)
        self.assertTrue(config["scenario_events_cleanup_blocked_at"])

    def test_exact_height_object_is_cleaned_from_source_after_restart(self):
        config = {
            "console_object_spawner": {
                "enabled": True,
                "object_path": "/custom/WanderingBotObjects.json",
                "objects": [{
                    "id": 9,
                    "name": "Hacksaw",
                    "pos": [8194, 55, 9092],
                    "ypr": [0, 0, 0],
                    "scale": 1,
                    "shop_delivery_state": "awaiting_restart",
                }],
            }
        }

        self.assertTrue(bot.mark_console_shop_object_deliveries_cleanup_due(config))
        self.assertEqual("cleanup_due", config["console_object_spawner"]["objects"][0]["shop_delivery_state"])
        with patch.object(bot, "upload_text_file_to_nitrado", return_value=(True, "uploaded")):
            changed = asyncio.run(bot.process_console_shop_object_delivery_cleanup(config))
        self.assertTrue(changed)
        self.assertEqual([], config["console_object_spawner"]["objects"])

    def test_exact_height_setup_uses_verified_live_mission_and_preserves_fields(self):
        guild_id = "987650001"
        config = {
            "server_map": "chernarus",
            "server_platform": "xbox",
            "console_object_spawner": {
                "enabled": False,
                "object_path": "/dayzxb/custom/WanderingBotObjects.json",
                "objects": [],
            },
        }
        live_cfg = """{
            "version": 129,
            "GeneralData": {"disableBaseDamage": true},
            "WorldsData": {
                "lightingConfig": 2,
                "objectSpawnersArr": ["./custom/ExistingBase.json"]
            }
        }"""
        live_path = "/dayzxb_missions/dayzOffline.chernarusplus/cfggameplay.json"
        uploads = []

        def upload(_config, path, content):
            uploads.append((path, content))
            return True, "uploaded"

        bot.guild_configs[guild_id] = config
        try:
            with (
                patch.object(
                    bot,
                    "download_live_cfggameplay_source",
                    return_value=(True, "verified live", live_cfg, live_path),
                ),
                patch.object(bot, "upload_text_file_to_nitrado", side_effect=upload),
                patch.object(bot, "save_guild_configs_for_runtime"),
            ):
                ok, message, details = asyncio.run(
                    bot.ensure_console_object_spawner_ready(guild_id, config)
                )
        finally:
            bot.guild_configs.pop(guild_id, None)

        self.assertTrue(ok, message)
        self.assertEqual(2, len(uploads))
        self.assertEqual(
            "/dayzxb_missions/dayzOffline.chernarusplus/custom/WanderingBotObjects.json",
            uploads[0][0],
        )
        self.assertEqual(live_path, uploads[1][0])
        updated_cfg = __import__("json").loads(uploads[1][1])
        self.assertTrue(updated_cfg["GeneralData"]["disableBaseDamage"])
        self.assertEqual(2, updated_cfg["WorldsData"]["lightingConfig"])
        self.assertEqual(
            ["./custom/ExistingBase.json", "./custom/WanderingBotObjects.json"],
            updated_cfg["WorldsData"]["objectSpawnersArr"],
        )
        self.assertTrue(config["console_object_spawner"]["enabled"])
        self.assertEqual(uploads[0][0], details["object_path"])

    def test_exact_height_setup_refuses_unverified_live_source_without_uploading(self):
        guild_id = "987650002"
        config = {"server_map": "chernarus", "server_platform": "xbox"}
        bot.guild_configs[guild_id] = config
        try:
            with (
                patch.object(
                    bot,
                    "download_live_cfggameplay_source",
                    return_value=(False, "live download failed", None, ""),
                ),
                patch.object(bot, "upload_text_file_to_nitrado") as upload_mock,
            ):
                ok, message, _details = asyncio.run(
                    bot.ensure_console_object_spawner_ready(guild_id, config)
                )
        finally:
            bot.guild_configs.pop(guild_id, None)

        self.assertFalse(ok)
        self.assertIn("live download failed", message)
        upload_mock.assert_not_called()
        self.assertFalse(config["console_object_spawner"]["enabled"])

    def test_exact_height_setup_does_not_enable_partial_two_file_upload(self):
        guild_id = "987650004"
        config = {"server_map": "sakhal", "server_platform": "playstation"}
        live_path = "/dayzps_missions/dayzOffline.sakhal/cfggameplay.json"
        live_cfg = '{"version":129,"WorldsData":{"objectSpawnersArr":[]}}'
        uploads = []

        def upload(_config, path, _content):
            uploads.append(path)
            if path.endswith("cfggameplay.json"):
                return False, "simulated cfg upload failure"
            return True, "uploaded"

        bot.guild_configs[guild_id] = config
        try:
            with (
                patch.object(
                    bot,
                    "download_live_cfggameplay_source",
                    return_value=(True, "verified live", live_cfg, live_path),
                ),
                patch.object(bot, "upload_text_file_to_nitrado", side_effect=upload),
            ):
                ok, message, details = asyncio.run(
                    bot.ensure_console_object_spawner_ready(guild_id, config)
                )
        finally:
            bot.guild_configs.pop(guild_id, None)

        self.assertFalse(ok)
        self.assertIn("simulated cfg upload failure", message)
        self.assertEqual(
            "/dayzps_missions/dayzOffline.sakhal/custom/WanderingBotObjects.json",
            uploads[0],
        )
        self.assertEqual(live_path, uploads[1])
        self.assertFalse(config["console_object_spawner"]["enabled"])
        self.assertFalse(details["cfg_upload"][0])

    def test_exact_height_purchase_auto_prepares_bridge_then_writes_order(self):
        guild_id = "987650003"
        config = {"server_map": "chernarus", "server_platform": "xbox"}
        live_path = "/dayzxb_missions/dayzOffline.chernarusplus/cfggameplay.json"
        live_cfg = '{"version":129,"WorldsData":{"objectSpawnersArr":[]}}'
        uploads = []

        def upload(_config, path, content):
            uploads.append((path, content))
            return True, "uploaded"

        bot.guild_configs[guild_id] = config
        try:
            with (
                patch.object(
                    bot,
                    "download_live_cfggameplay_source",
                    return_value=(True, "verified live", live_cfg, live_path),
                ),
                patch.object(bot, "upload_text_file_to_nitrado", side_effect=upload),
                patch.object(bot, "save_guild_configs_for_runtime"),
            ):
                ok, route, message = asyncio.run(
                    bot.route_console_shop_delivery(
                        guild_id,
                        config,
                        {"Hacksaw": 1},
                        8194,
                        9092,
                        True,
                        42.5,
                        "order-roof",
                        "Player",
                        "123",
                    )
                )
        finally:
            bot.guild_configs.pop(guild_id, None)

        self.assertTrue(ok, message)
        self.assertEqual("Object Spawner JSON (exact Y)", route)
        self.assertEqual(3, len(uploads))
        self.assertEqual(live_path, uploads[1][0])
        order_payload = __import__("json").loads(uploads[2][1])
        self.assertEqual("Hacksaw", order_payload["Objects"][0]["name"])
        self.assertEqual([8194.0, 42.5, 9092.0], order_payload["Objects"][0]["pos"])

    def test_exact_height_purchase_revalidates_saved_ready_state_against_live_cfg(self):
        guild_id = "987650005"
        live_path = "/dayzxb_missions/dayzOffline.chernarusplus/cfggameplay.json"
        config = {
            "server_map": "chernarus",
            "server_platform": "xbox",
            "console_object_spawner": {
                "enabled": True,
                "cfggameplay_path": live_path,
                "object_path": "/dayzxb_missions/dayzOffline.chernarusplus/custom/WanderingBotObjects.json",
                "spawner_ref": "./custom/WanderingBotObjects.json",
                "objects": [],
            },
        }
        # Simulate a mission reset/manual edit which removed the reference even
        # though the dashboard's saved state still says the bridge is ready.
        live_cfg = '{"version":129,"WorldsData":{"objectSpawnersArr":[]}}'
        uploads = []

        def upload(_config, path, content):
            uploads.append((path, content))
            return True, "uploaded"

        bot.guild_configs[guild_id] = config
        try:
            with (
                patch.object(
                    bot,
                    "download_live_cfggameplay_source",
                    return_value=(True, "verified live", live_cfg, live_path),
                ),
                patch.object(bot, "upload_text_file_to_nitrado", side_effect=upload),
                patch.object(bot, "save_guild_configs_for_runtime"),
            ):
                ok, route, message = asyncio.run(
                    bot.route_console_shop_delivery(
                        guild_id,
                        config,
                        {"Hacksaw": 1},
                        8194,
                        9092,
                        True,
                        42.5,
                        "order-revalidate",
                        "Player",
                        "123",
                    )
                )
        finally:
            bot.guild_configs.pop(guild_id, None)

        self.assertTrue(ok, message)
        self.assertEqual("Object Spawner JSON (exact Y)", route)
        self.assertEqual(3, len(uploads))
        repaired_cfg = __import__("json").loads(uploads[1][1])
        self.assertIn(
            "./custom/WanderingBotObjects.json",
            repaired_cfg["WorldsData"]["objectSpawnersArr"],
        )
        order_payload = __import__("json").loads(uploads[2][1])
        paid_objects = [row for row in order_payload["Objects"] if row.get("name") == "Hacksaw"]
        self.assertEqual(1, len(paid_objects))
        self.assertEqual([8194.0, 42.5, 9092.0], paid_objects[0]["pos"])

    def test_paid_restart_delivery_failure_blocks_restart_and_keeps_queue(self):
        guild_id = "987650006"
        config = {
            "server_platform": "pc",
            "dayz_delivery_bridge": {
                "installed_at": "2026-08-12T10:00:00+00:00",
                "bridge_version": bot.WANDERING_DELIVERY_BRIDGE_VERSION,
            },
        }
        queued = {"guild_id": guild_id, "item": "Hacksaw", "x": "1", "y": "0", "z": "2"}
        bot.delivery_queue.append(queued)
        try:
            with patch.object(bot, "write_and_upload_delivery_xml", return_value=(False, "failed.xml")):
                ready, had_paid, note = asyncio.run(
                    bot.prepare_delivery_xml_before_restart(guild_id, config)
                )
        finally:
            if queued in bot.delivery_queue:
                bot.delivery_queue.remove(queued)

        self.assertFalse(ready)
        self.assertTrue(had_paid)
        self.assertIn("remains queued", note)

    def test_paid_restart_delivery_requires_confirmed_pc_bridge(self):
        guild_id = "987650007"
        config = {"server_platform": "pc"}
        queued = {"guild_id": guild_id, "item": "Hacksaw", "x": "1", "y": "0", "z": "2"}
        bot.delivery_queue.append(queued)
        try:
            with patch.object(bot, "write_and_upload_delivery_xml") as upload:
                ready, had_paid, note = asyncio.run(
                    bot.prepare_delivery_xml_before_restart(guild_id, config)
                )
        finally:
            if queued in bot.delivery_queue:
                bot.delivery_queue.remove(queued)

        self.assertFalse(ready)
        self.assertTrue(had_paid)
        self.assertIn("no confirmed", note)
        self.assertIn("delivery bridge", note)
        upload.assert_not_called()

    def test_parallel_restart_workers_prepare_paid_batch_once(self):
        guild_id = "987650008"
        config = {
            "server_platform": "pc",
            "dayz_delivery_bridge": {
                "installed_at": "2026-08-12T10:00:00+00:00",
                "bridge_version": bot.WANDERING_DELIVERY_BRIDGE_VERSION,
            },
        }
        queued = {"guild_id": guild_id, "item": "Hacksaw", "x": "1", "y": "0", "z": "2"}
        bot.delivery_queue.append(queued)
        calls = []

        def slow_successful_upload(target_guild_id, *_args, **_kwargs):
            calls.append(target_guild_id)
            __import__("time").sleep(0.08)
            bot.remove_uploaded_queue_entries(target_guild_id)
            return True, "delivery.xml"

        async def run_both():
            return await asyncio.gather(
                bot.prepare_delivery_xml_before_restart(guild_id, config),
                bot.prepare_delivery_xml_before_restart(guild_id, config),
            )

        try:
            with patch.object(bot, "write_and_upload_delivery_xml", side_effect=slow_successful_upload):
                results = asyncio.run(run_both())
        finally:
            bot.delivery_queue = [entry for entry in bot.delivery_queue if entry is not queued]
            bot.delivery_upload_locks.pop(guild_id, None)

        self.assertEqual([guild_id], calls)
        self.assertTrue(results[0][0])
        self.assertTrue(results[0][1])
        self.assertTrue(results[1][0])
        self.assertFalse(results[1][1])


def _base_event(event_id, event_type, class_name, **overrides):
    event = {
        "id": event_id,
        "event_type": event_type,
        "class_name": class_name,
        "x": 5000,
        "y": 0,
        "z": 5000,
        "radius": 70,
        "native_ce_revision": 2,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    event.update(overrides)
    return event


class AirdropEventGroupTests(unittest.TestCase):
    """Verify the events.xml/cfgeventspawns/mapgroupproto linkage for airdrops."""

    def _build_airdrop_event_node(self, event):
        records, _warnings = bot.console_ce_records_for_event(event)
        self.assertTrue(records, "airdrop should produce at least one CE record")
        record = records[0]
        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record.get("event_child_type") or record["class_name"],
            record["count"],
            record["lifetime"],
            restock=record.get("restock", 0),
            use_eventgroup=bool(record.get("use_eventgroup")),
            limit_type=record.get("limit_type") or "child",
            child_lootmin=record.get("child_lootmin", 0),
            child_lootmax=record.get("child_lootmax", 0),
            nominal=record.get("nominal"),
            min_count=record.get("min_count"),
            max_count=record.get("max_count"),
            saferadius=record.get("saferadius", 0),
            distanceradius=record.get("distanceradius", 0),
            cleanupradius=record.get("cleanupradius", 100),
            child_records=record.get("child_records"),
            remove_damaged=bool(record.get("remove_damaged")),
            empty_children=bool(record.get("empty_event_children")),
            secondary=record.get("secondary", ""),
        )
        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            y=record.get("y"),
            count=record["count"],
            radius=record.get("radius") or 45,
            group_name=record["name"] if record.get("use_eventgroup") else "",
        )
        eventgroups_root = ET.Element("eventgroupdef")
        if record.get("use_eventgroup"):
            bot.add_console_ce_event_group(
                eventgroups_root,
                record["name"],
                record["class_name"],
                lootmin=record.get("child_lootmin", 40) or 40,
                lootmax=record.get("child_lootmax", 80) or 80,
                child_records=record.get("eventgroup_children"),
            )
        return record, events_root, spawns_root, eventgroups_root

    def test_airdrop_events_xml_uses_direct_mi8_child(self):
        """MI8 airdrops now follow the vanilla heli-crash shape: the real
        crash child lives directly in events.xml, and cfgeventspawns only
        carries the fixed x/z/a position."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, events_root, _spawns, _groups = self._build_airdrop_event_node(event)

        self.assertFalse(record.get("use_eventgroup"))
        self.assertFalse(record.get("empty_event_children"))
        self.assertEqual("StaticWanderingBot_29_airdrop", record["name"])
        self.assertNotIn("_r", record["name"])
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        children_node = event_node.find("children")
        self.assertIsNotNone(children_node, "events.xml event must still carry a <children/> element")
        child = children_node.find("child")
        self.assertIsNotNone(child)
        self.assertEqual("Wreck_Mi8_Crashed", child.get("type"))
        self.assertGreater(int(child.get("lootmax") or 0), 0)

    def test_random_airdrop_location_pool_uses_one_definition_and_many_ce_positions(self):
        event = _base_event(
            57,
            "airdrop",
            "Wreck_Mi8_Crashed",
            location_mode="random_pool",
            location_pool=[
                {"name": "NWAF", "x": 4481, "z": 10355, "angle": 15},
                {"name": "Tisy", "x": 1612, "z": 14175, "angle": 120},
                {"name": "Skalisty", "x": 13532, "z": 3131, "angle": 240},
            ],
            active_count=2,
            guard_class="ZmbM_SoldierNormal",
            guard_count=8,
        )

        records, warnings = bot.console_ce_records_for_event(event)

        self.assertEqual(2, len(records), "pool guards need one attached secondary definition")
        record = records[0]
        guard_record = records[1]
        self.assertEqual(3, len(record["spawn_positions"]))
        self.assertEqual(1, record["count"], "each selected location must receive one airdrop scene")
        self.assertEqual(2, record["nominal"])
        self.assertEqual(2, record["min_count"])
        self.assertEqual(2, record["max_count"])
        self.assertEqual(guard_record["name"], record["secondary"])
        self.assertEqual("player", guard_record["position"])
        self.assertTrue(guard_record["skip_spawn"])
        self.assertTrue(any("through `<secondary>`" in warning for warning in warnings))
        self.assertTrue(any("one nominal-2 airdrop definition" in warning for warning in warnings))

        spawns_root = ET.Element("eventposdef")
        for index, position in enumerate(record["spawn_positions"]):
            bot.add_console_ce_event_spawn(
                spawns_root,
                record["name"],
                position["x"],
                position["z"],
                angle=position["angle"],
                count=record["count"],
                radius=record["radius"],
                clear_existing=index == 0,
            )

        positions = spawns_root.findall("event/pos")
        self.assertEqual(3, len(positions))
        self.assertEqual(
            {("4481", "10355", "15"), ("1612", "14175", "120"), ("13532", "3131", "240")},
            {(node.get("x"), node.get("z"), node.get("a")) for node in positions},
        )
        self.assertTrue(all("y" not in node.attrib for node in positions))

    def test_airdrop_vanilla_mi8_timing_preserves_large_radii(self):
        event = _base_event(
            30,
            "airdrop",
            "Wreck_Mi8_Crashed",
            timing_preset="vanilla_mi8",
            lifetime=2100,
            restock=0,
            saferadius=1000,
            distanceradius=1000,
            cleanupradius=1000,
        )
        record, events_root, _spawns, _groups = self._build_airdrop_event_node(event)

        self.assertEqual(record.get("distanceradius"), 1000)
        self.assertEqual(record.get("cleanupradius"), 1000)
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        self.assertEqual(event_node.findtext("lifetime"), "2100")
        self.assertEqual(event_node.findtext("restock"), "0")
        self.assertEqual(event_node.findtext("saferadius"), "1000")
        self.assertEqual(event_node.findtext("distanceradius"), "1000")
        self.assertEqual(event_node.findtext("cleanupradius"), "1000")

    def test_airdrop_cfgeventspawns_pos_carries_group(self):
        """cfgeventspawns.xml <pos> must NOT contain ``y``. For direct MI8
        airdrops it also does not reference a cfgeventgroups group."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, _events, spawns_root, _groups = self._build_airdrop_event_node(event)

        spawn_event = spawns_root.find("event")
        self.assertIsNotNone(spawn_event)
        pos = spawn_event.find("pos")
        self.assertIsNotNone(pos)
        self.assertIsNone(pos.get("group"))
        for attr in ("x", "z", "a"):
            self.assertIn(attr, pos.attrib)
        self.assertNotIn(
            "y", pos.attrib,
            "cfgeventspawns.xml <pos> must not carry y ? vanilla DayZ samples "
            "terrain height itself, and forcing y=0 prevents the spawn.",
        )

    def test_airdrop_record_requests_mapgroupproto_for_crash_class(self):
        """Ground loot comes from mapgroupproto lootFloor tags on the crash
        class, not from WoodenCrate cargo."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, _events, _spawns, groups_root = self._build_airdrop_event_node(event)

        self.assertIsNone(groups_root.find("group"))
        self.assertEqual(["Wreck_Mi8_Crashed"], record.get("mapgroupproto_classes"))
        self.assertEqual("Wreck_Mi8_Crashed", record.get("event_child_type"))

    def test_helicopter_airdrop_uses_crash_and_proto_tags_not_item_children(self):
        event = _base_event(
            32,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            loot_preset="military_high",
        )
        record, events_root, _spawns, groups_root = self._build_airdrop_event_node(event)

        self.assertEqual(record["event_child_type"], "Wreck_Mi8_Crashed")
        self.assertIsNone(groups_root.find("group"))
        children = events_root.findall("event/children/child")
        types_in_event = [child.get("type") for child in children]
        self.assertIn("Wreck_Mi8_Crashed", types_in_event)
        self.assertNotIn("WoodenCrate", types_in_event)
        self.assertFalse(any(child.get("type") in bot.SCENARIO_AIRDROP_GROUND_LOOT for child in children))

    def test_airdrop_vehicle_class_is_replaced_by_static_loot_anchor(self):
        event = _base_event(
            52,
            "airdrop",
            "Sedan_02",
            visual_marker=False,
            loot_preset="vehicle_car",
        )
        records, warnings = bot.console_ce_records_for_event(event, map_key="livonia")
        self.assertEqual(1, len(records))
        record = records[0]

        self.assertEqual("Wreck_Mi8_Crashed", record["class_name"])
        self.assertEqual("Wreck_Mi8_Crashed", record["event_child_type"])
        self.assertEqual(["Wreck_Mi8_Crashed"], record.get("mapgroupproto_classes"))
        self.assertFalse(any(child.get("type") == "Sedan_02" for child in record["child_records"]))
        self.assertTrue(any("vehicle classname `Sedan_02`" in message for message in warnings))

    def test_drop_loot_list_strips_vehicle_classnames(self):
        event = _base_event(
            53,
            "airdrop",
            "WoodenCrate",
            loot=["M4A1", "Sedan_02", "Truck_01_Covered", "CarBattery"],
        )

        loot = bot.scenario_loot_items(event)
        records, warnings = bot.console_ce_records_for_event(event, map_key="livonia")

        self.assertIn("M4A1", loot)
        self.assertIn("CarBattery", loot)
        self.assertNotIn("Sedan_02", loot)
        self.assertNotIn("Truck_01_Covered", loot)
        self.assertEqual(["Wreck_Mi8_Crashed"], records[0].get("mapgroupproto_classes"))
        self.assertTrue(any("vehicle classname(s) in a drop loot list" in message for message in warnings))

    def test_drop_eventgroup_children_strip_vehicle_classnames(self):
        event = _base_event(54, "airdrop", "WoodenCrate", visual_marker=True)
        original_uses_eventgroup = bot.scenario_airdrop_uses_eventgroup
        original_eventgroup_children = bot.scenario_airdrop_eventgroup_children
        try:
            bot.scenario_airdrop_uses_eventgroup = lambda _event: True
            bot.scenario_airdrop_eventgroup_children = lambda _event, _class_name: [
                {
                    "type": "Sedan_02",
                    "x": "0.0",
                    "y": "0.0",
                    "z": "0.0",
                    "a": "0.0",
                    "min": 1,
                    "max": 1,
                    "lootmin": 1,
                    "lootmax": 5,
                },
                {
                    "type": "Truck_01_Covered",
                    "spawnsecondary": "false",
                    "x": "1.0",
                    "y": "0.0",
                    "z": "1.0",
                    "a": "0.0",
                },
                {
                    "type": "Wreck_Mi8_Crashed",
                    "x": "2.0",
                    "y": "0.0",
                    "z": "2.0",
                    "a": "0.0",
                    "min": 1,
                    "max": 1,
                    "lootmin": 1,
                    "lootmax": 5,
                },
            ]

            records, warnings = bot.console_ce_records_for_event(event, map_key="livonia")
        finally:
            bot.scenario_airdrop_uses_eventgroup = original_uses_eventgroup
            bot.scenario_airdrop_eventgroup_children = original_eventgroup_children

        self.assertEqual(1, len(records))
        record = records[0]
        child_types = [child.get("type") for child in record.get("eventgroup_children") or []]
        self.assertEqual(["Wreck_Mi8_Crashed"], child_types)
        self.assertEqual(["Wreck_Mi8_Crashed"], record.get("mapgroupproto_classes"))
        self.assertTrue(any("cfgeventgroups child props" in message for message in warnings))

    def test_old_drop_event_type_replaces_vehicle_classname(self):
        event = _base_event(55, "convoy_wreck", "Sedan_02")

        records, warnings = bot.console_ce_records_for_event(event, map_key="livonia")

        self.assertEqual(1, len(records))
        self.assertEqual("Wreck_Mi8_Crashed", records[0]["class_name"])
        self.assertEqual("Wreck_Mi8_Crashed", records[0]["event_child_type"])
        self.assertTrue(any("drop-style event" in message for message in warnings))

    def test_airdrop_guards_are_attached_secondary_events(self):
        event = _base_event(
            32,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            guard_class="ZmbM_SoldierNormal",
            guard_count=3,
            guard_radius=35,
        )
        records, _warnings = bot.console_ce_records_for_event(event)

        self.assertEqual(2, len(records))
        static_record = records[0]
        guard_record = records[1]
        self.assertTrue(static_record["name"].startswith("StaticWanderingBot_"))
        self.assertTrue(guard_record["name"].startswith("InfectedWanderingBot_"))
        self.assertTrue(guard_record.get("skip_spawn"))
        self.assertEqual("player", guard_record.get("position"))
        self.assertEqual("custom", guard_record.get("limit_type"))
        self.assertEqual(guard_record["name"], static_record.get("secondary"))
        self.assertFalse(any(
            child.get("type") == "ZmbM_SoldierNormal"
            for child in static_record["child_records"]
        ))
        self.assertTrue(any(
            child.get("type") == "ZmbM_SoldierNormal"
            and child.get("lootmax") == 5
            and child.get("min") == 3
            and child.get("max") == 0
            for child in guard_record["child_records"]
        ))

    def test_direct_airdrop_with_separate_guard_event_validates(self):
        event = _base_event(
            32,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            guard_class="ZmbM_SoldierNormal",
            guard_count=3,
        )
        records, _warnings = bot.console_ce_records_for_event(event)
        events_root = ET.Element("events")
        spawns_root = ET.Element("eventposdef")
        zombie_root = ET.Element("territory-type")
        ET.SubElement(zombie_root, "territory", {"color": "1291845632"})
        for record in records:
            if record.get("skip_definition"):
                continue
            bot.add_console_ce_event_definition(
                events_root,
                record["name"],
                record.get("event_child_type") or record["class_name"],
                record["count"],
                record["lifetime"],
                restock=record.get("restock", 0),
                limit_type=record.get("limit_type") or "child",
                child_records=record.get("child_records"),
                nominal=record.get("nominal"),
                min_count=record.get("min_count"),
                max_count=record.get("max_count"),
                saferadius=record.get("saferadius", 0),
                distanceradius=record.get("distanceradius", 0),
                cleanupradius=record.get("cleanupradius", 100),
                remove_damaged=bool(record.get("remove_damaged")),
                deletable=bool(record.get("deletable", True)),
                secondary=record.get("secondary", ""),
                position=record.get("position", "fixed"),
            )
            if record.get("skip_spawn"):
                continue
            bot.add_console_ce_event_spawn(
                spawns_root,
                record["name"],
                record["x"],
                record["z"],
                count=record["count"],
                radius=record.get("radius") or 45,
            )
        proto_root = ET.Element("prototype")
        for record in records:
            for class_name in record.get("mapgroupproto_classes") or []:
                bot.add_mapgroupproto_loot_group(
                    proto_root,
                    class_name,
                    lootmax=record.get("child_lootmax") or 80,
                    tags=record.get("mapgroupproto_tags"),
                )
        built = {
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": bot.xml_text_from_root(proto_root),
            "zombie_territories_text": bot.xml_text_from_root(zombie_root),
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

        guard_name = records[1]["name"]
        for event_node in list(events_root.findall("event")):
            if event_node.get("name") == guard_name:
                events_root.remove(event_node)
        missing_guard_bundle = dict(built)
        missing_guard_bundle["events_text"] = bot.xml_text_from_root(events_root)
        ok, messages = bot.validate_console_ce_xml_bundle(missing_guard_bundle, check_scope=False)
        self.assertFalse(ok)
        self.assertTrue(any(
            guard_name in message and "missing from events.xml" in message
            for message in messages
        ), "\n".join(messages))

    def test_convoy_airdrop_uses_direct_child_not_eventgroup(self):
        event = _base_event(
            46,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="convoy_wreck",
            loot_preset="military_high",
        )
        record, events_root, spawns_root, groups_root = self._build_airdrop_event_node(event)

        self.assertFalse(record.get("use_eventgroup"))
        self.assertFalse(record.get("empty_event_children"))
        self.assertEqual(["StaticObj_Wreck_HMMWV_DE"], record.get("mapgroupproto_classes"))
        children = events_root.findall("event/children/child")
        self.assertEqual(1, len(children))
        self.assertEqual("StaticObj_Wreck_HMMWV_DE", children[0].get("type"))
        pos = spawns_root.find("event/pos")
        self.assertIsNotNone(pos)
        self.assertIsNone(pos.get("group"))
        self.assertIsNone(groups_root.find("group"))

    def test_airdrop_loot_range_controls_events_and_proto_budget(self):
        event = _base_event(
            26,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            loot_preset="military_high",
            loot_count_range="30-40",
            loot=[f"Ammo_9x39_{index}" for index in range(40)],
        )

        record, events_root, _spawns_root, _groups_root = self._build_airdrop_event_node(event)

        child = events_root.find("./event/children/child")
        self.assertIsNotNone(child)
        self.assertEqual("Wreck_Mi8_Crashed", child.get("type"))
        self.assertEqual("30", child.get("lootmin"))
        self.assertEqual("40", child.get("lootmax"))
        self.assertEqual(30, record.get("child_lootmin"))
        self.assertEqual(40, record.get("child_lootmax"))

        proto_root = ET.Element("prototype")
        for class_name in record.get("mapgroupproto_classes") or []:
            bot.add_mapgroupproto_loot_group(
                proto_root,
                class_name,
                lootmax=record.get("child_lootmax") or 80,
                tags=record.get("mapgroupproto_tags"),
            )
        container = proto_root.find("./group[@name='Wreck_Mi8_Crashed']/container")
        self.assertIsNotNone(container)
        self.assertEqual("40", container.get("lootmax"))

    def test_airdrop_scenes_do_not_inject_extra_vehicle_wreck_props(self):
        for scene_key in ("cargo_plane_wreck", "convoy_wreck"):
            scene = bot.SCENARIO_AIRDROP_SCENES[scene_key]
            self.assertEqual([], scene.get("props"))

    def test_vehicle_spawn_position_spread_helper_is_explicit_only(self):
        positions = bot.console_ce_vehicle_spawn_positions(5000, 5000, radius=45)
        self.assertEqual(8, len(positions))
        self.assertNotIn((5000, 5000), [(x, z) for x, z, _angle in positions])

        protected = bot.console_ce_vehicle_spawn_positions(
            5000,
            5000,
            radius=45,
            exclusion_center=(5000, 5000),
            exclusion_radius=125,
        )
        self.assertEqual(8, len(protected))
        for pos_x, pos_z, _angle in protected:
            self.assertGreaterEqual(math.hypot(pos_x - 5000, pos_z - 5000), 125)

    def test_airdrop_direct_spawn_replaces_stale_grouped_spawn_pos(self):
        event = _base_event(
            49,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="convoy_wreck",
        )
        records, _warnings = bot.console_ce_records_for_event(event)
        record = records[0]
        self.assertFalse(record.get("use_eventgroup"))

        spawns_root = ET.Element("eventposdef")
        stale_event = ET.SubElement(spawns_root, "event", {"name": record["name"]})
        ET.SubElement(stale_event, "pos", {"x": "1", "z": "2", "a": "0", "group": record["name"]})

        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            y=record.get("y"),
            count=record["count"],
            radius=record.get("radius") or 45,
            group_name="",
        )

        positions = spawns_root.findall("event/pos")
        self.assertEqual(1, len(positions))
        self.assertIsNone(positions[0].get("group"))
        self.assertEqual("5000", positions[0].get("x"))

    def test_gas_zone_uses_static_contaminated_area_shape(self):
        event = _base_event(
            48,
            "gas_zone",
            "ContaminatedArea_Dynamic",
            radius=80,
            gas_lifetime=1800,
        )
        records, _warnings = bot.console_ce_records_for_event(event)
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("StaticWanderingBot_48_gaszone", record["name"])
        self.assertNotIn("_r", record["name"])
        self.assertFalse(record["name"].startswith("ContaminatedAreaWanderingBot"))
        self.assertEqual("parent", record.get("limit_type"))
        self.assertEqual("ContaminatedArea_Dynamic", record["child_records"][0]["type"])

        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record.get("event_child_type") or record["class_name"],
            record["count"],
            record["lifetime"],
            limit_type=record.get("limit_type") or "child",
            child_records=record.get("child_records"),
            nominal=record.get("nominal"),
            min_count=record.get("min_count"),
            max_count=record.get("max_count"),
        )
        self.assertEqual("parent", events_root.findtext("event/limit"))

        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            radius=record.get("radius") or 45,
        )
        zone = spawns_root.find("event/zone")
        pos = spawns_root.find("event/pos")
        self.assertIsNotNone(zone)
        self.assertEqual("80", zone.get("r"))
        self.assertIsNone(zone.get("x"))
        self.assertIsNotNone(pos)
        self.assertEqual("5000", pos.get("x"))
        built = {
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": "<prototype></prototype>",
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))


class VehicleAndZombieSpawnTests(unittest.TestCase):
    """Vehicles and hordes do NOT use cfgeventgroups. Their <pos> blocks must
    still avoid the y attribute and must carry the actual class as the
    events.xml ``<child type=...>`` value."""

    def _build_event(self, event):
        records, warnings = bot.console_ce_records_for_event(event)
        self.assertTrue(records, f"event {event} produced no CE records: {warnings}")
        record = records[0]
        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record.get("event_child_type") or record["class_name"],
            record["count"],
            record["lifetime"],
            restock=record.get("restock", 0),
            use_eventgroup=bool(record.get("use_eventgroup")),
            limit_type=record.get("limit_type") or "child",
            child_lootmin=record.get("child_lootmin", 0),
            child_lootmax=record.get("child_lootmax", 0),
            nominal=record.get("nominal"),
            min_count=record.get("min_count"),
            max_count=record.get("max_count"),
            saferadius=record.get("saferadius", 0),
            distanceradius=record.get("distanceradius", 0),
            cleanupradius=record.get("cleanupradius", 100),
            child_records=record.get("child_records"),
            remove_damaged=bool(record.get("remove_damaged")),
            deletable=bool(record.get("deletable", True)),
            empty_children=bool(record.get("empty_event_children")),
            secondary=record.get("secondary", ""),
        )
        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            y=record.get("y"),
            count=record["count"],
            radius=record.get("radius") or 45,
            group_name="",
        )
        return record, events_root, spawns_root

    def test_vehicle_event_has_real_class_child_and_no_pos_y(self):
        event = _base_event(31, "vehicle_spawn", "Hatchback_02")
        record, events_root, spawns_root = self._build_event(event)

        self.assertFalse(record.get("use_eventgroup"))
        self.assertFalse(record.get("empty_event_children"))
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        self.assertEqual(event_node.findtext("limit"), "mixed")
        self.assertEqual(event_node.findtext("saferadius"), "0")
        self.assertEqual(event_node.findtext("distanceradius"), "25")
        self.assertEqual(event_node.findtext("cleanupradius"), "200")
        self.assertEqual(event_node.find("flags").get("deletable"), "0")
        self.assertEqual(event_node.find("flags").get("remove_damaged"), "1")
        child = event_node.find("children/child")
        self.assertIsNotNone(child)
        self.assertEqual(child.get("type"), "Hatchback_02")

        positions = spawns_root.findall("event/pos")
        self.assertEqual(
            1,
            len(positions),
            "fixed vehicle events must not invent backup/ring coordinates around the requested point",
        )
        self.assertEqual("5000", positions[0].get("x"))
        self.assertEqual("5000", positions[0].get("z"))
        for pos in positions:
            self.assertNotIn("y", pos.attrib)

    def test_fixed_vehicle_quantity_does_not_create_extra_positions(self):
        event = _base_event(50, "vehicle_spawn", "Truck_01_Covered", x=1396, z=4004, count=10)
        record, _events_root, spawns_root = self._build_event(event)

        self.assertEqual(1, record["count"])
        positions = spawns_root.findall("event/pos")
        self.assertEqual(1, len(positions))
        self.assertEqual("1396", positions[0].get("x"))
        self.assertEqual("4004", positions[0].get("z"))
        self.assertEqual("0", positions[0].get("a"))

    def test_vehicle_radius_spread_mode_generates_candidate_positions(self):
        event = _base_event(
            50,
            "vehicle_spawn",
            "Truck_01_Covered",
            x=1396,
            z=4004,
            count=10,
            radius=45,
            location_mode="radius_spread",
        )
        records, warnings = bot.console_ce_records_for_event(event)
        record = records[0]

        self.assertEqual(10, record["count"])
        positions = record.get("spawn_positions")
        self.assertEqual(10, len(positions))
        self.assertNotIn((1396, 4004), [(position["x"], position["z"]) for position in positions])
        self.assertTrue(any("10 generated radius" in warning for warning in warnings))

    def test_vehicle_manual_mode_uses_one_supplied_position_per_vehicle(self):
        manual_positions = [
            {"name": f"Truck {index + 1}", "x": 1396 + (index * 12), "z": 4004 + (index * 7), "angle": index * 20}
            for index in range(10)
        ]
        event = _base_event(
            50,
            "vehicle_spawn",
            "Truck_01_Covered",
            x=1396,
            z=4004,
            count=10,
            location_mode="manual_positions",
            location_pool=manual_positions,
        )

        records, warnings = bot.console_ce_records_for_event(event)

        self.assertEqual(1, len(records))
        self.assertEqual(10, records[0]["count"])
        self.assertEqual(manual_positions, records[0]["spawn_positions"])
        self.assertTrue(any("10 manual" in warning for warning in warnings))

    def test_explicit_vehicle_candidate_positions_are_not_rewritten(self):
        spawns_root = ET.Element("eventposdef")
        event_name = "VehicleWanderingBot_50_vehicle_spawn"
        for index, position in enumerate(
            [
                {"x": 1396, "z": 4004, "angle": 0},
                {"x": 1410.5, "z": 4015.25, "angle": 90},
                {"x": 1420, "z": 4025, "angle": 180},
            ]
        ):
            bot.add_console_ce_event_spawn(
                spawns_root,
                event_name,
                position["x"],
                position["z"],
                angle=position["angle"],
                count=10,
                radius=45,
                clear_existing=index == 0,
            )

        positions = spawns_root.findall("event/pos")
        self.assertEqual(3, len(positions))
        self.assertEqual(
            [("1396", "4004", "0"), ("1410.5", "4015.25", "90"), ("1420", "4025", "180")],
            [(pos.get("x"), pos.get("z"), pos.get("a")) for pos in positions],
        )

    def test_fixed_vehicle_retry_does_not_duplicate_or_touch_unrelated_spawns(self):
        spawns_root = ET.Element("eventposdef")
        unrelated = ET.SubElement(spawns_root, "event", {"name": "VehicleSedan02"})
        ET.SubElement(unrelated, "pos", {"x": "100", "z": "200", "a": "45"})
        event_name = "VehicleWanderingBot_50_vehicle_spawn"

        for _attempt in range(2):
            bot.add_console_ce_event_spawn(
                spawns_root,
                event_name,
                1396,
                4004,
                angle=0,
                count=10,
                radius=45,
                clear_existing=True,
            )

        positions = spawns_root.findall(f"./event[@name='{event_name}']/pos")
        self.assertEqual(1, len(positions))
        self.assertEqual(("1396", "4004", "0"), (positions[0].get("x"), positions[0].get("z"), positions[0].get("a")))
        unrelated_after = spawns_root.find("./event[@name='VehicleSedan02']/pos")
        self.assertIsNotNone(unrelated_after)
        self.assertEqual(("100", "200", "45"), (unrelated_after.get("x"), unrelated_after.get("z"), unrelated_after.get("a")))

    def test_vehicle_start_speed_normal_keeps_cautious_distances(self):
        event = _base_event(31, "vehicle_spawn", "Hatchback_02", start_speed="normal")
        record, events_root, _spawns_root = self._build_event(event)

        self.assertEqual(record.get("start_speed"), "normal")
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        self.assertEqual(event_node.findtext("saferadius"), "500")
        self.assertEqual(event_node.findtext("distanceradius"), "500")
        self.assertEqual(event_node.findtext("cleanupradius"), "200")

    def test_zombie_horde_has_zone_block_no_y(self):
        event = _base_event(
            33,
            "zombie_horde",
            "ZmbM_HeavyIndustryWorker",
            preset="heavymilitaryzombie",
        )
        records, warnings = bot.console_ce_records_for_event(event)
        self.assertTrue(records, f"event {event} produced no CE records: {warnings}")
        record = records[0]

        self.assertTrue(record.get("zombie_territory"))
        self.assertTrue(record.get("skip_definition"))
        self.assertTrue(record.get("skip_spawn"))
        self.assertEqual("InfectedArmy", record.get("zombie_territory_name"))

        zombie_root = ET.Element("territory-type")
        ET.SubElement(zombie_root, "territory", {"color": "1291845632"})
        bot.add_zombie_territory_zone(zombie_root, record)
        zone = zombie_root.find("./territory/zone")
        self.assertIsNotNone(zone)
        self.assertEqual("InfectedArmy", zone.get("name"))
        self.assertEqual(str(record["count"]), zone.get("dmin"))
        self.assertEqual(str(record["count"]), zone.get("dmax"))
        self.assertEqual("0", zone.get("smin"))
        self.assertEqual("0", zone.get("smax"))
        self.assertEqual("5000", zone.get("x"))
        self.assertEqual("5000", zone.get("z"))
        self.assertNotIn("y", zone.attrib)

    def test_custom_mummy_horde_creates_matching_event_and_random_zone_range(self):
        event = _base_event(
            91,
            "zombie_horde",
            "ZmbM_Mummy",
            preset="custom",
            count=7,
            zombie_min_count=3,
            zombie_max_count=10,
            x=1420,
            z=9300,
            radius=85,
        )
        records, warnings = bot.console_ce_records_for_event(event)
        self.assertTrue(records, warnings)
        record = records[0]

        self.assertTrue(record.get("zombie_territory"))
        self.assertTrue(record.get("custom_zombie_definition"))
        self.assertFalse(record.get("skip_definition"))
        self.assertTrue(record.get("skip_spawn"))
        self.assertEqual(record["zombie_territory_name"], record["name"])
        self.assertTrue(record["name"].startswith("InfectedWanderingBot"))
        self.assertEqual(3, record["zone_min_count"])
        self.assertEqual(10, record["zone_max_count"])
        self.assertEqual(
            [{"type": "ZmbM_Mummy", "count": 1, "min": 30, "max": 0, "lootmin": 0, "lootmax": 5}],
            record["child_records"],
        )

        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record["class_name"],
            record["count"],
            record["lifetime"],
            restock=record["restock"],
            limit_type=record["limit_type"],
            child_records=record["child_records"],
            nominal=record["nominal"],
            min_count=record["min_count"],
            max_count=record["max_count"],
            saferadius=record["saferadius"],
            distanceradius=record["distanceradius"],
            cleanupradius=record["cleanupradius"],
            remove_damaged=record["remove_damaged"],
            deletable=record["deletable"],
            position=record["position"],
        )
        zombie_root = ET.Element("territory-type")
        ET.SubElement(zombie_root, "territory", {"color": "1291845632"})
        bot.add_zombie_territory_zone(zombie_root, record)
        zone = zombie_root.find("./territory/zone")
        self.assertIsNotNone(zone)
        self.assertEqual(record["name"], zone.get("name"))
        self.assertEqual("3", zone.get("dmin"))
        self.assertEqual("10", zone.get("dmax"))

        types_root = ET.Element("types")
        self.assertTrue(bot.add_console_zombie_type_entry(types_root, "ZmbM_Mummy"))
        self.assertFalse(bot.add_console_zombie_type_entry(types_root, "ZmbM_Mummy"))
        mummy_type = types_root.find("./type[@name='ZmbM_Mummy']")
        self.assertIsNotNone(mummy_type)
        self.assertEqual("0", mummy_type.findtext("nominal"))
        self.assertEqual("1800", mummy_type.findtext("lifetime"))

        built = {
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": "<eventposdef />",
            "zombie_territories_text": bot.xml_text_from_root(zombie_root),
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))


class EventGroupChildPlacementTests(unittest.TestCase):
    """The cfgeventgroups child placement still needs all four offset attrs
    (x, y, z, a) ? these are LOCAL offsets relative to the group anchor, not
    map coordinates. This guards against accidentally stripping them along
    with the cfgeventspawns y removal."""

    def test_eventgroup_child_has_full_local_offsets(self):
        event = _base_event(32, "airdrop", "WoodenCrate", visual_marker=True, scene_type="helicopter_crash")
        records, _ = bot.console_ce_records_for_event(event)
        record = records[0]
        groups_root = ET.Element("eventgroupdef")
        bot.add_console_ce_event_group(
            groups_root,
            record["name"],
            record["class_name"],
            lootmin=record.get("child_lootmin", 40) or 40,
            lootmax=record.get("child_lootmax", 80) or 80,
            child_records=record.get("eventgroup_children"),
        )
        children = groups_root.findall("group/child")
        self.assertTrue(children)
        for child in children:
            for attr in ("x", "y", "z", "a"):
                self.assertIn(attr, child.attrib, f"cfgeventgroups child missing {attr}")


class MapGroupProtoTests(unittest.TestCase):
    """Each loot-bearing airdrop child type must have a mapgroupproto group entry,
    otherwise the live RPT prints ``No group configured for '<class>'``."""

    def test_proto_group_added_for_helicopter_crash_loot_floor(self):
        event = _base_event(
            34,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            loot_preset="military_high",
        )
        records, _ = bot.console_ce_records_for_event(event)
        record = records[0]
        proto_root = ET.Element("prototype")
        for class_name in record.get("mapgroupproto_classes") or []:
            bot.add_mapgroupproto_loot_group(proto_root, class_name, tags=record.get("mapgroupproto_tags"))
        names = {g.get("name") for g in proto_root.findall("group")}
        self.assertIn("Wreck_Mi8_Crashed", names)
        self.assertNotIn("WoodenCrate", names)
        crash_group = next(g for g in proto_root.findall("group") if g.get("name") == "Wreck_Mi8_Crashed")
        container = crash_group.find("container")
        self.assertIsNotNone(container)
        self.assertEqual(container.get("name"), "lootFloor")
        self.assertGreater(int(container.get("lootmax") or "0"), 0)
        self.assertEqual([node.get("name") for node in crash_group.findall("usage")], ["Military"])
        self.assertEqual([node.get("name") for node in crash_group.findall("value")], ["Tier3", "Tier4"])
        self.assertIsNotNone(container.find("category"))
        self.assertIsNotNone(container.find("tag"))
        self.assertIsNotNone(container.find("point"))
        self.assertEqual(container.find("tag").get("name"), "floor")
        self.assertEqual(container.find("point").get("flags"), "32")
        self.assertGreaterEqual(len(container.findall("point")), 8)

    def test_airdrop_preset_counts_for_loot_budget(self):
        event = _base_event(
            34,
            "airdrop",
            "WoodenCrate",
            loot_preset="military_high",
        )

        loot_min, loot_max = bot.scenario_ce_loot_budget(event)

        self.assertGreater(loot_max, 15)
        self.assertGreaterEqual(loot_min, 1)

    def test_livonia_proto_values_do_not_generate_tier4(self):
        event = _base_event(
            34,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            loot_preset="military_high",
        )
        tags = bot.scenario_mapgroupproto_loot_tags(event, map_key="livonia")
        self.assertEqual(["Tier3"], tags.get("value"))

        proto_root = ET.Element("prototype")
        bot.add_mapgroupproto_loot_group(
            proto_root,
            "Wreck_Mi8_Crashed",
            tags=tags,
            map_key="livonia",
        )
        crash_group = next(g for g in proto_root.findall("group") if g.get("name") == "Wreck_Mi8_Crashed")
        self.assertEqual([node.get("name") for node in crash_group.findall("value")], ["Tier3"])

    def test_validator_rejects_livonia_tier4_mapgroupproto_value(self):
        event = _base_event(53, "airdrop", "WoodenCrate")
        records, _warnings = bot.console_ce_records_for_event(event, map_key="livonia")
        record = records[0]
        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record.get("event_child_type") or record["class_name"],
            record["count"],
            record["lifetime"],
            restock=record.get("restock", 0),
            limit_type=record.get("limit_type") or "child",
            child_records=record.get("child_records"),
            nominal=record.get("nominal"),
            min_count=record.get("min_count"),
            max_count=record.get("max_count"),
        )
        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            count=record["count"],
            radius=record.get("radius") or 45,
        )
        proto_root = ET.Element("prototype")
        group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "15"})
        ET.SubElement(group, "usage", {"name": "Military"})
        ET.SubElement(group, "value", {"name": "Tier4"})
        container = ET.SubElement(group, "container", {"name": "lootFloor", "lootmax": "15"})
        ET.SubElement(container, "category", {"name": "weapons"})
        ET.SubElement(container, "tag", {"name": "floor"})
        ET.SubElement(container, "point", {"pos": "0 0 0", "range": "1", "height": "1"})

        built = {
            "map_key": "livonia",
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": bot.xml_text_from_root(proto_root),
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertFalse(ok)
        self.assertTrue(any("Tier4" in message and "livonia" in message for message in messages), messages)

    def test_validator_rejects_livonia_historical_usage_and_bad_container_flags(self):
        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            "StaticWanderingBot_55_airdrop",
            "Wreck_Mi8_Crashed",
            1,
            7200,
            child_records=[{
                "type": "Wreck_Mi8_Crashed",
                "count": 1,
                "min": 1,
                "max": 1,
                "lootmin": 5,
                "lootmax": 15,
            }],
            nominal=1,
            min_count=1,
            max_count=1,
        )
        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(spawns_root, "StaticWanderingBot_55_airdrop", 5000, 5000)
        proto_root = ET.Element("prototype")
        group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "15"})
        ET.SubElement(group, "usage", {"name": "Historical"})
        ET.SubElement(group, "value", {"name": "Tier3"})
        container = ET.SubElement(group, "container", {"name": "lootFloor", "lootmax": "15"})
        ET.SubElement(container, "category", {"name": "vehicles"})
        ET.SubElement(container, "tag", {"name": "roof"})
        ET.SubElement(container, "point", {"pos": "0 0 0", "range": "1", "height": "1"})

        built = {
            "map_key": "livonia",
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": bot.xml_text_from_root(proto_root),
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertFalse(ok)
        rendered = "\n".join(messages)
        self.assertIn("Historical", rendered)
        self.assertIn("vehicles", rendered)
        self.assertIn("roof", rendered)

    def test_validator_rejects_working_vehicle_as_static_loot_child(self):
        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            "StaticWanderingBot_54_airdrop",
            "Sedan_02",
            1,
            7200,
            child_records=[{
                "type": "Sedan_02",
                "count": 1,
                "min": 1,
                "max": 1,
                "lootmin": 1,
                "lootmax": 5,
            }],
            nominal=1,
            min_count=1,
            max_count=1,
        )
        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(spawns_root, "StaticWanderingBot_54_airdrop", 5000, 5000)
        proto_root = ET.Element("prototype")
        group = ET.SubElement(proto_root, "group", {"name": "Sedan_02", "lootmax": "5"})
        container = ET.SubElement(group, "container", {"name": "lootFloor", "lootmax": "5"})
        ET.SubElement(container, "category", {"name": "tools"})
        ET.SubElement(container, "tag", {"name": "floor"})
        ET.SubElement(container, "point", {"pos": "0 0 0", "range": "1", "height": "1"})

        built = {
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": bot.xml_text_from_root(proto_root),
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertFalse(ok)
        self.assertTrue(any("Working vehicles must use a Vehicle CE event" in message for message in messages), messages)

    def test_airdrop_proto_categories_never_include_containers_or_vehicles(self):
        event = _base_event(
            35,
            "airdrop",
            "WoodenCrate",
            loot_preset="military",
        )
        tags = bot.scenario_mapgroupproto_loot_tags(event)
        categories = {str(item).lower() for item in tags.get("category") or []}

        self.assertNotIn("containers", categories)
        self.assertNotIn("vehicles", categories)

    def test_vehicle_detector_allows_bags_storage_and_vehicle_parts(self):
        self.assertTrue(bot.dayz_class_looks_like_vehicle("Hatchback_02"))
        self.assertTrue(bot.dayz_class_looks_like_vehicle("CivilianSedan"))
        self.assertTrue(bot.dayz_class_looks_like_vehicle("Offroad_02"))
        self.assertFalse(bot.dayz_class_looks_like_vehicle("AliceBag_Green"))
        self.assertFalse(bot.dayz_class_looks_like_vehicle("SeaChest"))
        self.assertFalse(bot.dayz_class_looks_like_vehicle("Truck_01_Wheel"))

    def test_invalid_crash_usage_cleanup_is_scope_safe(self):
        original = (
            '<prototype>'
            '<group name="Wreck_Mi8_Crashed" lootmax="15">'
            '<usage name="Crash" />'
            '<usage name="Military" />'
            '<container name="lootFloor" lootmax="15"><category name="weapons" />'
            '<tag name="floor" /><point pos="0 0 0" range="1" height="1" /></container>'
            '</group>'
            '</prototype>'
        )
        root = ET.fromstring(original)

        removed = bot.cleanup_invalid_mapgroupproto_usages(root)
        merged = bot.xml_text_from_root(root)

        self.assertEqual(1, removed)
        self.assertNotIn('usage name="Crash"', merged)
        ok, message = bot.validate_managed_ce_xml_scope("mapgroupproto.xml", original, merged)
        self.assertTrue(ok, message)

    def test_vehicle_types_repair_zeroes_vehicle_bodies_only(self):
        original = (
            '<types>'
            '<type name="Hatchback_02"><nominal>9</nominal><lifetime>3</lifetime><restock>1800</restock>'
            '<min>6</min><flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" '
            'count_in_player="0" crafted="0" deloot="1" /></type>'
            '<type name="CivilianSedan"><nominal>7</nominal><lifetime>3</lifetime><restock>1800</restock>'
            '<min>4</min><flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" '
            'count_in_player="0" crafted="0" deloot="0" /></type>'
            '<type name="Truck_01_Wheel"><nominal>111</nominal><lifetime>28800</lifetime>'
            '<restock>0</restock><min>96</min><flags count_in_cargo="0" count_in_hoarder="0" '
            'count_in_map="1" count_in_player="0" crafted="0" deloot="0" /></type>'
            '<type name="AliceBag_Green"><nominal>30</nominal><min>20</min>'
            '<flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" '
            'count_in_player="0" crafted="0" deloot="0" /></type>'
            '</types>'
        )
        root = ET.fromstring(original)

        repaired = bot.repair_vehicle_types_xml_values(root)
        merged = bot.xml_text_from_root(root)

        self.assertEqual(["Hatchback_02", "CivilianSedan"], repaired)
        repaired_root = ET.fromstring(merged)
        hatchback = repaired_root.find("./type[@name='Hatchback_02']")
        self.assertIsNotNone(hatchback)
        self.assertEqual("0", hatchback.findtext("nominal"))
        self.assertEqual("0", hatchback.findtext("min"))
        self.assertEqual("0", hatchback.find("flags").get("deloot"))
        sedan = repaired_root.find("./type[@name='CivilianSedan']")
        self.assertIsNotNone(sedan)
        self.assertEqual("0", sedan.findtext("nominal"))
        self.assertEqual("0", sedan.findtext("min"))
        wheel = repaired_root.find("./type[@name='Truck_01_Wheel']")
        self.assertIsNotNone(wheel)
        self.assertEqual("111", wheel.findtext("nominal"))
        self.assertEqual("96", wheel.findtext("min"))
        bag = repaired_root.find("./type[@name='AliceBag_Green']")
        self.assertIsNotNone(bag)
        self.assertEqual("30", bag.findtext("nominal"))
        self.assertEqual("20", bag.findtext("min"))

        ok, message = bot.validate_managed_ce_xml_scope("types.xml", original, merged)
        self.assertTrue(ok, message)

    def test_airdrop_guard_event_does_not_need_mapgroupproto(self):
        event = _base_event(34, "airdrop", "WoodenCrate", visual_marker=True, scene_type="helicopter_crash")
        event["guard_class"] = "ZmbM_SoldierNormal"
        event["guard_count"] = 2
        records, _ = bot.console_ce_records_for_event(event)

        self.assertEqual(2, len(records))
        self.assertEqual(records[1]["name"], records[0].get("secondary"))
        self.assertTrue(records[1].get("skip_spawn"))
        self.assertEqual("player", records[1].get("position"))
        self.assertEqual("custom", records[1].get("limit_type"))
        self.assertTrue(any(child.get("type") == "ZmbM_SoldierNormal" for child in records[1]["child_records"]))
        self.assertNotIn("ZmbM_SoldierNormal", records[0].get("mapgroupproto_classes") or [])
        self.assertEqual([], records[1].get("mapgroupproto_classes") or [])

    def test_existing_unmarked_proto_group_is_left_alone_and_managed_group_appended(self):
        proto_root = ET.Element("prototype")
        ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed"})

        _, changed = bot.add_mapgroupproto_loot_group(proto_root, "Wreck_Mi8_Crashed")

        self.assertTrue(changed)
        groups = proto_root.findall("./group[@name='Wreck_Mi8_Crashed']")
        self.assertEqual(2, len(groups))
        self.assertIsNone(groups[0].find("container"))
        container = groups[1].find("container")
        self.assertIsNotNone(container)
        self.assertEqual(container.get("name"), "lootFloor")
        self.assertGreater(int(container.get("lootmax") or "0"), 0)
        self.assertIsNotNone(container.find("category"))
        self.assertIsNotNone(container.find("tag"))
        self.assertIsNotNone(container.find("point"))
        self.assertEqual(container.find("tag").get("name"), "floor")
        self.assertEqual(container.find("point").get("flags"), "32")
        self.assertGreaterEqual(len(container.findall("point")), 8)

    def test_existing_unmarked_usable_proto_group_is_reused_without_duplicate(self):
        proto_root = ET.Element("prototype")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "15"})
        ET.SubElement(crash_group, "usage", {"name": "Military"})
        container = ET.SubElement(crash_group, "container", {"name": "lootFloor", "lootmax": "15"})
        ET.SubElement(container, "category", {"name": "weapons"})
        ET.SubElement(container, "tag", {"name": "floor"})
        ET.SubElement(container, "point", {"pos": "-2.693787 -1.888990 1.671386", "range": "0.703328", "height": "2.000000", "flags": "32"})

        returned_group, changed = bot.add_mapgroupproto_loot_group(proto_root, "Wreck_Mi8_Crashed")

        self.assertFalse(changed)
        self.assertIs(returned_group, crash_group)
        self.assertEqual(1, len(proto_root.findall("./group[@name='Wreck_Mi8_Crashed']")))

    def test_reference_static_helicrash_proto_can_bump_lootmax_when_requested(self):
        proto_root = ET.Element("prototype")
        crash_group = bot.dayz_reference_mapgroupproto_group("chernarus", "Wreck_Mi8_Crashed")
        self.assertIsNotNone(crash_group)
        proto_root.append(crash_group)
        container = crash_group.find("./container[@name='lootFloor']")
        self.assertIsNotNone(container)

        returned_group, changed = bot.add_mapgroupproto_loot_group(
            proto_root,
            "Wreck_Mi8_Crashed",
            lootmax=40,
            map_key="chernarus",
            patch_static_helicrash_lootmax=True,
        )

        self.assertTrue(changed)
        self.assertIs(returned_group, crash_group)
        self.assertEqual("40", crash_group.get("lootmax"))
        self.assertEqual("40", container.get("lootmax"))
        self.assertEqual(1, len(proto_root.findall("./group[@name='Wreck_Mi8_Crashed']")))

    def test_custom_unmarked_static_helicrash_proto_is_not_bumped(self):
        proto_root = ET.Element("prototype")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "15"})
        ET.SubElement(crash_group, "usage", {"name": "Military"})
        container = ET.SubElement(crash_group, "container", {"name": "lootFloor", "lootmax": "15"})
        ET.SubElement(container, "category", {"name": "weapons"})
        ET.SubElement(container, "tag", {"name": "floor"})
        ET.SubElement(container, "point", {
            "pos": "-2.693787 -1.888990 1.671386",
            "range": "0.703328",
            "height": "2.000000",
            "flags": "32",
        })

        returned_group, changed = bot.add_mapgroupproto_loot_group(
            proto_root,
            "Wreck_Mi8_Crashed",
            lootmax=40,
            map_key="chernarus",
            patch_static_helicrash_lootmax=True,
        )

        self.assertFalse(changed)
        self.assertIs(returned_group, crash_group)
        self.assertEqual("15", crash_group.get("lootmax"))
        self.assertEqual("15", container.get("lootmax"))

    def test_existing_marked_proto_group_gets_lootfloor_repaired(self):
        proto_root = ET.Element("prototype")
        bot.append_wandering_xml_comment(proto_root, "managed mapgroupproto group Wreck_Mi8_Crashed")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "80"})
        ET.SubElement(crash_group, "usage", {"name": "Military"})
        ET.SubElement(crash_group, "point", {"pos": "0 0 0", "range": "0.5", "height": "0.5"})

        _, changed = bot.add_mapgroupproto_loot_group(proto_root, "Wreck_Mi8_Crashed")

        self.assertTrue(changed)
        container = crash_group.find("container")
        self.assertIsNotNone(container)
        self.assertEqual(container.get("name"), "lootFloor")
        self.assertGreater(int(container.get("lootmax") or "0"), 0)
        self.assertIsNotNone(container.find("category"))
        self.assertEqual(container.find("tag").get("name"), "floor")
        self.assertEqual(container.find("point").get("flags"), "32")

    def test_existing_marked_proto_group_drops_vehicle_loot_categories(self):
        proto_root = ET.Element("prototype")
        bot.append_wandering_xml_comment(proto_root, "managed mapgroupproto group Wreck_Mi8_Crashed")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "80"})
        container = ET.SubElement(crash_group, "container", {"name": "lootFloor", "lootmax": "80"})
        ET.SubElement(container, "category", {"name": "containers"})
        ET.SubElement(container, "category", {"name": "vehicles"})
        ET.SubElement(container, "category", {"name": "weapons"})

        _, changed = bot.add_mapgroupproto_loot_group(
            proto_root,
            "Wreck_Mi8_Crashed",
            tags={"usage": ["Military"], "value": ["Tier4"], "category": ["weapons", "tools"]},
        )

        self.assertTrue(changed)
        categories = [node.get("name") for node in container.findall("category")]
        self.assertEqual(["weapons"], categories)

    def test_existing_marked_proto_group_drops_obsolete_crash_usage(self):
        proto_root = ET.Element("prototype")
        bot.append_wandering_xml_comment(proto_root, "managed mapgroupproto group Wreck_Mi8_Crashed")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "80"})
        ET.SubElement(crash_group, "usage", {"name": "Crash"})
        ET.SubElement(crash_group, "value", {"name": "Tier1"})

        _, changed = bot.add_mapgroupproto_loot_group(
            proto_root,
            "Wreck_Mi8_Crashed",
            tags={"usage": ["Military"], "value": ["Tier4"], "category": ["weapons"]},
        )

        self.assertTrue(changed)
        self.assertEqual([node.get("name") for node in crash_group.findall("usage")], ["Military"])
        self.assertEqual([node.get("name") for node in crash_group.findall("value")], ["Tier4"])

    def test_livonia_static_helicrash_proto_repair_restores_one_vanilla_group(self):
        proto_root = ET.Element("prototype")
        ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed"})
        duplicate_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "15"})
        container = ET.SubElement(duplicate_group, "container", {"name": "lootFloor", "lootmax": "15"})
        ET.SubElement(container, "category", {"name": "weapons"})
        ET.SubElement(container, "tag", {"name": "floor"})
        ET.SubElement(container, "point", {"pos": "0 0 0", "range": "0.5", "height": "0.5"})

        repaired = bot.repair_vanilla_static_helicrash_mapgroupproto(proto_root, "livonia")

        self.assertEqual(["Wreck_Mi8_Crashed"], repaired)
        groups = proto_root.findall("./group[@name='Wreck_Mi8_Crashed']")
        self.assertEqual(1, len(groups))
        self.assertTrue(bot.mapgroupproto_group_matches_reference(groups[0], "livonia", "Wreck_Mi8_Crashed"))
        self.assertGreaterEqual(len(groups[0].findall("./container/point")), 20)

    def test_static_helicrash_lootmax_bump_is_scope_safe(self):
        original_root = ET.Element("prototype")
        original_group = bot.dayz_reference_mapgroupproto_group("livonia", "Wreck_Mi8_Crashed")
        self.assertIsNotNone(original_group)
        original_root.append(original_group)

        merged_root = ET.fromstring(ET.tostring(original_root, encoding="utf-8"))
        merged_group = merged_root.find("./group[@name='Wreck_Mi8_Crashed']")
        self.assertIsNotNone(merged_group)
        changed = bot.bump_static_helicrash_mapgroupproto_lootmax(merged_group, 40)
        self.assertTrue(changed)

        ok, message = bot.validate_managed_ce_xml_scope(
            "mapgroupproto.xml",
            bot.xml_text_from_root(original_root),
            bot.xml_text_from_root(merged_root),
            map_key="livonia",
        )

        self.assertTrue(ok, message)


class BuildConsoleCeEventFilesTests(unittest.TestCase):
    def setUp(self):
        self.original_download = bot.download_console_ce_source
        self.original_download_text = bot.download_text_file_from_nitrado
        self.original_upload_latest_backup = bot.upload_ce_latest_backup_to_nitrado
        self.original_cleanup_backups = bot.cleanup_wanderingbot_backups_for_path
        self.guild_id = "999001"
        self.original_unowned_repair_setting = os.environ.get("WANDERING_ALLOW_UNOWNED_CE_REPAIRS")
        # These are structural generator tests for an owner-approved repair.
        # The default dashboard flow remains snippet-only and is covered by the
        # dedicated safe-upload tests below.
        os.environ["WANDERING_ALLOW_UNOWNED_CE_REPAIRS"] = "true"

    def tearDown(self):
        bot.download_console_ce_source = self.original_download
        bot.download_text_file_from_nitrado = self.original_download_text
        bot.upload_ce_latest_backup_to_nitrado = self.original_upload_latest_backup
        bot.cleanup_wanderingbot_backups_for_path = self.original_cleanup_backups
        bot.guild_configs.pop(self.guild_id, None)
        if self.original_unowned_repair_setting is None:
            os.environ.pop("WANDERING_ALLOW_UNOWNED_CE_REPAIRS", None)
        else:
            os.environ["WANDERING_ALLOW_UNOWNED_CE_REPAIRS"] = self.original_unowned_repair_setting

    def test_airdrop_upload_uses_existing_mi8_proto_as_context_only(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        proto_root = ET.Element("prototype")
        proto_root.append(bot.dayz_reference_mapgroupproto_group("chernarus", "Wreck_Mi8_Crashed"))
        bunker_group = ET.SubElement(proto_root, "group", {
            "name": "Land_Underground_Storage_Laboratory",
            "lootmax": "80",
        })
        ET.SubElement(bunker_group, "usage", {"name": "Bunker"})
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": (bot.xml_text_from_root(proto_root), f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    33,
                    "airdrop",
                    "WoodenCrate",
                    visual_marker=True,
                    scene_type="helicopter_crash",
                    loot_preset="military_high",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertFalse(built.get("mapgroupproto_text"))
        self.assertTrue(built.get("mapgroupproto_context_text"))
        proto_after = ET.fromstring(built["mapgroupproto_context_text"])
        self.assertIsNotNone(proto_after.find("./group[@name='Wreck_Mi8_Crashed']"))
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_unrelated_static_airplanecrate_without_spawn_does_not_block_airdrop(self):
        """A legacy live-file mismatch must not be mistaken for a generated event."""
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        proto_root = ET.Element("prototype")
        proto_root.append(bot.dayz_reference_mapgroupproto_group("chernarus", "Wreck_Mi8_Crashed"))
        live_events = (
            '<events>'
            '<event name="StaticAirplaneCrate"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>2100</lifetime><restock>0</restock><saferadius>1000</saferadius>'
            '<distanceradius>1000</distanceradius><cleanupradius>1000</cleanupradius>'
            '<flags deletable="1" init_random="0" remove_damaged="0" />'
            '<position>fixed</position><limit>child</limit><active>1</active>'
            '<children><child type="StaticObj_Misc_SupplyBox3_DE" lootmin="4" lootmax="8" min="2" max="4" /></children>'
            '</event>'
            '</events>'
        )
        sources = {
            "events_path": (live_events, f"{base_path}/db/events.xml"),
            # This reproduces the production failure: the unrelated vanilla
            # event exists, but its spawn block is absent from the live file.
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": (bot.xml_text_from_root(proto_root), f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    16,
                    "airdrop",
                    "WoodenCrate",
                    event_name="Shumnoye airdrop",
                    visual_marker=True,
                    scene_type="helicopter_crash",
                    loot_preset="military_high",
                    x=14277,
                    z=8606,
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        with patch.dict(os.environ, {"WANDERING_ALLOW_UNOWNED_CE_REPAIRS": "false"}):
            built = bot.build_console_ce_event_files(self.guild_id, config)

        events_root = ET.fromstring(built["events_text"])
        spawns_root = ET.fromstring(built["spawns_text"])
        self.assertIsNotNone(events_root.find("./event[@name='StaticAirplaneCrate']"))
        self.assertIsNone(spawns_root.find("./event[@name='StaticAirplaneCrate']"))
        self.assertTrue(bot.is_stale_spawn_only_event_name("StaticAirplaneCrate"))
        self.assertFalse(bot.is_wandering_managed_name("StaticAirplaneCrate"))

        generated_names = set(built.get("managed_event_names") or [])
        generated_spawn_names = set(built.get("managed_spawn_names") or [])
        self.assertTrue(generated_names)
        self.assertEqual(generated_names, generated_spawn_names)
        for name in generated_names:
            self.assertIsNotNone(events_root.find(f"./event[@name='{name}']"))
            self.assertIsNotNone(spawns_root.find(f"./event[@name='{name}']"))

        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_native_airdrop_location_pool_emits_all_candidates_in_one_spawn_block(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        proto_root = ET.Element("prototype")
        proto_root.append(bot.dayz_reference_mapgroupproto_group("chernarus", "Wreck_Mi8_Crashed"))
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": (bot.xml_text_from_root(proto_root), f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    57,
                    "airdrop",
                    "Wreck_Mi8_Crashed",
                    location_mode="random_pool",
                    location_pool=[
                        {"name": "NWAF", "x": 4481, "z": 10355},
                        {"name": "Tisy", "x": 1612, "z": 14175},
                        {"name": "Skalisty", "x": 13532, "z": 3131},
                    ],
                    active_count=2,
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        events_root = ET.fromstring(built["events_text"])
        event_node = events_root.find("./event[@name='StaticWanderingBot_57_airdrop']")
        self.assertIsNotNone(event_node)
        self.assertEqual("2", event_node.findtext("nominal"))
        self.assertEqual("2", event_node.findtext("min"))
        self.assertEqual("2", event_node.findtext("max"))
        child = event_node.find("./children/child")
        self.assertIsNotNone(child)
        self.assertEqual("1", child.get("min"))
        self.assertEqual("1", child.get("max"))
        spawns_root = ET.fromstring(built["spawns_text"])
        positions = spawns_root.findall("./event[@name='StaticWanderingBot_57_airdrop']/pos")
        self.assertEqual(3, len(positions))
        self.assertEqual(
            {("4481", "10355"), ("1612", "14175"), ("13532", "3131")},
            {(node.get("x"), node.get("z")) for node in positions},
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_chernarus_airdrop_repairs_one_point_mi8_proto(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        proto_root = ET.Element("prototype")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "80"})
        ET.SubElement(crash_group, "usage", {"name": "Military"})
        ET.SubElement(crash_group, "point", {"pos": "0 0 0", "range": "0.5", "height": "0.5"})
        container = ET.SubElement(crash_group, "container", {"name": "lootfloor", "lootmax": "80"})
        for category in ("weapons", "explosives", "tools", "clothes", "containers", "food"):
            ET.SubElement(container, "category", {"name": category})
        ET.SubElement(container, "point", {"pos": "0 0 0", "range": "0.5", "height": "0.5"})
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": (bot.xml_text_from_root(proto_root), f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    34,
                    "airdrop",
                    "WoodenCrate",
                    visual_marker=True,
                    scene_type="helicopter_crash",
                    loot_preset="military_high",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertTrue(built.get("mapgroupproto_text"))
        proto_after = ET.fromstring(built["mapgroupproto_text"])
        groups = proto_after.findall("./group[@name='Wreck_Mi8_Crashed']")
        self.assertEqual(1, len(groups))
        self.assertTrue(bot.mapgroupproto_group_matches_reference(groups[0], "chernarus", "Wreck_Mi8_Crashed"))
        points = groups[0].findall("./container/point")
        self.assertGreaterEqual(len(points), 20)
        self.assertFalse(any(str(point.get("pos") or "").strip() == "0 0 0" for point in points))
        self.assertTrue(
            any("Restored vanilla StaticHeliCrash" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_upload_scope_blocks_empty_chernarus_eventspawns_source(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        built = {
            "map_key": "chernarus",
            "spawns_path": f"{base_path}/cfgeventspawns.xml",
            "spawns_source_text": "<eventposdef></eventposdef>",
            "spawns_text": (
                "<eventposdef>"
                '<event name="StaticWanderingBot_34_airdrop">'
                '<pos x="5000" z="5000" a="0" />'
                "</event>"
                "</eventposdef>"
            ),
        }

        ok, messages = bot.validate_console_ce_upload_scope(built)

        self.assertFalse(ok)
        rendered = "\n".join(messages)
        self.assertIn("live source baseline check blocked upload", rendered)
        self.assertIn("empty/truncated Nitrado read", rendered)

    def test_build_blocks_empty_eventspawns_source_instead_of_using_latest_backup(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        reference_events = bot.load_dayz_reference_text("chernarus", "db", "events.xml")
        reference_spawns = bot.load_dayz_reference_text("chernarus", "cfgeventspawns.xml")
        sources = {
            "events_path": (reference_events, f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "") == f"{base_path}/cfgeventspawns.xml.wanderingbot-backup-latest":
                return True, "backup source", reference_spawns
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    34,
                    "airdrop",
                    "WoodenCrate",
                    visual_marker=False,
                    loot_preset="military_high",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertTrue(built.get("source_fallbacks"), built.get("source_fallbacks"))
        self.assertEqual("<eventposdef></eventposdef>", built.get("spawns_source_text"))
        self.assertTrue(
            any("no backup was used as a merge source" in str(message) for message in built.get("source_fallbacks", [])),
            built.get("source_fallbacks", []),
        )
        scope_ok, scope_messages = bot.validate_console_ce_upload_scope(built)
        self.assertFalse(scope_ok, "\n".join(scope_messages))
        self.assertTrue(any("baseline check blocked upload" in str(message) for message in scope_messages), scope_messages)

    def test_baseline_blocks_a_half_erased_event_source(self):
        reference_events = bot.load_dayz_reference_text("chernarus", "db", "events.xml")
        root = ET.fromstring(reference_events)
        event_nodes = root.findall("event")
        for node in event_nodes[len(event_nodes) // 2:]:
            root.remove(node)

        ok, message = bot.validate_console_ce_live_source_baseline(
            "events.xml",
            ET.tostring(root, encoding="unicode"),
            "chernarus",
        )

        self.assertFalse(ok)
        self.assertIn("requires at least", message)
        self.assertIn("not merge, restore, back up, or write over it", message)

    def test_latest_backup_guard_blocks_removed_unmanaged_event_records(self):
        live = '<eventposdef><event name="VanillaA" /><event name="VanillaB" /></eventposdef>'
        latest_backup = (
            '<eventposdef><event name="VanillaA" /><event name="VanillaB" />'
            '<event name="VanillaC" /></eventposdef>'
        )

        with patch.object(bot, "download_text_file_from_nitrado", return_value=(True, "downloaded", latest_backup)):
            ok, message = bot.validate_console_ce_live_source_against_latest_backup(
                {},
                "cfgeventspawns.xml",
                live,
                "/dayzxb_missions/dayzOffline.chernarusplus/cfgeventspawns.xml",
            )

        self.assertFalse(ok)
        self.assertIn("`VanillaC`", message)
        self.assertIn("will not silently restore", message)

    def test_static_airplanecrate_missing_proto_is_restored_for_horde_upload(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        live_events = (
            '<events>'
            '<event name="StaticAirplaneCrate"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>2100</lifetime><restock>0</restock><saferadius>1000</saferadius>'
            '<distanceradius>1000</distanceradius><cleanupradius>1000</cleanupradius>'
            '<flags deletable="1" init_random="0" remove_damaged="0" />'
            '<position>fixed</position><limit>child</limit><active>1</active>'
            '<children><child type="StaticObj_Misc_SupplyBox3_DE" lootmin="4" lootmax="8" min="2" max="4" /></children>'
            '</event>'
            '</events>'
        )
        sources = {
            "events_path": (live_events, f"{base_path}/db/events.xml"),
            "spawns_path": ('<eventposdef><event name="StaticAirplaneCrate"><pos x="4847" z="10083" a="0" /></event></eventposdef>', f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(8, "zombie_horde", "ZmbM_usSoldier_Heavy_Woodland", preset="heavy_military_zombie")
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        proto_root = ET.fromstring(built["mapgroupproto_text"])
        self.assertIsNotNone(proto_root.find("./group[@name='StaticObj_Misc_SupplyBox3_DE']"))
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, messages)
        self.assertTrue(
            any("Restored vanilla StaticAirplaneCrate mapgroupproto" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )

    def test_cfgspawnabletypes_scope_block_skips_optional_cargo_tuning(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": (
                '<spawnabletypes><type name="WoodenCrate"><damage min="0.1" max="0.2" /></type><type name="Hammer" /></spawnabletypes>',
                f"{base_path}/cfgspawnabletypes.xml",
            ),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    41,
                    "airdrop",
                    "WoodenCrate",
                    loot=["Hammer"],
                    loot_preset="custom",
                    visual_marker=False,
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertFalse(built.get("spawnabletypes_text"))
        self.assertFalse(built.get("spawnabletypes_path"))
        self.assertTrue(
            any("per-item cargo tuning" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_livonia_airdrop_repairs_missing_static_helicrash_proto(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    58,
                    "airdrop",
                    "WoodenCrate",
                    visual_marker=True,
                    scene_type="helicopter_crash",
                    loot_preset="military_high",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        proto_root = ET.fromstring(built["mapgroupproto_text"])
        groups = proto_root.findall("./group[@name='Wreck_Mi8_Crashed']")
        self.assertEqual(1, len(groups))
        self.assertTrue(bot.mapgroupproto_group_matches_reference(groups[0], "livonia", "Wreck_Mi8_Crashed"))
        self.assertTrue(
            any("Restored vanilla StaticHeliCrash" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_livonia_airdrop_requested_loot_range_bumps_mi8_proto_lootmax(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        proto_root = ET.Element("prototype")
        proto_root.append(bot.dayz_reference_mapgroupproto_group("livonia", "Wreck_Mi8_Crashed"))
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": (bot.xml_text_from_root(proto_root), f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    59,
                    "airdrop",
                    "WoodenCrate",
                    visual_marker=True,
                    scene_type="helicopter_crash",
                    loot_preset="military_high",
                    loot_count_range="30-40",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        events_root = ET.fromstring(built["events_text"])
        child = events_root.find("./event[@name='StaticWanderingBot_59_airdrop']/children/child")
        self.assertIsNotNone(child)
        self.assertEqual("30", child.get("lootmin"))
        self.assertEqual("40", child.get("lootmax"))
        merged_proto = ET.fromstring(built["mapgroupproto_text"])
        crash_group = merged_proto.find("./group[@name='Wreck_Mi8_Crashed']")
        self.assertIsNotNone(crash_group)
        self.assertEqual("40", crash_group.get("lootmax"))
        self.assertEqual("40", crash_group.find("./container[@name='lootFloor']").get("lootmax"))
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_livonia_cargo_plane_airdrop_falls_back_to_open_scene(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    52,
                    "airdrop",
                    "WoodenCrate",
                    visual_marker=True,
                    scene_type="cargo_plane_wreck",
                    loot_preset="military_high",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        proto_root = ET.fromstring(built["mapgroupproto_text"])
        self.assertIsNone(proto_root.find("./group[@name='Land_Wreck_C130J_Cargo']"))
        self.assertIsNotNone(proto_root.find("./group[@name='Wreck_Mi8_Crashed']"))
        events_root = ET.fromstring(built["events_text"])
        child = events_root.find("./event[@name='StaticWanderingBot_52_airdrop']/children/child")
        self.assertIsNotNone(child)
        self.assertEqual("Wreck_Mi8_Crashed", child.get("type"))
        self.assertTrue(
            any("unsafe visual scene" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        self.assertNotIn("Land_Wreck_C130J_Cargo", built["events_text"])
        self.assertNotIn("Land_Wreck_C130J_Cargo", built["spawns_text"])
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_visual_airdrop_moves_clear_of_existing_vehicle_spawn(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": (
                '<eventposdef><event name="VehicleHatchback02"><pos x="5000" z="5000" a="0" /></event></eventposdef>',
                f"{base_path}/cfgeventspawns.xml",
            ),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    53,
                    "airdrop",
                    "WoodenCrate",
                    visual_marker=True,
                    scene_type="helicopter_crash",
                    loot_preset="military_high",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        spawns_root = ET.fromstring(built["spawns_text"])
        airdrop_pos = spawns_root.find("./event[@name='StaticWanderingBot_53_airdrop']/pos")
        self.assertIsNotNone(airdrop_pos)
        self.assertNotEqual(("5000", "5000"), (airdrop_pos.get("x"), airdrop_pos.get("z")))
        distance = math.hypot(float(airdrop_pos.get("x")) - 5000, float(airdrop_pos.get("z")) - 5000)
        self.assertGreaterEqual(distance, 240)
        self.assertTrue(
            any("overlapped `VehicleHatchback02`" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_airdrop_build_repairs_vehicle_types_economy(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        bad_types = (
            '<types>'
            '<type name="Hatchback_02"><nominal>9</nominal><lifetime>3</lifetime><restock>1800</restock>'
            '<min>6</min><flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" '
            'count_in_player="0" crafted="0" deloot="1" /></type>'
            '<type name="Truck_01_Wheel"><nominal>111</nominal><lifetime>28800</lifetime>'
            '<restock>0</restock><min>96</min><flags count_in_cargo="0" count_in_hoarder="0" '
            'count_in_map="1" count_in_player="0" crafted="0" deloot="0" /></type>'
            '<type name="SeaChest"><nominal>20</nominal><min>10</min>'
            '<flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" '
            'count_in_player="0" crafted="0" deloot="0" /></type>'
            '</types>'
        )
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "types_path": (bad_types, f"{base_path}/db/types.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": ("<spawnabletypes></spawnabletypes>", f"{base_path}/cfgspawnabletypes.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    57,
                    "airdrop",
                    "WoodenCrate",
                    visual_marker=True,
                    scene_type="helicopter_crash",
                    loot_preset="military_high",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertEqual(f"{base_path}/db/types.xml", built.get("types_path"))
        types_root = ET.fromstring(built["types_text"])
        hatchback = types_root.find("./type[@name='Hatchback_02']")
        self.assertIsNotNone(hatchback)
        self.assertEqual("0", hatchback.findtext("nominal"))
        self.assertEqual("0", hatchback.findtext("min"))
        self.assertEqual("0", hatchback.find("flags").get("deloot"))
        wheel = types_root.find("./type[@name='Truck_01_Wheel']")
        self.assertIsNotNone(wheel)
        self.assertEqual("111", wheel.findtext("nominal"))
        self.assertEqual("96", wheel.findtext("min"))
        chest = types_root.find("./type[@name='SeaChest']")
        self.assertIsNotNone(chest)
        self.assertEqual("20", chest.findtext("nominal"))
        self.assertEqual("10", chest.findtext("min"))
        self.assertTrue(
            any("Repaired `types.xml` vehicle economy controls" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))
        scope_ok, scope_messages = bot.validate_console_ce_upload_scope(built)
        self.assertFalse(scope_ok)
        self.assertIn("live source baseline check blocked upload", "\n".join(scope_messages))

    def test_zombie_horde_uses_native_infected_loot_not_spawnabletypes(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": (
                '<spawnabletypes><type name="ZmbM_SoldierNormal"><cargo chance="1.00"><item name="Rag" /></cargo></type></spawnabletypes>',
                f"{base_path}/cfgspawnabletypes.xml",
            ),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    42,
                    "zombie_horde",
                    "ZmbM_SoldierNormal",
                    loot=["Rag", "BandageDressing"],
                    loot_preset="medical",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertFalse(built.get("spawnabletypes_text"))
        self.assertFalse(built.get("spawnabletypes_path"))
        events_root = ET.fromstring(built["events_text"])
        spawns_root = ET.fromstring(built["spawns_text"])
        self.assertFalse([
            node.get("name")
            for node in events_root.findall("event")
            if str(node.get("name") or "").startswith("InfectedWanderingBot_")
        ])
        self.assertFalse([
            node.get("name")
            for node in spawns_root.findall("event")
            if str(node.get("name") or "").startswith("InfectedWanderingBot_")
        ])
        zombie_root = ET.fromstring(built["zombie_territories_text"])
        zone = zombie_root.find(".//zone[@name='InfectedArmy']")
        self.assertIsNotNone(zone)
        self.assertEqual("5000", zone.get("x"))
        self.assertEqual("5000", zone.get("z"))
        self.assertNotIn("y", zone.attrib)
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_custom_mummy_castle_horde_builds_one_event_four_matching_zones_and_types_entry(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            # Preserve the historical lower-case vanilla entry; the builder
            # must add the exact ZmbM_Mummy type alongside it.
            "types_path": ("<types><type name=\"Zmbm_Mummy\" /></types>", f"{base_path}/db/types.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        castles = [
            ("Altar Castle", 1420, 9300),
            ("Zub Castle", 6535, 5625),
            ("Devil's Castle", 6895, 11430),
            ("Black Castle", 10220, 12030),
        ]
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    900 + index,
                    "zombie_horde",
                    "ZmbM_Mummy",
                    preset="custom",
                    name=name,
                    x=x,
                    z=z,
                    count=7,
                    zombie_min_count=3,
                    zombie_max_count=10,
                    radius=85,
                )
                for index, (name, x, z) in enumerate(castles)
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        events_root = ET.fromstring(built["events_text"])
        managed = [node for node in events_root.findall("event") if str(node.get("name") or "").startswith("InfectedWanderingBot")]
        self.assertEqual(1, len(managed))
        event_name = managed[0].get("name")
        self.assertEqual("player", managed[0].findtext("position"))
        self.assertEqual("custom", managed[0].findtext("limit"))
        child = managed[0].find("./children/child")
        self.assertIsNotNone(child)
        self.assertEqual("ZmbM_Mummy", child.get("type"))
        self.assertEqual("0", child.get("max"))
        self.assertEqual("30", child.get("min"))

        spawns_root = ET.fromstring(built["spawns_text"])
        self.assertIsNone(spawns_root.find(f"./event[@name='{event_name}']"))
        zombie_root = ET.fromstring(built["zombie_territories_text"])
        zones = zombie_root.findall(f".//zone[@name='{event_name}']")
        self.assertEqual(4, len(zones))
        self.assertEqual({("1420", "9300"), ("6535", "5625"), ("6895", "11430"), ("10220", "12030")}, {(zone.get("x"), zone.get("z")) for zone in zones})
        self.assertTrue(all(zone.get("dmin") == "3" and zone.get("dmax") == "10" and zone.get("r") == "85" for zone in zones))

        types_root = ET.fromstring(built["types_text"])
        self.assertIsNotNone(types_root.find("./type[@name='ZmbM_Mummy']"))
        self.assertIsNotNone(types_root.find("./type[@name='Zmbm_Mummy']"))
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_legacy_hordetrigger_spawn_block_is_removed(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        legacy_spawns = (
            '<eventposdef>'
            '<event name="HordeTrigger"><pos x="1" z="2" a="0" /></event>'
            '<event name="AnimalBear"><pos x="3" z="4" a="0" /></event>'
            '</eventposdef>'
        )
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": (legacy_spawns, f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    42,
                    "zombie_horde",
                    "ZmbM_SoldierNormal",
                    preset="military_zombie",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        spawns_root = ET.fromstring(built["spawns_text"])
        self.assertIsNone(spawns_root.find("./event[@name='HordeTrigger']"))
        self.assertIsNotNone(spawns_root.find("./event[@name='AnimalBear']"))
        self.assertFalse([
            node.get("name")
            for node in spawns_root.findall("event")
            if str(node.get("name") or "").startswith("InfectedWanderingBot_")
        ])
        zombie_root = ET.fromstring(built["zombie_territories_text"])
        self.assertIsNotNone(zombie_root.find(".//zone[@name='InfectedArmy']"))
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_legacy_livonia_revamp_wooden_crate_events_are_removed(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        legacy_events = (
            '<events>'
            '<event name="StaticLivoniaRevampLoot_01"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>7200</lifetime><restock>0</restock><saferadius>0</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>100</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="0" />'
            '<position>fixed</position><limit>child</limit><active>1</active>'
            '<children><child type="StaticObj_Misc_WoodenCrate_5x" lootmin="20" lootmax="40" min="1" max="1" /></children>'
            '</event>'
            '<event name="StaticLivoniaRevampLoot_99"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>7200</lifetime><restock>0</restock><saferadius>0</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>100</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="0" />'
            '<position>fixed</position><limit>child</limit><active>1</active>'
            '<children><child type="Wreck_Mi8_Crashed" lootmin="20" lootmax="40" min="1" max="1" /></children>'
            '</event>'
            '</events>'
        )
        legacy_spawns = (
            '<eventposdef>'
            '<event name="StaticLivoniaRevampLoot_01"><pos x="1000" z="2000" a="0" /></event>'
            '<event name="StaticLivoniaRevampLoot_99"><pos x="3000" z="4000" a="0" /></event>'
            '</eventposdef>'
        )
        sources = {
            "events_path": (legacy_events, f"{base_path}/db/events.xml"),
            "spawns_path": (legacy_spawns, f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    42,
                    "zombie_horde",
                    "ZmbM_SoldierNormal",
                    preset="military_zombie",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        events_root = ET.fromstring(built["events_text"])
        spawns_root = ET.fromstring(built["spawns_text"])
        self.assertIsNone(events_root.find("./event[@name='StaticLivoniaRevampLoot_01']"))
        self.assertIsNone(spawns_root.find("./event[@name='StaticLivoniaRevampLoot_01']"))
        self.assertIsNotNone(events_root.find("./event[@name='StaticLivoniaRevampLoot_99']"))
        self.assertIsNotNone(spawns_root.find("./event[@name='StaticLivoniaRevampLoot_99']"))
        self.assertTrue(
            any("stale Livonia revamp wooden-crate" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        events_scope_ok, events_scope_message = bot.validate_managed_ce_xml_scope(
            "events.xml",
            built["events_source_text"],
            built["events_text"],
        )
        self.assertTrue(events_scope_ok, events_scope_message)
        spawns_scope_ok, spawns_scope_message = bot.validate_managed_ce_xml_scope(
            "cfgeventspawns.xml",
            built["spawns_source_text"],
            built["spawns_text"],
        )
        self.assertTrue(spawns_scope_ok, spawns_scope_message)

    def test_cherno_revamp_backup_events_are_repaired_to_static_prefix(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        legacy_events = (
            '<events>'
            '<event name="StaticChernoRevampBackupLoot_23"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>7200</lifetime><restock>0</restock><saferadius>0</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>100</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="0" />'
            '<position>fixed</position><limit>child</limit><active>1</active>'
            '<children><child type="StaticObj_Wreck_HMMWV_DE" lootmin="7" lootmax="15" min="1" max="1" /></children>'
            '</event>'
            '<event name="ChernoRevampBackupLoot_26"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>7200</lifetime><restock>0</restock><saferadius>0</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>100</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="0" />'
            '<position>fixed</position><limit>child</limit><active>1</active>'
            '<children><child type="StaticObj_Wreck_HMMWV_DE" lootmin="7" lootmax="15" min="1" max="1" /></children>'
            '</event>'
            '</events>'
        )
        legacy_spawns = (
            '<eventposdef>'
            '<event name="StaticChernoRevampBackupLoot_23"><pos x="4770" z="7950" a="0" group="ChernoRevampBackupLootGrp_23" /></event>'
            '<event name="ChernoRevampBackupLoot_26"><pos x="4776.79" z="7951.65" a="0" group="ChernoRevampBackupLootGrp_26" /></event>'
            '<event name="StaticAirplaneCrate"><pos x="1" z="2" a="0" /></event>'
            '<event name="Static_NewAirDrops"><pos x="3" z="4" a="0" /></event>'
            '<event name="VehicleTransitBus"><pos x="5" z="6" a="0" /></event>'
            '</eventposdef>'
        )
        sources = {
            "events_path": (legacy_events, f"{base_path}/db/events.xml"),
            "spawns_path": (legacy_spawns, f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    42,
                    "zombie_horde",
                    "ZmbM_SoldierNormal",
                    preset="military_zombie",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        events_root = ET.fromstring(built["events_text"])
        spawns_root = ET.fromstring(built["spawns_text"])
        self.assertIsNone(events_root.find("./event[@name='ChernoRevampBackupLoot_26']"))
        self.assertIsNone(spawns_root.find("./event[@name='ChernoRevampBackupLoot_26']"))
        self.assertIsNotNone(events_root.find("./event[@name='StaticChernoRevampBackupLoot_26']"))
        repaired_spawn = spawns_root.find("./event[@name='StaticChernoRevampBackupLoot_26']/pos")
        self.assertIsNotNone(repaired_spawn)
        self.assertIsNone(repaired_spawn.get("group"))
        already_static_spawn = spawns_root.find("./event[@name='StaticChernoRevampBackupLoot_23']/pos")
        self.assertIsNotNone(already_static_spawn)
        self.assertIsNone(already_static_spawn.get("group"))
        self.assertIsNone(spawns_root.find("./event[@name='StaticAirplaneCrate']"))
        self.assertIsNone(spawns_root.find("./event[@name='Static_NewAirDrops']"))
        self.assertIsNone(spawns_root.find("./event[@name='VehicleTransitBus']"))
        proto_root = ET.fromstring(built["mapgroupproto_text"])
        self.assertIsNotNone(proto_root.find("./group[@name='StaticObj_Wreck_HMMWV_DE']"))
        self.assertTrue(
            any("Repaired Charnarus revamp backup" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )

    def test_cherno_revamp_backup_childless_events_copy_child_from_eventgroup_before_group_cleanup(self):
        base_path = "/dayzxb_missions/dayzOffline.chernarusplus"
        legacy_events = (
            '<events>'
            '<event name="StaticChernoRevampBackupLoot_23"><nominal>1</nominal><min>1</min><max>1</max>'
            '<lifetime>7200</lifetime><restock>0</restock><saferadius>0</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>100</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="0" />'
            '<position>fixed</position><limit>child</limit><active>1</active>'
            '<children />'
            '</event>'
            '</events>'
        )
        legacy_spawns = (
            '<eventposdef>'
            '<event name="StaticChernoRevampBackupLoot_23">'
            '<pos x="4770" z="7950" a="0" group="ChernoRevampBackupLootGrp_23" />'
            '</event>'
            '</eventposdef>'
        )
        legacy_eventgroups = (
            '<eventgroupdef>'
            '<group name="ChernoRevampBackupLootGrp_23">'
            '<child type="StaticObj_Wreck_HMMWV_DE" lootmin="7" lootmax="15" min="1" max="1" x="0" y="0" z="0" a="0" />'
            '</group>'
            '</eventgroupdef>'
        )
        sources = {
            "events_path": (legacy_events, f"{base_path}/db/events.xml"),
            "spawns_path": (legacy_spawns, f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": (legacy_eventgroups, f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/zombie_territories.xml"):
                return True, "zombie_territories source", '<territory-type><territory color="1291845632" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Cherno",
            "server_map": "chernarus",
            "server_platform": "xbox",
            "scenario_events": [],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        events_root = ET.fromstring(built["events_text"])
        spawns_root = ET.fromstring(built["spawns_text"])
        event_node = events_root.find("./event[@name='StaticChernoRevampBackupLoot_23']")
        self.assertIsNotNone(event_node)
        child = event_node.find("./children/child")
        self.assertIsNotNone(child)
        self.assertEqual(child.get("type"), "StaticObj_Wreck_HMMWV_DE")
        self.assertEqual(child.get("lootmax"), "15")
        spawn_pos = spawns_root.find("./event[@name='StaticChernoRevampBackupLoot_23']/pos")
        self.assertIsNotNone(spawn_pos)
        self.assertIsNone(spawn_pos.get("group"))
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, messages)
        self.assertFalse(
            any("has no `<child>` classname" in str(message) for message in messages),
            messages,
        )
        self.assertTrue(
            any("static event child classname" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        self.assertTrue(
            any("obsolete cfgeventgroups reference" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        events_scope_ok, events_scope_message = bot.validate_managed_ce_xml_scope(
            "events.xml",
            built["events_source_text"],
            built["events_text"],
        )
        self.assertTrue(events_scope_ok, events_scope_message)
        spawns_scope_ok, spawns_scope_message = bot.validate_managed_ce_xml_scope(
            "cfgeventspawns.xml",
            built["spawns_source_text"],
            built["spawns_text"],
        )
        self.assertTrue(spawns_scope_ok, spawns_scope_message)
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_animal_pack_reuses_vanilla_event_and_live_territory_file(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        vanilla_spawns = '<eventposdef><event name="AnimalBear"><pos x="1" z="2" a="0" /></event></eventposdef>'
        vanilla_events = (
            '<events><event name="AnimalBear"><nominal>10</nominal><min>5</min><max>12</max>'
            '<lifetime>180</lifetime><restock>0</restock><saferadius>200</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>0</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="1" />'
            '<position>fixed</position><limit>custom</limit><active>1</active>'
            '<children><child lootmax="0" lootmin="0" max="1" min="1" type="Animal_UrsusArctos" /></children>'
            '</event></events>'
        )
        sources = {
            "events_path": (vanilla_events, f"{base_path}/db/events.xml"),
            "spawns_path": (vanilla_spawns, f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": (
                '<env><territories><file path="env/bear_territories.xml" />'
                '<territory type="Herd" name="Bear" behavior="BlissBearGroupBeh">'
                '<file usable="bear_territories" /></territory></territories></env>',
                f"{base_path}/cfgenvironment.xml",
            ),
        }
        vanilla_bear_territories = (
            '<territory-type><territory color="889148672">'
            '<zone name="Graze" smin="0" smax="0" dmin="0" dmax="0" x="1" z="2" r="200" />'
            '</territory></territory-type>'
        )

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/bear_territories.xml"):
                return True, "bear_territories source", vanilla_bear_territories
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    20,
                    "animal_pack",
                    "Animal_UrsusArctos",
                    preset="bear",
                    count=2,
                    radius=90,
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        spawns_root = ET.fromstring(built["spawns_text"])
        vanilla_spawn = spawns_root.find("./event[@name='AnimalBear']")
        self.assertIsNotNone(vanilla_spawn)
        vanilla_positions = vanilla_spawn.findall("pos")
        self.assertEqual(1, len(vanilla_positions))
        self.assertEqual("1", vanilla_positions[0].get("x"))
        self.assertEqual("2", vanilla_positions[0].get("z"))
        for pos in vanilla_positions:
            self.assertNotIn("y", pos.attrib)

        managed_spawn = spawns_root.find("./event[@name='AnimalWanderingBot_animal_bear']")
        self.assertIsNone(managed_spawn)
        events_root = ET.fromstring(built["events_text"])
        vanilla_bear = events_root.find("./event[@name='AnimalBear']")
        self.assertIsNotNone(vanilla_bear)
        self.assertEqual("10", vanilla_bear.findtext("nominal"))
        self.assertEqual("5", vanilla_bear.findtext("min"))
        self.assertEqual("12", vanilla_bear.findtext("max"))
        self.assertEqual("custom", vanilla_bear.findtext("limit"))

        custom_bear = events_root.find("./event[@name='AnimalWanderingBot_animal_bear']")
        self.assertIsNone(custom_bear)
        territory_files = built.get("animal_territory_files") or []
        self.assertEqual(1, len(territory_files))
        self.assertEqual(
            "/dayzxb_missions/dayzOffline.enoch/env/bear_territories.xml",
            territory_files[0].get("path"),
        )
        self.assertEqual(["AnimalBear"], territory_files[0].get("event_names"))
        territory_root = ET.fromstring(territory_files[0]["text"])
        zone = next((node for node in territory_root.findall(".//zone") if node.get("x") == "5000"), None)
        self.assertIsNotNone(zone)
        self.assertEqual("HuntingGround", zone.get("name"))
        self.assertEqual("2", zone.get("dmin"))
        self.assertEqual("2", zone.get("dmax"))
        self.assertEqual("5000", zone.get("x"))
        self.assertEqual("5000", zone.get("z"))
        self.assertFalse(built.get("cfgenvironment_text"))
        self.assertTrue(
            any(
                "reuses vanilla animal event `AnimalBear`" in str(message)
                for message in built.get("messages", [])
            ),
            built.get("messages", []),
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))
        scope_ok, scope_messages = bot.validate_console_ce_upload_scope(built)
        self.assertFalse(scope_ok)
        self.assertIn("live source baseline check blocked upload", "\n".join(scope_messages))

    def test_animal_pack_replaces_stale_double_herd_environment_reference(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        stale_environment = (
            '<env><territories>'
            '<file path="env/bear_territories.xml" />'
            '<territory type="Herd" name="Bear" behavior="BlissBearGroupBeh">'
            '<file usable="bear_territories" />'
            '</territory>'
            '<file path="env/wanderingbot_animal_bear_territories.xml" />'
            '<territory type="Herd" name="HerdWanderingBot_animal_bear" behavior="BlissBearGroupBeh">'
            '<file usable="wanderingbot_animal_bear_territories" />'
            '</territory>'
            '</territories></env>'
        )
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": (stale_environment, f"{base_path}/cfgenvironment.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/bear_territories.xml"):
                return True, "bear_territories source", '<territory-type><territory color="889148672" /></territory-type>'
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(20, "animal_pack", "Animal_UrsusArctos", preset="bear", count=2, radius=90)
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertEqual(1, len(built.get("animal_territory_files") or []))
        self.assertTrue(built.get("cfgenvironment_text"))
        self.assertNotIn("wanderingbot_animal_bear_territories.xml", built["cfgenvironment_text"])
        self.assertNotIn("HerdWanderingBot_animal_bear", built["cfgenvironment_text"])
        self.assertIn('name="Bear"', built["cfgenvironment_text"])
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))
        scope_ok, scope_messages = bot.validate_console_ce_upload_scope(built)
        self.assertFalse(scope_ok)
        self.assertIn("live source baseline check blocked upload", "\n".join(scope_messages))

    def test_multiple_bear_packs_share_one_stable_territory_file(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        vanilla_events = (
            '<events><event name="AnimalBear"><nominal>0</nominal><min>5</min><max>8</max>'
            '<lifetime>180</lifetime><restock>0</restock><saferadius>200</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>0</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="1" />'
            '<position>fixed</position><limit>custom</limit><active>1</active>'
            '<children><child lootmax="0" lootmin="0" max="1" min="1" type="Animal_UrsusArctos" /></children>'
            '</event></events>'
        )
        sources = {
            "events_path": (vanilla_events, f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": (
                '<env><territories><file path="env/bear_territories.xml" />'
                '<territory type="Herd" name="Bear" behavior="BlissBearGroupBeh">'
                '<file usable="bear_territories" /></territory></territories></env>',
                f"{base_path}/cfgenvironment.xml",
            ),
        }
        vanilla_bear_territories = (
            '<territory-type><territory color="889148672">'
            '<zone name="Graze" smin="0" smax="0" dmin="0" dmax="0" x="1" z="2" r="200" />'
            '</territory></territory-type>'
        )

        def fake_download(_config, _guild_id, key, _requested_path=""):
            if key == "types_path" and key not in sources:
                return "<types></types>", f"{base_path}/db/types.xml", f"{key} source"
            text, path = sources[key]
            return text, path, f"{key} source"

        def fake_download_text(_config, remote_path):
            if str(remote_path or "").endswith("/env/bear_territories.xml"):
                return True, "bear_territories source", vanilla_bear_territories
            return False, "missing", ""

        bot.download_console_ce_source = fake_download
        bot.download_text_file_from_nitrado = fake_download_text
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(20, "animal_pack", "Animal_UrsusArctos", preset="bear", count=1, radius=70),
                _base_event(21, "animal_pack", "Animal_UrsusArctos", preset="bear", count=2, radius=90, x=5100, z=5200),
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        territory_files = built.get("animal_territory_files") or []
        self.assertEqual(1, len(territory_files))
        self.assertEqual(
            "/dayzxb_missions/dayzOffline.enoch/env/bear_territories.xml",
            territory_files[0].get("path"),
        )
        territory_root = ET.fromstring(territory_files[0]["text"])
        zones = [node for node in territory_root.findall(".//zone") if node.get("x") in {"5000", "5100"}]
        self.assertEqual(2, len(zones))
        self.assertEqual({"5000", "5100"}, {zone.get("x") for zone in zones})
        self.assertEqual({"1", "2"}, {zone.get("dmax") for zone in zones})
        self.assertFalse(built.get("cfgenvironment_text"))
        events_root = ET.fromstring(built["events_text"])
        animal_event_names = [
            node.get("name")
            for node in events_root.findall("event")
            if str(node.get("name") or "").startswith("AnimalWanderingBot")
        ]
        self.assertEqual([], animal_event_names)
        spawns_root = ET.fromstring(built["spawns_text"])
        managed_spawn = spawns_root.find("./event[@name='AnimalWanderingBot_animal_bear']")
        self.assertIsNone(managed_spawn)

        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_animal_environment_cleanup_removes_stale_managed_comments(self):
        env_root = ET.fromstring("""<env><territories>
            <file path="env/bear_territories.xml" />
            <!-- Wandering Bot: managed animal territory file env/wanderingbot_animal_bear_territories.xml -->
            <file path="env/wanderingbot_animal_bear_territories.xml" />
            <!-- Wandering Bot: managed animal territory HerdWanderingBot_animal_bear -->
            <territory type="Herd" name="HerdWanderingBot_animal_bear" behavior="BlissBearGroupBeh">
                <file usable="wanderingbot_animal_bear_territories" />
            </territory>
        </territories></env>""", parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))

        removed_files, removed_territories = bot.remove_wandering_environment_nodes(env_root)

        self.assertEqual(1, removed_files)
        self.assertEqual(1, removed_territories)
        self.assertIsNotNone(env_root.find("./territories/file[@path='env/bear_territories.xml']"))
        self.assertFalse(
            any(
                bot.is_xml_comment_node(child)
                and "managed animal territory" in str(child.text or "").lower()
                for child in list(env_root.find("territories"))
            )
        )

    def test_animal_pack_validation_rejects_custom_event_missing_herd_template(self):
        event_name = "AnimalWanderingBot_animal_bear"
        built = {
            "map_key": "livonia",
            "events_path": "/dayzxb_missions/dayzOffline.enoch/db/events.xml",
            "events_text": (
                f'<events><event name="{event_name}"><nominal>2</nominal><min>2</min><max>2</max>'
                '<lifetime>3600</lifetime><restock>0</restock><saferadius>0</saferadius>'
                '<distanceradius>0</distanceradius><cleanupradius>100</cleanupradius>'
                '<flags deletable="0" init_random="0" remove_damaged="1" />'
                '<position>fixed</position><limit>child</limit><active>1</active>'
                '<children><child lootmax="0" lootmin="0" max="1" min="1" type="Animal_UrsusArctos" /></children>'
                '</event></events>'
            ),
            "spawns_path": "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
            "spawns_text": f'<eventposdef><event name="{event_name}"><pos x="5000" z="5000" a="0" active="1" /></event></eventposdef>',
            "cfgenvironment_text": "<env><territories /></env>",
            "animal_territory_files": [],
        }

        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)

        self.assertTrue(ok, "\n".join(messages))

        built["animal_territory_files"] = [{
            "path": "/dayzxb_missions/dayzOffline.enoch/env/wanderingbot_animal_bear_territories.xml",
            "text": (
                '<territory-type><territory color="4294923520">'
                '<zone name="HuntingGround" smin="0" smax="0" dmin="2" dmax="2" x="5000" z="5000" r="90" />'
                "</territory></territory-type>"
            ),
            "event_names": [event_name],
        }]
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)

        self.assertFalse(ok)
        self.assertIn(
            "`AnimalWanderingBot_animal_bear` is a custom animal event but is missing matching Herd template `HerdWanderingBot_animal_bear` in `cfgenvironment.xml`.",
            messages,
        )

        built["cfgenvironment_text"] = (
            "<env><territories>"
            '<file path="env/wanderingbot_animal_bear_territories.xml" />'
            '<territory type="Herd" name="WanderingBot_animal_bear" behavior="BlissBearGroupBeh">'
            '<file usable="wanderingbot_animal_bear_territories" />'
            "</territory>"
            "</territories></env>"
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))


class CeValidationDiagnosticsTests(unittest.TestCase):
    def _base_bundle(self):
        return {
            "events_path": "/dayzxb_missions/dayzOffline.sakhal/db/events.xml",
            "events_text": "<events />",
            "spawns_path": "/dayzxb_missions/dayzOffline.sakhal/cfgeventspawns.xml",
            "spawns_text": "<eventposdef />",
        }

    def test_malformed_mapgroupproto_reports_exact_file_path_and_line(self):
        built = self._base_bundle()
        built.update({
            "mapgroupproto_context_path": "/dayzxb_missions/dayzOffline.sakhal/mapgroupproto.xml",
            "mapgroupproto_context_text": (
                "<prototype>\n"
                '  <group name="Wreck_Mi8_Crashed">\n'
                "    <!-- broken managed point\n"
                "  </group>\n"
                "</prototype>\n"
            ),
        })

        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        diagnostic = "\n".join(messages)

        self.assertFalse(ok)
        self.assertIn("`mapgroupproto.xml` validation failed before upload", diagnostic)
        self.assertIn("`/dayzxb_missions/dayzOffline.sakhal/mapgroupproto.xml`", diagnostic)
        self.assertIn("ParseError", diagnostic)
        self.assertIn("line 3", diagnostic)
        self.assertIn("Failing line: `<!-- broken managed point`", diagnostic)

    def test_malformed_events_reports_events_instead_of_generic_ce_xml(self):
        built = self._base_bundle()
        built["events_text"] = "<events>\n  <event name=\"Broken\">\n</events>"

        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        diagnostic = "\n".join(messages)
        public_error = bot._scenario_notice_public_error(messages)

        self.assertFalse(ok)
        self.assertIn("`events.xml` validation failed before upload", diagnostic)
        self.assertIn("`/dayzxb_missions/dayzOffline.sakhal/db/events.xml`", diagnostic)
        self.assertNotIn("CE file validation failed", diagnostic)
        self.assertIn("events.xml", public_error)
        self.assertIn("/dayzxb_missions/dayzOffline.sakhal/db/events.xml", public_error)

    def test_malformed_effect_area_json_reports_file_path_and_source_line(self):
        built = self._base_bundle()
        built.update({
            "cfgeffectarea_path": "/dayzxb_missions/dayzOffline.sakhal/cfgEffectArea.json",
            "cfgeffectarea_text": '{\n  "Areas": [\n    {"Name": "Broken",}\n  ]\n}',
        })

        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        diagnostic = "\n".join(messages)

        self.assertFalse(ok)
        self.assertIn("`cfgEffectArea.json` validation failed before upload", diagnostic)
        self.assertIn("line 3", diagnostic)
        self.assertIn('Failing line: `{"Name": "Broken",}`', diagnostic)


class CeUploadAuthorizationAndBackupTests(unittest.TestCase):
    def _backup_build(self):
        return {
            "map_key": "chernarus",
            "events_path": "/dayzxb_missions/dayzOffline.chernarusplus/db/events.xml",
            "events_source_text": '<events><event name="VanillaRecord" /></events>',
        }

    def test_background_upload_requires_an_explicit_event_request_marker(self):
        event = {
            "created_by": "dashboard",
            "event_type": "airdrop",
            "upload_status": "waiting_for_bot_upload",
            "status": "Native CE XML upload requested",
        }

        self.assertFalse(bot.scenario_event_upload_needs_resolution(event))

        event["ce_upload_requested_at"] = "2026-07-29T10:00:00+00:00"
        event["ce_upload_request_action"] = "create"
        self.assertTrue(bot.scenario_event_upload_needs_resolution(event))

    def test_failed_timestamped_backup_blocks_the_live_upload(self):
        source = '<events><event name="VanillaRecord" /></events>'
        with patch.object(bot, "download_text_file_from_nitrado", return_value=(True, "downloaded", source)), \
             patch.object(bot, "validate_console_ce_live_source_baseline", return_value=(True, "")), \
             patch.object(bot, "upload_ce_latest_backup_to_nitrado", return_value=(False, "backup rejected")):
            ok, messages = bot.backup_remote_ce_sources_before_upload({}, self._backup_build())

        self.assertFalse(ok)
        rendered = "\n".join(messages)
        self.assertIn("timestamped backup", rendered)
        self.assertIn("could not be created before the live upload", rendered)

    def test_verified_timestamped_and_latest_backups_are_both_written(self):
        source = '<events><event name="VanillaRecord" /></events>'
        backup_paths = []

        def capture_backup(_config, _label, backup_path, _content):
            backup_paths.append(backup_path)
            return True, "verified"

        with patch.object(bot, "download_text_file_from_nitrado", return_value=(True, "downloaded", source)), \
             patch.object(bot, "validate_console_ce_live_source_baseline", return_value=(True, "")), \
             patch.object(bot, "upload_ce_latest_backup_to_nitrado", side_effect=capture_backup), \
             patch.object(bot, "cleanup_wanderingbot_backups_for_path", return_value=([], [])):
            ok, messages = bot.backup_remote_ce_sources_before_upload({}, self._backup_build())

        self.assertTrue(ok, "\n".join(messages))
        self.assertEqual(2, len(backup_paths))
        self.assertIn(".wanderingbot-backup-", backup_paths[0])
        self.assertTrue(backup_paths[0].endswith("Z"))
        self.assertTrue(backup_paths[1].endswith(".wanderingbot-backup-latest"))

    def test_restart_schedule_cannot_invoke_native_ce_uploader(self):
        config = {"restart_interval_hours": 1, "restart_start_hour": 0}
        upload_calls = []

        async def no_results(*_args, **_kwargs):
            return []

        async def no_dashboard_upload(*_args, **_kwargs):
            return False

        async def inline_to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        def fail_if_called(*_args, **_kwargs):
            upload_calls.append(True)
            return False, {}, ["scheduler invoked CE uploader"]

        with patch.object(bot, "active_adm_config_items", return_value=[("guild-1", config)]), \
             patch.object(bot, "mark_server_control_scheduler_status", return_value=False), \
             patch.object(bot, "apply_due_damage_schedule", return_value=[]), \
             patch.object(bot, "queue_due_vehicle_reset_schedule", return_value=None), \
             patch.object(bot, "process_cfgignorelist_vehicle_reset_events", new=no_results), \
             patch.object(bot, "process_economy_vehicle_reset_events", new=no_results), \
             patch.object(bot, "process_dashboard_scenario_xml_upload", new=no_dashboard_upload), \
             patch.object(bot, "_restart_schedule_matches", return_value=True), \
             patch.object(bot, "bridge_scenario_events", return_value=[]), \
             patch.object(bot, "delivery_bridge_scenario_events", return_value=[]), \
             patch.object(bot, "native_ce_scenario_events", return_value=[{"id": 1}]), \
             patch.object(bot, "console_ce_event_config", return_value={"enabled": True}), \
             patch.object(bot, "queue_entries_for_guild", return_value=[]), \
             patch.object(bot, "upload_console_ce_event_files", side_effect=fail_if_called), \
             patch.object(bot.asyncio, "to_thread", new=inline_to_thread):
            asyncio.run(bot.restart_delivery_processor())

        self.assertEqual([], upload_calls)

    def test_bridge_upload_does_not_queue_native_ce_cleanup(self):
        config = {}
        event = {"id": 1, "event_type": "airdrop"}
        with patch.object(bot, "scenario_event_uses_delivery_bridge", return_value=True), \
             patch.object(bot, "write_and_upload_delivery_xml", return_value=(True, "/tmp/deliveries.xml")):
            ok, _path, _messages = bot.upload_delivery_bridge_scenario_events(
                "guild-1",
                config,
                [event],
                "test",
            )

        self.assertTrue(ok)
        self.assertNotIn("scenario_events_cleanup_pending", config)

    def test_generic_cleanup_flag_without_native_delete_cannot_invoke_uploader(self):
        config = {"scenario_events_cleanup_pending": True, "scenario_events": []}
        upload_calls = []

        def fail_if_called(*_args, **_kwargs):
            upload_calls.append(True)
            return False, {}, ["unexpected"]

        with patch.object(bot, "upload_console_ce_event_files", side_effect=fail_if_called):
            changed = asyncio.run(bot.process_dashboard_scenario_xml_upload("guild-1", config))

        self.assertFalse(changed)
        self.assertEqual([], upload_calls)

    def test_direct_dashboard_uploader_rejects_missing_explicit_request(self):
        config = {"scenario_events": []}
        upload_calls = []

        def fail_if_called(*_args, **_kwargs):
            upload_calls.append(True)
            return False, {}, ["unexpected"]

        with patch.object(bot, "load_guild_configs"), \
             patch.object(bot, "config_for_server_runtime", return_value=config), \
             patch.object(bot, "upload_console_ce_event_files", side_effect=fail_if_called):
            result = bot.dashboard_upload_console_ce_event_files("guild-1")

        self.assertFalse(result["ok"])
        self.assertIn("no explicit dashboard event", result["messages"][0])
        self.assertEqual([], upload_calls)


if __name__ == "__main__":
    unittest.main()
