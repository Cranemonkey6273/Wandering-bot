import unittest

from discord_setup_localization import (
    SETUP_SUPPORTED_LANGUAGES,
    SETUP_TEXT,
    setup_choice_text,
    setup_interaction_language,
    setup_language_code,
    setup_text,
)


class FakeInteraction:
    def __init__(self, locale=None, guild_locale=None):
        self.locale = locale
        self.guild_locale = guild_locale


class SetupLocalizationTests(unittest.TestCase):
    def test_supported_discord_locales_use_their_primary_language(self):
        cases = {
            "de": "de",
            "de-DE": "de",
            "fr": "fr",
            "fr-FR": "fr",
            "es-ES": "es",
            "pl": "pl",
            "en-US": "en",
            "en-GB": "en",
        }
        for locale, expected in cases.items():
            with self.subTest(locale=locale):
                self.assertEqual(setup_language_code(locale), expected)

    def test_unsupported_locale_safely_falls_back_to_english(self):
        self.assertEqual(setup_language_code("it-IT"), "en")
        self.assertEqual(setup_language_code(None), "en")
        self.assertEqual(setup_text("it-IT", "cancel"), "Cancel")

    def test_interaction_locale_wins_and_guild_locale_is_fallback(self):
        self.assertEqual(setup_interaction_language(FakeInteraction("de", "fr")), "de")
        self.assertEqual(setup_interaction_language(FakeInteraction(None, "pl")), "pl")

    def test_every_language_has_every_interface_phrase(self):
        english_keys = set(SETUP_TEXT["en"])
        self.assertEqual(set(SETUP_TEXT), SETUP_SUPPORTED_LANGUAGES)
        for language in SETUP_SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                self.assertEqual(set(SETUP_TEXT[language]), english_keys)
                self.assertTrue(all(str(value).strip() for value in SETUP_TEXT[language].values()))

    def test_each_non_english_language_translates_visible_controls(self):
        for language in ("de", "fr", "es", "pl"):
            with self.subTest(language=language):
                self.assertNotEqual(setup_text(language, "cancel"), setup_text("en", "cancel"))
                self.assertNotEqual(setup_text(language, "step_1"), setup_text("en", "step_1"))
                self.assertNotEqual(setup_text(language, "complete_desc"), setup_text("en", "complete_desc"))

    def test_technical_identifiers_are_not_translated(self):
        for language in SETUP_SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                self.assertIn("DayZXB", setup_text(language, "platform_xbox_desc"))
                self.assertIn("BEServer_x64.cfg", setup_text(language, "rcon_port_placeholder"))
                self.assertEqual(setup_text(language, "custom_channels_placeholder"), "killfeed, online, radar")

    def test_choice_helper_localizes_copy_but_keeps_internal_value_external(self):
        label, description = setup_choice_text(
            "de-DE", "platform", "pc", "PC", "DayZPC/MP missions",
        )
        self.assertEqual(label, "PC")
        self.assertIn("DayZPC/MP", description)

    def test_discord_component_text_stays_within_platform_limits(self):
        modal_title_keys = ("credentials_title", "advanced_title")
        input_label_keys = (
            "token_label", "service_label", "nitrado_user_label", "ftp_user_label",
            "ftp_password_label", "ftp_host_label", "rcon_host_label", "rcon_port_label",
            "rcon_password_label", "custom_channels_label",
        )
        placeholder_keys = (
            "token_placeholder", "service_placeholder", "nitrado_user_placeholder",
            "ftp_user_placeholder", "ftp_password_placeholder", "already_saved",
            "ftp_host_placeholder", "rcon_host_placeholder", "rcon_port_placeholder",
            "rcon_password_placeholder", "custom_channels_placeholder",
        )
        button_keys = (
            "cancel", "back", "continue", "credentials_button", "advanced_pc",
            "advanced_console", "review_button", "confirm",
        )
        for language in SETUP_SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                self.assertTrue(all(len(setup_text(language, key)) <= 45 for key in modal_title_keys))
                self.assertTrue(all(len(setup_text(language, key)) <= 45 for key in input_label_keys))
                self.assertTrue(all(len(setup_text(language, key)) <= 100 for key in placeholder_keys))
                self.assertTrue(all(len(setup_text(language, key)) <= 80 for key in button_keys))


if __name__ == "__main__":
    unittest.main()
