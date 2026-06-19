"""End-to-end test that exercises the bot's CE generator and feeds the
resulting XML bundle into ``tools/validate_ce_xml.py``.

This is the regression net that proves the airdrop / vehicle / horde generator
emits a bundle that the cross-file validator considers consistent. If a future
change re-introduces the empty-children or pos-y bug, this test fails.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()
from tools.validate_ce_xml import validate_bundle  # noqa: E402


def _emit_bundle(events):
    """Run the bot's CE generators end-to-end into in-memory roots."""
    events_root = ET.Element("events")
    spawns_root = ET.Element("eventposdef")
    eventgroups_root = ET.Element("eventgroupdef")
    mapgroupproto_root = ET.Element("prototype")
    cfgspawnabletypes_root = ET.Element("spawnabletypes")

    records = []
    for event in events:
        event_records, _ = bot.console_ce_records_for_event(event)
        records.extend(event_records)

    definition_records = bot.merge_console_ce_definition_records([
        record for record in records if not record.get("use_existing_definition")
    ])
    for record in definition_records:
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record.get("event_child_type") or record["class_name"],
            record["count"],
            record["lifetime"],
            restock=record.get("restock", 0),
            use_eventgroup=bool(record.get("use_eventgroup")),
            limit_type=record.get("limit_type") or "child",
            child_lootmin=record.get("child_lootmin", 0),
            child_lootmax=record.get("child_lootmax", 0),
            nominal=record.get("nominal"),
            min_count=record.get("min_count"),
            max_count=record.get("max_count"),
            saferadius=record.get("saferadius", 0),
            distanceradius=record.get("distanceradius", 0),
            cleanupradius=record.get("cleanupradius", 100),
            child_records=record.get("child_records"),
            empty_children=bool(record.get("empty_event_children")),
        )
    for record in records:
        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            y=record.get("y"),
            count=record["count"],
            radius=record.get("radius") or 45,
            group_name=record["name"] if record.get("use_eventgroup") else "",
        )

    for record in records:
        if not record.get("use_eventgroup"):
            continue
        bot.add_console_ce_event_group(
            eventgroups_root,
            record["name"],
            record["class_name"],
            lootmin=record.get("child_lootmin", 40) or 40,
            lootmax=record.get("child_lootmax", 80) or 80,
            child_records=record.get("eventgroup_children"),
        )
        proto_classes = [
            (child.get("type") or "").strip()
            for child in record.get("eventgroup_children", []) or []
        ]
        for proto in dict.fromkeys(proto_classes):
            if proto:
                bot.add_mapgroupproto_loot_group(mapgroupproto_root, proto)

    return events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root


def _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root):
    os.makedirs(os.path.join(tmpdir, "db"), exist_ok=True)
    ET.ElementTree(events_root).write(os.path.join(tmpdir, "db", "events.xml"), encoding="utf-8", xml_declaration=True)
    ET.ElementTree(spawns_root).write(os.path.join(tmpdir, "cfgeventspawns.xml"), encoding="utf-8", xml_declaration=True)
    ET.ElementTree(eventgroups_root).write(os.path.join(tmpdir, "cfgeventgroups.xml"), encoding="utf-8", xml_declaration=True)
    ET.ElementTree(mapgroupproto_root).write(os.path.join(tmpdir, "mapgroupproto.xml"), encoding="utf-8", xml_declaration=True)
    ET.ElementTree(cfgspawnabletypes_root).write(os.path.join(tmpdir, "cfgspawnabletypes.xml"), encoding="utf-8", xml_declaration=True)


def _base_event(event_id, event_type, class_name, **overrides):
    event = {
        "id": event_id,
        "event_type": event_type,
        "class_name": class_name,
        "x": 5000,
        "z": 5000,
        "y": 0,
        "radius": 70,
        "native_ce_revision": 2,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    event.update(overrides)
    return event


class GeneratorBundleValidationTests(unittest.TestCase):
    def test_airdrop_vehicle_horde_bundle_is_consistent(self):
        events = [
            _base_event(29, "airdrop", "WoodenCrate"),
            _base_event(31, "vehicle_spawn", "Hatchback_02"),
            _base_event(32, "airdrop", "WoodenCrate", visual_marker=True, scene_type="helicopter_crash"),
            _base_event(
                33,
                "zombie_horde",
                "ZmbM_HeavyIndustryWorker",
                preset="heavymilitaryzombie",
            ),
        ]
        bundle = _emit_bundle(events)
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, *bundle)
            report = validate_bundle(tmpdir)
            if report.errors:
                self.fail("Validator reported errors:\n" + report.render())

    def test_validator_rejects_pos_with_y_attribute(self):
        events = [_base_event(29, "airdrop", "WoodenCrate")]
        events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root = _emit_bundle(events)
        # Inject a regression: add y to a <pos>
        spawns_root.find("event/pos").set("y", "0")
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            self.assertTrue(any("includes y=" in err for err in report.errors))

    def test_validator_rejects_non_empty_children_with_group_pos(self):
        events = [_base_event(29, "airdrop", "WoodenCrate")]
        events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root = _emit_bundle(events)
        # Inject a regression: re-add a <child> to events.xml
        event_node = events_root.find("event")
        children = event_node.find("children")
        ET.SubElement(children, "child", {"type": "WoodenCrate", "max": "1", "min": "1", "lootmin": "0", "lootmax": "0"})
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            self.assertTrue(any("has <children> entries AND cfgeventspawns" in err for err in report.errors))

    def test_validator_rejects_missing_mapgroupproto_entry(self):
        events = [_base_event(29, "airdrop", "WoodenCrate")]
        events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root = _emit_bundle(events)
        # Strip mapgroupproto group for WoodenCrate
        for group in list(mapgroupproto_root.findall("group")):
            if (group.get("name") or "").strip() == "WoodenCrate":
                mapgroupproto_root.remove(group)
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            self.assertTrue(any("No group configured for 'WoodenCrate'" in err for err in report.errors))


if __name__ == "__main__":
    unittest.main()
