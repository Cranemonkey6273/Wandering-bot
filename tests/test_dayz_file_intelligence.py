from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _bot_loader import import_bot_module  # noqa: E402
from dayz_file_intelligence import dayz_agent_file_knowledge, dayz_agent_general_knowledge, dayz_custom_json_path, dayz_dependency_plan_for_request, dayz_file_spec_for_path, dayz_filename_for_path, dayz_json_schema_name, dayz_xml_root_for_path, validate_dayz_upload_text, validate_named_xml_upload_preserves_existing, validate_territory_xml_upload_preserves_unmanaged_content, validate_xml_upload_not_effectively_empty, validate_upload_not_dangerously_shrunken  # noqa: E402

bot = import_bot_module()


REFERENCE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dayz_reference"))


class DayZFileIntelligenceTests(unittest.TestCase):
    def test_every_bundled_vanilla_structured_file_rejects_truncated_error_input(self):
        checked = 0
        for directory, _subdirs, filenames in os.walk(REFERENCE_ROOT):
            for filename in filenames:
                if not filename.lower().endswith((".xml", ".json")):
                    continue
                source_path = os.path.join(directory, filename)
                with open(source_path, "r", encoding="utf-8-sig") as handle:
                    content = handle.read().rstrip()
                if len(content) < 2:
                    continue
                # Remove the final structural delimiter, reproducing a common
                # partial copy/download or model-truncation failure.
                malformed = content[:-1]
                ok, message = validate_dayz_upload_text(source_path, malformed)
                with self.subTest(path=os.path.relpath(source_path, REFERENCE_ROOT)):
                    self.assertFalse(ok)
                    self.assertTrue("invalid XML" in message or "invalid JSON" in message, message)
                checked += 1
        self.assertGreaterEqual(checked, 50)

    def test_dependency_plan_distinguishes_map_groups_from_object_spawner(self):
        map_group = dayz_dependency_plan_for_request(
            "Place a new loot-bearing static building and set up its loot points",
            "mapgrouppos.xml",
        )
        map_group_paths = {item["path"]: item for item in map_group["files"]}

        self.assertEqual("map_group_placement", map_group["workflow"])
        self.assertEqual("changed", map_group_paths["mapgrouppos.xml"]["action"])
        self.assertEqual("changed", map_group_paths["mapgroupproto.xml"]["action"])
        self.assertEqual("checked", map_group_paths["db/types.xml"]["action"])
        self.assertEqual("conditional", map_group_paths["cfglimitsdefinition.xml"]["action"])

        object_spawner = dayz_dependency_plan_for_request(
            "Create an ObjectSpawner base at these coordinates",
            "custom/my_base.json",
        )
        object_paths = {item["path"]: item for item in object_spawner["files"]}
        self.assertEqual("object_spawner", object_spawner["workflow"])
        self.assertEqual("changed", object_paths["custom/my_base.json"]["action"])
        self.assertEqual("changed", object_paths["cfggameplay.json"]["action"])
        self.assertEqual("preserved", object_paths["mapgrouppos.xml"]["action"])
        self.assertEqual("preserved", object_paths["mapgroupproto.xml"]["action"])

    def test_dependency_plan_links_the_map_group_proxy_method_without_events(self):
        plan = dayz_dependency_plan_for_request(
            "Use the proxy method to display an M4A1 on a wall.",
            "mapgroupproto.xml",
        )
        files = {item["path"]: item for item in plan["files"]}

        self.assertEqual("map_group_proxy_placement", plan["workflow"])
        self.assertEqual("changed", files["mapgrouppos.xml"]["action"])
        self.assertEqual("changed", files["mapgroupproto.xml"]["action"])
        self.assertEqual("checked", files["db/types.xml"]["action"])
        self.assertEqual("checked", files["db/globals.xml"]["action"])
        self.assertEqual("preserved", files["db/events.xml"]["action"])

    def test_dependency_plan_links_fire_smoke_proxy_scene_files(self):
        plan = dayz_dependency_plan_for_request(
            "Place a fire and smoke effect beneath a Static mass grave event.",
            "mapgroupproto.xml",
        )
        files = {item["path"]: item for item in plan["files"]}

        self.assertEqual("fire_smoke_proxy_event_scene", plan["workflow"])
        for path in ("db/types.xml", "mapgroupproto.xml", "mapgrouppos.xml", "cfgeventspawns.xml", "db/events.xml"):
            self.assertEqual("changed", files[path]["action"], path)
        self.assertEqual("conditional", files["cfglimitsdefinition.xml"]["action"])
        self.assertEqual("checked", files["db/globals.xml"]["action"])
        self.assertEqual("preserved", files["cfgEffectArea.json"]["action"])

    def test_map_group_point_and_proxy_vectors_are_validated(self):
        valid_prototype = """<prototype>
          <group name="EvalPoints" lootmax="1">
            <container name="loot" lootmax="1">
              <point pos="1.5 2.0 -1" range="0.5" height="1.0" />
              <point pos="-1.5 2.0 1" range="0.5" height="1.0" />
            </container>
            <dispatch><proxy type="M4A1" pos="-1 2 1.5" rpy="-225 90 0" /></dispatch>
          </group>
        </prototype>"""
        self.assertEqual((True, ""), validate_dayz_upload_text("mapgroupproto.xml", valid_prototype))

        invalid_cases = (
            (valid_prototype.replace('pos="1.5 2.0 -1"', 'pos="1.5 -1"'), "exactly 3"),
            (valid_prototype.replace('range="0.5"', 'range="-0.5"', 1), "positive finite"),
            (valid_prototype.replace('proxy type="M4A1"', 'proxy type=""'), "missing `type`"),
        )
        for content, expected in invalid_cases:
            with self.subTest(expected=expected):
                ok, message = validate_dayz_upload_text("mapgroupproto.xml", content)
                self.assertFalse(ok)
                self.assertIn(expected, message)

        valid_placement = '<map><group name="EvalPoints" pos="7000 10 7000" rpy="0 90 0" a="90" /></map>'
        self.assertEqual((True, ""), validate_dayz_upload_text("mapgrouppos.xml", valid_placement))
        ok, message = validate_dayz_upload_text(
            "mapgrouppos.xml",
            valid_placement.replace('pos="7000 10 7000"', 'pos="7000 7000"'),
        )
        self.assertFalse(ok)
        self.assertIn("exactly 3", message)

    def test_dependency_plan_uses_explicit_objectspawner_path_named_in_prompt(self):
        plan = dayz_dependency_plan_for_request(
            "Create custom/QA_Camp.json ObjectSpawner and register it in cfgGameplay.json.",
            "cfggameplay.json",
        )
        files = {item["path"]: item for item in plan["files"]}

        self.assertEqual("object_spawner", plan["workflow"])
        self.assertEqual("changed", files["custom/QA_Camp.json"]["action"])
        self.assertEqual("changed", files["cfggameplay.json"]["action"])

    def test_limits_user_file_is_planned_as_aliases_not_new_definitions(self):
        plan = dayz_dependency_plan_for_request(
            "Create a TownVillage alias from the existing Town and Village usages.",
            "cfglimitsdefinitionuser.xml",
        )
        files = {item["path"]: item for item in plan["files"]}

        self.assertEqual("central_economy_definitions", plan["workflow"])
        self.assertEqual("changed", files["cfglimitsdefinitionuser.xml"]["action"])
        self.assertEqual("checked", files["cfglimitsdefinition.xml"]["action"])
        self.assertIn("only creates named aliases", plan["summary"])
        self.assertIn("already exist", files["cfglimitsdefinitionuser.xml"]["reason"])

    def test_dependency_plan_uses_ambient_territories_not_fixed_event_positions(self):
        plan = dayz_dependency_plan_for_request("Create an ambient fox spawner zone", "env/fox_territories.xml")
        files = {item["path"]: item for item in plan["files"]}

        self.assertEqual("ambient_spawner", plan["workflow"])
        self.assertEqual("changed", files["env/*_territories.xml"]["action"])
        self.assertEqual("changed", files["db/events.xml"]["action"])
        self.assertEqual("checked", files["cfgenvironment.xml"]["action"])
        self.assertEqual("preserved", files["cfgeventspawns.xml"]["action"])

    def test_known_vanilla_xml_roots_are_detected_from_paths(self):
        self.assertEqual(
            dayz_xml_root_for_path("/dayzxb_missions/dayzOffline.enoch/db/events.xml"),
            "events",
        )
        self.assertEqual(
            dayz_xml_root_for_path("/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml"),
            "eventposdef",
        )
        self.assertEqual(
            dayz_xml_root_for_path("/dayzxb_missions/dayzOffline.enoch/mapgroupproto.xml"),
            "prototype",
        )
        self.assertEqual(
            dayz_xml_root_for_path("/dayzxb_missions/dayzOffline.enoch/env/zombie_territories.xml"),
            "territory-type",
        )
        self.assertEqual(
            dayz_xml_root_for_path("/dayzxb_missions/dayzOffline.enoch/env/bear_territories.xml"),
            "territory-type",
        )
        self.assertEqual(
            dayz_xml_root_for_path("/dayzxb_missions/dayzOffline.enoch/env/wanderingbot_animal_bear_territories.xml"),
            "territory-type",
        )
        self.assertEqual(
            dayz_xml_root_for_path("/dayzxb_missions/dayzOffline.chernarusplus/cfgweather.xml"),
            "weather",
        )
        self.assertEqual(
            dayz_xml_root_for_path("/dayzxb_missions/dayzOffline.chernarusplus/mapgrouppos.xml"),
            "map",
        )

    def test_cfgweather_uses_the_protected_weather_root(self):
        ok, message = validate_dayz_upload_text(
            "/dayzxb_missions/dayzOffline.chernarusplus/cfgweather.xml",
            '''<weather reset="0" enable="1">
              <overcast><current actual="0.4" time="120" duration="600" /><limits min="0" max="1" /><timelimits min="60" max="600" /><changelimits min="0" max="1" /></overcast>
              <fog><current actual="0.1" time="120" duration="600" /><limits min="0" max="1" /><timelimits min="60" max="600" /><changelimits min="0" max="1" /></fog>
              <rain><current actual="0.0" time="120" duration="600" /><limits min="0" max="1" /><timelimits min="60" max="600" /><changelimits min="0" max="1" /><thresholds min="0.6" max="1" end="60" /></rain>
              <windMagnitude><current actual="4" time="120" duration="600" /><limits min="0" max="12" /><timelimits min="60" max="600" /><changelimits min="0" max="4" /></windMagnitude>
              <windDirection><current actual="0" time="120" duration="600" /><limits min="-3.14" max="3.14" /><timelimits min="60" max="600" /><changelimits min="-1" max="1" /></windDirection>
              <snowfall><current actual="0" time="0" duration="600" /><limits min="0" max="0" /><timelimits min="60" max="600" /><changelimits min="0" max="0" /><thresholds min="1" max="1" end="60" /></snowfall>
              <storm density="0.2" threshold="0.8" timeout="120" />
            </weather>''',
        )

        self.assertTrue(ok, message)
        ok, message = validate_dayz_upload_text(
            "/dayzxb_missions/dayzOffline.chernarusplus/cfgweather.xml",
            '<weather reset="0" enable="1" />',
        )
        self.assertFalse(ok)
        self.assertIn("no weather section", message)

    def test_standard_support_files_have_their_real_roots(self):
        cases = {
            "cfgplayerspawnpoints.xml": '<playerspawnpoints><fresh /></playerspawnpoints>',
            "cfgignorelist.xml": '<ignore><type name="Bandage" /></ignore>',
            "cfglimitsdefinition.xml": '<lists><categories /></lists>',
            "cfglimitsdefinitionuser.xml": '<user_lists><usageflags /></user_lists>',
            "cfgrandompresets.xml": '<randompresets><cargo name="starter" chance="1" /></randompresets>',
            "cfgundergroundtriggers.json": '{"Triggers": []}',
        }
        for target_path, text in cases.items():
            with self.subTest(target_path=target_path):
                valid, message = validate_dayz_upload_text(target_path, text)
                self.assertTrue(valid, message)

    def test_vanilla_reference_files_load_for_all_supported_maps(self):
        bot.dayz_reference_cache.clear()

        for map_key in ("chernarus", "livonia", "sakhal"):
            reference = bot.load_dayz_reference(map_key)
            with self.subTest(map=map_key):
                self.assertTrue(reference["available"])
                self.assertGreater(len(reference["types"]), 1000)
                self.assertGreater(len(reference["zombies"]), 10)
                self.assertGreater(len(reference["animals"]), 1)

    def test_sakhal_reference_uses_sakhal_folder(self):
        self.assertTrue(
            bot.dayz_reference_path("sakhal", "db", "types.xml").endswith(
                os.path.join("dayzOffline.sakhal", "db", "types.xml")
            )
        )
        self.assertEqual(bot.normalize_dayz_reference_map_key("dayzOffline.sakhal"), "sakhal")

    def test_nonexistent_fixed_vanilla_filenames_are_not_registered(self):
        self.assertIsNone(dayz_file_spec_for_path("/mission/cfgareaeffects.xml"))
        self.assertIsNone(dayz_file_spec_for_path("/mission/cfgplayerspawn.json"))
        self.assertIsNotNone(dayz_file_spec_for_path("/mission/cfgEffectArea.json"))
        self.assertIsNotNone(dayz_file_spec_for_path("/mission/custom/MySpawnGear.json"))

    def test_extracted_vanilla_reference_shapes_validate(self):
        relative_paths = (
            "db/events.xml",
            "cfgeventspawns.xml",
            "cfgeventgroups.xml",
            "mapgroupproto.xml",
            "cfgspawnabletypes.xml",
            "mapclusterproto.xml",
            "mapgroupcluster.xml",
            "mapgroupcluster01.xml",
            "mapgroupcluster02.xml",
            "mapgroupcluster03.xml",
            "mapgroupcluster04.xml",
            "mapgroupdirt.xml",
            "db/types.xml",
            "db/globals.xml",
            "db/economy.xml",
            "cfgeconomycore.xml",
            "cfgenvironment.xml",
            "env/zombie_territories.xml",
            "env/fox_territories.xml",
            "env/hare_territories.xml",
            "env/hen_territories.xml",
            "cfggameplay.json",
            "cfgeffectarea.json",
            "cfgplayerspawnpoints.xml",
            "cfgignorelist.xml",
            "cfglimitsdefinition.xml",
            "cfglimitsdefinitionuser.xml",
            "cfgrandompresets.xml",
            "cfgundergroundtriggers.json",
        )

        for folder in ("dayzOffline.chernarusplus", "dayzOffline.enoch", "dayzOffline.sakhal"):
            for relative_path in relative_paths:
                path = os.path.join(REFERENCE_ROOT, folder, *relative_path.split("/"))
                if not os.path.exists(path):
                    continue
                with self.subTest(folder=folder, file=relative_path):
                    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                        text = handle.read()
                    ok, message = validate_dayz_upload_text(f"/mission/{relative_path}", text)
                    self.assertTrue(ok, message)

    def test_every_bundled_vanilla_xml_and_json_reference_validates(self):
        checked = 0
        for folder in ("dayzOffline.chernarusplus", "dayzOffline.enoch", "dayzOffline.sakhal"):
            mission_root = os.path.join(REFERENCE_ROOT, folder)
            for current_root, _directories, filenames in os.walk(mission_root):
                for filename in filenames:
                    if not filename.lower().endswith((".xml", ".json")):
                        continue
                    reference_path = os.path.join(current_root, filename)
                    relative_path = os.path.relpath(reference_path, mission_root).replace(os.sep, "/")
                    with self.subTest(folder=folder, file=relative_path):
                        with open(reference_path, "r", encoding="utf-8", errors="ignore") as handle:
                            content = handle.read()
                        ok, message = validate_dayz_upload_text(f"/mission/{relative_path}", content)
                        self.assertTrue(ok, message)
                    checked += 1

        self.assertGreater(checked, 100)

    def test_backup_suffix_keeps_original_filename_identity(self):
        self.assertEqual(
            dayz_filename_for_path("/mission/cfgeventspawns.xml.wanderingbot-backup-latest"),
            "cfgeventspawns.xml",
        )

    def test_live_required_child_guard_blocks_minimal_events_xml(self):
        ok, message = validate_dayz_upload_text("/mission/db/events.xml", "<events></events>")

        self.assertFalse(ok)
        self.assertIn("no <event>", message)

    def test_backup_xml_allows_minimal_root_for_restore_safety(self):
        ok, message = validate_dayz_upload_text(
            "/mission/db/events.xml.wanderingbot-backup-latest",
            "<events></events>",
        )

        self.assertTrue(ok)
        self.assertEqual("", message)

    def test_named_record_guard_blocks_events_xml_record_loss(self):
        existing = '<events><event name="AmbientHen" /><event name="VehicleTruck01" /></events>'
        upload = '<events><event name="VehicleTruck01" /></events>'

        ok, message = validate_named_xml_upload_preserves_existing(
            "/mission/db/events.xml",
            existing,
            upload,
        )

        self.assertFalse(ok)
        self.assertIn("AmbientHen", message)

    def test_named_record_guard_blocks_types_xml_record_loss(self):
        existing = '<types><type name="AKM" /><type name="M4A1" /></types>'
        upload = '<types><type name="M4A1" /></types>'

        ok, message = validate_named_xml_upload_preserves_existing(
            "/mission/db/types.xml",
            existing,
            upload,
        )

        self.assertFalse(ok)
        self.assertIn("AKM", message)

    def test_named_record_guard_blocks_empty_named_file_replacement(self):
        ok, message = validate_named_xml_upload_preserves_existing(
            "/mission/db/events.xml",
            '<events><event name="AmbientHen" /><event name="VehicleTruck01" /></events>',
            "<events></events>",
        )

        self.assertFalse(ok)
        self.assertIn("AmbientHen", message)

    def test_territory_guard_blocks_loss_of_unmarked_owner_zones(self):
        existing = (
            '<territory-type><territory color="1291845632">'
            '<zone name="OwnerCity" x="1" z="2" r="80" dmin="2" dmax="4" smin="0" smax="0" />'
            '<!-- Wandering Bot: managed zombie territory zone BotEvent -->'
            '<zone name="BotEvent" x="3" z="4" r="50" dmin="1" dmax="2" smin="0" smax="0" />'
            '</territory></territory-type>'
        )
        upload = (
            '<territory-type><territory color="1291845632">'
            '<!-- Wandering Bot: managed zombie territory zone AnotherBotEvent -->'
            '<zone name="AnotherBotEvent" x="5" z="6" r="50" dmin="1" dmax="2" smin="0" smax="0" />'
            '</territory></territory-type>'
        )

        ok, message = validate_territory_xml_upload_preserves_unmanaged_content(
            "/mission/env/zombie_territories.xml",
            existing,
            upload,
        )

        self.assertFalse(ok)
        self.assertIn("unmarked live territory", message)

    def test_xml_guard_blocks_populated_environment_being_replaced_by_empty_root(self):
        ok, message = validate_xml_upload_not_effectively_empty(
            "/mission/cfgenvironment.xml",
            '<env><territories><file path="env/zombie_territories.xml" /></territories></env>',
            "<env />",
        )

        self.assertFalse(ok)
        self.assertIn("empty root", message)

    def test_shrink_guard_blocks_zero_byte_live_file_replacement(self):
        existing = "<events>" + "".join(f'<event name="Event{i}" />' for i in range(300)) + "</events>"

        ok, message = validate_upload_not_dangerously_shrunken(
            "/mission/db/events.xml",
            existing,
            "",
        )

        self.assertFalse(ok)
        self.assertIn("0 bytes", message)

    def test_shrink_guard_blocks_tiny_types_xml_replacement(self):
        existing = "<types>" + "".join(f'<type name="Item{i}" />' for i in range(500)) + "</types>"
        upload = '<types><type name="Item1" /></types>'

        ok, message = validate_upload_not_dangerously_shrunken(
            "/mission/db/types.xml",
            existing,
            upload,
        )

        self.assertFalse(ok)
        self.assertIn("destructive", message)

    def test_custom_territory_file_requires_territory_type_root(self):
        ok, message = validate_dayz_upload_text(
            "/dayzxb_missions/dayzOffline.enoch/env/wanderingbot_animal_bear_territories.xml",
            "<env></env>",
        )

        self.assertFalse(ok)
        self.assertIn("expected <territory-type> root", message)

    def test_known_dayz_json_must_parse_and_use_expected_root_type(self):
        ok, message = validate_dayz_upload_text("/mission/cfggameplay.json", "{\"version\": 123}")

        self.assertTrue(ok)
        self.assertEqual("", message)

        ok, message = validate_dayz_upload_text("/mission/cfggameplay.json", "[1, 2, 3]")

        self.assertFalse(ok)
        self.assertIn("expected JSON root object", message)

    def test_unknown_json_uploads_are_still_syntax_checked(self):
        ok, message = validate_dayz_upload_text("/mission/custom/WanderingBotObjects.json", "[")

        self.assertFalse(ok)
        self.assertIn("invalid JSON", message)

    def test_custom_json_paths_are_limited_to_safe_mission_folders(self):
        self.assertEqual("custom/MyBase.json", dayz_custom_json_path("./custom/MyBase.json"))
        self.assertEqual("pra/NoLogoutArea.json", dayz_custom_json_path("pra/NoLogoutArea.json"))
        self.assertEqual("", dayz_custom_json_path("../custom/MyBase.json"))
        self.assertEqual("", dayz_custom_json_path("custom/../MyBase.json"))
        self.assertEqual("", dayz_custom_json_path("custom/MyBase.xml"))

        spec = dayz_file_spec_for_path("/mission/custom/MyBase.json")
        self.assertIsNotNone(spec)
        self.assertEqual("custom/*.json", spec.filename)

    def test_recognised_custom_json_schemas_validate_without_guessing_mods(self):
        cases = {
            "custom/StarterGear.json": (
                '{"name": "Starter", "spawnWeight": 1, "characterTypes": ["SurvivorM_Mirek"], '
                '"attachmentSlotItemSets": [], "discreteUnsortedItemSets": []}',
                "spawning_gear",
            ),
            "pra/NoLogoutArea.json": (
                '{"areaName": "NoLogoutArea", "PRABoxes": [[[27, 5.2, 11], [108, 0, 0], [2570, 15.22, 5963.8]]], '
                '"safePositions3D": [[2575.12, 15.25, 5954.31]]}',
                "restricted_area",
            ),
            "custom/MyEffectArea.json": (
                '{"Areas": [{"AreaName": "Test", "Type": "GeyserArea", "TriggerType": "GeyserTrigger", "Data": {'
                '"Pos": [100, 5, 200], "Radius": 2}}]}',
                "effect_area",
            ),
            "custom/MyUnderground.json": (
                '{"Triggers": [{"Position": [1, 2, 3], "Orientation": [0, 0, 0], '
                '"Size": [10, 5, 10], "EyeAccommodation": 0.2, "Breadcrumbs": '
                '[{"Position": [2, 2, 3], "EyeAccommodation": 0.5}]}]}',
                "underground",
            ),
        }
        for target_path, (text, schema) in cases.items():
            with self.subTest(target_path=target_path):
                ok, message = validate_dayz_upload_text(f"/mission/{target_path}", text)
                self.assertTrue(ok, message)
                self.assertEqual(schema, dayz_json_schema_name(json.loads(text)))

        ok, message = validate_dayz_upload_text("/mission/custom/UnknownModFile.json", '{"madeUpModSetting": true}')
        self.assertFalse(ok)
        self.assertIn("recognised", message)

    def test_custom_geometry_json_rejects_structurally_valid_but_semantically_incomplete_records(self):
        cases = {
            "pra/MissingName.json": (
                '{"PRABoxes": [[[10, 5, 10], [0, 0, 0], [100, 5, 100]]], "safePositions3D": [[110, 5, 110]]}',
                "areaName",
            ),
            "custom/IncompleteEffect.json": (
                '{"Areas": [{"AreaName": "Test", "Type": "GeyserArea", "Data": {"Pos": [100, 5, 200], "Radius": 2}}]}',
                "TriggerType",
            ),
            "custom/IncompleteUnderground.json": (
                '{"Triggers": [{"Position": [1, 2, 3], "EyeAccommodation": 0.2, "Breadcrumbs": []}]}',
                "Orientation",
            ),
            "custom/IncompleteBreadcrumb.json": (
                '{"Triggers": [{"Position": [1, 2, 3], "Orientation": [0, 0, 0], "Size": [10, 5, 10], '
                '"EyeAccommodation": 0.2, "Breadcrumbs": [{"Position": [2, 2, 3]}]}]}',
                "EyeAccommodation",
            ),
        }
        for target_path, (content, expected) in cases.items():
            with self.subTest(target_path=target_path):
                ok, message = validate_dayz_upload_text(target_path, content)
                self.assertFalse(ok)
                self.assertIn(expected, message)

    def test_spawn_gear_validator_enforces_official_nested_schema(self):
        valid = {
            "name": "QA Survivor",
            "spawnWeight": 1,
            "characterTypes": ["SurvivorM_Mirek"],
            "attachmentSlotItemSets": [{
                "slotName": "shoulderL",
                "discreteItemSets": [{
                    "itemType": "M4A1",
                    "spawnWeight": 1,
                    "attributes": {"healthMin": 1.0, "healthMax": 1.0},
                    "quickBarSlot": 1,
                    "complexChildrenTypes": [{
                        "itemType": "Mag_STANAG_30Rnd",
                        "attributes": {"quantityMin": 1.0, "quantityMax": 1.0},
                        "quickBarSlot": -1,
                    }],
                }],
            }],
            "discreteUnsortedItemSets": [{
                "name": "Cargo",
                "spawnWeight": 1,
                "simpleChildrenUseDefaultAttributes": False,
                "simpleChildrenTypes": ["BandageDressing"],
            }],
        }
        ok, message = validate_dayz_upload_text("custom/QA.json", json.dumps(valid))
        self.assertTrue(ok, message)

        mutations = (
            (lambda payload: payload.update(spawnWeight=0), "at least 1"),
            (lambda payload: payload["attachmentSlotItemSets"][0].update(discreteItemSets=[]), "non-empty array"),
            (lambda payload: payload["attachmentSlotItemSets"][0]["discreteItemSets"][0]["attributes"].update(healthMin=1.1), "between 0 and 1"),
            (lambda payload: payload["attachmentSlotItemSets"][0]["discreteItemSets"][0]["complexChildrenTypes"][0].pop("itemType"), "itemType"),
            (lambda payload: payload["attachmentSlotItemSets"][0]["discreteItemSets"][0].update(quickBarSlot=-2), "-1 or greater"),
            (lambda payload: payload["discreteUnsortedItemSets"][0].update(simpleChildrenTypes=[123]), "class-name strings"),
        )
        for mutate, expected in mutations:
            payload = json.loads(json.dumps(valid))
            mutate(payload)
            with self.subTest(expected=expected):
                ok, message = validate_dayz_upload_text("custom/QA.json", json.dumps(payload))
                self.assertFalse(ok)
                self.assertIn(expected, message)

        ok, message = validate_dayz_upload_text(
            "custom/FakeGear.json", '{"name":"Fake","discreteItemSets":[]}'
        )
        self.assertFalse(ok)
        self.assertIn("recognised", message)

    def test_cfggameplay_references_and_compact_weather_format_are_validated(self):
        gameplay = """{
          "PlayerData": {"spawnGearPresetFiles": ["./custom/StarterGear.json"]},
          "WorldsData": {
            "objectSpawnersArr": ["./custom/MyBase.json"],
            "playerRestrictedAreaFiles": ["./pra/NoLogoutArea.json"]
          }
        }"""
        ok, message = validate_dayz_upload_text("/mission/cfggameplay.json", gameplay)
        self.assertTrue(ok, message)

        compact_weather = """<weather reset="false" enable="true">
          <rain><limits><min>0</min><max>1</max></limits></rain>
          <wind maxspeed="0" />
        </weather>"""
        ok, message = validate_dayz_upload_text("/mission/cfgweather.xml", compact_weather)
        self.assertTrue(ok, message)

        knowledge = dayz_agent_file_knowledge("custom/StarterGear.json")
        self.assertIn("spawning gear", knowledge["known_schemas"])
        gameplay_knowledge = dayz_agent_file_knowledge("cfggameplay.json")
        self.assertIn("playerRestrictedAreaFiles", " ".join(gameplay_knowledge["dependencies"]))
        prototype_knowledge = dayz_agent_file_knowledge("mapgroupproto.xml")
        self.assertIn("mapgrouppos.xml", " ".join(prototype_knowledge["dependencies"]))
        self.assertIn("DayZ:Diag_Menu", " ".join(prototype_knowledge["official_sources"]))
        territory_knowledge = dayz_agent_file_knowledge("env/fox_territories.xml")
        self.assertIn("Ambient_Spawner", " ".join(territory_knowledge["official_sources"]))

        ignore = dayz_agent_file_knowledge("cfgignorelist.xml")
        ignore_knowledge = " ".join(
            [str(ignore.get("purpose") or ""), str(ignore.get("safety") or ""), *map(str, ignore.get("dependencies", []))]
        ).lower()
        self.assertIn("not saved", ignore_knowledge)
        self.assertIn("does not make", ignore_knowledge)

        economy_core = dayz_agent_file_knowledge("cfgeconomycore.xml")
        economy_core_knowledge = " ".join(
            [str(economy_core.get("safety") or ""), str(economy_core.get("variants") or ""), *map(str, economy_core.get("dependencies", []))]
        )
        self.assertIn('<ce folder="foldername">', economy_core_knowledge)
        self.assertIn('<file name="my_changes_to_types.xml" type="types" />', economy_core_knowledge)
        self.assertIn("non-conflicting", economy_core_knowledge)

        spawnable = dayz_agent_file_knowledge("cfgspawnabletypes.xml")
        spawnable_knowledge = " ".join(
            [str(spawnable.get("safety") or ""), str(spawnable.get("variants") or ""), *map(str, spawnable.get("dependencies", []))]
        )
        self.assertIn("FlashGrenade", spawnable_knowledge)
        self.assertIn("Grenade_ChemGas", spawnable_knowledge)
        self.assertIn("retain its existing", spawnable_knowledge)
        self.assertIn("every occurrence", spawnable_knowledge)
        self.assertIn("outer cargo/attachments chance", spawnable_knowledge)
        self.assertIn("not teach that multiple item children", spawnable_knowledge)

        types_knowledge = dayz_agent_file_knowledge("types.xml")
        types_safety = str(types_knowledge.get("safety") or "")
        self.assertIn("Removing all tier values", types_safety)
        self.assertIn("deloot", types_safety)

        limits_knowledge = dayz_agent_file_knowledge("cfglimitsdefinition.xml")
        limits_safety = str(limits_knowledge.get("safety") or "")
        self.assertIn("Never remove all vanilla definitions", limits_safety)
        self.assertIn("explicitly approve", limits_safety)

        event_knowledge = dayz_agent_file_knowledge("events.xml")
        event_text = " ".join(
            [str(event_knowledge.get("safety") or ""), str(event_knowledge.get("variants") or ""), *map(str, event_knowledge.get("dependencies", []))]
        )
        self.assertIn("Land_Wreck_C130J", event_text)
        self.assertIn("matching mapgroupproto.xml", event_text)
        self.assertIn("ExplosionTest", event_text)
        self.assertIn("severe server load", event_text)

    def test_general_daynight_and_central_economy_knowledge_is_available(self):
        general = dayz_agent_general_knowledge()
        daynight = " ".join(
            [
                str(general["daynight_duration_converter"].get("scope") or ""),
                *map(str, general["daynight_duration_converter"].get("examples", [])),
                str(general["daynight_duration_converter"].get("conversion") or ""),
                str(general["daynight_duration_converter"].get("server_config_distinction") or ""),
            ]
        )
        self.assertIn("/daynight day:2 night:0.50", daynight)
        self.assertIn("30 minute night", daynight)
        self.assertIn("serverTimeAcceleration", daynight)
        self.assertIn("not raw DayZ acceleration multipliers", daynight)

        tiers = " ".join(map(str, general["loot_tiers"].get("rules", [])))
        self.assertIn("Chernarus uses four", tiers)
        self.assertIn("Livonia uses three", tiers)
        self.assertIn("Sakhal", tiers)

        # Callers receive an isolated copy and cannot mutate global prompt knowledge.
        general["loot_tiers"]["rules"].append("unsafe mutation")
        self.assertNotIn(
            "unsafe mutation",
            dayz_agent_general_knowledge()["loot_tiers"]["rules"],
        )

        types_knowledge = str(dayz_agent_file_knowledge("types.xml").get("variants") or "")
        self.assertIn("quantmin/quantmax", types_knowledge)
        self.assertIn("count_in_hoarder", types_knowledge)

        events_knowledge = str(dayz_agent_file_knowledge("events.xml").get("variants") or "")
        self.assertIn("saferadius", events_knowledge)
        self.assertIn("lootmin/lootmax", events_knowledge)

        globals_knowledge = str(dayz_agent_file_knowledge("globals.xml").get("variants") or "")
        self.assertIn("LootProxyPlacement", globals_knowledge)

        economy_knowledge = str(dayz_agent_file_knowledge("economy.xml").get("variants") or "")
        self.assertIn("init controls", economy_knowledge)
        self.assertIn("save controls", economy_knowledge)

        economy_core_knowledge = str(dayz_agent_file_knowledge("cfgeconomycore.xml").get("variants") or "")
        self.assertIn("backup_period", economy_core_knowledge)

    def test_cfggameplay_references_reject_unsafe_paths(self):
        unsafe_paths = [
            "../custom/escape.json",
            "./custom/../escape.json",
            "/tmp/escape.json",
            "C:/temp/escape.json",
            "./custom/not-a-json.txt",
        ]
        for path in unsafe_paths:
            gameplay = json.dumps({"WorldsData": {"objectSpawnersArr": [path]}})
            ok, message = validate_dayz_upload_text("/mission/cfggameplay.json", gameplay)
            self.assertFalse(ok, path)
            self.assertIn("mission-relative", message)

    def test_special_numeric_values_are_rejected(self):
        invalid_weather = '<weather reset="0" enable="1"><rain><limits min="NaN" max="1" /></rain></weather>'
        ok, message = validate_dayz_upload_text("/mission/cfgweather.xml", invalid_weather)
        self.assertFalse(ok)
        self.assertIn("finite", message)

        invalid_spawns = '<eventposdef><event name="QA"><pos x="1" z="2" a="NaN" /></event></eventposdef>'
        ok, message = validate_dayz_upload_text("/mission/cfgeventspawns.xml", invalid_spawns)
        self.assertFalse(ok)
        self.assertIn("finite", message)

        invalid_messages = (
            "<messages><message><delay>0</delay><repeat>0</repeat><deadline>0</deadline>"
            "<onconnect>2</onconnect><shutdown>0</shutdown><text>QA</text></message></messages>"
        )
        ok, message = validate_dayz_upload_text("/mission/db/messages.xml", invalid_messages)
        self.assertFalse(ok)
        self.assertIn("0 or 1", message)

    def test_init_script_and_named_objectspawner_file_are_recognised(self):
        init_spec = dayz_file_spec_for_path("/mission/init.c")
        self.assertIsNotNone(init_spec)
        self.assertEqual("script", init_spec.kind)

        ok, message = validate_dayz_upload_text("/mission/init.c", "void main() {}")
        self.assertTrue(ok, message)

        ok, message = validate_dayz_upload_text(
            "/mission/custom/objectspawner.json",
            '{"Objects": [{"name": "Land_Wreck_Car3", "pos": [7500, 0, 7500], "ypr": [0, 0, 0]}]}',
        )
        self.assertTrue(ok, message)

        ok, message = validate_dayz_upload_text("/mission/custom/objectspawner.json", '{"Objects": [{}]}')
        self.assertFalse(ok)
        self.assertIn("missing `name`", message)

    def test_custom_cfggameplay_shape_with_spawners_and_spawn_gear_is_valid(self):
        text = """{
          "version": 129,
          "GeneralData": {"disableBaseDamage": false, "disableContainerDamage": false},
          "PlayerData": {"spawnGearPresetFiles": ["./custom/PoliceLoadoutCherno.json"]},
          "WorldsData": {"objectSpawnersArr": ["./custom/BuilderShed.json", "./custom/LIVONIAREVAMP.json"]},
          "MapData": {"displayPlayerPosition": true}
        }"""

        ok, message = validate_dayz_upload_text("/mission/cfggameplay.json", text)

        self.assertTrue(ok, message)

    def test_cfggameplay_rejects_known_stale_containerbase_spawner_ref(self):
        text = """{
          "version": 129,
          "WorldsData": {"objectSpawnersArr": ["./custom/newcontainerbase.json"]}
        }"""

        ok, message = validate_dayz_upload_text("/mission/cfggameplay.json", text)

        self.assertFalse(ok)
        self.assertIn("newcontainerbase.json", message)

    def test_cfggameplay_update_removes_known_stale_containerbase_spawner_ref(self):
        text = """{
          "version": 129,
          "WorldsData": {"objectSpawnersArr": ["./custom/newcontainerbase.json"]}
        }"""

        updated, changed = bot.update_cfggameplay_object_spawner(text, bot.CONSOLE_OBJECT_SPAWNER_REF)
        payload = json.loads(updated)
        spawners = payload["WorldsData"]["objectSpawnersArr"]

        self.assertTrue(changed)
        self.assertNotIn("./custom/newcontainerbase.json", spawners)
        self.assertIn(bot.CONSOLE_OBJECT_SPAWNER_REF, spawners)

    def test_custom_messages_xml_with_comments_and_multiline_text_is_valid(self):
        text = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<messages>
  <message>
    <!-- Message #1 -->
    <delay>1</delay>
    <repeat>30</repeat>
    <onconnect>1</onconnect>
    <text>Welcome to Wandering Around Livo ++LOOT++REVAMPED.</text>
  </message>
  <message>
    <!-- Message #2 -->
    <delay>3</delay>
    <repeat>30</repeat>
    <onconnect>1</onconnect>
    <text>30 MINUTES GRACE TILL TEMP BAN UNLESS LINKED THROUGH DC
