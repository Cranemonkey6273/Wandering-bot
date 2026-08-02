"""Shared DayZ file layout and upload validation helpers.

This module is the central registry for vanilla/custom DayZ file shapes that
Wandering Bot is allowed to read, merge, or upload. Keep file-specific roots
and JSON expectations here so bot and dashboard upload paths use the same
guardrails.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any


BACKUP_SUFFIX_RE = re.compile(
    r"^(?P<filename>.+\.(?:xml|json))\.wandering(?:bot)?-backup-(?:latest|\d{8,})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DayZFileSpec:
    filename: str
    kind: str
    xml_root: str = ""
    required_children: tuple[str, ...] = ()
    json_root_types: tuple[str, ...] = ()
    description: str = ""


DAYZ_FILE_SPECS: dict[str, DayZFileSpec] = {
    "init.c": DayZFileSpec("init.c", "script", description="mission initialisation script and ObjectSpawner hooks"),
    "events.xml": DayZFileSpec("events.xml", "xml", "events", ("event",), description="CE event definitions"),
    "cfgeventspawns.xml": DayZFileSpec("cfgeventspawns.xml", "xml", "eventposdef", ("event",), description="CE event positions"),
    "cfgeventgroups.xml": DayZFileSpec("cfgeventgroups.xml", "xml", "eventgroupdef", ("group",), description="CE static event groups"),
    "mapgroupproto.xml": DayZFileSpec("mapgroupproto.xml", "xml", "prototype", ("group",), description="CE map group loot prototypes"),
    "mapgrouppos.xml": DayZFileSpec("mapgrouppos.xml", "xml", "map", ("group",), description="map group placements"),
    "mapclusterproto.xml": DayZFileSpec("mapclusterproto.xml", "xml", "prototype", ("clusters",), description="map cluster prototype definitions"),
    "mapgroupcluster.xml": DayZFileSpec("mapgroupcluster.xml", "xml", "map", ("group",), description="map cluster placements"),
    "mapgroupcluster01.xml": DayZFileSpec("mapgroupcluster01.xml", "xml", "map", ("group",), description="map cluster placements"),
    "mapgroupcluster02.xml": DayZFileSpec("mapgroupcluster02.xml", "xml", "map", ("group",), description="map cluster placements"),
    "mapgroupcluster03.xml": DayZFileSpec("mapgroupcluster03.xml", "xml", "map", ("group",), description="map cluster placements"),
    "mapgroupcluster04.xml": DayZFileSpec("mapgroupcluster04.xml", "xml", "map", ("group",), description="map cluster placements"),
    "mapgroupdirt.xml": DayZFileSpec("mapgroupdirt.xml", "xml", "map", description="map dirt/terrain group placements"),
    "cfgspawnabletypes.xml": DayZFileSpec("cfgspawnabletypes.xml", "xml", "spawnabletypes", ("type",), description="attachments and cargo"),
    "cfgenvironment.xml": DayZFileSpec("cfgenvironment.xml", "xml", "env", description="environment/territory references"),
    "zombie_territories.xml": DayZFileSpec("zombie_territories.xml", "xml", "territory-type", ("territory",), description="infected territory zones"),
    "cfgareaeffects.xml": DayZFileSpec("cfgareaeffects.xml", "xml", "areaeffects", description="contaminated area presets"),
    "messages.xml": DayZFileSpec("messages.xml", "xml", "messages", description="server messages"),
    "cfgplayerspawnpoints.xml": DayZFileSpec("cfgplayerspawnpoints.xml", "xml", "playerspawnpoints", ("fresh",), description="fresh-spawn positions and loadout settings"),
    "cfgignorelist.xml": DayZFileSpec("cfgignorelist.xml", "xml", "ignore", ("type",), description="economy cleanup ignore list"),
    "cfglimitsdefinition.xml": DayZFileSpec("cfglimitsdefinition.xml", "xml", "lists", description="central economy category, tag and usage lists"),
    "cfglimitsdefinitionuser.xml": DayZFileSpec("cfglimitsdefinitionuser.xml", "xml", "user_lists", description="custom central economy category, tag and usage lists"),
    "cfgrandompresets.xml": DayZFileSpec("cfgrandompresets.xml", "xml", "randompresets", description="central economy random cargo presets"),
    "types.xml": DayZFileSpec("types.xml", "xml", "types", ("type",), description="loot economy types"),
    "globals.xml": DayZFileSpec("globals.xml", "xml", "variables", ("var",), description="global economy variables"),
    "economy.xml": DayZFileSpec("economy.xml", "xml", "economy", description="central economy switches"),
    "cfgeconomycore.xml": DayZFileSpec("cfgeconomycore.xml", "xml", "economycore", description="economy file includes"),
    "cfgweather.xml": DayZFileSpec("cfgweather.xml", "xml", "weather", description="weather, rain, fog and storm settings"),
    "cfggameplay.json": DayZFileSpec("cfggameplay.json", "json", json_root_types=("object",), description="gameplay flags and object spawner references"),
    "cfgundergroundtriggers.json": DayZFileSpec("cfgundergroundtriggers.json", "json", json_root_types=("object",), description="underground area trigger settings"),
    "cfgeffectarea.json": DayZFileSpec("cfgeffectarea.json", "json", json_root_types=("object",), description="gas particle settings"),
    "cfgplayerspawn.json": DayZFileSpec("cfgplayerspawn.json", "json", json_root_types=("object",), description="fresh spawn loadouts"),
    "objectspawner.json": DayZFileSpec("objectspawner.json", "json", json_root_types=("object",), description="ObjectSpawner object placements"),
}

DAYZ_TERRITORY_FILE_SPEC = DayZFileSpec(
    "*_territories.xml",
    "xml",
    "territory-type",
    ("territory",),
    description="animal/infected territory zones",
)

DAYZ_CUSTOM_JSON_FILE_SPEC = DayZFileSpec(
    "custom/*.json",
    "json",
    json_root_types=("object", "array"),
    description=(
        "custom DayZ JSON. Wandering Bot recognises ObjectSpawner, spawning-gear, "
        "restricted-area, effect-area and underground-trigger structures; mod-specific "
        "schemas still need that mod's current config or documentation."
    ),
)

DAYZ_BLOCKED_OBJECT_SPAWNER_REF_FILENAMES = {
    "newcontainerbase.json",
}

DAYZ_UNSAFE_OBJECT_SPAWNER_CLASS_KEYS = {
    "shockpistol",
    "shockpistolblack",
}

# Concise, version-aware working knowledge supplied to the DayZ AI sandbox.
# This is deliberately guidance rather than a copied third-party file library:
# a customer's complete current mission file and the bundled DayZ 1.29 vanilla
# reference remain the source of truth for any complete output.
DAYZ_AGENT_FILE_KNOWLEDGE: dict[str, dict[str, Any]] = {
    "cfggameplay.json": {
        "purpose": "Gameplay switches and cross-file mission references.",
        "dependencies": [
            "WorldsData.objectSpawnersArr -> ObjectSpawner JSON paths",
            "WorldsData.playerRestrictedAreaFiles -> restricted-area JSON paths",
            "PlayerData.spawnGearPresetFiles -> spawning-gear JSON paths",
        ],
        "variants": "Keep the selected map/version's existing GeneralData, PlayerData, WorldsData, UIData and MapData keys; do not invent missing sections.",
        "safety": "Changing a reference path without uploading the matching file will break that feature. Preserve all unrelated arrays.",
    },
    "cfgweather.xml": {
        "purpose": "Mission weather configuration when the server is using cfgweather rather than a scripted weather state machine.",
        "dependencies": ["Weather can also be controlled by mission init.c / WorldData scripts; use one intended control path."],
        "variants": "Modern DayZ 1.29 references use overcast, fog, rain, windMagnitude, windDirection, snowfall and storm. Older/documented layouts can use wind/maxspeed and child elements instead of attributes.",
        "safety": "Use the full current or matching vanilla layout for a replacement. Rain and storms depend on overcast thresholds; validate numbers and test after restart.",
    },
    "objectspawner.json": {
        "purpose": "Places supported DayZ objects via an Objects array.",
        "dependencies": ["Add the JSON file path to WorldsData.objectSpawnersArr in cfggameplay.json."],
        "variants": "Objects use name, pos [x,y,z], optional ypr [yaw,pitch,roll], optional scale and enabled fields. Use the current file for any extra fields.",
        "safety": "Do not use ObjectSpawner for weapon loot. Confirm classnames and true terrain height; test a small placement batch first.",
    },
    "spawning_gear": {
        "purpose": "Starting gear presets for fresh spawns.",
        "dependencies": ["Add the JSON file path to PlayerData.spawnGearPresetFiles in cfggameplay.json."],
        "variants": "Preset JSON commonly uses spawnWeight, characterTypes, attachmentSlotItemSets, discreteItemSets / discreteUnsortedItemSets and nested child item sets.",
        "safety": "A custom init.c StartingEquipSetup flow can override or conflict with this system. Keep quantities, health and attachments structurally valid and test on a new character.",
    },
    "restricted_area": {
        "purpose": "Player-restricted area with safe relocation positions.",
        "dependencies": ["Add the JSON file path to WorldsData.playerRestrictedAreaFiles in cfggameplay.json."],
        "variants": "A restricted-area file uses areaName, PRABoxes of [size, orientation, position] triples and safePositions3D coordinate triples.",
        "safety": "Y height is important for both box placement and safe positions. Do not use comments inside JSON.",
    },
    "cfgeffectarea.json": {
        "purpose": "Map effect areas such as contaminated areas and map-specific effects.",
        "dependencies": ["cfgareaeffects.xml may define related effect presets for the selected mission."],
        "variants": "The Area schema varies by map and version (for example particle/contaminated areas versus Sakhal geyser and volcanic area data). Empty {} is the documented way to disable static areas on installations that support it.",
        "safety": "Never convert one map's area schema into another map's schema. Preserve the current map's fields and validate every coordinate vector.",
    },
    "cfgundergroundtriggers.json": {
        "purpose": "Underground darkness, transition and ambient-sound trigger configuration.",
        "dependencies": ["Triggers can include Breadcrumbs for gradual eye-accommodation transitions."],
        "variants": "Current vanilla trigger records use Position, Orientation, Size, EyeAccommodation, optional InterpolationSpeed/AmbientSoundSet and Breadcrumbs.",
        "safety": "JSON comments are invalid. Preserve map-specific trigger behaviour and use actual underground Y coordinates.",
    },
    "events.xml": {
        "purpose": "Central Economy event definitions.",
        "dependencies": ["cfgeventspawns.xml position records must use the same event name.", "Object/item class names must exist in the matching DayZ version."],
        "variants": "Vehicle, Static, Loot, Item, Infected and Animal events have different CE semantics; choose the appropriate current event pattern.",
        "safety": "Treat a linked event package as multiple files. Merge named records instead of replacing a live events.xml.",
    },
    "types.xml": {
        "purpose": "Central Economy item quantities, lifetime, restock, tiers, categories, usages and flags.",
        "dependencies": ["cfgspawnabletypes.xml controls spawned attachments/cargo.", "cfglimitsdefinition XML and map group prototypes must agree on categories/usages."],
        "variants": "Use the matching vanilla class name and selected map/version item record as the base.",
        "safety": "Never guess classnames or mass-rewrite loot. Explain the impact of nominal/min/restock/lifetime before changing it.",
    },
    "cfgspawnabletypes.xml": {
        "purpose": "Central Economy attachments, cargo, presets, nested item content, quantity and damage behaviour.",
        "dependencies": ["types.xml determines whether and how the parent item enters the loot economy."],
        "variants": "Nested cargo and attachment structures are supported in modern DayZ; preserve the current schema and use matching item class names.",
        "safety": "Do not confuse attachment/cargo definitions with types.xml nominal world-loot settings.",
    },
    "territories": {
        "purpose": "Animal and infected spawn zone definitions.",
        "dependencies": ["cfgenvironment.xml references the relevant environment territory files."],
        "variants": "Territory records can use dynamic/static minimums and maximums; herd and behaviour fields vary by animal file.",
        "safety": "Use map coordinates and conservative population values. A very large static infected count can affect performance.",
    },
    "init.c": {
        "purpose": "Enforce Script mission entry point and optional script-driven behaviour.",
        "dependencies": ["May control weather, custom spawning, loadouts or mod hooks."],
        "variants": "There is no universal mod init.c. Vanilla ObjectSpawner, scripted SpawnObject calls and mod frameworks have different flows.",
        "safety": "Require the current complete init.c and exact mod/version before writing changes; always server-side test scripts.",
    },
}


def dayz_custom_json_path(target_path: Any) -> str:
    """Return a safe custom/pra relative JSON path or an empty string."""
    raw = str(target_path or "").replace("\\", "/").strip()
    absolute_mission_path = raw.startswith("/") or bool(re.match(r"^[A-Za-z]:/", raw))
    while raw.startswith("./"):
        raw = raw[2:]
    raw = raw.lstrip("/")
    if not raw or len(raw) > 220 or not raw.lower().endswith(".json"):
        return ""
    parts = raw.split("/")
    folder_index = 0 if parts and parts[0].lower() in {"custom", "pra"} else -1
    if folder_index < 0 and absolute_mission_path:
        folder_index = next((index for index, part in enumerate(parts) if part.lower() in {"custom", "pra"}), -1)
    if folder_index < 0 or len(parts) - folder_index < 2:
        return ""
    parts = parts[folder_index:]
    if any(not part or part in {".", ".."} for part in parts):
        return ""
    filename = parts[-1]
    if filename.lower() in {".json", "..json"}:
        return ""
    return "/".join(parts)


def dayz_is_supported_custom_json_path(target_path: Any) -> bool:
    return bool(dayz_custom_json_path(target_path))


def dayz_filename_for_path(target_path: Any) -> str:
    filename = os.path.basename(str(target_path or "").replace("\\", "/")).lower()
    match = BACKUP_SUFFIX_RE.match(filename)
    if match:
        return match.group("filename").lower()
    return filename


def dayz_is_backup_path(target_path: Any) -> bool:
    filename = os.path.basename(str(target_path or "").replace("\\", "/")).lower()
    return bool(BACKUP_SUFFIX_RE.match(filename))


def dayz_file_spec_for_path(target_path: Any) -> DayZFileSpec | None:
    filename = dayz_filename_for_path(target_path)
    spec = DAYZ_FILE_SPECS.get(filename)
    if spec:
        return spec
    if filename.endswith("_territories.xml"):
        return DAYZ_TERRITORY_FILE_SPEC
    if dayz_is_supported_custom_json_path(target_path):
        return DAYZ_CUSTOM_JSON_FILE_SPEC
    return None


def dayz_xml_root_for_path(target_path: Any) -> str:
    spec = dayz_file_spec_for_path(target_path)
    return spec.xml_root if spec and spec.kind == "xml" else ""


def dayz_agent_file_knowledge(target_path: Any) -> dict[str, Any]:
    """Return compact, relevant DayZ guidance for a protected file target."""
    filename = dayz_filename_for_path(target_path)
    key = filename
    if filename.endswith("_territories.xml"):
        key = "territories"
    elif dayz_is_supported_custom_json_path(target_path):
        key = "custom_json"
    if key == "custom_json":
        return {
            "purpose": "A new custom DayZ JSON file under custom/ or pra/.",
            "known_schemas": ["ObjectSpawner", "spawning gear", "player restricted area", "effect area", "underground triggers"],
            "safety": "Create a complete file only for a recognised vanilla schema. For a mod-specific JSON file, request the exact mod/version and its current config before drafting.",
            "official_sources": [
                "https://community.bistudio.com/wiki/DayZ:Object_Spawner",
                "https://community.bistudio.com/wiki/DayZ:Gameplay_Settings",
                "https://community.bistudio.com/wiki/DayZ:Spawning_Gear_Configuration",
            ],
        }
    guidance = dict(DAYZ_AGENT_FILE_KNOWLEDGE.get(key) or {})
    if guidance:
        guidance["official_sources"] = [
            "https://community.bistudio.com/wiki/DayZ:Central_Economy_Configuration",
            "https://community.bistudio.com/wiki/DayZ:Gameplay_Settings",
            "https://community.bistudio.com/wiki/DayZ:Weather_Configuration",
        ]
    return guidance


def _json_root_type(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return type(value).__name__


def _xml_text_without_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", str(text or ""), flags=re.DOTALL)


def _parse_dayz_xml(text: str) -> ET.Element:
    return ET.fromstring(_xml_text_without_comments(text).encode("utf-8"))


def validate_named_xml_upload_preserves_existing(
    target_path: Any,
    existing_text: Any,
    upload_text: Any,
    *,
    allowed_removed_names: set[str] | None = None,
    max_removed_names: int = 0,
) -> tuple[bool, str]:
    """Block protected XML uploads that would remove existing named records.

    This is intentionally stricter than XML shape validation. A valid
    ``events.xml`` with only one event is still dangerous if the live server
    file had hundreds of event definitions before the upload.
    """

    spec = dayz_file_spec_for_path(target_path)
    if not spec or spec.kind != "xml" or not spec.required_children or dayz_is_backup_path(target_path):
        return True, ""

    existing = str(existing_text or "").strip()
    upload = str(upload_text or "").strip()
    if not existing or not upload:
        return True, ""

    try:
        existing_root = _parse_dayz_xml(existing)
        upload_root = _parse_dayz_xml(upload)
    except Exception as error:
        return False, f"Refusing to upload `{target_path}`: could not compare existing XML records before upload: {error}"

    if existing_root.tag != upload_root.tag or existing_root.tag != spec.xml_root:
        return True, ""

    child_tag = spec.required_children[0]

    def named_children(root: ET.Element) -> set[str]:
        return {
            str(node.get("name") or "").strip()
            for node in root.findall(child_tag)
            if str(node.get("name") or "").strip()
        }

    existing_names = named_children(existing_root)
    upload_names = named_children(upload_root)
    if not existing_names or not upload_names:
        return True, ""

    allowed = {str(name or "").strip().lower() for name in (allowed_removed_names or set()) if str(name or "").strip()}
    removed = sorted(
        name
        for name in existing_names - upload_names
        if name.lower() not in allowed
    )
    if len(removed) <= max(0, int(max_removed_names or 0)):
        return True, ""

    sample = ", ".join(f"`{name}`" for name in removed[:8])
    if len(removed) > 8:
        sample += f", +{len(removed) - 8} more"
    return False, (
        f"Refusing to upload `{target_path}`: upload would remove `{len(removed)}` existing "
        f"<{child_tag} name=...> record(s): {sample}. This guard prevents Wandering Bot from "
        "emptying or replacing live CE files; merge only WanderingBot-managed records instead."
    )


def validate_upload_not_dangerously_shrunken(
    target_path: Any,
    existing_text: Any,
    upload_text: Any,
    *,
    min_existing_bytes: int = 2048,
    max_shrink_ratio: float = 0.35,
) -> tuple[bool, str]:
    """Block replacing a real live DayZ file with a tiny/gutted upload."""

    spec = dayz_file_spec_for_path(target_path)
    if not spec or dayz_is_backup_path(target_path):
        return True, ""

    existing = str(existing_text or "")
    upload = str(upload_text or "")
    existing_bytes = len(existing.encode("utf-8", errors="ignore"))
    upload_bytes = len(upload.encode("utf-8", errors="ignore"))
    if existing_bytes < max(1, int(min_existing_bytes or 0)):
        return True, ""
    if upload_bytes == 0:
        return False, (
            f"Refusing to upload `{target_path}`: upload content is 0 bytes while the live file "
            f"backup is {existing_bytes} bytes."
        )
    if upload_bytes >= int(existing_bytes * float(max_shrink_ratio or 0)):
        return True, ""
    return False, (
        f"Refusing to upload `{target_path}`: upload is only {upload_bytes} bytes, but the live "
        f"file backup is {existing_bytes} bytes. This looks like a destructive empty/truncated "
        "upload, so Wandering Bot stopped it."
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_number_triplet(value: Any, label: str) -> str:
    if not isinstance(value, list) or len(value) != 3 or not all(_is_number(item) for item in value):
        return f"{label} must be an array of 3 numbers."
    return ""


def _validate_object_spawner_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"Refusing to upload `{target_path}`: object spawner JSON root must be an object."
    objects = payload.get("Objects")
    if not isinstance(objects, list):
        return False, f"Refusing to upload `{target_path}`: object spawner JSON must contain an `Objects` array."
    for index, item in enumerate(objects[:5000]):
        if not isinstance(item, dict):
            return False, f"Refusing to upload `{target_path}`: Objects[{index}] must be an object."
        if not str(item.get("name") or "").strip():
            return False, f"Refusing to upload `{target_path}`: Objects[{index}] is missing `name`."
        class_name = str(item.get("name") or "").strip()
        class_key = re.sub(r"[^a-z0-9]+", "", class_name.lower())
        if class_key in DAYZ_UNSAFE_OBJECT_SPAWNER_CLASS_KEYS:
            return False, (
                f"Refusing to upload `{target_path}`: Objects[{index}] uses unsafe weapon class "
                f"`{class_name}`. Put weapons in CE loot/types, not ObjectSpawner JSON."
            )
        pos_error = _validate_number_triplet(item.get("pos"), f"Objects[{index}].pos")
        if pos_error:
            return False, f"Refusing to upload `{target_path}`: {pos_error}"
        if "ypr" in item:
            ypr_error = _validate_number_triplet(item.get("ypr"), f"Objects[{index}].ypr")
            if ypr_error:
                return False, f"Refusing to upload `{target_path}`: {ypr_error}"
        if "scale" in item and not _is_number(item.get("scale")):
            return False, f"Refusing to upload `{target_path}`: Objects[{index}].scale must be a number."
    return True, ""


def dayz_object_spawner_ref_is_blocked(value: Any) -> bool:
    filename = os.path.basename(str(value or "").replace("\\", "/")).lower()
    return filename in DAYZ_BLOCKED_OBJECT_SPAWNER_REF_FILENAMES


def _validate_string_path_list(value: Any, label: str, target_path: Any) -> tuple[bool, str]:
    if not isinstance(value, list):
        return False, f"Refusing to upload `{target_path}`: {label} must be an array."
    if not all(isinstance(item, str) and item.strip() for item in value):
        return False, f"Refusing to upload `{target_path}`: {label} must contain non-empty string paths."
    return True, ""


def _validate_restricted_area_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"Refusing to upload `{target_path}`: restricted-area JSON root must be an object."
    boxes = payload.get("PRABoxes")
    safe_positions = payload.get("safePositions3D")
    if not isinstance(boxes, list) or not boxes:
        return False, f"Refusing to upload `{target_path}`: restricted-area JSON needs a non-empty `PRABoxes` array."
    if not isinstance(safe_positions, list) or not safe_positions:
        return False, f"Refusing to upload `{target_path}`: restricted-area JSON needs a non-empty `safePositions3D` array."
    for index, box in enumerate(boxes):
        if not isinstance(box, list) or len(box) != 3:
            return False, f"Refusing to upload `{target_path}`: PRABoxes[{index}] must contain size, orientation and position triples."
        for part_index, part_label in enumerate(("size", "orientation", "position")):
            error = _validate_number_triplet(box[part_index], f"PRABoxes[{index}].{part_label}")
            if error:
                return False, f"Refusing to upload `{target_path}`: {error}"
    for index, position in enumerate(safe_positions):
        error = _validate_number_triplet(position, f"safePositions3D[{index}]")
        if error:
            return False, f"Refusing to upload `{target_path}`: {error}"
    return True, ""


def _validate_effect_area_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"Refusing to upload `{target_path}`: effect-area JSON root must be an object."
    # An empty object is a documented way to disable static areas for
    # applicable DayZ installations. A live replacement is still protected by
    # the separate destructive-shrink guard.
    if not payload:
        return True, ""
    areas = payload.get("Areas")
    if not isinstance(areas, list):
        return False, f"Refusing to upload `{target_path}`: effect-area JSON must contain an `Areas` array (or be {{}} to disable static areas)."
    for index, area in enumerate(areas):
        if not isinstance(area, dict):
            return False, f"Refusing to upload `{target_path}`: Areas[{index}] must be an object."
        data = area.get("Data") if isinstance(area.get("Data"), dict) else area
        for position_key in ("Pos", "Position"):
            if position_key in data:
                error = _validate_number_triplet(data.get(position_key), f"Areas[{index}].{position_key}")
                if error:
                    return False, f"Refusing to upload `{target_path}`: {error}"
                break
        for radius_key in ("Radius", "OuterRingRadius", "InnerRingRadius"):
            if radius_key in data and not _is_number(data.get(radius_key)):
                return False, f"Refusing to upload `{target_path}`: Areas[{index}].{radius_key} must be a number."
    return True, ""


def _validate_underground_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"Refusing to upload `{target_path}`: underground-trigger JSON root must be an object."
    triggers = payload.get("Triggers")
    if not isinstance(triggers, list):
        return False, f"Refusing to upload `{target_path}`: underground-trigger JSON must contain a `Triggers` array."
    for index, trigger in enumerate(triggers):
        if not isinstance(trigger, dict):
            return False, f"Refusing to upload `{target_path}`: Triggers[{index}] must be an object."
        for vector_key in ("Position", "Orientation", "Size"):
            if vector_key in trigger:
                error = _validate_number_triplet(trigger.get(vector_key), f"Triggers[{index}].{vector_key}")
                if error:
                    return False, f"Refusing to upload `{target_path}`: {error}"
        breadcrumbs = trigger.get("Breadcrumbs", [])
        if not isinstance(breadcrumbs, list):
            return False, f"Refusing to upload `{target_path}`: Triggers[{index}].Breadcrumbs must be an array."
        for breadcrumb_index, breadcrumb in enumerate(breadcrumbs):
            if not isinstance(breadcrumb, dict):
                return False, f"Refusing to upload `{target_path}`: Triggers[{index}].Breadcrumbs[{breadcrumb_index}] must be an object."
            if "Position" in breadcrumb:
                error = _validate_number_triplet(breadcrumb.get("Position"), f"Triggers[{index}].Breadcrumbs[{breadcrumb_index}].Position")
                if error:
                    return False, f"Refusing to upload `{target_path}`: {error}"
    return True, ""


def _validate_spawn_gear_preset_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    presets = payload if isinstance(payload, list) else [payload]
    if not presets or not all(isinstance(preset, dict) for preset in presets):
        return False, f"Refusing to upload `{target_path}`: spawning-gear JSON must be an object or array of objects."
    for index, preset in enumerate(presets):
        if not any(key in preset for key in ("spawnWeight", "attachmentSlotItemSets", "discreteUnsortedItemSets", "discreteItemSets")):
            return False, f"Refusing to upload `{target_path}`: spawning-gear preset {index} has no recognised gear fields."
        if "spawnWeight" in preset and not _is_number(preset.get("spawnWeight")):
            return False, f"Refusing to upload `{target_path}`: spawning-gear preset {index}.spawnWeight must be a number."
        for key in ("characterTypes", "attachmentSlotItemSets", "discreteUnsortedItemSets", "discreteItemSets"):
            if key in preset and not isinstance(preset.get(key), list):
                return False, f"Refusing to upload `{target_path}`: spawning-gear preset {index}.{key} must be an array."
    return True, ""


def dayz_json_schema_name(payload: Any) -> str:
    """Identify supported vanilla/custom JSON shapes without guessing mod schemas."""
    if isinstance(payload, dict):
        if "Objects" in payload:
            return "objectspawner"
        if "PRABoxes" in payload or "safePositions3D" in payload:
            return "restricted_area"
        if "Areas" in payload:
            return "effect_area"
        if "Triggers" in payload:
            return "underground"
        if any(key in payload for key in ("spawnWeight", "attachmentSlotItemSets", "discreteUnsortedItemSets", "discreteItemSets")):
            return "spawning_gear"
    if isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
        if all(any(key in item for key in ("spawnWeight", "attachmentSlotItemSets", "discreteUnsortedItemSets", "discreteItemSets")) for item in payload):
            return "spawning_gear"
    return ""


def _validate_known_dayz_json_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    schema = dayz_json_schema_name(payload)
    if schema == "objectspawner":
        return _validate_object_spawner_payload(payload, target_path)
    if schema == "restricted_area":
        return _validate_restricted_area_payload(payload, target_path)
    if schema == "effect_area":
        return _validate_effect_area_payload(payload, target_path)
    if schema == "underground":
        return _validate_underground_payload(payload, target_path)
    if schema == "spawning_gear":
        return _validate_spawn_gear_preset_payload(payload, target_path)
    return False, (
        f"Refusing to upload `{target_path}`: custom DayZ JSON must use a recognised ObjectSpawner, spawning-gear, "
        "restricted-area, effect-area or underground-trigger structure. Supply the exact current mod config for other schemas."
    )


def _validate_cfggameplay_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"Refusing to upload `{target_path}`: cfggameplay.json root must be an object."
    worlds = payload.get("WorldsData")
    if worlds is not None:
        if not isinstance(worlds, dict):
            return False, f"Refusing to upload `{target_path}`: WorldsData must be an object."
        spawners = worlds.get("objectSpawnersArr")
        if spawners is not None:
            valid, message = _validate_string_path_list(spawners, "WorldsData.objectSpawnersArr", target_path)
            if not valid:
                return valid, message
        for item in spawners or []:
            if dayz_object_spawner_ref_is_blocked(item):
                return False, (
                    f"Refusing to upload `{target_path}`: WorldsData.objectSpawnersArr still references "
                    f"`{item}`, which is a known crash-causing stale object-spawner file."
                )
        restricted_areas = worlds.get("playerRestrictedAreaFiles")
        if restricted_areas is not None:
            valid, message = _validate_string_path_list(restricted_areas, "WorldsData.playerRestrictedAreaFiles", target_path)
            if not valid:
                return valid, message
    player = payload.get("PlayerData")
    if player is not None:
        if not isinstance(player, dict):
            return False, f"Refusing to upload `{target_path}`: PlayerData must be an object."
        presets = player.get("spawnGearPresetFiles")
        if presets is not None:
            valid, message = _validate_string_path_list(presets, "PlayerData.spawnGearPresetFiles", target_path)
            if not valid:
                return valid, message
    return True, ""


def _validate_cfgweather_xml(root: ET.Element, target_path: Any) -> tuple[bool, str]:
    """Validate modern vanilla weather and documented compact/legacy layouts.

    DayZ's documentation permits a compact file and values expressed either as
    attributes or nested elements. Modern files are still kept strict: if any
    modern-only section appears, all sections from the selected 1.29 layout
    must be present. A tiny compact file cannot overwrite a real full live
    file because the separate shrink guard stops it.
    """
    modern_sections = {
        "overcast": ("current", "limits", "timelimits", "changelimits"),
        "fog": ("current", "limits", "timelimits", "changelimits"),
        "rain": ("current", "limits", "timelimits", "changelimits", "thresholds"),
        "windMagnitude": ("current", "limits", "timelimits", "changelimits"),
        "windDirection": ("current", "limits", "timelimits", "changelimits"),
        "snowfall": ("current", "limits", "timelimits", "changelimits", "thresholds"),
    }
    has_modern_only_section = any(root.find(name) is not None for name in ("windMagnitude", "windDirection", "snowfall"))
    if has_modern_only_section:
        for section_name, child_names in modern_sections.items():
            section = root.find(section_name)
            if section is None:
                return False, f"Refusing to upload `{target_path}`: modern cfgweather.xml is missing <{section_name}>."
            for child_name in child_names:
                if section.find(child_name) is None:
                    return False, f"Refusing to upload `{target_path}`: cfgweather.xml is missing <{section_name}><{child_name}>."
        if root.find("storm") is None:
            return False, f"Refusing to upload `{target_path}`: modern cfgweather.xml is missing <storm>."
    elif not any(root.find(name) is not None for name in ("overcast", "fog", "rain", "wind", "storm")):
        return False, f"Refusing to upload `{target_path}`: cfgweather.xml has no weather section to configure."

    def child_value(element: ET.Element | None, name: str) -> Any:
        if element is None:
            return None
        if element.get(name) is not None:
            return element.get(name)
        child = element.find(name)
        return child.text if child is not None else None

    def validate_probability(section_name: str, child_name: str, fields: tuple[str, ...]) -> tuple[bool, str]:
        section = root.find(section_name)
        if section is None:
            return True, ""
        child = section.find(child_name)
        if child is None:
            return True, ""
        for field in fields:
            raw_value = child_value(child, field)
            if raw_value is None:
                if has_modern_only_section:
                    return False, f"Refusing to upload `{target_path}`: <{section_name}><{child_name}> needs `{field}`."
                continue
            try:
                value = float(str(raw_value))
            except (TypeError, ValueError):
                return False, f"Refusing to upload `{target_path}`: <{section_name}><{child_name}> needs numeric `{field}`."
            if not 0.0 <= value <= 1.0:
                return False, f"Refusing to upload `{target_path}`: <{section_name}><{child_name}> `{field}` must be between 0 and 1."
        return True, ""

    for section_name in ("overcast", "fog", "rain", "snowfall"):
        for child_name, fields in (("current", ("actual",)), ("limits", ("min", "max")), ("changelimits", ("min", "max")), ("thresholds", ("min", "max"))):
            valid, message = validate_probability(section_name, child_name, fields)
            if not valid:
                return valid, message

    storm = root.find("storm")
    if storm is not None:
        for field in ("density", "threshold"):
            raw_value = child_value(storm, field)
            if raw_value is None:
                if has_modern_only_section:
                    return False, f"Refusing to upload `{target_path}`: <storm> needs `{field}`."
                continue
            try:
                value = float(str(raw_value))
            except (TypeError, ValueError):
                return False, f"Refusing to upload `{target_path}`: <storm> needs numeric `{field}`."
            if not 0.0 <= value <= 1.0:
                return False, f"Refusing to upload `{target_path}`: <storm> `{field}` must be between 0 and 1."
    wind = root.find("wind")
    if wind is not None:
        raw_maxspeed = child_value(wind, "maxspeed")
        if raw_maxspeed is not None:
            try:
                if float(str(raw_maxspeed)) < 0:
                    return False, f"Refusing to upload `{target_path}`: <wind> maxspeed cannot be negative."
            except (TypeError, ValueError):
                return False, f"Refusing to upload `{target_path}`: <wind> maxspeed must be numeric."
    return True, ""


def validate_dayz_upload_text(target_path: Any, text_content: Any) -> tuple[bool, str]:
    """Validate known DayZ XML/JSON files before upload.

    Unknown ``*.xml`` and ``*.json`` files are still parsed so dashboard/custom
    uploads cannot silently write malformed structured files. Unknown non-XML
    and non-JSON files are left alone.
    """

    filename = dayz_filename_for_path(target_path)
    spec = dayz_file_spec_for_path(target_path)
    extension = os.path.splitext(filename)[1].lower()
    text = str(text_content or "")

    if not text.strip() and (spec or extension in {".xml", ".json"}):
        return False, f"Refusing to upload empty `{os.path.basename(str(target_path or 'file'))}` to `{target_path}`."

    if spec and spec.kind == "xml":
        try:
            root = _parse_dayz_xml(text)
        except Exception as error:
            return False, f"Refusing to upload invalid XML to `{target_path}`: {error}"
        if root.tag != spec.xml_root:
            return False, f"Refusing to upload `{target_path}`: expected <{spec.xml_root}> root, got <{root.tag}>."
        if spec.required_children and not dayz_is_backup_path(target_path):
            if not any(root.findall(child_name) for child_name in spec.required_children):
                child_text = " or ".join(f"<{child}>" for child in spec.required_children)
                return False, (
                    f"Refusing to upload `{target_path}`: <{spec.xml_root}> has no {child_text} "
                    "records, which looks like an empty/minimal live file."
                )
        if filename == "cfgweather.xml":
            return _validate_cfgweather_xml(root, target_path)
        return True, ""

    if spec and spec.kind == "json":
        try:
            payload = json.loads(text)
        except Exception as error:
            return False, f"Refusing to upload invalid JSON to `{target_path}`: {error}"
        root_type = _json_root_type(payload)
        if spec.json_root_types and root_type not in spec.json_root_types:
            allowed = ", ".join(spec.json_root_types)
            return False, f"Refusing to upload `{target_path}`: expected JSON root {allowed}, got {root_type}."
        if filename == "cfggameplay.json":
            return _validate_cfggameplay_payload(payload, target_path)
        if filename == "objectspawner.json":
            return _validate_object_spawner_payload(payload, target_path)
        if filename == "cfgeffectarea.json":
            return _validate_effect_area_payload(payload, target_path)
        if filename == "cfgundergroundtriggers.json":
            return _validate_underground_payload(payload, target_path)
        if spec == DAYZ_CUSTOM_JSON_FILE_SPEC:
            return _validate_known_dayz_json_payload(payload, target_path)
        return True, ""

    if extension == ".xml":
        try:
            _parse_dayz_xml(text)
        except Exception as error:
            return False, f"Refusing to upload invalid XML to `{target_path}`: {error}"
        return True, ""

    if extension == ".json":
        try:
            payload = json.loads(text)
        except Exception as error:
            return False, f"Refusing to upload invalid JSON to `{target_path}`: {error}"
        if isinstance(payload, dict) and "Objects" in payload:
            return _validate_object_spawner_payload(payload, target_path)
        return True, ""

    return True, ""
