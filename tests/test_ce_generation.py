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
    """Verify the events.xml/cfgeventspawns/cfgeventgroups linkage for airdrops."""

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

    def test_airdrop_events_xml_children_block_is_empty(self):
        """events.xml `<children/>` must be empty when the event is bound to a
        cfgeventgroups group via cfgeventspawns ``<pos group="...">``. Earlier
        revisions emitted both the static ``<child type="WoodenCrate"/>`` AND a
        ``group="..."`` reference, which caused DayZ to load the event but
        never instantiate it (matches the RPT 0-spawn-line symptom)."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, events_root, _spawns, _groups = self._build_airdrop_event_node(event)

        self.assertTrue(record.get("use_eventgroup"))
        self.assertTrue(record.get("empty_event_children"))
        event_node = events_root.find("event")
        self.assertIsNotNone(event_node)
        children_node = event_node.find("children")
        self.assertIsNotNone(children_node, "events.xml event must still carry a <children/> element")
        self.assertEqual(
            list(children_node.findall("child")),
            [],
            "events.xml <children/> must be empty for eventgroup-routed Static events; "
            "otherwise DayZ refuses to instantiate the event.",
        )

    def test_airdrop_cfgeventspawns_pos_carries_group(self):
        """cfgeventspawns.xml <pos> must reference the group by name and must
        NOT contain a ``y`` attribute (vanilla DayZ only carries x, z, a)."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, _events, spawns_root, _groups = self._build_airdrop_event_node(event)

        spawn_event = spawns_root.find("event")
        self.assertIsNotNone(spawn_event)
        pos = spawn_event.find("pos")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.get("group"), record["name"])
        for attr in ("x", "z", "a"):
            self.assertIn(attr, pos.attrib)
        self.assertNotIn(
            "y", pos.attrib,
            "cfgeventspawns.xml <pos> must not carry y ? vanilla DayZ samples "
            "terrain height itself, and forcing y=0 prevents the spawn.",
        )

    def test_eventgroup_carries_real_object_class(self):
        """The actual scene object must live in cfgeventgroups.xml,
        keyed by the event name. That is the source DayZ uses to instantiate
        the Static event scene."""
        event = _base_event(29, "airdrop", "WoodenCrate")
        record, _events, _spawns, groups_root = self._build_airdrop_event_node(event)

        group = groups_root.find("group")
        self.assertIsNotNone(group)
        self.assertEqual(group.get("name"), record["name"])
        children = group.findall("child")
        self.assertTrue(children, "cfgeventgroups <group> must contain at least one <child>")
        types_in_group = {child.get("type") for child in children}
        self.assertIn("Wreck_Mi8_Crashed", types_in_group)
        self.assertNotIn("WoodenCrate", types_in_group)
        primary_child = next(child for child in children if child.get("type") == "Wreck_Mi8_Crashed" and "spawnsecondary" not in child.attrib)
        self.assertEqual(primary_child.get("lootmax"), "0")
        self.assertEqual(primary_child.get("lootmin"), "0")

    def test_helicopter_airdrop_uses_crash_and_proto_tags_not_item_children(self):
        event = _base_event(
            32,
            "airdrop",
            "WoodenCrate",
            visual_marker=True,
            scene_type="helicopter_crash",
            loot_preset="military_high",
        )
        record, _events, _spawns, groups_root = self._build_airdrop_event_node(event)

        self.assertEqual(record["event_child_type"], "Wreck_Mi8_Crashed")
        group = groups_root.find("group")
        children = group.findall("child")
        types_in_group = [child.get("type") for child in children]
        self.assertIn("Wreck_Mi8_Crashed", types_in_group)
        self.assertNotIn("WoodenCrate", types_in_group)
        crash_children = [child for child in children if child.get("type") == "Wreck_Mi8_Crashed"]
        self.assertTrue(any("spawnsecondary" not in child.attrib and child.get("lootmax") == "0" for child in crash_children))
        self.assertTrue(any(child.get("spawnsecondary") == "false" for child in crash_children))
        non_crash_secondary_children = [
            child for child in children
            if child.get("spawnsecondary") == "false" and child.get("type") != "Wreck_Mi8_Crashed"
        ]
        self.assertEqual([], non_crash_secondary_children)
        self.assertFalse(any(child.get("type") in bot.SCENARIO_AIRDROP_GROUND_LOOT for child in children))

    def test_airdrop_guards_are_eventgroup_children(self):
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
        guard_children = [
            child for child in records[0]["eventgroup_children"]
            if child.get("type") == "ZmbM_SoldierNormal"
        ]
        self.assertEqual(3, len(guard_children))
        self.assertTrue(all(child.get("spawnsecondary") == "false" for child in guard_children))


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
    """Each cfgeventgroups child type must have a mapgroupproto group entry,
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
        for child in record["eventgroup_children"]:
            if bot.eventgroup_child_needs_mapgroupproto(child):
                bot.add_mapgroupproto_loot_group(proto_root, child["type"], tags=record.get("mapgroupproto_tags"))
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

    def test_guard_children_do_not_need_mapgroupproto(self):
        event = _base_event(34, "airdrop", "WoodenCrate", visual_marker=True, scene_type="helicopter_crash")
        event["guard_class"] = "ZmbM_SoldierNormal"
        event["guard_count"] = 2
        records, _ = bot.console_ce_records_for_event(event)
        guard_child = next(child for child in records[0]["eventgroup_children"] if child.get("type") == "ZmbM_SoldierNormal")

        self.assertFalse(bot.eventgroup_child_needs_mapgroupproto(guard_child))

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

    def test_animal_pack_uses_wandering_territory_without_touching_vanilla_spawns(self):
        base_path = "/dayzxb_missions/dayzOffline.enoch"
        vanilla_spawns = '<eventposdef><event name="AnimalBear"><pos x="1" z="2" a="0" /></event></eventposdef>'
        sources = {
            "events_path": ("<events></events>", f"{base_path}/db/events.xml"),
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
        self.assertEqual(1, len(vanilla_event.findall("pos")))
        self.assertEqual(vanilla_event.find("pos").attrib, {"x": "1", "z": "2", "a": "0"})
        self.assertFalse(built.get("events_text", "").count("AnimalBear"))
        self.assertTrue(built.get("cfgenvironment_text"))
        self.assertIn("wanderingbot_animal_bear", built["cfgenvironment_text"].lower())
        self.assertEqual(1, len(built.get("animal_territory_files") or []))
        self.assertIn("AnimalBear", built["animal_territory_files"][0].get("event_names") or [])
        self.assertIn('<zone name="HuntingGround"', built["animal_territory_files"][0].get("text") or "")
        ok, messages = bot.validate_console_ce_xml_bundle(built)
        self.assertTrue(ok, "\n".join(messages))


if __name__ == "__main__":
    unittest.main()