https://discord.gg/U2sfF55rSD</text>
  </message>
</messages>"""

        ok, message = validate_dayz_upload_text("/mission/db/messages.xml", text)

        self.assertTrue(ok, message)

    def test_custom_object_spawner_base_json_shape_is_valid(self):
        text = """{
          "Objects": [
            {
              "name": "HuntingBag_Hannah",
              "pos": [3288.39404296875, 174.9205780029297, 8387.43359375],
              "ypr": [-91.20313262939453, -2.0e-13, 1.8e-13],
              "scale": 0.9999843239784241,
              "enableCEPersistency": 0,
              "customString": ""
            },
            {
              "name": "StaticObj_Misc_Barbedwire",
              "pos": [3338.25634765625, 176.16000366210938, 8439.736328125],
              "ypr": [-77.753662109375, -0.1811303049325943, -1.1038624048233033]
            }
          ]
        }"""

        ok, message = validate_dayz_upload_text("/mission/custom/CranesBaseLIVO.json", text)

        self.assertTrue(ok, message)

    def test_custom_object_spawner_rejects_bad_position(self):
        text = """{"Objects": [{"name": "StaticObj_Misc_Barbedwire", "pos": [1, 2]}]}"""

        ok, message = validate_dayz_upload_text("/mission/custom/CranesBaseLIVO.json", text)

        self.assertFalse(ok)
        self.assertIn("pos must be an array of 3 numbers", message)

    def test_custom_object_spawner_rejects_crash_prone_weapon_classes(self):
        text = """{"Objects": [{"name": "Shockpistol_Black", "pos": [1, 2, 3]}]}"""

        ok, message = validate_dayz_upload_text("/mission/custom/CranesBaseLIVO.json", text)

        self.assertFalse(ok)
        self.assertIn("unsafe weapon class", message)

    def test_static_airdrop_scene_keeps_object_spawner_and_effect_area_workflows_separate(self):
        object_spawner = json.dumps({
            "Objects": [
                {
                    "name": "Land_Roadblock_WoodenCrate",
                    "pos": [2016.79, 229.58, 9816.60],
                    "ypr": [0.0, 0.0, 0.0],
                }
            ]
        })
        gameplay = json.dumps({"WorldsData": {"objectSpawnersArr": ["custom/AD18.json"]}})
        effect_area = json.dumps({
            "Areas": [
                {
                    "AreaName": "AirdropSmoke",
                    "Type": "ContaminatedArea_Static",
                    "TriggerType": "EffectTrigger",
                    "Data": {"Pos": [2016.79, 229.58, 9816.60], "Radius": 0},
                }
            ]
        })

        self.assertEqual((True, ""), validate_dayz_upload_text("/mission/custom/AD18.json", object_spawner))
        self.assertEqual((True, ""), validate_dayz_upload_text("/mission/cfggameplay.json", gameplay))
        self.assertEqual((True, ""), validate_dayz_upload_text("/mission/cfgEffectArea.json", effect_area))
        invalid, message = validate_dayz_upload_text("/mission/custom/AD18.json", "f" + object_spawner)
        self.assertFalse(invalid)
        self.assertIn("invalid JSON", message)

        plan = dayz_dependency_plan_for_request(
            "Create a static airdrop crate staging scene using ObjectSpawner and link it through cfgGameplay.",
            "custom/AD18.json",
        )
        paths = {item["path"]: item for item in plan["files"]}
        self.assertEqual("object_spawner", plan["workflow"])
        self.assertEqual("changed", paths["custom/AD18.json"]["action"])
        self.assertEqual("changed", paths["cfggameplay.json"]["action"])
        self.assertEqual("preserved", paths["mapgrouppos.xml"]["action"])
        self.assertIn("dynamic repeatable CE airdrop", dayz_agent_file_knowledge("objectspawner.json")["variants"])
        self.assertIn("do not add cfgEffectArea.json to objectSpawnersArr", dayz_agent_file_knowledge("cfgEffectArea.json")["dependencies"][1])

    def test_live_style_custom_types_and_events_roots_are_valid(self):
        types_text = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<types>
  <type name="ACOGOptic">
    <nominal>12</nominal>
    <lifetime>14400</lifetime>
    <restock>1800</restock>
    <min>24</min>
    <quantmin>-1</quantmin>
    <quantmax>-1</quantmax>
    <cost>100</cost>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="weapons"/>
    <usage name="Military"/>
  </type>
</types>"""
        events_text = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
  <event name="AmbientFox">
    <nominal>0</nominal>
    <min>0</min>
    <max>30</max>
    <lifetime>33</lifetime>
    <restock>25</restock>
    <saferadius>0</saferadius>
    <distanceradius>80</distanceradius>
    <cleanupradius>120</cleanupradius>
    <flags deletable="0" init_random="0" remove_damaged="0" />
    <position>fixed</position>
    <limit>mixed</limit>
    <active>1</active>
    <children>
      <child lootmax="5" lootmin="0" max="0" min="0" type="Animal_VulpesVulpes" />
    </children>
  </event>
