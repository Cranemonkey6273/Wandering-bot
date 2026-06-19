"""Cross-file validator for the live Wandering-bot DayZ CE XML set.

USAGE:
    python tools/validate_ce_xml.py /path/to/dayzOffline.enoch

The folder is expected to contain the five files the bot writes to a live
Livonia/Enoch (or Chernarus) mission:

    db/events.xml
    cfgeventspawns.xml
    cfgeventgroups.xml
    mapgroupproto.xml
    cfgspawnabletypes.xml

The validator walks the relationships between the files and reports any
mismatch that would cause DayZ to load an event definition but refuse to
spawn it (the failure mode the live server was exhibiting):

* Every WanderingBot ``<event name="...">`` in events.xml has a matching
  cfgeventspawns ``<event name="...">``.
* Every ``<pos group="X">`` in cfgeventspawns has a matching
  cfgeventgroups ``<group name="X">``.
* Every ``<child type="C">`` inside cfgeventgroups has a matching
  ``<group name="C">`` in mapgroupproto.xml.
* events.xml Static events that reference a group via cfgeventspawns leave
  ``<children/>`` empty (vanilla DayZ pattern). Otherwise DayZ loads the
  definition but never spawns the event.
* cfgeventspawns ``<pos>`` carries only x/z/a ? never y.
* cfgspawnabletypes cargo entries referenced by Wandering events exist.

This is a read-only diagnostic; it does NOT mutate the files. Run it after
each dashboard ``Retry/save`` to confirm the generated CE bundle is internally
consistent before issuing a DayZ server restart.
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

WANDERING_MARKER = "WanderingBot_"
ALLOWED_FAMILIES = (
    "Ambient",
    "Animal",
    "ContaminatedArea",
    "Infected",
    "Item",
    "Static",
    "Trajectory",
    "Vehicle",
)


@dataclass
class ValidationReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.info.append(message)

    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines: List[str] = []
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            lines.extend(f"  - {item}" for item in self.errors)
        if self.warnings:
            lines.append(f"WARNINGS ({len(self.warnings)}):")
            lines.extend(f"  - {item}" for item in self.warnings)
        if self.info:
            lines.append(f"NOTES ({len(self.info)}):")
            lines.extend(f"  - {item}" for item in self.info)
        if not lines:
            lines.append("No issues found.")
        return "\n".join(lines)


def _parse_xml(path: str, fallback_root: str, report: ValidationReport) -> Optional[ET.Element]:
    if not os.path.exists(path):
        report.fail(f"Missing file: {path}")
        return None
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as error:
        report.fail(f"{os.path.basename(path)} parse error: {error}")
        return None


def _is_wandering(name: str) -> bool:
    return WANDERING_MARKER in str(name or "")


def _has_zone_family(name: str) -> bool:
    return name.startswith(("Ambient", "Animal", "ContaminatedArea", "Infected", "Item", "Trajectory"))


def _has_static_family(name: str) -> bool:
    return name.startswith("Static")


def validate_bundle(mission_dir: str) -> ValidationReport:
    report = ValidationReport()

    events_path = os.path.join(mission_dir, "db", "events.xml")
    spawns_path = os.path.join(mission_dir, "cfgeventspawns.xml")
    eventgroups_path = os.path.join(mission_dir, "cfgeventgroups.xml")
    mapgroupproto_path = os.path.join(mission_dir, "mapgroupproto.xml")
    cfgspawnabletypes_path = os.path.join(mission_dir, "cfgspawnabletypes.xml")

    events_root = _parse_xml(events_path, "events", report)
    spawns_root = _parse_xml(spawns_path, "eventposdef", report)
    eventgroups_root = _parse_xml(eventgroups_path, "eventgroupdef", report)
    mapgroupproto_root = _parse_xml(mapgroupproto_path, "prototype", report)
    cfgspawnabletypes_root = _parse_xml(cfgspawnabletypes_path, "spawnabletypes", report)

    if events_root is None or spawns_root is None:
        report.fail("Cannot continue without events.xml and cfgeventspawns.xml")
        return report

    wandering_events: Dict[str, ET.Element] = {}
    for event_node in events_root.findall("event"):
        name = (event_node.get("name") or "").strip()
        if not _is_wandering(name):
            continue
        wandering_events[name] = event_node

        if not name.startswith(ALLOWED_FAMILIES):
            report.fail(f"events.xml `{name}` is not prefixed with a known CE family")

        if (event_node.findtext("position") or "").strip() != "fixed":
            report.fail(f"events.xml `{name}` must use <position>fixed</position>")
        if (event_node.findtext("active") or "").strip() != "1":
            report.fail(f"events.xml `{name}` is not active (<active>0</active>)")
        try:
            nominal = int((event_node.findtext("nominal") or "0").strip() or 0)
        except ValueError:
            nominal = 0
        try:
            minimum = int((event_node.findtext("min") or "0").strip() or 0)
        except ValueError:
            minimum = 0
        if nominal <= 0 and minimum <= 0:
            report.fail(f"events.xml `{name}` has nominal=0 AND min=0 ? DayZ will never spawn it")

    spawn_events: Dict[str, ET.Element] = {
        (event_node.get("name") or "").strip(): event_node
        for event_node in spawns_root.findall("event")
        if _is_wandering(event_node.get("name") or "")
    }

    # Cross-check: every events.xml WanderingBot entry has a matching
    # cfgeventspawns entry, and vice versa.
    for name in wandering_events:
        if name not in spawn_events:
            report.fail(f"`{name}` is in events.xml but missing from cfgeventspawns.xml")
    for name in spawn_events:
        if name not in wandering_events:
            report.fail(f"`{name}` is in cfgeventspawns.xml but missing from events.xml")

    # cfgeventspawns sanity: no y attribute on <pos>, no y on <zone>, every
    # <pos group="..."> must resolve to a cfgeventgroups <group>.
    referenced_groups: Set[str] = set()
    for name, spawn_node in spawn_events.items():
        any_pos_or_zone = False
        for pos in spawn_node.findall("pos"):
            any_pos_or_zone = True
            if "y" in pos.attrib:
                report.fail(
                    f"cfgeventspawns.xml `{name}` <pos> includes y='{pos.attrib['y']}' ? vanilla DayZ "
                    "ignores/rejects forced height in cfgeventspawns."
                )
            group_name = (pos.get("group") or "").strip()
            if group_name:
                referenced_groups.add(group_name)
        for zone in spawn_node.findall("zone"):
            any_pos_or_zone = True
            if "y" in zone.attrib:
                report.fail(
                    f"cfgeventspawns.xml `{name}` <zone> includes y='{zone.attrib['y']}'"
                )
        if not any_pos_or_zone:
            report.fail(f"cfgeventspawns.xml `{name}` has no <pos> or <zone>")

    # events.xml children block must be empty for Static events bound to a
    # cfgeventgroups entry (the vanilla DayZ pattern).
    for name, event_node in wandering_events.items():
        spawn_node = spawn_events.get(name)
        if spawn_node is None:
            continue
        has_group_pos = any((pos.get("group") or "").strip() for pos in spawn_node.findall("pos"))
        child_nodes = event_node.findall("children/child")
        if has_group_pos and child_nodes:
            report.fail(
                f"events.xml `{name}` has <children> entries AND cfgeventspawns.xml uses "
                f"group=\"{name}\". DayZ refuses to instantiate the event when both paths are set; "
                "leave <children/> empty for eventgroup-routed Static events."
            )
        if not has_group_pos and not child_nodes:
            if _has_static_family(name):
                report.fail(
                    f"events.xml `{name}` has empty <children/> but cfgeventspawns has no "
                    "group reference either ? nothing to spawn."
                )
        if has_group_pos and not child_nodes and eventgroups_root is not None:
            group_names = [
                (pos.get("group") or "").strip()
                for pos in spawn_node.findall("pos")
                if (pos.get("group") or "").strip()
            ]
            for group_name in dict.fromkeys(group_names):
                group_node = eventgroups_root.find(f"./group[@name='{group_name}']")
                if group_node is None:
                    continue
                max_values: List[int] = []
                for child in group_node.findall("child"):
                    raw_max = child.get("max")
                    if raw_max is None:
                        raw_max = child.get("lootmax")
                    try:
                        max_values.append(int(str(raw_max or "0").strip() or 0))
                    except ValueError:
                        max_values.append(0)
                if not max_values or max(max_values) <= 0:
                    report.fail(
                        f"events.xml `{name}` has empty <children/> and uses cfgeventgroups.xml "
                        f"`{group_name}`, but all group child max/lootmax values are 0. DayZ disables "
                        "child-limited Static events in this shape."
                    )

    # cfgeventgroups validation.
    eventgroup_nodes: Dict[str, ET.Element] = {}
    if eventgroups_root is not None:
        for group_node in eventgroups_root.findall("group"):
            name = (group_node.get("name") or "").strip()
            if not _is_wandering(name):
                continue
            eventgroup_nodes[name] = group_node

        for group_name in referenced_groups:
            if group_name not in eventgroup_nodes:
                report.fail(
                    f"cfgeventspawns.xml references group `{group_name}` but cfgeventgroups.xml has no "
                    f"<group name=\"{group_name}\"> entry."
                )
        for group_name, group_node in eventgroup_nodes.items():
            if group_name not in referenced_groups:
                report.warn(
                    f"cfgeventgroups.xml has WanderingBot group `{group_name}` that is not referenced by "
                    "any cfgeventspawns <pos group=\"...\">"
                )
            children = group_node.findall("child")
            if not children:
                report.fail(f"cfgeventgroups.xml `{group_name}` has no <child>")
            for child in children:
                if not (child.get("type") or "").strip():
                    report.fail(f"cfgeventgroups.xml `{group_name}` <child> missing type")
                for axis in ("x", "y", "z", "a"):
                    if (child.get(axis) or "").strip() == "":
                        report.fail(
                            f"cfgeventgroups.xml `{group_name}` <child type='{child.get('type')}'> "
                            f"missing {axis} offset (these are local offsets relative to the group)."
                        )

    # mapgroupproto validation.
    proto_groups: Set[str] = set()
    if mapgroupproto_root is not None:
        for group_node in mapgroupproto_root.findall("group"):
            proto_groups.add((group_node.get("name") or "").strip())
        for group_name, group_node in eventgroup_nodes.items():
            for child in group_node.findall("child"):
                child_type = (child.get("type") or "").strip()
                if child_type and child_type not in proto_groups:
                    report.fail(
                        f"mapgroupproto.xml is missing <group name=\"{child_type}\"> ? required by "
                        f"cfgeventgroups.xml `{group_name}`. DayZ will log "
                        f"\"No group configured for '{child_type}'\" and skip the spawn."
                    )

    # cfgspawnabletypes sanity: every event group child class that is a known
    # crate-like container should optionally have a <type name="..."> entry.
    spawnable_types: Set[str] = set()
    if cfgspawnabletypes_root is not None:
        for type_node in cfgspawnabletypes_root.findall("type"):
            spawnable_types.add((type_node.get("name") or "").strip())

    # Static class names that DayZ will never cargo-spawn loot into. Just a
    # soft warning so the operator knows the crate cargo definition is being
    # ignored, not an error.
    static_only_classes = {"Wreck_Mi8_Crashed", "Wreck_UH1Y", "Land_Wreck_C130J_Cargo"}
    for group_name, group_node in eventgroup_nodes.items():
        for child in group_node.findall("child"):
            child_type = (child.get("type") or "").strip()
            if not child_type:
                continue
            try:
                lootmax = int((child.get("lootmax") or "0").strip() or 0)
            except ValueError:
                lootmax = 0
            if lootmax > 0 and child_type in static_only_classes:
                report.warn(
                    f"cfgeventgroups.xml `{group_name}` gives lootmax>0 to static prop "
                    f"`{child_type}` ? DayZ ignores cargo on these classes."
                )

    if not report.errors:
        report.note(f"Validated {len(wandering_events)} WanderingBot event(s).")
        report.note(f"Validated {len(eventgroup_nodes)} WanderingBot cfgeventgroups entry.")
        report.note(f"Mapgroupproto has {len(proto_groups)} group prototype(s).")

    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mission_dir",
        help="Path to the live mission folder (e.g. /dayzxb_missions/dayzOffline.enoch).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors when computing the exit code.",
    )
    args = parser.parse_args(argv)

    report = validate_bundle(args.mission_dir)
    print(report.render())
    if not report.ok():
        return 2
    if args.strict and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
