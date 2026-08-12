from __future__ import annotations

import unittest

import dashboard
from ui_localization import (
    CORE_APP_UI_TRANSLATIONS,
    PUBLIC_HOME_UI_TRANSLATIONS,
    SUPPORTED_UI_LANGUAGES,
    UI_TRANSLATIONS,
    ui_localization_javascript,
)


class UiLocalizationAndAppLaunchTests(unittest.TestCase):
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