</events>"""

        self.assertEqual((True, ""), validate_dayz_upload_text("/mission/db/types.xml", types_text))
        self.assertEqual((True, ""), validate_dayz_upload_text("/mission/db/events.xml", events_text))

    def test_unknown_xml_uploads_are_still_syntax_checked(self):
        ok, message = validate_dayz_upload_text("/mission/custom/custom_event.xml", "<root>")

        self.assertFalse(ok)
        self.assertIn("invalid XML", message)

    def test_bot_wrapper_uses_the_shared_upload_validator(self):
        bad_json = "{"

        self.assertEqual(
            bot.validate_protected_dayz_xml_upload("/mission/cfgEffectArea.json", bad_json),
            validate_dayz_upload_text("/mission/cfgEffectArea.json", bad_json),
        )

    def test_protected_json_compare_accepts_equivalent_structure(self):
        ok, message = bot.verify_protected_dayz_xml_content_matches(
            "cfggameplay.json",
            "/mission/cfggameplay.json",
            "{\"WorldsData\": {\"objectSpawnersArr\": []}, \"version\": 123}",
            "{\n  \"version\": 123,\n  \"WorldsData\": {\"objectSpawnersArr\": []}\n}",
        )

        self.assertTrue(ok)
        self.assertIn("matched JSON structure", message)


if __name__ == "__main__":
    unittest.main()
