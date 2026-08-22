from __future__ import annotations

import unittest
import json
from pathlib import Path
from unittest.mock import patch

import dashboard
from ui_localization import (
    CORE_APP_UI_TRANSLATIONS,
    PUBLIC_HOME_UI_TRANSLATIONS,
    SUPPORTED_UI_LANGUAGES,
    UI_TRANSLATIONS,
    ui_localization_javascript,
)


class UiLocalizationAndAppLaunchTests(unittest.TestCase):
    def test_authenticated_dashboard_translation_catalog_has_language_parity(self):
        payload = json.loads(
            (Path(__file__).resolve().parents[1] / "data" / "dashboard_ui_translations.json").read_text(
                encoding="utf-8"
            )
        )
        expected_languages = {"de", "fr", "es", "pl"}
        self.assertEqual(expected_languages, set(payload))
        expected_phrases = set(payload["de"])
        self.assertGreaterEqual(len(expected_phrases), 70)
        for language in expected_languages:
            self.assertEqual(expected_phrases, set(payload[language]), language)
            for english, translated in payload[language].items():
                self.assertTrue(english.strip())
                self.assertTrue(str(translated).strip(), f"{language}: {english}")
                self.assertEqual(translated, UI_TRANSLATIONS[language][english])
        for required in (
            "Admin Control Panel",
            "Live Event Manager",
            "Where Do I Go?",
            "Wandering Bot AI",
            "DayZ File Workbench",
            "What do you need help with?",
            "AI Sandbox",
            "Common Tasks",
            "Shop / Money",
            "Edit types.xml",
        ):
            self.assertIn(required, expected_phrases)

    def test_interface_localization_supports_five_languages(self):
        self.assertEqual({"en", "de", "fr", "es", "pl"}, set(SUPPORTED_UI_LANGUAGES))
        for language in ("de", "fr", "es", "pl"):
            self.assertIn("Save", UI_TRANSLATIONS[language])
            self.assertIn("Wandering Bot is now live on Google Play", UI_TRANSLATIONS[language])

    def test_core_mobile_and_onboarding_copy_is_complete_in_every_language(self):
        expected_phrases = set(CORE_APP_UI_TRANSLATIONS["de"])
        self.assertGreaterEqual(len(expected_phrases), 20)
        for language in ("de", "fr", "es", "pl"):
            self.assertEqual(expected_phrases, set(CORE_APP_UI_TRANSLATIONS[language]))
            for english in expected_phrases:
                self.assertIn(english, UI_TRANSLATIONS[language])
                self.assertNotEqual(english, UI_TRANSLATIONS[language][english])

    def test_localizer_is_offline_and_protects_dayz_technical_surfaces(self):
        script = ui_localization_javascript()

        self.assertIn("wanderingUiLanguage", script)
        self.assertIn("MutationObserver", script)
        self.assertIn("textarea", script)
        self.assertIn("code,pre", script)
        self.assertIn(".xml-editor", script)
        self.assertIn(".json-editor", script)
        self.assertIn("data-no-translate", script)
        self.assertIn("cfggameplay", script.lower())
        self.assertIn("if (result) return", script)
        self.assertLess(script.index("if (result) return"), script.index("if (isTechnicalText(key))"))
        self.assertNotIn("fetch(", script)
        self.assertNotIn("translate.googleapis", script)

    def test_public_homepage_has_full_core_translation_copy(self):
        required = {
            "Add Wandering Bot to your DayZ server",
            "Owner support is built in",
            "DayZ Android app",
            "DayZ kill feed and ADM feeds",
            "Airdrops, animals and hordes",
            "Server dashboard",
            "Restarts and vehicle resets",
            "Nitrado and Discord automation",
            "Automatic Discord translation",
            "Choose your Discord server, approve the requested permissions, then let the bot create or repair its channel layout.",
            "Enter platform, map, Nitrado token, service ID, FTP username, and FTP password. These are used for your server only.",
            "Enable dashboard login for trusted admins, then manage live events, XML tools, shop, economy, zones, and moderation from the web panel.",
        }
        for language in ("de", "fr", "es", "pl"):
            self.assertTrue(required.issubset(PUBLIC_HOME_UI_TRANSLATIONS[language]))
            for english in required:
                self.assertNotEqual(english, PUBLIC_HOME_UI_TRANSLATIONS[language][english])

    def test_public_feed_and_pricing_sections_are_translated(self):
        required = {
            "Live Feed Previews",
            "See how Wandering Bot posts into Discord",
            "Let your community speak its own language",
            "Pricing",
            "Pick the dashboard access that fits your server",
        }
        for language in ("de", "fr", "es", "pl"):
            for english in required:
                self.assertIn(english, UI_TRANSLATIONS[language])
                self.assertNotEqual(english, UI_TRANSLATIONS[language][english])

    def test_mobile_entry_page_has_no_known_english_fallbacks(self):
        required = {
            "Browse free Crafting & Survival library",
            "View DayZ loot tier maps",
            "Choose the Discord server you administer and approve the requested permissions.",
            "Have the Nitrado service ID and API token, plus the FTP host, username and password for the same DayZ service. Choose the correct platform and map.",
            "Save the dashboard ID and one-time password from the private setup reply, then enter both credentials below.",
            "Join the support Discord",
            "Forgotten password?",
        }
        for language in ("de", "fr", "es", "pl"):
            for english in required:
                self.assertIn(english, UI_TRANSLATIONS[language])
                self.assertNotEqual(english, UI_TRANSLATIONS[language][english])

    def test_localization_assets_are_injected_into_html_only(self):
        with dashboard.APP.test_client() as client:
            app_response = client.get("/app")
            script_response = client.get("/ui-localization.js")
            css_response = client.get("/ui-localization.css")

        self.assertEqual(200, app_response.status_code)
        app_html = app_response.get_data(as_text=True)
        self.assertIn('/ui-localization.css?v=2', app_html)
        self.assertIn('/ui-localization.js?v=2', app_html)
        self.assertNotIn("Wandering Bot is now live on Google Play", app_html)
        self.assertEqual(200, script_response.status_code)
        self.assertIn("application/javascript", script_response.content_type)
        self.assertNotIn('/ui-localization.js?v=2', script_response.get_data(as_text=True))
        self.assertEqual(200, css_response.status_code)
        self.assertIn("text/css", css_response.content_type)

    def test_google_play_launch_is_public_but_does_not_advertise_app_inside_itself(self):
        for template in (
            dashboard.PUBLIC_LANDING_TEMPLATE,
            dashboard.PAGE_TEMPLATE,
        ):
            self.assertIn("Wandering Bot is now live on Google Play", template)
            self.assertIn("android_play_store_url", template)
        for template in (dashboard.APP_WELCOME_TEMPLATE, dashboard.APP_DASHBOARD_TEMPLATE):
            self.assertNotIn("Wandering Bot is now live on Google Play", template)
            self.assertNotIn("Get it on Google Play", template)

    def test_dashboard_map_atmosphere_assets_are_served_for_all_supported_maps(self):
        """The command-centre backdrop must not silently fall back to a flat theme."""
        with dashboard.APP.test_client() as client:
            for map_key in ("chernarus", "livonia", "sakhal"):
                response = client.get(f"/dashboard-atmosphere/{map_key}")
                try:
                    self.assertEqual(200, response.status_code, map_key)
                    self.assertIn("image/png", response.content_type, map_key)
                    self.assertGreater(len(response.data), 50_000, map_key)
                finally:
                    response.close()

        self.assertIn("/dashboard-atmosphere/{{ server.map_key }}", dashboard.PAGE_TEMPLATE)
        self.assertIn('document.body.dataset.section === "reviews"', dashboard.PAGE_TEMPLATE)

    def test_command_dashboard_uses_the_server_led_control_centre_layout(self):
        """Keep the approved command-centre shell from regressing to the old card grid."""
        for marker in (
            "Wandering Bot · Command Centre",
            "command-hero-meta",
            "Server health",
            "Survivors online",
            "Next restart",
            "command-summary-grid",
            "Recent players",
            "Server tools",
            "command-logo-watermark { display: none;",
        ):
            self.assertIn(marker, dashboard.PAGE_TEMPLATE)

    def test_public_file_validator_is_independent_from_the_app(self):
        """The public validator must not send visitors into the signed-in app."""
        with dashboard.APP.test_client() as client:
            response = client.get("/validate")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("Free file validator", html)
        self.assertIn("validator-steps", html)
        self.assertIn("Wandering Bot home", html)
        self.assertIn('href="/"', html)
        self.assertIn("DayZ file guide", html)
        self.assertNotIn("App home", html)
        self.assertNotIn('href="/app"', html)

    def test_onboarding_save_keeps_unavailable_saved_roles_and_channels(self):
        state = {
            "guild-onboarding-qa": {
                "channels": {"admin_logs": "100"},
                "member_onboarding": {
                    "enabled": True,
                    "choice_channel_id": "900",
                    "choice_message_id": "901",
                    "choice_cherno_role_id": "800",
                    "rules_role_id": "801",
                },
            }
        }

        with (
            patch.object(dashboard, "current_auth", return_value={"kind": "owner"}),
            patch.object(dashboard, "load_store", return_value=state),
            patch.object(dashboard, "save_store"),
            patch.object(dashboard, "sync_runtime_store"),
            patch.object(dashboard, "discord_guild_roles", return_value=[{"id": "different-live-role", "assignable": True}]),
            patch.object(dashboard, "public_channels", return_value=[]),
        ):
            with dashboard.APP.test_request_context(
                "/api/admin/member-onboarding",
                method="POST",
                json={"guild_id": "guild-onboarding-qa", "enabled": True},
            ):
                response = dashboard.api_member_onboarding()

        self.assertEqual(200, response.status_code)
        saved = state["guild-onboarding-qa"]["member_onboarding"]
        self.assertEqual("900", saved["choice_channel_id"])
        self.assertEqual("901", saved["choice_message_id"])
        self.assertEqual("800", saved["choice_cherno_role_id"])
        self.assertEqual("801", saved["rules_role_id"])

    def test_onboarding_form_marks_unavailable_saved_selections_for_preservation(self):
        template = dashboard.PAGE_TEMPLATE

        self.assertIn('data-onboarding-saved-value="{{ onboarding.choice_channel_value }}"', template)
        self.assertIn('data-onboarding-saved-value="{{ onboarding.choice_cherno_role_id }}"', template)
        self.assertIn("preserveUnavailableOnboardingSelections()", template)
        self.assertIn("retainEmptyValues", template)
        self.assertIn("Set up the member journey in this order", template)
        self.assertIn("Rules &amp; link access", template)
        self.assertIn("Choice roles and welcomes", template)
        self.assertIn("Member messages", template)

    def test_onboarding_save_allows_an_intentional_blank_role_selection(self):
        state = {
            "guild-onboarding-clear": {
                "member_onboarding": {"choice_cherno_role_id": "800"},
            }
        }

        with (
            patch.object(dashboard, "current_auth", return_value={"kind": "owner"}),
            patch.object(dashboard, "load_store", return_value=state),
            patch.object(dashboard, "save_store"),
            patch.object(dashboard, "sync_runtime_store"),
            patch.object(dashboard, "discord_guild_roles", return_value=[]),
            patch.object(dashboard, "public_channels", return_value=[]),
        ):
            with dashboard.APP.test_request_context(
                "/api/admin/member-onboarding",
                method="POST",
                json={"guild_id": "guild-onboarding-clear", "choice_cherno_role_id": ""},
            ):
                response = dashboard.api_member_onboarding()

        self.assertEqual(200, response.status_code)
        self.assertEqual("", state["guild-onboarding-clear"]["member_onboarding"]["choice_cherno_role_id"])

    def test_live_feed_and_event_workspace_labels_are_unambiguous(self):
        self.assertEqual("ADM feed inbox", dashboard.COMMAND_SECTION_META["live-feeds"]["title"])
        self.assertIn("Choose dashboard feeds", dashboard.PAGE_TEMPLATE)
        self.assertIn("Event deployments", dashboard.PAGE_TEMPLATE)
        self.assertIn("event-table-shell", dashboard.PAGE_TEMPLATE)

    def test_dayz_app_has_a_public_search_page_and_google_play_schema(self):
        page = dashboard.PUBLIC_SEO_PAGES["dayz-server-app"]

        self.assertEqual("/dayz-server-app", page["path"])
        self.assertIn("DayZ Server App", page["title"])
        self.assertIn("DayZ app", page["keywords"])
        self.assertIn("DayZ app", dashboard.PUBLIC_SEO_PAGES["home"]["keywords"])
        self.assertIn("Android app live on Google Play", dashboard.PUBLIC_LANDING_TEMPLATE)
        self.assertNotIn("Android + iPhone App — Coming Soon", dashboard.PUBLIC_LANDING_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
