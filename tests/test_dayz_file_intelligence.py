from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _bot_loader import import_bot_module  # noqa: E402
from dayz_file_intelligence import dayz_agent_file_knowledge, dayz_custom_json_path, dayz_dependency_plan_for_request, dayz_file_spec_for_path, dayz_filename_for_path, dayz_json_schema_name, dayz_xml_root_for_path, validate_dayz_upload_text, validate_named_xml_upload_preserves_existing, validate_upload_not_dangerously_shrunken  # noqa: E402

bot = import_bot_module()


REFERENCE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dayz_reference"))


class DayZFileIntelligenceTests(unittest.TestCase):
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
            "cfgareaeffects.xml",
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
                '{"spawnWeight": 1, "characterTypes": ["SurvivorM_Mirek"], '
                '"attachmentSlotItemSets": [], "discreteUnsortedItemSets": []}',
                "spawning_gear",
            ),
            "pra/NoLogoutArea.json": (
                '{"areaName": "NoLogoutArea", "PRABoxes": [[[27, 5.2, 11], [108, 0, 0], [2570, 15.22, 5963.8]]], '
                '"safePositions3D": [[2575.12, 15.25, 5954.31]]}',
                "restricted_area",
            ),
            "custom/MyEffectArea.json": (
                '{"Areas": [{"AreaName": "Test", "Type": "GeyserArea", "Data": {'
                '"Pos": [100, 5, 200], "Radius": 2}}]}',
                "effect_area",
            ),
            "custom/MyUnderground.json": (
                '{"Triggers": [{"Position": [1, 2, 3], "Orientation": [0, 0, 0], '
                '"Size": [10, 5, 10], "EyeAccommodation": 0.2, "Breadcrumbs": [{"Position": [2, 2, 3]}]}]}',
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
