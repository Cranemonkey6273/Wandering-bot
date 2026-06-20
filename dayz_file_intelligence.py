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
            root = ET.fromstring(text.encode("utf-8"))
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
        return True, ""

    if extension == ".xml":
        try:
            ET.fromstring(text.encode("utf-8"))
        except Exception as error:
            return False, f"Refusing to upload invalid XML to `{target_path}`: {error}"
        return True, ""

    if extension == ".json":
        try:
            json.loads(text)
        except Exception as error:
            return False, f"Refusing to upload invalid JSON to `{target_path}`: {error}"
        return True, ""

    return True, ""
