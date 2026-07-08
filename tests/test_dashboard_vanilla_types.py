from __future__ import annotations

from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_FOLDERS = {
    "chernarus": "dayzOffline.chernarusplus",
    "livonia": "dayzOffline.enoch",
    "sakhal": "dayzOffline.sakhal",
}


class DashboardVanillaTypesTests(unittest.TestCase):
    def test_factory_types_files_are_available_for_supported_maps(self):
        for map_key, folder in REFERENCE_FOLDERS.items():
            with self.subTest(map_key=map_key):
                types_path = REPO_ROOT / "dayz_reference" / folder / "db" / "types.xml"
                root = ET.fromstring(types_path.read_text(encoding="utf-8", errors="ignore"))

                self.assertEqual("types", root.tag)
                self.assertGreater(len(root.findall(".//type")), 1000)

    def test_factory_map_cards_have_html_fallback_links(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertNotRegex(source, re.compile(r"<button[^>]+data-types-load-factory"))
        self.assertNotRegex(source, re.compile(r"<button[^>]+data-types-download-factory"))
        for map_key in REFERENCE_FOLDERS:
            with self.subTest(map_key=map_key):
                self.assertIn(f"factory_map={map_key}", source)
                self.assertIn(f"/api/admin/vanilla-types/download?map={map_key}", source)
                self.assertIn(f'data-types-load-factory data-map-key="{map_key}"', source)

    def test_factory_vanilla_download_and_preload_paths_are_wired(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn("def factory_vanilla_types_payload", source)
        self.assertIn('@APP.get("/api/admin/vanilla-types/download")', source)
        self.assertIn("types_factory_preload = factory_vanilla_types_payload", source)
        self.assertIn('data-types-preload>{{ types_factory_preload|tojson }}</script>', source)

    def test_types_editor_exposes_full_xml_copy_and_view_controls(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('data-tool-copy="generated_xml">Copy XML</button>', source)
        self.assertIn('data-types-show-xml>View XML</a>', source)
        self.assertIn('id="types-xml-output" data-types-xml-panel', source)
        self.assertIn("panel.open = true", source)

    def test_duplicate_xml_sections_are_consolidated_into_workshop(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('("loot", "Types Editor")', source)
        self.assertIn('"loot-engine": "loot"', source)
        self.assertIn('"bulk-economy": "loot"', source)
        self.assertIn('"dayz-converter": "loot"', source)
        self.assertNotIn('href="/admin?section=loot-engine{{ server_qs }}">Loot Balancer</a>', source)
        self.assertNotIn('href="/admin?section=bulk-economy{{ server_qs }}">Bulk XML Edit</a>', source)
        self.assertNotIn('href="/admin?section=dayz-converter{{ server_qs }}">Map Converter</a>', source)

    def test_admin_setup_sections_are_consolidated_into_admin_center(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('"automations": "discord"', source)
        self.assertIn('"server-rules": "rules"', source)
        self.assertIn('"server-control": "control"', source)
        self.assertIn("Admin Center", source)
        self.assertIn("setup_tool == 'discord'", source)
        self.assertIn("setup_tool == 'rules'", source)
        self.assertIn("setup_tool == 'moderation'", source)
        self.assertIn("setup_tool == 'control'", source)
        self.assertNotIn('href="/admin?section=automations{{ server_qs }}">Discord Setup</a>', source)
        self.assertNotIn('href="/admin?section=server-rules{{ server_qs }}">Server Rules</a>', source)
        self.assertNotIn('href="/admin?section=moderation{{ server_qs }}">Moderation</a>', source)
        self.assertNotIn('href="/admin?section=server-control{{ server_qs }}">Server Control</a>', source)

    def test_admin_feed_routes_are_managed_from_admin_center(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('"feeds"', source)
        self.assertIn("setup_tool == 'feeds'", source)
        self.assertIn('id="feed-routes"', source)
        self.assertIn('id="custom-feeds"', source)
        self.assertIn('@APP.post("/api/admin/feed-route")', source)
        self.assertIn('@APP.post("/api/admin/custom-feed")', source)
        self.assertIn("dashboard_feed_route_groups", source)
        self.assertIn("dashboard_custom_feed_rows", source)
        self.assertIn('"rpt_admin": "Server spawns / RPT tracker"', source)
        self.assertIn('"restart_alerts", "rpt_admin"', source)

    def test_dashboard_live_feeds_page_and_settings_are_wired(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('"live-feeds"', source)
        self.assertIn('id="live-feeds"', source)
        self.assertIn('@APP.post("/api/admin/live-feed-settings")', source)
        self.assertIn("dashboard_live_feed_rows", source)
        self.assertIn("dashboard_live_feed_filter_groups", source)
        self.assertIn("dashboard_live_feed_keys", source)
        self.assertIn("server_profile_id", source)
        self.assertIn('id="dayz-profile-picker"', source)
        self.assertIn("selected_dayz_profile", source)
        self.assertIn('"dashboard_live_feeds": "dashboard_live_feeds.json"', source)

    def test_dashboard_has_plain_task_entry_points_for_setup_and_economy(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn("Shop & Economy", source)
        self.assertIn('id="setup-common-tasks"', source)
        self.assertIn('id="economy-common-tasks"', source)
        self.assertIn('action="/api/admin/server-profile"', source)
        self.assertIn('@APP.post("/api/admin/server-profile")', source)
        self.assertIn('action="/api/admin/dayz-server-profile"', source)
        self.assertIn('@APP.post("/api/admin/dayz-server-profile")', source)
        self.assertIn("server_profiles", source)
        self.assertIn("normalize_dashboard_server_mode", source)
        self.assertIn("shop_economy_section", source)

    def test_owner_removed_dashboard_restore_and_confirmation_are_wired(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn("REMOVED_GUILD_RESTORE_SECRET_KEYS", source)
        self.assertIn("OWNER_DESTRUCTIVE_GUILD_ACTIONS", source)
        self.assertIn("def restore_removed_guild_dashboard_data", source)
        self.assertIn("def removed_guild_rows", source)
        self.assertIn('action" value="restore_data"', source)
        self.assertIn("Restore Removed Dashboards", source)
        self.assertIn("Restore Dashboard Data", source)
        self.assertIn('name="confirm_name"', source)
        self.assertIn("owner_guild_action_confirmation_error", source)
        self.assertIn('"config_full": removed_guild_config_snapshot(config)', source)

    def test_moderation_guard_has_cross_channel_spam_controls(self):
        dashboard_source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")
        bot_source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn("Cross-channel spam", dashboard_source)
        self.assertIn('name="watch_cross_channel_spam"', dashboard_source)
        self.assertIn('name="cross_channel_count"', dashboard_source)
        self.assertIn('"watch_cross_channel_spam"', dashboard_source)
        self.assertIn('"cross_channel_count"', dashboard_source)
        self.assertIn('"watch_cross_channel_spam": True', bot_source)
        self.assertIn('"cross_channel_count": 3', bot_source)
        self.assertIn('"channel_id": str(getattr(message.channel, "id", "") or "")', bot_source)
        self.assertIn("cross-channel spam", bot_source)

    def test_zone_ignored_gamertags_round_trip_to_safe_zone_whitelist(self):
        dashboard_source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")
        bot_source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('name="ignored_gamertags"', dashboard_source)
        self.assertIn('setControl(form, "ignored_gamertags"', dashboard_source)
        self.assertIn('"ignored_gamertags": ignored_gamertags', dashboard_source)
        self.assertIn('"whitelist": ignored_gamertags', dashboard_source)
        self.assertIn('or zone.get("whitelist")', dashboard_source)
        self.assertIn('"ignored_gamertags": ignored_gamertags', dashboard_source)
        self.assertIn('allowlist = parse_gamertag_list(zone.get("whitelist") or []) + radar_zone_ignored_gamertags(zone)', bot_source)

    def test_reviews_page_and_dashboard_section_are_wired(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('"reviews": "reviews.json"', source)
        self.assertIn('"path": "/reviews"', source)
        self.assertIn('@APP.get("/reviews")', source)
        self.assertIn('@APP.get("/api/reviews")', source)
        self.assertIn('@APP.post("/api/reviews")', source)
        self.assertIn('active_section == "reviews"', source)
        self.assertIn('data-review-form', source)
        self.assertIn('data-review-list', source)
        self.assertIn('data-review-prompt', source)
        self.assertIn('"aggregateRating"', source)


if __name__ == "__main__":
    unittest.main()
