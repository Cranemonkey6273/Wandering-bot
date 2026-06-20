from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class AdmDiscoveryTests(unittest.TestCase):
    def test_playstation_adm_paths_prefer_dayzps_roots(self):
        paths = bot.nitrado_adm_search_paths({
            "nitrado_user": "ni123",
            "server_platform": "PlayStation",
        })

        self.assertTrue(paths)
        self.assertIn("/games/ni123/noftp/dayzps/config/", paths[:4])
        self.assertIn("/games/ni123/noftp/dayzps/logs/", paths)
        self.assertIn("/games/ni123/noftp/dayzps/mpmissions/dayzOffline.chernarusplus/", paths)
        self.assertIn("/games/ni123/noftp/dayzxb/config/", paths)

    def test_xbox_adm_paths_keep_dayzxb_roots(self):
        paths = bot.nitrado_adm_search_paths({
            "nitrado_user": "ni123",
            "server_platform": "Xbox",
        })

        self.assertTrue(paths)
        self.assertIn("/games/ni123/noftp/dayzxb/config/", paths[:4])
        self.assertIn("/games/ni123/noftp/dayzps/config/", paths)

    def test_adm_paths_prefer_remembered_working_directory(self):
        paths = bot.nitrado_adm_search_paths({
            "nitrado_user": "ni123",
            "server_platform": "Xbox",
            "adm_log_directory": "/games/ni123/noftp/dayzxb/profiles/",
        })

        self.assertEqual("/games/ni123/noftp/dayzxb/profiles/", paths[0])

    def test_remember_adm_log_source_stores_path_and_directory(self):
        config = {}
        changed = bot.remember_adm_log_source(config, {
            "path": "/games/ni123/noftp/dayzxb/profiles/DayZServer_X1_x64_2026-06-20_20-22-59.ADM",
        })

        self.assertTrue(changed)
        self.assertEqual(
            "/games/ni123/noftp/dayzxb/profiles/DayZServer_X1_x64_2026-06-20_20-22-59.ADM",
            config["adm_last_log_path"],
        )
        self.assertEqual("/games/ni123/noftp/dayzxb/profiles/", config["adm_log_directory"])

    def test_adm_scan_failure_summary_includes_status_and_path(self):
        summary = bot.adm_scan_failure_summary([
            {
                "path": "/games/ni123/noftp/dayzps/config/",
                "status": 500,
                "error": "{\"status\":\"error\"}",
            },
            {
                "path": "/games/ni123/noftp/dayzps/logs/",
                "status": 200,
                "count": 0,
                "entries": 3,
            },
        ])

        self.assertIn("dayzps/config", summary)
        self.assertIn("500", summary)
        self.assertIn("dayzps/logs", summary)

    def test_adm_rate_limit_detection_treats_cloudflare_as_rate_limited(self):
        diagnostics = [
            {
                "path": "/games/ni123/noftp/dayzxb/",
                "status": 429,
                "error": "<!DOCTYPE html><title>Just a moment...</title>",
            }
        ]

        self.assertTrue(bot.adm_scan_diagnostics_rate_limited(diagnostics))
        message = bot.adm_rate_limited_message("search", diagnostics, 180)
        self.assertIn("rate-limited ADM search", message)
        self.assertIn("not a missing ADM file/path", message)

    def test_list_adm_logs_stops_after_cloudflare_rate_limit(self):
        original_get = bot.requests.get
        calls = []

        class FakeResponse:
            status_code = 429
            text = "<!DOCTYPE html><title>Just a moment...</title>"

        def fake_get(_url, headers=None, params=None, timeout=None):
            calls.append(params.get("dir"))
            return FakeResponse()

        try:
            bot.requests.get = fake_get
            diagnostics = []
            logs = bot.list_adm_logs(
                {
                    "nitrado_token": "token",
                    "service_id": "service",
                    "nitrado_user": "ni123",
                    "server_platform": "Xbox",
                },
                diagnostics=diagnostics,
            )
        finally:
            bot.requests.get = original_get

        self.assertEqual([], logs)
        self.assertEqual(1, len(calls))
        self.assertTrue(bot.adm_scan_diagnostics_rate_limited(diagnostics))

    def test_ping_latest_adm_log_stops_after_first_matching_directory(self):
        original_get = bot.requests.get
        calls = []

        class FakeResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "data": {
                        "entries": [
                            {
                                "name": "DayZServer_X1_x64_2026-06-20_20-22-59.ADM",
                                "path": "/games/ni123/noftp/dayzxb/profiles/DayZServer_X1_x64_2026-06-20_20-22-59.ADM",
                                "modified_at": "2026-06-20T20:23:00+00:00",
                            }
                        ]
                    }
                }

        def fake_get(_url, headers=None, params=None, timeout=None):
            calls.append(params.get("dir"))
            return FakeResponse()

        try:
            bot.requests.get = fake_get
            diagnostics = []
            latest = bot.ping_latest_adm_log(
                {
                    "nitrado_token": "token",
                    "service_id": "service",
                    "nitrado_user": "ni123",
                    "server_platform": "Xbox",
                    "adm_log_directory": "/games/ni123/noftp/dayzxb/profiles/",
                },
                diagnostics=diagnostics,
            )
        finally:
            bot.requests.get = original_get

        self.assertIsNotNone(latest)
        self.assertEqual("/games/ni123/noftp/dayzxb/profiles/", calls[0])
        self.assertEqual(1, len(calls))
        self.assertEqual(1, len(diagnostics))


if __name__ == "__main__":
    unittest.main()
