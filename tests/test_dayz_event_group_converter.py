from __future__ import annotations

import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import dashboard  # noqa: E402


class DayZEventGroupConverterTests(unittest.TestCase):
    def sample_editor_json(self) -> dict:
        return {
            "Objects": [
                {
                    "name": "Land_Wreck_Mi8_Crashed",
                    "pos": [100.0, 50.0, 200.0],
                    "ypr": [-45.0, 0.0, 0.0],
                },
                {
                    "name": "Land_Container_1Mo",
                    "pos": [110.0, 55.0, 180.0],
                    "ypr": [450.0, 10.0, 20.0],
                },
            ]
        }

    def test_json_to_xml_builds_three_linked_valid_snippets(self):
        result = dashboard.convert_dayz_editor_json(
            self.sample_editor_json(),
            "TestDrop",
            "Static_",
            "Injector_",
        )

        self.assertEqual("Static_TestDrop", result["event_name"])
        self.assertEqual("Injector_TestDrop", result["group_name"])
        self.assertEqual(2, result["object_count"])

        event = ET.fromstring(result["events_xml"])
        spawn = ET.fromstring(result["eventspawns_xml"])
        group = ET.fromstring(result["eventgroups_xml"])
        self.assertEqual("Static_TestDrop", event.get("name"))
        self.assertEqual("Static_TestDrop", spawn.get("name"))
        self.assertEqual("Injector_TestDrop", spawn.find("pos").get("group"))
        self.assertEqual("100", spawn.find("pos").get("x"))
        self.assertEqual("200", spawn.find("pos").get("z"))
        self.assertEqual("Injector_TestDrop", group.get("name"))

        children = group.findall("child")
        self.assertEqual(2, len(children))
        self.assertEqual("0", children[0].get("x"))
        self.assertEqual("0", children[0].get("z"))
        self.assertEqual("315", children[0].get("a"))
        self.assertEqual("0", children[0].get("deloot"))
        self.assertEqual("3", children[0].get("lootmax"))
        self.assertEqual("1", children[0].get("lootmin"))
        self.assertEqual("10", children[1].get("x"))
        self.assertEqual("-20", children[1].get("z"))
        self.assertEqual("90", children[1].get("a"))
        self.assertEqual("false", children[1].get("spawnsecondary"))
        self.assertNotIn("rpy=", result["eventgroups_xml"])
        self.assertNotIn("offset=", result["eventgroups_xml"])

    def test_legacy_editor_objects_are_supported(self):
        result = dashboard.convert_dayz_editor_json(
            {
                "EditorObjects": [
                    {
                        "Type": "Land_Wreck_Mi8_Crashed",
                        "Position": [123.5, 7.0, 456.25],
                        "Orientation": [12.0, 0.0, 0.0],
                    }
                ]
            },
            "Static_LegacyDrop",
        )
        self.assertEqual("Static_LegacyDrop", result["event_name"])
        self.assertEqual(1, result["object_count"])

    def test_xml_to_json_reconstructs_world_xz_and_yaw(self):
        forward = dashboard.convert_dayz_editor_json(
            self.sample_editor_json(),
            "TestDrop",
            "Static_",
            "Injector_",
        )
        linked_xml = "\n".join(
            [
                forward["events_xml"],
                forward["eventspawns_xml"],
                forward["eventgroups_xml"],
            ]
        )
        result = dashboard.convert_dayz_event_xml_to_json(linked_xml)
        data = json.loads(result["json_output"])

        self.assertEqual("Static_TestDrop", result["event_name"])
        self.assertEqual("Injector_TestDrop", result["group_name"])
        self.assertEqual(2, result["object_count"])
        self.assertEqual([100.0, 0.0, 200.0], data["Objects"][0]["pos"])
        self.assertEqual([315.0, 0.0, 0.0], data["Objects"][0]["ypr"])
        self.assertEqual([110.0, 0.0, 180.0], data["Objects"][1]["pos"])
        self.assertEqual([90.0, 0.0, 0.0], data["Objects"][1]["ypr"])

    def test_xml_to_json_rejects_missing_referenced_group(self):
        xml_text = """
        <event name="Static_Bad"><pos x="10" z="20" a="0" group="MissingGroup"/></event>
        <group name="DifferentGroup"><child type="Land_Wreck_Mi8_Crashed" x="0" z="0" a="0"/></group>
        """
        with self.assertRaisesRegex(ValueError, "MissingGroup"):
            dashboard.convert_dayz_event_xml_to_json(xml_text)


if __name__ == "__main__":
    unittest.main()
