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
    "events.xml": DayZFileSpec("events.xml", "xml", "events", ("event",), description="CE event definitions"),
    "cfgeventspawns.xml": DayZFileSpec("cfgeventspawns.xml", "xml", "eventposdef", ("event",), description="CE event positions"),
    "cfgeventgroups.xml": DayZFileSpec("cfgeventgroups.xml", "xml", "eventgroupdef", ("group",), description="CE static event groups"),
    "mapgroupproto.xml": DayZFileSpec("mapgroupproto.xml", "xml", "prototype", ("group",), description="CE map group loot prototypes"),
    "cfgspawnabletypes.xml": DayZFileSpec("cfgspawnabletypes.xml", "xml", "spawnabletypes", ("type",), description="attachments and cargo"),
    "cfgenvironment.xml": DayZFileSpec("cfgenvironment.xml", "xml", "env", description="environment/territory references"),
    "cfgareaeffects.xml": DayZFileSpec("cfgareaeffects.xml", "xml", "areaeffects", description="contaminated area presets"),
    "messages.xml": DayZFileSpec("messages.xml", "xml", "messages", description="server messages"),
    "types.xml": DayZFileSpec("types.xml", "xml", "types", ("type",), description="loot economy types"),
    "globals.xml": DayZFileSpec("globals.xml", "xml", "variables", ("var",), description="global economy variables"),
    "economy.xml": DayZFileSpec("economy.xml", "xml", "economy", description="central economy switches"),
    "cfgeconomycore.xml": DayZFileSpec("cfgeconomycore.xml", "xml", "economycore", description="economy file includes"),
    "cfggameplay.json": DayZFileSpec("cfggameplay.json", "json", json_root_types=("object",), description="gameplay flags and object spawner references"),
    "cfgeffectarea.json": DayZFileSpec("cfgeffectarea.json", "json", json_root_types=("object",), description="gas particle settings"),
    "cfgplayerspawn.json": DayZFileSpec("cfgplayerspawn.json", "json", json_root_types=("object",), description="fresh spawn loadouts"),
}


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
    return DAYZ_FILE_SPECS.get(dayz_filename_for_path(target_path))


def dayz_xml_root_for_path(target_path: Any) -> str:
    spec = dayz_file_spec_for_path(target_path)
    return spec.xml_root if spec and spec.kind == "xml" else ""


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


def _validate_cfggameplay_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"Refusing to upload `{target_path}`: cfggameplay.json root must be an object."
    worlds = payload.get("WorldsData")
    if worlds is not None:
        if not isinstance(worlds, dict):
            return False, f"Refusing to upload `{target_path}`: WorldsData must be an object."
        spawners = worlds.get("objectSpawnersArr")
        if spawners is not None and not isinstance(spawners, list):
            return False, f"Refusing to upload `{target_path}`: WorldsData.objectSpawnersArr must be an array."
        if spawners is not None and not all(isinstance(item, str) and item.strip() for item in spawners):
            return False, f"Refusing to upload `{target_path}`: WorldsData.objectSpawnersArr must contain string paths."
    player = payload.get("PlayerData")
    if player is not None:
        if not isinstance(player, dict):
            return False, f"Refusing to upload `{target_path}`: PlayerData must be an object."
        presets = player.get("spawnGearPresetFiles")
        if presets is not None and not isinstance(presets, list):
            return False, f"Refusing to upload `{target_path}`: PlayerData.spawnGearPresetFiles must be an array."
        if presets is not None and not all(isinstance(item, str) and item.strip() for item in presets):
            return False, f"Refusing to upload `{target_path}`: PlayerData.spawnGearPresetFiles must contain string paths."
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
