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
        self.original_verify = bot.verify_uploaded_protected_dayz_xml_text
        self.calls = []

    def tearDown(self):
        bot.upload_text_file_to_nitrado_api = self.original_api
        bot.upload_text_file_to_nitrado_ftp = self.original_ftp
        bot.verify_uploaded_protected_dayz_xml_text = self.original_verify

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

    def test_protected_xml_refuses_ftp_when_api_fails_before_write(self):
        def api_upload(*_args):
            self.calls.append("api")
            return False, "Nitrado API token or service ID is missing."

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

        self.assertFalse(ok)
        self.assertIn("Protected DayZ XML upload stopped before FTP fallback", message)
        self.assertEqual(["api"], self.calls)


if __name__ == "__main__":
    unittest.main()
