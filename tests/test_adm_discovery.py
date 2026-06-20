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


if __name__ == "__main__":
    unittest.main()
