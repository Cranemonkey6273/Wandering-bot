from __future__ import annotations

import unittest

import dashboard
from ui_localization import SUPPORTED_UI_LANGUAGES, UI_TRANSLATIONS, ui_localization_javascript


class UiLocalizationAndAppLaunchTests(unittest.TestCase):
    def test_interface_localization_supports_five_languages(self):
        self.assertEqual({"en", "de", "fr", "es", "pl"}, set(SUPPORTED_UI_LANGUAGES))
        for language in ("de", "fr", "es", "pl"):
            self.assertIn("Save", UI_TRANSLATIONS[language])
            self.assertIn("Wandering Bot is now live on Google Play", UI_TRANSLATIONS[language])

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

    def test_localization_assets_are_injected_into_html_only(self):
        with dashboard.APP.test_client() as client:
            app_response = client.get("/app")
            script_response = client.get("/ui-localization.js")
            css_response = client.get("/ui-localization.css")

        self.assertEqual(200, app_response.status_code)
        app_html = app_response.get_data(as_text=True)
        self.assertIn('/ui-localization.css?v=1', app_html)
        self.assertIn('/ui-localization.js?v=1', app_html)
        self.assertIn("Wandering Bot is now live on Google Play", app_html)
        self.assertEqual(200, script_response.status_code)
        self.assertIn("application/javascript", script_response.content_type)
        self.assertNotIn('/ui-localization.js?v=1', script_response.get_data(as_text=True))
        self.assertEqual(200, css_response.status_code)
        self.assertIn("text/css", css_response.content_type)

    def test_google_play_launch_is_present_across_public_dashboard_and_app_templates(self):
        for template in (
            dashboard.PUBLIC_LANDING_TEMPLATE,
            dashboard.PAGE_TEMPLATE,
            dashboard.APP_WELCOME_TEMPLATE,
            dashboard.APP_DASHBOARD_TEMPLATE,
        ):
            self.assertIn("Wandering Bot is now live on Google Play", template)
            self.assertIn("android_play_store_url", template)

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
