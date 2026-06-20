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
            remove_damaged=bool(record.get("remove_damaged")),
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
        proto_classes = [
            str(item or "").strip()
            for item in record.get("mapgroupproto_classes", []) or []
            if str(item or "").strip()
        ]
        if record.get("use_eventgroup"):
            bot.add_console_ce_event_group(
                eventgroups_root,
                record["name"],
                record["class_name"],
                lootmin=record.get("child_lootmin", 40) or 40,
                lootmax=record.get("child_lootmax", 80) or 80,
                child_records=record.get("eventgroup_children"),
            )
            if not proto_classes:
                proto_classes = [
                    (child.get("type") or "").strip()
                    for child in record.get("eventgroup_children", []) or []
                    if bot.eventgroup_child_needs_mapgroupproto(child)
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
        # Inject the old regression: keep events.xml children while also
        # routing cfgeventspawns through a group.
        event_name = events_root.find("event").get("name")
        spawns_root.find("event/pos").set("group", event_name)
        ET.SubElement(eventgroups_root, "group", {"name": event_name})
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
        # Strip mapgroupproto group for the retired-crate airdrop anchor.
        for group in list(mapgroupproto_root.findall("group")):
            if (group.get("name") or "").strip() == "Wreck_Mi8_Crashed":
                mapgroupproto_root.remove(group)
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            self.assertTrue(any("No group configured for 'Wreck_Mi8_Crashed'" in err for err in report.errors))

    def test_validator_rejects_bare_mapgroupproto_entry(self):
        events = [_base_event(29, "airdrop", "WoodenCrate")]
        events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root = _emit_bundle(events)
        events_root.find("event/children/child[@type='Wreck_Mi8_Crashed']").set("lootmax", "5")
        for group in mapgroupproto_root.findall("group"):
            if (group.get("name") or "").strip() == "Wreck_Mi8_Crashed":
                for child in list(group):
                    group.remove(child)
                group.attrib.pop("lootmax", None)
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            self.assertTrue(any("no usable loot container/point" in err for err in report.errors))

    def test_validator_rejects_mapgroupproto_container_without_floor_tag(self):
        events = [_base_event(29, "airdrop", "WoodenCrate")]
        events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root = _emit_bundle(events)
        events_root.find("event/children/child[@type='Wreck_Mi8_Crashed']").set("lootmax", "5")
        for group in mapgroupproto_root.findall("group"):
            if (group.get("name") or "").strip() == "Wreck_Mi8_Crashed":
                for tag in list(group.findall("./container/tag")):
                    group.find("container").remove(tag)
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            self.assertTrue(any("no usable loot container/point" in err for err in report.errors))

    def test_validator_rejects_secondary_only_eventgroup_children(self):
        events = [_base_event(29, "airdrop", "WoodenCrate")]
        events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root = _emit_bundle(events)
        # Inject the live RPT regression: every eventgroup child is marked as a
        # secondary scene prop, leaving DayZ with no positive child max/lootmax.
        event_name = events_root.find("event").get("name")
        events_root.find("event").find("children").clear()
        spawns_root.find("event/pos").set("group", event_name)
        group = ET.SubElement(eventgroups_root, "group", {"name": event_name})
        ET.SubElement(group, "child", {
            "type": "Wreck_Mi8_Crashed",
            "x": "0",
            "y": "0",
            "z": "0",
            "a": "0",
            "spawnsecondary": "false",
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            self.assertTrue(any("all group child max/lootmax values are 0" in err for err in report.errors))

    def test_validator_rejects_mixed_revision_bundle(self):
        events = [_base_event(29, "airdrop", "WoodenCrate", native_ce_revision=7)]
        events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root = _emit_bundle(events)
        # Simulate a partial upload/restore: events.xml has r7 while the spawn
        # file references r8, matching the mixed-revision RPT symptom.
        spawns_root.find("event").set("name", "StaticWanderingBot_29_airdrop_r8")
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            rendered = "\n".join(report.errors)
            self.assertIn("missing from cfgeventspawns.xml", rendered)
            self.assertIn("missing from events.xml", rendered)

    def test_validator_rejects_legacy_hordetrigger_orphan_spawn(self):
        events = [_base_event(33, "zombie_horde", "ZmbM_SoldierNormal", preset="military_zombie")]
        events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root = _emit_bundle(events)
        ET.SubElement(spawns_root, "event", {"name": "HordeTrigger"})
        spawns_root.find("./event[@name='HordeTrigger']").append(
            ET.Element("pos", {"x": "1", "z": "2", "a": "0"})
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_bundle(tmpdir, events_root, spawns_root, eventgroups_root, mapgroupproto_root, cfgspawnabletypes_root)
            report = validate_bundle(tmpdir)
            self.assertFalse(report.ok())
            self.assertTrue(any("HordeTrigger" in err and "missing from events.xml" in err for err in report.errors))


if __name__ == "__main__":
    unittest.main()
