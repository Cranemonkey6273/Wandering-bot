"""Regression tests for the Wandering-bot DayZ native CE XML generator.

These cover the two root-cause fixes made in response to the production RPT
symptom: WanderingBot event definitions appeared in the live RPT but DayZ
never produced any spawn lines for them.

Root cause 1 ? events.xml ``<children>`` was non-empty for events that
referenced an entry in ``cfgeventgroups.xml`` through a ``<pos group="...">``
attribute in ``cfgeventspawns.xml``. Vanilla DayZ Livonia events such as
``StaticMilitaryConvoy`` keep ``<children/>`` empty in that pattern, and DayZ
silently refuses to instantiate the event when both spawn paths are populated.

Root cause 2 ? ``cfgeventspawns.xml`` ``<pos>`` entries included a ``y``
attribute. Vanilla DayZ Livonia ``cfgeventspawns.xml`` only carries ``x``,
``z`` and ``a``; the engine samples terrain height itself. Forcing ``y=0``
makes vehicles and static crates fail to spawn on Livonia terrain.
"""

from __future__ import annotations

import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


def _base_event(event_id, event_type, class_name, **overrides):
    event = {
        "id": event_id,
        "event_type": event_type,
        "class_name": class_name,
        "x": 5000,
        "y": 0,
        "z": 5000,
        "radius": 70,
        "native_ce_revision": 2,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    event.update(overrides)
    return event


class AirdropEventGroupTests(unittest.TestCase):
    """Verify the events.xml/cfgeventspawns/mapgroupproto linkage for airdrops."""

    def _build_airdrop_event_node(self, event):
        records, _warnings = bot.console_ce_records_for_event(event)
        self.assertTrue(records, "airdrop should produce at least one CE record")
        record = records[0]
        events_root = ET.Element("events")
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
            secondary=record.get("secondary", ""),
        )
        spawns_root = ET.Element("eventposdef")
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
        eventgroups_root = ET.Element("eventgroupdef")
        if record.get("use_eventgroup"):
            bot.add_console_ce_event_group(
                eventgroups_root,
                record["name"],
                record["class_name"],
                lootmin=record.get("child_lootmin", 40) or 40,
                lootmax=record.get("child_lootmax", 80) or 80,
                child_records=record.get("eventgroup_children"),
            )
        return record, events_root, spawns_root, eventgroups_root

    def test_airdrop_events_xml_uses_direct_mi8_child(self):
        """MI8 airdrops now follow the vanilla heli-crash shape: the real
        crash child lives directly in events.xml, and cfgeventspawns only
        carries the fixed x/z/a position."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, events_root, _spawns, _groups = self._build_airdrop_event_node(event)

        self.assertFalse(record.get("use_eventgroup"))
        self.assertFalse(record.get("empty_event_children"))
        self.assertEqual("StaticWanderingBot_29_airdrop", record["name"])
        self.assertNotIn("_r", record["name"])
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        children_node = event_node.find("children")
        self.assertIsNotNone(children_node, "events.xml event must still carry a <children/> element")
        child = children_node.find("child")
        self.assertIsNotNone(child)
        self.assertEqual("Wreck_Mi8_Crashed", child.get("type"))
        self.assertGreater(int(child.get("lootmax") or 0), 0)

    def test_airdrop_cfgeventspawns_pos_carries_group(self):
        """cfgeventspawns.xml <pos> must NOT contain ``y``. For direct MI8
        airdrops it also does not reference a cfgeventgroups group."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, _events, spawns_root, _groups = self._build_airdrop_event_node(event)

        spawn_event = spawns_root.find("event")
        self.assertIsNotNone(spawn_event)
        pos = spawn_event.find("pos")
        self.assertIsNotNone(pos)
        self.assertIsNone(pos.get("group"))
        for attr in ("x", "z", "a"):
            self.assertIn(attr, pos.attrib)
        self.assertNotIn(
            "y", pos.attrib,
            "cfgeventspawns.xml <pos> must not carry y ? vanilla DayZ samples "
            "terrain height itself, and forcing y=0 prevents the spawn.",
        )

    def test_airdrop_record_requests_mapgroupproto_for_crash_class(self):
        """Ground loot comes from mapgroupproto lootFloor tags on the crash
        class, not from WoodenCrate cargo."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, _events, _spawns, groups_root = self._build_airdrop_event_node(event)

        self.assertIsNone(groups_root.find("group"))
        self.assertEqual(["Wreck_Mi8_Crashed"], record.get("mapgroupproto_classes"))
        self.assertEqual("Wreck_Mi8_Crashed", record.get("event_child_type"))

    def test_helicopter_airdrop_uses_crash_and_proto_tags_not_item_children(self):
        event = _base_event(
            32,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            loot_preset="military_high",
        )
        record, events_root, _spawns, groups_root = self._build_airdrop_event_node(event)

        self.assertEqual(record["event_child_type"], "Wreck_Mi8_Crashed")
        self.assertIsNone(groups_root.find("group"))
        children = events_root.findall("event/children/child")
        types_in_event = [child.get("type") for child in children]
        self.assertIn("Wreck_Mi8_Crashed", types_in_event)
        self.assertNotIn("WoodenCrate", types_in_event)
        self.assertFalse(any(child.get("type") in bot.SCENARIO_AIRDROP_GROUND_LOOT for child in children))

    def test_airdrop_vehicle_class_is_replaced_by_static_loot_anchor(self):
        event = _base_event(
            52,
            "airdrop",
            "Sedan_02",
            visual_marker=False,
            loot_preset="vehicle_car",
        )
        records, warnings = bot.console_ce_records_for_event(event, map_key="livonia")
        self.assertEqual(1, len(records))
        record = records[0]

        self.assertEqual("Wreck_Mi8_Crashed", record["class_name"])
        self.assertEqual("Wreck_Mi8_Crashed", record["event_child_type"])
        self.assertEqual(["Wreck_Mi8_Crashed"], record.get("mapgroupproto_classes"))
        self.assertFalse(any(child.get("type") == "Sedan_02" for child in record["child_records"]))
        self.assertTrue(any("vehicle classname `Sedan_02`" in message for message in warnings))

    def test_airdrop_guards_use_vanilla_secondary_infected(self):
        event = _base_event(
            32,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            guard_class="ZmbM_SoldierNormal",
            guard_count=3,
            guard_radius=35,
        )
        records, _warnings = bot.console_ce_records_for_event(event)

        self.assertEqual(1, len(records))
        self.assertEqual("InfectedArmy", records[0].get("secondary"))
        self.assertFalse(any(
            child.get("type") == "ZmbM_SoldierNormal"
            for child in records[0]["child_records"]
        ))
        record, events_root, _spawns, _groups = self._build_airdrop_event_node(event)
        self.assertEqual("InfectedArmy", record.get("secondary"))
        self.assertEqual("InfectedArmy", events_root.findtext("event/secondary"))

    def test_direct_airdrop_with_guard_children_validates(self):
        event = _base_event(
            32,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            guard_class="ZmbM_SoldierNormal",
            guard_count=3,
        )
        record, events_root, spawns_root, _groups = self._build_airdrop_event_node(event)
        proto_root = ET.Element("prototype")
        for class_name in record.get("mapgroupproto_classes") or []:
            bot.add_mapgroupproto_loot_group(proto_root, class_name, tags=record.get("mapgroupproto_tags"))
        built = {
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": bot.xml_text_from_root(proto_root),
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))

    def test_convoy_airdrop_uses_direct_child_not_eventgroup(self):
        event = _base_event(
            46,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="convoy_wreck",
            loot_preset="military_high",
        )
        record, events_root, spawns_root, groups_root = self._build_airdrop_event_node(event)

        self.assertFalse(record.get("use_eventgroup"))
        self.assertFalse(record.get("empty_event_children"))
        self.assertEqual(["StaticObj_Wreck_HMMWV_DE"], record.get("mapgroupproto_classes"))
        children = events_root.findall("event/children/child")
        self.assertEqual(1, len(children))
        self.assertEqual("StaticObj_Wreck_HMMWV_DE", children[0].get("type"))
        pos = spawns_root.find("event/pos")
        self.assertIsNotNone(pos)
        self.assertIsNone(pos.get("group"))
        self.assertIsNone(groups_root.find("group"))

    def test_airdrop_scenes_do_not_inject_extra_vehicle_wreck_props(self):
        for scene_key in ("cargo_plane_wreck", "convoy_wreck"):
            scene = bot.SCENARIO_AIRDROP_SCENES[scene_key]
            self.assertEqual([], scene.get("props"))

    def test_airdrop_direct_spawn_replaces_stale_grouped_spawn_pos(self):
        event = _base_event(
            49,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="convoy_wreck",
        )
        records, _warnings = bot.console_ce_records_for_event(event)
        record = records[0]
        self.assertFalse(record.get("use_eventgroup"))

        spawns_root = ET.Element("eventposdef")
        stale_event = ET.SubElement(spawns_root, "event", {"name": record["name"]})
        ET.SubElement(stale_event, "pos", {"x": "1", "z": "2", "a": "0", "group": record["name"]})

        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            y=record.get("y"),
            count=record["count"],
            radius=record.get("radius") or 45,
            group_name="",
        )

        positions = spawns_root.findall("event/pos")
        self.assertEqual(1, len(positions))
        self.assertIsNone(positions[0].get("group"))
        self.assertEqual("5000", positions[0].get("x"))

    def test_gas_zone_uses_static_contaminated_area_shape(self):
        event = _base_event(
            48,
            "gas_zone",
            "ContaminatedArea_Dynamic",
            radius=80,
            gas_lifetime=1800,
        )
        records, _warnings = bot.console_ce_records_for_event(event)
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("StaticWanderingBot_48_gaszone", record["name"])
        self.assertNotIn("_r", record["name"])
        self.assertFalse(record["name"].startswith("ContaminatedAreaWanderingBot"))
        self.assertEqual("parent", record.get("limit_type"))
        self.assertEqual("ContaminatedArea_Dynamic", record["child_records"][0]["type"])

        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record.get("event_child_type") or record["class_name"],
            record["count"],
            record["lifetime"],
            limit_type=record.get("limit_type") or "child",
            child_records=record.get("child_records"),
            nominal=record.get("nominal"),
            min_count=record.get("min_count"),
            max_count=record.get("max_count"),
        )
        self.assertEqual("parent", events_root.findtext("event/limit"))

        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            radius=record.get("radius") or 45,
        )
        zone = spawns_root.find("event/zone")
        pos = spawns_root.find("event/pos")
        self.assertIsNotNone(zone)
        self.assertEqual("80", zone.get("r"))
        self.assertIsNone(zone.get("x"))
        self.assertIsNotNone(pos)
        self.assertEqual("5000", pos.get("x"))
        built = {
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": "<prototype></prototype>",
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertTrue(ok, "\n".join(messages))


class VehicleAndZombieSpawnTests(unittest.TestCase):
    """Vehicles and hordes do NOT use cfgeventgroups. Their <pos> blocks must
    still avoid the y attribute and must carry the actual class as the
    events.xml ``<child type=...>`` value."""

    def _build_event(self, event):
        records, warnings = bot.console_ce_records_for_event(event)
        self.assertTrue(records, f"event {event} produced no CE records: {warnings}")
        record = records[0]
        events_root = ET.Element("events")
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
            secondary=record.get("secondary", ""),
        )
        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            y=record.get("y"),
            count=record["count"],
            radius=record.get("radius") or 45,
            group_name="",
        )
        return record, events_root, spawns_root

    def test_vehicle_event_has_real_class_child_and_no_pos_y(self):
        event = _base_event(31, "vehicle_spawn", "Hatchback_02")
        record, events_root, spawns_root = self._build_event(event)

        self.assertFalse(record.get("use_eventgroup"))
        self.assertFalse(record.get("empty_event_children"))
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        self.assertEqual(event_node.findtext("limit"), "mixed")
        self.assertEqual(event_node.findtext("saferadius"), "0")
        self.assertEqual(event_node.findtext("distanceradius"), "25")
        self.assertEqual(event_node.findtext("cleanupradius"), "200")
        self.assertEqual(event_node.find("flags").get("remove_damaged"), "1")
        child = event_node.find("children/child")
        self.assertIsNotNone(child)
        self.assertEqual(child.get("type"), "Hatchback_02")

        positions = spawns_root.findall("event/pos")
        self.assertGreaterEqual(
            len(positions),
            5,
            "vehicle events need several nearby candidate positions so DayZ can recover from one blocked spot",
        )
        self.assertGreater(len({(pos.get("x"), pos.get("z")) for pos in positions}), 1)
        for pos in positions:
            self.assertNotIn("y", pos.attrib)

    def test_vehicle_start_speed_normal_keeps_cautious_distances(self):
        event = _base_event(31, "vehicle_spawn", "Hatchback_02", start_speed="normal")
        record, events_root, _spawns_root = self._build_event(event)

        self.assertEqual(record.get("start_speed"), "normal")
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        self.assertEqual(event_node.findtext("saferadius"), "500")
        self.assertEqual(event_node.findtext("distanceradius"), "500")
        self.assertEqual(event_node.findtext("cleanupradius"), "200")

    def test_zombie_horde_has_zone_block_no_y(self):
        event = _base_event(
            33,
            "zombie_horde",
            "ZmbM_HeavyIndustryWorker",
            preset="heavymilitaryzombie",
        )
        record, events_root, spawns_root = self._build_event(event)

        self.assertFalse(record.get("use_eventgroup"))
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        self.assertEqual(event_node.findtext("position"), "fixed")
        children = event_node.findall("children/child")
        self.assertTrue(children)
        for child in children:
            self.assertTrue(child.get("type", "").startswith(("ZmbM_", "ZmbF_")))

        spawn_event = spawns_root.find("event")
        self.assertIsNotNone(spawn_event)
        for pos in spawn_event.findall("pos"):
            self.assertNotIn("y", pos.attrib)
        # Infected hordes are zone-spawn family ? make sure a zone block is
        # emitted with x/z/r and no y attribute.
        zone = spawn_event.find("zone")
        if zone is not None:
            self.assertNotIn("y", zone.attrib)


class EventGroupChildPlacementTests(unittest.TestCase):
    """The cfgeventgroups child placement still needs all four offset attrs
    (x, y, z, a) ? these are LOCAL offsets relative to the group anchor, not
    map coordinates. This guards against accidentally stripping them along
    with the cfgeventspawns y removal."""

    def test_eventgroup_child_has_full_local_offsets(self):
        event = _base_event(32, "airdrop", "WoodenCrate", visual_marker=True, scene_type="helicopter_crash")
        records, _ = bot.console_ce_records_for_event(event)
        record = records[0]
        groups_root = ET.Element("eventgroupdef")
        bot.add_console_ce_event_group(
            groups_root,
            record["name"],
            record["class_name"],
            lootmin=record.get("child_lootmin", 40) or 40,
            lootmax=record.get("child_lootmax", 80) or 80,
            child_records=record.get("eventgroup_children"),
        )
        children = groups_root.findall("group/child")
        self.assertTrue(children)
        for child in children:
            for attr in ("x", "y", "z", "a"):
                self.assertIn(attr, child.attrib, f"cfgeventgroups child missing {attr}")


class MapGroupProtoTests(unittest.TestCase):
    """Each loot-bearing airdrop child type must have a mapgroupproto group entry,
    otherwise the live RPT prints ``No group configured for '<class>'``."""

    def test_proto_group_added_for_helicopter_crash_loot_floor(self):
        event = _base_event(
            34,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            loot_preset="military_high",
        )
        records, _ = bot.console_ce_records_for_event(event)
        record = records[0]
        proto_root = ET.Element("prototype")
        for class_name in record.get("mapgroupproto_classes") or []:
            bot.add_mapgroupproto_loot_group(proto_root, class_name, tags=record.get("mapgroupproto_tags"))
        names = {g.get("name") for g in proto_root.findall("group")}
        self.assertIn("Wreck_Mi8_Crashed", names)
        self.assertNotIn("WoodenCrate", names)
        crash_group = next(g for g in proto_root.findall("group") if g.get("name") == "Wreck_Mi8_Crashed")
        container = crash_group.find("container")
        self.assertIsNotNone(container)
        self.assertEqual(container.get("name"), "lootFloor")
        self.assertGreater(int(container.get("lootmax") or "0"), 0)
        self.assertEqual([node.get("name") for node in crash_group.findall("usage")], ["Military"])
        self.assertEqual([node.get("name") for node in crash_group.findall("value")], ["Tier4"])
        self.assertIsNotNone(container.find("category"))
        self.assertIsNotNone(container.find("tag"))
        self.assertIsNotNone(container.find("point"))
        self.assertEqual(container.find("tag").get("name"), "floor")
        self.assertEqual(container.find("point").get("flags"), "32")
        self.assertGreaterEqual(len(container.findall("point")), 8)

    def test_livonia_proto_values_do_not_generate_tier4(self):
        event = _base_event(
            34,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            loot_preset="military_high",
        )
        tags = bot.scenario_mapgroupproto_loot_tags(event, map_key="livonia")
        self.assertEqual(["Tier3"], tags.get("value"))

        proto_root = ET.Element("prototype")
        bot.add_mapgroupproto_loot_group(
            proto_root,
            "Wreck_Mi8_Crashed",
            tags=tags,
            map_key="livonia",
        )
        crash_group = next(g for g in proto_root.findall("group") if g.get("name") == "Wreck_Mi8_Crashed")
        self.assertEqual([node.get("name") for node in crash_group.findall("value")], ["Tier3"])

    def test_validator_rejects_livonia_tier4_mapgroupproto_value(self):
        event = _base_event(53, "airdrop", "WoodenCrate")
        records, _warnings = bot.console_ce_records_for_event(event, map_key="livonia")
        record = records[0]
        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            record["name"],
            record.get("event_child_type") or record["class_name"],
            record["count"],
            record["lifetime"],
            restock=record.get("restock", 0),
            limit_type=record.get("limit_type") or "child",
            child_records=record.get("child_records"),
            nominal=record.get("nominal"),
            min_count=record.get("min_count"),
            max_count=record.get("max_count"),
        )
        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
            count=record["count"],
            radius=record.get("radius") or 45,
        )
        proto_root = ET.Element("prototype")
        group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "15"})
        ET.SubElement(group, "usage", {"name": "Military"})
        ET.SubElement(group, "value", {"name": "Tier4"})
        container = ET.SubElement(group, "container", {"name": "lootFloor", "lootmax": "15"})
        ET.SubElement(container, "category", {"name": "weapons"})
        ET.SubElement(container, "tag", {"name": "floor"})
        ET.SubElement(container, "point", {"pos": "0 0 0", "range": "1", "height": "1"})

        built = {
            "map_key": "livonia",
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": bot.xml_text_from_root(proto_root),
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertFalse(ok)
        self.assertTrue(any("Tier4" in message and "livonia" in message for message in messages), messages)

    def test_validator_rejects_working_vehicle_as_static_loot_child(self):
        events_root = ET.Element("events")
        bot.add_console_ce_event_definition(
            events_root,
            "StaticWanderingBot_54_airdrop",
            "Sedan_02",
            1,
            7200,
            child_records=[{
                "type": "Sedan_02",
                "count": 1,
                "min": 1,
                "max": 1,
                "lootmin": 1,
                "lootmax": 5,
            }],
            nominal=1,
            min_count=1,
            max_count=1,
        )
        spawns_root = ET.Element("eventposdef")
        bot.add_console_ce_event_spawn(spawns_root, "StaticWanderingBot_54_airdrop", 5000, 5000)
        proto_root = ET.Element("prototype")
        group = ET.SubElement(proto_root, "group", {"name": "Sedan_02", "lootmax": "5"})
        container = ET.SubElement(group, "container", {"name": "lootFloor", "lootmax": "5"})
        ET.SubElement(container, "category", {"name": "tools"})
        ET.SubElement(container, "tag", {"name": "floor"})
        ET.SubElement(container, "point", {"pos": "0 0 0", "range": "1", "height": "1"})

        built = {
            "events_text": bot.xml_text_from_root(events_root),
            "spawns_text": bot.xml_text_from_root(spawns_root),
            "eventgroups_text": "",
            "mapgroupproto_text": bot.xml_text_from_root(proto_root),
            "source_fallbacks": [],
        }
        ok, messages = bot.validate_console_ce_xml_bundle(built, check_scope=False)
        self.assertFalse(ok)
        self.assertTrue(any("Working vehicles must use a Vehicle CE event" in message for message in messages), messages)

    def test_airdrop_proto_categories_never_include_containers_or_vehicles(self):
        event = _base_event(
            35,
            "airdrop",
            "WoodenCrate",
            loot_preset="military",
        )
        tags = bot.scenario_mapgroupproto_loot_tags(event)
        categories = {str(item).lower() for item in tags.get("category") or []}

        self.assertNotIn("containers", categories)
        self.assertNotIn("vehicles", categories)

    def test_airdrop_secondary_infected_does_not_need_mapgroupproto(self):
        event = _base_event(34, "airdrop", "WoodenCrate", visual_marker=True, scene_type="helicopter_crash")
        event["guard_class"] = "ZmbM_SoldierNormal"
        event["guard_count"] = 2
        records, _ = bot.console_ce_records_for_event(event)

        self.assertEqual("InfectedArmy", records[0].get("secondary"))
        self.assertFalse(any(child.get("type") == "ZmbM_SoldierNormal" for child in records[0]["child_records"]))
        self.assertNotIn("ZmbM_SoldierNormal", records[0].get("mapgroupproto_classes") or [])

    def test_existing_unmarked_proto_group_is_left_alone_and_managed_group_appended(self):
        proto_root = ET.Element("prototype")
        ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed"})

        _, changed = bot.add_mapgroupproto_loot_group(proto_root, "Wreck_Mi8_Crashed")

        self.assertTrue(changed)
        groups = proto_root.findall("./group[@name='Wreck_Mi8_Crashed']")
        self.assertEqual(2, len(groups))
        self.assertIsNone(groups[0].find("container"))
        container = groups[1].find("container")
        self.assertIsNotNone(container)
        self.assertEqual(container.get("name"), "lootFloor")
        self.assertGreater(int(container.get("lootmax") or "0"), 0)
        self.assertIsNotNone(container.find("category"))
        self.assertIsNotNone(container.find("tag"))
        self.assertIsNotNone(container.find("point"))
        self.assertEqual(container.find("tag").get("name"), "floor")
        self.assertEqual(container.find("point").get("flags"), "32")
        self.assertGreaterEqual(len(container.findall("point")), 8)

    def test_existing_unmarked_usable_proto_group_is_reused_without_duplicate(self):
        proto_root = ET.Element("prototype")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "15"})
        ET.SubElement(crash_group, "usage", {"name": "Military"})
        container = ET.SubElement(crash_group, "container", {"name": "lootFloor", "lootmax": "15"})
        ET.SubElement(container, "category", {"name": "weapons"})
        ET.SubElement(container, "tag", {"name": "floor"})
        ET.SubElement(container, "point", {"pos": "-2.693787 -1.888990 1.671386", "range": "0.703328", "height": "2.000000", "flags": "32"})

        returned_group, changed = bot.add_mapgroupproto_loot_group(proto_root, "Wreck_Mi8_Crashed")

        self.assertFalse(changed)
        self.assertIs(returned_group, crash_group)
        self.assertEqual(1, len(proto_root.findall("./group[@name='Wreck_Mi8_Crashed']")))

    def test_existing_marked_proto_group_gets_lootfloor_repaired(self):
        proto_root = ET.Element("prototype")
        bot.append_wandering_xml_comment(proto_root, "managed mapgroupproto group Wreck_Mi8_Crashed")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "80"})
        ET.SubElement(crash_group, "usage", {"name": "Military"})
        ET.SubElement(crash_group, "point", {"pos": "0 0 0", "range": "0.5", "height": "0.5"})

        _, changed = bot.add_mapgroupproto_loot_group(proto_root, "Wreck_Mi8_Crashed")

        self.assertTrue(changed)
        container = crash_group.find("container")
        self.assertIsNotNone(container)
        self.assertEqual(container.get("name"), "lootFloor")
        self.assertGreater(int(container.get("lootmax") or "0"), 0)
        self.assertIsNotNone(container.find("category"))
        self.assertEqual(container.find("tag").get("name"), "floor")
        self.assertEqual(container.find("point").get("flags"), "32")

    def test_existing_marked_proto_group_drops_vehicle_loot_categories(self):
        proto_root = ET.Element("prototype")
        bot.append_wandering_xml_comment(proto_root, "managed mapgroupproto group Wreck_Mi8_Crashed")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "80"})
        container = ET.SubElement(crash_group, "container", {"name": "lootFloor", "lootmax": "80"})
        ET.SubElement(container, "category", {"name": "containers"})
        ET.SubElement(container, "category", {"name": "vehicles"})
        ET.SubElement(container, "category", {"name": "weapons"})

        _, changed = bot.add_mapgroupproto_loot_group(
            proto_root,
            "Wreck_Mi8_Crashed",
            tags={"usage": ["Military"], "value": ["Tier4"], "category": ["weapons", "tools"]},
        )

        self.assertTrue(changed)
        categories = [node.get("name") for node in container.findall("category")]
        self.assertEqual(["weapons"], categories)

    def test_existing_marked_proto_group_drops_obsolete_crash_usage(self):
        proto_root = ET.Element("prototype")
        bot.append_wandering_xml_comment(proto_root, "managed mapgroupproto group Wreck_Mi8_Crashed")
        crash_group = ET.SubElement(proto_root, "group", {"name": "Wreck_Mi8_Crashed", "lootmax": "80"})
        ET.SubElement(crash_group, "usage", {"name": "Crash"})
        ET.SubElement(crash_group, "value", {"name": "Tier1"})

        _, changed = bot.add_mapgroupproto_loot_group(
            proto_root,
            "Wreck_Mi8_Crashed",
            tags={"usage": ["Military"], "value": ["Tier4"], "category": ["weapons"]},
        )

        self.assertTrue(changed)
        self.assertEqual([node.get("name") for node in crash_group.findall("usage")], ["Military"])
        self.assertEqual([node.get("name") for node in crash_group.findall("value")], ["Tier4"])


class BuildConsoleCeEventFilesTests(unittest.TestCase):
    def setUp(self):
        self.original_download = bot.download_console_ce_source
        self.guild_id = "999001"

    def tearDown(self):
        bot.download_console_ce_source = self.original_download
        bot.guild_configs.pop(self.guild_id, None)

    def test_cfgspawnabletypes_scope_block_skips_optional_cargo_tuning(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": (
                '<spawnabletypes><type name="WoodenCrate"><damage min="0.1" max="0.2" /></type><type name="Hammer" /></spawnabletypes>',
                f"{base_path}/cfgspawnabletypes.xml",
            ),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    41,
                    "airdrop",
                    "WoodenCrate",
                    loot=["Hammer"],
                    loot_preset="custom",
                    visual_marker=False,
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertFalse(built.get("spawnabletypes_text"))
        self.assertFalse(built.get("spawnabletypes_path"))
        self.assertTrue(
            any("per-item cargo tuning" in str(message) for message in built.get("messages", [])),
            built.get("messages", []),
        )
        ok, messages = bot.validate_console_ce_xml_bundle(built)
        self.assertTrue(ok, "\n".join(messages))

    def test_zombie_horde_uses_native_infected_loot_not_spawnabletypes(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": ("<eventposdef></eventposdef>", f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
            "spawnabletypes_path": (
                '<spawnabletypes><type name="ZmbM_SoldierNormal"><cargo chance="1.00"><item name="Rag" /></cargo></type></spawnabletypes>',
                f"{base_path}/cfgspawnabletypes.xml",
            ),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    42,
                    "zombie_horde",
                    "ZmbM_SoldierNormal",
                    loot=["Rag", "BandageDressing"],
                    loot_preset="medical",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        self.assertFalse(built.get("spawnabletypes_text"))
        self.assertFalse(built.get("spawnabletypes_path"))
        events_root = ET.fromstring(built["events_text"])
        child = events_root.find("event/children/child")
        self.assertIsNotNone(child)
        self.assertEqual(child.get("type"), "ZmbM_SoldierNormal")
        self.assertEqual(child.get("lootmin"), "0")
        self.assertEqual(child.get("lootmax"), "5")
        ok, messages = bot.validate_console_ce_xml_bundle(built)
        self.assertTrue(ok, "\n".join(messages))

    def test_legacy_hordetrigger_spawn_block_is_removed(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        legacy_spawns = (
            '<eventposdef>'
            '<event name="HordeTrigger"><pos x="1" z="2" a="0" /></event>'
            '<event name="AnimalBear"><pos x="3" z="4" a="0" /></event>'
            '</eventposdef>'
        )
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
            "spawns_path": (legacy_spawns, f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    42,
                    "zombie_horde",
                    "ZmbM_SoldierNormal",
                    preset="military_zombie",
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        spawns_root = ET.fromstring(built["spawns_text"])
        self.assertIsNone(spawns_root.find("./event[@name='HordeTrigger']"))
        self.assertIsNotNone(spawns_root.find("./event[@name='AnimalBear']"))
        self.assertIsNotNone(spawns_root.find("./event[@name='InfectedWanderingBot_horde_militaryzombie']"))
        ok, messages = bot.validate_console_ce_xml_bundle(built)
        self.assertTrue(ok, "\n".join(messages))

    def test_animal_pack_adds_managed_animal_event_without_touching_vanilla(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        vanilla_spawns = '<eventposdef><event name="AnimalBear"><pos x="1" z="2" a="0" /></event></eventposdef>'
        vanilla_events = (
            '<events><event name="AnimalBear"><nominal>0</nominal><min>5</min><max>8</max>'
            '<lifetime>180</lifetime><restock>0</restock><saferadius>200</saferadius>'
            '<distanceradius>0</distanceradius><cleanupradius>0</cleanupradius>'
            '<flags deletable="0" init_random="0" remove_damaged="1" />'
            '<position>fixed</position><limit>custom</limit><active>1</active>'
            '<children><child lootmax="0" lootmin="0" max="1" min="1" type="Animal_UrsusArctos" /></children>'
            '</event></events>'
        )
        sources = {
            "events_path": (vanilla_events, f"{base_path}/db/events.xml"),
            "spawns_path": (vanilla_spawns, f"{base_path}/cfgeventspawns.xml"),
            "eventgroups_path": ("<eventgroupdef></eventgroupdef>", f"{base_path}/cfgeventgroups.xml"),
            "mapgroupproto_path": ("<prototype></prototype>", f"{base_path}/mapgroupproto.xml"),
            "cfgenvironment_path": ("<env><territories /></env>", f"{base_path}/cfgenvironment.xml"),
        }

        def fake_download(_config, _guild_id, key, _requested_path=""):
            text, path = sources[key]
            return text, path, f"{key} source"

        bot.download_console_ce_source = fake_download
        config = {
            "guild_name": "Test Livonia",
            "server_map": "livonia",
            "server_platform": "xbox",
            "scenario_events": [
                _base_event(
                    20,
                    "animal_pack",
                    "Animal_UrsusArctos",
                    preset="bear",
                    count=2,
                    radius=90,
                )
            ],
        }
        bot.guild_configs[self.guild_id] = config

        built = bot.build_console_ce_event_files(self.guild_id, config)

        spawns_root = ET.fromstring(built["spawns_text"])
        vanilla_event = spawns_root.find("./event[@name='AnimalBear']")
        self.assertIsNotNone(vanilla_event)
        self.assertTrue(any(pos.get("x") == "1" and pos.get("z") == "2" for pos in vanilla_event.findall("pos")))
        self.assertEqual(1, len(vanilla_event.findall("pos")))
        managed_spawn = spawns_root.find("./event[@name='AnimalWanderingBot_animal_bear']")
        self.assertIsNotNone(managed_spawn)
        positions = [pos for pos in managed_spawn.findall("pos") if pos.get("active") == "1"]
        self.assertEqual(2, len(positions))
        self.assertTrue(any(pos.get("x") == "5000" and pos.get("z") == "5000" for pos in positions))
        self.assertFalse("HerdWanderingBot" in built["spawns_text"])
        events_root = ET.fromstring(built["events_text"])
        vanilla_bear = events_root.find("./event[@name='AnimalBear']")
        self.assertIsNotNone(vanilla_bear)
        self.assertEqual("0", vanilla_bear.findtext("nominal"))
        managed_event = events_root.find("./event[@name='AnimalWanderingBot_animal_bear']")
        self.assertIsNotNone(managed_event)
        self.assertEqual("2", managed_event.findtext("nominal"))
        self.assertEqual("2", managed_event.findtext("min"))
        self.assertEqual("2", managed_event.findtext("max"))
        self.assertEqual("child", managed_event.findtext("limit"))
        flags = managed_event.find("flags")
        self.assertIsNotNone(flags)
        self.assertEqual("0", flags.get("deletable"))
        self.assertEqual("1", flags.get("remove_damaged"))
        child = managed_event.find("children/child")
        self.assertIsNotNone(child)
        self.assertEqual("Animal_UrsusArctos", child.get("type"))
        self.assertEqual("1", child.get("min"))
        self.assertEqual("1", child.get("max"))
        self.assertFalse("HerdWanderingBot" in built["events_text"])
        self.assertFalse(built.get("cfgenvironment_text"))
        self.assertEqual([], built.get("animal_territory_files") or [])
        ok, messages = bot.validate_console_ce_xml_bundle(built)
        self.assertTrue(ok, "\n".join(messages))
        scope_ok, scope_messages = bot.validate_console_ce_upload_scope(built)
        self.assertTrue(scope_ok, "\n".join(scope_messages))


if __name__ == "__main__":
    unittest.main()
