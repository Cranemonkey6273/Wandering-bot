from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


SPAWNS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventposdef>
    <event name="StaticWanderingBot_test">
        <pos x="1" z="2" a="0" />
    </event>
</eventposdef>
"""


class ProtectedXmlUploadOrderTests(unittest.TestCase):
    def setUp(self):
        self.original_api = bot.upload_text_file_to_nitrado_api
        self.original_ftp = bot.upload_text_file_to_nitrado_ftp
        self.original_prechecked_ftp = bot.upload_protected_dayz_xml_to_nitrado_ftp_prechecked
        self.original_verify = bot.verify_uploaded_protected_dayz_xml_text
        self.original_verify_remote = bot.verify_remote_protected_dayz_xml
        self.calls = []

    def tearDown(self):
        bot.upload_text_file_to_nitrado_api = self.original_api
        bot.upload_text_file_to_nitrado_ftp = self.original_ftp
        bot.upload_protected_dayz_xml_to_nitrado_ftp_prechecked = self.original_prechecked_ftp
        bot.verify_uploaded_protected_dayz_xml_text = self.original_verify
        bot.verify_remote_protected_dayz_xml = self.original_verify_remote

    def test_protected_xml_uses_api_before_ftp(self):
        def api_upload(*_args):
            self.calls.append("api")
            return True, "Uploaded successfully via Nitrado API."

        def ftp_upload(*_args):
            self.calls.append("ftp")
            return True, "Uploaded successfully via FTP."

        def verify(*_args):
            self.calls.append("verify")
            return True, "verified"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.verify_uploaded_protected_dayz_xml_text = verify

        ok, message = bot.upload_text_file_to_nitrado({}, "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", SPAWNS_XML)

        self.assertTrue(ok)
        self.assertIn("Nitrado API", message)
        self.assertEqual(["api", "verify"], self.calls)

    def test_protected_xml_does_not_ftp_after_api_verification_failure(self):
        def api_upload(*_args):
            self.calls.append("api")
            return True, "Uploaded successfully via Nitrado API."

        def ftp_upload(*_args):
            self.calls.append("ftp")
            return True, "Uploaded successfully via FTP."

        def verify(*_args):
            self.calls.append("verify")
            return False, "post-upload XML was malformed"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.verify_uploaded_protected_dayz_xml_text = verify

        ok, message = bot.upload_text_file_to_nitrado({}, "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", SPAWNS_XML)

        self.assertFalse(ok)
        self.assertIn("Post-upload verification failed", message)
        self.assertEqual(["api", "verify"], self.calls)

    def test_protected_xml_uses_prechecked_ftp_when_api_fails_before_write(self):
        def api_upload(*_args):
            self.calls.append("api")
            return False, "Nitrado API token or service ID is missing."

        def prechecked_upload(*_args):
            self.calls.append("prechecked")
            return True, "Precheck upload verified before direct live write via ukln138.gamedata.io."

        def verify(*_args):
            self.calls.append("verify")
            return True, "verified"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.upload_protected_dayz_xml_to_nitrado_ftp_prechecked = prechecked_upload
        bot.verify_uploaded_protected_dayz_xml_text = verify

        ok, message = bot.upload_text_file_to_nitrado({}, "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", SPAWNS_XML)

        self.assertTrue(ok)
        self.assertIn("prechecked FTP live write was used", message)
        self.assertEqual(["api", "prechecked"], self.calls)

    def test_ce_latest_backup_can_use_ftp_without_touching_api(self):
        backup_path = "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml.wanderingbot-backup-latest"

        def api_upload(*_args):
            self.calls.append("api")
            return False, "Nitrado API token failed with status 429."

        def ftp_upload(*_args):
            self.calls.append("ftp")
            return True, "Uploaded successfully via ukln138.gamedata.io."

        def verify_remote(*_args):
            self.calls.append("verify_remote")
            return True, "backup verified"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.verify_remote_protected_dayz_xml = verify_remote

        ok, message = bot.upload_ce_latest_backup_to_nitrado({}, "cfgeventspawns.xml", backup_path, SPAWNS_XML)

        self.assertTrue(ok)
        self.assertIn("ukln138.gamedata.io", message)
        self.assertEqual(["ftp", "verify_remote"], self.calls)

    def test_xml_compare_accepts_equivalent_structure(self):
        downloaded = """<eventposdef><event name="StaticWanderingBot_test"><pos a="0" z="2" x="1" /></event></eventposdef>"""

        ok, message = bot.verify_protected_dayz_xml_content_matches(
            "cfgeventspawns.xml",
            "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
            SPAWNS_XML,
            downloaded,
        )

        self.assertTrue(ok)
        self.assertIn("matched XML structure", message)


if __name__ == "__main__":
    unittest.main()
