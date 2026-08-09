from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class AdmDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_nitrado_panel_banlist_is_comma_separated_and_case_preserving(self):
        source = "DaddyR6294,LoganArcade,Mama Justice89,Liamchomski\nLeonDaBeast9249"
        entries = bot.nitrado_banlist_entries_from_text(source)
        self.assertEqual(
            ["DaddyR6294", "LoganArcade", "Mama Justice89", "Liamchomski", "LeonDaBeast9249"],
            entries,
        )
        self.assertEqual(
            "DaddyR6294,LoganArcade,Mama Justice89,Liamchomski,LeonDaBeast9249",
            bot.serialize_nitrado_web_banlist(entries),
        )

    def test_nitrado_ban_add_refreshes_exact_adm_casing(self):
        config = {"service_id": "service-1"}
        with patch.object(bot, "fetch_nitrado_banlist", return_value=["leondabeast9249"]), patch.object(
            bot,
            "push_nitrado_banlist",
            return_value=(True, "updated"),
        ) as push:
            ok, message = bot.add_player_to_nitrado_banlist(config, "LeonDaBeast9249")

        self.assertTrue(ok)
        self.assertEqual("updated", message)
        push.assert_called_once_with(config, ["LeonDaBeast9249"])

    def test_later_shot_on_recorded_dead_body_is_not_a_second_kill(self):
        first_death = (
            '23:20:00 | Player "Jayo2323" (DEAD) '
            '(id=AB7199B4A0373BFB046D29A85DA6E3EA4CF0D123 pos=<13052.2, 14034.8, 13.2>) '
            '[HP: 0] hit by Player "OriginalKiller" '
            '(id=1111111111111111111111111111111111111111 pos=<13050.0, 14035.0, 12.7>) '
            'into Torso(15) for 55 damage (Bullet_9x19) with SG5-K from 3.0 meters'
        )
        corpse_hit = (
            '23:23:24 | Player "Jayo2323" (DEAD) '
            '(id=AB7199B4A0373BFB046D29A85DA6E3EA4CF0D123 pos=<13052.2, 14034.8, 13.2>) '
            '[HP: 0] hit by Player "x OLIEJDM x" '
            '(id=4A25401DA2F4DC7162ACEC19467D3EE809B9D3E50 pos=<13050.8, 14036.1, 12.7>) '
            'into Head(0) for 40 damage (Bullet_9x19) with SG5-K from 2.0182 meters'
        )
        first_details = bot.extract_pvp_kill_details(first_death)
        corpse_details = bot.extract_pvp_kill_details(corpse_hit)
        self.assertEqual("AB7199B4A0373BFB046D29A85DA6E3EA4CF0D123", first_details["victim_id"])
        self.assertEqual("x OLIEJDM x", corpse_details["killer"])

        previous = bot.recorded_pvp_deaths
        bot.recorded_pvp_deaths = {}
        try:
            with patch.object(bot, "save_recorded_pvp_deaths"):
                self.assertFalse(bot.is_recorded_pvp_death_body("guild-1", first_details, now_ts=1000))
                self.assertTrue(bot.remember_recorded_pvp_death("guild-1", first_details, now_ts=1000))
                self.assertTrue(bot.is_recorded_pvp_death_body("guild-1", corpse_details, now_ts=1005))

                moved_body = dict(corpse_details, victim_coords="13152.2, 14134.8, 13.2")
                self.assertFalse(bot.is_recorded_pvp_death_body("guild-1", moved_body, now_ts=1005))
        finally:
            bot.recorded_pvp_deaths = previous

    def test_dead_character_self_hit_is_not_a_pvp_kill_or_safe_zone_offense(self):
        corpse_line = (
            '21:46:53 | Player "Jayo2323" (DEAD) (id=ab7199b84a0373bfb046d29a85ad6e3ea4cf0d123 '
            'pos=<11252.6, 4273.9, 313.3>) [HP: 0] hit by Player "Jayo2323" '
            'into Head(0) for 58.0499 damage (Bullet_357) with Revolver from 1.7762 meters'
        )
        details = bot.extract_pvp_kill_details(corpse_line)
        self.assertIsNotNone(details)
        self.assertEqual("Jayo2323", details["killer"])
        self.assertEqual("Jayo2323", details["victim"])
        self.assertTrue(bot.is_stale_self_kill_of_dead_player(corpse_line, details))

        live_self_hit = corpse_line.replace("(DEAD) ", "").replace("[HP: 0]", "[HP: 25]")
        self.assertFalse(bot.is_stale_self_kill_of_dead_player(live_self_hit))

        normal_pvp = corpse_line.replace('"Jayo2323"', '"OtherPlayer"', 1)
        self.assertFalse(bot.is_stale_self_kill_of_dead_player(normal_pvp))

        victim_first_line = corpse_line.replace('Player "Jayo2323" (DEAD)', 'Player "Jayo2323" (DEAD)', 1).replace(
            'Player "Jayo2323" into', 'Player "LeonDaBeast9249" into'
        )
        self.assertEqual("LeonDaBeast9249", bot.safe_zone_event_actor_name("kill", victim_first_line))

        screenshot_line = (
            '22:33:24 | Player "LeonDaBeast9249" (DEAD) '
            '(id=3B6C5BBD08E25390B241B36191315164D864055 pos=<13016.5, 14066.4, 13.3>) '
            '[HP: 0] hit by Player "CraneMonkey6273" '
            '(id=4880C7AC4F1774224D5ADE3CFC37FDD6D59090AF pos=<13012.4, 14063.1, 13.3>) '
            'into Torso(15) for 40 damage (Bullet_9x19) with SG5-K from 5.28035 m'
        )
        screenshot_details = bot.extract_pvp_kill_details(screenshot_line)
        self.assertIsNotNone(screenshot_details)
        self.assertEqual("CraneMonkey6273", screenshot_details["killer"])
        self.assertEqual("LeonDaBeast9249", screenshot_details["victim"])
        self.assertEqual("13012.4, 14063.1, 13.3", screenshot_details["killer_coords"])
        self.assertEqual("13016.5, 14066.4, 13.3", screenshot_details["victim_coords"])
        self.assertEqual("CraneMonkey6273", bot.safe_zone_event_actor_name("kill", screenshot_line))
        self.assertEqual("13012.4, 14063.1, 13.3", bot.safe_zone_event_actor_coords("kill", screenshot_line))

    def test_suicide_fingerprint_collapses_emote_and_death_pair(self):
        event_time = datetime(2026, 7, 11, 14, 33, 42, tzinfo=timezone.utc)
        emote_line = (
            '14:33:40 | Player "CraneMonkey6273" (id=abc pos=<13452.8, 6183.1, 6.1>) '
            "performed emotesuicide"
        )
        death_line = (
            '14:33:43 | Player "CraneMonkey6273" (id=abc pos=<13452.8, 6183.1, 6.1>) '
            "committed suicide"
        )

        self.assertEqual(bot.classify_event(emote_line), "suicide")
        self.assertEqual(bot.classify_event(death_line), "suicide")
        self.assertEqual(
            bot.adm_event_fingerprint(123, "suicide", emote_line, event_time=event_time),
            bot.adm_event_fingerprint(123, "suicide", death_line, event_time=event_time),
        )

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
        self.assertIn("temporarily blocked ADM search", message)
        self.assertIn("not a missing ADM file/path", message)

    def test_adm_rate_limit_detection_treats_nitrado_12004_as_temporary_block(self):
        diagnostics = [
            {
                "path": "/games/ni123/noftp/dayzxb/config/",
                "status": 500,
                "error": '{"status":"error","message":"Oops, something is going wrong with your server right now. Our team has already been informed and is working on a solution. We ask for your patience. #ErrorCode 12004"}',
            }
        ]

        self.assertTrue(bot.adm_scan_diagnostics_rate_limited(diagnostics))
        message = bot.adm_rate_limited_message("search", diagnostics, 180)
        self.assertIn("temporarily blocked ADM search", message)
        self.assertIn("not a missing ADM file/path", message)
        self.assertIn("ErrorCode 12004", message)

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

    def test_list_adm_logs_stops_after_nitrado_12004(self):
        original_get = bot.requests.get
        calls = []

        class FakeResponse:
            status_code = 500
            text = '{"status":"error","message":"Oops, something is going wrong with your server right now. #ErrorCode 12004"}'

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

    async def test_force_refresh_respects_active_adm_rate_limit_backoff(self):
        guild_id = "adm-backoff-test"
        old_backoff = dict(bot.adm_rate_limit_backoff_until)
        try:
            bot.adm_rate_limit_backoff_until[guild_id] = time.time() + 120
            ok, message = await bot._refresh_adm_for_guild_locked(
                guild_id,
                {
                    "nitrado_token": "token",
                    "service_id": "service",
                    "nitrado_user": "ni123",
                    "ftp_user": "ftp",
                    "ftp_password": "secret",
                },
                force=True,
            )
        finally:
            bot.adm_rate_limit_backoff_until.clear()
            bot.adm_rate_limit_backoff_until.update(old_backoff)

        self.assertFalse(ok)
        self.assertIn("backoff active", message)
        self.assertIn("Force reset was accepted", message)

    def test_adm_rate_limit_backoff_is_shared_by_nitrado_token(self):
        old_backoff = dict(bot.adm_rate_limit_backoff_until)
        config_a = {"nitrado_token": "shared-token", "nitrado_user": "ni123"}
        config_b = {"nitrado_token": "shared-token", "nitrado_user": "ni123"}
        try:
            bot.adm_rate_limit_backoff_until.clear()
            bot.set_adm_rate_limit_backoff("guild-a:cherno", config_a)

            self.assertGreater(bot.active_adm_rate_limit_backoff_until("guild-b:livo", config_b), time.time())
            self.assertNotIn("shared-token", "".join(bot.adm_rate_limit_backoff_until.keys()))
        finally:
            bot.adm_rate_limit_backoff_until.clear()
            bot.adm_rate_limit_backoff_until.update(old_backoff)

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
