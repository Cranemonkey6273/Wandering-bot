from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dashboard  # noqa: E402


EVENTS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticWanderingBot_test"><nominal>1</nominal></event>
</events>
"""


class DashboardProtectedUploadTests(unittest.TestCase):
    def setUp(self):
        self.original_reader = dashboard.CUSTOM_PROTECTED_FILE_READER
        self.original_writer = dashboard.CUSTOM_PROTECTED_FILE_WRITER

    def tearDown(self):
        dashboard.CUSTOM_PROTECTED_FILE_READER = self.original_reader
        dashboard.CUSTOM_PROTECTED_FILE_WRITER = self.original_writer

    def test_dashboard_refuses_protected_live_write_without_shared_transaction_writer(self):
        dashboard.CUSTOM_PROTECTED_FILE_WRITER = None

        ok, message = dashboard.dashboard_upload_text_file_to_nitrado(
            {},
            "/mission/db/events.xml",
            EVENTS_XML,
        )

        self.assertFalse(ok)
        self.assertIn("shared staged transaction writer is unavailable", message)
        self.assertIn("will not use its direct API overwrite route", message)

    def test_dashboard_delegates_protected_live_write_to_shared_transaction_writer(self):
        calls = []

        def writer(config, target_path, text_content):
            calls.append((config, target_path, text_content))
            return True, "shared staged writer completed"

        dashboard.CUSTOM_PROTECTED_FILE_WRITER = writer

        ok, message = dashboard.dashboard_upload_text_file_to_nitrado(
            {"service_id": "test"},
            "/mission/db/events.xml",
            EVENTS_XML,
        )

        self.assertTrue(ok)
        self.assertEqual("shared staged writer completed", message)
        self.assertEqual(1, len(calls))
        self.assertEqual("/mission/db/events.xml", calls[0][1])

    def test_dashboard_protected_read_uses_shared_verified_reader(self):
        calls = []

        def reader(config, target_path):
            calls.append((config, target_path))
            return True, "shared read", EVENTS_XML

        dashboard.CUSTOM_PROTECTED_FILE_READER = reader

        ok, message, content = dashboard.dashboard_download_text_file_from_nitrado(
            {"service_id": "test"},
            "/mission/db/events.xml",
        )

        self.assertTrue(ok)
        self.assertEqual("shared read", message)
        self.assertEqual(EVENTS_XML, content)
        self.assertEqual(1, len(calls))

    def test_dashboard_final_verify_rejects_valid_but_different_remote_content(self):
        changed = EVENTS_XML.replace("<nominal>1</nominal>", "<nominal>2</nominal>")
        dashboard.CUSTOM_PROTECTED_FILE_READER = lambda *_args: (True, "downloaded", changed)

        ok, message = dashboard.dashboard_verify_protected_dayz_xml_upload(
            {},
            "events.xml",
            "/mission/db/events.xml",
            EVENTS_XML,
        )

        self.assertFalse(ok)
        self.assertIn("did not exactly match the staged transaction", message)


if __name__ == "__main__":
    unittest.main()
