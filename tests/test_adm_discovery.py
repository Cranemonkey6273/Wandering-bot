from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class AdmDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _safe_zone_config():
        return {
            "safe_zones": [
                {
                    "id": "z1",
                    "name": "Test Safe Zone",
                    "enabled": True,
                    "shape": "circle",
                    "x": 100,
                    "y": 200,
                    "radius": 50,
                    "triggers": ["kill"],
                    "action": "ban",
                }
            ]
        }

    @staticmethod
    def _live_pvp_hit_line(*, victim="Victim", attacker="Attacker", health="40", dead_marker=""):
        return (
            f'18:19:00 | Player "{victim}" {dead_marker} '
            f'(id=victim pos=<10, 20, 3>) [HP: {health}] hit by Player "{attacker}" '
            '(id=attacker pos=<100, 200, 3>) into Torso(15) for 60 damage '
            '(Bullet_9x19) with SG5-K from 12.0 meters'
        )

    async def test_safe_zone_pvp_evidence_bans_only_the_verified_attacker_and_audits_exact_line(self):
        line = self._live_pvp_hit_line()
        evidence = bot.safe_zone_pvp_evidence(line)
        self.assertEqual("verified", evidence["status"])
        self.assertEqual("Victim", evidence["victim"])
        self.assertEqual("Attacker", evidence["attacker"])
        self.assertEqual("100, 200, 3", evidence["attacker_coords"])

        class CapturedEmbed:
            def __init__(self, *args, **kwargs):
                self.title = kwargs.get("title")
                self.description = kwargs.get("description")
                self.fields = []

            def add_field(self, **kwargs):
                self.fields.append(kwargs)
                return self

        guild = type("Guild", (), {"id": 123})()
        apply_ban = AsyncMock(return_value=(True, "TEMP ban 1 day (offense #1)"))
        post_report = AsyncMock()
        with patch.object(bot.discord, "Embed", CapturedEmbed), patch.object(bot, "style_embed", side_effect=lambda embed: embed), patch.object(
            bot, "discord_guild_for_runtime_id", return_value=guild
        ), patch.object(bot, "_safe_zone_apply_ban", apply_ban), patch.object(bot, "_safe_zone_post_report", post_report):
            await bot.check_safe_zones_for_adm("123", self._safe_zone_config(), "kill", line)

        apply_ban.assert_awaited_once()
        self.assertEqual("Attacker", apply_ban.call_args.args[3])
        report_embed = post_report.call_args.args[2]
        fields = {field["name"]: field["value"] for field in report_embed.fields}
        self.assertEqual("Victim", fields["Victim"])
        self.assertEqual("Attacker", fields["Attacker"])
        self.assertEqual("HP: 40", fields["Victim HP/dead state"])
        self.assertEqual("100, 200, 3", fields["Attacker position"])
        self.assertEqual(line, fields["Exact ADM evidence"])

    async def test_safe_zone_corpse_hit_variants_never_create_an_offence(self):
        cases = (
            self._live_pvp_hit_line(health="0"),
            self._live_pvp_hit_line(health="40", dead_marker="( dEaD )"),
            self._live_pvp_hit_line(health="-0.5"),
        )
        guild = type("Guild", (), {"id": 123})()
        apply_ban = AsyncMock()
        post_report = AsyncMock()
        with patch.object(bot, "discord_guild_for_runtime_id", return_value=guild), patch.object(
            bot, "_safe_zone_apply_ban", apply_ban
        ), patch.object(bot, "_safe_zone_post_report", post_report):
            for line in cases:
                evidence = bot.safe_zone_pvp_evidence(line)
                self.assertEqual("corpse", evidence["status"])
                await bot.check_safe_zones_for_adm("123", self._safe_zone_config(), "kill", line)

        apply_ban.assert_not_awaited()
        post_report.assert_not_awaited()

    async def test_safe_zone_ambiguous_pvp_evidence_is_reviewed_not_banned(self):
        cases = (
            self._live_pvp_hit_line(victim="SamePlayer", attacker="sameplayer"),
            '18:19:00 | Player "Victim" (id=victim pos=<10, 20, 3>) [HP: 40] hit by Player "" into Torso(15)',
            '18:19:00 | Player Victim [HP: 40] hit by Player Attacker into Torso(15)',
        )
        guild = type("Guild", (), {"id": 123})()
        apply_ban = AsyncMock()
        post_report = AsyncMock()
        with patch.object(bot, "discord_guild_for_runtime_id", return_value=guild), patch.object(
            bot, "_safe_zone_apply_ban", apply_ban
        ), patch.object(bot, "_safe_zone_post_report", post_report):
            for line in cases:
                evidence = bot.safe_zone_pvp_evidence(line)
                self.assertIn(evidence["status"], {"self", "unparseable"})
                await bot.check_safe_zones_for_adm("123", self._safe_zone_config(), "kill", line)

        apply_ban.assert_not_awaited()
        self.assertEqual(len(cases), post_report.await_count)

    async def test_safe_zone_ban_passes_exact_evidence_to_nitrado_audit(self):
        line = self._live_pvp_hit_line()
        guild = type("Guild", (), {"id": 123})()
        add_ban = AsyncMock(return_value=(True, "updated"))
        with patch.object(bot, "_safe_zone_offense_inc", return_value=1), patch.object(
            bot, "add_player_to_nitrado_banlist_async", add_ban
        ), patch.object(bot, "save_guild_configs"):
            ok, _label = await bot._safe_zone_apply_ban(
                guild,
                {},
                {"id": "z1", "name": "Test Safe Zone", "ban_type": "temp", "ban_duration_minutes": 60},
                "Attacker",
                "kill",
                line,
            )

        self.assertTrue(ok)
        self.assertEqual(line, add_ban.call_args.kwargs["evidence_line"])

    async def test_ban_announcement_falls_back_to_embed_when_media_upload_fails(self):
        class Channel:
            def __init__(self):
                self.calls = []

            async def send(self, **kwargs):
                self.calls.append(kwargs)
                if "file" in kwargs:
                    raise PermissionError("Attach Files denied")

        channel = Channel()
        guild = type("Guild", (), {"get_channel": lambda _self, _channel_id: channel})()
        config = {
            "ban_announcement": {
                "enabled": True,
                "channel_id": "42",
                "media_path": "ban_announcement_media/test.mp4",
            }
        }
        with patch.object(bot, "discord_guild_for_runtime_id", return_value=guild), patch.object(
            bot, "ban_announcement_media_absolute_path", return_value="C:/fake/ban.mp4"
        ), patch.object(bot.discord, "File", return_value=object()), patch.object(
            bot, "style_embed", side_effect=lambda embed: embed
        ):
            sent = await bot.post_confirmed_game_ban_announcement(
                "123",
                config,
                gamertag="Attacker",
                ban_type="temp",
                source="safe_zone",
                minutes=60,
            )

        self.assertTrue(sent)
        self.assertEqual(2, len(channel.calls))
        self.assertIn("file", channel.calls[0])
        self.assertNotIn("file", channel.calls[1])

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

    def test_adm_rate_limit_backoff_does_not_pause_unrelated_nitrado_customers(self):
        old_backoff = dict(bot.adm_rate_limit_backoff_until)
        config_a = {"nitrado_token": "account-a-token", "nitrado_user": "ni123", "service_id": "service-a"}
        config_b = {"nitrado_token": "account-b-token", "nitrado_user": "ni456", "service_id": "service-b"}
        try:
            with patch.dict(os.environ, {"WANDERING_ADM_PROVIDER_WIDE_BACKOFF": "0"}, clear=False):
                bot.adm_rate_limit_backoff_until.clear()
                bot.set_adm_rate_limit_backoff("guild-a:cherno", config_a)

                self.assertLessEqual(bot.active_adm_rate_limit_backoff_until("guild-b:livo", config_b), time.time())
            self.assertNotIn(bot.ADM_NITRADO_PROVIDER_BACKOFF_KEY, bot.adm_rate_limit_backoff_until)
            self.assertNotIn("account-a-token", "".join(bot.adm_rate_limit_backoff_until.keys()))
        finally:
            bot.adm_rate_limit_backoff_until.clear()
            bot.adm_rate_limit_backoff_until.update(old_backoff)

    def test_adm_pacing_uses_a_shared_egress_queue_without_global_backoff(self):
        config = {"nitrado_token": "account-token", "nitrado_user": "ni123", "service_id": "service-a"}

        with patch.dict(os.environ, {"WANDERING_ADM_PROVIDER_WIDE_BACKOFF": "0"}, clear=False):
            buckets = bot._adm_nitrado_bucket_ids("guild-a", config)

        self.assertIn(bot.ADM_NITRADO_EGRESS_PACING_KEY, buckets)
        self.assertIn("service:service-a", buckets)
        self.assertNotIn(bot.ADM_NITRADO_PROVIDER_BACKOFF_KEY, buckets)

    def test_rpt_rate_limit_does_not_pause_the_adm_feed(self):
        config = {
            "nitrado_token": "rpt-token",
            "service_id": "rpt-service",
            "nitrado_user": "ni123",
        }
        old_adm_backoff = dict(bot.adm_rate_limit_backoff_until)
        old_rpt_backoff = dict(bot.rpt_rate_limit_backoff_until)

        class RateLimitedResponse:
            status_code = 429
            text = "Nitrado/Cloudflare rate limit"

        try:
            bot.adm_rate_limit_backoff_until.clear()
            bot.rpt_rate_limit_backoff_until.clear()
            with patch.object(bot, "pace_adm_nitrado_request"), patch.object(
                bot.requests, "get", return_value=RateLimitedResponse()
            ) as request_get, patch.dict(os.environ, {"WANDERING_RPT_RATE_LIMIT_BACKOFF_SECONDS": "600"}, clear=False):
                self.assertEqual([], bot.list_rpt_logs(config))

            self.assertEqual(1, request_get.call_count)
            self.assertGreater(bot.active_rpt_rate_limit_backoff_until(config), time.time())
            self.assertLessEqual(bot.active_adm_rate_limit_backoff_until("guild-a", config), time.time())
        finally:
            bot.adm_rate_limit_backoff_until.clear()
            bot.adm_rate_limit_backoff_until.update(old_adm_backoff)
            bot.rpt_rate_limit_backoff_until.clear()
            bot.rpt_rate_limit_backoff_until.update(old_rpt_backoff)

    def test_rpt_parser_recognizes_native_wandering_bot_event_class_with_coordinates(self):
        _restarts, events = bot.parse_rpt_for_events(
            "12:00:00 [CE] Event spawned StaticWanderingBot_55_airdrop at <5000, 12, 6000>"
        )

        self.assertEqual(1, len(events))
        self.assertEqual("StaticWanderingBot_55_airdrop", events[0]["type"])
        self.assertEqual(5000.0, events[0]["x"])
        self.assertEqual(6000.0, events[0]["z"])

    def test_rpt_log_search_reuses_adm_directory_and_stops_after_a_match(self):
        original_get = bot.requests.get
        calls = []

        class FakeResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "data": {
                        "entries": [{
                            "name": "DayZServer_X1_x64_2026-08-19_16-00-00.RPT",
                            "path": "/games/ni123/noftp/dayzxb/profiles/DayZServer_X1_x64_2026-08-19_16-00-00.RPT",
                            "modified_at": "2026-08-19T16:00:00+00:00",
                        }]
                    }
                }

        def fake_get(_url, headers=None, params=None, timeout=None):
            calls.append(params.get("dir"))
            return FakeResponse()

        try:
            bot.requests.get = fake_get
            logs = bot.list_rpt_logs({
                "nitrado_token": "token",
                "service_id": "service",
                "nitrado_user": "ni123",
                "server_platform": "Xbox",
                "adm_log_directory": "/games/ni123/noftp/dayzxb/profiles/",
            })
        finally:
            bot.requests.get = original_get

        self.assertEqual(1, len(logs))
        self.assertEqual(["/games/ni123/noftp/dayzxb/profiles/"], calls)

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
