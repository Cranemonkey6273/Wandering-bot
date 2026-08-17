import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from tools.generate_explosive_infected_package import transform_spawnabletypes, validate_types


class ExplosiveInfectedPackageTests(unittest.TestCase):
    def test_preserves_existing_loot_and_adds_independent_explosive_blocks(self):
        spawnable = """<?xml version="1.0" encoding="utf-8"?>
<spawnabletypes>
  <type name="FlashGrenade"><damage min="0.0" max="0.0" /></type>
  <type name="ZmbM_Test">
    <cargo preset="foodArmy" />
    <cargo chance="0.25"><item name="BandageDressing" chance="1.0" /></cargo>
    <attachments preset="hatsArmy" />
  </type>
  <type name="CivilianBelt"><attachments preset="beltsCivilian" /></type>
</spawnabletypes>"""
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.xml"
            output = Path(temp) / "output.xml"
            source.write_text(spawnable, encoding="utf-8")

            self.assertEqual(transform_spawnabletypes(source, output), 1)
            root = ET.parse(output).getroot()
            infected = root.find('./type[@name="ZmbM_Test"]')
            self.assertIsNotNone(infected)
            self.assertIsNotNone(infected.find('./cargo[@preset="foodArmy"]'))
            self.assertIsNotNone(infected.find('./cargo[@chance="0.25"]/item[@name="BandageDressing"]'))
            self.assertIsNotNone(infected.find('./attachments[@preset="hatsArmy"]'))
            self.assertIsNotNone(infected.find('./cargo[@chance="0.05"]/item[@name="FlashGrenade"]'))
            self.assertIsNotNone(infected.find('./cargo[@chance="0.05"]/item[@name="Grenade_ChemGas"]'))
            self.assertIsNotNone(root.find('./type[@name="CivilianBelt"]/attachments[@preset="beltsCivilian"]'))
            for class_name in ("FlashGrenade", "Grenade_ChemGas"):
                damage = root.find(f'./type[@name="{class_name}"]/damage')
                self.assertIsNotNone(damage)
                self.assertEqual(damage.get("min"), "1.0")
                self.assertEqual(damage.get("max"), "1.0")

    def test_types_validation_requires_single_zeroed_support_records(self):
        valid_types = """<types>
  <type name="FlashGrenade"><nominal>0</nominal><min>0</min></type>
  <type name="Grenade_ChemGas"><nominal>0</nominal><min>0</min></type>
</types>"""
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "types.xml"
            source.write_text(valid_types, encoding="utf-8")
            validate_types(source)

            source.write_text(valid_types.replace("<nominal>0</nominal>", "<nominal>1</nominal>", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nominal 0/min 0"):
                validate_types(source)


if __name__ == "__main__":
    unittest.main()
