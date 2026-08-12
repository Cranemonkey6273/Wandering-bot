from __future__ import annotations

import unittest

import dashboard
from tests._bot_loader import import_bot_module


class EconomyCurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = import_bot_module()

    def test_dashboard_and_bot_offer_the_same_currency_choices(self):
        dashboard_choices = {item["value"] for item in dashboard.ECONOMY_CURRENCY_OPTIONS}
        self.assertEqual(dashboard_choices, set(self.bot.ECONOMY_CURRENCY_OPTIONS))
        self.assertLessEqual(len(dashboard_choices), 25)

    def test_common_currency_codes_normalize_consistently(self):
        expected = {
            "CAD": "canadian_dollars",
            "AUD": "australian_dollars",
            "JPY": "yen",
            "INR": "rupees",
            "PLN": "zloty",
            "CHF": "swiss_francs",
            "RUB": "rubles",
            "credits": "credits",
        }
        for raw, normalized in expected.items():
            self.assertEqual(normalized, self.bot.normalize_economy_currency(raw))
            self.assertEqual(normalized, dashboard.normalize_economy_currency(raw))

    def test_currency_formatting_uses_singular_and_plural_wording(self):
        self.assertEqual("1 Canadian dollar", dashboard.dashboard_format_currency(1, "CAD"))
        self.assertEqual("2 Canadian dollars", dashboard.dashboard_format_currency(2, "CAD"))
        self.assertEqual("1 credit", dashboard.dashboard_format_currency(1, "credits"))
        self.assertEqual("25 credits", dashboard.dashboard_format_currency(25, "credits"))
        self.assertEqual("1 yen", dashboard.dashboard_format_currency(1, "yen"))
        self.assertEqual("100 yen", dashboard.dashboard_format_currency(100, "yen"))


if __name__ == "__main__":
    unittest.main()
