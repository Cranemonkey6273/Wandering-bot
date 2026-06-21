from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class ShopCategoryTests(unittest.TestCase):
    def test_ammo_name_overrides_dayz_weapons_xml_category(self):
        self.assertEqual(bot.guess_shop_category("Ammo_9x39", "weapons"), "Ammunition")
        self.assertEqual(bot.guess_shop_category("Ammo_12gaPellets", "weapons"), "Ammunition")
        self.assertEqual(bot.guess_shop_category("Mag_AK74_30Rnd", "weapons"), "Ammunition")
        self.assertEqual(bot.guess_shop_category("CartridgeBox_9x39", "weapons"), "Ammunition")

    def test_shemag_and_hats_do_not_match_magazine_terms(self):
        self.assertEqual(bot.guess_shop_category("Shemag_Black", "ammunition"), "Clothing")
        self.assertEqual(bot.guess_shop_category("Ushanka_Black", "ammunition"), "Clothing")
        self.assertEqual(bot.guess_shop_category("BaseballCap_Blue", "ammunition"), "Clothing")

    def test_backpack_names_override_storage_xml_category(self):
        self.assertEqual(bot.guess_shop_category("AliceBag_Black", "containers"), "Backpacks")
        self.assertEqual(bot.guess_shop_category("DryBag_Red", "containers"), "Backpacks")

    def test_repair_existing_saved_categories(self):
        catalog = {
            "Ammo_9x39": {"price": 100, "category": "Weapons", "enabled": True},
            "Shemag_Black": {"price": 100, "category": "Ammunition", "enabled": True},
            "AliceBag_Black": {"price": 100, "category": "Base Storage", "enabled": True},
            "MysteryThing": {"price": 100, "category": "Special", "enabled": True},
        }

        repaired = bot.repair_shop_catalog_block_categories(catalog)

        self.assertEqual(repaired, 3)
        self.assertEqual(catalog["Ammo_9x39"]["category"], "Ammunition")
        self.assertEqual(catalog["Shemag_Black"]["category"], "Clothing")
        self.assertEqual(catalog["AliceBag_Black"]["category"], "Backpacks")
        self.assertEqual(catalog["MysteryThing"]["category"], "Special")


if __name__ == "__main__":
    unittest.main()
