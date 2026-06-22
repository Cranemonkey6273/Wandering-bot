from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _bot_loader import import_bot_module  # noqa: E402
from dayz_file_intelligence import dayz_filename_for_path, dayz_file_spec_for_path, dayz_xml_root_for_path, validate_dayz_upload_text  # noqa: E402

bot = import_bot_module()


REFERENCE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dayz_reference"))


class DayZFileIntelligenceTests(unittest.TestCase):
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
            "db/types.xml",
            "db/globals.xml",
            "db/economy.xml",
            "cfgeconomycore.xml",
            "cfgenvironment.xml",
            "env/zombie_territories.xml",
            "cfgareaeffects.xml",
            "cfggameplay.json",
            "cfgeffectarea.json",
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
