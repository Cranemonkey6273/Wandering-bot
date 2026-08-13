"""Shared DayZ file layout and upload validation helpers.

This module is the central registry for vanilla/custom DayZ file shapes that
Wandering Bot is allowed to read, merge, or upload. Keep file-specific roots
and JSON expectations here so bot and dashboard upload paths use the same
guardrails.
"""

from __future__ import annotations

import json
import math
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
    "messages.xml": DayZFileSpec("messages.xml", "xml", "messages", description="server messages"),
    "cfgplayerspawnpoints.xml": DayZFileSpec("cfgplayerspawnpoints.xml", "xml", "playerspawnpoints", ("fresh",), description="fresh-spawn positions and loadout settings"),
    "cfgignorelist.xml": DayZFileSpec("cfgignorelist.xml", "xml", "ignore", ("type",), description="economy cleanup ignore list"),
    "cfglimitsdefinition.xml": DayZFileSpec("cfglimitsdefinition.xml", "xml", "lists", description="central economy category, tag and usage lists"),
    "cfglimitsdefinitionuser.xml": DayZFileSpec("cfglimitsdefinitionuser.xml", "xml", "user_lists", description="user aliases combining existing CE usage/value definitions"),
    "cfgrandompresets.xml": DayZFileSpec("cfgrandompresets.xml", "xml", "randompresets", description="central economy random cargo presets"),
    "types.xml": DayZFileSpec("types.xml", "xml", "types", ("type",), description="loot economy types"),
    "globals.xml": DayZFileSpec("globals.xml", "xml", "variables", ("var",), description="global economy variables"),
    "economy.xml": DayZFileSpec("economy.xml", "xml", "economy", description="central economy switches"),
    "cfgeconomycore.xml": DayZFileSpec("cfgeconomycore.xml", "xml", "economycore", description="economy file includes"),
    "cfgweather.xml": DayZFileSpec("cfgweather.xml", "xml", "weather", description="weather, rain, fog and storm settings"),
    "cfggameplay.json": DayZFileSpec("cfggameplay.json", "json", json_root_types=("object",), description="gameplay flags and object spawner references"),
    "cfgundergroundtriggers.json": DayZFileSpec("cfgundergroundtriggers.json", "json", json_root_types=("object",), description="underground area trigger settings"),
    "cfgeffectarea.json": DayZFileSpec("cfgeffectarea.json", "json", json_root_types=("object",), description="static contaminated and map effect areas"),
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
        "dependencies": [
            "Add the JSON file path to WorldsData.objectSpawnersArr in cfggameplay.json.",
            "A separate cfgEffectArea.json can provide static smoke, contamination or visual effects near the scene; it is not linked through objectSpawnersArr.",
        ],
        "variants": "Objects use name, pos [x,y,z], optional ypr [yaw,pitch,roll], optional scale and enabled fields. A static airdrop/staging scene is an ObjectSpawner placement; a dynamic repeatable CE airdrop instead needs events.xml and cfgeventspawns.xml. Use the current file for any extra fields.",
        "safety": "Do not use ObjectSpawner for weapon loot or call a static scene a dynamic CE event. Confirm classnames and true terrain height; test a small placement batch first.",
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
        "dependencies": [
            "Dynamic contaminated areas are Central Economy events and use events.xml plus cfgeventspawns.xml rather than a companion area-effects XML file.",
            "An adjacent ObjectSpawner build remains a separate custom JSON file that must be linked in cfggameplay.json; do not add cfgEffectArea.json to objectSpawnersArr.",
        ],
        "variants": "The Area schema varies by map and version (for example particle/contaminated areas versus Sakhal geyser and volcanic area data). Static smoke around an airdrop scene can coexist with its ObjectSpawner file, but it is not a substitute for a dynamic CE airdrop event. Empty {} is the documented way to disable static areas on installations that support it.",
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
        "dependencies": [
            "cfgeventspawns.xml position records must use the same event name.",
            "Item/vehicle/infected/animal child classnames should be checked against the selected version's types.xml; a Static scene child can instead be an engine/static object whose supporting prototype or exact source must be verified.",
        ],
        "variants": "Vehicle, Static, Loot, Item, Infected and Animal events have different CE semantics; choose the appropriate current event pattern.",
        "safety": "Treat a linked event package as multiple files. Merge named records instead of replacing a live events.xml.",
    },
    "cfgeventspawns.xml": {
        "purpose": "Central Economy event positions and optional named event-group references.",
        "dependencies": ["Each <event name=...> must exactly match a db/events.xml event name.", "A pos group=... reference must match a cfgeventgroups.xml group name."],
        "variants": "Direct vehicle, infected and animal events normally use positions without a group reference. Static scenes may use a group, depending on the selected vanilla pattern.",
        "safety": "Coordinates belong here, not in events.xml. Use X/Z map coordinates and a six-decimal rotation; do not add a group= attribute unless the matching group is present.",
    },
    "cfgeventgroups.xml": {
        "purpose": "Reusable Central Economy static event-group definitions.",
        "dependencies": ["Only needed when cfgeventspawns.xml uses a matching pos group=... reference.", "Loot-bearing child classes need compatible mapgroupproto.xml definitions and types/categories/usages."],
        "variants": "A group is not a mandatory fourth event file. Direct native vehicle, animal and infected events do not need a synthetic group.",
        "safety": "Keep every group name and child classname exact. Do not fabricate an event group just to make a package look complete.",
    },
    "mapgroupproto.xml": {
        "purpose": "Reusable map-group prototypes, including compatible CE loot points, categories, usages and tiers for static objects/buildings.",
        "dependencies": [
            "mapgrouppos.xml places a matching group on the selected map; its group name must match exactly.",
            "types.xml item categories/usages must be compatible with ordinary container loot rules, and every explicit dispatch/proxy classname must exist in the selected map/version.",
            "globals.xml LootProxyPlacement must permit dispatch containers when the proxy method is requested.",
            "cfglimitsdefinition.xml defines any genuinely new category, tag, usage or value name; cfglimitsdefinitionuser.xml can only alias existing usage/value names.",
        ],
        "variants": (
            "Ordinary building loot uses one or more <container> records containing <point pos=\"localX localY localZ\" range=\"...\" height=\"...\"/> candidates. "
            "The point position is a model-local X/Y/Z offset, not a world X/Z coordinate; moving local X or Z changes the point around that object's own origin and orientation. "
            "A multi-floor point still needs the correct local Y offset, while range/height describe its placement volume and should normally come from DayZ CE diagnostics/export rather than guesswork. "
            "A container/group lootmax is the maximum simultaneous loot assigned there, not a rule that it must equal every candidate point: vanilla groups commonly have more points than lootmax because each point can hold at most one item. "
            "The separate proxy method uses <dispatch><proxy type=\"Classname\" pos=\"localX localY localZ\" rpy=\"roll pitch yaw\"/></dispatch> for deliberately displayed CE items such as wall-mounted or elevated loot. "
            "For a fixed one-item-per-proxy custom layout, set the intended lootmax consistently with the number of active proxy items, while still comparing with the selected vanilla pattern. "
            "A fire/smoke scene can use proxy groups such as a Bonfire or smoke-producing wreck placed through matching MapGroupPos groups; this is a proxy-visual workflow, not cfgEffectArea.json."
        ),
        "safety": (
            "Do not confuse prototypes with world placements or ObjectSpawner JSON. Preserve existing groups and use a merge patch for one custom group. "
            "Confirm the object/model origin and orientation in game; local positive/negative directions rotate with the placed group, so a flat screen-grid description is only a starting guide. "
            "Fire/smoke proxy classes and their CE records vary by map/version. Bonfire and Wreck_UH1Y already have vanilla records in current bundled missions, so never overwrite them with example values without an explicit diff and user approval. "
            "Use DayZ CE Loot Spawn Edit / Spawn Volume Vis / Re-Trace Group Points for final point placement when those tools are available."
        ),
    },
    "mapgrouppos.xml": {
        "purpose": "Selected-map placements of map-group prototypes, including group name, position and rotation.",
        "dependencies": ["Each placement group must have an exactly named compatible mapgroupproto.xml prototype.", "A prototype's categories/usages or explicit proxy classnames ultimately need compatible types.xml records."],
        "variants": (
            "A placement pos contains world X, elevation/Y, Z in that order; rpy contains roll, pitch, yaw. "
            "The matching mapgroupproto point/proxy pos values are local X/Y/Z offsets from this placed group's origin. "
            "Use this for map-native group placement data. A custom JSON ObjectSpawner placement instead needs custom/<file>.json plus cfggameplay.json."
        ),
        "safety": "Do not copy a placement from another map or change a group name without its matching prototype. Confirm elevation, terrain, object orientation and map bounds before upload; ADM logs commonly display coordinates in a different X/Z/elevation order.",
    },
    "types.xml": {
        "purpose": "Central Economy item quantities, lifetime, restock, tiers, categories, usages and flags.",
        "dependencies": ["cfgspawnabletypes.xml controls spawned attachments/cargo.", "cfglimitsdefinition XML and map group prototypes must agree on categories/usages."],
        "variants": "Use the matching vanilla class name and selected map/version item record as the base.",
        "safety": "Never guess classnames or mass-rewrite loot. Explain the impact of nominal/min/restock/lifetime before changing it. A custom hidden category/usage can keep a proxy-only class out of ordinary loot, but existing vanilla records such as Bonfire or Wreck_UH1Y must be diffed rather than blindly replaced.",
    },
    "cfgspawnabletypes.xml": {
        "purpose": "Central Economy attachments, cargo, presets, nested item content, quantity and damage behaviour.",
        "dependencies": ["types.xml determines whether and how the parent item enters the loot economy."],
        "variants": "Nested cargo and attachment structures are supported in modern DayZ; preserve the current schema and use matching item class names.",
        "safety": "Do not confuse attachment/cargo definitions with types.xml nominal world-loot settings.",
    },
    "cfgignorelist.xml": {
        "purpose": "Excludes listed classnames from Central Economy persistence/storage handling; it is not a keep-forever cleanup whitelist.",
        "dependencies": ["Every <type name=...> must use the exact selected-version classname."],
        "variants": "The vanilla file contains <type name=\"Classname\"/> records under the <ignore> root.",
        "safety": "An ignored entity is not saved by CE and therefore may not return after restart. Adding a container here does not make it persist forever.",
    },
    "cfgeconomycore.xml": {
        "purpose": "Central Economy root configuration, persistence/backup settings and optional custom CE XML include folders.",
        "dependencies": ["The official custom CE include shape is <ce folder=\"foldername\"><file name=\"my_changes_to_types.xml\" type=\"types\" /></ce>; use the exact supported file type.", "Included partial files follow override/append rules rather than replacing the full vanilla mission file."],
        "variants": "The official mission-file modding schema uses a ce element with a folder attribute and nested file elements with name/type attributes. Core settings remain map/mission-specific.",
        "safety": "Do not use a partial include as a full-file replacement. Keep every file type and include path exact, then validate the resulting mission after restart.",
    },
    "globals.xml": {
        "purpose": "Global Central Economy limits and cleanup behaviour, including broader infected/animal and persistence-related limits.",
        "dependencies": ["Event and territory populations remain constrained by applicable global limits."],
        "variants": "Existing variable types are part of the schema and must be preserved; selected-map values may differ.",
        "safety": "A higher event/territory count will not override an incompatible global maximum. Change one scoped value at a time and measure server performance.",
    },
    "economy.xml": {
        "purpose": "Central Economy switches controlling initialisation, loading, respawning and saving for entity groups.",
        "dependencies": ["The enabled economy groups determine whether corresponding CE data can initialise, load, respawn and persist."],
        "variants": "Dynamic loot, animals, zombies, vehicles, custom objects, buildings and player data have separate switches.",
        "safety": "All flags for an edited economy element must be retained. Treat a persistence change as a server-wide behaviour change and back up first.",
    },
    "territories": {
        "purpose": "Animal and infected spawn zone definitions, including ambient living-entity zones.",
        "dependencies": ["cfgenvironment.xml references the relevant environment territory files.", "Ambient zones use a matching db/events.xml event family; that event's distance/cleanup/restock controls activation and cooldown behaviour."],
        "variants": "Territory records can use dynamic/static minimums and maximums; herd and behaviour fields vary by animal file. Ambient animals use territory dmin/dmax and event child min values as type weights. Copy the zone name from the selected map's matching vanilla territory file; do not derive a name such as BearPack from the animal name.",
        "safety": "Use map coordinates and conservative population values. A very large static infected count can affect performance. Do not use cfgeventspawns.xml for an ambient territory zone unless the selected vanilla pattern also has a separate fixed event.",
    },
    "cfglimitsdefinition.xml": {
        "purpose": "Central Economy category, tag and usage definitions used by types.xml and map-group loot rules.",
        "dependencies": ["types.xml and mapgroupproto.xml can only refer to category/usage/tag names that are defined for the mission."],
        "variants": "This <lists> file defines the actual category, tag, usage and value names. cfglimitsdefinitionuser.xml does not define new limiter names; it creates shorter named combinations from definitions that already exist here.",
        "safety": "Adding a new loot item does not automatically require a new category or usage. Add one only when the requested loot logic genuinely needs a new named definition.",
    },
    "cfglimitsdefinitionuser.xml": {
        "purpose": "Named user aliases that combine limiter flags already defined by cfglimitsdefinition.xml, such as TownVillage or Tier234.",
        "dependencies": ["Every nested usage/value name must already exist in cfglimitsdefinition.xml.", "Use cfglimitsdefinition.xml, not this file, to define a genuinely new category, tag, usage or value name."],
        "variants": "The vanilla <user_lists> layout contains <usageflags> and <valueflags>, each with named <user> groups and nested <usage> or <value> members.",
        "safety": "Do not put <category> or <tag> definitions here and do not invent nested limiter names that the selected mission has not defined.",
    },
    "cfgplayerspawnpoints.xml": {
        "purpose": "Fresh-spawn positions and selected spawn/loadout settings.",
        "dependencies": ["A JSON spawn-gear preset is separately referenced by PlayerData.spawnGearPresetFiles in cfggameplay.json."],
        "variants": "Spawn locations and gear are separate systems; do not treat cfgplayerspawnpoints.xml as a generic loadout JSON file.",
        "safety": "Use the selected map's spawn pattern and test with a new character. Do not put player inventory XML into map or CE files.",
    },
    "messages.xml": {
        "purpose": "Server on-screen message schedule and text.",
        "dependencies": ["No CE map/prototype dependency; validate it independently as a messages XML file."],
        "variants": "Message count, duration, colour and scheduler layout must follow the selected current/vanilla file.",
        "safety": "Keep user-facing text separate from XML markup and preserve existing message records when making a merge patch.",
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


def dayz_custom_json_path_from_text(value: Any) -> str:
    """Return the first explicit safe custom/pra JSON path in prose."""
    match = re.search(
        r"(?<![A-Za-z0-9_./-])(?:\./)?(?:custom|pra)/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.json(?![A-Za-z0-9_.-])",
        str(value or "").replace("\\", "/"),
        re.IGNORECASE,
    )
    return dayz_custom_json_path(match.group(0)) if match else ""


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


def dayz_dependency_plan_for_request(objective: Any, target_path: Any = "") -> dict[str, Any]:
    """Return the linked DayZ files a request must *consider* before drafting.

    This is an intentionally conservative planning layer, not an instruction to
    edit every listed file.  ``changed`` means the workflow normally needs that
    file, ``checked`` means it must be inspected for a named relationship, and
    ``conditional`` means it changes only when the supplied current file proves
    the relationship exists.  The distinction prevents an assistant from
    making up unrelated CE groups, map prototypes or gameplay references.
    """
    raw_path = str(target_path or "").replace("\\", "/").strip()
    filename = dayz_filename_for_path(raw_path)
    custom_path = dayz_custom_json_path(raw_path) or dayz_custom_json_path_from_text(objective)
    text = f"{objective or ''} {raw_path}".lower()

    def entry(path: str, action: str, reason: str) -> dict[str, str]:
        return {"path": path, "action": action, "reason": reason}

    def plan(workflow: str, summary: str, files: list[dict[str, str]], guard: str) -> dict[str, Any]:
        return {"workflow": workflow, "summary": summary, "files": files, "guard": guard}

    ambient_terms = ("ambient spawner", "ambient animal", "ambient hen", "ambient fox", "ambient wildlife")
    proxy_method_terms = (
        "proxy method", "dispatch proxy", "dispatch/proxy", "spawnable loot position",
        "spawn items anywhere", "wall mounted loot", "floating loot", "weapon on a wall",
    )
    fire_proxy_terms = (
        "fire effect", "smoke effect", "fire and smoke", "fire/smoke", "burning event",
        "burning scene", "mass grave fire", "mass grave smoke", "fireeffect", "helismoke",
    )
    map_group_terms = (
        "mapgrouppos", "mapgroupproto", "map group", "mapgroup", "loot point", "lootpoint",
        *proxy_method_terms,
    )
    object_spawner_terms = ("objectspawner", "object spawner", "spawnobject", "spawn object")
    spawn_gear_terms = (
        "spawn gear", "starting gear", "starter gear", "spawngear", "loadout json",
        "fresh-spawn", "fresh spawn", "player loadout", "full loadout",
    )
    restricted_terms = ("restricted area", "player restricted", "safe position", "safepositions3d")
    category_terms = ("custom category", "custom usage", "custom tag", "cfglimitsdefinition")
    event_terms = ("custom event", "vehicle event", "static event", "loot event", "infected event", "animal event", "event spawn")

    if any(term in text for term in ambient_terms):
        return plan(
            "ambient_spawner",
            "Ambient living entities are territory-driven: the zone and the matching CE event work together; they are not fixed cfgeventspawns positions.",
            [
                entry("env/*_territories.xml", "changed", "Add or adjust the zone's X/Z/radius and dmin/dmax population."),
                entry("db/events.xml", "changed", "Define or adjust the matching Ambient/Animal event: global max, distance radius, cleanup radius, restock and child weights."),
                entry("cfgenvironment.xml", "checked", "Confirm the selected map references the territory file and review the zone cooldown setting."),
                entry("cfgeventspawns.xml", "preserved", "Ambient territory zones do not use fixed event-position records unless a separate selected pattern explicitly does."),
            ],
            "Validate that the event's global max, the territory dmin/dmax and child min weights are compatible; child weights should describe the intended type distribution.",
        )

    if any(term in text for term in fire_proxy_terms):
        return plan(
            "fire_smoke_proxy_event_scene",
            "A CE fire/smoke scene can combine proxy visual groups at world coordinates with a separately positioned Static event object. This is a linked XML workflow, not a cfgEffectArea.json contaminated-area file.",
            [
                entry("db/types.xml", "changed", "Merge only the deliberate proxy-class CE changes after diffing any existing selected-map Bonfire/smoke records; do not replace the complete file."),
                entry("cfglimitsdefinition.xml", "conditional", "Define a custom hidden category/usage only when the chosen proxy records genuinely use those new exact names."),
                entry("mapgroupproto.xml", "changed", "Add merge-only fire/smoke proxy groups and any static object's loot prototype, using validated local X/Y/Z and rpy values."),
                entry("mapgrouppos.xml", "changed", "Place each visual group at world X/elevation/Z with names exactly matching its prototype."),
                entry("cfgeventspawns.xml", "changed", "Place the Static event at matching X/Z coordinates and use the exact events.xml name."),
                entry("db/events.xml", "changed", "Add the matching Static event definition and verified static child classname."),
                entry("db/globals.xml", "checked", "Confirm LootProxyPlacement permits the selected dispatch/proxy method."),
                entry("cfgEffectArea.json", "preserved", "This particular fire/smoke proxy method does not use the contaminated/effect-area JSON schema."),
            ],
            "Cross-check event names, MapGroup names, coordinates, categories/usages, classnames and proxy offsets. Fire-only or smoke-only requests may omit the other visual group, but must not omit the files genuinely linked by the selected mechanism.",
        )

    if filename in {"events.xml", "cfgeventspawns.xml", "cfgeventgroups.xml"} or any(term in text for term in event_terms):
        return plan(
            "ce_event_package",
            "A positioned CE event normally changes the definition and matching position together; event groups and map prototypes change only when the design actually references them.",
            [
                entry("db/events.xml", "changed", "Add or adjust the named CE definition, classname, counts, lifetime, radii, flags and children."),
                entry("cfgeventspawns.xml", "changed", "Add or adjust positions using exactly the same case-sensitive event name and six-decimal rotation."),
                entry("cfgeventgroups.xml", "conditional", "Change only when a cfgeventspawns position uses a group= reference."),
                entry("mapgroupproto.xml", "conditional", "Change only when a loot-bearing static/group child needs a compatible prototype and loot points."),
                entry("db/types.xml", "checked", "Confirm every requested child classname exists for the selected map/version."),
                entry("cfgspawnabletypes.xml", "conditional", "Change only when requested attachments or cargo need an explicit spawnable-type record."),
            ],
            "Event names must match exactly in events.xml and cfgeventspawns.xml. Do not manufacture group/prototype records for an event that does not reference them.",
        )

    if filename in {"mapgrouppos.xml", "mapgroupproto.xml"} or any(term in text for term in map_group_terms):
        is_proxy_method = any(term in text for term in proxy_method_terms)
        placement_action = "changed" if filename == "mapgrouppos.xml" or any(term in text for term in ("place", "placement", "move", "position", "new building", "new group")) else "checked"
        prototype_action = "changed" if filename == "mapgroupproto.xml" or any(term in text for term in ("loot point", "lootpoint", "new building", "new group", "prototype")) or is_proxy_method else "checked"
        if is_proxy_method:
            placement_action = "changed"
            return plan(
                "map_group_proxy_placement",
                "The CE proxy method places a named group at world coordinates, then places explicit item proxies at model-local offsets inside that same group.",
                [
                    entry("mapgrouppos.xml", "changed", "Add the world X/elevation/Z placement and rotation using the exact same custom group name as the prototype."),
                    entry("mapgroupproto.xml", "changed", "Add a merge-only group containing compatible loot rules and explicit dispatch/proxy records with local X/Y/Z and rpy values."),
                    entry("db/types.xml", "checked", "Confirm every proxy classname exists in the active map/version and has enough CE availability for the intended proxy spawn."),
                    entry("db/globals.xml", "checked", "Confirm LootProxyPlacement is enabled for dispatch-container loot."),
                    entry("cfglimitsdefinition.xml", "conditional", "Change only if the proxy layout genuinely introduces a new category/usage/tag name."),
                    entry("db/events.xml", "preserved", "The map-group proxy method is CE loot placement, not a positioned event package."),
                ],
                "World placement pos is X/elevation/Z; proxy pos is local X/Y/Z. Match the group name exactly, validate every classname, keep unrelated groups intact, and do not claim a building itself can be used as a proxy loot item.",
            )
        return plan(
            "map_group_placement",
            "MapGroupPos places a named group on one map; MapGroupProto defines that group's reusable structure and loot points. They must be considered together, but either one may remain unchanged.",
            [
                entry("mapgrouppos.xml", placement_action, "Placement group name, map coordinates and rotation must match the selected map/prototype relationship."),
                entry("mapgroupproto.xml", prototype_action, "Prototype group name, containers and loot points must match the placement and requested loot behaviour."),
                entry("db/types.xml", "checked", "Any item expected to spawn from those loot points must have compatible categories/usages and a valid selected-map classname."),
                entry("cfglimitsdefinition.xml", "conditional", "Only add a user/category/usage/tag definition if the requested loot rule introduces a new named definition."),
                entry("cfglimitsdefinitionuser.xml", "conditional", "Use only to add a named alias combining usage/value names already present in cfglimitsdefinition.xml."),
            ],
            "Do not use MapGroup files for a normal ObjectSpawner JSON base. Do not add a prototype or loot points unless the placement/event actually requires them.",
        )

    if filename == "objectspawner.json" or any(term in text for term in object_spawner_terms):
        json_path = custom_path or "custom/objectspawner.json"
        return plan(
            "object_spawner",
            "ObjectSpawner uses a complete JSON object list and an explicit cfgGameplay WorldsData.objectSpawnersArr reference; it is not a MapGroupPos/Proto workflow.",
            [
                entry(json_path, "changed", "Complete ObjectSpawner JSON containing Objects entries with valid classname/model path and position/orientation vectors."),
                entry("cfggameplay.json", "changed", "Add the exact relative JSON path to WorldsData.objectSpawnersArr while preserving existing references."),
                entry("init.c", "checked", "Only inspect if the server uses script-based spawning or customString handling; do not rewrite it for ordinary ObjectSpawner JSON."),
                entry("mapgrouppos.xml", "preserved", "ObjectSpawner placement is not map-group placement data."),
                entry("mapgroupproto.xml", "preserved", "Only a separate request for CE loot points needs a map-group prototype."),
            ],
            "Validate the JSON separately, confirm terrain height and classnames, and test a small placement batch before adding a large build.",
        )

    if custom_path and any(term in text for term in restricted_terms):
        return plan(
            "player_restricted_area",
            "A player-restricted area is a custom JSON plus a matching cfgGameplay WorldsData reference.",
            [
                entry(custom_path, "changed", "Complete restricted-area JSON with PRABoxes and safePositions3D vectors."),
                entry("cfggameplay.json", "changed", "Add the exact relative path to WorldsData.playerRestrictedAreaFiles."),
            ],
            "Check every Y coordinate, keep JSON comments out of the upload, and never replace existing gameplay path arrays.",
        )

    if custom_path and any(term in text for term in spawn_gear_terms):
        return plan(
            "spawn_gear",
            "Spawn gear presets are custom JSON files enabled through cfgGameplay; player spawn locations are a separate configuration.",
            [
                entry(custom_path, "changed", "Complete recognised spawning-gear preset JSON."),
                entry("cfggameplay.json", "changed", "Add the exact relative path to PlayerData.spawnGearPresetFiles."),
                entry("cfgplayerspawnpoints.xml", "checked", "Only change this for fresh-spawn location/group rules, not to insert JSON inventory."),
                entry("init.c", "checked", "Inspect only because StartingEquipSetup or CreateCharacter overrides can conflict with spawn-gear presets."),
            ],
            "Use the selected map/current preset schema and test with a newly created character; mod or script loadouts need their actual configuration.",
        )

    if filename in {"types.xml", "cfgspawnabletypes.xml"} or any(term in text for term in ("boost loot", "loot boost", "nominal", "restock", "lifetime", "attachments", "cargo")):
        return plan(
            "central_economy_loot",
            "Types controls world-loot eligibility and quantities; spawnable types controls nested attachments/cargo. Map-group and limit files only enter the package when the request changes building eligibility or named CE definitions.",
            [
                entry("db/types.xml", "changed" if filename == "types.xml" or "loot" in text else "checked", "Review classnames, nominal/min/lifetime/restock, flags, tiers, categories and usages."),
                entry("cfgspawnabletypes.xml", "changed" if filename == "cfgspawnabletypes.xml" or any(term in text for term in ("attachment", "cargo", "preset", "loadout")) else "checked", "Review nested cargo, attachments, quantities and damage only when requested."),
                entry("mapgroupproto.xml", "conditional", "Needed only if the requested item must become eligible at specific static building/group loot points."),
                entry("cfglimitsdefinition.xml", "conditional", "Needed only for a new custom category, usage or tag."),
            ],
            "Changing nominal alone cannot make an item spawn in a building whose group/category/usage rules do not allow it.",
        )

    if filename in {"cfglimitsdefinition.xml", "cfglimitsdefinitionuser.xml"} or any(term in text for term in category_terms):
        return plan(
            "central_economy_definitions",
            "Actual CE categories, tags, usages and values belong in cfglimitsdefinition.xml; cfglimitsdefinitionuser.xml only creates named aliases from existing usage/value definitions.",
            [
                entry("cfglimitsdefinition.xml", "changed" if filename == "cfglimitsdefinition.xml" else "checked", "Use the selected mission's primary CE definition file and preserve existing lists."),
                entry("cfglimitsdefinitionuser.xml", "changed" if filename == "cfglimitsdefinitionuser.xml" else "conditional", "Create only usage/value alias groups whose nested names already exist in cfglimitsdefinition.xml."),
                entry("db/types.xml", "checked", "Confirm every item uses the exact defined category/usage/tag name."),
                entry("mapgroupproto.xml", "checked", "Confirm static building/group loot rules use the same exact names where applicable."),
            ],
            "A definition name is case-sensitive project data: do not add it in one file and assume other CE files will discover it automatically.",
        )

    if filename.endswith("_territories.xml") or "territory" in text or "infected zone" in text or "animal zone" in text:
        return plan(
            "territory_zone",
            "Animal/infected territory zones and their environment references form a linked configuration; fixed CE event positions are a different workflow.",
            [
                entry("env/*_territories.xml", "changed", "Add or adjust the correct selected animal/infected territory records."),
                entry("cfgenvironment.xml", "checked", "Confirm the selected map/environment includes the territory file."),
                entry("db/events.xml", "conditional", "Needed for ambient/dynamic event behaviour, not for every ordinary territory edit."),
            ],
            "Use conservative dmin/dmax values and selected-map coordinates. Prefer an ambient-spawner plan when the request is explicitly on-demand wildlife.",
        )

    spec = dayz_file_spec_for_path(raw_path)
    target = raw_path or (spec.filename if spec else "the selected DayZ file")
    dependencies = dayz_agent_file_knowledge(raw_path).get("dependencies", []) if raw_path else []
    return plan(
        "single_file_or_unknown",
        "Start with the selected current/vanilla file and identify references before generating a complete replacement.",
        [entry(target, "changed" if raw_path else "checked", "The selected target must use its real map/version schema.")],
        "Related references to inspect: " + ("; ".join(str(item) for item in dependencies) if dependencies else "none can be safely assumed; request the complete current file or exact feature details."),
    )


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
        common_sources = [
            "https://community.bistudio.com/wiki/DayZ:Central_Economy_Configuration",
            "https://community.bistudio.com/wiki/DayZ:Gameplay_Settings",
        ]
        focused_sources = {
            "cfgweather.xml": ["https://community.bistudio.com/wiki/DayZ:Weather_Configuration"],
            "objectspawner.json": ["https://community.bistudio.com/wiki/DayZ:Object_Spawner"],
            "cfggameplay.json": ["https://community.bistudio.com/wiki/DayZ:Gameplay_Settings"],
            "spawning_gear": ["https://community.bistudio.com/wiki/DayZ:Spawning_Gear_Configuration"],
            "cfgplayerspawnpoints.xml": ["https://community.bistudio.com/wiki/DayZ:Player_Spawning_Configuration"],
            "cfgundergroundtriggers.json": ["https://community.bistudio.com/wiki/DayZ:Underground_Areas_Configuration"],
            "cfgeffectarea.json": ["https://community.bistudio.com/wiki/DayZ:Contaminated_Areas_Configuration"],
            "territories": ["https://community.bistudio.com/wiki/DayZ:CE:_Ambient_Spawner"],
            "cfgeconomycore.xml": ["https://community.bistudio.com/wiki/DayZ:Central_Economy_mission_files_modding"],
            "types.xml": ["https://community.bistudio.com/wiki/DayZ:Central_Economy_mission_files_modding"],
            "cfgspawnabletypes.xml": ["https://community.bistudio.com/wiki/DayZ:Central_Economy_mission_files_modding"],
            "events.xml": ["https://community.bistudio.com/wiki/DayZ:Central_Economy_mission_files_modding"],
            "mapgroupproto.xml": ["https://community.bistudio.com/wiki/DayZ:Diag_Menu"],
            "mapgrouppos.xml": ["https://community.bistudio.com/wiki/DayZ:Diag_Menu"],
        }
        guidance["official_sources"] = list(dict.fromkeys([*focused_sources.get(key, []), *common_sources]))
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
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


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
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            return False, f"Refusing to upload `{target_path}`: {label}[{index}] must be a non-empty string path."
        normalized = item.strip().replace("\\", "/")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            return False, f"Refusing to upload `{target_path}`: {label}[{index}] must be a mission-relative JSON path."
        parts = normalized.split("/")
        if parts and parts[0] == ".":
            parts = parts[1:]
        if (
            not parts
            or any(not part or part in {".", ".."} for part in parts)
            or not parts[-1].lower().endswith(".json")
        ):
            return False, (
                f"Refusing to upload `{target_path}`: {label}[{index}] must be a safe mission-relative `.json` path "
                "without `.`/`..` traversal segments."
            )
    return True, ""


def _validate_restricted_area_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"Refusing to upload `{target_path}`: restricted-area JSON root must be an object."
    if not isinstance(payload.get("areaName"), str) or not payload.get("areaName", "").strip():
        return False, f"Refusing to upload `{target_path}`: restricted-area JSON needs a non-empty `areaName`."
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
        for string_key in ("AreaName", "Type", "TriggerType"):
            if not isinstance(area.get(string_key), str) or not area.get(string_key, "").strip():
                return False, f"Refusing to upload `{target_path}`: Areas[{index}] needs a non-empty `{string_key}`."
        data = area.get("Data")
        if not isinstance(data, dict):
            return False, f"Refusing to upload `{target_path}`: Areas[{index}].Data must be an object."
        position_key = "Pos" if "Pos" in data else "Position" if "Position" in data else ""
        if not position_key:
            return False, f"Refusing to upload `{target_path}`: Areas[{index}].Data needs a `Pos` coordinate triplet."
        error = _validate_number_triplet(data.get(position_key), f"Areas[{index}].Data.{position_key}")
        if error:
            return False, f"Refusing to upload `{target_path}`: {error}"
        if not any(radius_key in data for radius_key in ("Radius", "OuterRingRadius", "InnerRingRadius")):
            return False, f"Refusing to upload `{target_path}`: Areas[{index}].Data needs a radius value."
        for radius_key in ("Radius", "OuterRingRadius", "InnerRingRadius"):
            if radius_key in data and (not _is_number(data.get(radius_key)) or float(data.get(radius_key)) < 0):
                return False, f"Refusing to upload `{target_path}`: Areas[{index}].Data.{radius_key} must be a non-negative number."
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
            if vector_key not in trigger:
                return False, f"Refusing to upload `{target_path}`: Triggers[{index}] is missing `{vector_key}`."
            error = _validate_number_triplet(trigger.get(vector_key), f"Triggers[{index}].{vector_key}")
            if error:
                return False, f"Refusing to upload `{target_path}`: {error}"
        accommodation = trigger.get("EyeAccommodation")
        if not _is_number(accommodation) or not 0.0 <= float(accommodation) <= 1.0:
            return False, f"Refusing to upload `{target_path}`: Triggers[{index}].EyeAccommodation must be a number between 0 and 1."
        breadcrumbs = trigger.get("Breadcrumbs", [])
        if not isinstance(breadcrumbs, list):
            return False, f"Refusing to upload `{target_path}`: Triggers[{index}].Breadcrumbs must be an array."
        for breadcrumb_index, breadcrumb in enumerate(breadcrumbs):
            if not isinstance(breadcrumb, dict):
                return False, f"Refusing to upload `{target_path}`: Triggers[{index}].Breadcrumbs[{breadcrumb_index}] must be an object."
            if "Position" not in breadcrumb:
                return False, f"Refusing to upload `{target_path}`: Triggers[{index}].Breadcrumbs[{breadcrumb_index}] is missing `Position`."
            error = _validate_number_triplet(breadcrumb.get("Position"), f"Triggers[{index}].Breadcrumbs[{breadcrumb_index}].Position")
            if error:
                return False, f"Refusing to upload `{target_path}`: {error}"
            breadcrumb_accommodation = breadcrumb.get("EyeAccommodation")
            if not _is_number(breadcrumb_accommodation) or not 0.0 <= float(breadcrumb_accommodation) <= 1.0:
                return False, (
                    f"Refusing to upload `{target_path}`: Triggers[{index}].Breadcrumbs[{breadcrumb_index}]"
                    ".EyeAccommodation must be a number between 0 and 1."
                )
    return True, ""


def _validate_spawn_gear_preset_payload(payload: Any, target_path: Any) -> tuple[bool, str]:
    presets = payload if isinstance(payload, list) else [payload]
    if not presets or not all(isinstance(preset, dict) for preset in presets):
        return False, f"Refusing to upload `{target_path}`: spawning-gear JSON must be an object or array of objects."

    def validate_weight(value: Any, label: str) -> str:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return f"{label} must be an integer of at least 1."
        return ""

    def validate_attributes(value: Any, label: str) -> str:
        if value is None:
            return ""
        if not isinstance(value, dict):
            return f"{label} must be an object."
        for key in ("healthMin", "healthMax", "quantityMin", "quantityMax"):
            if key in value and (not _is_number(value.get(key)) or not 0.0 <= float(value.get(key)) <= 1.0):
                return f"{label}.{key} must be a number between 0 and 1."
        for minimum_key, maximum_key in (("healthMin", "healthMax"), ("quantityMin", "quantityMax")):
            if minimum_key in value and maximum_key in value and float(value[minimum_key]) > float(value[maximum_key]):
                return f"{label} must satisfy {minimum_key} <= {maximum_key}."
        return ""

    def validate_children(container: dict[str, Any], label: str, depth: int) -> str:
        if depth > 8:
            return f"{label} nesting exceeds the supported safety depth of 8."
        if "simpleChildrenUseDefaultAttributes" in container and not isinstance(container.get("simpleChildrenUseDefaultAttributes"), bool):
            return f"{label}.simpleChildrenUseDefaultAttributes must be true or false."
        simple = container.get("simpleChildrenTypes")
        if simple is not None:
            if not isinstance(simple, list) or any(not isinstance(item, str) or not item.strip() for item in simple):
                return f"{label}.simpleChildrenTypes must be an array of non-empty class-name strings."
        complex_children = container.get("complexChildrenTypes")
        if complex_children is not None:
            if not isinstance(complex_children, list):
                return f"{label}.complexChildrenTypes must be an array."
            for child_index, child in enumerate(complex_children):
                child_label = f"{label}.complexChildrenTypes[{child_index}]"
                if not isinstance(child, dict):
                    return f"{child_label} must be an object."
                if not isinstance(child.get("itemType"), str) or not child.get("itemType", "").strip():
                    return f"{child_label}.itemType must be a non-empty class name."
                error = validate_attributes(child.get("attributes"), f"{child_label}.attributes")
                if error:
                    return error
                if "quickBarSlot" in child and (
                    isinstance(child.get("quickBarSlot"), bool)
                    or not isinstance(child.get("quickBarSlot"), int)
                    or child.get("quickBarSlot") < -1
                ):
                    return f"{child_label}.quickBarSlot must be an integer of -1 or greater."
                error = validate_children(child, child_label, depth + 1)
                if error:
                    return error
        return ""

    for index, preset in enumerate(presets):
        label = f"spawning-gear preset {index}"
        if not any(key in preset for key in ("spawnWeight", "attachmentSlotItemSets", "discreteUnsortedItemSets")):
            return False, f"Refusing to upload `{target_path}`: spawning-gear preset {index} has no recognised gear fields."
        if not isinstance(preset.get("name"), str) or not preset.get("name", "").strip():
            return False, f"Refusing to upload `{target_path}`: {label}.name must be a non-empty string."
        error = validate_weight(preset.get("spawnWeight"), f"{label}.spawnWeight")
        if error:
            return False, f"Refusing to upload `{target_path}`: {error}"
        character_types = preset.get("characterTypes", [])
        if not isinstance(character_types, list) or any(
            not isinstance(item, str) or not item.strip() for item in character_types
        ):
            return False, f"Refusing to upload `{target_path}`: {label}.characterTypes must be an array of non-empty class-name strings."
        attachment_sets = preset.get("attachmentSlotItemSets", [])
        if not isinstance(attachment_sets, list):
            return False, f"Refusing to upload `{target_path}`: {label}.attachmentSlotItemSets must be an array."
        for slot_index, slot in enumerate(attachment_sets):
            slot_label = f"{label}.attachmentSlotItemSets[{slot_index}]"
            if not isinstance(slot, dict):
                return False, f"Refusing to upload `{target_path}`: {slot_label} must be an object."
            if not isinstance(slot.get("slotName"), str) or not slot.get("slotName", "").strip():
                return False, f"Refusing to upload `{target_path}`: {slot_label}.slotName must be a non-empty string."
            item_sets = slot.get("discreteItemSets")
            if not isinstance(item_sets, list) or not item_sets:
                return False, f"Refusing to upload `{target_path}`: {slot_label}.discreteItemSets must be a non-empty array."
            for item_index, item in enumerate(item_sets):
                item_label = f"{slot_label}.discreteItemSets[{item_index}]"
                if not isinstance(item, dict):
                    return False, f"Refusing to upload `{target_path}`: {item_label} must be an object."
                # An empty itemType is an official way to represent a weighted
                # "nothing in this slot" variant, but the field must be a string.
                if not isinstance(item.get("itemType"), str):
                    return False, f"Refusing to upload `{target_path}`: {item_label}.itemType must be a class-name string."
                error = validate_weight(item.get("spawnWeight"), f"{item_label}.spawnWeight")
                if error:
                    return False, f"Refusing to upload `{target_path}`: {error}"
                error = validate_attributes(item.get("attributes"), f"{item_label}.attributes")
                if error:
                    return False, f"Refusing to upload `{target_path}`: {error}"
                if "quickBarSlot" in item and (
                    isinstance(item.get("quickBarSlot"), bool)
                    or not isinstance(item.get("quickBarSlot"), int)
                    or item.get("quickBarSlot") < -1
                ):
                    return False, f"Refusing to upload `{target_path}`: {item_label}.quickBarSlot must be an integer of -1 or greater."
                error = validate_children(item, item_label, 0)
                if error:
                    return False, f"Refusing to upload `{target_path}`: {error}"
        cargo_sets = preset.get("discreteUnsortedItemSets", [])
        if not isinstance(cargo_sets, list):
            return False, f"Refusing to upload `{target_path}`: {label}.discreteUnsortedItemSets must be an array."
        for cargo_index, cargo in enumerate(cargo_sets):
            cargo_label = f"{label}.discreteUnsortedItemSets[{cargo_index}]"
            if not isinstance(cargo, dict):
                return False, f"Refusing to upload `{target_path}`: {cargo_label} must be an object."
            if not isinstance(cargo.get("name"), str) or not cargo.get("name", "").strip():
                return False, f"Refusing to upload `{target_path}`: {cargo_label}.name must be a non-empty string."
            error = validate_weight(cargo.get("spawnWeight"), f"{cargo_label}.spawnWeight")
            if error:
                return False, f"Refusing to upload `{target_path}`: {error}"
            error = validate_attributes(cargo.get("attributes"), f"{cargo_label}.attributes")
            if error:
                return False, f"Refusing to upload `{target_path}`: {error}"
            error = validate_children(cargo, cargo_label, 0)
            if error:
                return False, f"Refusing to upload `{target_path}`: {error}"
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
        if any(key in payload for key in ("spawnWeight", "attachmentSlotItemSets", "discreteUnsortedItemSets")):
            return "spawning_gear"
    if isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
        if all(any(key in item for key in ("spawnWeight", "attachmentSlotItemSets", "discreteUnsortedItemSets")) for item in payload):
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
            if not math.isfinite(value):
                return False, f"Refusing to upload `{target_path}`: <{section_name}><{child_name}> `{field}` must be finite."
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
            if not math.isfinite(value):
                return False, f"Refusing to upload `{target_path}`: <storm> `{field}` must be finite."
            if not 0.0 <= value <= 1.0:
                return False, f"Refusing to upload `{target_path}`: <storm> `{field}` must be between 0 and 1."
    wind = root.find("wind")
    if wind is not None:
        raw_maxspeed = child_value(wind, "maxspeed")
        if raw_maxspeed is not None:
            try:
                maxspeed = float(str(raw_maxspeed))
                if not math.isfinite(maxspeed):
                    return False, f"Refusing to upload `{target_path}`: <wind> maxspeed must be finite."
                if maxspeed < 0:
                    return False, f"Refusing to upload `{target_path}`: <wind> maxspeed cannot be negative."
            except (TypeError, ValueError):
                return False, f"Refusing to upload `{target_path}`: <wind> maxspeed must be numeric."
    return True, ""


def _validate_space_separated_vector(value: Any, label: str, target_path: Any, size: int = 3) -> tuple[bool, str]:
    parts = str(value or "").strip().split()
    if len(parts) != size:
        return False, f"Refusing to upload `{target_path}`: {label} must contain exactly {size} space-separated numbers."
    try:
        numbers = [float(part) for part in parts]
    except (TypeError, ValueError):
        return False, f"Refusing to upload `{target_path}`: {label} must contain only numbers."
    if not all(math.isfinite(number) for number in numbers):
        return False, f"Refusing to upload `{target_path}`: {label} values must be finite."
    return True, ""


def _validate_mapgroupproto_xml(root: ET.Element, target_path: Any) -> tuple[bool, str]:
    seen_group_names: set[str] = set()
    for group_index, group in enumerate(root.findall("group")):
        group_name = str(group.get("name") or "").strip()
        if not group_name:
            return False, f"Refusing to upload `{target_path}`: group {group_index + 1} is missing `name`."
        if group_name in seen_group_names:
            return False, f"Refusing to upload `{target_path}`: duplicate prototype group name `{group_name}`."
        seen_group_names.add(group_name)
        for node_label, node in [("group", group), *(("container", node) for node in group.findall("container"))]:
            raw_lootmax = node.get("lootmax")
            if raw_lootmax is None:
                continue
            try:
                lootmax = int(raw_lootmax)
            except (TypeError, ValueError):
                return False, f"Refusing to upload `{target_path}`: {group_name} {node_label} lootmax must be an integer."
            if lootmax < 0:
                return False, f"Refusing to upload `{target_path}`: {group_name} {node_label} lootmax cannot be negative."
        for point_index, point in enumerate(group.findall(".//point")):
            valid, message = _validate_space_separated_vector(
                point.get("pos"), f"{group_name} point {point_index + 1} `pos`", target_path
            )
            if not valid:
                return valid, message
            for attribute in ("range", "height"):
                raw_value = point.get(attribute)
                if raw_value is None:
                    continue
                try:
                    number = float(raw_value)
                except (TypeError, ValueError):
                    return False, f"Refusing to upload `{target_path}`: {group_name} point {point_index + 1} `{attribute}` must be numeric."
                if not math.isfinite(number) or number <= 0:
                    return False, f"Refusing to upload `{target_path}`: {group_name} point {point_index + 1} `{attribute}` must be a positive finite number."
        for proxy_index, proxy in enumerate(group.findall("./dispatch/proxy")):
            if not str(proxy.get("type") or "").strip():
                return False, f"Refusing to upload `{target_path}`: {group_name} proxy {proxy_index + 1} is missing `type`."
            for attribute in ("pos", "rpy"):
                valid, message = _validate_space_separated_vector(
                    proxy.get(attribute), f"{group_name} proxy {proxy_index + 1} `{attribute}`", target_path
                )
                if not valid:
                    return valid, message
    return True, ""


def _validate_mapgrouppos_xml(root: ET.Element, target_path: Any) -> tuple[bool, str]:
    for group_index, group in enumerate(root.findall("group")):
        group_name = str(group.get("name") or "").strip()
        if not group_name:
            return False, f"Refusing to upload `{target_path}`: placement group {group_index + 1} is missing `name`."
        valid, message = _validate_space_separated_vector(
            group.get("pos"), f"{group_name} placement `pos`", target_path
        )
        if not valid:
            return valid, message
        if group.get("rpy") is not None:
            valid, message = _validate_space_separated_vector(
                group.get("rpy"), f"{group_name} placement `rpy`", target_path
            )
            if not valid:
                return valid, message
        if group.get("a") is not None:
            try:
                angle = float(group.get("a"))
            except (TypeError, ValueError):
                return False, f"Refusing to upload `{target_path}`: {group_name} placement `a` must be numeric."
            if not math.isfinite(angle):
                return False, f"Refusing to upload `{target_path}`: {group_name} placement `a` must be finite."
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
        if filename == "mapgroupproto.xml":
            return _validate_mapgroupproto_xml(root, target_path)
        if filename == "mapgrouppos.xml":
            return _validate_mapgrouppos_xml(root, target_path)
        if filename == "cfgeventspawns.xml":
            for event in root.findall("event"):
                for position_index, position in enumerate(event.findall("pos")):
                    for key in ("x", "z", "y", "a"):
                        raw_value = position.get(key)
                        if raw_value is None:
                            if key in {"x", "z"}:
                                return False, (
                                    f"Refusing to upload `{target_path}`: event {event.get('name')} position "
                                    f"{position_index + 1} is missing `{key}`."
                                )
                            continue
                        try:
                            value = float(raw_value)
                        except (TypeError, ValueError):
                            return False, (
                                f"Refusing to upload `{target_path}`: event {event.get('name')} position "
                                f"{position_index + 1} `{key}` must be numeric."
                            )
                        if not math.isfinite(value):
                            return False, (
                                f"Refusing to upload `{target_path}`: event {event.get('name')} position "
                                f"{position_index + 1} `{key}` must be finite."
                            )
        if filename == "messages.xml":
            for message_index, message in enumerate(root.findall("message")):
                for tag in ("delay", "repeat", "deadline", "onconnect", "shutdown"):
                    child = message.find(tag)
                    if child is None:
                        continue
                    try:
                        value = float(str(child.text or "").strip())
                    except (TypeError, ValueError):
                        return False, f"Refusing to upload `{target_path}`: message {message_index + 1} `<{tag}>` must be numeric."
                    if not math.isfinite(value):
                        return False, f"Refusing to upload `{target_path}`: message {message_index + 1} `<{tag}>` must be finite."
                    if tag in {"onconnect", "shutdown"} and value not in {0, 1}:
                        return False, f"Refusing to upload `{target_path}`: message {message_index + 1} `<{tag}>` must be 0 or 1."
                    if tag in {"delay", "repeat", "deadline"} and value < 0:
                        return False, f"Refusing to upload `{target_path}`: message {message_index + 1} `<{tag}>` cannot be negative."
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
