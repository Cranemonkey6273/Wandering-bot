from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _bot_loader import import_bot_module  # noqa: E402
from dayz_file_intelligence import dayz_filename_for_path, dayz_xml_root_for_path, validate_dayz_upload_text  # noqa: E402

bot = import_bot_module()


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
