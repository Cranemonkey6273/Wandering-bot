"""Flask dashboard for Wandering Bot.

The dashboard reads and writes the same JSON files used by ``bot.py``. It is
deliberately conservative: secrets are never rendered, and admin routes mutate
local JSON state only so the Discord bot can pick up changes on its next read.
"""

from __future__ import annotations

import json
import io
import os
import re
import secrets
import hashlib
import zipfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from threading import Thread
from typing import Any
from zoneinfo import ZoneInfo

import requests
from flask import Flask, g, jsonify, make_response, redirect, render_template_string, request, send_file


DATA_ROOT = (
    os.getenv("WANDERING_DATA_DIR")
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    or os.getenv("RAILWAY_VOLUME_PATH")
    or "."
)
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
BOT_IMAGE_FILE = os.getenv("WANDERING_BOT_IMAGE_FILE", os.path.join(APP_ROOT, "wanderingbot.png"))
BOT_CHARACTER_FILE = os.getenv("WANDERING_BOT_CHARACTER_FILE", os.path.join(APP_ROOT, "wanderingbot_character.png"))
MAP_IMAGE_FILES = {
    "chernarus": os.getenv("WANDERING_CHERNARUS_MAP_FILE", os.path.join(APP_ROOT, "chernarus_map.jpg")),
    "livonia": os.getenv("WANDERING_LIVONIA_MAP_FILE", os.path.join(APP_ROOT, "livonia_map.jpg")),
}
DEFAULT_MAP_IMAGE_SOURCES = {
    "chernarus": os.getenv("WANDERING_CHERNARUS_MAP_URL", "https://i.redd.it/a2mn8bzx93gd1.jpeg"),
    "livonia": os.getenv("WANDERING_LIVONIA_MAP_URL", "https://i.imgur.com/nzEp9wF.jpeg"),
}
BUILD_COMMIT = (
    os.getenv("RAILWAY_GIT_COMMIT_SHA")
    or os.getenv("GIT_COMMIT_SHA")
    or os.getenv("SOURCE_VERSION")
    or ""
)
SCENARIO_SPAWN_PRESETS = {
    "bear": {"label": "Bears", "class": "Animal_UrsusArctos", "event_type": "animal_pack", "count": 3, "radius": 90},
    "wolf": {"label": "Wolves", "class": "Animal_CanisLupus_Grey", "event_type": "animal_pack", "count": 6, "radius": 120},
    "deer": {"label": "Deer", "class": "Animal_CervusElaphus", "event_type": "animal_pack", "count": 5, "radius": 120},
    "boar": {"label": "Boar", "class": "Animal_SusScrofa", "event_type": "animal_pack", "count": 4, "radius": 80},
    "civilian_zombie": {"label": "Civilian infected", "class": "ZmbM_CitizenASkinny_Brown", "event_type": "zombie_horde", "count": 10, "radius": 55},
    "military_zombie": {"label": "Military infected", "class": "ZmbM_SoldierNormal", "event_type": "zombie_horde", "count": 12, "radius": 60},
    "heavy_military_zombie": {"label": "Heavy military infected", "class": "ZmbM_usSoldier_Heavy_Woodland", "event_type": "zombie_horde", "count": 8, "radius": 55},
    "police_zombie": {"label": "Police infected", "class": "ZmbM_PolicemanFat", "event_type": "zombie_horde", "count": 10, "radius": 55},
    "medical_zombie": {"label": "Medical infected", "class": "ZmbM_DoctorFat", "event_type": "zombie_horde", "count": 8, "radius": 45},
    "military_crate": {"label": "Military loot", "class": "WoodenCrate", "event_type": "airdrop", "loot_preset": "military_high"},
    "wooden_crate": {"label": "Survival loot", "class": "WoodenCrate", "event_type": "airdrop", "loot_preset": "survival"},
    "sea_chest": {"label": "Sea chest container", "class": "SeaChest", "event_type": "airdrop", "loot_preset": "survival"},
    "green_barrel": {"label": "Green barrel container", "class": "Barrel_Green", "event_type": "airdrop", "loot_preset": "survival"},
    "medical_crate": {"label": "Medical loot", "class": "WoodenCrate", "event_type": "airdrop", "loot_preset": "medical"},
    "building_crate": {"label": "Building loot", "class": "WoodenCrate", "event_type": "airdrop", "loot_preset": "building"},
    "food_crate": {"label": "Food loot", "class": "WoodenCrate", "event_type": "airdrop", "loot_preset": "food"},
    "gas_temp": {"label": "Temporary gas zone", "class": "ContaminatedArea_Dynamic", "event_type": "gas_zone", "count": 1, "radius": 120},
    "gas_permanent": {"label": "Permanent gas zone", "class": "ContaminatedArea_Dynamic", "event_type": "gas_zone", "count": 1, "radius": 150},
    "gas_red_temp": {"label": "Temporary red gas zone", "class": "ContaminatedArea_Dynamic", "event_type": "gas_zone", "count": 1, "radius": 120, "gas_particle": "debug"},
    "gas_red_permanent": {"label": "Permanent red gas zone", "class": "ContaminatedArea_Dynamic", "event_type": "gas_zone", "count": 1, "radius": 150, "gas_particle": "debug"},
    "custom": {"label": "Custom classname", "class": "", "event_type": "custom"},
}
DASHBOARD_AIRDROP_LOCATION_PRESETS = {
    "chernarus": [
        {"name": "NWAF", "x": 4481, "z": 10355},
        {"name": "M&M base", "x": 1084, "z": 6637},
        {"name": "NEAF", "x": 12136, "z": 12513},
        {"name": "Tisy", "x": 1612, "z": 14175},
        {"name": "Skalisty Island", "x": 13532, "z": 3131},
        {"name": "Balota Airstrip", "x": 4810, "z": 2520},
        {"name": "Cherno Docks", "x": 6560, "z": 2520},
        {"name": "Elektro", "x": 10480, "z": 2320},
        {"name": "Berezino", "x": 12200, "z": 9500},
        {"name": "Green Mountain", "x": 3700, "z": 6000},
        {"name": "Vybor Military", "x": 4600, "z": 8400},
        {"name": "Zelenogorsk", "x": 2520, "z": 5140},
    ],
    "livonia": [
        {"name": "Lukow Airfield", "x": 3800, "z": 11700},
        {"name": "Brena", "x": 6700, "z": 11200},
        {"name": "Nadbor", "x": 6100, "z": 4100},
        {"name": "Topolin", "x": 10800, "z": 7900},
        {"name": "Sobotka", "x": 6350, "z": 8200},
        {"name": "Polana", "x": 10700, "z": 5400},
        {"name": "Tarnow", "x": 9200, "z": 10450},
        {"name": "Dolnik", "x": 11350, "z": 11350},
    ],
}
SCENARIO_LOOT_PRESETS = {
    "none": [],
    "military_high": [
        "M4A1", "AKM", "AK74", "SVD", "SKS", "Mosin9130", "FAL", "VSS", "ASVAL", "Saiga",
        "PlateCarrierVest", "PlateCarrierPouches", "PlateCarrierHolster",
        "BallisticHelmet_Green", "BallisticHelmet_Black", "Mich2001Helmet", "TacticalHelmet_Green",
        "M65Jacket_Black", "M65Jacket_Khaki", "GorkaEJacket_PautRev", "GorkaEJacket_Summer",
        "GorkaPants_PautRev", "GorkaPants_Summer", "BDUJacket", "BDUPants",
        "TacticalGloves_Black", "TacticalGloves_Green", "MilitaryBoots_Black", "MilitaryBoots_Brown",
        "MountainBag_Green", "AssaultBag_Green", "AliceBag_Green", "AliceBag_Black", "CoyoteBag_Green",
        "SmershVest", "SmershBag", "BalaclavaMask_Black", "NVGoggles",
        "NBCJacketGray", "NBCPantsGray", "NBCBootsGray", "NBCGlovesGray", "GasMask",
        "M67Grenade", "RGD5Grenade", "FlashGrenade", "M18SmokeGrenade_Red",
        "M18SmokeGrenade_Green", "M18SmokeGrenade_Yellow", "M18SmokeGrenade_Purple",
        "Mag_STANAG_30Rnd", "Mag_AKM_30Rnd", "Mag_AK74_30Rnd", "Mag_SVD_10Rnd",
        "Mag_FAL_20Rnd", "Mag_VSS_10Rnd", "Mag_VAL_20Rnd", "Mag_Saiga_8Rnd",
        "AmmoBox_556x45_20Rnd",
        "AmmoBox_762x39_20Rnd", "AmmoBox_545x39_20Rnd", "AmmoBox_762x54_20Rnd", "AmmoBox_9x39_20Rnd", "AmmoBox_12gaSlug_10Rnd",
        "Ammo_556x45", "Ammo_762x39", "Ammo_545x39", "Ammo_762x54", "Ammo_9x39", "Ammo_12gaSlug",
        "BandageDressing", "TetracyclineAntibiotics", "Morphine", "SalineBagIV",
        "Epinephrine", "BloodBagEmpty", "StartKitIV", "Canteen", "TacticalBaconCan", "Battery9V",
    ],
    "military_basic": ["SKS", "AK74", "Mag_AK74_30Rnd", "Ammo_545x39", "BandageDressing"],
    "medical": ["BandageDressing", "TetracyclineAntibiotics", "SalineBagIV", "Morphine"],
    "survival": ["Canteen", "TacticalBaconCan", "HuntingKnife", "Matchbox", "Rope"],
    "building": ["NailBox", "Hammer", "Handsaw", "Hatchet", "MetalWire"],
    "food": ["BakedBeansCan", "PeachesCan", "SpaghettiCan", "SodaCan_Cola", "WaterBottle"],
    "vehicle_car": ["SparkPlug", "CarBattery", "CarRadiator", "CanisterGasoline", "TireRepairKit", "Blowtorch"],
    "vehicle_truck": ["NailBox", "MetalPlate", "WoodenPlank", "Hammer", "Hatchet", "Handsaw", "CanisterGasoline"],
}
SCENARIO_VEHICLE_PRESETS = {
    "ada": {"label": "Ada 4x4", "class": "OffroadHatchback", "loot_preset": "vehicle_car"},
    "gunter": {"label": "Gunter 2", "class": "Hatchback_02", "loot_preset": "vehicle_car"},
    "sarka": {"label": "Sarka 120", "class": "CivilianSedan", "loot_preset": "vehicle_car"},
    "olga": {"label": "Olga 24", "class": "Sedan_02", "loot_preset": "vehicle_car"},
    "m3s": {"label": "M3S covered truck", "class": "Truck_01_Covered", "loot_preset": "vehicle_truck"},
    "custom_vehicle": {"label": "Custom vehicle classname", "class": "", "loot_preset": "vehicle_car"},
}
VISUAL_LOADOUT_SLOTS = [
    {"key": "Headgear", "label": "Headgear", "picker": "Head", "group": "cloth"},
    {"key": "Mask", "label": "Mask", "picker": "Mask", "group": "cloth"},
    {"key": "Glasses", "label": "Glasses", "picker": "Eyes", "group": "cloth"},
    {"key": "Torso", "label": "Torso / Jacket", "picker": "Body", "group": "cloth"},
    {"key": "Vest", "label": "Vest", "picker": "Vest", "group": "cloth"},
    {"key": "Gloves", "label": "Gloves", "picker": "Gloves", "group": "cloth"},
    {"key": "Legs", "label": "Legs / Pants", "picker": "Legs", "group": "cloth"},
    {"key": "Feet", "label": "Feet / Boots", "picker": "Feet", "group": "cloth"},
    {"key": "Backpack", "label": "Backpack", "picker": "Back", "group": "cloth"},
    {"key": "Shoulder1", "label": "Shoulder 1", "picker": "Left Shoulder", "group": "attachments"},
    {"key": "Shoulder2", "label": "Shoulder 2", "picker": "Right Shoulder", "group": "attachments"},
    {"key": "Belt", "label": "Belt", "picker": "Hips", "group": "attachments"},
    {"key": "Holster", "label": "Holster", "picker": "Hands", "group": "attachments"},
]
VISUAL_LOADOUT_CARGO_SLOTS = [
    {"key": "cargo:Backpack", "label": "Backpack Cargo", "container": "Backpack"},
    {"key": "cargo:Torso", "label": "Jacket Cargo", "container": "Torso"},
    {"key": "cargo:Legs", "label": "Pants Cargo", "container": "Legs"},
]
VISUAL_LOADOUT_CATEGORY_FILTERS = [
    {"key": "", "label": "Slot Items"},
    {"key": "Weapons", "label": "Weapons"},
    {"key": "Clothing", "label": "Clothing"},
    {"key": "Ammunition", "label": "Ammo"},
    {"key": "Medical", "label": "Medical"},
    {"key": "Food/Drink", "label": "Food"},
    {"key": "Misc", "label": "Misc"},
]
VISUAL_LOADOUT_CAPACITY_HINTS = {
    "alicebag": 90,
    "mountainbag": 80,
    "fieldbackpack": 90,
    "drybag": 63,
    "taloonbag": 35,
    "courierbag": 30,
    "improvisedbag": 42,
    "huntingbag": 63,
    "assaultbag": 42,
    "platecarriervest": 24,
    "highcapacityvest": 30,
    "smershvest": 30,
    "smershbag": 30,
    "jacket": 42,
    "pants": 30,
}
VISUAL_LOADOUT_SIZE_HINTS = {
    "m4a1": 27,
    "akm": 27,
    "ak74": 27,
    "sks": 24,
    "mosin": 30,
    "svd": 30,
    "fal": 27,
    "vss": 24,
    "platecarrier": 25,
    "helmet": 9,
    "mag_": 4,
    "ammobox": 4,
    "ammo_": 1,
    "grenade": 2,
    "bandage": 1,
    "canteen": 4,
    "waterbottle": 4,
    "knife": 2,
    "pistol": 6,
}
DASHBOARD_HOST = os.getenv("WANDERING_DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("PORT") or os.getenv("WANDERING_DASHBOARD_PORT", "8080"))
DASHBOARD_REFRESH_SECONDS = int(os.getenv("WANDERING_DASHBOARD_REFRESH_SECONDS", "45"))
ADMIN_TOKEN = os.getenv("WANDERING_DASHBOARD_ADMIN_TOKEN", "")
OWNER_DASHBOARD_ID = os.getenv("WANDERING_OWNER_DASHBOARD_ID", "owner").strip().lower()
OWNER_DASHBOARD_PASSWORD = os.getenv("WANDERING_OWNER_DASHBOARD_PASSWORD", "")
OWNER_ADMIN_GUILD_IDS = os.getenv("WANDERING_OWNER_ADMIN_GUILD_IDS", "")
DASHBOARD_COOKIE_SECRET = os.getenv("WANDERING_DASHBOARD_COOKIE_SECRET") or ADMIN_TOKEN or secrets.token_urlsafe(32)
DASHBOARD_PUBLIC_URL = os.getenv("WANDERING_DASHBOARD_PUBLIC_URL", "https://dayzwanderingbot.com")
DASHBOARD_TIMEZONE = ZoneInfo(os.getenv("WANDERING_DASHBOARD_TIMEZONE", "Europe/Dublin"))
FORCE_HTTPS = os.getenv("WANDERING_FORCE_HTTPS", "true").lower() not in {"0", "false", "off", "no"}
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_CHANNEL_CACHE_SECONDS = int(os.getenv("WANDERING_DISCORD_CHANNEL_CACHE_SECONDS", "300"))
DISCORD_CHANNEL_CACHE: dict[str, tuple[datetime, list[dict[str, str]]]] = {}
DISCORD_ROLE_CACHE: dict[str, tuple[datetime, list[dict[str, str]]]] = {}
DISCORD_MEMBER_CACHE: dict[str, tuple[datetime, list[dict[str, str]]]] = {}
DISCORD_GUILD_COUNT_CACHE: dict[str, tuple[datetime, int]] = {}

APP = Flask(__name__)
APP.secret_key = DASHBOARD_COOKIE_SECRET
CUSTOM_STATE_PROVIDER = None


@APP.before_request
def enforce_https():
    if not FORCE_HTTPS:
        return None
    host = request.host.split(":", 1)[0].lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return None
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    primary_proto = forwarded_proto.split(",", 1)[0].strip().lower()
    if primary_proto == "https" or request.is_secure:
        return None
    if primary_proto == "http" or request.url.startswith("http://"):
        target = f"https://{request.host}{request.full_path}".rstrip("?")
        return redirect(target, code=301)
    return None


@APP.after_request
def add_security_headers(response):
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
    try:
        enqueue_dashboard_audit_event(response)
    except Exception as error:
        print(f"[DASHBOARD AUDIT] queue failed: {error}")
    return response

SECRET_KEYS = {
    "token",
    "password",
    "secret",
    "ftp_password",
    "ftp_user",
    "ftp_host",
    "nitrado_token",
    "nitrado_user",
    "service_id",
}

FILES = {
    "guild_configs": "guild_configs.json",
    "player_stats": "player_stats.json",
    "online_players": "online_players.json",
    "shop": "shop.json",
    "wallets": "wallets.json",
    "factions": "factions.json",
    "wages": "wages.json",
    "delivery_queue": "delivery_queue.json",
    "dashboard_audit_queue": "dashboard_audit_queue.json",
    "dashboard_admin": "dashboard_admin.json",
    "heatmap": "heatmap.json",
    "pve_challenges": "pve_challenges.json",
    "pve_ai_campaigns": "pve_ai_campaigns.json",
    "pve_workshop_schedules": "pve_workshop_schedules.json",
    "swear_jar": "swear_jar.json",
    "longshot_records": "longshot_records.json",
    "removed_guilds": "removed_guilds.json",
}
GUILD_CONFIG_FOLDER = os.path.join("guild_data", "guilds")
LEGACY_GUILD_CONFIG_FOLDER = "guilds"

LOGIN_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wandering Bot Dashboard Login</title>
  <style>
    :root { color-scheme: dark; --bg: #050806; --panel: #111710; --line: rgba(209,203,145,.24); --text: #f3ecd9; --muted: #c4bda7; --gold: #d5b45f; --olive: #8d963e; --red: #ed3853; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: linear-gradient(180deg, #10150d, var(--bg)); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width: min(94vw, 30rem); border: 1px solid var(--line); border-radius: .5rem; background: var(--panel); padding: 1.25rem; box-shadow: 0 1rem 2.5rem rgba(0,0,0,.35); }
    img { width: 4rem; height: 4rem; border-radius: .75rem; object-fit: cover; }
    h1 { margin: .8rem 0 .35rem; text-transform: uppercase; letter-spacing: 0; }
    p { color: var(--muted); line-height: 1.5; }
    form { display: grid; gap: .75rem; margin-top: 1rem; }
    label { display: grid; gap: .25rem; color: var(--muted); font-size: .9rem; }
    input { width: 100%; border: 1px solid var(--line); border-radius: .45rem; background: #080d09; color: var(--text); padding: .75rem .8rem; }
    button { border: 0; border-radius: .45rem; background: var(--olive); color: #070a06; padding: .8rem; font-weight: 900; cursor: pointer; }
    .error { color: #ffd8df; background: rgba(237,56,83,.16); border: 1px solid rgba(237,56,83,.35); padding: .65rem; border-radius: .45rem; }
    code { color: var(--gold); }
  </style>
</head>
<body>
  <main>
    <img src="/brand-image" alt="Wandering Bot logo">
    <h1>Wandering Bot</h1>
    <p>Use a server dashboard ID/password for that one server, or your private owner login for the protected owner console.</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="post" action="/login">
      <label>Dashboard ID <input name="dashboard_id" autocomplete="username" required></label>
      <label>Password <input name="password" type="password" autocomplete="current-password" required></label>
      <button type="submit">Open Dashboard</button>
    </form>
  </main>
</body>
</html>
"""

PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wandering Bot Dashboard</title>
  <script>
    (function () {
      if (window.__wanderingDashboardCoreClicks) return;
      window.__wanderingDashboardCoreClicks = true;

      function closest(node, selector) {
        while (node && node !== document) {
          if (node.matches && node.matches(selector)) return node;
          node = node.parentNode;
        }
        return null;
      }
      function stop(event) {
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      }
      function parseJson(text) {
        try { return JSON.parse(text || "{}"); } catch (error) { return {}; }
      }
      function firstValue() {
        for (var index = 0; index < arguments.length; index += 1) {
          if (arguments[index] !== undefined && arguments[index] !== null && arguments[index] !== "") return arguments[index];
        }
        return "";
      }
      function secureUrl(path) {
        var base = "{{ public_url }}" || window.location.origin;
        try {
          var url = new URL(path || window.location.href, base);
          if (["localhost", "127.0.0.1", "0.0.0.0"].indexOf(url.hostname) === -1) url.protocol = "https:";
          return url.toString();
        } catch (error) {
          return path;
        }
      }
      window.wanderingMeasureZoneMapClick = function (event, control) {
        if (!event || !control || !control.form) return true;
        var rect = control.getBoundingClientRect ? control.getBoundingClientRect() : null;
        if (!rect || !rect.width || !rect.height) return true;
        var pointerX = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
        var pointerY = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
        var form = control.form;
        var setField = function (selector, value) {
          var field = form.querySelector(selector);
          if (field) field.value = String(value);
        };
        setField("[data-map-render-width]", Math.round(rect.width));
        setField("[data-map-render-height]", Math.round(rect.height));
        setField("[data-map-pointer-x]", pointerX);
        setField("[data-map-pointer-y]", pointerY);
        setField("[data-map-percent-x]", (pointerX / rect.width) * 100);
        setField("[data-map-percent-y]", (pointerY / rect.height) * 100);
        var map = closest(control, "[data-zone-map]");
        var size = map ? Number(map.getAttribute("data-map-size") || 15360) : 15360;
        var zoneX = Math.max(0, Math.min(size, Math.round((pointerX / rect.width) * size)));
        var zoneZ = Math.max(0, Math.min(size, Math.round(size - ((pointerY / rect.height) * size))));
        setField("[name='map_click_scale']", rect.width ? (size / rect.width) : 10);
        setField("[name='map_click_override']", "1");
        setField("[name='x']", zoneX);
        setField("[name='y']", zoneZ);
        return true;
      };
      function setControl(form, name, value) {
        if (!form || !form.elements[name]) return;
        var control = form.elements[name];
        var controls = typeof control.length === "number" && !control.tagName ? Array.prototype.slice.call(control) : [control];
        controls.forEach(function (item) {
          if (!item) return;
          if (item.type === "checkbox") {
            item.checked = Boolean(value);
          } else if (item.tagName === "SELECT") {
            var wanted = String(value == null ? "" : value);
            var chosen = "";
            Array.prototype.slice.call(item.options || []).forEach(function (option) {
              if (!chosen && (option.value === wanted || option.getAttribute("data-channel-id") === wanted)) chosen = option.value;
            });
            item.value = chosen || wanted;
            item.dispatchEvent(new Event("change", {bubbles: true}));
          } else {
            item.value = value == null ? "" : value;
            item.dispatchEvent(new Event("input", {bubbles: true}));
          }
        });
      }
      function readCardJson(button, cardSelector, jsonSelector) {
        var card = closest(button, cardSelector);
        var script = card ? card.querySelector(jsonSelector) : null;
        return script ? parseJson(script.textContent) : {};
      }
      function scrollToForm(form) {
        if (!form) return;
        form.classList.add("dashboard-edit-modal");
        form.scrollIntoView({behavior: "smooth", block: "center"});
        var first = form.querySelector('input:not([type="hidden"]), select, textarea');
        if (first && first.focus) {
          try { first.focus({preventScroll: true}); } catch (error) { first.focus(); }
        }
      }
      function embedFieldsToLines(fields) {
        if (!Array.isArray(fields)) return "";
        return fields.map(function (field) {
          var name = String(firstValue(field && field.name, "")).replace(/[|]/g, "/");
          var value = String(firstValue(field && field.value, "")).replace(/[|]/g, "/");
          return name + " | " + value + " | " + (field && field.inline ? "true" : "false");
        }).filter(function (line) { return line.trim(); }).join("\n");
      }
      function fillEmbed(template) {
        var form = document.getElementById("embed-template-form");
        if (!form || !template || !Object.keys(template).length) return false;
        var embed = template.embed || {};
        var delivery = template.delivery || {};
        var schedule = template.schedule || {};
        setControl(form, "name", firstValue(template.name, "custom-message"));
        setControl(form, "template_id", firstValue(template.template_id, template.id, ""));
        setControl(form, "content_mode", firstValue(delivery.content_mode, template.content_mode, "embed"));
        setControl(form, "channel_key", firstValue(delivery.channel_key, template.channel_key, ""));
        setControl(form, "title", firstValue(embed.title, template.title, ""));
        setControl(form, "colour", firstValue(embed.colour, embed.color, template.colour, "#8d963e"));
        setControl(form, "author_name", firstValue(embed.author && embed.author.name, template.author_name, ""));
        setControl(form, "author_icon_url", firstValue(embed.author && embed.author.icon_url, template.author_icon_url, ""));
        setControl(form, "thumbnail_url", firstValue(embed.thumbnail_url, template.thumbnail_url, ""));
        setControl(form, "image_url", firstValue(embed.image_url, template.image_url, ""));
        setControl(form, "footer_text", firstValue(embed.footer && embed.footer.text, template.footer_text, ""));
        setControl(form, "footer_icon_url", firstValue(embed.footer && embed.footer.icon_url, template.footer_icon_url, ""));
        setControl(form, "mention_mode", firstValue(delivery.mention_mode, template.mention_mode, "none"));
        setControl(form, "mention_role_id", firstValue(delivery.mention_role_id, template.mention_role_id, ""));
        setControl(form, "schedule_type", firstValue(schedule.type, template.schedule_type, "manual"));
        setControl(form, "schedule_time", firstValue(schedule.time, template.schedule_time, ""));
        setControl(form, "event_filter", firstValue(schedule.event_filter, template.event_filter, ""));
        setControl(form, "event_minimum", firstValue(schedule.event_minimum, template.event_minimum, 0));
        setControl(form, "interval_minutes", firstValue(schedule.interval_minutes, template.interval_minutes, 60));
        setControl(form, "timezone", firstValue(schedule.timezone, template.timezone, "Europe/Dublin"));
        setControl(form, "button_label", firstValue(delivery.button_label, template.button_label, ""));
        setControl(form, "button_url", firstValue(delivery.button_url, template.button_url, ""));
        setControl(form, "body", firstValue(embed.description, template.body, ""));
        setControl(form, "fields_lines", embedFieldsToLines(embed.fields));
        var result = form.querySelector(".result");
        if (result) result.textContent = "Loaded for editing.";
        scrollToForm(form);
        return true;
      }
      function fillRecord(button) {
        var form = document.getElementById(button.getAttribute("data-form-id") || "");
        var record = readCardJson(button, "[data-dashboard-record-card]", "[data-dashboard-record-json]");
        if (!form || !record || !Object.keys(record).length) return false;
        Object.keys(record).forEach(function (key) {
          if (record[key] && typeof record[key] === "object") return;
          setControl(form, key, record[key]);
        });
        var result = form.querySelector(".result");
        if (result) result.textContent = "Loaded for editing.";
        scrollToForm(form);
        return true;
      }
      function zoneFromButton(button) {
        var row = closest(button, "[data-zone-row]");
        var script = row ? row.querySelector("[data-zone-json]") : null;
        if (!script && button.getAttribute("data-zone-key")) {
          var key = button.getAttribute("data-zone-key");
          Array.prototype.slice.call(document.querySelectorAll("[data-zone-json]")).forEach(function (item) {
            if (!script && item.getAttribute("data-zone-key") === key) script = item;
          });
        }
        if (script) return parseJson(script.textContent);
        return parseJson(button.getAttribute("data-zone") || "{}");
      }
      function fillZone(button) {
        var form = document.getElementById("zone-edit-form");
        var zone = zoneFromButton(button);
        if (!form || !zone || !Object.keys(zone).length) return false;
        setControl(form, "zone_id", firstValue(zone.id, zone.name, ""));
        setControl(form, "name", firstValue(zone.name, ""));
        setControl(form, "zone_type", firstValue(zone.zone_type, zone.type, "radar"));
        setControl(form, "x", Number(firstValue(zone.x, zone.center_x, 0)));
        setControl(form, "y", Number(firstValue(zone.z, zone.y, zone.center_z, zone.center_y, 0)));
        setControl(form, "shape", firstValue(zone.shape, "circle"));
        setControl(form, "radius", firstValue(zone.radius, zone.radius_m, 250));
        setControl(form, "radius_slider", firstValue(zone.radius, zone.radius_m, 250));
        setControl(form, "channel_key", firstValue(zone.channel_key, zone.alert_channel_id, zone.report_channel_id, ""));
        setControl(form, "role_id", firstValue(zone.role_id, zone.mention_role_id, ""));
        setControl(form, "faction_name", firstValue(zone.faction_name, zone.faction, ""));
        setControl(form, "colour", firstValue(zone.display_colour, button.getAttribute("data-zone-colour"), zone.colour, zone.color, "#8d963e"));
        setControl(form, "enabled", zone.enabled === false ? "false" : "true");
        setControl(form, "action", firstValue(zone.action, "none"));
        setControl(form, "ban_type", firstValue(zone.ban_type, "temp"));
        setControl(form, "ban_duration_minutes", firstValue(zone.ban_duration_minutes, 1440));
        setControl(form, "trigger_territory", firstValue(zone.trigger_territory, "inside"));
        setControl(form, "triggers", Array.isArray(zone.triggers) ? zone.triggers.join(",") : firstValue(zone.triggers, ""));
        setControl(form, "ignored_gamertags", Array.isArray(zone.ignored_gamertags) ? zone.ignored_gamertags.join(",") : firstValue(zone.ignored_gamertags, ""));
        var save = form.querySelector("[data-zone-save-button]");
        var remove = form.querySelector("[data-zone-delete-current]");
        var readout = form.querySelector("[data-map-readout]");
        if (save) save.textContent = "Save Zone Changes";
        if (remove) remove.disabled = false;
        if (readout) readout.textContent = "Editing " + firstValue(zone.name, "zone") + " - save to update this radar/zone.";
        Array.prototype.slice.call(document.querySelectorAll("[data-zone-edit].editing")).forEach(function (item) { item.classList.remove("editing"); });
        Array.prototype.slice.call(document.querySelectorAll("[data-zone-edit]")).forEach(function (item) {
          if (item.getAttribute("data-zone-key") && item.getAttribute("data-zone-key") === button.getAttribute("data-zone-key")) item.classList.add("editing");
        });
        var map = closest(button, "[data-zone-map]");
        if (map) showZonePopover(map, form, zone, button);
        else scrollToForm(form);
        return true;
      }
      function escapeText(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, "");
      }
      function escapeAttr(value) {
        return String(value == null ? "" : value).replace(/"/g, "&quot;");
      }
      function showZonePopover(map, form, zone, button) {
        var popover = map.querySelector("[data-zone-popover]");
        if (!popover) return;
        var size = Number(map.getAttribute("data-map-size") || 15360);
        var x = Number(firstValue(zone.x, zone.center_x, form.elements.x && form.elements.x.value, 0));
        var z = Number(firstValue(zone.z, zone.y, zone.center_z, zone.center_y, form.elements.y && form.elements.y.value, 0));
        var xPercent = Math.max(2, Math.min(98, (x / size) * 100));
        var yPercent = Math.max(8, Math.min(92, 100 - ((z / size) * 100)));
        var radius = firstValue(zone.radius, zone.radius_m, form.elements.radius && form.elements.radius.value, 250);
        popover.style.left = xPercent + "%";
        popover.style.top = yPercent + "%";
        popover.setAttribute("data-side", xPercent > 62 ? "left" : "right");
        popover.innerHTML =
          "<strong>" + escapeText(firstValue(zone.name, "Zone")) + "</strong>" +
          "<span>" + escapeText(firstValue(zone.zone_type, zone.type, "radar")) + " zone - X " + Math.round(x) + ", Z " + Math.round(z) + " - radius " + escapeText(radius) + "m</span>" +
          "<div class=\"zone-popover-actions\">" +
          "<button type=\"button\" data-zone-popover-save>Save Changes</button>" +
          "<button type=\"button\" data-zone-delete data-zone-key=\"" + escapeAttr(button.getAttribute("data-zone-key")) + "\" data-zone-id=\"" + escapeAttr(firstValue(zone.id, "")) + "\" data-zone-type=\"" + escapeAttr(firstValue(zone.zone_type, zone.type, "")) + "\" data-zone-name=\"" + escapeAttr(firstValue(zone.name, "")) + "\" data-guild-id=\"" + escapeAttr(form.elements.guild_id && form.elements.guild_id.value) + "\">Delete</button>" +
          "<button type=\"button\" data-zone-popover-close>Close</button>" +
          "</div>";
        popover.hidden = false;
      }
      function applyZonePopoverFields(popover, form) {
        if (!popover || !form) return;
        Array.prototype.slice.call(popover.querySelectorAll("[data-zone-popover-field]")).forEach(function (field) {
          var name = field.getAttribute("data-zone-popover-field");
          if (!name) return;
          setControl(form, name, field.value);
          if (name === "radius") setControl(form, "radius_slider", field.value);
          if (name === "y") setControl(form, "z", field.value);
        });
      }
      function zoneOption(value, label, selected) {
        return "<option value=\"" + escapeAttr(value) + "\" " + (String(selected) === String(value) ? "selected" : "") + ">" + escapeText(label) + "</option>";
      }
      function showZoneDraftPopover(map, form, zone) {
        var popover = map.querySelector("[data-zone-popover]");
        if (!popover) return;
        var size = Number(map.getAttribute("data-map-size") || 15360);
        var x = Number(firstValue(zone.x, form.elements.x && form.elements.x.value, 0));
        var z = Number(firstValue(zone.z, zone.y, form.elements.y && form.elements.y.value, 0));
        var xPercent = Math.max(2, Math.min(98, (x / size) * 100));
        var yPercent = Math.max(8, Math.min(92, 100 - ((z / size) * 100)));
        var type = firstValue(zone.zone_type, form.elements.zone_type && form.elements.zone_type.value, "radar");
        var radius = firstValue(zone.radius, form.elements.radius && form.elements.radius.value, 250);
        var colour = firstValue(zone.colour, form.elements.colour && form.elements.colour.value, "#8d963e");
        popover.style.left = xPercent + "%";
        popover.style.top = yPercent + "%";
        popover.style.setProperty("--zone-colour", colour);
        popover.setAttribute("data-side", xPercent > 62 ? "left" : "right");
        popover.setAttribute("data-zone-draft", "true");
        popover.innerHTML =
          "<strong>New zone draft</strong>" +
          "<span>Edit this spot, then save it as a new zone.</span>" +
          "<div class=\"zone-popover-grid\">" +
          "<label>Name <input data-zone-popover-field=\"name\" value=\"" + escapeAttr(firstValue(zone.name, "New " + type + " zone")) + "\"></label>" +
          "<label>Type <select data-zone-popover-field=\"zone_type\">" +
          zoneOption("radar", "Radar", type) + zoneOption("safe", "Safe", type) + zoneOption("pvp", "PVP", type) + zoneOption("action", "Action", type) + zoneOption("faction", "Faction", type) + zoneOption("custom", "Custom", type) +
          "</select></label>" +
          "<label>X <input data-zone-popover-field=\"x\" type=\"number\" value=\"" + Math.round(x) + "\"></label>" +
          "<label>Z <input data-zone-popover-field=\"y\" type=\"number\" value=\"" + Math.round(z) + "\"></label>" +
          "<label>Radius <input data-zone-popover-field=\"radius\" type=\"number\" min=\"10\" step=\"10\" value=\"" + escapeAttr(radius) + "\"></label>" +
          "<label>Colour <input data-zone-popover-field=\"colour\" type=\"color\" value=\"" + escapeAttr(colour) + "\"></label>" +
          "</div>" +
          "<div class=\"zone-popover-actions\">" +
          "<button type=\"button\" data-zone-popover-save>Save Zone</button>" +
          "<button type=\"button\" data-zone-popover-close>Close</button>" +
          "</div>";
        popover.hidden = false;
      }
      function draftZoneFromMap(map, event) {
        if (!map || closest(event.target, "[data-zone-edit]") || closest(event.target, "[data-zone-popover]")) return false;
        var now = Date.now ? Date.now() : new Date().getTime();
        var lastDraft = Number(map.getAttribute("data-zone-draft-at") || 0);
        if (event.type === "click" && lastDraft && now - lastDraft < 350) return false;
        var form = closest(map, "form");
        if (!form || !form.elements) return false;
        var rect = map.getBoundingClientRect();
        if (!rect.width || !rect.height) return false;
        var size = Number(map.getAttribute("data-map-size") || 15360);
        var xPercent = Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100));
        var yPercent = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));
        var x = Math.max(0, Math.min(size, Math.round((xPercent / 100) * size)));
        var z = Math.max(0, Math.min(size, Math.round((1 - (yPercent / 100)) * size)));
        if (form.elements.map_render_width) form.elements.map_render_width.value = String(Math.round(rect.width));
        if (form.elements.map_render_height) form.elements.map_render_height.value = String(Math.round(rect.height));
        if (form.elements.map_pointer_x) form.elements.map_pointer_x.value = String(Math.max(0, Math.min(rect.width, event.clientX - rect.left)));
        if (form.elements.map_pointer_y) form.elements.map_pointer_y.value = String(Math.max(0, Math.min(rect.height, event.clientY - rect.top)));
        if (form.elements.map_percent_x) form.elements.map_percent_x.value = xPercent.toFixed(6);
        if (form.elements.map_percent_y) form.elements.map_percent_y.value = yPercent.toFixed(6);
        var type = firstValue(form.elements.zone_type && form.elements.zone_type.value, "radar");
        var colour = firstValue(form.elements.colour && form.elements.colour.value, "#8d963e");
        setControl(form, "zone_id", "");
        setControl(form, "name", "New " + type + " zone");
        setControl(form, "x", x);
        setControl(form, "y", z);
        setControl(form, "enabled", "true");
        setControl(form, "action", "none");
        Array.prototype.slice.call(document.querySelectorAll("[data-zone-edit].editing")).forEach(function (item) { item.classList.remove("editing"); });
        var save = form.querySelector("[data-zone-save-button]");
        var remove = form.querySelector("[data-zone-delete-current]");
        var readout = form.querySelector("[data-map-readout]");
        if (save) save.textContent = "Save Zone";
        if (remove) remove.disabled = true;
        if (readout) readout.textContent = "New zone X " + x + ", Z " + z + " - click Save Zone in the popup to create it.";
        var cursor = map.querySelector(".zone-cursor");
        if (!cursor) {
          cursor = document.createElement("span");
          cursor.className = "zone-cursor";
          map.appendChild(cursor);
        }
        cursor.style.left = xPercent + "%";
        cursor.style.top = yPercent + "%";
        cursor.style.setProperty("--zone-colour", colour);
        var circle = map.querySelector(".zone-preview-circle");
        if (!circle) {
          circle = document.createElement("span");
          circle.className = "zone-preview-circle";
          map.appendChild(circle);
        }
        var radius = Number((form.elements.radius && form.elements.radius.value) || (form.elements.draft_radius && form.elements.draft_radius.value) || 250);
        var circleWidth = ((Math.max(10, radius) * 2) / size) * rect.width;
        circle.style.width = Math.max(12, circleWidth) + "px";
        circle.style.height = Math.max(12, circleWidth) + "px";
        circle.style.left = xPercent + "%";
        circle.style.top = yPercent + "%";
        circle.style.setProperty("--zone-colour", colour);
        circle.style.display = form.elements.shape && form.elements.shape.value === "boundary" ? "none" : "";
        showZoneDraftPopover(map, form, {name: "New " + type + " zone", zone_type: type, x: x, z: z, radius: form.elements.radius && form.elements.radius.value, colour: colour});
        map.setAttribute("data-zone-draft-at", String(now));
        return true;
      }
      window.wanderingDraftZoneFromMap = function (map, event) {
        return true;
      };
      function postJson(route, payload, done) {
        var token = new URLSearchParams(window.location.search).get("token");
        var xhr = new XMLHttpRequest();
        xhr.open("POST", secureUrl(route + (token ? "?token=" + encodeURIComponent(token) : "")), true);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.setRequestHeader("Accept", "application/json");
        xhr.setRequestHeader("X-Requested-With", "fetch");
        xhr.onreadystatechange = function () {
          if (xhr.readyState !== 4) return;
          if (xhr.status >= 200 && xhr.status < 300) done();
          else window.alert("Dashboard request failed: " + (xhr.responseText || xhr.status));
        };
        xhr.send(JSON.stringify(payload));
      }
      document.addEventListener("click", function (event) {
        var close = closest(event.target, "[data-zone-popover-close]");
        if (close) {
          stop(event);
          var popover = closest(close, "[data-zone-popover]");
          if (popover) popover.hidden = true;
          return;
        }
        var save = closest(event.target, "[data-zone-popover-save]");
        if (save) {
          stop(event);
          var form = document.getElementById("zone-edit-form");
          applyZonePopoverFields(closest(save, "[data-zone-popover]"), form);
          if (form && form.requestSubmit) form.requestSubmit(form.querySelector("[data-zone-save-button]") || undefined);
          else if (form && form.querySelector("[data-zone-save-button]")) form.querySelector("[data-zone-save-button]").click();
          return;
        }
        var embedEdit = closest(event.target, "[data-embed-template-edit]");
        if (embedEdit) {
          if (!fillEmbed(readCardJson(embedEdit, "[data-embed-template-card]", "[data-embed-template-json]"))) return;
          stop(event);
          return;
        }
        var recordEdit = closest(event.target, "[data-dashboard-record-edit]");
        if (recordEdit) {
          if (!fillRecord(recordEdit)) return;
          stop(event);
          return;
        }
        var zoneEdit = closest(event.target, "[data-zone-edit]");
        if (zoneEdit) {
          return;
        }
        var embedDelete = closest(event.target, "[data-embed-template-delete]");
        if (embedDelete) {
          if (closest(embedDelete, "form")) return;
          stop(event);
          if (embedDelete.getAttribute("data-confirm") && !window.confirm(embedDelete.getAttribute("data-confirm"))) return;
          var embedCard = closest(embedDelete, "[data-embed-template-card]");
          postJson("/api/admin/embed-template-action", {
            action: "delete",
            template_id: firstValue(embedDelete.getAttribute("data-template-id"), embedCard && embedCard.getAttribute("data-template-id"), ""),
            guild_id: firstValue(embedDelete.getAttribute("data-guild-id"), "{{ server.guild_id if server else '' }}"),
            dashboard_mode: "{{ mode }}"
          }, function () { if (embedCard) embedCard.parentNode.removeChild(embedCard); });
          return;
        }
        var recordDelete = closest(event.target, "[data-dashboard-record-delete]");
        if (recordDelete) {
          if (closest(recordDelete, "form")) return;
          stop(event);
          if (recordDelete.getAttribute("data-confirm") && !window.confirm(recordDelete.getAttribute("data-confirm"))) return;
          var recordCard = closest(recordDelete, "[data-dashboard-record-card]");
          postJson("/api/admin/dashboard-record-action", {
            action: "delete",
            section: firstValue(recordDelete.getAttribute("data-section"), recordCard && recordCard.getAttribute("data-section"), ""),
            record_id: firstValue(recordDelete.getAttribute("data-record-id"), recordCard && recordCard.getAttribute("data-record-id"), ""),
            guild_id: firstValue(recordDelete.getAttribute("data-guild-id"), "{{ server.guild_id if server else '' }}"),
            dashboard_mode: "{{ mode }}"
          }, function () { if (recordCard) recordCard.parentNode.removeChild(recordCard); });
          return;
        }
        var zoneDelete = closest(event.target, "[data-zone-delete]");
        if (zoneDelete) {
          if (closest(zoneDelete, "form")) return;
          stop(event);
          var zone = zoneFromButton(zoneDelete);
          var name = firstValue(zoneDelete.getAttribute("data-zone-name"), zone.name, "this zone");
          if (!window.confirm("Delete " + name + " from this server?")) return;
          var zoneForm = document.getElementById("zone-edit-form");
          postJson("/api/admin/zone-action", {
            action: "delete",
            guild_id: firstValue(zoneDelete.getAttribute("data-guild-id"), zoneForm && zoneForm.elements.guild_id && zoneForm.elements.guild_id.value, "{{ server.guild_id if server else '' }}"),
            zone_id: firstValue(zoneDelete.getAttribute("data-zone-id"), zone.id, zoneForm && zoneForm.elements.zone_id && zoneForm.elements.zone_id.value, ""),
            zone_type: firstValue(zoneDelete.getAttribute("data-zone-type"), zone.zone_type, zone.type, zoneForm && zoneForm.elements.zone_type && zoneForm.elements.zone_type.value, ""),
            name: name,
            dashboard_mode: "{{ mode }}"
          }, function () {
            var row = closest(zoneDelete, "[data-zone-row]");
            if (row) row.parentNode.removeChild(row);
            else window.location.reload();
          });
        }
      }, true);
    }());
  </script>
  <script>
    (function () {
      try {
        var serverTheme = "{{ dashboard_theme }}";
        var theme = "command";
        document.documentElement.dataset.theme = theme === "default" ? "" : theme;
      } catch (error) {}
    })();
  </script>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050806;
      --panel: #172016;
      --panel-2: #222d1b;
      --panel-3: #10180f;
      --line: rgba(209, 203, 145, .32);
      --text: #f3ecd9;
      --muted: #c4bda7;
      --dim: #8f8a6e;
      --olive: #8d963e;
      --gold: #d5b45f;
      --red: #ed3853;
      --accent: var(--gold);
      --map-image: linear-gradient(transparent, transparent);
    }
    html[data-theme="forest"], body[data-theme="forest"] { --bg: #07100b; --panel: #18251a; --panel-2: #26351f; --panel-3: #101910; --line: rgba(143, 201, 128, .34); --text: #f1f7e9; --muted: #c8d8bb; --olive: #7ca45a; --gold: #c8d46a; --accent: #9fcd73; }
    html[data-theme="amber"], body[data-theme="amber"] { --bg: #120d06; --panel: #241b10; --panel-2: #342514; --panel-3: #1a130b; --line: rgba(225, 178, 94, .36); --text: #fff1d8; --muted: #dec8a4; --olive: #a47d3a; --gold: #e3b65f; --accent: #e3b65f; }
    html[data-theme="steel"], body[data-theme="steel"] { --bg: #071014; --panel: #142027; --panel-2: #1f3038; --panel-3: #0d171c; --line: rgba(134, 191, 210, .34); --text: #edf7fb; --muted: #b9ced6; --olive: #5b8ea0; --gold: #79c7dd; --accent: #79c7dd; }
    html[data-theme="highland"], body[data-theme="highland"] { --bg: #0f0d0b; --panel: #211d18; --panel-2: #302a21; --panel-3: #17130f; --line: rgba(198, 169, 121, .35); --text: #f8eddd; --muted: #d4c0a4; --olive: #8b7652; --gold: #d9b779; --accent: #d9b779; }
    html[data-theme="daylight"], body[data-theme="daylight"] { color-scheme: light; --bg: #e9edde; --panel: #fbfff5; --panel-2: #dfe8ce; --panel-3: #f4f8eb; --line: rgba(74, 98, 55, .32); --text: #182013; --muted: #4e6044; --dim: #6f7d65; --olive: #718948; --gold: #9f7c2c; --accent: #6f8f3f; }
    html[data-theme="sandstorm"], body[data-theme="sandstorm"] { color-scheme: light; --bg: #efe3c9; --panel: #fff7e7; --panel-2: #e6d0a3; --panel-3: #f6eddc; --line: rgba(121, 87, 43, .34); --text: #261b0f; --muted: #6b5132; --dim: #8d7652; --olive: #8d7b39; --gold: #b77c2c; --accent: #b77c2c; }
    html[data-theme="midnight"], body[data-theme="midnight"] { --bg: #05070d; --panel: #121726; --panel-2: #202940; --panel-3: #0b1020; --line: rgba(130, 153, 216, .34); --text: #f3f7ff; --muted: #bec8e4; --olive: #6878b8; --gold: #94b4ff; --accent: #94b4ff; }
    html[data-theme="bloodmoon"], body[data-theme="bloodmoon"] { --bg: #100607; --panel: #241012; --panel-2: #38191a; --panel-3: #180a0c; --line: rgba(226, 92, 92, .34); --text: #fff0ed; --muted: #dfb7b2; --olive: #a94444; --gold: #ffb45d; --accent: #ff866d; }
    html[data-theme="radioactive"], body[data-theme="radioactive"] { --bg: #061006; --panel: #10210c; --panel-2: #18300f; --panel-3: #0a1708; --line: rgba(159, 255, 74, .32); --text: #f2ffe8; --muted: #c4ddb1; --olive: #5f9b36; --gold: #b6ff4d; --accent: #7cff5b; }
    html[data-theme="arctic"], body[data-theme="arctic"] { --bg: #071014; --panel: #10212a; --panel-2: #183444; --panel-3: #0b1820; --line: rgba(164, 225, 255, .34); --text: #edfaff; --muted: #bbd9e6; --olive: #4f91a8; --gold: #a7e5ff; --accent: #6fd3ff; }
    html[data-theme="toxic"], body[data-theme="toxic"] { --bg: #0e0f05; --panel: #1b2109; --panel-2: #2a3210; --panel-3: #111606; --line: rgba(211, 231, 82, .34); --text: #fbffd9; --muted: #d3dca0; --olive: #8fa23b; --gold: #e1f25a; --accent: #c6ef3e; }
    html[data-theme="violet"], body[data-theme="violet"] { --bg: #0c0712; --panel: #1c1228; --panel-2: #2b1b3d; --panel-3: #130c1d; --line: rgba(196, 151, 255, .32); --text: #fbf4ff; --muted: #d5c0e8; --olive: #7951aa; --gold: #d6a2ff; --accent: #b889ff; }
    html[data-theme="rose"], body[data-theme="rose"] { --bg: #13070c; --panel: #26111a; --panel-2: #3a1a27; --panel-3: #1a0b11; --line: rgba(255, 144, 181, .34); --text: #fff2f6; --muted: #e3b8c7; --olive: #9e4c68; --gold: #ff9abc; --accent: #ff719e; }
    html[data-theme="command"], body[data-theme="command"] { --bg: #03070a; --panel: #091014; --panel-2: #132127; --panel-3: #071114; --line: rgba(103, 245, 231, .30); --text: #effcff; --muted: #a8bec3; --dim: #6f858b; --olive: #94ff64; --gold: #67f5e7; --accent: #67f5e7; }
    html { scroll-behavior: smooth; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background: linear-gradient(180deg, #10150d 0%, var(--bg) 100%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow-x: hidden;
    }
    body[data-theme="command"] { background: linear-gradient(180deg, #071014 0%, var(--bg) 100%); }
    a { color: var(--gold); text-decoration: none; }
    h1, h2, h3, p { margin-top: 0; }
    header {
      position: sticky;
      top: 0;
      z-index: 3;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: .85rem clamp(1rem, 4vw, 2rem);
      background: rgba(5, 8, 6, .92);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(16px);
    }
    body[data-theme="command"] header { background: rgba(3, 7, 10, .94); }
    .brand { display: flex; align-items: center; gap: .75rem; min-width: 0; }
    .brand img { width: 3rem; height: 3rem; border-radius: .75rem; object-fit: cover; }
    .brand strong { display: block; text-transform: uppercase; letter-spacing: .08em; }
    .brand span, .muted { color: var(--muted); }
    .theme-picker { display: flex; gap: .35rem; align-items: center; justify-content: flex-end; flex-wrap: wrap; max-width: min(42rem, 100%); }
    .theme-picker label { display: flex; align-items: center; gap: .35rem; color: var(--muted); font-size: .85rem; }
    .theme-picker select { min-height: 2rem; padding: .25rem .55rem; width: 9.5rem; }
    .theme-picker button { width: 2rem; height: 2rem; padding: 0; border-radius: 999px; border-color: var(--line); color: transparent; overflow: hidden; }
    .theme-picker button[data-theme-choice="default"] { background: linear-gradient(135deg, #8d963e 0 50%, #d5b45f 50%); }
    .theme-picker button[data-theme-choice="forest"] { background: linear-gradient(135deg, #7ca45a 0 50%, #c8d46a 50%); }
    .theme-picker button[data-theme-choice="amber"] { background: linear-gradient(135deg, #a47d3a 0 50%, #e3b65f 50%); }
    .theme-picker button[data-theme-choice="steel"] { background: linear-gradient(135deg, #5b8ea0 0 50%, #79c7dd 50%); }
    .theme-picker button[data-theme-choice="highland"] { background: linear-gradient(135deg, #8b7652 0 50%, #d9b779 50%); }
    .theme-picker button[data-theme-choice="daylight"] { background: linear-gradient(135deg, #fbfff5 0 50%, #718948 50%); }
    .theme-picker button[data-theme-choice="sandstorm"] { background: linear-gradient(135deg, #fff7e7 0 50%, #b77c2c 50%); }
    .theme-picker button[data-theme-choice="midnight"] { background: linear-gradient(135deg, #121726 0 50%, #94b4ff 50%); }
    .theme-picker button[data-theme-choice="bloodmoon"] { background: linear-gradient(135deg, #38191a 0 50%, #ff866d 50%); }
    .theme-picker button[data-theme-choice="radioactive"] { background: linear-gradient(135deg, #10210c 0 50%, #b6ff4d 50%); }
    .theme-picker button[data-theme-choice="arctic"] { background: linear-gradient(135deg, #10212a 0 50%, #a7e5ff 50%); }
    .theme-picker button[data-theme-choice="toxic"] { background: linear-gradient(135deg, #1b2109 0 50%, #e1f25a 50%); }
    .theme-picker button[data-theme-choice="violet"] { background: linear-gradient(135deg, #1c1228 0 50%, #d6a2ff 50%); }
    .theme-picker button[data-theme-choice="rose"] { background: linear-gradient(135deg, #26111a 0 50%, #ff9abc 50%); }
    .theme-picker button[data-theme-choice="command"] { background: linear-gradient(135deg, #071114 0 50%, #67f5e7 50%); }
    .theme-picker button.active { box-shadow: 0 0 0 2px var(--text); }
    nav { display: flex; flex-wrap: wrap; gap: .45rem; }
    nav a, button, .button, .tab-link {
      border: 1px solid var(--line);
      border-radius: .5rem;
      background: var(--panel-2);
      color: var(--text);
      padding: .6rem .8rem;
      font-weight: 800;
      cursor: pointer;
    }
    main { max-width: 1440px; margin: 0 auto; padding: 1.1rem clamp(1rem, 4vw, 2rem) 2rem; display: grid; gap: 1rem; }
    .hero, .card, .wide, .section-panel {
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(243, 236, 217, .05), rgba(243, 236, 217, .015)), var(--panel);
      border-radius: .5rem;
      box-shadow: 0 1rem 2.5rem rgba(0, 0, 0, .3);
    }
    .hero { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1rem; align-items: center; padding: clamp(1rem, 4vw, 2rem); }
    h1 { margin: .2rem 0 .5rem; font-size: clamp(2rem, 5vw, 4.25rem); line-height: .95; text-transform: uppercase; letter-spacing: 0; }
    .hero img { width: min(11rem, 35vw); aspect-ratio: 1; object-fit: cover; border-radius: 50%; border: 2px solid var(--gold); }
    .stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .75rem; }
    .stat, .card { padding: 1rem; }
    .stat { border: 1px solid var(--line); border-radius: .5rem; background: var(--panel-3); }
    .stat span { display: block; color: var(--muted); font-size: .8rem; text-transform: uppercase; }
    .stat strong { display: block; color: var(--accent); font-size: 1.8rem; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .85rem; }
    .servers { display: grid; gap: .85rem; }
    .server-head { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
    .pills { display: flex; flex-wrap: wrap; gap: .4rem; }
    .pill-row { display: flex; flex-wrap: wrap; gap: .45rem; align-items: center; justify-content: flex-end; }
    .pill { border: 1px solid var(--line); border-radius: 999px; padding: .28rem .55rem; color: var(--muted); background: #0a0f0b; font-size: .8rem; }
    .ok { color: #eef7c6; background: rgba(141, 150, 62, .22); }
    .bad { color: #ffd8df; background: rgba(237, 56, 83, .16); }
    .columns { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; margin-top: .85rem; }
    ul { margin: .4rem 0 0; padding: 0; list-style: none; display: grid; gap: .35rem; }
    li { display: flex; justify-content: space-between; gap: .75rem; color: var(--muted); }
    code { background: #0a0f0b; border: 1px solid var(--line); border-radius: .35rem; padding: .1rem .3rem; }
    form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
    label { display: grid; gap: .25rem; color: var(--muted); font-size: .9rem; }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: .45rem;
      background: #080d09;
      color: var(--text);
      padding: .65rem .75rem;
    }
    body[data-theme="daylight"] input, body[data-theme="daylight"] textarea, body[data-theme="daylight"] select,
    body[data-theme="sandstorm"] input, body[data-theme="sandstorm"] textarea, body[data-theme="sandstorm"] select { background: #fffdf4; color: var(--text); }
    textarea { min-height: 7rem; resize: vertical; }
    input[readonly] { color: var(--gold); background: rgba(213, 180, 95, .08); cursor: default; }
    .full { grid-column: 1 / -1; }
    .route-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .4rem; }
    .route-list code { display: block; overflow-wrap: anywhere; }
    .panel-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem; align-items: start; }
    .admin-panel { min-width: 0; border: 1px solid var(--line); border-radius: .5rem; padding: 1rem; background: var(--panel-3); }
    .admin-panel:nth-of-type(2n) { background: color-mix(in srgb, var(--panel-3) 84%, #123b46); }
    .admin-panel:nth-of-type(3n) { background: color-mix(in srgb, var(--panel-3) 86%, #3f3411); }
    body[data-theme="command"] .admin-panel:nth-of-type(2n) { background: color-mix(in srgb, var(--panel-3) 88%, #0c3a3f); }
    body[data-theme="command"] .admin-panel:nth-of-type(3n) { background: color-mix(in srgb, var(--panel-3) 90%, #24410d); }
    body[data-theme="command"] nav a,
    body[data-theme="command"] button,
    body[data-theme="command"] .button,
    body[data-theme="command"] .tab-link { background: color-mix(in srgb, var(--panel-2) 88%, #061013); }
    body[data-theme="command"] .brand img { box-shadow: 0 0 0 1px var(--line), 0 0 22px rgba(103,245,231,.20); }
    body[data-section="pve"] .admin-panel:nth-of-type(3) { --accent: #f2c14e; background: linear-gradient(135deg, rgba(63,49,15,.72), rgba(15,22,18,.94)); }
    body[data-section="pve"] .admin-panel:nth-of-type(4) { --accent: #6fd3ff; background: linear-gradient(135deg, rgba(18,48,58,.72), rgba(15,22,18,.94)); }
    body[data-section="xml-workshop"] .admin-panel:nth-of-type(1) { --accent: #75d89a; background: linear-gradient(135deg, rgba(20,55,34,.72), rgba(15,22,18,.94)); }
    body[data-section="visual-loadout"] .admin-panel:nth-of-type(1) { --accent: #7ec8ff; background: linear-gradient(135deg, rgba(20,48,66,.74), rgba(15,22,18,.94)); }
    body[data-section="visual-loadout"] .admin-panel:nth-of-type(2) { --accent: #f2c14e; background: linear-gradient(135deg, rgba(65,51,15,.74), rgba(15,22,18,.94)); }
    body[data-section="visual-loadout"] .admin-panel:nth-of-type(3) { --accent: #75d89a; background: linear-gradient(135deg, rgba(19,57,34,.74), rgba(15,22,18,.94)); }
    body[data-theme="command"][data-section="visual-loadout"] .admin-panel:nth-of-type(1),
    body[data-theme="command"][data-section="visual-loadout"] .admin-panel:nth-of-type(2),
    body[data-theme="command"][data-section="visual-loadout"] .admin-panel:nth-of-type(3) { --accent: #67f5e7; background: linear-gradient(135deg, rgba(7,32,37,.82), rgba(5,10,12,.96)); }
    .command-sidebar, .command-overview, .command-loadout-stage, .command-status-bar { display: none; }
    body[data-theme="command"] {
      --sidebar-w: 13.25rem;
      color: #dbe8eb;
      background: #061014;
    }
    body[data-theme="command"] header {
      left: var(--sidebar-w);
      min-height: 3.8rem;
      padding: .55rem 1rem;
      border-bottom-color: rgba(103,245,231,.16);
      box-shadow: 0 1px 0 rgba(255,255,255,.03), 0 18px 48px rgba(0,0,0,.22);
    }
    body[data-theme="command"] header .brand { display: none; }
    body[data-theme="command"] header > nav { display: none; }
    body[data-theme="command"] .theme-picker {
      margin-left: auto;
      max-width: none;
      justify-content: flex-end;
    }
    body[data-theme="command"] .theme-picker label { text-transform: none; }
    body[data-theme="command"] .theme-picker select {
      width: 8.2rem;
      border-radius: .45rem;
      background: #081216;
    }
    body[data-theme="command"] .theme-picker button {
      width: 1.55rem;
      height: 1.55rem;
      border-color: rgba(255,255,255,.18);
    }
    body[data-theme="command"] main {
      max-width: none;
      margin-left: var(--sidebar-w);
      padding: 4.35rem .9rem 2.9rem;
      gap: .9rem;
      overflow-x: hidden;
    }
    body[data-theme="command"] .hero,
    body[data-theme="command"] .stats,
    body[data-theme="command"] .category-grid { display: none; }
    body[data-theme="command"][data-section="overview"] main > .grid,
    body[data-theme="command"][data-section="overview"] main > .servers { display: none; }
    body[data-theme="command"] .theme-picker button:not([data-theme-choice="command"]) {
      display: none;
    }
    body[data-theme="command"] .command-sidebar {
      position: fixed;
      inset: 0 auto 0 0;
      z-index: 6;
      display: flex;
      flex-direction: column;
      width: var(--sidebar-w);
      padding: .9rem .85rem;
      border-right: 1px solid rgba(103,245,231,.15);
      background: linear-gradient(180deg, #0a1519 0%, #050b0e 100%);
      box-shadow: 18px 0 55px rgba(0,0,0,.35);
      overflow-y: auto;
    }
    .command-logo {
      display: grid;
      gap: .75rem;
      margin-bottom: .8rem;
    }
    .command-logo img {
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: contain;
      border: 1px solid rgba(255,255,255,.58);
      border-radius: .7rem;
      background: radial-gradient(circle at center, rgba(103,245,231,.08), rgba(3,10,13,.58));
      box-shadow: 0 20px 40px rgba(0,0,0,.34), 0 0 0 1px rgba(103,245,231,.10);
    }
    .command-logo strong { font-size: .98rem; }
    .command-logo small { color: var(--muted); }
    .command-status { display: flex; align-items: center; gap: .35rem; color: #8ded63; font-size: .74rem; font-weight: 900; text-transform: uppercase; }
    .command-dot { width: .48rem; height: .48rem; border-radius: 50%; background: #8ded63; box-shadow: 0 0 12px rgba(141,237,99,.65); }
    .command-server-form {
      display: grid;
      gap: .4rem;
      margin: 0 0 .7rem;
      padding: .65rem;
      border: 1px solid rgba(103,245,231,.15);
      border-radius: .55rem;
      background: rgba(3,12,15,.72);
    }
    .command-server-form label { gap: .35rem; color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; }
    .command-server-form select {
      min-height: 2.35rem;
      width: 100%;
      border-color: rgba(103,245,231,.24);
      background: #061114;
      color: #effcff;
      font-size: .86rem;
    }
    .command-server-form button {
      min-height: 2rem;
      padding: .35rem .5rem;
      font-size: .76rem;
    }
    .command-login-actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: .35rem;
      margin-bottom: .75rem;
    }
    .command-login-actions a {
      display: flex;
      align-items: center;
      min-height: 2.15rem;
      justify-content: center;
      padding: .45rem .5rem;
      border: 1px solid rgba(103,245,231,.18);
      border-radius: .45rem;
      background: rgba(10,25,31,.72);
      color: #cbdadd;
      font-size: .76rem;
      font-weight: 800;
      text-align: center;
    }
    .command-login-actions a:hover { border-color: rgba(103,245,231,.34); color: #effcff; }
    .command-side-nav { display: grid; gap: .35rem; margin-top: .55rem; }
    .command-side-nav a,
    .command-quick a {
      display: flex;
      align-items: center;
      gap: .58rem;
      min-height: 2.45rem;
      padding: .55rem .7rem;
      border: 1px solid transparent;
      border-radius: .45rem;
      color: #cbdadd;
      background: transparent;
      font-size: .85rem;
      font-weight: 700;
    }
    .command-side-nav a.active,
    .command-side-nav a:hover,
    .command-quick a:hover {
      border-color: rgba(103,245,231,.20);
      background: linear-gradient(90deg, rgba(21,205,198,.28), rgba(18,32,38,.45));
      color: #effcff;
    }
    .command-quick {
      display: grid;
      gap: .35rem;
      margin-top: auto;
      padding-top: .9rem;
      border-top: 1px solid rgba(103,245,231,.13);
    }
    .command-quick span {
      color: var(--muted);
      font-size: .72rem;
      text-transform: uppercase;
      letter-spacing: .08em;
    }
    .command-server-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
      gap: .7rem;
    }
    .command-server-card {
      display: grid;
      gap: .55rem;
      min-height: 8.25rem;
      padding: .85rem;
      border: 1px solid rgba(103,245,231,.14);
      border-radius: .55rem;
      background: linear-gradient(180deg, rgba(10,25,31,.78), rgba(2,9,11,.9));
      color: #dbe8eb;
      text-decoration: none;
    }
    .command-server-card:hover,
    .command-server-card.active {
      border-color: rgba(38,239,228,.48);
      background: linear-gradient(180deg, rgba(17,49,57,.9), rgba(2,12,15,.96));
    }
    .command-server-card strong {
      color: #effcff;
      font-size: .95rem;
      overflow-wrap: anywhere;
    }
    .command-server-card small {
      color: #9fb4ba;
      line-height: 1.35;
    }
    .command-server-card .pills {
      justify-content: flex-start;
    }
    body[data-theme="command"] .section-nav {
      position: sticky;
      top: 3.8rem;
      z-index: 4;
      display: flex;
      gap: 1.05rem;
      padding: .45rem 1rem .55rem;
      margin: 0 0 .85rem;
      overflow-x: auto;
      border-bottom: 1px solid rgba(103,245,231,.14);
      background: rgba(6,16,20,.92);
      backdrop-filter: blur(16px);
    }
    body[data-theme="command"] .section-nav .tab-link {
      border: 0;
      border-radius: 0;
      background: transparent;
      color: #9eadb1;
      padding: .65rem .15rem;
      font-size: .75rem;
      text-transform: uppercase;
      letter-spacing: .04em;
      white-space: nowrap;
    }
    body[data-theme="command"] .section-nav .tab-link:hover,
    body[data-theme="command"] .section-nav .tab-link.active {
      color: #26efe4;
      box-shadow: inset 0 -2px 0 #26efe4;
    }
    body[data-theme="command"] .section-panel,
    body[data-theme="command"] .card,
    body[data-theme="command"] .admin-panel,
    body[data-theme="command"] .wide {
      border-color: rgba(103,245,231,.14);
      background: linear-gradient(180deg, rgba(20,34,41,.84), rgba(7,15,18,.96));
      box-shadow: 0 14px 40px rgba(0,0,0,.28);
    }
    body[data-theme="command"] .command-overview {
      display: grid;
      gap: .75rem;
    }
    body[data-theme="command"][data-section="overview"] main > section.grid,
    body[data-theme="command"][data-section="overview"] main > section.servers {
      display: none;
    }
    body[data-theme="command"] .section-nav {
      display: flex;
      flex-wrap: nowrap;
      align-items: center;
      gap: 1rem;
      min-height: 3rem;
      padding: .45rem .9rem;
      max-width: 100%;
      overflow-x: auto;
      overflow-y: hidden;
      scrollbar-width: thin;
      border-color: rgba(103,245,231,.16);
      border-radius: .55rem;
      background: rgba(4,12,15,.68);
      -webkit-overflow-scrolling: touch;
      margin: 0 0 .85rem;
      flex-shrink: 0;
    }
    body[data-theme="command"] .section-nav .tab-link {
      flex: 0 0 auto;
      min-height: 2rem;
      padding: .35rem 0;
      border: 0;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      background: transparent;
      color: #92a8ad;
      font-size: .72rem;
      text-transform: uppercase;
      letter-spacing: .06em;
      box-shadow: none;
    }
    body[data-theme="command"] .section-nav .tab-link:hover,
    body[data-theme="command"] .section-nav .tab-link:focus-visible {
      color: #effcff;
      border-bottom-color: rgba(103,245,231,.55);
    }
    body[data-theme="command"] .section-nav .tab-link.active {
      color: #26efe4;
      border-bottom-color: #26efe4;
    }
    .command-metrics {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: .65rem;
    }
    .command-metric {
      min-height: 5.5rem;
      padding: .85rem 1rem;
      border: 1px solid rgba(103,245,231,.14);
      border-radius: .5rem;
      background: linear-gradient(180deg, rgba(21,35,42,.88), rgba(8,17,21,.98));
    }
    .command-metric span { display: block; color: #94a7ac; font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; }
    .command-metric strong { display: block; margin-top: .25rem; color: #f4fbfc; font-size: 1.9rem; line-height: 1; }
    .command-metric small { display: block; margin-top: .35rem; color: #8ded63; }
    .command-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.28fr) minmax(31rem, .82fr);
      gap: .75rem;
      align-items: start;
    }
    .command-row {
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(18rem, .58fr) minmax(20rem, .72fr);
      gap: .75rem;
      align-items: start;
    }
    .command-card {
      min-width: 0;
      border: 1px solid rgba(103,245,231,.14);
      border-radius: .55rem;
      background: linear-gradient(180deg, rgba(19,32,38,.88), rgba(7,15,18,.98));
      overflow: hidden;
    }
    .command-table-scroll {
      width: 100%;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: thin;
    }
    .command-card-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: .75rem;
      padding: .85rem 1rem;
      border-bottom: 1px solid rgba(103,245,231,.11);
    }
    .command-card-head h2,
    .command-card-head h3 {
      margin: 0;
      font-size: .86rem;
      text-transform: uppercase;
      letter-spacing: .06em;
    }
    .command-table {
      width: 100%;
      min-width: 52rem;
      border-collapse: collapse;
      font-size: .82rem;
    }
    .command-table th,
    .command-table td {
      padding: .72rem .8rem;
      border-bottom: 1px solid rgba(103,245,231,.08);
      text-align: left;
      vertical-align: middle;
      overflow-wrap: anywhere;
    }
    .command-table th:first-child,
    .command-table td:first-child,
    .command-table th:nth-child(5),
    .command-table td:nth-child(5),
    .command-table th:nth-child(6),
    .command-table td:nth-child(6),
    .command-table th:nth-child(7),
    .command-table td:nth-child(7),
    .command-table th:nth-child(8),
    .command-table td:nth-child(8) {
      white-space: nowrap;
    }
    .command-table th { color: #96a7ac; font-size: .68rem; text-transform: uppercase; letter-spacing: .05em; }
    .command-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 6rem;
      max-width: 8.5rem;
      padding: .25rem .55rem;
      border-radius: .28rem;
      background: rgba(47,67,76,.75);
      color: #d9e8eb;
      font-size: .72rem;
      font-weight: 900;
      text-transform: uppercase;
      white-space: nowrap;
      line-height: 1.15;
    }
    .command-badge.ok { background: rgba(72,160,70,.7); }
    .command-badge.warn { background: rgba(168,126,35,.72); }
    .command-badge.info { background: rgba(43,91,136,.72); }
    .command-badge.bad { background: rgba(145,56,56,.72); }
    .command-mini-actions { display: flex; flex-wrap: wrap; gap: .35rem; }
    .command-mini-actions a,
    .command-mini-actions button,
    .command-card .button {
      min-height: 2rem;
      padding: .38rem .6rem;
      border-color: rgba(103,245,231,.18);
      border-radius: .35rem;
      font-size: .78rem;
    }
    .command-loadout {
      display: grid;
      grid-template-columns: minmax(8.5rem, .65fr) minmax(13.5rem, .92fr) minmax(8.5rem, .65fr);
      gap: .75rem;
      padding: .9rem;
      align-items: center;
    }
    .command-paperdoll {
      display: grid;
      place-items: center;
      min-height: 20rem;
      border-radius: .45rem;
      background:
        radial-gradient(circle at 50% 38%, rgba(103,245,231,.22), transparent 34%),
        linear-gradient(180deg, rgba(24,42,49,.62), rgba(4,12,15,.1));
    }
    .command-paperdoll img {
      width: min(15rem, 96%);
      max-height: 19rem;
      object-fit: contain;
      filter: drop-shadow(0 18px 28px rgba(0,0,0,.45));
    }
    .command-character {
      position: relative;
      overflow: visible;
      min-height: 21rem;
      isolation: isolate;
      background: radial-gradient(circle at 50% 42%, rgba(103,245,231,.16), transparent 42%), linear-gradient(180deg, rgba(17,35,42,.72), rgba(3,10,13,.28));
    }
    .command-character::before {
      content: "";
      position: absolute;
      inset: 1rem 12%;
      z-index: -1;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(103,245,231,.20), transparent 68%);
      filter: blur(10px);
    }
    .command-character .command-character-portrait {
      position: relative;
      width: auto;
      max-width: 98%;
      height: min(21rem, 96%);
      max-height: 21rem;
      transform: none;
      object-fit: contain;
      object-position: center bottom;
      filter: drop-shadow(0 24px 32px rgba(0,0,0,.55));
    }
    .command-gear-column { display: grid; gap: .45rem; }
    .command-gear-card {
      min-height: 4.45rem;
      padding: .55rem;
      border: 1px solid rgba(103,245,231,.13);
      border-radius: .38rem;
      background: rgba(2,9,11,.62);
      overflow: hidden;
      text-decoration: none;
    }
    .command-gear-card span { display: block; color: #94a7ac; font-size: .68rem; }
    .command-gear-card strong { display: block; margin-top: .18rem; color: #e8f5f7; font-size: .82rem; overflow-wrap: anywhere; }
    .command-gear-card img { width: 2.35rem; height: 2.35rem; object-fit: contain; float: right; }
    .command-loadout-extra {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: .45rem;
    }
    .command-loadout-extra .command-gear-card {
      min-height: 3.8rem;
    }
    .command-map-card { padding: .65rem; }
    .command-map {
      position: relative;
      min-height: 20.5rem;
      border-radius: .45rem;
      overflow: hidden;
      background: var(--map-image), linear-gradient(135deg, #182a1d, #0b171c);
      background-size: cover;
      background-position: center;
      border: 1px solid rgba(103,245,231,.14);
    }
    .command-map::after {
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      background: rgba(2,12,14,.26);
      box-shadow: inset 0 0 90px rgba(0,0,0,.36);
    }
    .command-zone-dot {
      position: absolute;
      left: calc(var(--x) * 1%);
      top: calc(var(--y) * 1%);
      z-index: 2;
      width: 2.4rem;
      height: 2.4rem;
      transform: translate(-50%, -50%);
      border: 2px solid currentColor;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: color-mix(in srgb, currentColor 32%, rgba(2,9,11,.72));
      box-shadow: 0 0 0 .35rem color-mix(in srgb, currentColor 18%, transparent), 0 0 22px color-mix(in srgb, currentColor 55%, transparent);
      color: var(--zone-colour, #26efe4);
      font-weight: 900;
    }
    .command-zone-dot span {
      position: absolute;
      left: 2rem;
      min-width: max-content;
      padding: .18rem .42rem;
      border-radius: .25rem;
      background: rgba(2,9,11,.78);
      color: #effcff;
      font-size: .68rem;
    }
    .command-zone-form {
      display: grid;
      gap: .55rem;
      padding: .85rem;
    }
    .command-zone-form label { gap: .25rem; }
    .command-upload-list { display: grid; gap: .4rem; padding: .85rem; }
    .command-upload-row {
      display: flex;
      justify-content: space-between;
      gap: .75rem;
      padding: .55rem .65rem;
      border: 1px solid rgba(103,245,231,.09);
      border-radius: .35rem;
      background: rgba(2,9,11,.42);
      color: #c7d6d9;
      font-size: .82rem;
    }
    .command-map-toolbar {
      position: absolute;
      left: .55rem;
      bottom: .55rem;
      z-index: 3;
      display: flex;
      flex-wrap: wrap;
      gap: .35rem;
      padding: .35rem;
      border-radius: .45rem;
      background: rgba(2,9,11,.74);
      backdrop-filter: blur(10px);
    }
    .command-subnav {
      display: flex;
      flex-wrap: wrap;
      gap: .45rem;
      margin: .75rem 0;
    }
    .command-subnav a {
      display: inline-flex;
      align-items: center;
      min-height: 2.25rem;
      padding: .45rem .75rem;
      border: 1px solid rgba(103,245,231,.18);
      border-radius: .45rem;
      background: rgba(6,17,20,.82);
      color: #cbdadd;
      font-weight: 800;
    }
    .command-subnav a.active,
    .command-subnav a:hover {
      border-color: rgba(103,245,231,.48);
      background: linear-gradient(90deg, rgba(21,205,198,.30), rgba(18,32,38,.62));
      color: #effcff;
    }
    body[data-section="pve"] .section-head .command-subnav + .tool-note { display: none; }
    body[data-theme="command"] .scenario-actions {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(5.2rem, max-content));
      gap: .35rem;
      align-items: center;
    }
    body[data-theme="command"] .scenario-actions .inline-action,
    body[data-theme="command"] .scenario-actions .button {
      margin: 0;
      width: auto;
    }
    body[data-theme="command"] .scenario-actions button,
    body[data-theme="command"] .scenario-actions .button {
      min-height: 2rem;
      padding: .35rem .55rem;
      font-size: .76rem;
    }
    body[data-section="pve"] [data-pve-panel] { display: none; }
    body[data-section="pve"][data-pve-tool="events"] [data-pve-panel="events"],
    body[data-section="pve"][data-pve-tool="builder"] [data-pve-panel="builder"],
    body[data-section="pve"][data-pve-tool="quests"] [data-pve-panel="quests"] { display: block; }
    body[data-section="pve"][data-pve-tool="events"] [data-pve-panel="events"].full,
    body[data-section="pve"][data-pve-tool="builder"] [data-pve-panel="builder"].full,
    body[data-section="pve"][data-pve-tool="quests"] [data-pve-panel="quests"].full { grid-column: 1 / -1; }
    body[data-section="pve"] [data-pve-panel="events"] { overflow-x: auto; }
    body[data-section="pve"] [data-pve-panel="events"] .item-table { min-width: 56rem; table-layout: auto; }
    body[data-section="pve"] [data-pve-panel="events"] .item-table td,
    body[data-section="pve"] [data-pve-panel="events"] .item-table th { white-space: normal; vertical-align: top; }
    body[data-theme="command"][data-section="pve"] .panel-grid {
      grid-template-columns: 1fr;
    }
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table th:first-child,
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table td:first-child,
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table th:nth-child(5),
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table td:nth-child(5),
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table th:nth-child(6),
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table td:nth-child(6) {
      white-space: nowrap;
    }
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table th:nth-child(7),
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table td:nth-child(7) {
      min-width: 15rem;
    }
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table th:nth-child(8),
    body[data-theme="command"][data-section="pve"] [data-pve-panel="events"] .item-table td:nth-child(8) {
      min-width: 13rem;
    }
    .command-check {
      display: inline-flex;
      align-items: center;
      gap: .3rem;
      min-height: 1.8rem;
      padding: .2rem .45rem;
      border: 1px solid rgba(103,245,231,.16);
      border-radius: .32rem;
      color: #d6e8ea;
      font-size: .72rem;
      font-weight: 800;
    }
    .command-check input { width: auto; min-height: 0; accent-color: #26efe4; }
    body[data-theme="command"] .command-status-bar {
      position: fixed;
      left: var(--sidebar-w);
      right: 0;
      bottom: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: .8rem;
      min-height: 2.1rem;
      padding: .38rem 1rem;
      border-top: 1px solid rgba(103,245,231,.12);
      background: rgba(5,11,14,.92);
      color: #a8bcc1;
      font-size: .72rem;
      backdrop-filter: blur(14px);
    }
    body[data-theme="command"] .command-status-bar span {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    body[data-theme="command"] .command-status-bar strong { color: #effcff; }
    body[data-theme="command"] .command-status-bar .ok { color: #8ded63; }
    body[data-theme="command"][data-section="visual-loadout"] .visual-loadout-layout {
      grid-template-columns: minmax(18rem, .7fr) minmax(34rem, 1.5fr) minmax(22rem, .85fr);
    }
    body[data-theme="command"][data-section="visual-loadout"] .visual-canvas {
      position: relative;
      overflow: hidden;
    }
    body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage {
      display: grid;
      grid-template-columns: .75fr minmax(14rem, 1fr) .75fr;
      gap: .65rem;
      align-items: center;
      margin: .85rem 0;
      padding: .75rem;
      border: 1px solid rgba(103,245,231,.14);
      border-radius: .55rem;
      background: radial-gradient(circle at center, rgba(38,239,228,.13), rgba(2,9,11,.38) 64%);
    }
    .command-loadout-stage .command-paperdoll { min-height: 22rem; }
    .command-loadout-stage .command-paperdoll img { max-height: 21rem; }
    body[data-theme="command"][data-section="visual-loadout"] .loadout-slot-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    body[data-theme="command"] .command-page-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 1rem;
      align-items: end;
      position: relative;
      z-index: 1;
      padding: 1rem 1.05rem;
      border: 1px solid rgba(103,245,231,.14);
      border-radius: .55rem;
      background:
        linear-gradient(120deg, rgba(18,37,44,.90), rgba(6,14,17,.96) 64%),
        radial-gradient(circle at 92% 0%, rgba(38,239,228,.16), transparent 36%);
      box-shadow: 0 18px 42px rgba(0,0,0,.25);
    }
    body[data-theme="command"] .command-page-head span {
      color: #26efe4;
      font-size: .68rem;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: .08em;
    }
    body[data-theme="command"] .command-page-head h1 {
      margin: .18rem 0 .22rem;
      color: #f3fbfc;
      font-size: clamp(1.45rem, 2.5vw, 2.35rem);
      line-height: 1.05;
    }
    body[data-theme="command"] .command-page-head p {
      margin: 0;
      max-width: 68rem;
      color: #a7b9be;
      line-height: 1.45;
    }
    body[data-theme="command"] .command-page-meta {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: .4rem;
      max-width: 28rem;
    }
    body[data-theme="command"] .command-page-meta span {
      min-height: 1.8rem;
      padding: .36rem .55rem;
      border: 1px solid rgba(103,245,231,.14);
      border-radius: .35rem;
      background: rgba(2,9,11,.54);
      color: #d8e8eb;
      font-size: .72rem;
      letter-spacing: 0;
      text-transform: none;
    }
    body[data-theme="command"] .section-panel {
      padding: 0;
      overflow: hidden;
      border-color: rgba(103,245,231,.14);
      border-radius: .55rem;
      background: linear-gradient(180deg, rgba(17,31,37,.86), rgba(5,11,14,.98));
      box-shadow: 0 18px 44px rgba(0,0,0,.25);
    }
    body[data-theme="command"] .section-panel > .section-head {
      margin: 0;
      padding: .95rem 1rem;
      border-bottom: 1px solid rgba(103,245,231,.11);
      background: linear-gradient(90deg, rgba(18,41,48,.72), rgba(5,12,15,.48));
    }
    body[data-theme="command"] .section-panel > .section-head h2,
    body[data-theme="command"] .admin-panel h3 {
      color: #effcff;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    body[data-theme="command"] .section-panel > .section-head .tool-note {
      max-width: 62rem;
      color: #9fb4ba;
    }
    body[data-theme="command"] .section-panel > :not(.section-head) {
      margin: .85rem;
    }
    body[data-theme="command"] .panel-grid {
      grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr));
    }
    body[data-theme="command"] .admin-panel,
    body[data-theme="command"] .mini-card,
    body[data-theme="command"] .option-card,
    body[data-theme="command"] .item-picker,
    body[data-theme="command"] .embed-preview,
    body[data-theme="command"] .notification,
    body[data-theme="command"] .cargo-box,
    body[data-theme="command"] .visual-slot,
    body[data-theme="command"] .equipped-card,
    body[data-theme="command"] .child-slot {
      border-color: rgba(103,245,231,.13);
      background: linear-gradient(180deg, rgba(12,25,30,.78), rgba(2,9,11,.88));
      box-shadow: none;
    }
    body[data-theme="command"] .admin-panel:nth-of-type(2n),
    body[data-theme="command"] .admin-panel:nth-of-type(3n) {
      background: linear-gradient(180deg, rgba(12,25,30,.78), rgba(2,9,11,.88));
    }
    body[data-theme="command"] input,
    body[data-theme="command"] textarea,
    body[data-theme="command"] select {
      border-color: rgba(103,245,231,.16);
      background: #031014;
      color: #f1fbfc;
    }
    body[data-theme="command"] input[readonly] {
      color: #8ded63;
      background: rgba(141,237,99,.08);
    }
    body[data-theme="command"] button,
    body[data-theme="command"] .button {
      border-color: rgba(103,245,231,.20);
      border-radius: .38rem;
      background: linear-gradient(180deg, rgba(31,55,64,.9), rgba(10,23,28,.96));
      color: #effcff;
    }
    body[data-theme="command"] button:hover,
    body[data-theme="command"] .button:hover {
      border-color: rgba(38,239,228,.55);
      background: linear-gradient(180deg, rgba(24,86,91,.88), rgba(10,29,34,.98));
    }
    body[data-theme="command"] .table th,
    body[data-theme="command"] .item-table th,
    body[data-theme="command"] .command-table th {
      color: #9bb2b8;
      font-size: .68rem;
      letter-spacing: .06em;
    }
    body[data-theme="command"] .table td,
    body[data-theme="command"] .item-table td {
      color: #d5e4e8;
      border-bottom-color: rgba(103,245,231,.09);
    }
    body[data-theme="command"] tr.status-ok td {
      background: rgba(97,184,94,.06);
    }
    body[data-theme="command"] tr.status-warn td {
      background: rgba(204,159,59,.07);
    }
    body[data-theme="command"] tr.status-bad td {
      background: rgba(194,72,72,.08);
    }
    body[data-theme="command"] tr.status-info td {
      background: rgba(80,140,190,.06);
    }
    body[data-theme="command"] .tool-note,
    body[data-theme="command"] .field-help,
    body[data-theme="command"] .muted {
      color: #9fb4ba;
    }
    body[data-theme="command"][data-section="visual-loadout"] .visual-loadout-layout {
      align-items: start;
      gap: .85rem;
      grid-template-columns: minmax(16rem, .58fr) minmax(0, 1fr);
      min-width: 0;
    }
    body[data-theme="command"][data-section="visual-loadout"] .visual-browser,
    body[data-theme="command"][data-section="visual-loadout"] .visual-export-panel {
      position: sticky;
      top: 8.25rem;
      max-height: calc(100vh - 10.5rem);
      overflow: auto;
    }
    body[data-theme="command"][data-section="visual-loadout"] .visual-export-panel {
      grid-column: 1 / -1;
      position: static;
      max-height: none;
    }
    body[data-theme="command"][data-section="visual-loadout"] .visual-canvas {
      min-height: 44rem;
      min-width: 0;
    }
    body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage {
      grid-template-columns: minmax(8.5rem, .58fr) minmax(15rem, .9fr) minmax(8.5rem, .58fr);
      gap: .85rem;
      padding: 1rem;
      background:
        radial-gradient(circle at center, rgba(38,239,228,.18), transparent 42%),
        linear-gradient(180deg, rgba(9,24,29,.78), rgba(2,9,11,.38));
    }
    body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-paperdoll {
      min-height: 26rem;
    }
    body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-paperdoll img:not(.command-character-portrait) {
      width: min(20rem, 98%);
      max-height: 29rem;
      border-radius: 0;
      object-fit: contain;
    }
    body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-character {
      min-height: 26rem;
      background:
        radial-gradient(circle at 50% 38%, rgba(103,245,231,.18), transparent 35%),
        linear-gradient(180deg, rgba(16,35,42,.58), rgba(2,9,11,.08));
    }
    body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-character .command-character-portrait {
      width: auto;
      max-width: 98%;
      height: min(25rem, 96%);
      max-height: 25rem;
    }
    body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-gear-card {
      min-height: 5.1rem;
    }
    body[data-theme="command"][data-section="visual-loadout"] .loadout-item-grid {
      grid-template-columns: 1fr;
    }
    @media (max-width: 1700px) {
      .command-grid {
        grid-template-columns: 1fr;
      }
      .command-loadout {
        grid-template-columns: minmax(10rem, .75fr) minmax(17rem, 1fr) minmax(10rem, .75fr);
      }
      .command-character {
        min-height: 22rem;
      }
      .command-character .command-character-portrait {
        height: min(21rem, 96%);
        max-height: 21rem;
      }
    }
    @media (max-width: 1180px) {
      body[data-theme="command"] { --sidebar-w: 0rem; }
      body[data-theme="command"] header { left: 0; }
      body[data-theme="command"] main { margin-left: 0; padding-top: 4.8rem; }
      body[data-theme="command"] .command-status-bar {
        flex-wrap: wrap;
        justify-content: flex-start;
      }
      body[data-theme="command"] .command-sidebar {
        position: static;
        width: auto;
        max-height: none;
        margin: 4.4rem 1rem .75rem;
        border: 1px solid rgba(103,245,231,.15);
        border-radius: .65rem;
      }
      body[data-theme="command"] .command-logo {
        grid-template-columns: 5rem minmax(0, 1fr);
        align-items: center;
      }
      body[data-theme="command"] .command-logo img { aspect-ratio: 1 / 1; }
      body[data-theme="command"] .command-side-nav { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      body[data-theme="command"] .command-quick { margin-top: .65rem; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .command-metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .command-grid, .command-row { grid-template-columns: 1fr; }
      .command-status-bar { left: 0; }
      body[data-theme="command"] .command-page-head { grid-template-columns: 1fr; }
      body[data-theme="command"] .command-page-meta { justify-content: flex-start; }
      body[data-theme="command"][data-section="visual-loadout"] .visual-loadout-layout { grid-template-columns: 1fr; }
      body[data-theme="command"][data-section="visual-loadout"] .visual-browser,
      body[data-theme="command"][data-section="visual-loadout"] .visual-export-panel {
        position: static;
        max-height: none;
      }
    }
    @media (max-width: 720px) {
      body[data-theme="command"] header { padding: .55rem .7rem; }
      body[data-theme="command"] .theme-picker button { width: 1.35rem; height: 1.35rem; }
      body[data-theme="command"] .section-nav { display: none; }
      body[data-theme="command"] .mobile-section-picker { display: block; }
      body[data-theme="command"] main { padding-inline: .55rem; }
      body[data-theme="command"] .command-sidebar { margin: 4.1rem .55rem .65rem; padding: .65rem; }
      body[data-theme="command"] .command-side-nav,
      body[data-theme="command"] .command-quick,
      .command-metrics,
      .command-loadout,
      body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage {
        grid-template-columns: 1fr;
      }
      .command-loadout-extra { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .command-paperdoll { min-height: 14rem; }
      .command-paperdoll img { max-height: 13rem; }
      .command-table { min-width: 46rem; }
      .command-card { overflow-x: auto; }
      .command-status-bar { position: static; margin-inline: -.55rem; }
      body[data-theme="command"] .command-page-head { padding: .85rem; }
      body[data-theme="command"] .command-page-meta span { width: 100%; }
      body[data-theme="command"] .section-panel > :not(.section-head) { margin: .65rem; }
      body[data-theme="command"] .panel-grid { grid-template-columns: 1fr; }
      body[data-theme="command"][data-section="visual-loadout"] .loadout-slot-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-paperdoll { min-height: 18rem; }
      body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-paperdoll img:not(.command-character-portrait) { max-height: 17rem; }
      body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-character { min-height: 18rem; }
      body[data-theme="command"][data-section="visual-loadout"] .command-loadout-stage .command-character .command-character-portrait {
        width: auto;
        max-width: 96%;
        height: min(17rem, 96%);
        max-height: 17rem;
      }
    }
    .admin-panel form { margin-top: .75rem; }
    .result { min-height: 1.25rem; }
    .owner-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
    .owner-tile { border: 1px solid var(--line); border-radius: .5rem; padding: .85rem; background: var(--panel-3); }
    .owner-tile strong { display: block; color: var(--gold); font-size: 1.35rem; }
    .table { width: 100%; border-collapse: collapse; margin-top: .75rem; }
    .table th, .table td { border-bottom: 1px solid var(--line); padding: .55rem; text-align: left; color: var(--muted); }
    .table th { color: var(--text); font-size: .8rem; text-transform: uppercase; }
    .section-nav { display: flex; flex-wrap: wrap; gap: .35rem; padding: .45rem; border: 1px solid var(--line); border-radius: .5rem; background: rgba(5, 8, 6, .9); }
    .section-nav a { min-height: 2.1rem; padding: .42rem .6rem; font-size: .84rem; border-radius: .45rem; }
    .mobile-section-picker { display: none; padding: .5rem; border: 1px solid var(--line); border-radius: .5rem; background: rgba(5, 8, 6, .92); }
    .mobile-section-picker label { font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
    .section-panel { min-width: 0; padding: 1rem; scroll-margin-top: 8rem; }
    body[data-section="leaderboards"] { --accent: #f1c40f; }
    body[data-section="automations"] { --accent: #6fd3ff; }
    body[data-section="dayz-converter"] { --accent: #79c7dd; }
    body[data-section="loot-engine"] { --accent: #c8d46a; }
    body[data-section="visual-loadout"] { --accent: #75d89a; }
    body[data-section="bulk-economy"] { --accent: #e3b65f; }
    body[data-section="factions"] { --accent: #d6a2ff; }
    body[data-section="zones"] { --accent: #75d89a; }
    body[data-section="members"] { --accent: #ff9abc; }
    body[data-section="heatmaps"] { --accent: #ff866d; }
    body[data-section="pve"] { --accent: #e1f25a; }
    body[data-section="economy"] { --accent: #d5b45f; }
    body[data-section="shop"] { --accent: #79c7dd; }
    body[data-section="xml-workshop"] { --accent: #7cff5b; }
    body[data-section="server-rules"] { --accent: #ff9f43; }
    body[data-section="moderation"] { --accent: #ff719e; }
    body[data-section="server-control"] { --accent: #94b4ff; }
    .section-panel { border-top-color: color-mix(in srgb, var(--accent) 72%, var(--line)); }
    .section-panel .section-head h2 { color: var(--accent); }
    .section-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; flex-wrap: wrap; margin-bottom: .85rem; }
    .server-lock { display: grid; grid-template-columns: 1fr; gap: .35rem; margin-bottom: .75rem; }
    .server-lock span { color: var(--muted); font-size: .85rem; }
    .leaderboard { display: grid; gap: .45rem; margin-top: .75rem; }
    .leader-row { display: grid; grid-template-columns: 3rem minmax(0, 1fr) repeat(3, minmax(4rem, auto)); gap: .55rem; align-items: center; border: 1px solid var(--line); border-radius: .5rem; padding: .65rem; background: #070b08; }
    .rank { color: var(--gold); font-weight: 900; font-size: 1.15rem; }
    .leader-name { color: var(--text); font-weight: 900; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .metric { color: var(--muted); text-align: right; }
    .metric strong { color: var(--text); display: block; }
    .discord-board { border-left: 4px solid #f1c40f; border-radius: .45rem; background: #202126; padding: 1rem; }
    .discord-board h2 { margin-bottom: .35rem; text-transform: uppercase; }
    .leader-category-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .95rem; margin-top: 1rem; }
    .lb-card { min-width: 0; }
    .lb-card h3 { margin-bottom: .45rem; color: #f4f4f5; text-transform: uppercase; font-size: 1rem; }
    .lb-list { display: grid; gap: .28rem; }
    .lb-row { display: flex; flex-wrap: wrap; gap: .25rem; align-items: center; color: #f4f4f5; font-weight: 800; }
    .lb-rank { display: inline-grid; place-items: center; min-width: 1.45rem; height: 1.45rem; border-radius: .25rem; background: #3498db; color: white; font-weight: 900; }
    .lb-rank.gold { background: #f1b82d; color: #17202a; border-radius: 999px; }
    .lb-rank.silver { background: #b8c2cc; color: #17202a; border-radius: 999px; }
    .lb-rank.bronze { background: #e67e22; color: #17202a; border-radius: 999px; }
    .lb-value { display: inline-block; border: 1px solid #3f4255; background: #292b3a; color: #f4f4f5; border-radius: .35rem; padding: .05rem .32rem; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-weight: 500; }
    .lb-empty { color: #d8d8dc; font-style: italic; }
    .tool-note { color: var(--muted); font-size: .9rem; line-height: 1.45; }
    .field-help { display: block; margin-top: .3rem; color: color-mix(in srgb, var(--muted) 72%, #ffffff); font-size: .78rem; line-height: 1.35; font-weight: 500; }
    .option-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; }
    .option-card { border: 1px solid var(--line); border-radius: .5rem; padding: .8rem; background: #070b08; }
    .option-card strong { display: block; color: var(--gold); margin-bottom: .25rem; }
    .check-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .5rem; }
    .check { display: flex; align-items: center; gap: .5rem; color: var(--muted); border: 1px solid var(--line); border-radius: .45rem; padding: .55rem; background: #070b08; }
    .check input { width: auto; accent-color: var(--olive); }
    .mini-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; }
    .mini-card { border: 1px solid var(--line); border-radius: .5rem; padding: .75rem; background: #070b08; }
    .mini-card strong { display: block; color: var(--gold); font-size: 1.25rem; }
    .stack { display: grid; gap: .65rem; }
    .notification { display: grid; gap: .2rem; border-left: 3px solid var(--gold); background: #070b08; border-radius: .35rem; padding: .65rem .75rem; color: var(--muted); }
    .notification small { display: block; color: var(--muted); margin-top: .15rem; }
    .row-between { display: flex; justify-content: space-between; gap: .8rem; align-items: center; flex-wrap: wrap; }
    .inline-actions { display: inline-flex; gap: .45rem; align-items: center; flex-wrap: wrap; }
    .dashboard-edit-modal { position: fixed; left: 50%; top: 50%; transform: translate(-50%, -50%); z-index: 40; width: min(56rem, calc(100vw - 2rem)); max-height: calc(100vh - 2rem); overflow: auto; border: 1px solid color-mix(in srgb, var(--accent) 70%, var(--line)); border-radius: .65rem; padding: 1rem; background: color-mix(in srgb, var(--panel) 94%, #000); box-shadow: 0 24px 70px rgba(0,0,0,.64); }
    .dashboard-edit-modal::before { content: "Edit"; position: sticky; top: -.2rem; display: block; margin: -.2rem 0 .7rem; color: var(--accent); font-weight: 900; font-size: 1.05rem; }
    .admin-form:not(.dashboard-edit-modal) [data-dashboard-modal-close] { display: none; }
    .modal-actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
    .toolbar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
    .embed-preview { border-left: 4px solid var(--gold); border-radius: .45rem; background: #202126; padding: .85rem; color: #f4f4f5; }
    .embed-preview strong { display: block; color: #fff; margin-bottom: .25rem; }
    .embed-preview span { color: #d8d8dc; }
    .embed-preview small { display: block; color: #aeb0b8; margin-top: .55rem; }
    .heat-list { display: grid; gap: .45rem; }
    .heat-row { display: grid; grid-template-columns: minmax(0, 1fr) 5rem; gap: .65rem; align-items: center; }
    .bar { height: .65rem; border-radius: 999px; background: rgba(213, 180, 95, .18); overflow: hidden; }
    .bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--olive), var(--gold)); }
    .item-table { width: 100%; border-collapse: collapse; }
    .item-table th, .item-table td { padding: .45rem; border-bottom: 1px solid var(--line); color: var(--muted); text-align: left; overflow-wrap: anywhere; }
    .table-scroll { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
    .table-scroll .item-table { min-width: 44rem; }
    input[type="color"] { min-height: 2.8rem; padding: .25rem; cursor: pointer; }
    .item-table button, .item-table .button { padding: .35rem .5rem; font-size: .85rem; }
    .scenario-actions { display: flex; flex-wrap: wrap; gap: .35rem; align-items: center; min-width: 18rem; }
    .scenario-actions .inline-action { display: inline-flex; width: auto; gap: .35rem; }
    .scenario-actions .result { display: none; }
    .scenario-actions button { min-height: 2.2rem; padding: .35rem .55rem; white-space: nowrap; }
    .inline-action { display: grid; grid-template-columns: minmax(7rem, 1fr) auto; gap: .35rem; align-items: center; margin: 0; }
    .inline-action .result { grid-column: 1 / -1; font-size: .78rem; }
    .owner-server-list { display: grid; gap: .65rem; }
    .owner-server-card { display: grid; grid-template-columns: minmax(12rem, 1fr) minmax(14rem, auto); gap: .75rem; align-items: center; border: 1px solid var(--line); border-radius: .5rem; padding: .75rem; background: #070b08; }
    .owner-server-card h4 { margin: 0 0 .35rem; color: var(--text); }
    .owner-server-meta { display: flex; flex-wrap: wrap; gap: .35rem; }
    .owner-server-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .4rem; align-items: center; }
    .owner-server-actions .inline-action { display: inline-flex; width: auto; gap: .35rem; }
    .owner-server-actions .result { display: none; }
    .owner-server-actions button, .owner-server-actions .button { min-height: 2.25rem; padding: .42rem .55rem; font-size: .78rem; line-height: 1.1; white-space: normal; }
    .shop-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) minmax(10rem, .35fr) auto; gap: .65rem; align-items: end; margin-bottom: .75rem; }
    .admin-panel form[data-route="/api/admin/xml-workshop"] { grid-template-columns: 1fr; }
    .item-picker { border: 1px solid var(--line); border-radius: .5rem; padding: .65rem; background: #070b08; display: grid; gap: .55rem; min-width: 0; overflow: hidden; }
    .item-picker label { min-width: 0; }
    .item-picker-controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr)); gap: .45rem; align-items: end; min-width: 0; }
    .item-picker-controls button { align-self: end; min-width: 5rem; }
    .item-picker-preview { display: flex; gap: .5rem; align-items: center; color: var(--muted); min-width: 0; }
    .xml-tool-layout { display: grid; grid-template-columns: minmax(20rem, .9fr) minmax(24rem, 1.1fr); gap: .85rem; align-items: start; }
    .xml-tool-layout > * { min-width: 0; }
    .xml-output-panel { display: grid; gap: .65rem; align-content: start; position: sticky; top: .75rem; min-width: 0; }
    .xml-output-panel .save-preview { min-height: 18rem; max-height: 34rem; }
    .xml-file-tabs { display: flex; gap: .35rem; flex-wrap: wrap; }
    .xml-file-tabs button { min-height: 2.2rem; padding: .45rem .6rem; font-size: .78rem; background: #070b08; color: var(--muted); }
    .xml-file-tabs button.active { background: var(--panel-2); color: var(--gold); border-color: var(--accent); }
    .xml-converter-grid { display: grid; grid-template-columns: minmax(20rem, .8fr) minmax(24rem, 1.2fr); gap: .85rem; align-items: start; }
    .xml-snippet-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: .75rem; }
    .xml-snippet-box { display: grid; gap: .45rem; min-width: 0; border: 1px solid var(--line); border-radius: .5rem; padding: .75rem; background: #070b08; }
    .xml-snippet-box textarea { min-height: 16rem; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .84rem; line-height: 1.35; }
    .xml-tool-form { margin-top: .75rem; }
    .xml-tool-form .result.error { color: #ff8fa5; }
    .xml-tool-form .result.success { color: #c8f28b; }
    .flag-grid { display: flex; flex-wrap: wrap; gap: .35rem; }
    .flag-grid label { display: inline-flex; align-items: center; gap: .3rem; border: 1px solid var(--line); border-radius: .45rem; padding: .4rem .55rem; background: #070b08; color: var(--muted); }
    .flag-grid input { width: auto; min-height: 0; }
    .airdrop-map-tools { display: flex; flex-wrap: wrap; gap: .45rem; align-items: center; }
    .airdrop-dot { position: absolute; transform: translate(-50%, -50%); z-index: 3; width: 1.4rem; height: 1.4rem; border-radius: 999px; display: grid; place-items: center; background: var(--gold); color: #080b06; border: 2px solid rgba(255,255,255,.78); font-size: .75rem; font-weight: 900; box-shadow: 0 .25rem .8rem rgba(0,0,0,.45); }
    .visual-select-grid { margin-top: .45rem; max-height: 16rem; overflow: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr)); gap: .45rem; }
    .visual-select-card { display: grid; grid-template-rows: 3.5rem auto auto; gap: .25rem; border: 1px solid var(--line); border-radius: .5rem; background: var(--panel-2); color: var(--muted); padding: .45rem; text-align: left; min-width: 0; }
    .visual-select-card.active, .visual-select-card:hover { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .visual-select-card::after { content: "Choose"; display: inline-flex; justify-content: center; align-items: center; min-height: 2rem; border: 1px solid var(--line); border-radius: .35rem; color: var(--text); font-weight: 800; background: #070b08; }
    .visual-select-card img { width: 100%; height: 3.5rem; object-fit: contain; background: #050806; border-radius: .4rem; }
    .visual-select-card strong { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .visual-picker { display: grid; gap: .45rem; }
    .visual-picker input { width: 100%; }
    .visual-picker-grid { max-height: 22rem; overflow: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr)); gap: .5rem; padding: .15rem; }
    .visual-picker-card { display: grid; grid-template-rows: 3.5rem auto auto; gap: .25rem; align-items: center; text-align: left; border: 1px solid var(--line); border-radius: .5rem; background: var(--panel-2); color: var(--muted); padding: .45rem; min-width: 0; }
    .visual-picker-card:hover, .visual-picker-card.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .visual-picker-card::after { content: "Select"; display: inline-flex; justify-content: center; align-items: center; min-height: 2rem; border: 1px solid var(--line); border-radius: .35rem; color: var(--text); font-weight: 800; background: #070b08; }
    .visual-picker-card img { width: 100%; height: 3.5rem; object-fit: contain; background: #050806; border-radius: .4rem; }
    .visual-picker-card strong { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .visual-picker-card small { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .shop-picker-list { max-height: 18rem; overflow: auto; border: 1px solid var(--line); border-radius: .5rem; padding: .5rem; background: #070b08; display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: .35rem; }
    .shop-picker-card { display: grid; grid-template-columns: 2rem minmax(0, 1fr); gap: .45rem; align-items: center; text-align: left; background: #0a0f0b; border: 1px solid var(--line); border-radius: .45rem; padding: .35rem; color: var(--muted); min-width: 0; }
    .shop-picker-card img, .item-thumb { width: 2rem; height: 2rem; border-radius: .4rem; object-fit: cover; border: 1px solid var(--line); background: var(--panel-2); }
    .shop-picker-card strong { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .shop-picker-card span { color: var(--muted); font-size: .78rem; }
    .item-table .item-name-cell { display: flex; align-items: center; gap: .55rem; min-width: 0; }
    .item-table .item-name-cell strong { overflow-wrap: anywhere; }
    .loadout-builder { display: grid; grid-template-columns: minmax(16rem, .75fr) minmax(16rem, 1fr); gap: .75rem; align-items: start; }
    .loadout-slots { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .45rem; }
    .loadout-slot { border: 1px dashed var(--line); border-radius: 999px; padding: .45rem .6rem; background: #070b08; color: var(--muted); font-size: .85rem; }
    .loadout-slot.active { border-style: solid; border-color: var(--gold); color: var(--text); background: rgba(213,180,95,.12); }
    .loadout-selected-slot { border: 1px solid var(--line); border-radius: .5rem; padding: .65rem; background: #070b08; color: var(--muted); }
    .loadout-selected-slot strong { display: block; color: var(--gold); margin-bottom: .25rem; }
    .loadout-workbench { display: grid; gap: .75rem; }
    .player-loadout-layout { display: block; }
    .player-loadout-layout .xml-output-panel { position: static; margin-top: .85rem; }
    .player-loadout-layout .xml-output-panel .save-preview { min-height: 8rem; max-height: 18rem; }
    .player-loadout-layout .loadout-workbench { margin-top: .75rem; }
    .player-loadout-layout .visual-picker-grid { max-height: 30rem; grid-template-columns: repeat(auto-fill, minmax(8.75rem, 1fr)); }
    .vehicle-workbench { display: grid; gap: .75rem; }
    .vehicle-cargo-board { min-height: 12rem; }
    .visual-loadout-layout { display: grid; grid-template-columns: minmax(16rem, .8fr) minmax(28rem, 1.35fr) minmax(20rem, .95fr); gap: .85rem; align-items: start; }
    .visual-browser, .visual-export-panel { position: sticky; top: 6rem; }
    .loadout-category-row { display: flex; flex-wrap: wrap; gap: .35rem; margin: .65rem 0; }
    .loadout-category-row button, .loadout-category-row a { min-height: 2.1rem; padding: .35rem .55rem; font-size: .8rem; background: #070b08; color: var(--muted); }
    .loadout-category-row button.active, .loadout-category-row a.active { color: var(--text); border-color: var(--accent); background: var(--panel-2); }
    .loadout-item-grid { max-height: 34rem; overflow: auto; display: grid; gap: .45rem; padding-right: .15rem; }
    .loadout-item-form { display: block; margin: 0; }
    .loadout-item-card { display: grid; grid-template-columns: 2.7rem minmax(0, 1fr); gap: .5rem; align-items: center; min-height: 4rem; border: 1px solid var(--line); border-radius: .5rem; padding: .42rem; background: #070b08; color: var(--muted); text-align: left; }
    .loadout-item-form .loadout-item-card { width: 100%; cursor: pointer; }
    a.loadout-item-card { text-decoration: none; }
    .loadout-item-card:hover, .loadout-item-card:focus-visible { border-color: var(--accent); outline: none; box-shadow: 0 0 0 1px var(--accent); }
    .loadout-item-card img { width: 2.7rem; height: 2.7rem; border-radius: .4rem; border: 1px solid var(--line); background: var(--panel-2); object-fit: contain; }
    .loadout-item-card strong { display: block; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .loadout-item-card small { color: var(--muted); }
    .visual-canvas { display: grid; gap: .75rem; }
    .loadout-slot-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .55rem; }
    .visual-slot { min-height: 5rem; display: grid; align-content: center; gap: .25rem; text-align: left; border-style: dashed; background: #070b08; overflow: hidden; }
    a.visual-slot { text-decoration: none; color: inherit; }
    .visual-slot span { display: block; color: var(--muted); font-size: .78rem; font-weight: 700; }
    .visual-slot strong { display: block; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .visual-slot.active { border-style: solid; border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .visual-slot.filled { border-style: solid; background: color-mix(in srgb, var(--panel-2) 72%, #000); }
    .visual-slot.weapon { border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); }
    .loadout-cargo-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .55rem; }
    .cargo-box { min-height: 9rem; border: 1px dashed var(--line); border-radius: .5rem; padding: .55rem; background: #070b08; }
    a.cargo-box { display: block; text-decoration: none; color: inherit; }
    .cargo-box.drag-over, .visual-slot.drag-over { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, #070b08); }
    .cargo-box > strong { display: block; color: var(--gold); margin-bottom: .45rem; }
    .cargo-box [data-cargo-items] { display: flex; flex-wrap: wrap; gap: .35rem; min-height: 5rem; align-content: flex-start; }
    .cargo-chip, .attachment-chip { display: inline-flex; align-items: center; gap: .35rem; max-width: 100%; border: 1px solid var(--line); border-radius: .4rem; padding: .28rem .42rem; background: var(--panel-2); color: var(--text); font-size: .82rem; font-weight: 800; }
    .cargo-chip button, .attachment-chip button { min-height: 1.6rem; padding: 0 .35rem; font-size: .72rem; }
    .equipped-list { display: grid; gap: .65rem; }
    .equipped-card { border: 1px solid var(--line); border-radius: .5rem; padding: .65rem; background: #070b08; display: grid; gap: .6rem; }
    .equipped-head { display: grid; grid-template-columns: 3.2rem minmax(0, 1fr); gap: .6rem; align-items: center; }
    .equipped-head img { width: 3.2rem; height: 3.2rem; object-fit: contain; border: 1px solid var(--line); border-radius: .45rem; background: var(--panel-2); }
    .equipped-head strong, .child-slot strong { display: block; color: var(--text); overflow-wrap: anywhere; }
    .equipped-meta { display: flex; flex-wrap: wrap; gap: .35rem; color: var(--muted); font-size: .78rem; }
    .child-slot-grid { display: grid; gap: .55rem; }
    .child-slot { border: 1px solid var(--line); border-radius: .45rem; padding: .55rem; background: color-mix(in srgb, var(--panel-2) 75%, #000); }
    .child-choice-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .45rem; align-items: end; margin-top: .4rem; }
    .child-choice-row select { min-width: 0; }
    .attachment-tray { border: 1px solid var(--line); border-radius: .5rem; padding: .65rem; background: #070b08; }
    .attachment-tray [data-attachment-items] { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .55rem; }
    .visual-export-panel textarea { min-height: 16rem; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .84rem; line-height: 1.35; }
    .visual-export-panel textarea[name="cfggameplay_json"] { min-height: 8rem; }
    .tool-switcher { display: flex; flex-wrap: wrap; gap: .45rem; margin: .75rem 0 1rem; }
    .tool-switcher a { border: 1px solid var(--line); border-radius: .5rem; padding: .55rem .75rem; background: #070b08; color: var(--text); font-weight: 800; }
    .tool-switcher a.active { background: var(--panel-2); border-color: var(--accent); color: var(--gold); }
    .picker-select { min-width: 0; width: 100%; }
    .save-preview { white-space: pre-wrap; max-height: 22rem; overflow: auto; border: 1px solid var(--line); border-radius: .5rem; padding: .75rem; background: #070b08; color: var(--text); }
    .recipe-list { display: grid; gap: .65rem; margin-top: .85rem; }
    .recipe-row { border: 1px solid var(--line); border-radius: .5rem; padding: .75rem; background: #070b08; }
    .recipe-row strong { display: block; color: var(--gold); margin-bottom: .25rem; }
    .selected-items { display: grid; gap: .45rem; border: 1px solid var(--line); border-radius: .5rem; background: #070b08; padding: .55rem; min-height: 3rem; }
    .selected-row { display: grid; grid-template-columns: 2rem minmax(0, 1fr) auto; gap: .5rem; align-items: center; border: 1px solid var(--line); border-radius: .45rem; background: var(--panel-2); padding: .4rem; cursor: grab; }
    .selected-row.dragging { opacity: .55; }
    .selected-row strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .selected-row small { color: var(--muted); }
    .selected-row button { min-height: 2rem; padding: .25rem .5rem; }
    .raw-output { display: none; min-height: 4rem; font-size: .85rem; opacity: .72; }
    .zone-builder-form { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .zone-tools { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; }
    .zone-tool-actions { display: flex; flex-wrap: wrap; align-items: end; gap: .5rem; }
    .zone-map-viewport { width: 100%; overflow: visible; border: 1px solid var(--line); border-radius: .5rem; background: rgba(5,8,6,.45); }
    .zone-map-viewport .zone-map { border: 0; border-radius: .45rem; margin: 0 auto; }
    .zone-map { position: relative; width: min(100%, var(--zone-map-display-size, 512px)); max-width: 100%; margin-inline: auto; min-height: 0; aspect-ratio: 1 / 1; border: 1px solid var(--line); border-radius: .5rem; overflow: hidden; isolation: isolate; contain: paint; background:
      var(--map-image),
      radial-gradient(circle at 22% 68%, rgba(213,180,95,.18), transparent 10%),
      radial-gradient(circle at 38% 38%, rgba(141,150,62,.34), transparent 18%),
      radial-gradient(circle at 62% 55%, rgba(52,152,219,.12), transparent 13%),
      linear-gradient(135deg, #182315, #071008 68%);
      background-size: 100% 100%, auto, auto, auto, auto;
      background-position: center, center, center, center, center;
      background-repeat: no-repeat, no-repeat, no-repeat, no-repeat, no-repeat;
      cursor: crosshair;
    }
    .zone-map::before { content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 1; background-image: linear-gradient(rgba(243,236,217,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(243,236,217,.08) 1px, transparent 1px); background-size: 12.5% 12.5%; }
    .zone-map::after { content: "Click map to add - click marker to edit"; position: absolute; right: .75rem; bottom: .65rem; z-index: 8; pointer-events: none; color: var(--dim); font-size: .85rem; background: rgba(5,8,6,.72); border: 1px solid var(--line); border-radius: .35rem; padding: .3rem .45rem; }
    .zone-map-hit-layer { position: absolute; inset: 0; z-index: 2; width: 100%; height: 100%; min-height: 0; padding: 0; border: 0; border-radius: 0; background: transparent; cursor: crosshair; opacity: 1; object-fit: fill; }
    .zone-map-hit-label { position: absolute; left: .75rem; bottom: .65rem; z-index: 8; padding: .32rem .5rem; border: 1px solid var(--line); border-radius: .35rem; background: rgba(5,8,6,.74); color: var(--text); font-size: .82rem; font-weight: 900; pointer-events: none; }
    .zone-map-hit-layer:focus-visible { outline: 2px solid #fff; outline-offset: -4px; background: rgba(255,255,255,.04); }
    .zone-radius-ring { position: absolute; transform: translate(-50%, -50%); width: var(--zone-radius, 3%); aspect-ratio: 1 / 1; border: 2px solid color-mix(in srgb, var(--zone-colour, var(--gold)) 82%, #fff); border-radius: 50%; background: radial-gradient(circle, color-mix(in srgb, var(--zone-colour, var(--gold)) 16%, transparent) 0 58%, color-mix(in srgb, var(--zone-colour, var(--gold)) 30%, transparent) 59% 100%); box-shadow: 0 0 26px color-mix(in srgb, var(--zone-colour, var(--gold)) 48%, transparent); pointer-events: none; z-index: 4; }
    .zone-radius-ring { padding: 0; min-height: 0; color: inherit; text-decoration: none; }
    .zone-dot { position: absolute; transform: translate(-50%, -50%); min-width: 34px; min-height: 34px; border: 3px solid var(--zone-colour, var(--gold)); background: color-mix(in srgb, var(--zone-colour, var(--gold)) 58%, rgba(5,8,6,.16)); border-radius: 50%; display: grid; place-items: center; color: #fff; font-size: .82rem; font-weight: 900; text-shadow: 0 1px 2px #000; cursor: pointer; box-shadow: 0 0 0 3px rgba(5,8,6,.44), 0 0 22px color-mix(in srgb, var(--zone-colour, var(--gold)) 72%, transparent); z-index: 5; isolation: isolate; }
    button.zone-dot, a.zone-dot { padding: 0; min-height: 0; overflow: visible; text-decoration: none; }
    .zone-dot > span { width: 100%; height: 100%; display: grid; place-items: center; border-radius: inherit; }
    .zone-dot:hover, .zone-dot:focus-visible, .zone-dot.editing { outline: 2px solid #fff; outline-offset: 2px; filter: brightness(1.2); }
    .zone-dot small { position: absolute; left: calc(100% + .35rem); top: 50%; transform: translateY(-50%); max-width: 12rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border: 1px solid color-mix(in srgb, var(--zone-colour, var(--gold)) 74%, rgba(255,255,255,.35)); border-radius: .35rem; padding: .22rem .42rem; background: rgba(5,8,6,.86); color: var(--text); font-size: .74rem; font-weight: 900; text-align: left; pointer-events: none; }
    .zone-dot.editing small { color: #fff; border-color: #fff; }
    .zone-map-popover { position: absolute; z-index: 12; width: min(25rem, calc(100% - 1rem)); max-height: min(32rem, calc(100% - 1rem)); overflow: auto; transform: translate(.7rem, -50%); border: 1px solid color-mix(in srgb, var(--zone-colour, var(--accent)) 74%, var(--line)); border-radius: .6rem; padding: .75rem; background: color-mix(in srgb, var(--panel) 88%, #000); box-shadow: 0 18px 40px rgba(0,0,0,.42); color: var(--text); }
    .zone-map-popover[data-side="left"] { transform: translate(calc(-100% - .7rem), -50%); }
    .zone-map-popover[hidden] { display: none; }
    .zone-map-popover strong { display: block; margin-bottom: .18rem; color: var(--zone-colour, var(--accent)); font-size: 1rem; }
    .zone-map-popover span { display: block; color: var(--muted); font-size: .86rem; line-height: 1.35; }
    .zone-popover-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .45rem; margin-top: .65rem; }
    .zone-popover-grid label { gap: .2rem; font-size: .78rem; color: var(--muted); }
    .zone-popover-grid input, .zone-popover-grid select { min-height: 2.2rem; padding: .34rem .45rem; font-size: .86rem; }
    .zone-popover-grid label:first-child { grid-column: 1 / -1; }
    .zone-map-popover .zone-popover-actions { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .65rem; }
    .zone-map-popover button { min-height: 2.15rem; padding: .35rem .55rem; font-size: .84rem; }
    .zone-dot.safe { --zone-colour: #22c55e; }
    .zone-dot.pvp { --zone-colour: #ef4444; }
    .zone-dot.radar { --zone-colour: #38bdf8; }
    .zone-dot.action { --zone-colour: #f97316; }
    .zone-dot.faction { --zone-colour: #a855f7; }
    .zone-dot.custom { --zone-colour: #facc15; }
    .zone-form-actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
    .zone-form-actions button[disabled] { opacity: .45; cursor: not-allowed; }
    .zone-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; }
    .zone-cursor { position: absolute; transform: translate(-50%, -50%); width: 1.2rem; height: 1.2rem; border: 2px solid #fff; border-radius: 50%; box-shadow: 0 0 0 .45rem color-mix(in srgb, var(--zone-colour, var(--accent)) 28%, transparent); background: var(--zone-colour, var(--accent)); pointer-events: none; z-index: 6; }
    .zone-preview-circle { position: absolute; transform: translate(-50%, -50%); border: 2px solid var(--zone-colour, var(--accent)); border-radius: 50%; background: color-mix(in srgb, var(--zone-colour, var(--accent)) 18%, transparent); pointer-events: none; z-index: 2; }
    .zone-boundary-layer { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 3; }
    .zone-boundary-layer polygon { fill: color-mix(in srgb, var(--zone-colour, var(--accent)) 18%, transparent); stroke: var(--zone-colour, var(--accent)); stroke-width: 2.5; }
    .zone-boundary-layer polyline { fill: none; stroke: var(--zone-colour, var(--accent)); stroke-width: 2.5; stroke-dasharray: 7 5; }
    .zone-boundary-point { position: absolute; transform: translate(-50%, -50%); width: .9rem; height: .9rem; border: 2px solid var(--bg); border-radius: 50%; background: var(--zone-colour, var(--accent)); pointer-events: none; z-index: 4; }
    .zone-swatch { display: inline-block; width: .85rem; height: .85rem; border-radius: 50%; border: 1px solid rgba(255,255,255,.55); background: var(--zone-colour, var(--gold)); vertical-align: middle; margin-right: .35rem; }
    .map-missing { position: absolute; left: .75rem; top: .75rem; z-index: 7; max-width: min(34rem, calc(100% - 1.5rem)); border: 1px solid rgba(237,56,83,.4); border-radius: .45rem; background: rgba(5,8,6,.84); color: #ffd8df; padding: .55rem .7rem; font-size: .9rem; }
    .trial-notice { display: flex; align-items: center; justify-content: space-between; gap: .75rem; border: 1px solid rgba(213,180,95,.45); border-radius: .5rem; padding: .7rem .85rem; background: rgba(213,180,95,.13); color: var(--text); }
    .trial-notice span { color: var(--muted); }
    .map-readout { margin-top: .4rem; color: var(--gold); font-size: .9rem; }
    .help-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem; }
    .help-card { border: 1px solid var(--line); border-radius: .5rem; padding: 1rem; background: linear-gradient(135deg, color-mix(in srgb, var(--panel-3) 84%, #123b46), #070b08); }
    .help-card h3 { color: var(--accent); margin-bottom: .55rem; }
    .help-card ol { margin: .5rem 0 0; padding-left: 1.2rem; color: var(--muted); line-height: 1.55; }
    .server-switcher { display: grid; gap: .65rem; }
    .server-tabs { display: flex; flex-wrap: wrap; gap: .5rem; }
    .server-tab { border: 1px solid var(--line); border-radius: .5rem; padding: .65rem .75rem; background: #070b08; color: var(--muted); }
    .server-tab.active { color: var(--text); border-color: var(--gold); background: rgba(213, 180, 95, .12); }
    .category-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; }
    .category-link { border: 1px solid var(--line); border-radius: .5rem; padding: .85rem; background: #070b08; color: var(--muted); }
    .category-link strong { display: block; color: var(--gold); margin-bottom: .2rem; }
    .hidden-field { display: none; }
    @media (max-width: 980px) {
      .hero, .grid, .columns, .stats, form, .zone-builder-form, .zone-options, .zone-tools, .route-list, .panel-grid, .owner-grid, .option-grid, .leader-row, .leader-category-grid, .check-grid, .mini-grid, .heat-row, .category-grid, .help-grid, .owner-server-card, .xml-tool-layout, .xml-converter-grid, .loadout-builder, .visual-loadout-layout, .loadout-slot-grid, .loadout-cargo-grid { grid-template-columns: 1fr; }
      .xml-output-panel { position: static; }
      .visual-browser, .visual-export-panel { position: static; }
      .owner-server-actions { justify-content: flex-start; }
      .zone-map { min-height: 0; aspect-ratio: 1 / 1; }
      .metric { text-align: left; }
      nav { display: none; }
    }
    @media (max-width: 720px) {
      header { position: static; display: grid; grid-template-columns: 1fr; align-items: start; padding: .75rem; gap: .75rem; }
      .brand img { width: 2.55rem; height: 2.55rem; }
      .brand strong { font-size: .95rem; }
      .brand span { font-size: .85rem; }
      .theme-picker { gap: .28rem; }
      .theme-picker button { width: 1.65rem; height: 1.65rem; }
      main { width: 100%; padding: .65rem .55rem 1.25rem; gap: .75rem; }
      .hero { display: block; padding: .85rem; }
      .hero img { display: none; }
      h1 { font-size: clamp(1.8rem, 10vw, 2.75rem); line-height: 1; }
      h2 { font-size: 1.35rem; }
      h3 { font-size: 1.05rem; }
      p, li, .tool-note { font-size: .9rem; }
      .field-help { font-size: .74rem; line-height: 1.25; }
      .stat, .card, .admin-panel, .section-panel { padding: .8rem; }
      .admin-panel { overflow-x: auto; -webkit-overflow-scrolling: touch; }
      .section-nav { display: none; }
      .mobile-section-picker { display: block; top: 0; }
      .mobile-section-picker select { min-height: 2.9rem; }
      .section-panel { scroll-margin-top: 5.25rem; }
      .server-tabs { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(13rem, 82vw); overflow-x: auto; flex-wrap: nowrap; padding-bottom: .25rem; -webkit-overflow-scrolling: touch; }
      .server-tab { min-width: 0; overflow-wrap: anywhere; }
      .shop-toolbar { grid-template-columns: 1fr; align-items: stretch; }
      .scenario-actions, .owner-server-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); min-width: 0; width: 100%; }
      .scenario-actions .inline-action, .owner-server-actions .inline-action { width: 100%; }
      .scenario-actions button, .owner-server-actions button, .owner-server-actions .button { width: 100%; white-space: normal; }
      .inline-action { grid-template-columns: 1fr; }
      .inline-action button { width: 100%; }
      button, .button, .tab-link, nav a { min-height: 2.65rem; padding: .62rem .7rem; font-size: .95rem; }
      input, textarea, select { min-height: 2.75rem; font-size: 16px; }
      .zone-map { min-height: 0; aspect-ratio: 1 / 1; }
      .zone-map::after { font-size: .76rem; right: .45rem; bottom: .45rem; }
      .zone-dot small { display: none; }
      .map-missing { font-size: .8rem; }
      .leader-row { gap: .4rem; }
      .leader-name { white-space: normal; }
      .item-table { min-width: 40rem; }
      .item-table th, .item-table td { padding: .55rem .5rem; font-size: .88rem; }
      .item-picker-controls { grid-template-columns: 1fr; }
      .visual-picker-grid, .visual-select-grid { max-height: 18rem; grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr)); }
      .visual-loadout-layout { gap: .65rem; }
      .loadout-item-grid { max-height: 28rem; overflow-y: auto; -webkit-overflow-scrolling: touch; }
      .loadout-item-card { min-height: 4.5rem; }
      .loadout-selected-slot span, .embed-preview span { overflow-wrap: anywhere; }
      body[data-section="pve"] .admin-form label { gap: .25rem; }
      body[data-section="pve"] .admin-form .field-help { display: none; }
      body[data-section="pve"] .admin-form label:focus-within .field-help { display: block; }
      body[data-section="pve"] .embed-preview { padding: .55rem .65rem; }
      body[data-section="pve"] .embed-preview span { font-size: .82rem; line-height: 1.25; }
      .xml-output-panel { position: static; }
      .table-scroll .item-table { min-width: 40rem; }
      .category-link, .option-card, .help-card { padding: .75rem; }
      .trial-notice { align-items: stretch; flex-direction: column; }
    }
    @media (max-width: 430px) {
      .scenario-actions, .owner-server-actions { grid-template-columns: 1fr; }
      .item-table { min-width: 36rem; }
      .table-scroll .item-table { min-width: 36rem; }
      .zone-map { min-height: 0; aspect-ratio: 1 / 1; }
      .pill { font-size: .76rem; }
    }
  </style>
</head>
<body data-section="{{ active_section }}" data-pve-tool="{{ pve_tool }}">
  {% set server = servers[0] if servers else none %}
  {% set server_qs = '&guild_id=' ~ server.guild_id if server else '' %}
  <header>
    <div class="brand">
      <img src="/brand-image" alt="Wandering Bot logo">
      <div><strong>Wandering Bot</strong><span>{{ view_title }}</span></div>
    </div>
    <nav>
      <a href="/">Overview</a>
      <a href="/admin">Admin</a>
      {% if auth.kind == "owner" %}<a href="/owner">Owner</a>{% endif %}
      <a href="/api/summary">API</a>
      <a href="/login">Switch Login</a>
      <a href="/logout">Logout</a>
    </nav>
    <div class="theme-picker" aria-label="Theme picker">
      <label>Theme
        <select data-theme-select onchange="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice(this.value)">
          <option value="command">Command</option>
        </select>
      </label>
      <button type="button" data-theme-choice="default" title="Wandering" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('default')"></button>
      <button type="button" data-theme-choice="forest" title="Forest" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('forest')"></button>
      <button type="button" data-theme-choice="amber" title="Amber" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('amber')"></button>
      <button type="button" data-theme-choice="steel" title="Steel" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('steel')"></button>
      <button type="button" data-theme-choice="highland" title="Highland" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('highland')"></button>
      <button type="button" data-theme-choice="daylight" title="Daylight" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('daylight')"></button>
      <button type="button" data-theme-choice="sandstorm" title="Sandstorm" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('sandstorm')"></button>
      <button type="button" data-theme-choice="midnight" title="Midnight" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('midnight')"></button>
      <button type="button" data-theme-choice="bloodmoon" title="Blood Moon" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('bloodmoon')"></button>
      <button type="button" data-theme-choice="radioactive" title="Radioactive" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('radioactive')"></button>
      <button type="button" data-theme-choice="arctic" title="Arctic" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('arctic')"></button>
      <button type="button" data-theme-choice="toxic" title="Toxic" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('toxic')"></button>
      <button type="button" data-theme-choice="violet" title="Violet" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('violet')"></button>
      <button type="button" data-theme-choice="rose" title="Rose" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('rose')"></button>
      <button type="button" data-theme-choice="command" title="Command" onclick="window.wanderingApplyThemeChoice && window.wanderingApplyThemeChoice('command')"></button>
    </div>
    <script>
      (function () {
        const serverTheme = "{{ dashboard_theme }}";
        const initialTheme = "command";
        function apply(theme, persist) {
          const safeTheme = "command";
          document.documentElement.dataset.theme = safeTheme === "default" ? "" : safeTheme;
          document.body.dataset.theme = safeTheme === "default" ? "" : safeTheme;
          document.querySelectorAll("[data-theme-select]").forEach((select) => { select.value = safeTheme; });
          document.querySelectorAll("[data-theme-choice]").forEach((button) => {
            button.classList.toggle("active", button.dataset.themeChoice === safeTheme);
          });
          localStorage.setItem("wanderingDashboardTheme", safeTheme);
          if (persist) {
            const token = new URLSearchParams(window.location.search).get("token");
            const guildId = new URLSearchParams(window.location.search).get("guild_id") || "{{ server.guild_id if server else '' }}";
            fetch(`/api/admin/theme${token ? `?token=${encodeURIComponent(token)}` : ""}`, {
              method: "POST",
              headers: {"Content-Type": "application/json", "Accept": "application/json"},
              credentials: "same-origin",
              body: JSON.stringify({theme: safeTheme, guild_id: guildId})
            }).catch(function () {});
          }
        }
        window.wanderingApplyThemeChoice = function (theme) { apply(theme, true); };
        apply(initialTheme, false);
      })();
    </script>
  </header>
  <aside class="command-sidebar" aria-label="Command dashboard navigation">
    <div class="command-logo">
      <img src="/brand-image" alt="Wandering Bot">
      <div>
        <strong>Wandering Bot</strong>
        <small>{{ server.guild_name if server else view_title }}</small>
        <span class="command-status"><span class="command-dot"></span>Online</span>
        <small>DayZ | {{ server.platform_label if server else 'Xbox' }} | {{ (server.map|capitalize) if server else 'Chernarus' }}</small>
      </div>
    </div>
    {% if servers|length > 1 %}
    <form class="command-server-form" method="get" action="/{{ 'owner' if mode == 'owner' else 'admin' }}">
      <input class="hidden-field" type="hidden" name="section" value="{{ active_section }}">
      {% if active_section == "pve" %}<input class="hidden-field" type="hidden" name="pve_tool" value="{{ pve_tool }}">{% endif %}
      <label>Active Server
        <select name="guild_id" onchange="this.form.submit()">
          {% for item in servers %}
          <option value="{{ item.guild_id }}" {% if server and item.guild_id == server.guild_id %}selected{% endif %}>{{ item.guild_name }} - {{ item.map|upper }}</option>
          {% endfor %}
        </select>
      </label>
      <button type="submit">Switch Server</button>
    </form>
    {% endif %}
    <div class="command-login-actions">
      <a href="/login">Switch Login</a>
      <a href="/logout">Logout</a>
    </div>
    <nav class="command-side-nav">
      <a class="{{ 'active' if active_section == 'overview' else '' }}" href="/admin?section=overview{{ server_qs }}">Overview</a>
      <a class="{{ 'active' if active_section == 'access' else '' }}" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=access{{ server_qs }}">Servers & Login</a>
      {% if section_allowed('pve') %}<a class="{{ 'active' if active_section == 'pve' else '' }}" href="/admin?section=pve&pve_tool=events{{ server_qs }}">Live Events</a>{% endif %}
      {% if section_allowed('zones') %}<a class="{{ 'active' if active_section == 'zones' else '' }}" href="/admin?section=zones{{ server_qs }}">Zones & Map</a>{% endif %}
      {% if section_allowed('xml-workshop') %}<a class="{{ 'active' if active_section == 'xml-workshop' else '' }}" href="/admin?section=xml-workshop{{ server_qs }}">XML Workshop</a>{% endif %}
      {% if section_allowed('visual-loadout') %}<a class="{{ 'active' if active_section == 'visual-loadout' else '' }}" href="/admin?section=visual-loadout{{ server_qs }}">Visual Loadout</a>{% endif %}
      {% if section_allowed('economy') %}<a class="{{ 'active' if active_section == 'economy' else '' }}" href="/admin?section=economy{{ server_qs }}">Economy</a>{% endif %}
      {% if section_allowed('shop') %}<a class="{{ 'active' if active_section == 'shop' else '' }}" href="/admin?section=shop{{ server_qs }}">Manage Shop</a>{% endif %}
      {% if section_allowed('server-rules') %}<a class="{{ 'active' if active_section == 'server-rules' else '' }}" href="/admin?section=server-rules{{ server_qs }}">Server Rules</a>{% endif %}
      {% if section_allowed('moderation') %}<a class="{{ 'active' if active_section == 'moderation' else '' }}" href="/admin?section=moderation{{ server_qs }}">Moderation</a>{% endif %}
      {% if section_allowed('leaderboards') %}<a class="{{ 'active' if active_section == 'leaderboards' else '' }}" href="/admin?section=leaderboards{{ server_qs }}">Leaderboards</a>{% endif %}
      <a class="{{ 'active' if active_section == 'help' else '' }}" href="/admin?section=help{{ server_qs }}">Help</a>
      {% if section_allowed('server-control') %}<a class="{{ 'active' if active_section == 'server-control' else '' }}" href="/admin?section=server-control{{ server_qs }}">Console</a>{% endif %}
    </nav>
    <div class="command-quick">
      <span>Quick actions</span>
      {% if section_allowed('pve') %}<a href="/admin?section=pve&pve_tool=builder{{ server_qs }}#pve-workshop">Queue Event</a>{% endif %}
      {% if section_allowed('zones') %}<a href="/admin?section=zones{{ server_qs }}#zones-list">Create Zone</a>{% endif %}
      {% if section_allowed('xml-workshop') %}<a href="/admin?section=xml-workshop{{ server_qs }}">Upload XML</a>{% endif %}
      {% if section_allowed('server-control') %}<a href="/admin?section=server-control{{ server_qs }}">Restart Server</a>{% endif %}
    </div>
  </aside>
  <main>
    <section class="hero">
      <div>
        <p class="muted">{{ generated_at }}</p>
        <h1>{{ view_title }}</h1>
        <p class="muted">Live readout for {{ auth.label }}. Server dashboards use private ID/password logins. Link another server from Servers & Login when you manage more than one.</p>
        {% if server %}
        <div class="pills">
          <span class="pill ok">{{ server.guild_name }}</span>
          <span class="pill">{{ server.map|upper }}</span>
          <span class="pill">{{ server.channels|length }} channels</span>
        </div>
        {% endif %}
      </div>
      <img src="/brand-image" alt="Wandering Bot mark">
    </section>

    {% if auth.kind == "owner" and server and server.dashboard_access.plan_status == "trial" and server.dashboard_access.trial_notice_enabled %}
    <section class="trial-notice" data-plan-notice data-plan-key="{{ server.guild_id }}-trial">
      <div><strong>Trial dashboard</strong> <span>{% if server.dashboard_access.trial_ends_at %}Trial ends {{ server.dashboard_access.trial_ends_at }}.{% else %}This server is currently running as a trial.{% endif %}</span></div>
      <button type="button" data-dismiss-plan-notice>Dismiss today</button>
    </section>
    {% endif %}

    <section class="stats">
      <div class="stat"><span>Server</span><strong>{{ server.map|upper if server else summary.guilds }}</strong></div>
      <div class="stat"><span>Online</span><strong>{{ summary.online }}</strong></div>
      <div class="stat"><span>Players</span><strong>{{ summary.players }}</strong></div>
      <div class="stat"><span>Shop</span><strong>{{ summary.shop_items }}</strong></div>
      <div class="stat"><span>Factions</span><strong>{{ summary.factions }}</strong></div>
    </section>

    {% if servers|length > 1 %}
    <section class="section-panel server-switcher" id="servers">
      <div class="section-head">
        <div>
          <h2>Server Switcher</h2>
          <p class="tool-note">{% if auth.kind == "owner" and mode == "owner" %}Owner view only: every server the bot knows about is visible here.{% else %}Admin view is scoped to the private dashboard login and linked servers only. Pick a server, then every category below uses that server's data and locked server identity.{% endif %}</p>
        </div>
      </div>
      <div class="server-tabs">
        {% for item in servers %}
        <a class="server-tab {{ 'active' if server and item.guild_id == server.guild_id else '' }}" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section={{ active_section }}{% if active_section == 'pve' %}&pve_tool={{ pve_tool }}{% endif %}&guild_id={{ item.guild_id }}">{{ item.guild_name }} · {{ item.map|upper }}</a>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    <section class="section-nav" aria-label="Dashboard sections">
      <a class="tab-link {{ 'active' if active_section == 'overview' else '' }}" href="/admin?section=overview{{ server_qs }}">Overview</a>
      {% if servers|length > 1 %}<a class="tab-link" href="/admin?section=overview{{ server_qs }}#servers">Servers</a>{% endif %}
      <a class="tab-link {{ 'active' if active_section == 'access' else '' }}" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=access{{ server_qs }}">Servers & Login</a>
      {% if section_allowed('leaderboards') %}<a class="tab-link {{ 'active' if active_section == 'leaderboards' else '' }}" href="/admin?section=leaderboards{{ server_qs }}">Leaderboards</a>{% endif %}
      {% if section_allowed('automations') %}<a class="tab-link {{ 'active' if active_section == 'automations' else '' }}" href="/admin?section=automations{{ server_qs }}">Embeds & Welcome</a>{% endif %}
      {% if section_allowed('factions') %}<a class="tab-link {{ 'active' if active_section == 'factions' else '' }}" href="/admin?section=factions{{ server_qs }}">Factions</a>{% endif %}
      {% if section_allowed('zones') %}<a class="tab-link {{ 'active' if active_section == 'zones' else '' }}" href="/admin?section=zones{{ server_qs }}">Zones</a>{% endif %}
      {% if section_allowed('members') %}<a class="tab-link {{ 'active' if active_section == 'members' else '' }}" href="/admin?section=members{{ server_qs }}">Members</a>{% endif %}
      {% if section_allowed('heatmaps') %}<a class="tab-link {{ 'active' if active_section == 'heatmaps' else '' }}" href="/admin?section=heatmaps{{ server_qs }}">Heatmaps</a>{% endif %}
      {% if section_allowed('pve') %}<a class="tab-link {{ 'active' if active_section == 'pve' else '' }}" href="/admin?section=pve&pve_tool=events{{ server_qs }}">Live Events</a>{% endif %}
      {% if section_allowed('economy') %}<a class="tab-link {{ 'active' if active_section == 'economy' else '' }}" href="/admin?section=economy{{ server_qs }}">Economy</a>{% endif %}
      {% if section_allowed('shop') %}<a class="tab-link {{ 'active' if active_section == 'shop' else '' }}" href="/admin?section=shop{{ server_qs }}">Manage Shop</a>{% endif %}
      {% if section_allowed('xml-workshop') %}<a class="tab-link {{ 'active' if active_section == 'xml-workshop' else '' }}" href="/admin?section=xml-workshop{{ server_qs }}">XML Workshop</a>{% endif %}
      {% if section_allowed('dayz-converter') %}<a class="tab-link {{ 'active' if active_section == 'dayz-converter' else '' }}" href="/admin?section=dayz-converter{{ server_qs }}">Map Converter</a>{% endif %}
      {% if section_allowed('loot-engine') %}<a class="tab-link {{ 'active' if active_section == 'loot-engine' else '' }}" href="/admin?section=loot-engine{{ server_qs }}">Loot Engine</a>{% endif %}
      {% if section_allowed('visual-loadout') %}<a class="tab-link {{ 'active' if active_section == 'visual-loadout' else '' }}" href="/admin?section=visual-loadout{{ server_qs }}">Visual Loadout</a>{% endif %}
      {% if section_allowed('bulk-economy') %}<a class="tab-link {{ 'active' if active_section == 'bulk-economy' else '' }}" href="/admin?section=bulk-economy{{ server_qs }}">Bulk Economy</a>{% endif %}
      {% if section_allowed('server-rules') %}<a class="tab-link {{ 'active' if active_section == 'server-rules' else '' }}" href="/admin?section=server-rules{{ server_qs }}">Server Rules</a>{% endif %}
      {% if section_allowed('moderation') %}<a class="tab-link {{ 'active' if active_section == 'moderation' else '' }}" href="/admin?section=moderation{{ server_qs }}">Moderation</a>{% endif %}
      {% if section_allowed('server-control') %}<a class="tab-link {{ 'active' if active_section == 'server-control' else '' }}" href="/admin?section=server-control{{ server_qs }}">Server Control</a>{% endif %}
      <a class="tab-link {{ 'active' if active_section == 'help' else '' }}" href="/admin?section=help{{ server_qs }}">Help</a>
      {% if auth.kind == "owner" %}<a class="tab-link {{ 'active' if mode == 'owner' and active_section == 'owner' else '' }}" href="/owner?section=owner">Owner Control</a>{% endif %}
      {% if auth.kind == "owner" and mode == "owner" %}<a class="tab-link {{ 'active' if active_section == 'access' else '' }}" href="/owner?section=access{{ server_qs }}">Access</a>{% endif %}
    </section>
    <section class="mobile-section-picker" aria-label="Dashboard section picker">
      <label>
        Jump to section
        <select onchange="if (this.value) window.location.href = this.value;">
          <option value="/admin?section=overview{{ server_qs }}" {{ 'selected' if active_section == 'overview' else '' }}>Overview</option>
          {% if servers|length > 1 %}<option value="/admin?section=overview{{ server_qs }}#servers">Servers</option>{% endif %}
          <option value="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=access{{ server_qs }}" {{ 'selected' if active_section == 'access' else '' }}>Servers & Login</option>
          {% if section_allowed('leaderboards') %}<option value="/admin?section=leaderboards{{ server_qs }}" {{ 'selected' if active_section == 'leaderboards' else '' }}>Leaderboards</option>{% endif %}
          {% if section_allowed('automations') %}<option value="/admin?section=automations{{ server_qs }}" {{ 'selected' if active_section == 'automations' else '' }}>Embeds & Welcome</option>{% endif %}
          {% if section_allowed('factions') %}<option value="/admin?section=factions{{ server_qs }}" {{ 'selected' if active_section == 'factions' else '' }}>Factions</option>{% endif %}
          {% if section_allowed('zones') %}<option value="/admin?section=zones{{ server_qs }}" {{ 'selected' if active_section == 'zones' else '' }}>Zones</option>{% endif %}
          {% if section_allowed('members') %}<option value="/admin?section=members{{ server_qs }}" {{ 'selected' if active_section == 'members' else '' }}>Members</option>{% endif %}
          {% if section_allowed('heatmaps') %}<option value="/admin?section=heatmaps{{ server_qs }}" {{ 'selected' if active_section == 'heatmaps' else '' }}>Heatmaps</option>{% endif %}
          {% if section_allowed('pve') %}<option value="/admin?section=pve&pve_tool=events{{ server_qs }}" {{ 'selected' if active_section == 'pve' else '' }}>Live Events</option>{% endif %}
          {% if section_allowed('economy') %}<option value="/admin?section=economy{{ server_qs }}" {{ 'selected' if active_section == 'economy' else '' }}>Economy</option>{% endif %}
          {% if section_allowed('shop') %}<option value="/admin?section=shop{{ server_qs }}" {{ 'selected' if active_section == 'shop' else '' }}>Manage Shop</option>{% endif %}
          {% if section_allowed('xml-workshop') %}<option value="/admin?section=xml-workshop{{ server_qs }}" {{ 'selected' if active_section == 'xml-workshop' else '' }}>XML Workshop</option>{% endif %}
          {% if section_allowed('dayz-converter') %}<option value="/admin?section=dayz-converter{{ server_qs }}" {{ 'selected' if active_section == 'dayz-converter' else '' }}>Map Converter</option>{% endif %}
          {% if section_allowed('loot-engine') %}<option value="/admin?section=loot-engine{{ server_qs }}" {{ 'selected' if active_section == 'loot-engine' else '' }}>Loot Engine</option>{% endif %}
          {% if section_allowed('visual-loadout') %}<option value="/admin?section=visual-loadout{{ server_qs }}" {{ 'selected' if active_section == 'visual-loadout' else '' }}>Visual Loadout</option>{% endif %}
          {% if section_allowed('bulk-economy') %}<option value="/admin?section=bulk-economy{{ server_qs }}" {{ 'selected' if active_section == 'bulk-economy' else '' }}>Bulk Economy</option>{% endif %}
          {% if section_allowed('server-rules') %}<option value="/admin?section=server-rules{{ server_qs }}" {{ 'selected' if active_section == 'server-rules' else '' }}>Server Rules</option>{% endif %}
          {% if section_allowed('moderation') %}<option value="/admin?section=moderation{{ server_qs }}" {{ 'selected' if active_section == 'moderation' else '' }}>Moderation</option>{% endif %}
          {% if section_allowed('server-control') %}<option value="/admin?section=server-control{{ server_qs }}" {{ 'selected' if active_section == 'server-control' else '' }}>Server Control</option>{% endif %}
          <option value="/admin?section=help{{ server_qs }}" {{ 'selected' if active_section == 'help' else '' }}>Help</option>
          {% if auth.kind == "owner" %}<option value="/owner?section=owner" {{ 'selected' if active_section == 'owner' else '' }}>Owner Control</option>{% endif %}
          {% if auth.kind == "owner" and mode == "owner" %}<option value="/owner?section=access{{ server_qs }}" {{ 'selected' if active_section == 'access' else '' }}>Access</option>{% endif %}
          <option value="/logout">Logout</option>
        </select>
      </label>
    </section>

    {% if active_section != "overview" %}
    <section class="command-page-head" aria-label="Current command section">
      <div>
        <span>{{ command_section.kicker }}</span>
        <h1>{{ command_section.title }}</h1>
        <p>{{ command_section.body }}</p>
      </div>
      <div class="command-page-meta">
        <span>{{ server.guild_name if server else view_title }}</span>
        <span>{{ server.platform_label if server else 'Xbox' }}</span>
        <span>{{ (server.map|capitalize) if server else 'Chernarus' }}</span>
      </div>
    </section>
    {% endif %}

    {% if active_section == "overview" %}
    <section class="command-overview" aria-label="Command overview">
      {% set active_event_count = (server.scenario_events|selectattr('enabled')|list|length) if server else 0 %}
      {% set zone_count = (server.zones|length) if server else 0 %}
      <div class="command-metrics">
        <div class="command-metric"><span>Players Online</span><strong>{{ summary.online }} / {{ summary.players }}</strong><small>Live tracker</small></div>
        <div class="command-metric"><span>Uptime</span><strong>Live</strong><small>{{ generated_at }}</small></div>
        <div class="command-metric"><span>PVE Events</span><strong>{{ server.scenario_events|length if server else 0 }}</strong><small>{{ active_event_count }} active</small></div>
        <div class="command-metric"><span>Zones</span><strong>{{ zone_count }}</strong><small>{{ zone_count }} mapped</small></div>
        <div class="command-metric"><span>Shop Items</span><strong>{{ summary.shop_items }}</strong><small>Economy ready</small></div>
        <div class="command-metric"><span>Last Refresh</span><strong>{{ generated_clock }}</strong><small>Dashboard sync</small></div>
      </div>

      <div class="command-grid">
        <article class="command-card">
          <div class="command-card-head">
            <h2>Live Event Manager</h2>
            <a class="button" href="/admin?section=pve&pve_tool=events{{ server_qs }}#pve-workshop">Open Events</a>
          </div>
          <div class="command-table-scroll">
          <table class="command-table">
            <thead><tr><th>ID</th><th>Type</th><th>Name</th><th>Class</th><th>Position</th><th>Runs</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {% for event in (server.scenario_events if server else [])[:5] %}
              {% set status_text = event.status or ('Running' if event.enabled else 'Idle') %}
              {% set status_lower = status_text|string|lower %}
              {% set status_label = 'Failed' if 'fail' in status_lower else ('Ready' if 'ready' in status_lower else ('Done' if 'done' in status_lower or 'uploaded' in status_lower else ('Uploading' if 'upload' in status_lower or 'starting' in status_lower else ('Running' if event.enabled else 'Queued')))) %}
              <tr>
                <td>{{ event.id or loop.index }}</td>
                <td>{{ event.event_type or 'event' }}</td>
                <td>{{ event.name or event.event_name or 'Scenario' }}</td>
                <td>{{ event.class_name or '-' }}</td>
                <td>{{ event.x or '-' }}, {{ event.z or '-' }}</td>
                <td>{{ event.remaining_restarts or event.runs or 0 }}</td>
                <td><span class="command-badge {{ 'ok' if status_label in ['Done', 'Running'] else ('bad' if status_label == 'Failed' else 'warn') }}" title="{{ status_text }}">{{ status_label }}</span></td>
                <td><div class="command-mini-actions"><a href="/admin?section=pve&pve_tool=builder{{ server_qs }}#pve-workshop">Edit</a><a href="/admin?section=pve&pve_tool=events{{ server_qs }}#pve-workshop">View</a></div></td>
              </tr>
              {% else %}
              <tr><td colspan="8">No live events queued yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
          </div>
        </article>

        <article class="command-card">
          <div class="command-card-head">
            <h3>Visual Loadout</h3>
            <a class="button" href="/admin?section=visual-loadout{{ server_qs }}#visual-loadout">Open Builder</a>
          </div>
          <div class="command-loadout">
            <div class="command-gear-column">
              {% for card in visual_loadout_slot_cards[:4] %}
              {% set item = card.item %}
              <a class="command-gear-card" href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ card.slot.key|urlencode }}#visual-loadout">
                {% if item.name %}<img src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt="">{% endif %}
                <span>{{ card.slot.label }}</span><strong>{{ item.name if item.name else 'Empty' }}</strong>
              </a>
              {% endfor %}
            </div>
            <div class="command-paperdoll command-character"><img class="command-character-portrait" src="/brand-character" alt="Wandering Bot loadout preview"></div>
            <div class="command-gear-column">
              {% for card in visual_loadout_slot_cards[4:8] %}
              {% set item = card.item %}
              <a class="command-gear-card" href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ card.slot.key|urlencode }}#visual-loadout">
                {% if item.name %}<img src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt="">{% endif %}
                <span>{{ card.slot.label }}</span><strong>{{ item.name if item.name else 'Empty' }}</strong>
              </a>
              {% endfor %}
            </div>
            <div class="command-loadout-extra">
              {% for card in visual_loadout_slot_cards[8:13] %}
              {% set item = card.item %}
              <a class="command-gear-card" href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ card.slot.key|urlencode }}#visual-loadout">
                {% if item.name %}<img src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt="">{% endif %}
                <span>{{ card.slot.label }}</span><strong>{{ item.name if item.name else 'Empty' }}</strong>
              </a>
              {% endfor %}
            </div>
          </div>
        </article>
      </div>

      <div class="command-row">
        <article class="command-card command-map-card">
          <div class="command-card-head">
            <h3>Map / Event Builder</h3>
            <div class="command-mini-actions"><a href="/admin?section=zones{{ server_qs }}">Add Zone</a><a href="/admin?section=pve&pve_tool=builder{{ server_qs }}">Event Mode</a></div>
          </div>
          <div class="command-map" {% if server %}style="--map-image: url('/map-image/{{ server.map_key }}');"{% endif %}>
            {% for zone in (server.zones if server else [])[:10] %}
            <a class="command-zone-dot" href="/admin?section=zones{{ server_qs }}&edit_zone={{ (zone.id or zone.name)|urlencode }}#zone-edit-form" style="--x: {{ zone.x_percent|default(50) }}; --y: {{ zone.y_percent|default(50) }}; --zone-colour: {{ zone.display_colour or zone.colour or '#26efe4' }};">
              {{ loop.index }}<span>{{ zone.name }}</span>
            </a>
            {% endfor %}
            <div class="command-map-toolbar">
              <label class="command-check"><input type="checkbox" checked> Zones</label>
              <label class="command-check"><input type="checkbox" checked> Events</label>
              <label class="command-check"><input type="checkbox"> Players</label>
              <label class="command-check"><input type="checkbox"> Grid</label>
            </div>
          </div>
        </article>

        <article class="command-card">
          <div class="command-card-head"><h3>New Radar Zone</h3></div>
          <form class="command-zone-form" method="get" action="/admin">
            <input class="hidden-field" name="section" value="zones">
            {% if server %}<input class="hidden-field" name="guild_id" value="{{ server.guild_id }}">{% endif %}
            <label>Zone type <select name="draft_type"><option value="radar">Radar ping zone</option><option value="safe">Safe zone</option><option value="pvp">PVP zone</option></select></label>
            <label>Shape <select name="draft_shape"><option value="circle">Circle</option><option value="polygon">Boundary</option></select></label>
            <label>Center X <input name="draft_x" value="{{ request.args.get('draft_x', '4210') }}"></label>
            <label>Center Z <input name="draft_z" value="{{ request.args.get('draft_z', '11580') }}"></label>
            <label>Radius (m) <input type="number" name="draft_radius" value="{{ request.args.get('draft_radius', '250') }}"></label>
            <label>Name <input name="draft_name" value="{{ request.args.get('draft_name', 'New radar zone') }}"></label>
            <div class="toolbar"><a class="button" href="/admin?section=zones{{ server_qs }}">Cancel</a><button type="submit">Save Zone</button></div>
          </form>
        </article>

        <article class="command-card">
          <div class="command-card-head">
            <h3>PVE Workshop</h3>
            <a class="button" href="/admin?section=xml-workshop{{ server_qs }}">View Workshop</a>
          </div>
          <div class="command-upload-list">
            {% for event in (server.scenario_events if server else [])[:4] %}
            {% set event_status = event.status or ('Imported' if event.enabled else 'Queued') %}
            <div class="command-upload-row"><span>{{ event.name or event.event_type or 'Scenario event' }}</span><strong class="{{ 'ok' if event.enabled else '' }}">{{ event_status }}</strong></div>
            {% else %}
            <div class="command-upload-row"><span>No recent PVE uploads</span><strong>Ready</strong></div>
            {% endfor %}
          </div>
        </article>
      </div>
    </section>
    <section class="category-grid" aria-label="Main categories">
      <a class="category-link" href="/admin?section=leaderboards{{ server_qs }}"><strong>Leaderboard</strong><span>Live kills, deaths, builds and rankings.</span></a>
      <a class="category-link" href="/admin?section=automations{{ server_qs }}"><strong>Embeds & Welcome</strong><span>Auto messages, welcomes and reaction roles.</span></a>
      <a class="category-link" href="/admin?section=factions{{ server_qs }}"><strong>Factions</strong><span>Faction setup, leaders, roles and members.</span></a>
      <a class="category-link" href="/admin?section=zones{{ server_qs }}"><strong>Zones</strong><span>Safe zones, PVP zones, radar pings and ban/action rules.</span></a>
      <a class="category-link" href="/admin?section=members{{ server_qs }}"><strong>Members</strong><span>Server player list, Discord IDs, kick and ban actions.</span></a>
      <a class="category-link" href="/admin?section=economy{{ server_qs }}"><strong>Economy</strong><span>Wallets, wages, rewards and punishments.</span></a>
      <a class="category-link" href="/admin?section=shop{{ server_qs }}"><strong>Manage Shop</strong><span>Items, prices, limits, availability and role restrictions.</span></a>
      <a class="category-link" href="/admin?section=xml-workshop{{ server_qs }}"><strong>XML Workshop</strong><span>Loot quality, filled bags, loadouts and vehicle cargo recipes.</span></a>
      <a class="category-link" href="/admin?section=dayz-converter{{ server_qs }}"><strong>Map Converter</strong><span>Turn DayZ Editor JSON into events, spawns and event group XML snippets.</span></a>
      <a class="category-link" href="/admin?section=loot-engine{{ server_qs }}"><strong>Loot Engine</strong><span>Edit types.xml values and generate player or vehicle loadout XML.</span></a>
      <a class="category-link" href="/admin?section=visual-loadout{{ server_qs }}"><strong>Visual Loadout</strong><span>Build spawn gear visually and download the cfggameplay package.</span></a>
      <a class="category-link" href="/admin?section=bulk-economy{{ server_qs }}"><strong>Bulk Economy</strong><span>Batch-edit types.xml counts and lifetimes with validation.</span></a>
      <a class="category-link" href="/admin?section=server-rules{{ server_qs }}"><strong>Server Rules</strong><span>Discord link enforcement, Nitrado bans and on-screen server messages.</span></a>
      <a class="category-link" href="/admin?section=moderation{{ server_qs }}"><strong>Moderation Guard</strong><span>Spam, invite adverts, scam phrases, mass mentions and auto actions.</span></a>
      <a class="category-link" href="/admin?section=server-control{{ server_qs }}"><strong>Server Control</strong><span>Restart schedules and base/container damage toggles.</span></a>
      <a class="category-link" href="/admin?section=pve&pve_tool=events{{ server_qs }}"><strong>Live Events</strong><span>Track airdrops, hordes, gas zones, animals and vehicles.</span></a>
      <a class="category-link" href="/admin?section=heatmaps{{ server_qs }}"><strong>Heatmaps</strong><span>PVP, PVE, infected, animal and build activity.</span></a>
      <a class="category-link" href="/admin?section=help{{ server_qs }}"><strong>Help</strong><span>Walkthroughs, setup notes and what each control does.</span></a>
      <a class="category-link" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=access{{ server_qs }}"><strong>Servers & Login</strong><span>Switch server, link another server, or change dashboard login.</span></a>
    </section>
    {% endif %}

    {% if active_section == "leaderboards" %}
    <section class="section-panel" id="leaderboards">
      <div class="discord-board">
        <h2>{{ server.guild_name if server else 'Server' }} — Server Leaderboard</h2>
        <p><em>Top 10 per category — dashboard live view.</em></p>
        <div class="leader-category-grid">
          {% for board in (server.leaderboards if server else []) %}
          <article class="lb-card">
            <h3>{{ board.title }}</h3>
            <div class="lb-list">
              {% for row in board.rows %}
              <div class="lb-row">
                <span class="lb-rank {{ row.medal }}">{{ loop.index }}</span>
                <span>{{ row.name }}</span>
                <span>·</span>
                <span class="lb-value">{{ row.value }}</span>
              </div>
              {% else %}
              <p class="lb-empty">— no data yet —</p>
              {% endfor %}
            </div>
          </article>
          {% endfor %}
        </div>
      </div>
    </section>
    {% endif %}

    {% if mode == "owner" and active_section in ["owner", "overview"] %}
    <section class="section-panel" id="owner-control">
      <div class="section-head">
        <div>
          <h2>Owner Command Center</h2>
          <p class="tool-note">Only your owner token can open this section. Use it to inspect every guild, jump into a server dashboard, and control which modules customers can use.</p>
        </div>
      </div>
      <div class="mini-grid">
        <div class="mini-card"><span class="muted">Guilds</span><strong>{{ summary.guilds }}</strong></div>
        <div class="mini-card"><span class="muted">Members tracked</span><strong>{{ summary.players }}</strong></div>
        <div class="mini-card"><span class="muted">Heat points</span><strong>{{ summary.heatmap_points }}</strong></div>
        <div class="mini-card"><span class="muted">PVE quests</span><strong>{{ summary.pve_active }}</strong></div>
      </div>
      <div class="panel-grid" style="margin-top:.85rem">
        <article class="admin-panel">
          <h3>Owner Notifications</h3>
          <div class="stack">
            {% for note in owner_notifications %}
            <div class="notification"><strong>{{ note.title }}</strong><span>{{ note.body }}</span></div>
            {% else %}
            <p class="muted">No owner alerts right now.</p>
            {% endfor %}
          </div>
        </article>
        <article class="admin-panel">
          <h3>All Server Dashboards</h3>
          <div class="owner-server-list">
            {% for owned in servers %}
            <div class="owner-server-card">
              <div>
                <h4>{{ owned.guild_name }}</h4>
                <div class="owner-server-meta">
                  <span class="pill">{{ owned.map|upper }}</span>
                  <span class="pill {{ 'ok' if owned.dashboard_access.enabled else 'bad' }}">Admin {{ 'enabled' if owned.dashboard_access.enabled else 'locked' }}</span>
                  <span class="pill">{{ owned.dashboard_access.tier or owned.dashboard_access.plan_status }}</span>
                </div>
              </div>
              <div class="owner-server-actions">
                <a class="button" href="/owner?guild_id={{ owned.guild_id }}">Open</a>
                {% if owned.dashboard_access.owner_admin_visible %}
                <form class="admin-form inline-action" method="post" action="/api/owner/guild-action" data-route="/api/owner/guild-action">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="return_to" value="/owner?guild_id={{ owned.guild_id }}#owner-servers">
                  <input class="hidden-field" name="action" value="hide_from_owner_admin">
                  <button type="submit">Hide From My Admin</button> <span class="result muted"></span>
                </form>
                {% else %}
                <form class="admin-form inline-action" method="post" action="/api/owner/guild-action" data-route="/api/owner/guild-action">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="return_to" value="/owner?guild_id={{ owned.guild_id }}#owner-servers">
                  <input class="hidden-field" name="action" value="show_in_owner_admin">
                  <button type="submit">Show In My Admin</button> <span class="result muted"></span>
                </form>
                {% endif %}
                {% if not owned.dashboard_access.enabled %}
                <form class="admin-form inline-action" method="post" action="/api/admin/guild-access" data-route="/api/admin/guild-access">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="return_to" value="/owner?guild_id={{ owned.guild_id }}#owner-servers">
                  <input class="hidden-field" name="enabled" value="true">
                  <input class="hidden-field" name="tier" value="owner">
                  <input class="hidden-field" name="plan_status" value="lifetime">
                  <button type="submit">Enable Admin Access</button> <span class="result muted"></span>
                </form>
                {% else %}
                <form class="admin-form inline-action" method="post" action="/api/admin/guild-access" data-route="/api/admin/guild-access" data-confirm="This locks normal admin dashboard login for {{ owned.guild_name }}. Your owner login will still work. Continue?">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="return_to" value="/owner?guild_id={{ owned.guild_id }}#owner-servers">
                  <input class="hidden-field" name="enabled" value="false">
                  <input class="hidden-field" name="tier" value="{{ owned.dashboard_access.tier or 'none' }}">
                  <input class="hidden-field" name="plan_status" value="{{ owned.dashboard_access.plan_status or 'none' }}">
                  <button type="submit">Lock Admin Access</button> <span class="result muted"></span>
                </form>
                {% endif %}
                <form class="admin-form inline-action" method="post" action="/api/owner/guild-action" data-route="/api/owner/guild-action" data-confirm="This will make the bot leave {{ owned.guild_name }}. Continue?">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="return_to" value="/owner?guild_id={{ owned.guild_id }}#owner-servers">
                  <input class="hidden-field" name="action" value="leave">
                  <button type="submit">Leave Discord</button> <span class="result muted"></span>
                </form>
                <form class="admin-form inline-action" method="post" action="/api/owner/guild-action" data-route="/api/owner/guild-action" data-confirm="This will make the bot leave {{ owned.guild_name }} and remove this guild from dashboard data. Continue?">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="return_to" value="/owner?guild_id={{ owned.guild_id }}#owner-servers">
                  <input class="hidden-field" name="action" value="leave_and_remove">
                  <button type="submit">Leave + Remove Data</button> <span class="result muted"></span>
                </form>
              </div>
            </div>
            {% endfor %}
          </div>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "automations" %}
    <section class="section-panel" id="automations">
      <div class="section-head">
        <div>
          <h2>Auto Messages & Embeds</h2>
          <p class="tool-note">Create messages the bot can use for rules, restarts, welcomes, events, shop notices, and staff announcements.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Embed & Timed Message Builder</h3>
          {% set edit_embed_key = request.args.get('edit_embed', '') %}
          {% set edit_embed = namespace(name='server-rules', template_id='server-rules', content_mode='embed', channel_key='', title='Server Rules', colour='#8d963e', author_name='', author_icon_url='', thumbnail_url='', image_url='', footer_text='Wandering Bot', footer_icon_url='', mention_mode='none', mention_role_id='', schedule_type='manual', schedule_time='', event_filter='', event_minimum=0, interval_minutes=60, timezone='Europe/Dublin', button_label='', button_url='', body='Respect the server, no exploits, and keep it fair.', fields_lines='Server Rule | No exploits, duping, or glitch abuse. | false\nRespect | Keep chat and gameplay fair. | false') %}
          {% if server and edit_embed_key %}
            {% for template in server.embed_templates %}
              {% if template.template_id == edit_embed_key or template.name == edit_embed_key %}
                {% set embed = template.embed or {} %}
                {% set delivery = template.delivery or {} %}
                {% set schedule = template.schedule or {} %}
                {% set edit_embed.name = template.name or 'custom-message' %}
                {% set edit_embed.template_id = template.template_id or template.id or '' %}
                {% set edit_embed.content_mode = delivery.content_mode or template.content_mode or 'embed' %}
                {% set edit_embed.channel_key = delivery.channel_key or template.channel_key or '' %}
                {% set edit_embed.title = embed.title or template.title or '' %}
                {% set edit_embed.colour = embed.colour or embed.color or template.colour or '#8d963e' %}
                {% set edit_embed.author_name = embed.author.name if embed.author else template.author_name or '' %}
                {% set edit_embed.author_icon_url = embed.author.icon_url if embed.author else template.author_icon_url or '' %}
                {% set edit_embed.thumbnail_url = embed.thumbnail_url or template.thumbnail_url or '' %}
                {% set edit_embed.image_url = embed.image_url or template.image_url or '' %}
                {% set edit_embed.footer_text = embed.footer.text if embed.footer else template.footer_text or '' %}
                {% set edit_embed.footer_icon_url = embed.footer.icon_url if embed.footer else template.footer_icon_url or '' %}
                {% set edit_embed.mention_mode = delivery.mention_mode or template.mention_mode or 'none' %}
                {% set edit_embed.mention_role_id = delivery.mention_role_id or template.mention_role_id or '' %}
                {% set edit_embed.schedule_type = schedule.type or template.schedule_type or 'manual' %}
                {% set edit_embed.schedule_time = schedule.time or template.schedule_time or '' %}
                {% set edit_embed.event_filter = schedule.event_filter or template.event_filter or '' %}
                {% set edit_embed.event_minimum = schedule.event_minimum if schedule.event_minimum is defined else template.event_minimum or 0 %}
                {% set edit_embed.interval_minutes = schedule.interval_minutes if schedule.interval_minutes is defined else template.interval_minutes or 60 %}
                {% set edit_embed.timezone = schedule.timezone or template.timezone or 'Europe/Dublin' %}
                {% set edit_embed.button_label = delivery.button_label or template.button_label or '' %}
                {% set edit_embed.button_url = delivery.button_url or template.button_url or '' %}
                {% set edit_embed.body = embed.description or template.body or '' %}
                {% set lines = namespace(value='') %}
                {% for field in embed.fields or [] %}
                  {% set field_line = (field.name or '') ~ ' | ' ~ (field.value or '') ~ ' | ' ~ ('true' if field.inline else 'false') %}
                  {% set lines.value = lines.value ~ ('\n' if lines.value else '') ~ field_line %}
                {% endfor %}
                {% set edit_embed.fields_lines = lines.value %}
              {% endif %}
            {% endfor %}
          {% endif %}
          {% set edit_record_section = request.args.get('edit_record_section', '') %}
          {% set edit_record_id = request.args.get('edit_record_id', '') %}
          {% set edit_welcome = namespace(automation_id='', name='new-survivor-welcome', channel_key='', enabled='true', birthday_role_id='', send_hour='10:00', message='Welcome survivor. Read the rules, link your gamer tag, and good luck out there.') %}
          {% set edit_utility = namespace(module='server_stats', enabled='true', channel_key='', limit=10, xp_per_message=15, cooldown_seconds=60, card_colour='#8d963e', background_url='', notes='Configure this module for this server.') %}
          {% set edit_panel = namespace(panel_id='', name='server-roles', channel_key='', roles='Verified | yes | 1234567890\nTrader pings | coin | 1234567890\nEvent pings | bell | 1234567890') %}
          {% if server and edit_record_section == 'welcome_automations' and edit_record_id %}
            {% for automation in server.welcome_automations %}
              {% set automation_id = automation.automation_id or automation.name %}
              {% if automation_id == edit_record_id %}
                {% set edit_welcome.automation_id = automation_id %}
                {% set edit_welcome.name = automation.name or 'new-survivor-welcome' %}
                {% set edit_welcome.channel_key = automation.channel_key or '' %}
                {% set edit_welcome.enabled = 'true' if automation.enabled else 'false' %}
                {% set edit_welcome.birthday_role_id = automation.birthday_role_id or '' %}
                {% set edit_welcome.send_hour = automation.send_hour or '10:00' %}
                {% set edit_welcome.message = automation.message or '' %}
              {% endif %}
            {% endfor %}
          {% endif %}
          {% if server and edit_record_section == 'utility_configs' and edit_record_id %}
            {% for utility in server.utility_configs %}
              {% set utility_id = utility.module or utility.name %}
              {% if utility_id == edit_record_id %}
                {% set edit_utility.module = utility.module or utility.name or 'server_stats' %}
                {% set edit_utility.enabled = 'true' if utility.enabled else 'false' %}
                {% set edit_utility.channel_key = utility.channel_key or '' %}
                {% set edit_utility.limit = utility.limit or 10 %}
                {% set edit_utility.xp_per_message = utility.xp_per_message or 15 %}
                {% set edit_utility.cooldown_seconds = utility.cooldown_seconds or 60 %}
                {% set edit_utility.card_colour = utility.card_colour or '#8d963e' %}
                {% set edit_utility.background_url = utility.background_url or '' %}
                {% set edit_utility.notes = utility.notes or '' %}
              {% endif %}
            {% endfor %}
          {% endif %}
          {% if server and edit_record_section == 'reaction_role_panels' and edit_record_id %}
            {% for panel in server.reaction_role_panels %}
              {% set panel_id = panel.panel_id or panel.name %}
              {% if panel_id == edit_record_id %}
                {% set edit_panel.panel_id = panel_id %}
                {% set edit_panel.name = panel.name or 'server-roles' %}
                {% set edit_panel.channel_key = panel.channel_key or '' %}
                {% set edit_panel.roles = panel.roles or '' %}
              {% endif %}
            {% endfor %}
          {% endif %}
          <form id="embed-template-form" class="admin-form {% if edit_embed_key %}dashboard-edit-modal{% endif %}" method="post" action="/api/admin/embed-template" data-route="/api/admin/embed-template">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=automations&guild_id={{ server.guild_id if server else '' }}#embed-template-form">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Purpose
              <select name="name">
                <option value="timed-reminder" {% if edit_embed.name == 'timed-reminder' %}selected{% endif %}>Timed reminder</option>
                <option value="server-rules" {% if edit_embed.name == 'server-rules' %}selected{% endif %}>Server rules</option>
                <option value="restart-warning" {% if edit_embed.name == 'restart-warning' %}selected{% endif %}>Restart warning</option>
                <option value="event-announcement" {% if edit_embed.name == 'event-announcement' %}selected{% endif %}>Event announcement</option>
                <option value="shop-notice" {% if edit_embed.name == 'shop-notice' %}selected{% endif %}>Shop notice</option>
                <option value="staff-alert" {% if edit_embed.name == 'staff-alert' %}selected{% endif %}>Staff alert</option>
                <option value="giveaway" {% if edit_embed.name == 'giveaway' %}selected{% endif %}>Giveaway</option>
                <option value="level-up" {% if edit_embed.name == 'level-up' %}selected{% endif %}>Level up notice</option>
                <option value="server-stats" {% if edit_embed.name == 'server-stats' %}selected{% endif %}>Server stats panel</option>
                <option value="birthday" {% if edit_embed.name == 'birthday' %}selected{% endif %}>Birthday message</option>
                <option value="moderation" {% if edit_embed.name == 'moderation' %}selected{% endif %}>Moderation message</option>
                <option value="custom-command" {% if edit_embed.name == 'custom-command' %}selected{% endif %}>Custom command response</option>
                <option value="custom-message" {% if edit_embed.name == 'custom-message' %}selected{% endif %}>Custom message</option>
              </select>
            </label>
            <label>Message key <input name="template_id" value="{{ edit_embed.template_id }}" placeholder="unique name for this embed"></label>
            <label>Message type
              <select name="content_mode"><option value="embed" {% if edit_embed.content_mode == 'embed' %}selected{% endif %}>Embed</option><option value="text" {% if edit_embed.content_mode == 'text' %}selected{% endif %}>Plain text</option><option value="both" {% if edit_embed.content_mode == 'both' %}selected{% endif %}>Text + embed</option></select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if edit_embed.channel_key and (channel.value == edit_embed.channel_key or channel.id == edit_embed.channel_key) %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Title <input name="title" value="{{ edit_embed.title }}"></label>
            <label>Colour <input name="colour" type="color" value="{{ edit_embed.colour }}"></label>
            <label>Author name <input name="author_name" value="{{ edit_embed.author_name }}" placeholder="optional"></label>
            <label>Author icon URL <input name="author_icon_url" value="{{ edit_embed.author_icon_url }}" placeholder="https://..."></label>
            <label>Thumbnail URL <input name="thumbnail_url" value="{{ edit_embed.thumbnail_url }}" placeholder="https://..."></label>
            <label>Large image URL <input name="image_url" value="{{ edit_embed.image_url }}" placeholder="https://..."></label>
            <label>Footer text <input name="footer_text" value="{{ edit_embed.footer_text }}"></label>
            <label>Footer icon URL <input name="footer_icon_url" value="{{ edit_embed.footer_icon_url }}" placeholder="https://..."></label>
            <label>Mention
              <select name="mention_mode"><option value="none" {% if edit_embed.mention_mode == 'none' %}selected{% endif %}>No mention</option><option value="everyone" {% if edit_embed.mention_mode == 'everyone' %}selected{% endif %}>@everyone</option><option value="here" {% if edit_embed.mention_mode == 'here' %}selected{% endif %}>@here</option><option value="role" {% if edit_embed.mention_mode == 'role' %}selected{% endif %}>Role mention</option></select>
            </label>
            <label>Role ID to mention <input name="mention_role_id" value="{{ edit_embed.mention_role_id }}" placeholder="optional role id"></label>
            <label>Schedule / trigger
              <select name="schedule_type">
                <option value="manual" {% if edit_embed.schedule_type == 'manual' %}selected{% endif %}>Manual / save only</option>
                <option value="timer" {% if edit_embed.schedule_type == 'timer' %}selected{% endif %}>Timer</option>
                <option value="daily" {% if edit_embed.schedule_type == 'daily' %}selected{% endif %}>Daily at time</option>
                <option value="weekly" {% if edit_embed.schedule_type == 'weekly' %}selected{% endif %}>Weekly at time</option>
                <option value="interval" {% if edit_embed.schedule_type == 'interval' %}selected{% endif %}>Repeat every X minutes</option>
                <option value="member_join" {% if edit_embed.schedule_type == 'member_join' %}selected{% endif %}>Member joins</option>
                <option value="member_leave" {% if edit_embed.schedule_type == 'member_leave' %}selected{% endif %}>Member leaves</option>
                <option value="level_up" {% if edit_embed.schedule_type == 'level_up' %}selected{% endif %}>Level up</option>
                <option value="birthday" {% if edit_embed.schedule_type == 'birthday' %}selected{% endif %}>Member birthday</option>
                <option value="stats_refresh" {% if edit_embed.schedule_type == 'stats_refresh' %}selected{% endif %}>Server stats refresh</option>
                <option value="player_kill" {% if edit_embed.schedule_type == 'player_kill' %}selected{% endif %}>Player kills another player</option>
                <option value="player_death" {% if edit_embed.schedule_type == 'player_death' %}selected{% endif %}>Player dies</option>
                <option value="zombie_death" {% if edit_embed.schedule_type == 'zombie_death' %}selected{% endif %}>Player killed by infected</option>
                <option value="animal_death" {% if edit_embed.schedule_type == 'animal_death' %}selected{% endif %}>Player killed by animal</option>
                <option value="longshot" {% if edit_embed.schedule_type == 'longshot' %}selected{% endif %}>Longshot recorded</option>
                <option value="flag_raise" {% if edit_embed.schedule_type == 'flag_raise' %}selected{% endif %}>Territory flag raised</option>
                <option value="flag_lower" {% if edit_embed.schedule_type == 'flag_lower' %}selected{% endif %}>Territory flag lowered</option>
                <option value="player_join_server" {% if edit_embed.schedule_type == 'player_join_server' %}selected{% endif %}>Player joins DayZ server</option>
                <option value="player_leave_server" {% if edit_embed.schedule_type == 'player_leave_server' %}selected{% endif %}>Player leaves DayZ server</option>
                <option value="chat_keyword" {% if edit_embed.schedule_type == 'chat_keyword' %}selected{% endif %}>Discord message contains keyword</option>
                <option value="wallet_change" {% if edit_embed.schedule_type == 'wallet_change' %}selected{% endif %}>Wallet balance changes</option>
                <option value="shop_purchase" {% if edit_embed.schedule_type == 'shop_purchase' %}selected{% endif %}>Shop purchase queued</option>
                <option value="quest_complete" {% if edit_embed.schedule_type == 'quest_complete' %}selected{% endif %}>PVE quest completed</option>
                <option value="radar_enter" {% if edit_embed.schedule_type == 'radar_enter' %}selected{% endif %}>Player enters radar zone</option>
                <option value="safe_zone_enter" {% if edit_embed.schedule_type == 'safe_zone_enter' %}selected{% endif %}>Player enters safe zone</option>
              </select>
            </label>
            <label>Time / day <input name="schedule_time" value="{{ edit_embed.schedule_time }}" placeholder="10:00, Monday 18:00, etc."></label>
            <label>Player/event filter <input name="event_filter" value="{{ edit_embed.event_filter }}" placeholder="keyword, player name, weapon, zone, any"></label>
            <label>Minimum value <input name="event_minimum" type="number" value="{{ edit_embed.event_minimum }}" placeholder="distance, kills, amount, etc."></label>
            <label>Interval minutes <input name="interval_minutes" type="number" value="{{ edit_embed.interval_minutes }}"></label>
            <label>Timezone <input name="timezone" value="{{ edit_embed.timezone }}"></label>
            <label>Button label <input name="button_label" value="{{ edit_embed.button_label }}" placeholder="optional link button"></label>
            <label>Button URL <input name="button_url" value="{{ edit_embed.button_url }}" placeholder="https://..."></label>
            <label class="full">Message <textarea name="body">{{ edit_embed.body }}</textarea></label>
            <label class="full">Embed fields <textarea name="fields_lines">{{ edit_embed.fields_lines }}</textarea></label>
            <div class="full embed-preview">
              <strong>Embed preview shape</strong>
              <span>Title, description, colour, author, thumbnail/image, footer, custom fields, link button and trigger settings are saved together.</span>
              <small>Fields use: Name | Value | inline true/false</small>
            </div>
            <div class="full modal-actions"><button type="submit">Save Message</button>{% if edit_embed_key %}<a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}#embed-template-form">Close</a>{% endif %} <span class="result muted"></span></div>
          </form>
          <div class="stack" style="margin-top:.75rem" data-embed-template-list>
            {% for template in (server.embed_templates if server else []) %}
            <div class="notification" data-embed-template-card data-remove-row data-template-id="{{ template.template_id }}">
              <div class="row-between">
                <div>
                  <strong>{{ template.template_id }}</strong>
                  <span>{{ template.name }} -> {{ template.schedule.type if template.schedule else 'manual' }}</span>
                  <small>Channel: {{ channel_label(server.channels if server else [], template.delivery.channel_key if template.delivery else '', 'not set') }}{% if template.schedule and template.schedule.time %} | Time: {{ template.schedule.time }}{% endif %}</small>
                </div>
                <div class="inline-actions">
                  <a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}&edit_embed={{ (template.template_id or template.name)|urlencode }}#embed-template-form" data-embed-template-edit>Edit</a>
                  <form class="admin-form inline-action" method="post" action="/api/admin/embed-template-action" data-route="/api/admin/embed-template-action" data-confirm="Delete embed template {{ template.template_id }}?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="return_to" value="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}#embed-template-form">
                    <input class="hidden-field" name="dashboard_mode" value="{{ mode }}">
                    <input class="hidden-field" name="template_id" value="{{ template.template_id }}">
                    <input class="hidden-field" name="action" value="delete">
                    <button type="submit" data-embed-template-delete data-template-id="{{ template.template_id }}" data-guild-id="{{ server.guild_id if server else '' }}">Delete</button>
                  </form>
                  <span class="result muted" data-template-result></span>
                </div>
              </div>
              <script type="application/json" data-embed-template-json>{{ template | tojson }}</script>
            </div>
            {% else %}
            <p class="muted" data-empty-embed-templates>No saved embed templates for this server yet.</p>
            {% endfor %}
          </div>
        </article>
        <article class="admin-panel">
          <h3>Welcome, Goodbye & Birthday</h3>
          <form id="welcome-automation-form" class="admin-form {% if edit_record_section == 'welcome_automations' and edit_record_id %}dashboard-edit-modal{% endif %}" method="post" action="/api/admin/welcome-automation" data-route="/api/admin/welcome-automation">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=automations&guild_id={{ server.guild_id if server else '' }}#welcome-automation-form">
            <input class="hidden-field" name="automation_id" value="{{ edit_welcome.automation_id }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>When should it send?
              <select name="name">
                <option value="new-survivor-welcome" {% if edit_welcome.name == 'new-survivor-welcome' %}selected{% endif %}>New survivor joins Discord</option>
                <option value="member-goodbye" {% if edit_welcome.name == 'member-goodbye' %}selected{% endif %}>Member leaves Discord</option>
                <option value="birthday" {% if edit_welcome.name == 'birthday' %}selected{% endif %}>Member birthday</option>
                <option value="first-time-seen" {% if edit_welcome.name == 'first-time-seen' %}selected{% endif %}>New gamertag appears in ADM</option>
                <option value="returning-player" {% if edit_welcome.name == 'returning-player' %}selected{% endif %}>Returning player reconnects</option>
              </select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if (edit_welcome.channel_key and (channel.value == edit_welcome.channel_key or channel.id == edit_welcome.channel_key)) or (not edit_welcome.channel_key and channel.key == 'welcome') %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Enabled <select name="enabled"><option value="true" {% if edit_welcome.enabled == 'true' %}selected{% endif %}>On</option><option value="false" {% if edit_welcome.enabled == 'false' %}selected{% endif %}>Off</option></select></label>
            <label>Assign birthday role ID <input name="birthday_role_id" value="{{ edit_welcome.birthday_role_id }}" placeholder="optional role id"></label>
            <label>Send hour <input name="send_hour" value="{{ edit_welcome.send_hour }}"></label>
            <label class="full">Message <textarea name="message">{{ edit_welcome.message }}</textarea></label>
            <div class="full modal-actions"><button type="submit">Save Welcome</button>{% if edit_record_section == 'welcome_automations' and edit_record_id %}<a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}#welcome-automation-form">Close</a>{% endif %} <span class="result muted"></span></div>
          </form>
          <div class="stack" style="margin-top:.75rem" data-dashboard-record-list data-section="welcome_automations" data-empty-message="No saved welcome, goodbye or birthday automations for this server yet.">
            {% for automation in (server.welcome_automations if server else []) %}
            {% set automation_id = automation.automation_id or automation.name %}
            <div class="notification" data-dashboard-record-card data-section="welcome_automations" data-record-id="{{ automation_id }}" data-remove-row>
              <div class="row-between">
                <div>
                  <strong>{{ automation.name or automation_id }}</strong>
                  <span>{{ 'On' if automation.enabled else 'Off' }} -> {{ channel_label(server.channels if server else [], automation.channel_key, 'no channel') }}</span>
                  <small>{% if automation.send_hour %}Send hour: {{ automation.send_hour }}{% else %}Manual timing{% endif %}</small>
                </div>
                <div class="inline-actions">
                  <a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}&edit_record_section=welcome_automations&edit_record_id={{ automation_id|urlencode }}#welcome-automation-form" data-dashboard-record-edit data-form-id="welcome-automation-form">Edit</a>
                  <form class="admin-form inline-action" method="post" action="/api/admin/dashboard-record-action" data-route="/api/admin/dashboard-record-action" data-confirm="Delete welcome automation {{ automation_id }}?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="return_to" value="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}#welcome-automation-form">
                    <input class="hidden-field" name="dashboard_mode" value="{{ mode }}">
                    <input class="hidden-field" name="section" value="welcome_automations">
                    <input class="hidden-field" name="record_id" value="{{ automation_id }}">
                    <input class="hidden-field" name="action" value="delete">
                    <button type="submit" data-dashboard-record-delete data-section="welcome_automations" data-record-id="{{ automation_id }}" data-guild-id="{{ server.guild_id if server else '' }}">Delete</button>
                  </form>
                  <span class="result muted" data-dashboard-record-result></span>
                </div>
              </div>
              <script type="application/json" data-dashboard-record-json>{{ automation | tojson }}</script>
            </div>
            {% else %}
            <p class="muted" data-empty-dashboard-records>No saved welcome, goodbye or birthday automations for this server yet.</p>
            {% endfor %}
          </div>
        </article>
        <article class="admin-panel">
          <h3>Utilities & Server Growth</h3>
          <form id="utility-config-form" class="admin-form {% if edit_record_section == 'utility_configs' and edit_record_id %}dashboard-edit-modal{% endif %}" method="post" action="/api/admin/utility-config" data-route="/api/admin/utility-config">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=automations&guild_id={{ server.guild_id if server else '' }}#utility-config-form">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Module
              <select name="module">
                <option value="server_stats" {% if edit_utility.module == 'server_stats' %}selected{% endif %}>Server statistics counters</option>
                <option value="leveling" {% if edit_utility.module == 'leveling' %}selected{% endif %}>Leveling and XP</option>
                <option value="profile_card" {% if edit_utility.module == 'profile_card' %}selected{% endif %}>Custom profile/rank card</option>
                <option value="giveaways" {% if edit_utility.module == 'giveaways' %}selected{% endif %}>Giveaways</option>
                <option value="birthdays" {% if edit_utility.module == 'birthdays' %}selected{% endif %}>Birthday notifications</option>
                <option value="custom_commands" {% if edit_utility.module == 'custom_commands' %}selected{% endif %}>Custom commands</option>
                <option value="moderation" {% if edit_utility.module == 'moderation' %}selected{% endif %}>Moderation helpers</option>
                <option value="invite_tracker" {% if edit_utility.module == 'invite_tracker' %}selected{% endif %}>Invite tracker</option>
                <option value="transcripts" {% if edit_utility.module == 'transcripts' %}selected{% endif %}>Ticket transcripts</option>
              </select>
            </label>
            <label>Enabled <select name="enabled"><option value="true" {% if edit_utility.enabled == 'true' %}selected{% endif %}>On</option><option value="false" {% if edit_utility.enabled == 'false' %}selected{% endif %}>Off</option></select></label>
            <label>Output channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if edit_utility.channel_key and (channel.value == edit_utility.channel_key or channel.id == edit_utility.channel_key) %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Limit / max count <input name="limit" type="number" value="{{ edit_utility.limit }}"></label>
            <label>XP per message <input name="xp_per_message" type="number" value="{{ edit_utility.xp_per_message }}"></label>
            <label>Cooldown seconds <input name="cooldown_seconds" type="number" value="{{ edit_utility.cooldown_seconds }}"></label>
            <label>Card accent colour <input name="card_colour" type="color" value="{{ edit_utility.card_colour }}"></label>
            <label>Background image URL <input name="background_url" value="{{ edit_utility.background_url }}" placeholder="https://..."></label>
            <label class="full">Settings note <textarea name="notes">{{ edit_utility.notes }}</textarea></label>
            <div class="full modal-actions"><button type="submit">Save Utility</button>{% if edit_record_section == 'utility_configs' and edit_record_id %}<a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}#utility-config-form">Close</a>{% endif %} <span class="result muted"></span></div>
          </form>
          <div class="stack" style="margin-top:.75rem" data-dashboard-record-list data-section="utility_configs" data-empty-message="No saved utility modules for this server yet.">
            {% for utility in (server.utility_configs if server else []) %}
            {% set utility_id = utility.module or utility.name %}
            <div class="notification" data-dashboard-record-card data-section="utility_configs" data-record-id="{{ utility_id }}" data-remove-row>
              <div class="row-between">
                <div>
                  <strong>{{ utility.module or utility_id }}</strong>
                  <span>{{ 'On' if utility.enabled else 'Off' }} -> {{ channel_label(server.channels if server else [], utility.channel_key, 'no channel') }}</span>
                  <small>Limit: {{ utility.limit or 0 }} | XP: {{ utility.xp_per_message or 0 }} | Cooldown: {{ utility.cooldown_seconds or 0 }}s</small>
                </div>
                <div class="inline-actions">
                  <a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}&edit_record_section=utility_configs&edit_record_id={{ utility_id|urlencode }}#utility-config-form" data-dashboard-record-edit data-form-id="utility-config-form">Edit</a>
                  <form class="admin-form inline-action" method="post" action="/api/admin/dashboard-record-action" data-route="/api/admin/dashboard-record-action" data-confirm="Delete utility module {{ utility_id }}?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="return_to" value="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}#utility-config-form">
                    <input class="hidden-field" name="dashboard_mode" value="{{ mode }}">
                    <input class="hidden-field" name="section" value="utility_configs">
                    <input class="hidden-field" name="record_id" value="{{ utility_id }}">
                    <input class="hidden-field" name="action" value="delete">
                    <button type="submit" data-dashboard-record-delete data-section="utility_configs" data-record-id="{{ utility_id }}" data-guild-id="{{ server.guild_id if server else '' }}">Delete</button>
                  </form>
                  <span class="result muted" data-dashboard-record-result></span>
                </div>
              </div>
              <script type="application/json" data-dashboard-record-json>{{ utility | tojson }}</script>
            </div>
            {% else %}
            <p class="muted" data-empty-dashboard-records>No saved utility modules for this server yet.</p>
            {% endfor %}
          </div>
        </article>
        <article class="admin-panel">
          <h3>Reaction Roles</h3>
          <form id="reaction-role-panel-form" class="admin-form {% if edit_record_section == 'reaction_role_panels' and edit_record_id %}dashboard-edit-modal{% endif %}" method="post" action="/api/admin/reaction-role-panel" data-route="/api/admin/reaction-role-panel">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=automations&guild_id={{ server.guild_id if server else '' }}#reaction-role-panel-form">
            <input class="hidden-field" name="panel_id" value="{{ edit_panel.panel_id }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Panel type
              <select name="name">
                <option value="server-roles" {% if edit_panel.name == 'server-roles' %}selected{% endif %}>Server roles</option>
                <option value="platform-roles" {% if edit_panel.name == 'platform-roles' %}selected{% endif %}>Platform roles</option>
                <option value="event-pings" {% if edit_panel.name == 'event-pings' %}selected{% endif %}>Event pings</option>
                <option value="faction-alerts" {% if edit_panel.name == 'faction-alerts' %}selected{% endif %}>Faction alert roles</option>
              </select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if edit_panel.channel_key and (channel.value == edit_panel.channel_key or channel.id == edit_panel.channel_key) %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label class="full">Role lines <textarea name="roles">{{ edit_panel.roles }}</textarea></label>
            <div class="full modal-actions"><button type="submit">Save Panel</button>{% if edit_record_section == 'reaction_role_panels' and edit_record_id %}<a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}#reaction-role-panel-form">Close</a>{% endif %} <span class="result muted"></span></div>
          </form>
          <div class="stack" style="margin-top:.75rem" data-dashboard-record-list data-section="reaction_role_panels" data-empty-message="No saved reaction role panels for this server yet.">
            {% for panel in (server.reaction_role_panels if server else []) %}
            {% set panel_id = panel.panel_id or panel.name %}
            <div class="notification" data-dashboard-record-card data-section="reaction_role_panels" data-record-id="{{ panel_id }}" data-remove-row>
              <div class="row-between">
                <div>
                  <strong>{{ panel.name or panel_id }}</strong>
                  <span>Channel: {{ channel_label(server.channels if server else [], panel.channel_key, 'no channel') }}</span>
                  {% set panel_role_lines = (panel.roles or '').splitlines() %}
                  <small>{{ panel_role_lines|length }} role line(s)</small>
                </div>
                <div class="inline-actions">
                  <a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}&edit_record_section=reaction_role_panels&edit_record_id={{ panel_id|urlencode }}#reaction-role-panel-form" data-dashboard-record-edit data-form-id="reaction-role-panel-form">Edit</a>
                  <form class="admin-form inline-action" method="post" action="/api/admin/dashboard-record-action" data-route="/api/admin/dashboard-record-action" data-confirm="Delete reaction role panel {{ panel_id }}?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="return_to" value="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=automations&guild_id={{ server.guild_id if server else '' }}#reaction-role-panel-form">
                    <input class="hidden-field" name="dashboard_mode" value="{{ mode }}">
                    <input class="hidden-field" name="section" value="reaction_role_panels">
                    <input class="hidden-field" name="record_id" value="{{ panel_id }}">
                    <input class="hidden-field" name="action" value="delete">
                    <button type="submit" data-dashboard-record-delete data-section="reaction_role_panels" data-record-id="{{ panel_id }}" data-guild-id="{{ server.guild_id if server else '' }}">Delete</button>
                  </form>
                  <span class="result muted" data-dashboard-record-result></span>
                </div>
              </div>
              <script type="application/json" data-dashboard-record-json>{{ panel | tojson }}</script>
            </div>
            {% else %}
            <p class="muted" data-empty-dashboard-records>No saved reaction role panels for this server yet.</p>
            {% endfor %}
          </div>
        </article>
      </div>
    </section>

    {% endif %}

    {% if mode == "admin" and auth.kind == "owner" and not servers %}
    <section class="section-panel">
      <h2>No Owner Admin Servers Selected</h2>
      <p class="tool-note">Your owner login can still see and manage every guild from the Owner section. Mark your own servers as “Show In My Admin” there before using the Admin section.</p>
      <a class="button" href="/owner">Open Owner Section</a>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "factions" %}
    {% set edit_faction_name = request.args.get('edit_faction', '') %}
    {% set edit_faction = namespace(name=(edit_faction_name or 'The Wanderers'), leader='', role='', channel='', colour='#8d963e') %}
    {% if server and server.factions and edit_faction_name %}
      {% for faction_name, faction in server.factions.items() %}
        {% set display_name = faction.name or faction_name %}
        {% if display_name == edit_faction_name or faction_name == edit_faction_name %}
          {% set edit_faction.name = display_name %}
          {% set edit_faction.leader = faction.leader_id or faction.leader or '' %}
          {% set edit_faction.role = faction.role_id or faction.discord_role_id or '' %}
          {% set edit_faction.channel = faction.alert_channel_key or faction.alert_channel_id or '' %}
          {% set edit_faction.colour = faction.colour or faction.color or '#8d963e' %}
        {% endif %}
      {% endfor %}
    {% endif %}
    <section class="section-panel" id="factions-radar">
      <div class="section-head">
        <div>
          <h2>Factions & Radar</h2>
          <p class="tool-note">Manage faction info, faction members, and the channels that should receive radar pings or faction alerts.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Faction</h3>
          <form class="admin-form {% if edit_faction_name %}dashboard-edit-modal{% endif %}" method="post" action="/api/admin/faction" data-route="/api/admin/faction" id="faction-edit-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=factions&guild_id={{ server.guild_id if server else '' }}#faction-edit-form">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Faction name <input name="name" value="{{ edit_faction.name }}"></label>
            <label>Leader
              <select name="leader_id">
                <option value="">No leader selected</option>
                {% if edit_faction.leader %}<option value="{{ edit_faction.leader }}" selected>Stored leader {{ edit_faction.leader }}</option>{% endif %}
                {% for member in (server.discord_members if server else []) %}<option value="{{ member.id }}" {% if member.id == edit_faction.leader %}selected{% endif %}>{{ member.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Faction role
              <select name="role_id">
                <option value="">No faction role selected</option>
                {% if edit_faction.role %}<option value="{{ edit_faction.role }}" selected>Stored role {{ edit_faction.role }}</option>{% endif %}
                {% for role in (server.discord_roles if server else []) %}<option value="{{ role.id }}" {% if role.id == edit_faction.role %}selected{% endif %}>{{ role.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Alert channel
              <select name="alert_channel_key">
                {% if edit_faction.channel %}<option value="{{ edit_faction.channel }}" selected>{{ channel_label(server.channels if server else [], edit_faction.channel, 'Stored channel') }}</option>{% endif %}
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if channel.value == edit_faction.channel or channel.id == edit_faction.channel or channel.key == edit_faction.channel or (not edit_faction.channel and channel.key == 'factions_chat') %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Colour <input name="colour" type="color" value="{{ edit_faction.colour }}"></label>
            <div class="full modal-actions"><button type="submit">{{ 'Update Faction' if edit_faction_name else 'Save Faction' }}</button>{% if edit_faction_name %}<a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=factions&guild_id={{ server.guild_id if server else '' }}#factions-radar">Close</a>{% endif %} <span class="result muted">{% if edit_faction_name %}Editing {{ edit_faction.name }}.{% endif %}</span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Faction Member</h3>
          <form class="admin-form" method="post" action="/api/admin/faction-member" data-route="/api/admin/faction-member">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=factions&guild_id={{ server.guild_id if server else '' }}#factions-radar">
            <input class="hidden-field" name="member_name" value="">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Faction
              <select name="name" data-faction-member-select>
                {% if server and server.factions %}
                  {% for faction_name, faction in server.factions.items() %}<option value="{{ faction.name or faction_name }}">{{ faction.name or faction_name }}</option>{% endfor %}
                {% else %}
                  <option value="The Wanderers">The Wanderers</option>
                {% endif %}
              </select>
            </label>
            <label>Member
              <select name="member_id" data-member-id-select>
                <option value="">Choose Discord member/player</option>
                {% if server and server.discord_members %}
                <optgroup label="Discord members">
                  {% for member in server.discord_members %}<option value="{{ member.id }}" data-member-name="{{ member.name }}">{{ member.label }}</option>{% endfor %}
                </optgroup>
                {% endif %}
                {% if server and server.members %}
                <optgroup label="Tracked players with Discord IDs">
                  {% for member in server.members if member.discord_id %}<option value="{{ member.discord_id }}" data-member-name="{{ member.discord_name or member.name }}">{{ member.name }}{% if member.discord_name %} / {{ member.discord_name }}{% endif %} ({{ member.discord_id }})</option>{% endfor %}
                </optgroup>
                {% endif %}
              </select>
            </label>
            <label>Action <select name="action"><option value="add">Add member</option><option value="remove">Remove member</option></select></label>
            <div class="full"><button type="submit">Update Member</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel full">
          <h3>Existing Factions</h3>
          <table class="item-table">
            <thead><tr><th>Faction</th><th>Members</th><th>Leader</th><th>Role</th><th>Alert channel</th><th>Actions</th></tr></thead>
            <tbody>
              {% for faction_name, faction in (server.factions.items() if server and server.factions else []) %}
              <tr>
                <td>{{ faction.name or faction_name }}</td>
                <td>{{ faction.members|length if faction.members else 0 }}</td>
                <td>{{ faction.leader_id or faction.leader or '-' }}</td>
                <td>{{ faction.role_id or faction.discord_role_id or '-' }}</td>
                <td>{{ faction.alert_channel_label or channel_label(server.channels if server else [], faction.alert_channel_key or faction.alert_channel_id, '-') }}</td>
                <td>
                  <form class="inline-action" method="get" action="/admin#faction-edit-form">
                    <input class="hidden-field" name="section" value="factions">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="edit_faction" value="{{ faction.name or faction_name }}">
                    <button type="submit">Edit</button>
                  </form>
                  <form class="admin-form inline-action" method="post" action="/api/admin/faction-action" data-route="/api/admin/faction-action" data-confirm="Delete faction {{ faction.name or faction_name }} from this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="return_to" value="/admin?section=factions&guild_id={{ server.guild_id if server else '' }}#factions-radar">
                    <input class="hidden-field" name="name" value="{{ faction.name or faction_name }}">
                    <input class="hidden-field" name="action" value="delete">
                    <button type="submit">Delete</button> <span class="result muted"></span>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="6">No factions found for this server yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "zones" %}
    {% set edit_zone_key = request.args.get('edit_zone', '') %}
    {% set draft_zone_active = (not edit_zone_key and request.args.get('draft_x') and request.args.get('draft_z')) %}
    {% set edit_zone = namespace(id='', name='North West Airfield', zone_type='radar', x=7500, y=7500, shape='circle', radius=250, channel_key='', role_id='', faction_name='', colour='#d5b45f', enabled='true', action='none', ban_type='temp', ban_duration_minutes=1440, trigger_territory='inside', triggers='detection,login,kill,build', ignored_gamertags='', boundary_points='[]') %}
    {% if server and edit_zone_key %}
      {% for zone in server.zones %}
        {% if zone.id == edit_zone_key or zone.name == edit_zone_key %}
          {% set edit_zone.id = zone.id %}
          {% set edit_zone.name = zone.name %}
          {% set edit_zone.zone_type = zone.zone_type %}
          {% set edit_zone.x = zone.x %}
          {% set edit_zone.y = zone.y %}
          {% set edit_zone.shape = zone.shape %}
          {% set edit_zone.radius = zone.radius %}
          {% set edit_zone.channel_key = zone.channel_key or zone.alert_channel_id or zone.report_channel_id %}
          {% set edit_zone.role_id = zone.role_id or zone.mention_role_id %}
          {% set edit_zone.faction_name = zone.faction_name %}
          {% set edit_zone.colour = zone.colour %}
          {% set edit_zone.enabled = 'true' if zone.enabled else 'false' %}
          {% set edit_zone.action = zone.action or 'none' %}
          {% set edit_zone.ban_type = zone.ban_type or 'temp' %}
          {% set edit_zone.ban_duration_minutes = zone.ban_duration_minutes or 1440 %}
          {% set edit_zone.trigger_territory = zone.trigger_territory or 'inside' %}
          {% set edit_zone.triggers = zone.triggers|join(',') if zone.triggers is iterable and zone.triggers is not string else zone.triggers or '' %}
          {% set edit_zone.ignored_gamertags = zone.ignored_gamertags|join(',') if zone.ignored_gamertags is iterable and zone.ignored_gamertags is not string else zone.ignored_gamertags or '' %}
          {% set edit_zone.boundary_points = zone.boundary_points|tojson %}
        {% endif %}
      {% endfor %}
    {% endif %}
    {% if draft_zone_active %}
      {% set edit_zone.name = request.args.get('draft_name', 'New radar zone') %}
      {% set edit_zone.zone_type = request.args.get('draft_type', 'radar') %}
      {% set edit_zone.x = request.args.get('draft_x') %}
      {% set edit_zone.y = request.args.get('draft_z') %}
      {% set edit_zone.shape = request.args.get('draft_shape', 'circle') %}
      {% set edit_zone.radius = request.args.get('draft_radius', edit_zone.radius) %}
      {% set edit_zone.colour = request.args.get('draft_colour', edit_zone.colour) %}
      {% set edit_zone.boundary_points = request.args.get('draft_points', '[]') %}
    {% endif %}
    {% set draft_map_size = server.map_size if server else 15360 %}
    {% set draft_x_percent = ((edit_zone.x|float / draft_map_size) * 100) if draft_zone_active else 0 %}
    {% set draft_y_percent = (100 - ((edit_zone.y|float / draft_map_size) * 100)) if draft_zone_active else 0 %}
    {% set draft_radius_percent = (((edit_zone.radius|float * 2) / draft_map_size) * 100) if draft_zone_active else 0 %}
    {% set draft_point_count = request.args.get('draft_point_count', 0)|int if draft_zone_active else 0 %}
    <section class="section-panel" id="zones">
      <div class="section-head">
        <div>
          <h2>Zones</h2>
          <p class="tool-note">Create and manage safe zones, PVP zones, radar ping zones, faction territory, and action rules. Existing radar zones created with Discord commands are shown here too.</p>
        </div>
        <span class="pill">{{ server.zones|length if server else 0 }} zones</span>
      </div>
      <div class="panel-grid">
        <article class="admin-panel full">
          <h3>Interactive Zone Builder</h3>
          <form class="admin-form zone-builder-form {% if edit_zone_key or draft_zone_active %}dashboard-edit-modal{% endif %}" method="post" action="/api/admin/zone" data-route="/api/admin/zone" id="zone-edit-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="zone_id" value="{{ edit_zone.id }}">
            <div class="server-lock full"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Zone name <input name="name" value="{{ edit_zone.name }}"></label>
            <label>Zone type
              <select name="zone_type">
                <option value="radar" {% if edit_zone.zone_type == 'radar' %}selected{% endif %}>Radar ping zone</option>
                <option value="safe" {% if edit_zone.zone_type == 'safe' %}selected{% endif %}>Safe zone</option>
                <option value="pvp" {% if edit_zone.zone_type == 'pvp' %}selected{% endif %}>PVP zone</option>
                <option value="action" {% if edit_zone.zone_type == 'action' %}selected{% endif %}>Ban / action zone</option>
                <option value="faction" {% if edit_zone.zone_type == 'faction' %}selected{% endif %}>Faction territory</option>
                <option value="custom" {% if edit_zone.zone_type == 'custom' %}selected{% endif %}>Custom marker</option>
              </select>
            </label>
            <label>X coordinate <input name="x" type="number" value="{{ edit_zone.x }}"></label>
            <label>Z coordinate <input name="y" type="number" value="{{ edit_zone.z or edit_zone.y }}"></label>
            <label>Shape
              <select name="shape" data-zone-shape><option value="circle" {% if edit_zone.shape == 'circle' %}selected{% endif %}>Circle</option><option value="boundary" {% if edit_zone.shape == 'boundary' %}selected{% endif %}>Draw boundary</option></select>
            </label>
            <label>Radius meters <input name="radius" type="number" min="10" max="{{ server.map_size if server else 15360 }}" step="10" value="{{ edit_zone.radius }}" data-zone-radius></label>
            <label class="full">Radius slider <input name="radius_slider" type="range" min="10" max="3000" step="10" value="{{ edit_zone.radius }}" data-zone-radius-slider></label>
            <label>Ping / report channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if (edit_zone.channel_key and (channel.value == edit_zone.channel_key or channel.id == edit_zone.channel_key)) or (not edit_zone.id and not edit_zone.channel_key and (channel.key == 'radar' or channel.key == 'pvp_intel')) %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Ping role ID <input name="role_id" value="{{ edit_zone.role_id }}" placeholder="optional Discord role id"></label>
            <label>Faction colour source
              <select name="faction_name">
                <option value="">No faction colour</option>
                {% for faction_name, faction in (server.factions.items() if server and server.factions else []) %}<option value="{{ faction.name or faction_name }}" data-faction-colour="{{ faction.colour or faction.color or '#8d963e' }}" {% if edit_zone.faction_name == (faction.name or faction_name) %}selected{% endif %}>{{ faction.name or faction_name }}</option>{% endfor %}
              </select>
            </label>
            <label>Zone colour <input name="colour" type="color" value="{{ edit_zone.colour }}" data-zone-colour></label>
            <label>Enabled <select name="enabled"><option value="true" {% if edit_zone.enabled == 'true' %}selected{% endif %}>On</option><option value="false" {% if edit_zone.enabled == 'false' %}selected{% endif %}>Off</option></select></label>
            <label>Action on violation
              <select name="action"><option value="none" {% if edit_zone.action == 'none' %}selected{% endif %}>Notify only</option><option value="manhunt" {% if edit_zone.action == 'manhunt' %}selected{% endif %}>Start manhunt</option><option value="ban" {% if edit_zone.action == 'ban' %}selected{% endif %}>Ban through Nitrado</option></select>
            </label>
            <label>Ban type <select name="ban_type"><option value="temp" {% if edit_zone.ban_type == 'temp' %}selected{% endif %}>Temp ban</option><option value="perm" {% if edit_zone.ban_type == 'perm' %}selected{% endif %}>Perm ban</option></select></label>
            <label>Temp ban minutes <input name="ban_duration_minutes" type="number" value="{{ edit_zone.ban_duration_minutes }}"></label>
            <label>Trigger territory <select name="trigger_territory"><option value="inside" {% if edit_zone.trigger_territory == 'inside' %}selected{% endif %}>Inside zone</option><option value="outside" {% if edit_zone.trigger_territory == 'outside' %}selected{% endif %}>Outside zone</option></select></label>
            <label class="full">Triggers <input name="triggers" value="{{ edit_zone.triggers }}" placeholder="detection, login, kill, build, flag_raise"></label>
            <label class="full">Ignored gamertags <input name="ignored_gamertags" value="{{ edit_zone.ignored_gamertags }}" placeholder="comma-separated names that should not ping radar"></label>
            <input class="hidden-field" name="boundary_points" data-boundary-points value="{{ edit_zone.boundary_points|forceescape }}">
            <div class="full embed-preview">
              <strong>Map controls</strong>
              <span>Circle mode sets the center and radius. For a polygon/freehand zone, choose Draw boundary, then click multiple points around the area and save when the outline covers it.</span>
            </div>
            <div class="full zone-tools">
              <div class="mini-card"><strong data-zone-radius-label>{{ edit_zone.radius }}m</strong><span class="muted">Circle radius</span></div>
              <div class="mini-card"><strong data-zone-shape-label>{{ 'Boundary' if edit_zone.shape == 'boundary' else 'Circle' }}</strong><span class="muted">Drawing mode</span></div>
              <div class="mini-card"><strong data-boundary-count>{{ draft_point_count if edit_zone.shape == 'boundary' else 0 }}</strong><span class="muted">Boundary points</span></div>
              <div class="zone-tool-actions">
                <button type="submit" formaction="/{{ 'owner' if mode == 'owner' else 'admin' }}/zone-draft" formmethod="get" name="boundary_action" value="clear" data-zone-map-hit data-clear-boundary>Clear Boundary</button>
                <button type="submit" formaction="/{{ 'owner' if mode == 'owner' else 'admin' }}/zone-draft" formmethod="get" name="boundary_action" value="undo" data-zone-map-hit data-undo-boundary>Undo Point</button>
              </div>
            </div>
            <div class="full zone-map-viewport">
            <div class="zone-map" data-zone-map data-map-size="{{ server.map_size if server else 15360 }}" style="--zone-map-display-size: 512px;{% if server %} --map-image: url('/map-image/{{ server.map_key }}');{% endif %}">
              {% if server and not server.map_image_available %}
              <div class="map-missing">Real {{ server.map|upper }} map image is not installed yet. Add <code>{{ server.map_key }}_map.jpg</code> beside the bot, or set the Railway map image variable, and this builder will use it automatically.</div>
              {% endif %}
              <input type="image" class="zone-map-hit-layer" name="zone_click" src="/map-image/{{ server.map_key if server else 'chernarus' }}" alt="Draft a new zone here" formaction="/{{ 'owner' if mode == 'owner' else 'admin' }}/zone-draft" formmethod="get" onpointerdown="return window.wanderingMeasureZoneMapClick ? window.wanderingMeasureZoneMapClick(event, this) : true" onclick="return window.wanderingMeasureZoneMapClick ? window.wanderingMeasureZoneMapClick(event, this) : true" data-zone-map-hit>
              <input class="hidden-field" name="map_click_scale" value="{{ ((server.map_size if server else 15360) / 512)|round(6) }}">
              <input class="hidden-field" name="map_render_width" data-map-render-width value="512">
              <input class="hidden-field" name="map_render_height" data-map-render-height value="512">
              <input class="hidden-field" name="map_pointer_x" data-map-pointer-x value="">
              <input class="hidden-field" name="map_pointer_y" data-map-pointer-y value="">
              <input class="hidden-field" name="map_percent_x" data-map-percent-x value="">
              <input class="hidden-field" name="map_percent_y" data-map-percent-y value="">
              <input class="hidden-field" name="map_click_override" value="">
              <input class="hidden-field" name="draft_radius" value="{{ edit_zone.radius }}">
              <span class="zone-map-hit-label">Click empty map to add zone</span>
              <svg class="zone-boundary-layer" data-boundary-layer viewBox="0 0 100 100" preserveAspectRatio="none"></svg>
              {% if draft_zone_active and edit_zone.shape == "circle" %}
              <span class="zone-radius-ring {{ edit_zone.zone_type }}" aria-hidden="true" style="--zone-colour: {{ edit_zone.colour }}; --zone-radius: {{ draft_radius_percent }}%; left: {{ draft_x_percent }}%; top: {{ draft_y_percent }}%;"></span>
              <span class="zone-cursor" aria-hidden="true" style="--zone-colour: {{ edit_zone.colour }}; left: {{ draft_x_percent }}%; top: {{ draft_y_percent }}%;"></span>
              {% endif %}
              {% if draft_zone_active and edit_zone.shape == "boundary" and request.args.get('draft_points_percent') %}
              <svg class="zone-boundary-layer" viewBox="0 0 100 100" preserveAspectRatio="none" style="--zone-colour: {{ edit_zone.colour }};">{% if draft_point_count >= 3 %}<polygon points="{{ request.args.get('draft_points_percent') }}"></polygon>{% else %}<polyline points="{{ request.args.get('draft_points_percent') }}"></polyline>{% endif %}</svg>
              {% for point in request.args.get('draft_points_percent').split(' ') if point %}
              {% set parts = point.split(',') %}
              <span class="zone-boundary-point" aria-hidden="true" style="--zone-colour: {{ edit_zone.colour }}; left: {{ parts[0] }}%; top: {{ parts[1] }}%;"></span>
              {% endfor %}
              {% endif %}
              {% for zone in (server.zones if server else []) %}
              {% if zone.shape == "boundary" and zone.points_percent %}
              <svg class="zone-boundary-layer" viewBox="0 0 100 100" preserveAspectRatio="none" style="--zone-colour: {{ zone.display_colour or zone.colour }};"><polygon points="{{ zone.points_percent }}"></polygon></svg>
              {% endif %}
              {% if zone.shape != "boundary" %}
              <span class="zone-radius-ring {{ zone.zone_type }}" aria-hidden="true" style="--zone-colour: {{ zone.display_colour or zone.colour }}; --zone-radius: {{ zone.radius_percent }}%; left: {{ zone.x_percent }}%; top: {{ zone.y_percent }}%;"></span>
              {% endif %}
              <a class="zone-dot {{ zone.zone_type }}" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=zones&guild_id={{ server.guild_id if server else '' }}&edit_zone={{ (zone.id or zone.name)|urlencode }}#zone-edit-form" title="Edit {{ zone.name }}" aria-label="Edit {{ zone.name }}" data-zone-edit data-zone-key="{{ (zone.id or zone.name)|e }}" data-zone='{{ zone|tojson|forceescape }}' data-zone-colour="{{ zone.display_colour or zone.colour }}" style="--zone-colour: {{ zone.display_colour or zone.colour }}; left: {{ zone.x_percent }}%; top: {{ zone.y_percent }}%; width: {{ zone.dot_size }}px; height: {{ zone.dot_size }}px;"><span>{{ loop.index }}</span><small>{{ zone.name }}</small></a>
              {% endfor %}
              <div class="zone-map-popover" data-zone-popover hidden></div>
            </div>
            </div>
            <div class="full map-readout" data-map-readout>{% if draft_zone_active and edit_zone.shape == 'boundary' %}Boundary draft has {{ draft_point_count }} point{{ '' if draft_point_count == 1 else 's' }}. Click the map again to add another point, then save when it has at least 3 points.{% elif draft_zone_active %}Circle draft at X {{ edit_zone.x }}, Z {{ edit_zone.y }} with {{ edit_zone.radius }}m radius. Adjust the radius/name if needed, then save.{% else %}Click empty map space to draft a new zone. Click a marker or Edit to load an existing zone.{% endif %}</div>
            <div class="full zone-form-actions">
              <button type="submit" data-zone-save-button>{{ 'Save Zone Changes' if edit_zone.id else 'Save Zone' }}</button>
              <button type="button" data-zone-delete-current {% if not edit_zone.id %}disabled{% endif %}>Delete Selected Zone</button>
              {% if edit_zone_key or draft_zone_active %}<a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=zones&guild_id={{ server.guild_id if server else '' }}#zones-list">Close</a>{% endif %}
              <span class="result muted">{% if draft_zone_active %}Draft from map click. Adjust anything here, then save the new zone.{% endif %}</span>
            </div>
          </form>
        </article>
        <article class="admin-panel full" id="zones-list">
          <h3>Existing Zones</h3>
          <table class="item-table">
            <thead><tr><th>#</th><th>Name</th><th>Type</th><th>Center</th><th>Radius</th><th>Action</th><th>Channel</th><th>Actions</th></tr></thead>
            <tbody>
              {% for zone in (server.zones if server else []) %}
              <tr data-zone-row data-zone-key="{{ (zone.id or zone.name)|e }}">
                <td>{{ loop.index }}</td>
                <td><span class="zone-swatch" style="--zone-colour: {{ zone.display_colour or zone.colour }};"></span>{{ zone.name }}</td>
                <td>{{ zone.zone_type }}</td>
                <td>{{ zone.x }}, {{ zone.z or zone.y }}</td>
                <td>{{ zone.radius }}m</td>
                <td>{{ zone.action or 'notify' }}</td>
                <td>{{ zone.channel_label or channel_label(server.channels if server else [], zone.channel_key or zone.alert_channel_id or zone.report_channel_id, 'default') }}</td>
                <td>
                  <div class="inline-action">
                    <a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=zones&guild_id={{ server.guild_id if server else '' }}&edit_zone={{ (zone.id or zone.name)|urlencode }}#zone-edit-form" data-zone-edit data-zone-key="{{ (zone.id or zone.name)|e }}" data-zone-colour="{{ zone.display_colour or zone.colour }}">Edit</a>
                  </div>
                  <form class="admin-form inline-action" method="post" action="/api/admin/zone-action" data-route="/api/admin/zone-action" data-confirm="Delete zone {{ zone.name }} from this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="return_to" value="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=zones&guild_id={{ server.guild_id if server else '' }}#zones-list">
                    <input class="hidden-field" name="dashboard_mode" value="{{ mode }}">
                    <input class="hidden-field" name="zone_id" value="{{ zone.id }}">
                    <input class="hidden-field" name="zone_type" value="{{ zone.zone_type }}">
                    <input class="hidden-field" name="name" value="{{ zone.name }}">
                    <input class="hidden-field" name="action" value="delete">
                    <button type="submit" data-zone-delete data-zone-key="{{ (zone.id or zone.name)|e }}" data-zone-id="{{ zone.id }}" data-zone-type="{{ zone.zone_type }}" data-zone-name="{{ zone.name }}" data-guild-id="{{ server.guild_id if server else '' }}">Delete</button>
                    <span class="result muted"></span>
                  </form>
                  <script type="application/json" data-zone-json data-zone-key="{{ (zone.id or zone.name)|e }}">{{ zone | tojson }}</script>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="8">No zones saved yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "members" %}
    <section class="section-panel" id="members">
      <div class="section-head">
        <div>
          <h2>Members</h2>
          <p class="tool-note">Player and member controls are scoped to this server only. Discord kick/ban needs a linked Discord ID; DayZ bans are queued for the bot/Nitrado workflow.</p>
        </div>
        <div class="pill-row">
          <span class="pill">{{ server.discord_member_count if server else 0 }} Discord members</span>
          <span class="pill">{{ server.members|length if server else 0 }} tracked players</span>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel full">
          <h3>Server Members</h3>
          <table class="item-table">
            <thead><tr><th>Player</th><th>Discord</th><th>Faction</th><th>Online</th><th>Kills</th><th>Deaths</th><th>Actions</th></tr></thead>
            <tbody>
              {% for member in (server.members if server else []) %}
              <tr>
                <td>{{ member.name }}</td>
                <td>{% if member.discord_name %}<strong>{{ member.discord_name }}</strong><br><small class="muted">{{ member.discord_id }}</small>{% else %}{{ member.discord_id or '-' }}{% endif %}</td>
                <td>{{ member.faction or '-' }}</td>
                <td>{{ 'Online' if member.online else 'Offline' }}</td>
                <td>{{ member.kills }}</td>
                <td>{{ member.deaths }}</td>
                <td>
                  <form class="admin-form inline-action" method="post" action="/api/admin/member-action" data-route="/api/admin/member-action" data-confirm="Kick {{ member.name }} from Discord for this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="member_id" value="{{ member.discord_id }}">
                    <input class="hidden-field" name="player_name" value="{{ member.name }}">
                    <input class="hidden-field" name="action" value="discord_kick">
                    <button type="submit" {% if not member.discord_id %}disabled{% endif %}>Kick</button> <span class="result muted"></span>
                  </form>
                  <form class="admin-form inline-action" method="post" action="/api/admin/member-action" data-route="/api/admin/member-action" data-confirm="Ban {{ member.name }} from Discord for this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="member_id" value="{{ member.discord_id }}">
                    <input class="hidden-field" name="player_name" value="{{ member.name }}">
                    <input class="hidden-field" name="action" value="discord_ban">
                    <button type="submit" {% if not member.discord_id %}disabled{% endif %}>Discord Ban</button> <span class="result muted"></span>
                  </form>
                  <form class="admin-form inline-action" method="post" action="/api/admin/member-action" data-route="/api/admin/member-action" data-confirm="Queue a DayZ/Nitrado ban for {{ member.name }} on this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="member_id" value="{{ member.discord_id }}">
                    <input class="hidden-field" name="player_name" value="{{ member.name }}">
                    <input class="hidden-field" name="action" value="dayz_perm_ban">
                    <button type="submit">DayZ Ban</button> <span class="result muted"></span>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="7">No tracked members or player stats found for this server yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "heatmaps" %}
    <section class="section-panel" id="heatmaps">
      <div class="section-head">
        <div>
          <h2>Heatmaps</h2>
          <p class="tool-note">See the busiest PVP, PVE, infected, animal, build, and movement zones the bot has collected from ADM activity.</p>
        </div>
        <span class="pill">{{ server.heatmap.total if server else 0 }} events</span>
      </div>
      <div class="panel-grid">
        {% for mode_name, heat in (server.heatmap.modes.items() if server else []) %}
        <article class="admin-panel">
          <h3>{{ mode_name|upper }} Heat</h3>
          <div class="heat-list">
            {% for zone in heat %}
            <div>
              <div class="heat-row"><span>{{ zone.name }}</span><strong>{{ zone.count }}</strong></div>
              <div class="bar"><span style="width: {{ zone.percent }}%"></span></div>
            </div>
            {% else %}
            <p class="muted">No heat recorded for this mode yet.</p>
            {% endfor %}
          </div>
        </article>
        {% else %}
        <article class="admin-panel"><h3>No Heatmap Data</h3><p class="muted">The bot will fill this once ADM events are processed.</p></article>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "pve" %}
    {% set edit_event_key = request.args.get('edit_event', '') %}
    {% set edit_event = namespace(id='', name='Supply drop', event_type='airdrop', class_name='WoodenCrate', x=7500, y=0, z=7500, count=1, radius=35, permanent='false', restarts=1, loot_preset='none', visual_marker='true', scene_type='compact_crater', guard_class='ZmbM_SoldierNormal', guard_count=8, guard_radius=35, gas_lifetime=1800, gas_particle='server_default') %}
    {% if server and edit_event_key %}
      {% for event in server.scenario_events %}
        {% if event.id|string == edit_event_key or event.name == edit_event_key %}
          {% set edit_event.id = event.id %}
          {% set edit_event.name = event.name %}
          {% set edit_event.event_type = event.event_type %}
          {% set edit_event.class_name = event.class_name %}
          {% set edit_event.x = event.x %}
          {% set edit_event.y = event.y %}
          {% set edit_event.z = event.z %}
          {% set edit_event.count = event.count %}
          {% set edit_event.radius = event.radius %}
          {% set edit_event.permanent = 'true' if event.permanent else 'false' %}
          {% set edit_event.restarts = event.remaining_restarts %}
          {% set edit_event.loot_preset = event.loot_preset or 'none' %}
          {% set edit_event.visual_marker = 'true' if event.visual_marker else 'false' %}
          {% set edit_event.scene_type = event.scene_type or 'compact_crater' %}
          {% set edit_event.guard_class = event.guard_class or '' %}
          {% set edit_event.guard_count = event.guard_count or 0 %}
          {% set edit_event.guard_radius = event.guard_radius or 35 %}
          {% set edit_event.gas_lifetime = event.gas_lifetime or 1800 %}
          {% set edit_event.gas_particle = event.gas_particle or 'server_default' %}
        {% endif %}
      {% endfor %}
    {% endif %}
    <section class="section-panel" id="pve-workshop">
      <div class="section-head">
        <div>
          <h2>PVE Live Ops</h2>
          <p class="tool-note">Events, drops, hordes, gas zones, vehicles and quest status for the selected server.</p>
          <nav class="command-subnav" aria-label="PVE tools">
            <a class="{{ 'active' if pve_tool == 'events' else '' }}" href="/admin?section=pve&pve_tool=events{{ server_qs }}#pve-workshop">Live Events</a>
            <a class="{{ 'active' if pve_tool == 'builder' else '' }}" href="/admin?section=pve&pve_tool=builder{{ server_qs }}#pve-workshop">Event Builder</a>
            <a class="{{ 'active' if pve_tool == 'quests' else '' }}" href="/admin?section=pve&pve_tool=quests{{ server_qs }}#pve-workshop">Quest Board</a>
          </nav>
          <p class="tool-note">Use the tabs to manage live events, build new deployments, or review quest status.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel" data-pve-panel="quests">
          <h3>Active Quest Board</h3>
          <table class="item-table">
            <thead><tr><th>Quest</th><th>Difficulty</th><th>Reward</th></tr></thead>
            <tbody>
              {% for quest in (server.pve.active[:10] if server else []) %}
              <tr><td>{{ quest.title }}</td><td>{{ quest.difficulty }}</td><td>{{ quest.reward_pennies }}</td></tr>
              {% else %}
              <tr><td colspan="3">No active PVE quests found yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
        <article class="admin-panel" data-pve-panel="quests">
          <h3>Quest Workshop</h3>
          <div class="mini-grid">
            <div class="mini-card"><span class="muted">Campaigns</span><strong>{{ server.pve.campaigns if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Schedules</span><strong>{{ server.pve.schedules if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Rewards</span><strong>{{ server.pve.reward_types|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Quest channels</span><strong>{{ server.pve.quest_channels if server else 0 }}</strong></div>
          </div>
          <p class="tool-note" style="margin-top:.75rem">AI quests live in Discord. This panel shows status and module controls.</p>
        </article>
        <article class="admin-panel full" data-pve-panel="builder">
          <h3>Airdrop / Event Builder</h3>
          <form class="admin-form {% if edit_event_key %}dashboard-edit-modal{% endif %}" action="/api/admin/scenario-event" method="post" data-route="/api/admin/scenario-event" id="scenario-event-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="event_id" value="{{ edit_event.id }}">
            <input class="hidden-field" name="return_to" value="/admin?section=pve&pve_tool=events{{ server_qs }}#pve-workshop">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Event type
              <select name="event_type" data-scenario-type>
                <option value="airdrop" data-default-preset="military_crate" {% if edit_event.event_type in ['airdrop', 'loot_crate'] %}selected{% endif %}>Airdrop loot</option>
                <option value="animal_pack" data-default-preset="bear" {% if edit_event.event_type == 'animal_pack' %}selected{% endif %}>Airdrop animals</option>
                <option value="zombie_horde" data-default-preset="civilian_zombie" {% if edit_event.event_type == 'zombie_horde' %}selected{% endif %}>Airdrop horde</option>
                <option value="vehicle_spawn" data-default-preset="m3s" {% if edit_event.event_type == 'vehicle_spawn' %}selected{% endif %}>Vehicle spawn</option>
                <option value="gas_zone" data-default-preset="gas_temp" {% if edit_event.event_type == 'gas_zone' %}selected{% endif %}>Gas zone</option>
              </select>
            </label>
            <label>Spawn type
              <select name="spawn_preset" data-scenario-preset>
                <option value="military_crate" data-type="airdrop" data-class="WoodenCrate" data-count="1" data-radius="35" data-loot="military_high">Military loot</option>
                <option value="wooden_crate" data-type="airdrop" data-class="WoodenCrate" data-count="1" data-radius="20" data-loot="survival">Survival loot</option>
                <option value="medical_crate" data-type="airdrop" data-class="WoodenCrate" data-count="1" data-radius="20" data-loot="medical">Medical loot</option>
                <option value="building_crate" data-type="airdrop" data-class="WoodenCrate" data-count="1" data-radius="20" data-loot="building">Building loot</option>
                <option value="food_crate" data-type="airdrop" data-class="WoodenCrate" data-count="1" data-radius="20" data-loot="food">Food loot</option>
                <option value="bear" data-type="animal_pack" data-class="Animal_UrsusArctos" data-count="3" data-radius="90">Bears</option>
                <option value="wolf" data-type="animal_pack" data-class="Animal_CanisLupus_Grey" data-count="6" data-radius="120">Wolves</option>
                <option value="deer" data-type="animal_pack" data-class="Animal_CervusElaphus" data-count="5" data-radius="120">Deer</option>
                <option value="boar" data-type="animal_pack" data-class="Animal_SusScrofa" data-count="4" data-radius="80">Boar</option>
                <option value="civilian_zombie" data-type="zombie_horde" data-class="ZmbM_CitizenASkinny_Brown" data-count="10" data-radius="55">Civilian infected</option>
                <option value="military_zombie" data-type="zombie_horde" data-class="ZmbM_SoldierNormal" data-count="12" data-radius="60">Military infected</option>
                <option value="heavy_military_zombie" data-type="zombie_horde" data-class="ZmbM_usSoldier_Heavy_Woodland" data-count="8" data-radius="55">Heavy military infected</option>
                <option value="ada" data-type="vehicle_spawn" data-class="OffroadHatchback" data-count="1" data-radius="5" data-loot="vehicle_car">Ada 4x4</option>
                <option value="gunter" data-type="vehicle_spawn" data-class="Hatchback_02" data-count="1" data-radius="5" data-loot="vehicle_car">Gunter 2</option>
                <option value="sarka" data-type="vehicle_spawn" data-class="CivilianSedan" data-count="1" data-radius="5" data-loot="vehicle_car">Sarka 120</option>
                <option value="olga" data-type="vehicle_spawn" data-class="Sedan_02" data-count="1" data-radius="5" data-loot="vehicle_car">Olga 24</option>
                <option value="m3s" data-type="vehicle_spawn" data-class="Truck_01_Covered" data-count="1" data-radius="5" data-loot="vehicle_truck">M3S covered truck</option>
                <option value="custom_vehicle" data-type="vehicle_spawn" data-count="1" data-radius="5" data-loot="vehicle_car">Custom vehicle classname</option>
                <option value="gas_temp" data-type="gas_zone" data-class="ContaminatedArea_Dynamic" data-count="1" data-radius="120" data-gas-lifetime="1800" data-permanent="false">Temporary gas zone</option>
                <option value="gas_permanent" data-type="gas_zone" data-class="ContaminatedArea_Dynamic" data-count="1" data-radius="150" data-gas-lifetime="3888000" data-permanent="true">Permanent gas zone</option>
                <option value="gas_red_temp" data-type="gas_zone" data-class="ContaminatedArea_Dynamic" data-count="1" data-radius="120" data-gas-lifetime="1800" data-gas-particle="debug" data-permanent="false">Temporary red gas zone</option>
                <option value="gas_red_permanent" data-type="gas_zone" data-class="ContaminatedArea_Dynamic" data-count="1" data-radius="150" data-gas-lifetime="3888000" data-gas-particle="debug" data-permanent="true">Permanent red gas zone</option>
                <option value="custom">Custom classname</option>
              </select>
            </label>
            <label>Event name <input name="name" value="{{ edit_event.name }}" placeholder="Optional display name"><small class="field-help">🏷️ Name shown in Live Events.</small></label>
            <label>Saved location
              <select name="saved_location" data-scenario-location-preset>
                <option value="">Manual X/Z</option>
                {% for location in airdrop_location_presets %}
                <option value="{{ location.name }}" data-x="{{ location.x }}" data-z="{{ location.z }}">{{ location.name }} ({{ location.x }}, {{ location.z }})</option>
                {% endfor %}
              </select>
              <small class="field-help">📍 Pick a saved spot or type X/Z.</small>
            </label>
            <label>Resolved spawn class <input name="class_name" value="{{ edit_event.class_name }}" data-scenario-class readonly placeholder="Pick Custom classname to type manually"><small class="field-help">🧩 DayZ classname for CE XML.</small></label>
            <label>X coordinate <input name="x" type="number" value="{{ edit_event.x }}"><small class="field-help">↔️ iZurvive/dashboard X.</small></label>
            <label>Z coordinate <input name="z" type="number" value="{{ edit_event.z }}"><small class="field-help">↕️ iZurvive/dashboard Z.</small></label>
            <label>Y height <input name="y" type="number" value="{{ edit_event.y }}" placeholder="ignored by console CE XML"><small class="field-help">⬆️ Usually 0 on console.</small></label>
            <label>Quantity in event <input name="count" type="number" min="1" max="250" value="{{ edit_event.count }}"><small class="field-help">🔢 Animals/infected count. Drops use batch for multiples.</small></label>
            <label>Spread radius <input name="radius" type="number" value="{{ edit_event.radius }}"><small class="field-help">⭕ Spread around the point.</small></label>
            <label class="full">Batch locations
              <textarea name="batch_locations" data-scenario-batch-locations placeholder="Skalisty Island, 13532, 3131&#10;NWAF, 4481, 10355&#10;Tisy, 1612, 14175"></textarea>
              <small class="field-help">🗺️ One per line: name, X, Z.</small>
            </label>
            <div class="full" data-zombie-mix-builder>
              <h4>Zombie Horde Mix</h4>
              <input type="hidden" name="zombie_mix" data-zombie-mix-value>
              <div data-zombie-mix-rows></div>
              <button type="button" data-add-zombie-row>Add Zombie Type</button>
            </div>
            <label>Event length
              <select name="permanent">
                <option value="false" {% if edit_event.permanent == 'false' %}selected{% endif %}>One restart only</option>
                <option value="true" {% if edit_event.permanent == 'true' %}selected{% endif %}>Permanent until deleted</option>
              </select>
            </label>
            <label>Runs for restarts <input name="restarts" type="number" value="{{ edit_event.restarts }}" placeholder="Used only for one-time events"></label>
            <label>Gas duration seconds <input name="gas_lifetime" type="number" min="60" max="3888000" value="{{ edit_event.gas_lifetime }}"><small class="field-help">Used by gas zones as the CE lifetime. Permanent keeps the zone in XML until deleted.</small></label>
            <label>Gas particle
              <select name="gas_particle">
                <option value="server_default" {% if edit_event.gas_particle in ['', 'server_default'] %}selected{% endif %}>Leave server default</option>
                <option value="debug" {% if edit_event.gas_particle in ['debug', 'red'] %}selected{% endif %}>Red / debug gas</option>
                <option value="normal" {% if edit_event.gas_particle in ['normal', 'green', 'restore'] %}selected{% endif %}>Restore normal green</option>
              </select>
              <small class="field-help">Red/debug updates cfgareaeffects.xml ParticleName to the _debug particle. It can affect all contaminated gas using that particle.</small>
            </label>
            <div class="full embed-preview"><strong>Gas colour</strong><span>Red gas writes cfgareaeffects.xml using graphics/particles/contaminated_area_gas_bigass_debug. Use Restore normal green to switch it back.</span></div>
            <label>Loot preset
              <select name="loot_preset"><option value="none" {% if edit_event.loot_preset == 'none' %}selected{% endif %}>None</option><option value="military_high" {% if edit_event.loot_preset == 'military_high' %}selected{% endif %}>Military high tier</option><option value="military_basic" {% if edit_event.loot_preset == 'military_basic' %}selected{% endif %}>Military basic</option><option value="medical" {% if edit_event.loot_preset == 'medical' %}selected{% endif %}>Medical</option><option value="survival" {% if edit_event.loot_preset == 'survival' %}selected{% endif %}>Survival</option><option value="building" {% if edit_event.loot_preset == 'building' %}selected{% endif %}>Building</option><option value="food" {% if edit_event.loot_preset == 'food' %}selected{% endif %}>Food</option><option value="vehicle_car" {% if edit_event.loot_preset == 'vehicle_car' %}selected{% endif %}>Vehicle kit</option><option value="vehicle_truck" {% if edit_event.loot_preset == 'vehicle_truck' %}selected{% endif %}>Truck build kit</option></select>
              <small class="field-help">✨ Pristine loot. Ammo/medical in crates, big gear around scene.</small>
            </label>
            <label>Vehicle condition
              <select name="vehicle_condition"><option value="full">Full fuel, fluids, and common parts</option><option value="random_parts">Random common parts</option><option value="no_parts">Body only / missing parts</option></select>
            </label>
            <label>Vehicle cargo
              <select name="vehicle_cargo_mode"><option value="normal_with_loot">Full vehicle with selected loot</option><option value="normal_no_loot">Full vehicle with no bot-added loot</option><option value="native_only">Use my server files only</option></select>
            </label>
            <label class="full">Extra loot items <input name="loot_items" placeholder="Optional extras only, comma-separated"><small class="field-help">➕ Exact classnames, comma separated.</small></label>
            <label>Visual marker <select name="visual_marker"><option value="false" {% if edit_event.visual_marker == 'false' %}selected{% endif %}>Off</option><option value="true" {% if edit_event.visual_marker == 'true' %}selected{% endif %}>On</option></select></label>
            <label>Airdrop scene
              <select name="scene_type">
                <option value="compact_crater" {% if edit_event.scene_type == 'compact_crater' %}selected{% endif %}>Compact crater</option>
                <option value="helicopter_crash" {% if edit_event.scene_type == 'helicopter_crash' %}selected{% endif %}>Helicopter crash</option>
                <option value="cargo_plane_wreck" {% if edit_event.scene_type == 'cargo_plane_wreck' %}selected{% endif %}>Cargo plane wreck</option>
                <option value="convoy_wreck" {% if edit_event.scene_type == 'convoy_wreck' %}selected{% endif %}>Convoy wreck</option>
              </select>
              <small class="field-help">🚁 Marker scenes. Heli min 100m, plane min 120m.</small>
            </label>
            <label>Guard class <input name="guard_class" value="{{ edit_event.guard_class }}" placeholder="optional infected guard classname"></label>
            <label>Guard count <input name="guard_count" type="number" value="{{ edit_event.guard_count }}"></label>
            <label>Guard radius <input name="guard_radius" type="number" value="{{ edit_event.guard_radius }}"></label>
            <div class="full embed-preview"><strong>Status</strong><span>Save queues native CE XML upload. Max 250 spawns per event.</span></div>
            <div class="full modal-actions"><button type="submit">Save / Queue Event</button>{% if edit_event_key %}<a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=pve&pve_tool=events{{ server_qs }}#pve-workshop">Close</a>{% endif %} <span class="result muted"></span></div>
          </form>
          <p class="tool-note" style="margin-top:.75rem">Events save to bot config. Console CE XML applies after restart.</p>
        </article>
        <article class="admin-panel" data-pve-panel="builder">
          <h3>Server Control Moved</h3>
          <p class="tool-note">Restarts, raid damage and vehicle resets moved to Server Control.</p>
          <a class="button-link" href="/admin?section=server-control{{ server_qs }}">Open Server Control</a>
        </article>
        <article class="admin-panel full" data-pve-panel="events">
          <h3>Live Event Manager</h3>
          <div class="mini-grid">
            <div class="mini-card"><span class="muted">Total</span><strong>{{ server.scenario_events|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Active</span><strong>{{ server.scenario_events|selectattr('enabled')|list|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Permanent</span><strong>{{ server.scenario_events|selectattr('permanent')|list|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Uploads</span><strong>{{ server.scenario_events|selectattr('upload_status', 'equalto', 'uploaded')|list|length if server else 0 }}</strong></div>
          </div>
          <div class="shop-toolbar" style="margin-top:.85rem">
            <label>Search events <input data-event-search placeholder="name/type/class/status"></label>
            <label>Status
              <select data-event-status>
                <option value="">All events</option>
                <option value="active">Active only</option>
                <option value="paused">Paused only</option>
                <option value="permanent">Permanent</option>
                <option value="failed">Upload failed</option>
              </select>
            </label>
            <span class="pill">Guild scoped</span>
          </div>
          <table class="item-table">
            <thead><tr><th>ID</th><th>Type</th><th>Name</th><th>Class</th><th>Position</th><th>Runs</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>
              {% for event in (server.scenario_events if server else []) %}
              <tr data-scenario-event-row="{{ event.id }}" data-event-row data-event-enabled="{{ 'true' if event.enabled else 'false' }}" data-event-permanent="{{ 'true' if event.permanent else 'false' }}" data-event-upload="{{ event.upload_status or '' }}" data-event-search="{{ event.id }} {{ event.event_type|lower }} {{ event.name|lower }} {{ event.class_name|lower }} {{ event.status|lower }}">
                <td>{{ event.id }}</td><td>{{ event.event_type }}</td><td>{{ event.name }}</td><td>{% if event.zombie_mix %}{% for item in event.zombie_mix[:3] %}{{ item.count }}x {{ item.class }}{% if not loop.last %}<br>{% endif %}{% endfor %}{% if event.zombie_mix|length > 3 %}<br><small class="muted">+ {{ event.zombie_mix|length - 3 }} more</small>{% endif %}{% else %}{{ event.class_name }}{% endif %}</td><td>{{ event.x }}, {{ event.z }}</td><td>{{ '∞' if event.permanent else event.remaining_restarts }}</td><td data-scenario-status>{{ event.status or 'Queued ✅' }}{% if event.upload_error %}<br><small class="muted">⚠️ {{ event.upload_error }}</small>{% endif %}</td>
                <td>
                  <div class="scenario-actions">
                    <a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=pve&pve_tool=builder{{ server_qs }}&edit_event={{ event.id|urlencode }}#scenario-event-form" data-scenario-edit data-id="{{ event.id }}" data-type="{{ event.event_type }}" data-preset="{{ event.preset or event.spawn_preset or '' }}" data-name="{{ event.name }}" data-class="{{ event.class_name }}" data-x="{{ event.x }}" data-y="{{ event.y }}" data-z="{{ event.z }}" data-count="{{ event.count }}" data-radius="{{ event.radius }}" data-permanent="{{ 'true' if event.permanent else 'false' }}" data-restarts="{{ event.remaining_restarts }}" data-loot="{{ event.loot_preset }}" data-marker="{{ 'true' if event.visual_marker else 'false' }}" data-scene="{{ event.scene_type or 'compact_crater' }}" data-guard="{{ event.guard_class }}" data-guard-count="{{ event.guard_count }}" data-guard-radius="{{ event.guard_radius }}" data-gas-lifetime="{{ event.gas_lifetime or 1800 }}" data-gas-particle="{{ event.gas_particle or 'server_default' }}">Edit</a>
                    {% for action, label in [('upload', 'Retry'), ('pause', 'Pause'), ('cancel', 'Cancel'), ('delete', 'Delete')] %}
                    {% if action != 'upload' or event.upload_status == 'failed' %}
                    <form class="admin-form inline-action" action="/api/admin/scenario-event-action" method="post" data-route="/api/admin/scenario-event-action" data-scenario-action-form="true" {% if action in ['cancel', 'delete'] %}data-confirm="{{ 'Delete' if action == 'delete' else 'Cancel' }} event {{ event.name }} for this server? This will also rebuild native CE XML without that event when possible."{% endif %}>
                      <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                      <input class="hidden-field" name="event_id" value="{{ event.id }}">
                      <input class="hidden-field" name="action" value="{{ action }}">
                      <input class="hidden-field" name="return_to" value="/admin?section=pve&pve_tool=events{{ server_qs }}#pve-workshop">
                      <button type="submit">{{ label }}</button><span class="result muted"></span>
                    </form>
                    {% endif %}
                    {% endfor %}
                  </div>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="8">No scenario events queued.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "economy" %}
    <section class="section-panel" id="economy">
      <div class="section-head">
        <div>
          <h2>Economy</h2>
          <p class="tool-note">Control wallets, recurring wages, and reward or punishment rules without touching raw JSON.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Wage</h3>
          <form class="admin-form" method="post" action="/api/admin/wage" data-route="/api/admin/wage" id="wage-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="id" value="">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Pay who?
              <select name="target_type"><option value="user">One player</option><option value="role">Discord role</option><option value="faction">Faction balance</option></select>
            </label>
            <label>Target
              <select name="target_id" data-wage-target>
                <option value="">Choose member, role, or faction</option>
                <optgroup label="Discord members">
                  {% for member in (server.discord_members if server else []) %}<option value="{{ member.id }}" data-target-type="user">{{ member.label }}</option>{% endfor %}
                </optgroup>
                <optgroup label="Discord roles">
                  {% for role in (server.discord_roles if server else []) %}<option value="{{ role.id }}" data-target-type="role">{{ role.label }}</option>{% endfor %}
                </optgroup>
                <optgroup label="Factions">
                  {% for faction in (server.factions.values() if server and server.factions else []) %}<option value="{{ faction.name }}" data-target-type="faction">{{ faction.name }}</option>{% endfor %}
                </optgroup>
              </select>
            </label>
            <label>Amount <input name="amount" type="number" value="250"></label>
            <label>Cadence <select name="cadence"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
            <label>Active <select name="active"><option value="true">On</option><option value="false">Off</option></select></label>
            <div class="full"><button type="submit">Save Wage</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Wallet Adjustment</h3>
          <form class="admin-form" method="post" action="/api/admin/wallet-adjustment" data-route="/api/admin/wallet-adjustment">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Wallet type
              <select name="target_type"><option value="user">Player</option><option value="faction">Faction</option></select>
            </label>
            <label>Target
              <select name="target_id" data-wallet-target>
                <option value="">Choose player or faction</option>
                <optgroup label="Discord members">
                  {% for member in (server.discord_members if server else []) %}<option value="{{ member.id }}" data-target-type="user">{{ member.label }}</option>{% endfor %}
                </optgroup>
                <optgroup label="Factions">
                  {% for faction in (server.factions.values() if server and server.factions else []) %}<option value="{{ faction.name }}" data-target-type="faction">{{ faction.name }}</option>{% endfor %}
                </optgroup>
              </select>
            </label>
            <label>Amount <input name="amount" type="number" value="100"></label>
            <label>Account
              <select name="account"><option value="cash">Cash</option><option value="bank">Bank</option></select>
            </label>
            <label>Reason
              <select name="reason">
                <option value="admin reward">Admin reward</option>
                <option value="event prize">Event prize</option>
                <option value="refund">Refund</option>
                <option value="rule penalty">Rule penalty</option>
              </select>
            </label>
            <div class="full"><button type="submit">Adjust Wallet</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel full">
          <h3>Active Wages</h3>
          <table>
            <thead><tr><th>ID</th><th>Target</th><th>Amount</th><th>Cadence</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {% for wage in (server.wages if server else []) %}
              <tr>
                <td>{{ wage.id }}</td>
                <td>{{ wage.target_label or (wage.target_type ~ ' · ' ~ wage.target_id) }}</td>
                <td>{{ wage.amount }}</td>
                <td>{{ wage.cadence }}</td>
                <td>{{ 'On' if wage.active else 'Off' }}</td>
                <td>
                  <button type="button" data-wage-edit data-id="{{ wage.id }}" data-target-type="{{ wage.target_type }}" data-target-id="{{ wage.target_id }}" data-amount="{{ wage.amount }}" data-cadence="{{ wage.cadence }}" data-active="{{ 'true' if wage.active else 'false' }}">Edit</button>
                  <form class="admin-form inline-action" method="post" action="/api/admin/wage" data-route="/api/admin/wage" data-confirm="Delete wage {{ wage.id }}?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="id" value="{{ wage.id }}">
                    <input class="hidden-field" name="action" value="delete">
                    <button type="submit">Delete</button>
                  </form>
                </td>
              </tr>
              {% else %}
              <tr><td colspan="6">No wages set for this server yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
        <article class="admin-panel">
          <h3>Reward / Punishment Rule</h3>
          <form class="admin-form" method="post" action="/api/admin/economy-rule" data-route="/api/admin/economy-rule">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>When this happens
              <select name="event_type">
                <option value="chat_keyword">Chat keyword</option>
                <option value="kill">Player kill</option>
                <option value="death">Player death</option>
                <option value="zombie_kill">Infected kill</option>
                <option value="animal_kill">Animal kill</option>
                <option value="longshot">Longshot</option>
              </select>
            </label>
            <label>Reward or punish
              <select name="kind"><option value="reward">Reward pennies</option><option value="punishment">Remove pennies</option></select>
            </label>
            <label>Keyword / condition <input name="keyword" placeholder="e.g. gg, kill, longshot"></label>
            <label>Amount <input name="amount" type="number" value="100"></label>
            <div class="full"><button type="submit">Save Rule</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "shop" %}
    {% set edit_shop_key = request.args.get('edit_shop', '') %}
    {% set edit_shop = namespace(item_name=(edit_shop_key or 'NailsBox'), price=100, category='General', enabled='true', daily_limit=0, allowed_role_ids='', blocked_user_ids='') %}
    {% if server and edit_shop_key %}
      {% for item in server.shop_items %}
        {% if item.name == edit_shop_key %}
          {% set edit_shop.item_name = item.name %}
          {% set edit_shop.price = item.price %}
          {% set edit_shop.category = item.category %}
          {% set edit_shop.enabled = 'true' if item.enabled else 'false' %}
          {% set edit_shop.daily_limit = item.daily_limit or 0 %}
          {% set edit_shop.allowed_role_ids = item.allowed_role_ids|join(',') if item.allowed_role_ids else '' %}
          {% set edit_shop.blocked_user_ids = item.blocked_user_ids|join(',') if item.blocked_user_ids else '' %}
        {% endif %}
      {% endfor %}
    {% endif %}
    <section class="section-panel" id="shop-control">
      <div class="section-head">
        <div>
          <h2>Shop Control</h2>
          <p class="tool-note">Items imported from types.xml appear here already grouped by category. Admins can set prices, enable/disable items, add limits, and restrict items by Discord role or player.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Edit Shop Item</h3>
          <form class="admin-form {% if edit_shop_key %}dashboard-edit-modal{% endif %}" method="post" action="/api/admin/shop-item" data-route="/api/admin/shop-item" id="shop-edit-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label>Item name <input name="item_name" value="{{ edit_shop.item_name }}"></label>
            <label>Price <input name="price" type="number" value="{{ edit_shop.price }}"></label>
            <label>Category
              <select name="category">
                <option value="Building" {% if edit_shop.category == 'Building' %}selected{% endif %}>Building</option>
                <option value="Weapons" {% if edit_shop.category == 'Weapons' %}selected{% endif %}>Weapons</option>
                <option value="Medical" {% if edit_shop.category == 'Medical' %}selected{% endif %}>Medical</option>
                <option value="Food" {% if edit_shop.category == 'Food' %}selected{% endif %}>Food</option>
                <option value="Tools" {% if edit_shop.category == 'Tools' %}selected{% endif %}>Tools</option>
                <option value="Clothing" {% if edit_shop.category == 'Clothing' %}selected{% endif %}>Clothing</option>
                <option value="General" {% if edit_shop.category == 'General' %}selected{% endif %}>General</option>
              </select>
            </label>
            <label>Available <select name="enabled"><option value="true" {% if edit_shop.enabled == 'true' %}selected{% endif %}>On</option><option value="false" {% if edit_shop.enabled == 'false' %}selected{% endif %}>Off</option></select></label>
            <label>Daily purchase limit <input name="daily_limit" type="number" value="{{ edit_shop.daily_limit }}" placeholder="0 = server default"></label>
            <label>Role IDs allowed <input name="allowed_role_ids" value="{{ edit_shop.allowed_role_ids }}" placeholder="optional comma-separated role IDs"></label>
            <label class="full">Blocked player IDs <input name="blocked_user_ids" value="{{ edit_shop.blocked_user_ids }}" placeholder="optional comma-separated Discord user IDs"></label>
            <div class="full modal-actions"><button type="submit">Save Item</button>{% if edit_shop_key %}<a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=shop&guild_id={{ server.guild_id if server else '' }}#shop-control">Close</a>{% endif %} <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Build Shop Bundle</h3>
          <form class="admin-form" method="post" action="/api/admin/shop-bundle" data-route="/api/admin/shop-bundle" id="shop-bundle-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label>Bundle name <input name="bundle_name" value="Flagpole Kit"></label>
            <label>Price <input name="price" type="number" value="2500"></label>
            <label>Category <input name="category" value="Bundles"></label>
            <label>Available <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Daily purchase limit <input name="daily_limit" type="number" value="0" placeholder="0 = server default"></label>
            <label>Role IDs allowed <input name="allowed_role_ids" placeholder="optional comma-separated role IDs"></label>
            <div class="full">
              <div class="item-picker" data-item-picker data-picker-mode="bundle">
                <div class="item-picker-controls">
                  <label>Find item from this server's shop/types list
                    <input data-picker-item list="bundle-item-options" placeholder="Search item classname">
                  </label>
                  <label>Qty <input data-picker-qty type="number" min="1" max="999" value="1"></label>
                  <label>Damage <select data-picker-damage><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
                  <label>Slot <select data-picker-slot><option value="">Any</option><option>Head</option><option>Body</option><option>Vest</option><option>Back</option><option>Hips</option><option>Legs</option><option>Feet</option><option>Hands</option></select></label>
                  <button type="button" data-picker-add>Add</button>
                </div>
                <div class="item-picker-preview"><img class="item-thumb" data-picker-image src="/item-thumb/General" alt=""><span data-picker-label>Pick an item to preview it.</span></div>
                <div class="shop-picker-list">
                  {% for item in (server.shop_items[:12] if server else []) %}
                  <button type="button" class="shop-picker-card" data-picker-card data-item="{{ item.name }}" data-image="{{ item.image_url }}" data-fallback="{{ item.fallback_image_url }}"><img src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt=""><span><strong>{{ item.name }}</strong><span>{{ item.category }}</span></span></button>
                  {% endfor %}
                </div>
              </div>
              <datalist id="bundle-item-options">
                {% for item in (server.shop_items if server else []) %}<option value="{{ item.name }}">{{ item.category }}</option>{% endfor %}
              </datalist>
            </div>
            <label class="full">Bundle items
              <textarea name="bundle_items" data-picker-output placeholder="1x Flag_Base&#10;1x WoodenLog&#10;32x Nail"></textarea>
            </label>
            <label class="full">Blocked player IDs <input name="blocked_user_ids" placeholder="optional comma-separated Discord user IDs"></label>
            <div class="full"><button type="submit">Save Bundle</button> <span class="result muted"></span></div>
          </form>
          <p class="tool-note" style="margin-top:.75rem">Players buy the bundle name once. The bot charges once, then queues each listed item for the next restart delivery.</p>
        </article>
        <article class="admin-panel full" data-shop-list>
          <h3>All Shop Items</h3>
          <div class="shop-toolbar">
            <label>Search items <input data-shop-search oninput="window.filterShopItems && window.filterShopItems(this)" placeholder="type item/category/status"></label>
            <label>Category
              <select data-shop-category onchange="window.filterShopItems && window.filterShopItems(this)">
                <option value="">All categories</option>
                {% for category in (server.shop_categories.keys() if server else []) %}<option value="{{ category|lower }}">{{ category }}</option>{% endfor %}
              </select>
            </label>
            <span class="pill"><span data-shop-count>{{ server.shop_items|length if server else 0 }}</span> items</span>
          </div>
          <table class="item-table">
            <thead><tr><th>Item</th><th>Category</th><th>Price</th><th>Status</th><th>Limit</th><th>Edit</th></tr></thead>
            <tbody>
              {% for item in (server.shop_items if server else []) %}
              <tr data-shop-row data-category="{{ item.category|lower }}" data-search="{{ item.name|lower }} {{ item.category|lower }} {{ 'on' if item.enabled else 'off' }}">
                <td><div class="item-name-cell"><img class="item-thumb" src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt=""><span><strong>{{ item.name }}</strong>{% if item.type == 'bundle' %}<br><small>{{ item.bundle_summary }}</small>{% endif %}</span></div></td>
                <td>{{ item.category }}</td>
                <td>{{ item.price }}</td>
                <td>{{ 'On' if item.enabled else 'Off' }}</td>
                <td>{{ item.daily_limit if item.daily_limit else 'default' }}</td>
                <td><a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=shop&guild_id={{ server.guild_id if server else '' }}&edit_shop={{ item.name|urlencode }}#shop-edit-form" data-shop-edit data-item="{{ item.name }}" data-price="{{ item.price }}" data-category="{{ item.category }}" data-enabled="{{ 'true' if item.enabled else 'false' }}" data-limit="{{ item.daily_limit }}" data-roles="{{ item.allowed_role_ids|join(',') }}" data-blocked="{{ item.blocked_user_ids|join(',') }}">Edit</a></td>
              </tr>
              {% else %}
              <tr><td colspan="6">No shop items available.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
        {% for category, items in (server.shop_categories.items() if server else []) %}
        <article class="admin-panel">
          <h3>{{ category }}</h3>
          <table class="item-table">
            <thead><tr><th>Item</th><th>Price</th><th>Status</th><th>Edit</th></tr></thead>
            <tbody>
              {% for item in items %}
              <tr>
                <td><div class="item-name-cell"><img class="item-thumb" src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt=""><span><strong>{{ item.name }}</strong>{% if item.type == 'bundle' %}<br><small>{{ item.bundle_summary }}</small>{% endif %}</span></div></td>
                <td>{{ item.price }}</td>
                <td>{{ 'On' if item.enabled else 'Off' }}</td>
                <td><a class="button" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=shop&guild_id={{ server.guild_id if server else '' }}&edit_shop={{ item.name|urlencode }}#shop-edit-form" data-shop-edit data-item="{{ item.name }}" data-price="{{ item.price }}" data-category="{{ item.category }}" data-enabled="{{ 'true' if item.enabled else 'false' }}" data-limit="{{ item.daily_limit }}" data-roles="{{ item.allowed_role_ids|join(',') }}" data-blocked="{{ item.blocked_user_ids|join(',') }}">Edit</a></td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
        {% else %}
        <article class="admin-panel"><h3>No Shop Items</h3><p class="muted">Import types.xml in Discord with `/tools importtypesxml`, then manage the items here.</p></article>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "xml-workshop" %}
    <section class="section-panel" id="xml-workshop">
      <div class="section-head">
        <div>
          <h2>XML Workshop</h2>
          <p class="tool-note">Build safe loot and loadout recipes for this server. These are saved as dashboard drafts first; live XML upload will only be added through the guarded injector path.</p>
        </div>
      </div>
      <nav class="tool-switcher" aria-label="XML workshop tools">
        {% for key, label in [("loot", "Loot Rules"), ("airdrop", "Airdrop Builder"), ("container", "Bags & Containers"), ("player-loadout", "Player Loadouts"), ("vehicle-loadout", "Vehicle Loadouts"), ("saved", "Saved Recipes")] %}
        <a class="{{ 'active' if xml_tool == key else '' }}" href="/admin?section=xml-workshop&xml_tool={{ key }}{{ server_qs }}">{{ label }}</a>
        {% endfor %}
      </nav>
      <div class="panel-grid">
        {% if xml_tool == "loot" %}
        <article class="admin-panel full" data-types-tool>
          <h3>Types XML Tools</h3>
          <p class="tool-note">Paste a types.xml file, choose a tool, then generate a safe edited copy. This belongs in XML Workshop and does not overwrite the server file until the guarded uploader is used.</p>
          <div class="panel-grid">
            <label class="full">Paste types.xml
              <textarea data-types-input placeholder="<?xml version=&quot;1.0&quot;?><types><type name=&quot;AKM&quot;>...</type></types>"></textarea>
            </label>
            <label>Tool
              <select data-types-action>
                <option value="reduce">Types Reducer</option>
                <option value="boost">Types Booster</option>
                <option value="lifetime_reduce">Lifetime Reducer</option>
                <option value="tier_boost">Tier Booster</option>
                <option value="organize">Types Organizer</option>
              </select>
            </label>
            <label>Factor <input data-types-factor type="number" step="0.05" value="0.5"></label>
            <label>Filter <input data-types-filter placeholder="classname/category/tier"></label>
            <label class="check"><input data-types-field value="nominal" type="checkbox" checked> Nominal</label>
            <label class="check"><input data-types-field value="min" type="checkbox"> Min</label>
            <label class="check"><input data-types-field value="lifetime" type="checkbox"> Lifetime</label>
            <label class="check"><input data-types-field value="restock" type="checkbox"> Restock</label>
            <div class="full"><button type="button" data-types-process>Generate XML</button> <button type="button" data-types-copy>Copy Output</button> <span class="result muted" data-types-result></span></div>
            <label class="full">Generated XML
              <textarea data-types-output readonly placeholder="Processed XML appears here"></textarea>
            </label>
          </div>
        </article>
        <article class="admin-panel">
          <h3>Loot Quality Rules</h3>
          <form class="admin-form" method="post" action="/api/admin/xml-workshop" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=xml-workshop&guild_id={{ server.guild_id if server else '' }}#xml-workshop">
            <input class="hidden-field" name="recipe_kind" value="settings">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Default item damage
              <select name="default_damage">
                <option value="pristine">Pristine</option>
                <option value="worn">Worn</option>
                <option value="random">Random</option>
              </select>
            </label>
            <label>Types quantity mode
              <select name="quantity_mode">
                <option value="full">Force selected categories full / 100%</option>
                <option value="vanilla">Keep vanilla</option>
                <option value="custom">Use recipe values</option>
              </select>
            </label>
            <label class="check"><input type="checkbox" name="full_magazines" checked> Weapons, magazines and ammo quantity rules</label>
            <label class="check"><input type="checkbox" name="full_liquids" checked> Food, drink and container quantity rules</label>
            <label class="check"><input type="checkbox" name="full_meds" checked> Medical, tablets and survival item quantity rules</label>
            <label class="check"><input type="checkbox" name="weapon_attachments" checked> Weapons use attachment recipes</label>
            <div class="full embed-preview"><strong>Types.xml scope</strong><span>These are draft rule choices for whole categories. The final injector must show exactly which XML fields it will change before upload.</span></div>
            <label class="full">Notes <input name="notes" placeholder="What this rule pack is for"></label>
            <div class="full embed-preview"><strong>Safe mode</strong><span>This saves the intent only. The injector must download current XML, validate it, show a diff, keep one latest backup, then upload.</span></div>
            <div class="full"><button type="submit">Save Loot Rules</button> <span class="result muted"></span></div>
          </form>
        </article>
        {% endif %}
        {% if xml_tool == "airdrop" %}
        <article class="admin-panel full">
          <h3>Airdrop Builder</h3>
          <form class="admin-form" method="post" action="/api/admin/xml-workshop" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=xml-workshop&guild_id={{ server.guild_id if server else '' }}#airdrop-builder">
            <input class="hidden-field" name="recipe_kind" value="airdrop">
            <div class="full xml-tool-layout">
              <div class="stack">
                <label>Recipe name <input name="recipe_name" value="Military Airdrop"></label>
                <div class="mini-grid">
                  <label>Event name <input name="event_name" value="Static_WanderingAirdrop"></label>
                </div>
                <label>Container
                  <select class="picker-select" name="container_class" data-visual-select="containers">
                    {% for item in xml_picker_groups.containers %}<option value="{{ item.name }}" {{ 'selected' if item.name == 'StaticObj_Misc_WoodenCrate_5x' else '' }}>{{ item.name }} - {{ item.category }}</option>{% endfor %}
                  </select>
                </label>
                <div class="mini-grid">
                  <label>Nominal <input name="nominal" type="number" min="0" value="1"></label>
                  <label>Min <input name="min_count" type="number" min="0" value="1"></label>
                  <label>Max <input name="max_count" type="number" min="0" value="1"></label>
                  <label>Lifetime seconds <input name="lifetime" type="number" min="1" value="1800"></label>
                  <label>Restock seconds <input name="restock" type="number" min="0" value="3600"></label>
                  <label>Safe radius <input name="saferadius" type="number" min="0" value="0"></label>
                  <label>Distance radius <input name="distanceradius" type="number" min="0" value="1000"></label>
                  <label>Cleanup radius <input name="cleanupradius" type="number" min="0" value="1500"></label>
                  <label>Loot min <input name="lootmin" type="number" min="0" value="40"></label>
                  <label>Loot max <input name="lootmax" type="number" min="0" value="40"></label>
                  <label>Spawn radius <input name="spawn_radius" type="number" min="1" value="20"></label>
                  <label>Zombie guard event
                    <select name="secondary_event">
                      <option value="">No guards</option>
                      <option value="InfectedArmy">Military infected</option>
                      <option value="InfectedPolice">Police infected</option>
                      <option value="InfectedMedic">Medical infected</option>
                    </select>
                  </label>
                </div>
                <div class="mini-grid">
                  <label>Duration
                    <select name="duration_mode">
                      <option value="permanent">Permanent event</option>
                      <option value="temporary">Temporary event</option>
                    </select>
                  </label>
                  <label>Temporary restarts <input name="temporary_restarts" type="number" min="1" value="2"></label>
                  <label>Placement
                    <select name="placement_mode">
                      <option value="manual">Use map-picked positions</option>
                      <option value="random_inland">Random inland positions</option>
                      <option value="random_military">Random military/high-tier positions</option>
                    </select>
                  </label>
                  <label>Random count
                    <select name="random_count">
                      <option value="2">2 drops</option>
                      <option value="4">4 drops</option>
                      <option value="6">6 drops</option>
                    </select>
                  </label>
                </div>
                <label>Spawn positions
                  <textarea name="positions" placeholder="10869, 10937&#10;9621, 10184"></textarea>
                </label>
                <div class="full zone-map" data-airdrop-map data-map-size="{{ server.map_size if server else 15360 }}" {% if server %}style="--map-image: url('/map-image/{{ server.map_key }}');"{% endif %}>
                  {% if server and not server.map_image_available %}
                  <div class="map-missing">Real {{ server.map|upper }} map image is not installed yet. Add <code>{{ server.map_key }}_map.jpg</code> beside the bot, or set the Railway map image variable, and the airdrop picker will use it automatically.</div>
                  {% endif %}
                </div>
                <div class="airdrop-map-tools">
                  <button type="button" data-airdrop-clear>Clear Locations</button>
                  <button type="button" data-airdrop-undo>Undo Location</button>
                  <span class="muted" data-airdrop-readout>Click the map to add airdrop positions.</span>
                </div>
                <div class="item-picker" data-item-picker data-picker-mode="xml" data-picker-group="cargo">
                  <div class="item-picker-controls">
                    <label>Optional fixed cargo
                      <select class="picker-select" data-picker-item>
                        <option value="">Choose item</option>
                        {% for item in xml_picker_groups.cargo %}<option value="{{ item.name }}">{{ item.name }} - {{ item.category }}</option>{% endfor %}
                      </select>
                    </label>
                    <label>Qty <input data-picker-qty type="number" min="1" max="999" value="1"></label>
                    <label>Fill <select data-picker-quantity><option value="-1">Native</option><option value="100">Full</option><option value="75">75%</option><option value="50">50%</option></select></label>
                    <label>Damage <select data-picker-damage><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
                    <button type="button" data-picker-add>Add</button>
                  </div>
                  <div class="item-picker-preview"><img class="item-thumb" data-picker-image src="/item-thumb/General" alt=""><span data-picker-label>Optional fixed cargo is added as a draft cargo block.</span></div>
                </div>
                <label>Fixed cargo draft
                  <div class="selected-items" data-selected-items data-empty-text="No fixed cargo added yet"></div>
                  <textarea class="raw-output" name="items" data-picker-output placeholder="Ammo_762x39Tracer, 1, -1, pristine"></textarea>
                </label>
                <div><button type="submit">Save Airdrop Package</button> <span class="result muted"></span></div>
              </div>
              <aside class="xml-output-panel">
                <div class="xml-file-tabs" data-airdrop-tabs>
                  <button type="button" class="active" data-airdrop-file="events">events.xml</button>
                  <button type="button" data-airdrop-file="spawns">cfgeventspawns.xml</button>
                  <button type="button" data-airdrop-file="spawnable">cfgspawnabletypes.xml</button>
                </div>
                <pre class="save-preview" data-live-output data-airdrop-output-file="events"></pre>
                <div class="embed-preview"><strong>Console airdrop package</strong><span>These snippets spawn the selected container directly and put cargo on that container class through cfgspawnabletypes.xml.</span></div>
              </aside>
            </div>
          </form>
        </article>
        {% endif %}
        {% if xml_tool == "container" %}
        <article class="admin-panel full">
          <h3>Filled Bag / Container Generator</h3>
          <form class="admin-form" method="post" action="/api/admin/xml-workshop" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=xml-workshop&guild_id={{ server.guild_id if server else '' }}#container-builder">
            <input class="hidden-field" name="recipe_kind" value="container">
            <div class="full xml-tool-layout">
              <div class="stack">
                <label>Recipe name <input name="recipe_name" value="Starter Builder Bag"></label>
                <label>Container classname
                  <select class="picker-select" name="container_class" data-visual-select="containers">
                    {% for item in xml_picker_groups.containers %}<option value="{{ item.name }}" {{ 'selected' if item.name == 'DryBag_Black' else '' }}>{{ item.name }} - {{ item.category }}</option>{% endfor %}
                  </select>
                </label>
                <label>Spawn damage <select name="damage"><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
                <label>Maximum cargo slots <input name="capacity_hint" type="number" value="0" placeholder="optional"></label>
                <div class="item-picker" data-item-picker data-picker-mode="xml" data-picker-group="cargo">
                  <div class="item-picker-controls">
                    <label>Find item
                      <select class="picker-select" data-picker-item>
                        <option value="">Choose item</option>
                        {% for item in xml_picker_groups.cargo %}<option value="{{ item.name }}">{{ item.name }} - {{ item.category }}</option>{% endfor %}
                      </select>
                    </label>
                    <label>Qty <input data-picker-qty type="number" min="1" max="999" value="1"></label>
                    <label>Fill <select data-picker-quantity><option value="-1">Native</option><option value="100">Full</option><option value="75">75%</option><option value="50">50%</option><option value="25">25%</option></select></label>
                    <label>Damage <select data-picker-damage><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
                    <button type="button" data-picker-add>Add</button>
                  </div>
                  <div class="item-picker-preview"><img class="item-thumb" data-picker-image src="/item-thumb/General" alt=""><span data-picker-label>Choose items without typing classnames by hand.</span></div>
                </div>
                <label>Items inside
                  <div class="selected-items" data-selected-items data-empty-text="No items added yet"></div>
                  <textarea class="raw-output" name="items" data-picker-output placeholder="Nail, 32, -1, pristine&#10;Hatchet, 1, -1, pristine"></textarea>
                </label>
                <div><button type="submit">Save Container Recipe</button> <span class="result muted"></span></div>
              </div>
              <aside class="xml-output-panel">
                <div class="mini-grid">
                  <div class="mini-card"><span class="muted">Output</span><strong>cfgspawnabletypes</strong></div>
                  <div class="mini-card"><span class="muted">Mode</span><strong>Draft</strong></div>
                </div>
                <pre class="save-preview" data-live-output></pre>
                <div class="embed-preview"><strong>Where this goes</strong><span>This generates a safe draft for `cfgspawnabletypes.xml`. Live upload should use the guarded injector after preview/diff validation.</span></div>
              </aside>
            </div>
          </form>
        </article>
        {% endif %}
        {% if xml_tool == "player-loadout" %}
        <article class="admin-panel full">
          <h3>Player Loadout</h3>
          <form class="admin-form player-loadout-form" method="post" action="/api/admin/xml-workshop" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=xml-workshop&guild_id={{ server.guild_id if server else '' }}#player-loadout-builder">
            <input class="hidden-field" name="recipe_kind" value="player_loadout">
            <div class="full xml-tool-layout player-loadout-layout">
              <div class="stack">
                <label>Loadout name <input name="recipe_name" value="Fresh Spawn Plus"></label>
                <label>Custom file path <input name="custom_path" value="./custom/WanderingLoadout.json"></label>
                <label>Role restriction
                  <select name="role_ids">
                    <option value="">No role restriction</option>
                    {% for role in (server.discord_roles if server else []) %}<option value="{{ role.id }}">{{ role.label }}</option>{% endfor %}
                  </select>
                </label>
                <div class="loadout-builder">
                  <div>
                    <h4>Player Slots</h4>
                    <div class="loadout-slots">
                      {% for slot in ["Head", "Eyes", "Mask", "Body", "Vest", "Back", "Hips", "Legs", "Feet", "Hands", "Left Shoulder", "Right Shoulder", "Gloves", "Armband"] %}
                      <button class="loadout-slot" type="button" data-loadout-slot="{{ slot }}">{{ slot }}</button>
                      {% endfor %}
                    </div>
                  </div>
                  <div class="loadout-selected-slot">
                    <strong data-active-slot-label>Selected slot: Head</strong>
                    <p class="tool-note" data-active-slot-note>Showing Head options below. Pick a card or use the dropdown, then press Add.</p>
                  </div>
                </div>
                <div class="loadout-workbench">
                  <div class="embed-preview"><strong>Player loadout builder</strong><span>Pick a body slot, add items from the picker, then drag selected rows to reorder the generated loadout.</span></div>
                  <div class="item-picker" data-item-picker data-picker-mode="loadout" data-picker-group="Head">
                    <div class="item-picker-controls">
                      <label>Find item
                        <select class="picker-select" data-picker-item>
                          <option value="">Choose item</option>
                          {% for item in xml_picker_groups.Head %}<option value="{{ item.name }}">{{ item.name }} - {{ item.category }}</option>{% endfor %}
                        </select>
                      </label>
                      <label>Qty <input data-picker-qty type="number" min="1" max="999" value="1"></label>
                      <label>Fill <select data-picker-quantity><option value="-1">Native</option><option value="100">Full</option><option value="75">75%</option><option value="50">50%</option></select></label>
                      <label>Slot <select data-picker-slot><option selected>Head</option><option>Eyes</option><option>Mask</option><option>Body</option><option>Vest</option><option>Back</option><option>Hips</option><option>Legs</option><option>Feet</option><option>Hands</option><option>Left Shoulder</option><option>Right Shoulder</option><option>Gloves</option><option>Armband</option><option value="">Unsorted</option></select></label>
                      <button type="button" data-picker-add>Add</button>
                    </div>
                    <label>Attachment for weapon/item
                      <select class="picker-select" data-picker-attachment>
                        <option value="">None</option>
                        {% for item in xml_picker_groups.cargo %}<option value="{{ item.name }}">{{ item.name }} - {{ item.category }}</option>{% endfor %}
                      </select>
                    </label>
                    <label>Damage <select data-picker-damage><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
                    <div class="item-picker-preview"><img class="item-thumb" data-picker-image src="/item-thumb/General" alt=""><span data-picker-label>Pick gear, slot, quantity and damage.</span></div>
                  </div>
                  <label>Loadout items
                    <div class="selected-items" data-selected-items data-empty-text="No loadout items added yet"></div>
                    <textarea class="raw-output" name="items" data-picker-output placeholder="BandageDressing, 2, -1, pristine, Body&#10;WaterBottle, 1, 100, pristine, Back&#10;Mag_STANAG_30Rnd, 2, 100, pristine"></textarea>
                    <small class="field-help">Generated by the picker. Keep damage on Pristine for clean spawn kits.</small>
                  </label>
                </div>
                <div><button type="submit">Save Player Loadout</button> <span class="result muted"></span></div>
              </div>
              <aside class="xml-output-panel">
                <div class="mini-grid">
                  <div class="mini-card"><span class="muted">Output</span><strong>loadout JSON</strong></div>
                  <div class="mini-card"><span class="muted">File</span><strong>custom</strong></div>
                </div>
                <pre class="save-preview" data-live-output></pre>
                <div class="embed-preview"><strong>Where this goes</strong><span>Save this as the custom JSON file, then reference it in `cfggameplay.json` under `PlayerData.spawnGearPresetFiles`.</span></div>
              </aside>
            </div>
            <pre class="full save-preview" data-save-preview hidden></pre>
          </form>
        </article>
        {% endif %}
        {% if xml_tool == "vehicle-loadout" %}
        <article class="admin-panel full">
          <h3>Vehicle Loadout</h3>
          <form class="admin-form" method="post" action="/api/admin/xml-workshop" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=xml-workshop&guild_id={{ server.guild_id if server else '' }}#vehicle-loadout-builder">
            <input class="hidden-field" name="recipe_kind" value="vehicle_loadout">
            <div class="full xml-tool-layout">
              <div class="stack">
                <label>Vehicle recipe <input name="recipe_name" value="Builder Truck"></label>
                <label>Vehicle classname
                  <select class="picker-select" name="vehicle_class" data-visual-select="vehicles">
                    {% for item in xml_picker_groups.vehicles %}<option value="{{ item.name }}" {{ 'selected' if item.name == 'Truck_01_Covered' else '' }}>{{ item.name }} - {{ item.category }}</option>{% endfor %}
                  </select>
                </label>
                <label>Mode <select name="vehicle_mode"><option value="full_with_cargo">Full vehicle with cargo</option><option value="full_no_cargo">Full vehicle, no cargo</option><option value="native">Use native files</option></select></label>
                <div class="vehicle-workbench">
                  <div class="item-picker" data-item-picker data-picker-mode="vehicle_cargo" data-picker-group="cargo">
                    <div class="item-picker-controls">
                      <label>Find cargo item
                        <select class="picker-select" data-picker-item>
                          <option value="">Choose item</option>
                          {% for item in xml_picker_groups.cargo %}<option value="{{ item.name }}">{{ item.name }} - {{ item.category }}</option>{% endfor %}
                        </select>
                      </label>
                      <label>Qty <input data-picker-qty type="number" min="1" max="999" value="1"></label>
                      <label>Fill <select data-picker-quantity><option value="-1">Native</option><option value="100">Full</option><option value="75">75%</option><option value="50">50%</option></select></label>
                      <label>Damage <select data-picker-damage><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
                      <button type="button" data-picker-add>Add</button>
                    </div>
                    <div class="item-picker-preview"><img class="item-thumb" data-picker-image src="/item-thumb/General" alt=""><span data-picker-label>Click cargo cards to add them, then drag the selected cargo rows into order.</span></div>
                  </div>
                  <label>Cargo items
                    <div class="selected-items vehicle-cargo-board" data-selected-items data-empty-text="No cargo items added yet"></div>
                    <textarea class="raw-output" name="items" data-picker-output placeholder="WoodenPlank, 20, -1, pristine&#10;Nail, 99, -1, pristine"></textarea>
                  </label>
                </div>
                <div><button type="submit">Save Vehicle Loadout</button> <span class="result muted"></span></div>
              </div>
              <aside class="xml-output-panel">
                <div class="mini-grid">
                  <div class="mini-card"><span class="muted">Output</span><strong>spawnabletypes</strong></div>
                  <div class="mini-card"><span class="muted">Vehicle</span><strong>cargo</strong></div>
                </div>
                <pre class="save-preview" data-live-output></pre>
                <div class="embed-preview"><strong>Where this goes</strong><span>This drafts the vehicle `cfgspawnabletypes.xml` cargo/attachment block. Parts and cargo should be previewed before live upload.</span></div>
              </aside>
            </div>
          </form>
        </article>
        {% endif %}
        {% if xml_tool == "saved" %}
        <article class="admin-panel full">
          <h3>Saved XML Recipes</h3>
          <div class="mini-grid">
            <div class="mini-card"><span class="muted">Containers</span><strong>{{ server.xml_workshop.container_recipes|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Airdrops</span><strong>{{ server.xml_workshop.airdrop_recipes|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Player loadouts</span><strong>{{ server.xml_workshop.player_loadouts|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Vehicle loadouts</span><strong>{{ server.xml_workshop.vehicle_loadouts|length if server else 0 }}</strong></div>
          </div>
          <p class="tool-note" style="margin-top:.75rem">{{ server.xml_workshop.status if server else 'No recipes saved yet.' }}</p>
          <div class="recipe-list">
            {% for recipe in (server.xml_workshop.player_loadouts if server else []) %}
            <div class="recipe-row">
              <strong>Player: {{ recipe.name }}</strong>
              <span class="muted">{{ recipe.custom_path or recipe.cfggameplay_reference }}</span>
              <div>{% for item in recipe.items[:10] %}{{ item.quantity }}x {{ item.item }}{% if item.slot %} -> {{ item.slot }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}</div>
            </div>
            {% endfor %}
            {% for recipe in (server.xml_workshop.container_recipes if server else []) %}
            <div class="recipe-row">
              <strong>Container: {{ recipe.name }}</strong>
              <span class="muted">{{ recipe.container_class }} · {{ recipe.damage }}</span>
              <div>{% for item in recipe.items[:10] %}{{ item.quantity }}x {{ item.item }}{% if not loop.last %}, {% endif %}{% endfor %}</div>
            </div>
            {% endfor %}
            {% for recipe in (server.xml_workshop.airdrop_recipes if server else []) %}
            <div class="recipe-row">
              <strong>Airdrop: {{ recipe.name }}</strong>
              <span class="muted">{{ recipe.event_name }} · {{ recipe.container_class }} · {{ recipe.positions|length }} position(s)</span>
              <div>{% for item in recipe.items[:10] %}{{ item.quantity }}x {{ item.item }}{% if not loop.last %}, {% endif %}{% endfor %}</div>
            </div>
            {% endfor %}
            {% for recipe in (server.xml_workshop.vehicle_loadouts if server else []) %}
            <div class="recipe-row">
              <strong>Vehicle: {{ recipe.name }}</strong>
              <span class="muted">{{ recipe.vehicle_class }} · {{ recipe.vehicle_mode }}</span>
              <div>{% for item in recipe.items[:10] %}{{ item.quantity }}x {{ item.item }}{% if not loop.last %}, {% endif %}{% endfor %}</div>
            </div>
            {% endfor %}
          </div>
        </article>
        {% endif %}
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "dayz-converter" %}
    <section class="section-panel" id="dayz-converter">
      <div class="section-head">
        <div>
          <h2>DayZ Map JSON Converter</h2>
          <p class="tool-note">Upload a DayZ Editor JSON export and convert it into the three matching CE snippets: events, event spawns and event groups. Generate first, then use guarded merge upload when you are ready to update the live server files.</p>
        </div>
      </div>
      <form class="xml-tool-form" data-local-generator-form data-route="/api/admin/convert-dayz-xml" enctype="multipart/form-data">
        <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
        <div class="full xml-converter-grid">
          <div class="stack">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Event Name
              <input name="event_name" value="Event_MyCustomBase" placeholder="Event_MyCustomBase">
            </label>
            <label>DayZ Editor JSON file
              <input type="file" name="dayz_json" accept=".json,application/json">
            </label>
            <label>Or paste JSON
              <textarea name="json_text" placeholder='{"EditorObjects":[{"Type":"Land_Mil_Barracks_i","Position":[2500.5,120.2,5000.1],"Orientation":[45,0,0]}]}'></textarea>
            </label>
            <div class="toolbar">
              <button type="submit">Generate DayZ XML</button>
              <span class="result muted" data-tool-result></span>
            </div>
          </div>
          <aside class="xml-output-panel">
            <div class="mini-grid">
              <div class="mini-card"><span class="muted">Input</span><strong>Editor JSON</strong></div>
              <div class="mini-card"><span class="muted">Anchor</span><strong>First valid object</strong></div>
              <div class="mini-card"><span class="muted">Coords</span><strong>6 decimals max</strong></div>
              <div class="mini-card"><span class="muted">Live</span><strong>Backup then merge</strong></div>
            </div>
            <div class="embed-preview"><strong>Output files</strong><span>Copy each generated block or merge the named event/group into the matching live file. Invalid objects are skipped with warnings instead of crashing the converter.</span></div>
          </aside>
        </div>
        <div class="full xml-snippet-grid" data-tool-output-group hidden>
          <div class="xml-snippet-box">
            <div class="row-between"><strong>events.xml Snippet</strong><button type="button" data-tool-copy="events_xml">Copy to Clipboard</button></div>
            <textarea readonly data-tool-output="events_xml"></textarea>
          </div>
          <div class="xml-snippet-box">
            <div class="row-between"><strong>eventspawns.xml Snippet</strong><button type="button" data-tool-copy="eventspawns_xml">Copy to Clipboard</button></div>
            <textarea readonly data-tool-output="eventspawns_xml"></textarea>
          </div>
          <div class="xml-snippet-box">
            <div class="row-between"><strong>eventgroups.xml Snippet</strong><button type="button" data-tool-copy="eventgroups_xml">Copy to Clipboard</button></div>
            <textarea readonly data-tool-output="eventgroups_xml"></textarea>
          </div>
        </div>
        <article class="admin-panel full" data-converter-inject-panel>
          <h3>Guarded Merge Upload</h3>
          <p class="tool-note">This downloads each live XML file, backs it up, replaces any matching event/group name, then uploads the merged file. It does not replace the whole file with a snippet.</p>
          <div class="mini-grid">
            <label>events.xml path
              <input name="events_path" value="{{ ce_defaults.events_path }}">
            </label>
            <label>event spawns path
              <input name="eventspawns_path" value="{{ ce_defaults.eventspawns_path }}">
            </label>
            <label>event groups path
              <input name="eventgroups_path" value="{{ ce_defaults.eventgroups_path }}">
            </label>
          </div>
          <div class="toolbar">
            <button type="button" data-converter-inject>Merge Generated XML to Server</button>
            <label class="check"><input type="checkbox" name="allow_create"> Create missing XML files if needed</label>
            <span class="result muted" data-inject-result></span>
          </div>
        </article>
      </form>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "loot-engine" %}
    <section class="section-panel" id="loot-engine">
      <div class="section-head">
        <div>
          <h2>DayZ Loot & Loadout Engine</h2>
          <p class="tool-note">Separate generators for economy XML, player loadout snippets and vehicle spawnabletypes. These tools generate guarded XML text only; live file upload stays separate.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel full">
          <h3>types.xml Loot Tweaker</h3>
          <form class="xml-tool-form" data-local-generator-form data-route="/api/admin/loot-tweak">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label class="full">Paste full types.xml or one type block
              <textarea name="xml_text" placeholder='<types><type name="M4A1"><nominal>10</nominal><min>5</min><lifetime>3600</lifetime><restock>0</restock><flags count_in_map="1" /></type></types>'></textarea>
            </label>
            <label>Item classname <input name="item_name" value="M4A1"></label>
            <label>nominal <input type="number" min="0" name="nominal" placeholder="leave blank to keep"></label>
            <label>min <input type="number" min="0" name="min" placeholder="leave blank to keep"></label>
            <label>lifetime <input type="number" min="0" name="lifetime" placeholder="leave blank to keep"></label>
            <label>restock <input type="number" min="0" name="restock" placeholder="leave blank to keep"></label>
            <div class="full toolbar"><button type="submit">Generate Tweaked XML</button><button type="button" data-tool-copy="generated_xml">Copy Output</button><span class="result muted" data-tool-result></span></div>
            <label class="full">Generated XML
              <textarea readonly data-tool-output="generated_xml"></textarea>
            </label>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Player Spawn Loadout Generator</h3>
          <form class="xml-tool-form" data-local-generator-form data-route="/api/admin/loadout-generate">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label>Main item <input name="item_name" value="M4A1"></label>
            <label>Chance <input name="chance" type="number" min="0" max="1" step="0.01" value="1.00"></label>
            <label class="full">Attachments, comma-separated
              <input name="attachments" value="M4_RISHndgrd, M4_MPBttstck">
            </label>
            <label class="full">Extra item lines
              <textarea name="items" placeholder="BandageDressing | | 1.00&#10;WaterBottle | | 1.00"></textarea>
            </label>
            <div class="full toolbar"><button type="submit">Generate Loadout XML</button><button type="button" data-tool-copy="generated_xml">Copy Output</button><span class="result muted" data-tool-result></span></div>
            <label class="full">Generated XML
              <textarea readonly data-tool-output="generated_xml"></textarea>
            </label>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Vehicle Spawn Loadout Injector</h3>
          <form class="xml-tool-form" data-local-generator-form data-route="/api/admin/vehicle-loadout-generate">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label>Vehicle classname <input name="vehicle_class" value="OffroadHatchback"></label>
            <label>Wheel chance <input name="wheel_chance" type="number" min="0" max="1" step="0.01" value="0.80"></label>
            <label>Door chance <input name="door_chance" type="number" min="0" max="1" step="0.01" value="0.50"></label>
            <label>Radiator chance <input name="radiator_chance" type="number" min="0" max="1" step="0.01" value="1.00"></label>
            <label>Battery chance <input name="battery_chance" type="number" min="0" max="1" step="0.01" value="1.00"></label>
            <label>Fuel / spark chance <input name="fuel_chance" type="number" min="0" max="1" step="0.01" value="1.00"></label>
            <label class="full">Cargo items, comma-separated
              <input name="cargo_items" placeholder="CanisterGasoline, TireRepairKit">
            </label>
            <div class="full toolbar"><button type="submit">Generate Vehicle XML</button><button type="button" data-tool-copy="generated_xml">Copy Output</button><span class="result muted" data-tool-result></span></div>
            <label class="full">Generated XML
              <textarea readonly data-tool-output="generated_xml"></textarea>
            </label>
          </form>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "visual-loadout" %}
    <section class="section-panel" id="visual-loadout" data-visual-loadout-page>
      <div class="section-head">
        <div>
          <h2>Visual Spawn Loadout</h2>
          <p class="tool-note">Build spawn gear with body slots, weapon slots, cargo containers and attachment sockets. Download creates a ZIP with <code>custom/custom_loadout.json</code> and <code>cfggameplay.json</code>.</p>
        </div>
      </div>
      <div class="visual-loadout-layout">
        <aside class="admin-panel visual-browser" data-loadout-browser>
          <h3>Item Browser</h3>
          <label>Search items <input data-loadout-search placeholder="M4, backpack, bandage"><small class="field-help">Filter the server item list, then click or drag a card into the player layout.</small></label>
          <div class="loadout-category-row" data-loadout-categories>
            {% for category in visual_loadout_categories %}
            <a class="button {% if category.key == visual_loadout_category %}active{% endif %}" href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ visual_loadout_slot|urlencode }}{% if category.key %}&loadout_category={{ category.key|urlencode }}{% endif %}#visual-loadout" data-loadout-category="{{ category.key or 'all' }}">{{ category.label }}</a>
            {% endfor %}
          </div>
          <div class="embed-preview"><strong>{{ visual_loadout_category or visual_loadout_slot }}</strong><span>Click an item card to add it to the selected slot. These cards are rendered by HTML so they still work if browser scripts fail.</span></div>
          <div class="loadout-item-grid" data-loadout-items>
            {% for item in visual_loadout_items %}
            <form class="loadout-item-form" method="post" action="/api/admin/visual-loadout-draft">
              <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
              <input class="hidden-field" name="slot" value="{{ visual_loadout_slot }}">
              <input class="hidden-field" name="item" value="{{ item.name }}">
              <input class="hidden-field" name="action" value="add">
              <input class="hidden-field" name="return_to" value="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ visual_loadout_slot|urlencode }}{% if visual_loadout_category %}&loadout_category={{ visual_loadout_category|urlencode }}{% endif %}#visual-loadout">
              <button type="submit" class="loadout-item-card" draggable="true" data-loadout-item="{{ item.name }}">
                <img src="{{ item.image_url }}" loading="lazy" decoding="async" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt="">
                <span><strong>{{ item.label or item.name }}</strong><small>{{ item.name }} - {{ item.category }}</small></span>
              </button>
            </form>
            {% else %}
            <div class="embed-preview"><strong>No items found</strong><span>No matching items were found for this slot. Try Weapons, Clothing, or another slot.</span></div>
            {% endfor %}
          </div>
        </aside>
        <article class="admin-panel visual-canvas">
          <h3>Survivor Canvas</h3>
          <div class="embed-preview"><strong>Drag and drop loadout</strong><span>Drop clothing into body slots, weapons into shoulder/holster slots, and supplies into backpack, jacket, or pants cargo.</span></div>
          <div class="loadout-selected-slot" data-selected-loadout-slot><strong>{{ visual_loadout_slot }}</strong><span>Showing matching items in the browser. Pick another slot below to change the list.</span></div>
          <div class="command-loadout-stage" aria-label="Command visual loadout preview">
            <div class="command-gear-column">
              {% for card in visual_loadout_slot_cards[:5] %}
              {% set item = card.item %}
              <a class="command-gear-card" href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ card.slot.key|urlencode }}#visual-loadout">
                {% if item.name %}<img src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt="">{% endif %}
                <span>{{ card.slot.label }}</span><strong>{{ item.name if item.name else 'Empty' }}</strong>
              </a>
              {% endfor %}
            </div>
            <div class="command-paperdoll command-character"><img class="command-character-portrait" src="/brand-character" alt="Wandering Bot loadout preview"></div>
            <div class="command-gear-column">
              {% for card in visual_loadout_slot_cards[5:10] %}
              {% set item = card.item %}
              <a class="command-gear-card" href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ card.slot.key|urlencode }}#visual-loadout">
                {% if item.name %}<img src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt="">{% endif %}
                <span>{{ card.slot.label }}</span><strong>{{ item.name if item.name else 'Empty' }}</strong>
              </a>
              {% endfor %}
            </div>
            <div class="command-loadout-extra">
              {% for card in visual_loadout_slot_cards[10:13] %}
              {% set item = card.item %}
              <a class="command-gear-card" href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ card.slot.key|urlencode }}#visual-loadout">
                {% if item.name %}<img src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt="">{% endif %}
                <span>{{ card.slot.label }}</span><strong>{{ item.name if item.name else 'Empty' }}</strong>
              </a>
              {% endfor %}
            </div>
          </div>
          <div class="loadout-slot-grid">
            {% for card in visual_loadout_slot_cards %}
            {% set slot = card.slot %}
            {% set item = card.item %}
            <a href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ slot.key|urlencode }}#visual-loadout" class="visual-slot {% if slot.group == 'attachments' %}weapon{% endif %} {% if visual_loadout_slot == slot.key %}active{% endif %} {% if item.name %}filled{% endif %}" data-loadout-slot="{{ slot.key }}" data-slot-group="{{ slot.group }}">
              <span>{{ slot.label }}</span>
              {% if item.name %}
              <img class="item-thumb" src="{{ item.image_url }}" onerror="this.onerror=null;this.src='{{ item.fallback_image_url }}';" alt="">
              <strong>{{ item.name }}</strong>
              <small class="muted">Pristine{% if item.capacity %} · {{ item.capacity }} slots{% elif item.size %} · uses {{ item.size }} slots{% endif %}</small>
              {% else %}
              <strong>Empty</strong>
              {% endif %}
            </a>
            {% endfor %}
          </div>
          <div class="loadout-cargo-grid">
            {% for cargo in visual_loadout_cargo_slots %}
            <a class="cargo-box {% if visual_loadout_slot == cargo.key %}active drag-over{% endif %}" href="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ cargo.key|urlencode }}#visual-loadout" data-cargo-container="{{ cargo.container }}"><strong>{{ cargo.label }}</strong><div data-cargo-items="{{ cargo.container }}">{% for item in visual_loadout_draft.cargo.get(cargo.container, []) %}<span class="cargo-chip">{{ item }}</span>{% else %}<span class="muted">Empty</span>{% endfor %}</div></a>
            {% endfor %}
          </div>
          <div class="equipped-list">
            {% for row in visual_loadout_selected_rows %}
            <article class="equipped-card">
              <div class="equipped-head">
                <img src="{{ row.item.image_url }}" onerror="this.onerror=null;this.src='{{ row.item.fallback_image_url }}';" alt="">
                <div>
                  <strong>{{ row.slot.label }}: {{ row.item.name }}</strong>
                  <div class="equipped-meta">
                    <span>Pristine</span>
                    {% if row.item.capacity %}<span>{{ row.item.capacity }} storage slots estimate</span>{% endif %}
                    {% if row.item.size %}<span>{{ row.item.size }} item slots estimate</span>{% endif %}
                  </div>
                </div>
              </div>
              {% if row.child_slots %}
              <div class="child-slot-grid">
                {% for child in row.child_slots %}
                <div class="child-slot">
                  <strong>{{ child.label }}</strong>
                  {% if child.mode == "multi" %}
                  <div class="equipped-meta">
                    {% for added in child.current_values %}
                    <span class="cargo-chip">{{ added }}</span>
                    {% endfor %}
                  </div>
                  {% elif child.current_values %}
                  <div class="equipped-meta">{% for added in child.current_values %}<span class="cargo-chip">{{ added }}</span>{% endfor %}</div>
                  {% endif %}
                  <form class="child-choice-row" method="post" action="/api/admin/visual-loadout-draft">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="slot" value="{{ row.slot.key }}">
                    <input class="hidden-field" name="child_slot" value="{{ child.key }}">
                    <input class="hidden-field" name="action" value="add_child">
                    <input class="hidden-field" name="return_to" value="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ row.slot.key|urlencode }}#visual-loadout">
                    <select name="item">
                      {% for option in child["items"] %}
                      <option value="{{ option.name }}">{{ option.name }} - {{ option.category }}{% if option.size %} ({{ option.size }} slots){% endif %}</option>
                      {% endfor %}
                    </select>
                    <button type="submit">Add</button>
                  </form>
                  {% if child.selected and child.nested_slots %}
                  <div class="child-slot-grid" style="margin-top:.55rem">
                    {% for nested in child.nested_slots %}
                    <div class="child-slot">
                      <strong>{{ child.selected }} · {{ nested.label }}</strong>
                      {% if nested.current_values %}
                      <div class="equipped-meta">{% for added in nested.current_values %}<span class="cargo-chip">{{ added }}</span>{% endfor %}</div>
                      {% endif %}
                      <form class="child-choice-row" method="post" action="/api/admin/visual-loadout-draft">
                        <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                        <input class="hidden-field" name="slot" value="{{ row.slot.key }}">
                        <input class="hidden-field" name="child_slot" value="{{ child.key }}">
                        <input class="hidden-field" name="nested_slot" value="{{ nested.key }}">
                        <input class="hidden-field" name="action" value="add_grandchild">
                        <input class="hidden-field" name="return_to" value="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ row.slot.key|urlencode }}#visual-loadout">
                        <select name="item">
                          {% for option in nested["items"] %}
                          <option value="{{ option.name }}">{{ option.name }} - {{ option.category }}{% if option.size %} ({{ option.size }} slots){% endif %}</option>
                          {% endfor %}
                        </select>
                        <button type="submit">Add</button>
                      </form>
                    </div>
                    {% endfor %}
                  </div>
                  {% endif %}
                </div>
                {% endfor %}
              </div>
              {% else %}
              <span class="muted">No known child slots for this item yet.</span>
              {% endif %}
            </article>
            {% else %}
            <div class="embed-preview"><strong>No gear selected</strong><span>Pick a slot, then choose an item from the browser to unlock compatible attachments and cargo options.</span></div>
            {% endfor %}
          </div>
          <div class="attachment-tray" data-attachment-tray>
            <div class="row-between"><strong>Weapon Attachments</strong><button type="button" data-clear-selected-slot>Clear Selected</button></div>
            <div data-attachment-items></div>
          </div>
          <form method="post" action="/api/admin/visual-loadout-draft" class="toolbar">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="action" value="clear">
            <input class="hidden-field" name="return_to" value="/admin?section=visual-loadout{{ server_qs }}&loadout_slot={{ visual_loadout_slot|urlencode }}#visual-loadout">
            <button type="submit">Clear Loadout Draft</button>
          </form>
        </article>
        <aside class="admin-panel visual-export-panel">
          <h3>Live Export & Package</h3>
          <form class="xml-tool-form" method="post" action="/api/admin/loadout-package" data-loadout-package-form data-route="/api/admin/loadout-package">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label>Custom loadout JSON
              <textarea name="loadout_json" data-loadout-json spellcheck="false">{{ visual_loadout_json_text }}</textarea>
            </label>
            <label>Optional cfggameplay.json override
              <textarea name="cfggameplay_json" placeholder="Leave blank to let the bot create the correct cfggameplay.json"></textarea>
            </label>
            <label>Server custom_loadout.json path
              <input name="loadout_path" value="{{ ce_defaults.custom_loadout_path }}">
              <small class="field-help">Where the generated custom loadout file should upload on Nitrado.</small>
            </label>
            <label>Server cfggameplay.json path
              <input name="cfggameplay_path" value="{{ ce_defaults.cfggameplay_path }}">
              <small class="field-help">This file points DayZ at custom/custom_loadout.json.</small>
            </label>
            <div class="toolbar">
              <button type="submit">Download Complete Server Package</button>
              <button type="button" data-upload-loadout-package>Upload Package to Nitrado</button>
              <button type="button" data-copy-loadout-json>Copy Loadout JSON</button>
              <button type="button" data-reset-loadout>Reset</button>
            </div>
            <label class="check"><input type="checkbox" name="allow_create" checked> Create missing files/folders if needed</label>
            <span class="result muted" data-package-result></span>
          </form>
        </aside>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "bulk-economy" %}
    <section class="section-panel" id="bulk-economy">
      <div class="section-head">
        <div>
          <h2>Bulk Economy XML Utility</h2>
          <p class="tool-note">Paste a full <code>types.xml</code>, filter classnames, multiply nominal values or set lifetime in one guarded pass. Output is validated before it is shown.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel full">
          <h3>Batch types.xml Editor</h3>
          <form class="xml-tool-form" data-local-generator-form data-route="/api/admin/loot-bulk-tweak">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label class="full">Paste full types.xml
              <textarea name="xml_text" placeholder='<types><type name="Mag_STANAG_30Rnd"><nominal>20</nominal><lifetime>3600</lifetime><flags count_in_map="1" /></type></types>'></textarea>
            </label>
            <label>Filter text <input name="filter_text" placeholder="Mag_ or _Tier3"></label>
            <label>Match mode
              <select name="match_mode">
                <option value="contains">Contains</option>
                <option value="startswith">Starts with</option>
                <option value="endswith">Ends with</option>
                <option value="regex">Regex</option>
              </select>
            </label>
            <label>Multiply nominal by <input type="number" name="nominal_multiplier" min="0" max="20" step="0.01" value="1"></label>
            <label>Set lifetime to <input type="number" name="lifetime_value" min="0" placeholder="leave blank to keep"></label>
            <label>Set restock to <input type="number" name="restock_value" min="0" placeholder="leave blank to keep"></label>
            <label>Set min to <input type="number" name="min_value" min="0" placeholder="leave blank to keep"></label>
            <label class="full">Live server types.xml path
              <input name="target_path" value="{{ ce_defaults.types_path }}">
            </label>
            <div class="full toolbar">
              <button type="submit">Run Bulk Tweak</button>
              <button type="button" data-tool-copy="generated_xml">Copy Output</button>
              <button type="button" data-xml-inject data-output-key="generated_xml" data-file-kind="xml" data-label="types.xml">Upload Generated types.xml</button>
              <label class="check"><input type="checkbox" name="allow_create"> Create file if missing</label>
              <span class="result muted" data-tool-result></span>
            </div>
            <label class="full">Generated types.xml
              <textarea readonly data-tool-output="generated_xml"></textarea>
            </label>
          </form>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "moderation" %}
    {% set guard = (server.config.moderation_guard if server and server.config and server.config.moderation_guard else {}) %}
    {% set strikes = (server.config.moderation_guard_strikes if server and server.config and server.config.moderation_guard_strikes else {}) %}
    {% set cheat = (server.config.cheat_check if server and server.config and server.config.cheat_check else {}) %}
    {% set stack = (server.config.stack_watch if server and server.config and server.config.stack_watch else {}) %}
    <section class="section-panel" id="moderation">
      <div class="section-head">
        <div>
          <h2>Moderation Guard</h2>
          <p class="tool-note">Guild-scoped protection for spam, Discord invite adverts, scam phrases, mass mentions and PC cheat-check alerts. These settings only affect the selected server.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Spam, Scam & Advert Guard</h3>
          <form class="admin-form" method="post" action="/api/admin/moderation-guard" data-route="/api/admin/moderation-guard">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Guard enabled
              <select name="enabled"><option value="false" {{ 'selected' if not guard.enabled else '' }}>Off</option><option value="true" {{ 'selected' if guard.enabled else '' }}>On</option></select>
            </label>
            <label>Delete caught messages
              <select name="delete_messages"><option value="true" {{ 'selected' if guard.delete_messages is not defined or guard.delete_messages else '' }}>Yes</option><option value="false" {{ 'selected' if guard.delete_messages is defined and not guard.delete_messages else '' }}>No, log only</option></select>
            </label>
            <label>Staff/admin bypass
              <select name="staff_bypass"><option value="true" {{ 'selected' if guard.staff_bypass is not defined or guard.staff_bypass else '' }}>Yes</option><option value="false" {{ 'selected' if guard.staff_bypass is defined and not guard.staff_bypass else '' }}>No</option></select>
            </label>
            <label>Discord invite adverts
              <select name="watch_discord_invites"><option value="true" {{ 'selected' if guard.watch_discord_invites is not defined or guard.watch_discord_invites else '' }}>Watch</option><option value="false" {{ 'selected' if guard.watch_discord_invites is defined and not guard.watch_discord_invites else '' }}>Ignore</option></select>
            </label>
            <label>External links
              <select name="watch_external_links"><option value="false" {{ 'selected' if not guard.watch_external_links else '' }}>Ignore normal links</option><option value="true" {{ 'selected' if guard.watch_external_links else '' }}>Watch all links</option></select>
            </label>
            <label>Scam/fraud words
              <select name="watch_scam_words"><option value="true" {{ 'selected' if guard.watch_scam_words is not defined or guard.watch_scam_words else '' }}>Watch</option><option value="false" {{ 'selected' if guard.watch_scam_words is defined and not guard.watch_scam_words else '' }}>Ignore</option></select>
            </label>
            <label>Spam burst count <input type="number" min="1" max="50" name="spam_message_count" value="{{ guard.spam_message_count or 5 }}"></label>
            <label>Spam window seconds <input type="number" min="2" max="600" name="spam_window_seconds" value="{{ guard.spam_window_seconds or 12 }}"></label>
            <label>Repeated text count <input type="number" min="2" max="20" name="repeat_message_count" value="{{ guard.repeat_message_count or 3 }}"></label>
            <label>Mass mention limit <input type="number" min="1" max="100" name="mass_mention_limit" value="{{ guard.mass_mention_limit or 5 }}"></label>
            <label>First strike
              <select name="action_first"><option value="log" {{ 'selected' if guard.action_first == 'log' else '' }}>Log</option><option value="delete" {{ 'selected' if guard.action_first == 'delete' else '' }}>Delete</option><option value="warn" {{ 'selected' if guard.action_first is not defined or guard.action_first == 'warn' else '' }}>Warn</option><option value="timeout" {{ 'selected' if guard.action_first == 'timeout' else '' }}>Timeout</option><option value="kick" {{ 'selected' if guard.action_first == 'kick' else '' }}>Kick</option><option value="ban" {{ 'selected' if guard.action_first == 'ban' else '' }}>Ban</option></select>
            </label>
            <label>Second strike
              <select name="action_second"><option value="log" {{ 'selected' if guard.action_second == 'log' else '' }}>Log</option><option value="delete" {{ 'selected' if guard.action_second == 'delete' else '' }}>Delete</option><option value="warn" {{ 'selected' if guard.action_second == 'warn' else '' }}>Warn</option><option value="timeout" {{ 'selected' if guard.action_second is not defined or guard.action_second == 'timeout' else '' }}>Timeout</option><option value="kick" {{ 'selected' if guard.action_second == 'kick' else '' }}>Kick</option><option value="ban" {{ 'selected' if guard.action_second == 'ban' else '' }}>Ban</option></select>
            </label>
            <label>Third+ strike
              <select name="action_third"><option value="log" {{ 'selected' if guard.action_third == 'log' else '' }}>Log</option><option value="delete" {{ 'selected' if guard.action_third == 'delete' else '' }}>Delete</option><option value="warn" {{ 'selected' if guard.action_third == 'warn' else '' }}>Warn</option><option value="timeout" {{ 'selected' if guard.action_third is not defined or guard.action_third == 'timeout' else '' }}>Timeout</option><option value="kick" {{ 'selected' if guard.action_third == 'kick' else '' }}>Kick</option><option value="ban" {{ 'selected' if guard.action_third == 'ban' else '' }}>Ban</option></select>
            </label>
            <label>Timeout minutes <input type="number" min="1" max="10080" name="timeout_minutes" value="{{ guard.timeout_minutes or 10 }}"></label>
            <label class="full">Allowed link domains <textarea name="invite_allowlist" placeholder="dayzwanderingbot.com&#10;discord.gg/your-official-server">{% for item in (guard.invite_allowlist or ['dayzwanderingbot.com']) %}{{ item }}{% if not loop.last %}&#10;{% endif %}{% endfor %}</textarea></label>
            <label class="full">Blocked phrases <textarea name="blocked_phrases" placeholder="paste forbidden words or phrases, one per line">{% for item in (guard.blocked_phrases or []) %}{{ item }}{% if not loop.last %}&#10;{% endif %}{% endfor %}</textarea></label>
            <label class="full">Scam/fraud phrases <textarea name="scam_phrases" placeholder="free nitro&#10;steam gift&#10;airdrop crypto">{% for item in (guard.scam_phrases or []) %}{{ item }}{% if not loop.last %}&#10;{% endif %}{% endfor %}</textarea></label>
            <div class="full">
              <button type="submit">Save Moderation Guard</button>
              <span class="result muted"></span>
            </div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>PC Cheat Guard</h3>
          <form class="admin-form" method="post" action="/api/admin/moderation-guard" data-route="/api/admin/moderation-guard">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label>PC cheat checks
              <select name="cheat_check_enabled"><option value="true" {{ 'selected' if cheat.enabled is not defined or cheat.enabled else '' }}>On</option><option value="false" {{ 'selected' if cheat.enabled is defined and not cheat.enabled else '' }}>Off</option></select>
            </label>
            <label>Auto-ban suspicious chains
              <select name="cheat_check_auto_ban"><option value="false" {{ 'selected' if not cheat.auto_ban else '' }}>No, alert staff</option><option value="true" {{ 'selected' if cheat.auto_ban else '' }}>Yes</option></select>
            </label>
            <label>Kill chain window seconds <input type="number" min="10" max="900" name="cheat_chain_window_seconds" value="{{ cheat.chain_window_seconds or 200 }}"></label>
            <label>Cluster window seconds <input type="number" min="10" max="900" name="cheat_cluster_window_seconds" value="{{ cheat.cluster_window_seconds or 180 }}"></label>
            <label>Cluster minimum kills <input type="number" min="2" max="20" name="cheat_cluster_min_kills" value="{{ cheat.cluster_min_kills or 3 }}"></label>
            <label>Cluster max radius metres <input type="number" min="5" max="1000" name="cheat_cluster_max_radius" value="{{ cheat.cluster_max_radius or 50 }}"></label>
            <div class="embed-preview full"><strong>PC Cheat Feed</strong><span>Alerts post to the private `pc-cheat-check` channel. Auto-ban stays off unless you explicitly enable it for this server.</span></div>
          <div class="full"><button type="submit">Save PC Cheat Settings</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Stack Watch</h3>
          <form class="admin-form" method="post" action="/api/admin/moderation-guard" data-route="/api/admin/moderation-guard">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label>Watch placements
              <select name="stack_watch_enabled"><option value="true" {{ 'selected' if stack.enabled is not defined or stack.enabled else '' }}>On</option><option value="false" {{ 'selected' if stack.enabled is defined and not stack.enabled else '' }}>Off</option></select>
            </label>
            <label>Alert channel
              <select name="stack_watch_channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key or channel.value }}" {% if (stack.channel_key or 'admin_logs') == channel.key or (stack.channel_key or 'admin_logs') == channel.value %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Recent window seconds <input type="number" min="10" max="1800" name="stack_watch_window_seconds" value="{{ stack.window_seconds or 180 }}"></label>
            <label>Nearby radius metres <input type="number" min="1" max="100" name="stack_watch_radius_meters" value="{{ stack.radius_meters or 8 }}"></label>
            <label>Trigger count <input type="number" min="1" max="20" name="stack_watch_min_count" value="{{ stack.min_count or 2 }}"></label>
            <label>Alert each watched placement
              <select name="stack_watch_alert_each"><option value="true" {{ 'selected' if stack.alert_each_watched is not defined or stack.alert_each_watched else '' }}>Yes</option><option value="false" {{ 'selected' if stack.alert_each_watched is defined and not stack.alert_each_watched else '' }}>Only after trigger count</option></select>
            </label>
            <label>Area X <input name="stack_watch_area_x" value="{{ stack.area_x or '' }}" placeholder="optional"></label>
            <label>Area Z <input name="stack_watch_area_z" value="{{ stack.area_z or '' }}" placeholder="optional"></label>
            <label>Area radius metres <input type="number" min="0" max="30000" name="stack_watch_area_radius_meters" value="{{ stack.area_radius_meters or 0 }}" placeholder="0 = whole map"></label>
            <label>Minimum height <input name="stack_watch_min_height" value="{{ stack.min_height or '' }}" placeholder="optional"></label>
            <label>Maximum height <input name="stack_watch_max_height" value="{{ stack.max_height or '' }}" placeholder="optional"></label>
            <label class="full">Watched objects <textarea name="stack_watch_objects" placeholder="GardenPlot&#10;Fireplace&#10;FenceKit">{% for item in (stack.objects or ['GardenPlot', 'Fireplace', 'FireplaceIndoor', 'OvenIndoor', 'FenceKit', 'WatchtowerKit', 'TerritoryFlagKit']) %}{{ item }}{% if not loop.last %}&#10;{% endif %}{% endfor %}</textarea></label>
            <div class="embed-preview full"><strong>ADM placement watch</strong><span>Detects lines like Nameless Object&lt;GardenPlot&gt;, counts nearby repeat placements, and alerts staff for possible stacking raids.</span></div>
            <div class="full"><button type="submit">Save Stack Watch</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3 style="margin-top:1rem">Current Guard State</h3>
          <div class="mini-grid">
            <div class="mini-card"><span class="muted">Guard</span><strong>{{ 'On' if guard.enabled else 'Off' }}</strong></div>
            <div class="mini-card"><span class="muted">Tracked users</span><strong>{{ strikes|length }}</strong></div>
            <div class="mini-card"><span class="muted">PC cheat</span><strong>{{ 'On' if cheat.enabled is not defined or cheat.enabled else 'Off' }}</strong></div>
            <div class="mini-card"><span class="muted">Stack watch</span><strong>{{ 'On' if stack.enabled is not defined or stack.enabled else 'Off' }}</strong></div>
          </div>
          <div class="recipe-list">
            {% for user_id, strike in strikes.items() %}
            <div class="recipe-row"><strong>{{ user_id }}</strong><span class="muted">{{ strike.count or 0 }} strike(s) · {{ strike.last_violation or 'no detail' }}</span></div>
            {% else %}
            <p class="muted">No moderation strikes recorded for this server.</p>
            {% endfor %}
          </div>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "server-rules" %}
    <section class="section-panel" id="server-rules">
      <div class="section-head">
        <div>
          <h2>Server Rules & Nitrado Control</h2>
          <p class="tool-note">Control Discord-link enforcement, automatic Nitrado bans, immediate restart-on-ban, and DayZ on-screen messages. File changes take effect after a server restart.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Discord Link Enforcement</h3>
          <form class="admin-form" method="post" action="/api/admin/link-enforcement" data-route="/api/admin/link-enforcement">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Grace minutes after join <input name="grace_minutes" type="number" value="30" min="1"></label>
            <label>Action if still unlinked
              <select name="action">
                <option value="notify">Notify staff only</option>
                <option value="kick">Kick request / notify</option>
                <option value="temp_ban">Temp ban through Nitrado</option>
                <option value="perm_ban">Perm ban through Nitrado</option>
              </select>
            </label>
            <label>Temp ban minutes <input name="temp_ban_minutes" type="number" value="60" min="1"></label>
            <label>Restart after ban <select name="restart_on_ban"><option value="true">Yes, immediately</option><option value="false">No</option></select></label>
            <label>Notify channel
              <select name="notification_channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if channel.key == 'public_shame' or channel.key == 'admin_logs' %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label class="full">Player message / reason <textarea name="reason">You must join this Discord and link your gamertag with /linkgamer to play on this server.</textarea></label>
            <div class="full"><button type="submit">Save Enforcement</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>On-Screen Messages</h3>
          <form class="admin-form" method="post" action="/api/admin/on-screen-message" data-route="/api/admin/on-screen-message">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Message key <input name="message_id" value="discord-required"></label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>When to show
              <select name="trigger">
                <option value="server_restart">After restart</option>
                <option value="scheduled">Timed schedule</option>
                <option value="discord_required">Discord link reminder timer</option>
                <option value="custom">Custom timer</option>
              </select>
            </label>
            <label>Start delay seconds <input name="delay_seconds" type="number" value="30" min="0"></label>
            <label>Repeat minutes <input name="repeat_minutes" type="number" value="30" min="0"></label>
            <label>Display seconds <input name="display_seconds" type="number" value="10" min="1"></label>
            <label>Colour <input name="colour" type="color" value="#d5b45f"></label>
            <label class="full">Message text <textarea name="text">Join the Discord and link your gamertag with /linkgamer to keep playing.</textarea></label>
            <div class="full embed-preview">
              <strong>Restart required</strong>
              <span>The bot uploads this server's messages.xml only. DayZ reads it on server start, so the change applies after the next restart.</span>
            </div>
            <div class="full"><button type="submit">Save On-Screen Message</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "server-control" %}
    <section class="section-panel" id="server-control">
      <div class="section-head">
        <div>
          <h2>Server Control</h2>
          <p class="tool-note">Maintenance controls for this server only: restarts, raid damage, container damage, and vehicle reset schedules. Spawn events and loadout builders live on their own pages.</p>
        </div>
      </div>
      {% set restart_on = not (server and server.config.restart_schedule_enabled == false) %}
      {% set restart_hours = (server.config.restart_interval_hours if server else 4) or 4 %}
      {% set restart_start = (server.config.restart_start_hour if server else 0) or 0 %}
      {% set restart_warnings = (server.config.restart_warning_minutes|join(', ') if server and server.config.restart_warning_minutes else '30, 15, 10, 5, 1') %}
      {% set base_state = (server.config.base_damage_state if server else 'on') or 'on' %}
      {% set container_state = (server.config.container_damage_state if server else 'on') or 'on' %}
      {% set dmg = server.config.damage_schedule if server and server.config.damage_schedule else {} %}
      {% set dmg_enabled = dmg.enabled if dmg and dmg.enabled is defined else (server.config.damage_schedule_enabled if server else false) %}
      {% set dmg_first_date = (dmg.first_date or server.config.damage_first_date or '') if server else '' %}
      {% set dmg_time = (dmg.time or server.config.damage_time or '04:00') if server else '04:00' %}
      {% set dmg_timezone = (dmg.timezone or server.config.damage_timezone or 'Europe/Dublin') if server else 'Europe/Dublin' %}
      {% set dmg_interval_value = (dmg.interval_value or server.config.damage_interval_value or 7) if server else 7 %}
      {% set dmg_interval_unit = (dmg.interval_unit or server.config.damage_interval_unit or 'days') if server else 'days' %}
      {% set dmg_weekday = (dmg.day_of_week or server.config.damage_day_of_week or '') if server else '' %}
      {% set dmg_month_day = (dmg.day_of_month or server.config.damage_day_of_month or '') if server else '' %}
      {% set vr = server.config.vehicle_reset_schedule if server and server.config.vehicle_reset_schedule else {} %}
      {% set vr_enabled = server.config.vehicle_reset_schedule_enabled if server else false %}
      {% if vr and vr.enabled is defined %}
      {% set vr_enabled = vr.enabled %}
      {% endif %}
      {% set vr_first_date = (vr.first_date or server.config.vehicle_reset_first_date or '') if server else '' %}
      {% set vr_time = (vr.time or server.config.vehicle_reset_time or '04:00') if server else '04:00' %}
      {% set vr_timezone = (vr.timezone or server.config.vehicle_reset_timezone or 'Europe/Dublin') if server else 'Europe/Dublin' %}
      {% set vr_interval_value = (vr.interval_value or server.config.vehicle_reset_interval_value or 7) if server else 7 %}
      {% set vr_interval_unit = (vr.interval_unit or server.config.vehicle_reset_interval_unit or 'days') if server else 'days' %}
      {% set vr_weekday = (vr.day_of_week or server.config.vehicle_reset_day_of_week or '') if server else '' %}
      {% set vr_month_day = (vr.day_of_month or server.config.vehicle_reset_day_of_month or '') if server else '' %}
      {% set vr_method = (vr.method or server.config.vehicle_reset_method or 'cfgignorelist') if server else 'cfgignorelist' %}
      <div class="mini-grid" style="margin-bottom:1rem">
        <div class="mini-card"><span class="muted">Restart schedule</span><strong>{{ 'On' if restart_on else 'Off' }}</strong><span>Every {{ restart_hours }}h from {{ restart_start }}:00 UTC</span></div>
        <div class="mini-card"><span class="muted">Damage</span><strong>Base {{ base_state|title }} / Containers {{ container_state|title }}</strong><span>{{ 'Scheduled' if dmg_enabled else 'Manual toggles' }}{% if dmg_first_date %} from {{ dmg_first_date }} {{ dmg_time }}{% endif %}</span></div>
        <div class="mini-card"><span class="muted">Vehicle reset</span><strong>{{ 'On' if vr_enabled else 'Off' }}</strong><span>{{ vr_method|replace('_', ' ')|title }}{% if vr_first_date %} from {{ vr_first_date }} {{ vr_time }}{% endif %}</span></div>
        <div class="mini-card"><span class="muted">Repeat</span><strong>{{ vr_interval_value }} {{ vr_interval_unit }}</strong><span>{% if vr_weekday %}{{ vr_weekday|title }}{% elif vr_month_day %}Day {{ vr_month_day }}{% else %}From first date{% endif %}</span></div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Restart Schedule</h3>
          <form class="admin-form" method="post" action="/api/admin/server-control" data-route="/api/admin/server-control">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Restart schedule <select name="restart_schedule_enabled"><option value="true" {% if restart_on %}selected{% endif %}>On</option><option value="false" {% if not restart_on %}selected{% endif %}>Off</option></select></label>
            <label>Every hours <input name="restart_interval_hours" type="number" min="1" max="24" value="{{ restart_hours }}"></label>
            <label>Start hour UTC <input name="restart_start_hour" type="number" min="0" max="23" value="{{ restart_start }}"></label>
            <label>Warning minutes <input name="restart_warning_minutes" value="{{ restart_warnings|replace(' ', '') }}"></label>
            <label>Notify channel
              <select name="restart_channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if channel.key == 'restart' or channel.key == 'admin_logs' %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <div class="full"><button type="submit">Save Restart Schedule</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Damage Settings</h3>
          <form class="admin-form" method="post" action="/api/admin/server-control" data-route="/api/admin/server-control">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Base damage <select name="base_damage_state"><option value="on" {% if base_state != 'off' %}selected{% endif %}>On</option><option value="off" {% if base_state == 'off' %}selected{% endif %}>Off</option></select></label>
            <label>Container damage <select name="container_damage_state"><option value="on" {% if container_state != 'off' %}selected{% endif %}>On</option><option value="off" {% if container_state == 'off' %}selected{% endif %}>Off</option></select></label>
            <label>Schedule damage changes <select name="damage_schedule_enabled"><option value="false" {% if not dmg_enabled %}selected{% endif %}>Off</option><option value="true" {% if dmg_enabled %}selected{% endif %}>On</option></select></label>
            <label>First change date <input name="damage_first_date" type="date" value="{{ dmg_first_date }}"></label>
            <label>Change time <input name="damage_time" type="time" value="{{ dmg_time }}"></label>
            <label>Timezone <input name="damage_timezone" value="{{ dmg_timezone }}"></label>
            <label>Repeat every <input name="damage_interval_value" type="number" min="1" max="999" value="{{ dmg_interval_value }}"></label>
            <label>Repeat unit
              <select name="damage_interval_unit">
                <option value="hours" {% if dmg_interval_unit == 'hours' %}selected{% endif %}>Hours</option>
                <option value="days" {% if dmg_interval_unit == 'days' %}selected{% endif %}>Days</option>
                <option value="weeks" {% if dmg_interval_unit == 'weeks' %}selected{% endif %}>Weeks</option>
                <option value="months" {% if dmg_interval_unit == 'months' %}selected{% endif %}>Months</option>
              </select>
            </label>
            <label>Preferred weekday
              <select name="damage_day_of_week">
                <option value="">Use first date</option>
                {% for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] %}<option value="{{ day|lower }}" {% if dmg_weekday == day|lower %}selected{% endif %}>{{ day }}</option>{% endfor %}
              </select>
            </label>
            <label>Monthly day <input name="damage_day_of_month" type="number" min="1" max="31" value="{{ dmg_month_day }}" placeholder="optional"></label>
            <div class="full embed-preview"><strong>Current Damage Plan</strong><span>{{ 'Enabled' if dmg_enabled else 'Disabled' }}{% if dmg_first_date %}: {{ dmg_first_date }} {{ dmg_time }} {{ dmg_timezone }}{% endif %}, repeating every {{ dmg_interval_value }} {{ dmg_interval_unit }}.</span></div>
            <div class="full"><button type="submit">Save Damage Settings</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Vehicle Reset Schedule</h3>
          <form class="admin-form" method="post" action="/api/admin/server-control" data-route="/api/admin/server-control">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Schedule <select name="vehicle_reset_schedule_enabled"><option value="false" {% if not vr_enabled %}selected{% endif %}>Off</option><option value="true" {% if vr_enabled %}selected{% endif %}>On</option></select></label>
            <label>Method <select name="vehicle_reset_method"><option value="cfgignorelist" {% if vr_method != 'bridge' %}selected{% endif %}>cfgignorelist.xml vehicle-only reset</option><option value="bridge" {% if vr_method == 'bridge' %}selected{% endif %}>Bridge radius delete</option></select></label>
            <label>First reset date <input name="vehicle_reset_first_date" type="date" value="{{ vr_first_date }}"></label>
            <label>Reset time <input name="vehicle_reset_time" type="time" value="{{ vr_time }}"></label>
            <label>Timezone <input name="vehicle_reset_timezone" value="{{ vr_timezone }}"></label>
            <label>Repeat every <input name="vehicle_reset_interval_value" type="number" min="1" max="999" value="{{ vr_interval_value }}"></label>
            <label>Repeat unit
              <select name="vehicle_reset_interval_unit">
                <option value="hours" {% if vr_interval_unit == 'hours' %}selected{% endif %}>Hours</option>
                <option value="days" {% if vr_interval_unit == 'days' %}selected{% endif %}>Days</option>
                <option value="weeks" {% if vr_interval_unit == 'weeks' %}selected{% endif %}>Weeks</option>
                <option value="months" {% if vr_interval_unit == 'months' %}selected{% endif %}>Months</option>
              </select>
            </label>
            <label>Preferred weekday
              <select name="vehicle_reset_day_of_week">
                <option value="">Use first date</option>
                {% for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] %}<option value="{{ day|lower }}" {% if vr_weekday == day|lower %}selected{% endif %}>{{ day }}</option>{% endfor %}
              </select>
            </label>
            <label>Monthly day <input name="vehicle_reset_day_of_month" type="number" min="1" max="31" value="{{ vr_month_day }}" placeholder="optional"></label>
            <div class="full embed-preview"><strong>Current Reset</strong><span>{{ 'Enabled' if vr_enabled else 'Disabled' }}{% if vr_first_date %}: {{ vr_first_date }} {{ vr_time }} {{ vr_timezone }}{% endif %}, repeating every {{ vr_interval_value }} {{ vr_interval_unit }}. The default method stages vehicle classes in cfgignorelist.xml before the restart, waits for the server to return, restores the backup, then requests the restore restart.</span></div>
            <div class="full"><button type="submit">Save Vehicle Reset Schedule</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "help" %}
    <section class="section-panel" id="help">
      <div class="section-head">
        <div>
          <h2>Dashboard Help</h2>
          <p class="tool-note">A quick walkthrough for the controls admins ask about most often.</p>
        </div>
      </div>
      <div class="help-grid">
        <article class="help-card">
          <h3>PVE Airdrops</h3>
          <ol>
            <li>Use Saved location for common places, or type exact iZurvive X/Z coordinates.</li>
            <li>Use Batch locations when you want several drops with the same loot settings.</li>
            <li>One batch line should be name, X, Z, for example Skalisty Island, 13532, 3131.</li>
            <li>The dashboard saves the event immediately and asks the bot to upload native CE XML in the background.</li>
            <li>Console airdrops apply after server restart because they use events.xml, cfgeventspawns.xml, and eventgroups.xml.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Loot Scenes</h3>
          <ol>
            <li>Military high tier creates a crater-style scene with pristine weapons, clothing, ammo boxes, medical items, and grenades.</li>
            <li>Ammo and medical supplies are kept in crates where possible.</li>
            <li>Large weapons and bulky military gear are placed around the scene so small crates do not hide them.</li>
            <li>Extra loot items must be exact DayZ classnames separated by commas.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Visual Loadout</h3>
          <ol>
            <li>Search or filter items, then drag an item onto a body slot, weapon slot, or cargo box.</li>
            <li>Click a filled weapon slot to add attachment items to that weapon.</li>
            <li>Copy the generated loadout JSON for checking, or upload the package when the Nitrado paths are correct.</li>
            <li>custom_loadout.json and cfggameplay.json must both be present for DayZ spawn gear to work.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Zones</h3>
          <ol>
            <li>Open Zones and click the map to fill X/Z coordinates.</li>
            <li>Radar zones only send Discord alerts; Safe/PVP zones can notify, manhunt, or ban.</li>
            <li>Choose channel names from the picker where available so the dashboard avoids raw Discord IDs.</li>
            <li>Existing slash-command zones are loaded into the dashboard automatically.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>XML Safety</h3>
          <ol>
            <li>The guarded uploader keeps live files protected and writes one latest backup marker instead of flooding backups.</li>
            <li>Native CE XML uploads never need init.c access on console servers.</li>
            <li>Restart the server after CE XML changes so the economy reloads the new events.</li>
            <li>If an upload fails, the event row shows Retry XML only for failed events.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Dashboard Colours</h3>
          <ol>
            <li>Use the top colour circles to change the overall theme in this browser.</li>
            <li>Tool panels now use different accent colours so separate tools are easier to scan.</li>
            <li>The theme only changes dashboard colours, not bot behaviour or server files.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Servers & Login</h3>
          <ol>
            <li>Each server uses its own private dashboard ID and password.</li>
            <li>Use Link Another Server to add a second dashboard into the same login group.</li>
            <li>After linking, use the left rail picker or Linked Dashboard Servers cards to switch server.</li>
            <li>The selected server controls every form, upload, event, zone and shop edit on the page.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Red Gas Zones</h3>
          <ol>
            <li>Choose a red gas preset in PVE Event Builder, or set Gas particle to Red / debug gas.</li>
            <li>The bot updates cfgareaeffects.xml to use the contaminated_area_gas_bigass_debug particle.</li>
            <li>This can affect all gas zones that use that effect file, not only one location.</li>
            <li>Use Restore normal green if you want to switch the server back.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Discord Spawn Tracker</h3>
          <ol>
            <li>Native CE XML uploads tell Discord what files changed and where they were uploaded.</li>
            <li>The live spawn tracker updates after the next RPT pull sees the server restart or new spawns.</li>
            <li>If RPT cannot be pulled, the upload can still be complete, but Discord cannot confirm visible spawns yet.</li>
            <li>RPT warnings are shown in the deployment message so admins can see missing files or bad classnames.</li>
          </ol>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "access" %}
    <section class="section-panel" id="access">
      <div class="section-head">
        <div>
          <h2>Servers & Login</h2>
          <p class="tool-note">Link another server with that server's dashboard ID/password. After linking, use the server picker in the left rail to switch between them.</p>
        </div>
      </div>
      <div class="panel-grid">
        {% if auth.kind == "owner" %}
        <article class="admin-panel">
          <h3>Feature Access</h3>
          <form class="admin-form" method="post" action="/api/admin/guild-access" data-route="/api/admin/guild-access">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=access&guild_id={{ server.guild_id if server else '' }}#access">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Tier <select name="tier"><option value="owner">owner</option><option value="premium">premium</option><option value="trial">trial</option><option value="none">none</option></select></label>
            <label>Plan status
              <select name="plan_status">
                <option value="trial" {% if server and server.dashboard_access.plan_status == 'trial' %}selected{% endif %}>Trial</option>
                <option value="subscription" {% if server and server.dashboard_access.plan_status == 'subscription' %}selected{% endif %}>Subscription</option>
                <option value="lifetime" {% if server and server.dashboard_access.plan_status == 'lifetime' %}selected{% endif %}>Lifetime</option>
                <option value="suspended" {% if server and server.dashboard_access.plan_status == 'suspended' %}selected{% endif %}>Suspended</option>
                <option value="none" {% if server and server.dashboard_access.plan_status == 'none' %}selected{% endif %}>None</option>
              </select>
            </label>
            <label>Trial ends <input name="trial_ends_at" type="date" value="{{ server.dashboard_access.trial_ends_at if server else '' }}"></label>
            <label>Subscription ends <input name="subscription_ends_at" type="date" value="{{ server.dashboard_access.subscription_ends_at if server else '' }}"></label>
            <label>Daily trial notice
              <select name="trial_notice_enabled">
                <option value="true" {% if not server or server.dashboard_access.trial_notice_enabled %}selected{% endif %}>On</option>
                <option value="false" {% if server and not server.dashboard_access.trial_notice_enabled %}selected{% endif %}>Off</option>
              </select>
            </label>
            <label>Allowed role IDs <input name="allowed_role_ids" placeholder="optional Discord role IDs"></label>
            <label class="full">Owner note <input name="owner_note" value="{{ server.dashboard_access.owner_note if server else '' }}" placeholder="private note only you see"></label>
            <div class="full">
              <span class="muted">Enabled modules</span>
              {% set features = server.dashboard_access.features if server else {} %}
              <div class="check-grid">
                <label class="check"><input type="checkbox" name="feature_leaderboards" {% if features.leaderboards %}checked{% endif %}> Leaderboards</label>
                <label class="check"><input type="checkbox" name="feature_economy" {% if features.economy %}checked{% endif %}> Economy</label>
                <label class="check"><input type="checkbox" name="feature_factions" {% if features.factions %}checked{% endif %}> Factions</label>
                <label class="check"><input type="checkbox" name="feature_embeds" {% if features.embeds %}checked{% endif %}> Auto messages</label>
                <label class="check"><input type="checkbox" name="feature_safe_zones" {% if features.safe_zones %}checked{% endif %}> Radar zones</label>
                <label class="check"><input type="checkbox" name="feature_members" {% if features.members %}checked{% endif %}> Member actions</label>
                <label class="check"><input type="checkbox" name="feature_heatmaps" {% if features.heatmaps %}checked{% endif %}> Heatmaps</label>
                <label class="check"><input type="checkbox" name="feature_pve_quests" {% if features.pve_quests %}checked{% endif %}> PVE quests</label>
                <label class="check"><input type="checkbox" name="feature_quest_workshop" {% if features.quest_workshop %}checked{% endif %}> Quest workshop</label>
                <label class="check"><input type="checkbox" name="feature_shop" {% if features.shop %}checked{% endif %}> Shop control</label>
                <label class="check"><input type="checkbox" name="feature_xml_workshop" {% if features.xml_workshop %}checked{% endif %}> XML workshop</label>
                <label class="check"><input type="checkbox" name="feature_server_rules" {% if features.server_rules %}checked{% endif %}> Server rules</label>
                <label class="check"><input type="checkbox" name="feature_server_control" {% if features.server_control %}checked{% endif %}> Server control</label>
                <label class="check"><input type="checkbox" name="feature_wages" {% if features.wages %}checked{% endif %}> Economy wages</label>
              </div>
            </div>
            <div class="full"><button type="submit">Save Access</button> <span class="result muted"></span></div>
          </form>
        </article>
        {% endif %}
        <article class="admin-panel">
          <h3>Link Another Server</h3>
          <form class="admin-form" method="post" action="/api/admin/link-server" data-route="/api/admin/link-server">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=access&guild_id={{ server.guild_id if server else '' }}#linked-servers">
            <div class="server-lock"><span>Current dashboard group</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Other dashboard ID <input name="dashboard_id" autocomplete="off" placeholder="private dashboard id"></label>
            <label>Other dashboard password <input name="password" type="password" autocomplete="new-password" placeholder="private dashboard password"></label>
            <div class="full"><button type="submit">Link Server</button> <span class="result muted"></span></div>
          </form>
          <p class="tool-note" style="margin-top:.75rem">This verifies the other server's private dashboard login before it appears in this dashboard group.</p>
        </article>
        <article class="admin-panel full" id="linked-servers">
          <h3>Linked Dashboard Servers</h3>
          <p class="tool-note">Switch between every server available to this dashboard login. The active card controls which server every page edits.</p>
          <div class="command-server-grid">
            {% for item in servers %}
            <a class="command-server-card {{ 'active' if server and item.guild_id == server.guild_id else '' }}" href="/{{ 'owner' if mode == 'owner' else 'admin' }}?section=access&guild_id={{ item.guild_id }}#linked-servers">
              <strong>{{ item.guild_name }}</strong>
              <small>{{ item.platform_label }} server on {{ item.map|capitalize }}.</small>
              <div class="pills">
                <span class="pill {{ 'ok' if item.active else 'bad' }}">{{ 'online config' if item.active else 'inactive' }}</span>
                <span class="pill">{{ item.dashboard_access.plan_status or item.dashboard_access.tier or 'dashboard' }}</span>
                <span class="pill">{{ item.channels|length }} channels</span>
              </div>
            </a>
            {% else %}
            <div class="notification"><strong>No linked servers yet</strong><span>Link another dashboard ID/password above to make it appear here.</span></div>
            {% endfor %}
          </div>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode == "owner" and active_section == "overview" %}
    <section class="wide card">
      <h2>Owner Console</h2>
      <div class="owner-grid">
        <div class="owner-tile"><span class="muted">Active guilds</span><strong>{{ summary.guilds }}</strong></div>
        <div class="owner-tile"><span class="muted">Dashboard enabled</span><strong>{{ summary.dashboard_enabled }}</strong></div>
        <div class="owner-tile"><span class="muted">Admin routes</span><strong>{{ admin_routes|length }}</strong></div>
      </div>
      <table class="table">
        <thead><tr><th>Server</th><th>Server ID</th><th>Map</th><th>Channels</th><th>Plan</th><th>Access</th></tr></thead>
        <tbody>
          {% for server in servers %}
          <tr><td>{{ server.guild_name }}</td><td>{{ server.guild_id }}</td><td>{{ server.map }}</td><td>{{ server.channels|length }}</td><td>{{ server.dashboard_access.plan_status }}</td><td>{{ 'admin enabled' if server.dashboard_access.enabled else 'admin locked, owner override active' }}</td></tr>
          {% endfor %}
        </tbody>
      </table>
      <h3>Routes</h3>
      <div class="route-list">
        {% for route in all_routes %}<code>{{ route }}</code>{% endfor %}
      </div>
    </section>
    {% endif %}

    {% if active_section == "overview" %}
    <section class="grid">
      <article class="card"><h3>Economy</h3><p class="muted">{{ summary.wallets }} wallets, {{ summary.delivery_queue }} queued deliveries and {{ summary.wages }} active wages.</p></article>
      <article class="card"><h3>Automations</h3><p class="muted">{{ summary.embed_templates }} message templates, {{ summary.welcome_automations }} welcomes, {{ summary.utility_configs }} utilities and {{ summary.reaction_role_panels }} role panels.</p></article>
      <article class="card"><h3>Access</h3><p class="muted">{{ 'This dashboard is enabled.' if summary.dashboard_enabled else 'This dashboard is locked.' }}</p></article>
    </section>

    <section class="servers">
      {% for server in servers %}
      <article class="card">
        <div class="server-head">
          <div>
            <h2>{{ server.guild_name }}</h2>
            <div class="pills">
              <span class="pill">Server ID {{ server.guild_id }}</span>
              <span class="pill {{ 'ok' if server.active else 'bad' }}">{{ 'active' if server.active else 'inactive' }}</span>
              <span class="pill {{ 'ok' if server.dashboard_access.enabled else 'bad' }}">Admin dashboard {{ 'enabled' if server.dashboard_access.enabled else 'locked' }}</span>
              <span class="pill">{{ server.map|upper }}</span>
            </div>
          </div>
        </div>
        <div class="columns">
          <section><h3>Online</h3><ul>{% for player in server.online[:6] %}<li><span>{{ player }}</span><span>online</span></li>{% else %}<li>No survivors online</li>{% endfor %}</ul></section>
          <section><h3>Leaders</h3><ul>{% for leader in server.leaders[:6] %}<li><span>{{ leader.name }}</span><span>{{ leader.kills }}</span></li>{% else %}<li>No stats yet</li>{% endfor %}</ul></section>
          <section><h3>Channels</h3><ul>{% for channel in server.channels[:6] %}<li><span>{{ channel.label }}</span><span>{{ channel.key or channel.name or 'live channel' }}</span></li>{% else %}<li>No channels found</li>{% endfor %}</ul></section>
          <section><h3>Totals</h3><ul><li><span>Kills</span><span>{{ server.totals.kills }}</span></li><li><span>Deaths</span><span>{{ server.totals.deaths }}</span></li><li><span>Safe zones</span><span>{{ server.safe_zones|length }}</span></li><li><span>Factions</span><span>{{ server.factions|length }}</span></li></ul></section>
        </div>
      </article>
      {% else %}
      <article class="card"><h2>No guilds configured</h2><p class="muted">Run the Discord setup flow, then refresh this dashboard.</p></article>
      {% endfor %}
    </section>
    {% endif %}
  </main>
  <div class="command-status-bar" aria-label="Command connection status">
    <span>UK Time: <strong>{{ generated_at }}</strong></span>
    <span>Version: <strong>1.26</strong></span>
    <span>Platform: <strong>{{ server.platform_label if server else 'Xbox' }}</strong></span>
    <span>Map: <strong>{{ server.map|capitalize if server else 'Chernarus' }}</strong></span>
    <span><span class="ok">Database: Connected</span> | <span class="ok">Nitrado: Connected</span></span>
    <span>Players: <strong>{{ summary.online }}/{{ summary.players }}</strong></span>
  </div>
  <script>
    const DASHBOARD_PUBLIC_URL = "{{ public_url }}";
    const DASHBOARD_THEME = "{{ dashboard_theme }}";
    const ITEM_LOOKUP = {{ (server.shop_items if server and active_section in ["shop", "xml-workshop", "loot-engine", "visual-loadout", "bulk-economy"] else [])|tojson }};
    const XML_PICKER_GROUPS = {{ xml_picker_groups|tojson }};
    const VISUAL_LOADOUT_DRAFT = {{ visual_loadout_draft|tojson }};
    const DEFAULT_LOADOUT_SLOT = "Head";
    document.body.dataset.section = "{{ active_section }}";
    function secureDashboardUrl(path) {
      const fallback = window.location.origin;
      const base = DASHBOARD_PUBLIC_URL || fallback;
      try {
        const url = new URL(path || window.location.href, base);
        if (!["localhost", "127.0.0.1", "0.0.0.0"].includes(url.hostname)) url.protocol = "https:";
        return url.toString();
      } catch (error) {
        return path;
      }
    }
    function installDashboardCoreClicks() {
      if (window.__wanderingDashboardCoreClicks) return;
      window.__wanderingDashboardCoreClicks = true;
      function stop(event) {
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      }
      function parseJson(text) {
        try { return JSON.parse(text || "{}"); } catch (error) { return {}; }
      }
      function readJsonScript(root, selector) {
        const script = root ? root.querySelector(selector) : null;
        return script ? parseJson(script.textContent) : {};
      }
      function setControl(form, name, value) {
        if (!form || !form.elements[name]) return;
        const control = form.elements[name];
        const controls = typeof control.length === "number" && !control.tagName ? Array.from(control) : [control];
        controls.forEach((item) => {
          if (!item) return;
          if (item.type === "checkbox") item.checked = Boolean(value);
          else if (item.tagName === "SELECT") {
            const wanted = String(value ?? "");
            const option = Array.from(item.options || []).find((entry) => entry.value === wanted || entry.dataset.channelId === wanted);
            item.value = option ? option.value : wanted;
            item.dispatchEvent(new Event("change", {bubbles: true}));
          } else {
            item.value = value ?? "";
            item.dispatchEvent(new Event("input", {bubbles: true}));
          }
        });
      }
      function scrollToForm(form) {
        if (!form) return;
        form.classList.add("dashboard-edit-modal");
        form.scrollIntoView({behavior: "smooth", block: "center"});
        const first = form.querySelector('input:not([type="hidden"]), select, textarea');
        if (first) first.focus({preventScroll: true});
      }
      function embedFieldsToLines(fields) {
        if (!Array.isArray(fields)) return "";
        return fields.map((field) => {
          const name = String(field && field.name || "").replace(/[|]/g, "/");
          const value = String(field && field.value || "").replace(/[|]/g, "/");
          const inline = field && field.inline ? "true" : "false";
          return `${name} | ${value} | ${inline}`;
        }).filter((line) => line.trim()).join("\n");
      }
      function fillEmbedTemplateForm(template) {
        const form = document.getElementById("embed-template-form");
        if (!form || !template || !Object.keys(template).length) return false;
        const embed = template.embed || {};
        const delivery = template.delivery || {};
        const schedule = template.schedule || {};
        setControl(form, "name", template.name || "custom-message");
        setControl(form, "template_id", template.template_id || template.id || "");
        setControl(form, "content_mode", delivery.content_mode || template.content_mode || "embed");
        setControl(form, "channel_key", delivery.channel_key || template.channel_key || "");
        setControl(form, "title", embed.title || template.title || "");
        setControl(form, "colour", embed.colour || embed.color || template.colour || "#8d963e");
        setControl(form, "author_name", (embed.author && embed.author.name) || template.author_name || "");
        setControl(form, "author_icon_url", (embed.author && embed.author.icon_url) || template.author_icon_url || "");
        setControl(form, "thumbnail_url", embed.thumbnail_url || template.thumbnail_url || "");
        setControl(form, "image_url", embed.image_url || template.image_url || "");
        setControl(form, "footer_text", (embed.footer && embed.footer.text) || template.footer_text || "");
        setControl(form, "footer_icon_url", (embed.footer && embed.footer.icon_url) || template.footer_icon_url || "");
        setControl(form, "mention_mode", delivery.mention_mode || template.mention_mode || "none");
        setControl(form, "mention_role_id", delivery.mention_role_id || template.mention_role_id || "");
        setControl(form, "schedule_type", schedule.type || template.schedule_type || "manual");
        setControl(form, "schedule_time", schedule.time || template.schedule_time || "");
        setControl(form, "event_filter", schedule.event_filter || template.event_filter || "");
        setControl(form, "event_minimum", schedule.event_minimum ?? template.event_minimum ?? 0);
        setControl(form, "interval_minutes", schedule.interval_minutes ?? template.interval_minutes ?? 60);
        setControl(form, "timezone", schedule.timezone || template.timezone || "Europe/Dublin");
        setControl(form, "button_label", delivery.button_label || template.button_label || "");
        setControl(form, "button_url", delivery.button_url || template.button_url || "");
        setControl(form, "body", embed.description || template.body || "");
        setControl(form, "fields_lines", embedFieldsToLines(embed.fields));
        scrollToForm(form);
        const result = form.querySelector(".result");
        if (result) result.textContent = "Loaded for editing.";
        return true;
      }
      function fillDashboardRecordForm(formId, record) {
        const form = document.getElementById(formId || "");
        if (!form || !record || !Object.keys(record).length) return false;
        Object.entries(record).forEach(([key, value]) => {
          if (value && typeof value === "object") return;
          setControl(form, key, value);
        });
        scrollToForm(form);
        const result = form.querySelector(".result");
        if (result) result.textContent = "Loaded for editing.";
        return true;
      }
      function zoneKey(zone) {
        return String((zone && (zone.id || zone.name)) || "");
      }
      function zoneFromControl(control) {
        if (!control) return {};
        const rowScript = control.closest("[data-zone-row]")?.querySelector("[data-zone-json]");
        if (rowScript) return parseJson(rowScript.textContent);
        const key = control.dataset.zoneKey || "";
        if (key) {
          const scripts = Array.from(document.querySelectorAll("[data-zone-json]"));
          const script = scripts.find((item) => String(item.dataset.zoneKey || "") === String(key));
          if (script) return parseJson(script.textContent);
        }
        return parseJson(control.dataset.zone || "{}");
      }
      function showZoneFallbackPopover(map, zone, form) {
        const popover = map ? map.querySelector("[data-zone-popover]") : null;
        if (!popover) return;
        const size = Number(map.dataset.mapSize || 15360);
        const x = Number(zone.x ?? zone.center_x ?? form?.elements.x?.value ?? 0);
        const z = Number(zone.z ?? zone.y ?? zone.center_z ?? zone.center_y ?? form?.elements.y?.value ?? 0);
        const xPercent = Math.max(2, Math.min(98, (x / size) * 100));
        const yPercent = Math.max(8, Math.min(92, 100 - ((z / size) * 100)));
        const radius = zone.radius ?? zone.radius_m ?? form?.elements.radius?.value ?? 250;
        popover.style.left = `${xPercent}%`;
        popover.style.top = `${yPercent}%`;
        popover.dataset.side = xPercent > 62 ? "left" : "right";
        popover.innerHTML = `
          <strong>${String(zone.name || "Zone").replace(/[&<>"']/g, "")}</strong>
          <span>${String(zone.zone_type || zone.type || "radar")} zone - X ${Math.round(x)}, Z ${Math.round(z)} - radius ${radius}m</span>
          <div class="zone-popover-actions">
            <button type="button" data-zone-popover-save>Save Changes</button>
            <button type="button" data-zone-delete data-zone-key="${String(zoneKey(zone)).replace(/"/g, "&quot;")}" data-zone-id="${String(zone.id || "").replace(/"/g, "&quot;")}" data-zone-type="${String(zone.zone_type || zone.type || "").replace(/"/g, "&quot;")}" data-zone-name="${String(zone.name || "").replace(/"/g, "&quot;")}" data-guild-id="${String(form?.elements.guild_id?.value || "").replace(/"/g, "&quot;")}">Delete</button>
            <button type="button" data-zone-popover-close>Close</button>
          </div>`;
        popover.hidden = false;
      }
      function fillZoneForm(zone, source) {
        const form = document.getElementById("zone-edit-form");
        if (!form || !zone || !Object.keys(zone).length) return false;
        setControl(form, "zone_id", zone.id || zone.name || "");
        setControl(form, "name", zone.name || "");
        setControl(form, "zone_type", zone.zone_type || zone.type || "radar");
        setControl(form, "x", Number(zone.x ?? zone.center_x ?? 0));
        setControl(form, "y", Number(zone.z ?? zone.y ?? zone.center_z ?? zone.center_y ?? 0));
        setControl(form, "shape", zone.shape || "circle");
        setControl(form, "radius", zone.radius ?? zone.radius_m ?? 250);
        setControl(form, "radius_slider", zone.radius ?? zone.radius_m ?? 250);
        setControl(form, "channel_key", zone.channel_key || zone.alert_channel_id || zone.report_channel_id || "");
        setControl(form, "role_id", zone.role_id || zone.mention_role_id || "");
        setControl(form, "faction_name", zone.faction_name || zone.faction || "");
        setControl(form, "colour", zone.display_colour || source?.dataset.zoneColour || zone.colour || zone.color || "#8d963e");
        setControl(form, "enabled", zone.enabled === false ? "false" : "true");
        setControl(form, "action", zone.action || "none");
        setControl(form, "ban_type", zone.ban_type || "temp");
        setControl(form, "ban_duration_minutes", zone.ban_duration_minutes || 1440);
        setControl(form, "trigger_territory", zone.trigger_territory || "inside");
        setControl(form, "triggers", Array.isArray(zone.triggers) ? zone.triggers.join(",") : (zone.triggers || ""));
        setControl(form, "ignored_gamertags", Array.isArray(zone.ignored_gamertags) ? zone.ignored_gamertags.join(",") : (zone.ignored_gamertags || ""));
        const save = form.querySelector("[data-zone-save-button]");
        const remove = form.querySelector("[data-zone-delete-current]");
        const readout = form.querySelector("[data-map-readout]");
        if (save) save.textContent = "Save Zone Changes";
        if (remove) remove.disabled = false;
        if (readout) readout.textContent = `Editing ${zone.name || "zone"} - save to update this radar/zone.`;
        document.querySelectorAll("[data-zone-edit].editing").forEach((item) => item.classList.remove("editing"));
        document.querySelectorAll("[data-zone-edit]").forEach((item) => {
          if (item.dataset.zoneKey && item.dataset.zoneKey === (source?.dataset.zoneKey || zoneKey(zone))) item.classList.add("editing");
        });
        const map = source && source.closest("[data-zone-map]");
        if (map) showZoneFallbackPopover(map, zone, form);
        else scrollToForm(form);
        return true;
      }
      async function postJson(route, payload) {
        const token = new URLSearchParams(window.location.search).get("token");
        const target = token ? `${route}?token=${encodeURIComponent(token)}` : route;
        const response = await fetch(secureDashboardUrl(target), {
          method: "POST",
          headers: {"Content-Type": "application/json", "Accept": "application/json", "X-Requested-With": "fetch"},
          credentials: "same-origin",
          body: JSON.stringify(payload),
        });
        let body = {};
        try { body = await response.json(); } catch (error) {}
        if (!response.ok || body.ok === false) throw new Error(body.error || "Request rejected.");
        return body;
      }
      document.addEventListener("click", async (event) => {
        const popoverClose = event.target.closest("[data-zone-popover-close]");
        if (popoverClose) {
          stop(event);
          const popover = popoverClose.closest("[data-zone-popover]");
          if (popover) popover.hidden = true;
          return;
        }
        const popoverSave = event.target.closest("[data-zone-popover-save]");
        if (popoverSave) {
          stop(event);
          const form = document.getElementById("zone-edit-form");
          if (form && form.requestSubmit) form.requestSubmit(form.querySelector("[data-zone-save-button]") || undefined);
          else form?.querySelector("[data-zone-save-button]")?.click();
          return;
        }
        const embedEdit = event.target.closest("[data-embed-template-edit]");
        if (embedEdit) {
          if (!fillEmbedTemplateForm(readJsonScript(embedEdit.closest("[data-embed-template-card]"), "[data-embed-template-json]"))) return;
          stop(event);
          return;
        }
        const recordEdit = event.target.closest("[data-dashboard-record-edit]");
        if (recordEdit) {
          if (!fillDashboardRecordForm(recordEdit.dataset.formId, readJsonScript(recordEdit.closest("[data-dashboard-record-card]"), "[data-dashboard-record-json]"))) return;
          stop(event);
          return;
        }
        const zoneEdit = event.target.closest("[data-zone-edit]");
        if (zoneEdit) {
          return;
        }
        const embedDelete = event.target.closest("[data-embed-template-delete]");
        if (embedDelete) {
          if (embedDelete.closest("form")) return;
          stop(event);
          if (embedDelete.dataset.confirm && !window.confirm(embedDelete.dataset.confirm)) return;
          const card = embedDelete.closest("[data-embed-template-card]");
          await postJson("/api/admin/embed-template-action", {
            action: "delete",
            template_id: embedDelete.dataset.templateId || card?.dataset.templateId || "",
            guild_id: embedDelete.dataset.guildId || "{{ server.guild_id if server else '' }}",
            dashboard_mode: "{{ mode }}",
          });
          if (card) card.remove();
          return;
        }
        const recordDelete = event.target.closest("[data-dashboard-record-delete]");
        if (recordDelete) {
          if (recordDelete.closest("form")) return;
          stop(event);
          if (recordDelete.dataset.confirm && !window.confirm(recordDelete.dataset.confirm)) return;
          const card = recordDelete.closest("[data-dashboard-record-card]");
          await postJson("/api/admin/dashboard-record-action", {
            action: "delete",
            section: recordDelete.dataset.section || card?.dataset.section || "",
            record_id: recordDelete.dataset.recordId || card?.dataset.recordId || "",
            guild_id: recordDelete.dataset.guildId || "{{ server.guild_id if server else '' }}",
            dashboard_mode: "{{ mode }}",
          });
          if (card) card.remove();
          return;
        }
        const zoneDelete = event.target.closest("[data-zone-delete]");
        if (zoneDelete) {
          if (zoneDelete.closest("form")) return;
          stop(event);
          const zone = zoneFromControl(zoneDelete);
          const name = zoneDelete.dataset.zoneName || zone.name || "this zone";
          if (!window.confirm(`Delete ${name} from this server?`)) return;
          const form = document.getElementById("zone-edit-form");
          await postJson("/api/admin/zone-action", {
            action: "delete",
            guild_id: zoneDelete.dataset.guildId || form?.elements.guild_id?.value || "{{ server.guild_id if server else '' }}",
            zone_id: zoneDelete.dataset.zoneId || zone.id || form?.elements.zone_id?.value || "",
            zone_type: zoneDelete.dataset.zoneType || zone.zone_type || zone.type || form?.elements.zone_type?.value || "",
            name,
            dashboard_mode: "{{ mode }}",
          });
          const row = zoneDelete.closest("[data-zone-row]");
          if (row) row.remove();
          else window.location.reload();
        }
      }, true);
    }
    installDashboardCoreClicks();
    const DIRECT_DASHBOARD_SAVE_ROUTES = {
      "/api/admin/embed-template": {bodyKey: "template", message: "Saved embed template."},
      "/api/admin/welcome-automation": {bodyKey: "automation", message: "Saved welcome automation."},
      "/api/admin/utility-config": {bodyKey: "utility", message: "Saved utility module."},
      "/api/admin/reaction-role-panel": {bodyKey: "panel", message: "Saved reaction role panel."},
    };
    function directDashboardValue(value) {
      if (value === "true") return true;
      if (value === "false") return false;
      if (value !== "" && /^-?\\d+(\\.\\d+)?$/.test(value)) return Number(value);
      return value;
    }
    function directDashboardPayload(form) {
      const payload = {};
      new FormData(form).forEach((value, key) => {
        if (value === "") return;
        const parsed = directDashboardValue(value);
        if (payload[key] !== undefined) {
          payload[key] = Array.isArray(payload[key]) ? payload[key].concat([parsed]) : [payload[key], parsed];
        } else {
          payload[key] = parsed;
        }
      });
      payload.dashboard_mode = "{{ mode }}";
      return payload;
    }
    function directDashboardResult(form, message, failed) {
      const result = form ? form.querySelector(".result") : null;
      if (!result) return;
      result.textContent = message || "";
      result.classList.toggle("error", !!failed);
      result.classList.toggle("success", !failed && !!message);
    }
    function directDashboardFallbackTitle(routePath, record) {
      if (routePath === "/api/admin/embed-template") return record?.template_id || record?.name || "embed template";
      if (routePath === "/api/admin/welcome-automation") return record?.name || record?.automation_id || "welcome automation";
      if (routePath === "/api/admin/utility-config") return record?.module || record?.name || "utility module";
      if (routePath === "/api/admin/reaction-role-panel") return record?.name || record?.panel_id || "reaction role panel";
      return record?.name || "saved record";
    }
    function directDashboardFallbackList(routePath) {
      if (routePath === "/api/admin/embed-template") return document.querySelector("[data-embed-template-list]");
      const sectionByRoute = {
        "/api/admin/welcome-automation": "welcome_automations",
        "/api/admin/utility-config": "utility_configs",
        "/api/admin/reaction-role-panel": "reaction_role_panels",
      };
      const section = sectionByRoute[routePath];
      return section ? document.querySelector(`[data-dashboard-record-list][data-section="${section}"]`) : null;
    }
    function directDashboardFallbackUpsert(routePath, record, form) {
      if (!record) return;
      if (routePath === "/api/admin/embed-template" && typeof upsertEmbedTemplateCard === "function") {
        upsertEmbedTemplateCard(record, form);
        return;
      }
      const directRecordRoutes = {
        "/api/admin/welcome-automation": {section: "welcome_automations"},
        "/api/admin/utility-config": {section: "utility_configs"},
        "/api/admin/reaction-role-panel": {section: "reaction_role_panels"},
      };
      const dashboardRecordRoute = directRecordRoutes[routePath];
      if (dashboardRecordRoute && typeof upsertDashboardRecordCard === "function") {
        upsertDashboardRecordCard(dashboardRecordRoute.section, record, form);
        return;
      }
      const list = directDashboardFallbackList(routePath);
      if (!list) return;
      list.querySelectorAll("[data-empty-embed-templates], [data-empty-dashboard-records]").forEach((empty) => empty.remove());
      const card = document.createElement("div");
      card.className = "notification";
      const title = document.createElement("strong");
      title.textContent = directDashboardFallbackTitle(routePath, record);
      const summary = document.createElement("span");
      summary.textContent = "Saved for this server.";
      card.append(title, summary);
      list.prepend(card);
    }
    async function wanderingDashboardSubmit(form, event) {
      if (event) {
        event.preventDefault();
        if (event.stopPropagation) event.stopPropagation();
      }
      const routePath = String(form?.dataset?.route || "").split("?")[0];
      const routeInfo = DIRECT_DASHBOARD_SAVE_ROUTES[routePath];
      if (!form || !routeInfo) return false;
      if (form.dataset.directSaving === "1") return false;
      if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return false;
      const button = event?.submitter || form.querySelector('button[type="submit"]');
      const originalButtonText = button ? button.textContent : "";
      form.dataset.directSaving = "1";
      directDashboardResult(form, "Saving...", false);
      if (button) {
        button.disabled = true;
        button.textContent = "Saving...";
      }
      const token = new URLSearchParams(window.location.search).get("token");
      const route = token ? `${form.dataset.route}?token=${encodeURIComponent(token)}` : form.dataset.route;
      try {
        const response = await fetch(secureDashboardUrl(route), {
          method: "POST",
          headers: {"Content-Type": "application/json", "Accept": "application/json", "X-Requested-With": "fetch"},
          credentials: "same-origin",
          body: JSON.stringify(directDashboardPayload(form)),
        });
        let body = {};
        try { body = await response.json(); } catch (error) {}
        if (!response.ok) {
          directDashboardResult(form, body.error || "Save rejected.", true);
          return false;
        }
        const record = body[routeInfo.bodyKey];
        directDashboardFallbackUpsert(routePath, record, form);
        directDashboardResult(form, body.note || routeInfo.message || "Saved.", false);
      } catch (error) {
        directDashboardResult(form, `Save failed: ${error && error.message ? error.message : error}`, true);
      } finally {
        delete form.dataset.directSaving;
        if (button) {
          button.disabled = false;
          button.textContent = originalButtonText;
        }
      }
      return false;
    }
    window.wanderingDashboardSubmit = wanderingDashboardSubmit;
    document.addEventListener("submit", (event) => {
      if (event.submitter && event.submitter.matches && event.submitter.matches("[data-zone-map-hit]")) return;
      const form = event.target && event.target.closest ? event.target.closest(".admin-form") : null;
      const routePath = String(form?.dataset?.route || "").split("?")[0];
      if (!DIRECT_DASHBOARD_SAVE_ROUTES[routePath]) return;
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      wanderingDashboardSubmit(form, event);
    }, true);
    if (window.location.protocol === "http:" && !["localhost", "127.0.0.1", "0.0.0.0"].includes(window.location.hostname)) {
      window.location.replace(secureDashboardUrl(window.location.pathname + window.location.search + window.location.hash));
    }
    function applyTheme(theme) {
      const safeTheme = "command";
      document.documentElement.dataset.theme = safeTheme === "default" ? "" : safeTheme;
      document.body.dataset.theme = safeTheme === "default" ? "" : safeTheme;
      document.querySelectorAll("[data-theme-choice]").forEach((button) => {
        button.classList.toggle("active", button.dataset.themeChoice === safeTheme);
      });
      document.querySelectorAll("[data-theme-select]").forEach((select) => {
        select.value = safeTheme;
      });
    }
    const itemLookup = new Map((ITEM_LOOKUP || []).map((item) => [String(item.name || "").toLowerCase(), item]));
    function itemInfo(name) {
      return itemLookup.get(String(name || "").trim().toLowerCase()) || {};
    }
    function fallbackThumb(category) {
      return `/item-thumb/${encodeURIComponent(category || "General")}`;
    }
    const LOADOUT_SLOT_TERMS = {
      "Head": {include: ["helmet", "cap", "beanie", "beret", "ushanka", "boonie", "cowboyhat", "leatherhat", "baseballcap", "zsh3", "mich", "headtorch"], exclude: ["armband", "mask", "glove", "pants", "boots", "bag", "vest"]},
      "Eyes": {include: ["glasses", "eyewear", "nvg", "goggles"], exclude: ["armband", "mask", "helmet", "pants", "boots", "bag"]},
      "Mask": {include: ["mask", "respirator", "bandana", "balaclava", "shemag", "airborne"], exclude: ["armband", "glove", "pants", "boots", "bag"]},
      "Body": {include: ["jacket", "shirt", "hoodie", "coat", "torso", "sweater", "parka", "gorka", "nbcjacket", "bdujacket", "ttskojacket"], exclude: ["armband", "mask", "pants", "boots", "glove", "bag", "vest"]},
      "Vest": {include: ["vest", "platecarrier", "chestholster", "smershvest"], exclude: ["armband", "mask", "pants", "boots", "glove", "bag"]},
      "Back": {include: ["bag", "backpack", "drybag", "alicebag", "mountainbag", "taloonbag", "courierbag", "burlapsack", "improvisedbag"], exclude: ["armband", "mask", "pants", "boots", "glove"]},
      "Hips": {include: ["belt", "holster", "sheath", "fanny"], exclude: ["armband", "mask", "pants", "boots", "bag", "vest"]},
      "Legs": {include: ["pants", "trousers", "jeans", "shorts", "skirt", "cargo"], exclude: ["armband", "mask", "glove", "boots", "bag", "vest"]},
      "Feet": {include: ["boots", "shoes", "sneakers", "wellies", "footwraps"], exclude: ["armband", "mask", "glove", "pants", "bag", "vest", "helmet"]},
      "Hands": {include: ["weapon", "rifle", "gun", "pistol", "shotgun", "smg", "akm", "ak74", "ak101", "m4a1", "mosin", "sks", "svd", "fal", "aug", "vss", "crossbow", "knife", "axe", "hatchet", "hammer", "shovel", "saw", "wrench", "pickaxe", "tool"], exclude: ["armband", "mask", "pants", "boots", "bag", "vest"]},
      "Left Shoulder": {include: ["weapon", "rifle", "gun", "shotgun", "smg", "akm", "ak74", "ak101", "m4a1", "mosin", "sks", "svd", "fal", "aug", "vss", "crossbow"], exclude: ["mag_", "ammo", "armband", "mask", "pants", "boots", "bag", "vest"]},
      "Right Shoulder": {include: ["weapon", "rifle", "gun", "shotgun", "smg", "akm", "ak74", "ak101", "m4a1", "mosin", "sks", "svd", "fal", "aug", "vss", "crossbow"], exclude: ["mag_", "ammo", "armband", "mask", "pants", "boots", "bag", "vest"]},
      "Gloves": {include: ["glove", "gloves"], exclude: ["armband", "mask", "pants", "boots", "bag", "vest"]},
      "Armband": {include: ["armband"], exclude: ["mask", "glove", "pants", "boots", "bag", "vest"]},
    };
    const LOADOUT_SLOT_PICKERS = {
      Headgear: "Head",
      Mask: "Mask",
      Glasses: "Eyes",
      Torso: "Body",
      Vest: "Vest",
      Gloves: "Gloves",
      Legs: "Legs",
      Feet: "Feet",
      Backpack: "Back",
      Shoulder1: "Left Shoulder",
      Shoulder2: "Right Shoulder",
      Belt: "Hips",
      Holster: "Hands"
    };
    function itemSearchText(item) {
      return `${item?.name || ""} ${item?.category || ""}`.toLowerCase();
    }
    function strictSlotMatches(item, slot) {
      const rules = LOADOUT_SLOT_TERMS[slot];
      if (!rules) return true;
      const text = itemSearchText(item);
      return rules.include.some((term) => text.includes(term)) && !rules.exclude.some((term) => text.includes(term));
    }
    function slotFilteredItems(slot) {
      const rules = LOADOUT_SLOT_TERMS[slot];
      const slotItems = XML_PICKER_GROUPS[slot] || [];
      const allItems = XML_PICKER_GROUPS.all || ITEM_LOOKUP || [];
      if (!rules) return slotItems.length ? slotItems : (XML_PICKER_GROUPS.cargo || allItems || []);
      const strictSlotItems = slotItems.filter((item) => strictSlotMatches(item, slot));
      if (strictSlotItems.length) return strictSlotItems;
      const strictAllItems = allItems.filter((item) => strictSlotMatches(item, slot));
      if (strictAllItems.length) return strictAllItems;
      return [];
    }
    function selectedPickerSlot(slot) {
      if (!slot) return "Head";
      if (String(slot).startsWith("cargo:")) return "";
      return LOADOUT_SLOT_PICKERS[slot] || slot;
    }
    function normaliseLoadoutCandidate(item) {
      const classname = String(item?.classname || item?.name || "").trim();
      return {
        ...item,
        classname,
        readable: String(item?.readable || item?.label || item?.name || classname).trim(),
        category: String(item?.category || "Misc").trim() || "Misc"
      };
    }
    function selectedLoadoutItems(slot) {
      if (String(slot || "").startsWith("cargo:")) {
        const cargoItems = LOADOUT_DB.filter((item) => !PLAYER_CARGO_NAMES.size || PLAYER_CARGO_NAMES.has(item.classname));
        return cargoItems.map(normaliseLoadoutCandidate);
      }
      return slotFilteredItems(selectedPickerSlot(slot)).map(normaliseLoadoutCandidate);
    }
    function pickerGroupItems(groupName, picker) {
      if (picker?.dataset.pickerMode === "loadout" && LOADOUT_SLOT_TERMS[groupName]) {
        return slotFilteredItems(groupName);
      }
      return XML_PICKER_GROUPS[groupName] || XML_PICKER_GROUPS.cargo || XML_PICKER_GROUPS.all || [];
    }
    function rebuildPickerOptions(picker, groupName) {
      const select = picker ? picker.querySelector("[data-picker-item]") : null;
      if (!select || select.tagName !== "SELECT") return;
      const items = pickerGroupItems(groupName, picker);
      picker.dataset.pickerGroup = groupName || "cargo";
      select.innerHTML = '<option value="">Choose item</option>';
      items.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.name || "";
        option.textContent = `${item.name || ""} - ${item.category || "General"}`;
        select.appendChild(option);
      });
      syncPickerPreview(picker);
      renderVisualPicker(picker);
    }
    function imageForItem(item) {
      return item.image_url || itemInfo(item.name).image_url || fallbackThumb(item.category);
    }
    function selectOptionItem(option) {
      const value = option ? String(option.value || "").trim() : "";
      const text = option ? String(option.textContent || value) : value;
      const category = text.includes(" - ") ? text.split(" - ").slice(1).join(" - ") : itemInfo(value).category || "General";
      return Object.assign({name: value, category}, itemInfo(value));
    }
    function renderVisualSelect(select) {
      if (!select || !select.dataset.visualSelect) return;
      let visual = select.parentElement.querySelector("[data-visual-select-grid]");
      if (!visual) {
        const wrapper = document.createElement("div");
        wrapper.className = "visual-picker";
        wrapper.innerHTML = '<input type="search" data-visual-select-search placeholder="Search choices"><div class="visual-select-grid" data-visual-select-grid></div>';
        select.parentElement.appendChild(wrapper);
        visual = wrapper.querySelector("[data-visual-select-grid]");
      }
      const query = (select.parentElement.querySelector("[data-visual-select-search]")?.value || "").trim().toLowerCase();
      const options = Array.from(select.options || [])
        .filter((option) => option.value)
        .map(selectOptionItem)
        .filter((item) => !query || `${item.name} ${item.category}`.toLowerCase().includes(query))
        .slice(0, 48);
      visual.innerHTML = "";
      options.forEach((item) => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "visual-select-card";
        card.dataset.visualSelectValue = item.name;
        card.classList.toggle("active", String(select.value).toLowerCase() === String(item.name).toLowerCase());
        const img = document.createElement("img");
        img.src = imageForItem(item);
        img.alt = "";
        img.onerror = function () { this.onerror = null; this.src = item.fallback_image_url || fallbackThumb(item.category); };
        const title = document.createElement("strong");
        title.textContent = item.name;
        card.appendChild(img);
        card.appendChild(title);
        visual.appendChild(card);
      });
    }
    function renderVisualPicker(picker) {
      if (!picker) return;
      const select = picker.querySelector("[data-picker-item]");
      if (!select || select.tagName !== "SELECT") return;
      let visual = picker.querySelector("[data-visual-picker]");
      if (!visual) {
        visual = document.createElement("div");
        visual.className = "visual-picker";
        visual.dataset.visualPicker = "true";
        visual.innerHTML = '<input type="search" data-visual-search placeholder="Search visible items"><div class="visual-picker-grid" data-visual-grid></div>';
        const controls = picker.querySelector(".item-picker-controls");
        if (controls && controls.nextSibling) {
          picker.insertBefore(visual, controls.nextSibling);
        } else {
          picker.appendChild(visual);
        }
      }
      const grid = visual.querySelector("[data-visual-grid]");
      const query = (visual.querySelector("[data-visual-search]")?.value || "").trim().toLowerCase();
      const rawSlotValue = picker.querySelector("[data-picker-slot]")?.value || "";
      const slotValue = picker.dataset.pickerMode === "loadout" ? (rawSlotValue || DEFAULT_LOADOUT_SLOT) : rawSlotValue;
      const group = picker.dataset.pickerMode === "loadout"
        ? slotValue
        : (picker.dataset.pickerGroup || slotValue || "cargo");
      const sourceItems = pickerGroupItems(group, picker);
      const selected = String(select.value || "").toLowerCase();
      const items = sourceItems
        .filter((item) => {
          const text = `${item.name || ""} ${item.category || ""}`.toLowerCase();
          return !query || text.includes(query);
        })
        .slice(0, 72);
      grid.innerHTML = "";
      items.forEach((item) => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "visual-picker-card";
        card.dataset.visualItem = item.name || "";
        card.classList.toggle("active", selected && selected === String(item.name || "").toLowerCase());
        const img = document.createElement("img");
        img.src = imageForItem(item);
        img.alt = "";
        img.onerror = function () { this.onerror = null; this.src = item.fallback_image_url || fallbackThumb(item.category); };
        const title = document.createElement("strong");
        title.textContent = item.name || "";
        const meta = document.createElement("small");
        meta.textContent = item.category || "General";
        card.appendChild(img);
        card.appendChild(title);
        card.appendChild(meta);
        grid.appendChild(card);
      });
    }
    function syncLoadoutPickerSlot(slotSelect) {
      const picker = slotSelect ? slotSelect.closest("[data-item-picker]") : null;
      if (!picker || picker.dataset.pickerMode !== "loadout") return;
      const form = picker.closest("form");
      if (!slotSelect.value) slotSelect.value = DEFAULT_LOADOUT_SLOT;
      const slot = slotSelect.value || DEFAULT_LOADOUT_SLOT;
      picker.dataset.pickerGroup = slot;
      if (form) {
        const label = form.querySelector("[data-active-slot-label]");
        if (label) label.textContent = `Selected slot: ${slot}`;
        const note = form.querySelector("[data-active-slot-note]");
        if (note) {
          note.textContent = `Showing ${slot} options below. Pick a card or use the dropdown, then press Add.`;
        }
        form.querySelectorAll("[data-loadout-slot]").forEach((button) => {
          button.classList.toggle("active", button.dataset.loadoutSlot === slot);
        });
      }
      try {
        rebuildPickerOptions(picker, slot);
      } catch (error) {
        console.warn("Loadout picker rebuild failed", error);
      }
      const itemSelect = picker.querySelector("[data-picker-item]");
      if (itemSelect && itemSelect.options.length > 1 && itemSelect.selectedIndex < 1) {
        itemSelect.selectedIndex = 0;
      }
      syncPickerPreview(picker);
      try {
        renderVisualPicker(picker);
      } catch (error) {
        console.warn("Loadout visual picker render failed", error);
      }
    }
    function syncPickerPreview(picker) {
      if (!picker) return;
      const input = picker.querySelector("[data-picker-item]");
      const image = picker.querySelector("[data-picker-image]");
      const label = picker.querySelector("[data-picker-label]");
      const name = input ? input.value.trim() : "";
      const info = itemInfo(name);
      if (image) {
        image.src = info.image_url || fallbackThumb(info.category);
        image.onerror = () => { image.onerror = null; image.src = info.fallback_image_url || fallbackThumb(info.category); };
      }
      if (label) label.textContent = name ? `${name}${info.category ? ` - ${info.category}` : ""}` : "Pick an item to preview it.";
    }
    function pickerLine(picker) {
      const itemInput = picker ? picker.querySelector("[data-picker-item]") : null;
      const item = itemInput ? itemInput.value.trim() : "";
      if (!item) return "";
      const qty = Math.max(1, Math.min(999, Number(picker.querySelector("[data-picker-qty]")?.value || 1) || 1));
      const mode = picker.dataset.pickerMode || "xml";
      const quantity = picker.querySelector("[data-picker-quantity]")?.value || "-1";
      const damage = picker.querySelector("[data-picker-damage]")?.value || "pristine";
      const slot = picker.querySelector("[data-picker-slot]")?.value || "";
      const attachment = picker.querySelector("[data-picker-attachment]")?.value || "";
      return mode === "bundle"
        ? `${qty}x ${item}`
        : [item, qty, quantity, damage, slot, attachment].filter((part, index) => index < 4 || String(part || "").trim()).join(", ");
    }
    function lineParts(line) {
      const parts = String(line || "").split(",").map((part) => part.trim());
      if (/^\\d+x\\s+/i.test(parts[0] || "")) {
        const match = parts[0].match(/^(\\d+)x\\s+(.+)$/i);
        return match ? {name: match[2], meta: `${match[1]}x`} : {name: parts[0], meta: ""};
      }
      return {
        name: parts[0] || "",
        meta: [parts[1] ? `${parts[1]}x` : "", parts[3] || "", parts[4] || ""].filter(Boolean).join(" - "),
      };
    }
    function syncSelectedItems(output) {
      const form = output ? output.closest("form") : null;
      const board = form ? form.querySelector("[data-selected-items]") : null;
      if (!board) return;
      const lines = output.value.split(/\n+/).map((line) => line.trim()).filter(Boolean);
      board.innerHTML = "";
      if (!lines.length) {
        const empty = document.createElement("span");
        empty.className = "muted";
        empty.textContent = board.dataset.emptyText || "No items added yet";
        board.appendChild(empty);
        syncLiveOutput(form);
        return;
      }
      lines.forEach((line, index) => {
        const info = lineParts(line);
        const item = itemInfo(info.name);
        const row = document.createElement("div");
        row.className = "selected-row";
        row.draggable = true;
        row.dataset.index = String(index);
        row.innerHTML = `<img class="item-thumb" src="${item.image_url || fallbackThumb(item.category)}" alt=""><span><strong></strong><small></small></span><button type="button" data-remove-selected>&times;</button>`;
        row.querySelector("strong").textContent = info.name;
        row.querySelector("small").textContent = info.meta || line;
        row.querySelector("img").onerror = function () { this.onerror = null; this.src = item.fallback_image_url || fallbackThumb(item.category); };
        board.appendChild(row);
      });
      syncLiveOutput(form);
    }
    function setOutputLines(output, lines) {
      output.value = lines.filter(Boolean).join("\n");
      syncSelectedItems(output);
      syncLiveOutput(output.closest("form"));
    }
    function outputLines(output) {
      return output.value.split(/\n+/).map((line) => line.trim()).filter(Boolean);
    }
    function appendPickerLine(picker, output) {
      const line = pickerLine(picker);
      const itemInput = picker ? picker.querySelector("[data-picker-item]") : null;
      if (!line || !output) return false;
      output.value = output.value.trim() ? `${output.value.trim()}\n${line}` : line;
      syncSelectedItems(output);
      syncLiveOutput(output.closest("form"));
      if (itemInput) {
        itemInput.value = "";
        itemInput.focus();
      }
      if (picker) syncPickerPreview(picker);
      return true;
    }
    function xmlEscape(value) {
      return String(value ?? "").replace(/[<>&"']/g, (char) => ({"<": "&lt;", ">": "&gt;", "&": "&amp;", "\"": "&quot;", "'": "&apos;"}[char]));
    }
    function parsedOutputItems(form) {
      const output = form ? form.querySelector("[data-picker-output]") : null;
      return outputLines(output).map((line) => {
        const parts = String(line || "").split(",").map((part) => part.trim());
        return {
          item: parts[0] || "",
          quantity: Math.max(1, Number(parts[1] || 1) || 1),
          quantityPercent: Number(parts[2] || -1),
          damage: parts[3] || "pristine",
          slot: parts[4] || "",
          attachmentFor: parts[5] || "",
        };
      }).filter((item) => item.item);
    }
    function damageRange(damage) {
      return {pristine: [1, 1], worn: [0.7, 1], damaged: [0.45, 0.7], badly_damaged: [0.2, 0.45], ruined: [0, 0.2], random: [0.2, 1]}[damage] || [1, 1];
    }
    function buildCargoXml(typeName, items) {
      const lines = [`<type name="${xmlEscape(typeName || "Classname")}">`];
      items.forEach((item) => {
        lines.push(`    <cargo chance="1.00">`);
        lines.push(`        <item name="${xmlEscape(item.item)}" chance="1.00" />`);
        lines.push(`    </cargo>`);
      });
      lines.push(`</type>`);
      return lines.join("\n");
    }
    function buildLoadoutPreview(form, items) {
      const bySlot = {};
      const unsorted = [];
      items.forEach((item) => {
        const range = damageRange(item.damage);
        const entry = {
          itemType: item.item,
          spawnWeight: item.quantity,
          attributes: {healthMin: range[0], healthMax: range[1]},
        };
        if (item.quantityPercent >= 0) {
          entry.attributes.quantityMin = item.quantityPercent / 100;
          entry.attributes.quantityMax = item.quantityPercent / 100;
        }
        if (item.attachmentFor) entry.attachmentFor = item.attachmentFor;
        if (item.slot) {
          (bySlot[item.slot] ||= []).push(entry);
        } else {
          unsorted.push(entry);
        }
      });
      const preset = {
        name: form?.elements.recipe_name?.value || "Wandering Bot Loadout",
        spawnWeight: 1,
        attachmentSlotItemSets: Object.keys(bySlot).sort().map((slot) => ({
          slotName: slot,
          discreteItemSets: [{spawnWeight: 1, items: bySlot[slot]}],
        })),
      };
      if (unsorted.length) preset.discreteUnsortedItemSets = [{spawnWeight: 1, items: unsorted}];
      return JSON.stringify({presets: [preset]}, null, 2);
    }
    function safeXmlName(value, fallback) {
      const text = String(value || "").trim().replace(/[^A-Za-z0-9_]/g, "_").replace(/^_+|_+$/g, "");
      return text || fallback;
    }
    function checkedValues(form, name) {
      return Array.from(form.querySelectorAll(`input[name="${name}"]:checked`)).map((item) => item.value);
    }
    function airdropPositions(form) {
      const raw = String(form.elements.positions?.value || "").trim();
      if (!raw) return [];
      return raw.split(/\n+/).map((line) => {
        const parts = line.split(/[,\\s]+/).map((part) => part.trim()).filter(Boolean);
        return {x: parts[0] || "0", z: parts[1] || "0"};
      }).filter((pos) => pos.x && pos.z).slice(0, 80);
    }
    function setAirdropPositions(form, positions) {
      if (!form || !form.elements.positions) return;
      form.elements.positions.value = positions.map((pos) => `${Math.round(Number(pos.x) || 0)}, ${Math.round(Number(pos.z) || 0)}`).join("\n");
      renderAirdropMap(form);
      syncLiveOutput(form);
    }
    function airdropMapSize(map) {
      const size = Number(map?.dataset.mapSize || 15360);
      return Number.isFinite(size) && size > 0 ? size : 15360;
    }
    function renderAirdropMap(form) {
      const map = form?.querySelector("[data-airdrop-map]");
      if (!map) return;
      const size = airdropMapSize(map);
      map.querySelectorAll(".airdrop-dot").forEach((dot) => dot.remove());
      const positions = airdropPositions(form).filter((pos) => Number(pos.x) > 0 && Number(pos.z) > 0);
      positions.forEach((pos, index) => {
        const dot = document.createElement("span");
        dot.className = "airdrop-dot";
        dot.textContent = String(index + 1);
        dot.title = `Airdrop ${index + 1}: ${Math.round(Number(pos.x) || 0)}, ${Math.round(Number(pos.z) || 0)}`;
        dot.style.left = `${Math.max(0, Math.min(100, (Number(pos.x) / size) * 100))}%`;
        dot.style.top = `${Math.max(0, Math.min(100, 100 - ((Number(pos.z) / size) * 100)))}%`;
        map.appendChild(dot);
      });
      const readout = form.querySelector("[data-airdrop-readout]");
      if (readout) {
        readout.textContent = positions.length
          ? `${positions.length} airdrop location${positions.length === 1 ? "" : "s"} selected.`
          : "Click the map to add airdrop positions.";
      }
    }
    function randomAirdropPositions(form) {
      const map = form?.querySelector("[data-airdrop-map]");
      const size = airdropMapSize(map);
      const count = Math.max(2, Math.min(6, Number(form?.elements.random_count?.value || 2) || 2));
      const mode = String(form?.elements.placement_mode?.value || "manual");
      const ranges = mode === "random_military"
        ? {xMin: 0.12, xMax: 0.78, zMin: 0.55, zMax: 0.92}
        : {xMin: 0.16, xMax: 0.82, zMin: 0.20, zMax: 0.88};
      return Array.from({length: count}, () => ({
        x: Math.round(size * (ranges.xMin + Math.random() * (ranges.xMax - ranges.xMin))),
        z: Math.round(size * (ranges.zMin + Math.random() * (ranges.zMax - ranges.zMin))),
      }));
    }
    function buildAirdropPackage(form, items) {
      const eventName = safeXmlName(form.elements.event_name?.value, "Static_WanderingAirdrop");
      const containerClass = safeXmlName(form.elements.container_class?.value, "StaticObj_Misc_WoodenCrate_5x");
      const numberValue = (name, fallback) => Math.max(0, Number(form.elements[name]?.value || fallback) || 0);
      const positions = airdropPositions(form);
      const nominal = Math.max(1, numberValue("nominal", 1));
      const minCount = Math.max(1, numberValue("min_count", 1));
      const maxCount = Math.max(minCount, numberValue("max_count", 1));
      const spawnRadius = Math.max(1, numberValue("spawn_radius", 20));
      const secondaryEvent = safeXmlName(form.elements.secondary_event?.value, "");
      const cargoXml = items.map((item) => `        <cargo chance="1.00">\n            <item name="${xmlEscape(item.item)}" chance="1.00" />\n        </cargo>`).join("\n");
      return {
        events: [
          `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`,
          `<events>`,
          `    <event name="${xmlEscape(eventName)}">`,
          `        <nominal>${nominal}</nominal>`,
          `        <min>${minCount}</min>`,
          `        <max>${maxCount}</max>`,
          `        <lifetime>${numberValue("lifetime", 1800)}</lifetime>`,
          `        <restock>${numberValue("restock", 3600)}</restock>`,
          `        <saferadius>${numberValue("saferadius", 0)}</saferadius>`,
          `        <distanceradius>${numberValue("distanceradius", 1000)}</distanceradius>`,
          `        <cleanupradius>${numberValue("cleanupradius", 1500)}</cleanupradius>`,
          secondaryEvent ? `        <secondary>${xmlEscape(secondaryEvent)}</secondary>` : "",
          `        <flags deletable="1" init_random="0" remove_damaged="0" />`,
          `        <position>fixed</position>`,
          `        <limit>child</limit>`,
          `        <active>1</active>`,
          `        <children>`,
          `            <child lootmax="0" lootmin="0" max="1" min="1" type="${xmlEscape(containerClass)}" />`,
          `        </children>`,
          `    </event>`,
          `</events>`,
        ].filter(Boolean).join("\n"),
        spawns: [
          `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`,
          `<eventposdef>`,
          `    <event name="${xmlEscape(eventName)}">`,
          `        <zone smin="1" smax="1" dmin="1" dmax="1" r="${spawnRadius}" />`,
          ...positions.map((pos) => `        <pos x="${xmlEscape(pos.x)}" z="${xmlEscape(pos.z)}" a="0" y="0" />`),
          `    </event>`,
          `</eventposdef>`,
        ].join("\n"),
        spawnable: [
          `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`,
          `<spawnabletypes>`,
          `    <type name="${xmlEscape(containerClass)}">`,
          cargoXml,
          `    </type>`,
          `</spawnabletypes>`,
        ].filter(Boolean).join("\n"),
      };
    }
    function syncLiveOutput(form) {
      if (!form) return;
      const preview = form.querySelector("[data-live-output]");
      if (!preview) return;
      const kind = form.elements.recipe_kind ? String(form.elements.recipe_kind.value || "") : "";
      const items = parsedOutputItems(form);
      if (kind === "player_loadout") {
        preview.textContent = buildLoadoutPreview(form, items);
      } else if (kind === "vehicle_loadout") {
        preview.textContent = buildCargoXml(form.elements.vehicle_class?.value || "VehicleClass", items);
      } else if (kind === "container") {
        preview.textContent = buildCargoXml(form.elements.container_class?.value || "ContainerClass", items);
      } else if (kind === "airdrop") {
        const packageOutput = buildAirdropPackage(form, items);
        const activeFile = preview.dataset.airdropOutputFile || "events";
        preview.textContent = packageOutput[activeFile] || packageOutput.events;
      }
    }
    document.querySelectorAll("[data-picker-output]").forEach(syncSelectedItems);
    applyTheme("command");
    document.addEventListener("click", (event) => {
      const themeButton = event.target.closest("[data-theme-choice]");
      if (themeButton) {
        const theme = themeButton.dataset.themeChoice || "default";
        localStorage.setItem("wanderingDashboardTheme", theme);
        applyTheme(theme);
        const token = new URLSearchParams(window.location.search).get("token");
        const guildId = new URLSearchParams(window.location.search).get("guild_id") || "{{ server.guild_id if server else '' }}";
        fetch(secureDashboardUrl(`/api/admin/theme${token ? `?token=${encodeURIComponent(token)}` : ""}`), {
          method: "POST",
          headers: {"Content-Type": "application/json", "Accept": "application/json"},
          credentials: "same-origin",
          body: JSON.stringify({theme, guild_id: guildId})
        }).catch(() => {});
        return;
      }
      const pickerCard = event.target.closest("[data-picker-card]");
      if (pickerCard) {
        const picker = pickerCard.closest("[data-item-picker]");
        const input = picker ? picker.querySelector("[data-picker-item]") : null;
        if (input) input.value = pickerCard.dataset.item || "";
        if (picker) syncPickerPreview(picker);
        return;
      }
      const visualCard = event.target.closest("[data-visual-item]");
      if (visualCard) {
        const picker = visualCard.closest("[data-item-picker]");
        const input = picker ? picker.querySelector("[data-picker-item]") : null;
        if (input) input.value = visualCard.dataset.visualItem || "";
        if (picker) {
          syncPickerPreview(picker);
          renderVisualPicker(picker);
          if (picker.dataset.pickerMode === "loadout" || picker.dataset.pickerMode === "vehicle_cargo") {
            const form = picker.closest("form");
            const output = form ? form.querySelector("[data-picker-output]") : null;
            appendPickerLine(picker, output);
          }
        }
        return;
      }
      const visualSelectCard = event.target.closest("[data-visual-select-value]");
      if (visualSelectCard) {
        const label = visualSelectCard.closest("label");
        const select = label ? label.querySelector("select[data-visual-select]") : null;
        if (select) {
          select.value = visualSelectCard.dataset.visualSelectValue || "";
          renderVisualSelect(select);
          syncLiveOutput(select.closest("form"));
        }
        return;
      }
      const airdropTab = event.target.closest("[data-airdrop-file]");
      if (airdropTab) {
        const form = airdropTab.closest("form");
        const preview = form ? form.querySelector("[data-airdrop-output-file]") : null;
        if (preview) {
          preview.dataset.airdropOutputFile = airdropTab.dataset.airdropFile || "events";
          form.querySelectorAll("[data-airdrop-file]").forEach((button) => {
            button.classList.toggle("active", button === airdropTab);
          });
          syncLiveOutput(form);
        }
        return;
      }
      const airdropClear = event.target.closest("[data-airdrop-clear]");
      if (airdropClear) {
        const form = airdropClear.closest("form");
        setAirdropPositions(form, []);
        return;
      }
      const airdropUndo = event.target.closest("[data-airdrop-undo]");
      if (airdropUndo) {
        const form = airdropUndo.closest("form");
        const positions = airdropPositions(form);
        positions.pop();
        setAirdropPositions(form, positions);
        return;
      }
      const airdropMap = event.target.closest("[data-airdrop-map]");
      if (airdropMap) {
        const form = airdropMap.closest("form");
        const rect = airdropMap.getBoundingClientRect();
        const size = airdropMapSize(airdropMap);
        const x = Math.round(((event.clientX - rect.left) / Math.max(1, rect.width)) * size);
        const z = Math.round((1 - ((event.clientY - rect.top) / Math.max(1, rect.height))) * size);
        const positions = airdropPositions(form).filter((pos) => Number(pos.x) > 0 && Number(pos.z) > 0);
        positions.push({x: Math.max(0, Math.min(size, x)), z: Math.max(0, Math.min(size, z))});
        setAirdropPositions(form, positions);
        return;
      }
      const pickerButton = event.target.closest("[data-picker-add]");
      if (pickerButton) {
        event.preventDefault();
        const picker = pickerButton.closest("[data-item-picker]");
        const form = picker ? picker.closest("form") : null;
        const output = form ? form.querySelector("[data-picker-output]") : null;
        appendPickerLine(picker, output);
        return;
      }
      const slotButton = event.target.closest("[data-loadout-slot]");
      if (slotButton && !slotButton.closest("[data-visual-loadout-page]")) {
        event.preventDefault();
        const form = slotButton.closest("form");
        const slotSelect = form ? form.querySelector("[data-picker-slot]") : null;
        if (slotSelect) {
          slotSelect.value = slotButton.dataset.loadoutSlot || "";
          syncLoadoutPickerSlot(slotSelect);
          slotSelect.dispatchEvent(new Event("change", {bubbles: true}));
          const picker = slotSelect.closest("[data-item-picker]");
          if (picker) {
            picker.scrollIntoView({behavior: "smooth", block: "center"});
            const search = picker.querySelector("[data-visual-search]");
            if (search) search.focus({preventScroll: true});
          }
        }
        return;
      }
      const removeSelected = event.target.closest("[data-remove-selected]");
      if (removeSelected) {
        const row = removeSelected.closest("[data-index]");
        const form = removeSelected.closest("form");
        const output = form ? form.querySelector("[data-picker-output]") : null;
        if (row && output) {
          const lines = outputLines(output);
          lines.splice(Number(row.dataset.index || 0), 1);
          setOutputLines(output, lines);
        }
      }
    });
    document.addEventListener("dragstart", (event) => {
      const row = event.target.closest(".selected-row");
      if (!row) return;
      row.classList.add("dragging");
      event.dataTransfer.setData("text/plain", row.dataset.index || "0");
    });
    document.addEventListener("dragend", (event) => {
      const row = event.target.closest(".selected-row");
      if (row) row.classList.remove("dragging");
    });
    document.addEventListener("dragover", (event) => {
      if (event.target.closest("[data-selected-items]")) event.preventDefault();
    });
    document.addEventListener("drop", (event) => {
      const board = event.target.closest("[data-selected-items]");
      if (!board) return;
      event.preventDefault();
      const form = board.closest("form");
      const output = form ? form.querySelector("[data-picker-output]") : null;
      if (!output) return;
      const from = Number(event.dataTransfer.getData("text/plain") || 0);
      const targetRow = event.target.closest(".selected-row");
      const to = targetRow ? Number(targetRow.dataset.index || 0) : outputLines(output).length - 1;
      const lines = outputLines(output);
      const moved = lines.splice(from, 1)[0];
      if (!moved) return;
      lines.splice(Math.max(0, Math.min(lines.length, to)), 0, moved);
      setOutputLines(output, lines);
    });
    document.addEventListener("input", (event) => {
      if (event.target.matches("[data-picker-item]")) syncPickerPreview(event.target.closest("[data-item-picker]"));
      if (event.target.matches("[data-picker-output]")) syncSelectedItems(event.target);
      if (event.target.matches("[data-visual-search]")) renderVisualPicker(event.target.closest("[data-item-picker]"));
      if (event.target.matches("[data-visual-select-search]")) {
        const select = event.target.closest("label")?.querySelector("select[data-visual-select]");
        renderVisualSelect(select);
      }
      if (event.target.closest("form")) syncLiveOutput(event.target.closest("form"));
    });
    document.addEventListener("change", (event) => {
      if (event.target.matches("[data-picker-item]")) syncPickerPreview(event.target.closest("[data-item-picker]"));
      if (event.target.matches("[data-picker-slot]")) {
        syncLoadoutPickerSlot(event.target);
        renderVisualPicker(event.target.closest("[data-item-picker]"));
      }
      if (event.target.matches("[data-theme-select]")) {
        const theme = event.target.value || "default";
        localStorage.setItem("wanderingDashboardTheme", theme);
        applyTheme(theme);
        const token = new URLSearchParams(window.location.search).get("token");
        const guildId = new URLSearchParams(window.location.search).get("guild_id") || "{{ server.guild_id if server else '' }}";
        fetch(secureDashboardUrl(`/api/admin/theme${token ? `?token=${encodeURIComponent(token)}` : ""}`), {
          method: "POST",
          headers: {"Content-Type": "application/json", "Accept": "application/json"},
          credentials: "same-origin",
          body: JSON.stringify({theme, guild_id: guildId})
        }).catch(() => {});
      }
      if (event.target.matches("select[data-visual-select]")) renderVisualSelect(event.target);
      if (event.target.matches('select[name="placement_mode"], select[name="random_count"]')) {
        const form = event.target.closest("form");
        const placement = String(form?.elements.placement_mode?.value || "manual");
        if (placement.startsWith("random_")) setAirdropPositions(form, randomAirdropPositions(form));
        else renderAirdropMap(form);
      }
      if (event.target.closest("form")) syncLiveOutput(event.target.closest("form"));
    });
    function filterShopPanel(panel) {
      if (!panel) return;
      const input = panel.querySelector("[data-shop-search]");
      const category = panel.querySelector("[data-shop-category]");
      const count = panel.querySelector("[data-shop-count]");
      const query = input ? input.value.trim().toLowerCase() : "";
      const categoryValue = category ? category.value.trim().toLowerCase() : "";
      let visible = 0;
      panel.querySelectorAll("[data-shop-row]").forEach((row) => {
        const search = row.dataset.search || "";
        const rowCategory = row.dataset.category || "";
        const show = (!query || search.includes(query)) && (!categoryValue || rowCategory === categoryValue);
        row.hidden = !show;
        if (show) visible += 1;
      });
      if (count) count.textContent = visible;
    }
    window.filterShopItems = (control) => filterShopPanel(control?.closest?.("[data-shop-list]"));
    document.addEventListener("input", (event) => {
      if (event.target.matches("[data-shop-search]")) {
        filterShopPanel(event.target.closest("[data-shop-list]"));
      }
    });
    document.addEventListener("change", (event) => {
      if (event.target.matches("[data-shop-category]")) {
        filterShopPanel(event.target.closest("[data-shop-list]"));
      }
    });
    document.querySelectorAll("[data-shop-list]").forEach(filterShopPanel);
    const PLAYER_CARGO_NAMES = new Set({{ visual_player_cargo_names|tojson }});
    const FALLBACK_LOADOUT_DB = [
      {classname: "M4A1", readable: "M4A1 Assault Rifle", category: "Weapons"},
      {classname: "AKM", readable: "AKM Rifle", category: "Weapons"},
      {classname: "SKS", readable: "SKS Rifle", category: "Weapons"},
      {classname: "SVD", readable: "SVD Rifle", category: "Weapons"},
      {classname: "Mosin9130", readable: "Mosin 9130", category: "Weapons"},
      {classname: "Glock19", readable: "Glock 19", category: "Weapons"},
      {classname: "Mag_STANAG_30Rnd", readable: "STANAG 30 Round Mag", category: "Ammunition"},
      {classname: "Mag_AKM_30Rnd", readable: "AKM 30 Round Mag", category: "Ammunition"},
      {classname: "Ammo_556x45", readable: "5.56 Ammo", category: "Ammunition"},
      {classname: "Ammo_762x39", readable: "7.62x39 Ammo", category: "Ammunition"},
      {classname: "BallisticHelmet_Green", readable: "Ballistic Helmet", category: "Clothing"},
      {classname: "Mich2001Helmet", readable: "MICH Helmet", category: "Clothing"},
      {classname: "M65Jacket_Black", readable: "M65 Jacket Black", category: "Clothing"},
      {classname: "GorkaPants_PautRev", readable: "Gorka Pants PautRev", category: "Clothing"},
      {classname: "PlateCarrierVest", readable: "Plate Carrier Vest", category: "Clothing"},
      {classname: "TacticalGloves_Black", readable: "Tactical Gloves", category: "Clothing"},
      {classname: "MilitaryBoots_Black", readable: "Military Boots", category: "Clothing"},
      {classname: "MountainBag_Green", readable: "Mountain Backpack", category: "Clothing"},
      {classname: "BalaclavaMask_Black", readable: "Balaclava Mask", category: "Clothing"},
      {classname: "NVGoggles", readable: "NV Goggles", category: "Misc"},
      {classname: "BandageDressing", readable: "Bandage", category: "Medical"},
      {classname: "TetracyclineAntibiotics", readable: "Tetracycline", category: "Medical"},
      {classname: "Morphine", readable: "Morphine", category: "Medical"},
      {classname: "SalineBagIV", readable: "Saline IV", category: "Medical"},
      {classname: "SodaCan_Cola", readable: "Cola", category: "Food/Drink"},
      {classname: "WaterBottle", readable: "Water Bottle", category: "Food/Drink"},
      {classname: "TacticalBaconCan", readable: "Tactical Bacon", category: "Food/Drink"},
      {classname: "HuntingKnife", readable: "Hunting Knife", category: "Misc"},
      {classname: "Matchbox", readable: "Matchbox", category: "Misc"},
      {classname: "Compass", readable: "Compass", category: "Misc"},
      {classname: "M4_RISHndgrd", readable: "M4 RIS Handguard", category: "Misc", attachment: true},
      {classname: "M4_MPBttstck", readable: "M4 MP Buttstock", category: "Misc", attachment: true},
      {classname: "ACOGOptic", readable: "ACOG Optic", category: "Misc", attachment: true},
      {classname: "Battery9V", readable: "9V Battery", category: "Misc"}
    ];
    const SERVER_LOADOUT_DB = (Array.isArray(ITEM_LOOKUP) ? ITEM_LOOKUP : []).map((item) => ({
      classname: String(item.name || item.classname || "").trim(),
      readable: String(item.label || item.name || item.classname || "").trim(),
      category: String(item.category || "Misc").trim() || "Misc"
    })).filter((item) => item.classname);
    const LOADOUT_DB = SERVER_LOADOUT_DB.length ? SERVER_LOADOUT_DB : FALLBACK_LOADOUT_DB;
    const LOADOUT_ATTACHMENTS = {
      M4A1: ["M4_RISHndgrd", "M4_MPBttstck", "Mag_STANAG_30Rnd", "ACOGOptic", "Battery9V"],
      AKM: ["Mag_AKM_30Rnd"],
      SVD: ["Battery9V"],
      SKS: ["Ammo_762x39"]
    };
    const loadoutState = {
      selected: "{{ visual_loadout_slot }}",
      category: "all",
      cloth: VISUAL_LOADOUT_DRAFT.cloth || {},
      attachments: VISUAL_LOADOUT_DRAFT.attachments || {},
      weaponAttachments: VISUAL_LOADOUT_DRAFT.weaponAttachments || {},
      children: VISUAL_LOADOUT_DRAFT.children || {},
      cargo: VISUAL_LOADOUT_DRAFT.cargo || {Backpack: [], Torso: [], Legs: []}
    };
    function loadoutItemImage(classname) {
      return `https://db.mydayz.eu/wp-content/uploads/2025/08/${encodeURIComponent(classname)}.png.webp`;
    }
    function loadoutFallback(category) {
      const safe = encodeURIComponent(String(category || "General"));
      return `/item-thumb/${safe}`;
    }
    function loadoutItem(classname) {
      const key = String(classname || "").toLowerCase();
      return LOADOUT_DB.find((item) => item.classname.toLowerCase() === key) || {classname, readable: classname, category: "Misc"};
    }
    function loadoutCategoryMatches(item, category) {
      if (!category || category === "all") return true;
      const wanted = String(category || "").toLowerCase();
      const haystack = `${item.classname} ${item.readable} ${item.category}`.toLowerCase();
      if (wanted === "weapons") return haystack.includes("weapon") || haystack.includes("rifle") || haystack.includes("pistol") || haystack.includes("shotgun") || haystack.includes("m4") || haystack.includes("ak") || haystack.includes("mosin") || haystack.includes("sks");
      if (wanted === "ammunition") return haystack.includes("ammo") || haystack.includes("mag_") || haystack.includes("magazine") || haystack.includes("round");
      if (wanted === "clothing") return haystack.includes("cloth") || haystack.includes("jacket") || haystack.includes("pants") || haystack.includes("helmet") || haystack.includes("vest") || haystack.includes("boots") || haystack.includes("glove");
      if (wanted === "medical") return haystack.includes("medical") || haystack.includes("bandage") || haystack.includes("morphine") || haystack.includes("saline") || haystack.includes("epi") || haystack.includes("tetra");
      if (wanted === "food/drink") return haystack.includes("food") || haystack.includes("drink") || haystack.includes("water") || haystack.includes("canteen") || haystack.includes("can");
      return haystack.includes(wanted);
    }
    function loadoutPages() {
      return Array.from(document.querySelectorAll("[data-visual-loadout-page]"));
    }
    function selectedSlotLabel(slot) {
      if (!slot) return "No slot selected";
      if (slot.startsWith("cargo:")) return `${slot.slice(6)} Cargo`;
      return slot;
    }
    function setSelectedLoadoutSlot(slot) {
      loadoutState.selected = slot || "";
      document.querySelectorAll("[data-loadout-slot], [data-cargo-container]").forEach((node) => {
        const cargoSlot = node.dataset.cargoContainer ? `cargo:${node.dataset.cargoContainer}` : "";
        const nodeSlot = node.dataset.loadoutSlot || cargoSlot;
        node.classList.toggle("active", nodeSlot === loadoutState.selected);
      });
      loadoutPages().forEach((page) => {
        const panel = page.querySelector("[data-selected-loadout-slot]");
        if (!panel) return;
        panel.innerHTML = `<strong>${selectedSlotLabel(loadoutState.selected)}</strong><span>${loadoutState.selected ? "Click an item to place it here, or drag one in." : "Pick a slot, then click or drag an item into it."}</span>`;
      });
      renderAttachmentTray();
    }
    function equipLoadoutItem(classname, slot) {
      const target = slot || loadoutState.selected;
      if (!target) return false;
      const item = loadoutItem(classname);
      if (target.startsWith("cargo:")) {
        if (PLAYER_CARGO_NAMES.size && !PLAYER_CARGO_NAMES.has(item.classname)) return false;
        const container = target.slice(6);
        loadoutState.cargo[container] = loadoutState.cargo[container] || [];
        loadoutState.cargo[container].push(item.classname);
      } else {
        const allowed = selectedLoadoutItems(target);
        if (allowed.length && !allowed.some((row) => String(row.classname || row.name || "").toLowerCase() === item.classname.toLowerCase())) return false;
        const button = document.querySelector(`[data-loadout-slot="${CSS.escape(target)}"]`);
        const group = button ? button.dataset.slotGroup || "cloth" : "cloth";
        loadoutState[group][target] = item.classname;
        if (group === "attachments") loadoutState.weaponAttachments[target] = loadoutState.weaponAttachments[target] || [];
      }
      renderLoadoutState();
      return true;
    }
    function renderLoadoutBrowser(page) {
      const grid = page.querySelector("[data-loadout-items]");
      if (!grid) return;
      const query = String(page.querySelector("[data-loadout-search]")?.value || "").trim().toLowerCase();
      const category = loadoutState.category || "all";
      const items = selectedLoadoutItems(loadoutState.selected).filter((item) => {
        const haystack = `${item.classname} ${item.readable} ${item.category}`.toLowerCase();
        return (!query || haystack.includes(query)) && loadoutCategoryMatches(item, category);
      });
      grid.innerHTML = items.map((item) => `
        <button type="button" class="loadout-item-card" draggable="true" data-loadout-item="${item.classname}">
          <img src="${loadoutItemImage(item.classname)}" loading="lazy" decoding="async" onerror="this.onerror=null;this.src='${loadoutFallback(item.category)}';" alt="">
          <span><strong>${item.readable}</strong><small>${item.classname} - ${item.category}</small></span>
        </button>
      `).join("");
    }
    function renderCargo() {
      document.querySelectorAll("[data-cargo-items]").forEach((node) => {
        const container = node.dataset.cargoItems || "";
        const items = loadoutState.cargo[container] || [];
        node.innerHTML = items.map((classname, index) => `
          <span class="cargo-chip">${classname}<button type="button" data-remove-cargo="${container}" data-cargo-index="${index}">x</button></span>
        `).join("");
      });
    }
    function renderAttachmentTray() {
      const trayItems = document.querySelectorAll("[data-attachment-items]");
      const selected = loadoutState.selected || "";
      const selectedClass = loadoutState.attachments[selected] || "";
      const allowed = LOADOUT_ATTACHMENTS[selectedClass] || [];
      trayItems.forEach((node) => {
        if (!selected || !selectedClass || !allowed.length) {
          node.innerHTML = '<span class="muted">Select a weapon slot with a weapon to add sockets.</span>';
          return;
        }
        const attached = loadoutState.weaponAttachments[selected] || [];
        node.innerHTML = allowed.map((classname) => {
          const active = attached.includes(classname);
          return `<button type="button" class="attachment-chip" data-add-attachment="${classname}">${active ? "Added" : "Add"} ${classname}</button>`;
        }).join("");
      });
    }
    function renderLoadoutState() {
      document.querySelectorAll("[data-loadout-slot]").forEach((slot) => {
        const name = slot.dataset.loadoutSlot || "";
        const group = slot.dataset.slotGroup || "cloth";
        const value = loadoutState[group][name] || "";
        const strong = slot.querySelector("strong");
        if (strong) strong.textContent = value || "Empty";
        slot.classList.toggle("filled", Boolean(value));
      });
      renderCargo();
      renderAttachmentTray();
      const weaponSlots = Object.entries(loadoutState.attachments).filter(([, value]) => value);
      const weaponAttachments = {};
      weaponSlots.forEach(([slot, classname]) => {
        weaponAttachments[slot] = {
          item: classname,
          attachments: loadoutState.weaponAttachments[slot] || []
        };
      });
      const exportPayload = {
        PlayerData: {
          SpawnGear: {
            unclothed: false,
            cloth: Object.values(loadoutState.cloth).filter(Boolean),
            attachments: weaponSlots.map(([, value]) => value),
            cargo: Object.values(loadoutState.cargo).flat().filter(Boolean),
            slots: {
              cloth: loadoutState.cloth,
              weapons: weaponAttachments,
              cargo: loadoutState.cargo,
              children: loadoutState.children || {}
            }
          }
        }
      };
      const text = JSON.stringify(exportPayload, null, 2);
      document.querySelectorAll("[data-loadout-json]").forEach((output) => { output.value = text; });
    }
    function resetVisualLoadout() {
      loadoutState.selected = "";
      loadoutState.cloth = {};
      loadoutState.attachments = {};
      loadoutState.weaponAttachments = {};
      loadoutState.children = {};
      loadoutState.cargo = {Backpack: [], Torso: [], Legs: []};
      setSelectedLoadoutSlot("");
      renderLoadoutState();
    }
    loadoutPages().forEach((page) => {
      const grid = page.querySelector("[data-loadout-items]");
      if (!grid || !grid.children.length) renderLoadoutBrowser(page);
      renderLoadoutState();
    });
    document.addEventListener("input", (event) => {
      const page = event.target.closest("[data-visual-loadout-page]");
      if (page && event.target.matches("[data-loadout-search]")) renderLoadoutBrowser(page);
    });
    document.addEventListener("click", async (event) => {
      const categoryButton = event.target.closest("[data-loadout-category]");
      if (categoryButton) {
        loadoutState.category = categoryButton.dataset.loadoutCategory || "all";
        categoryButton.closest("[data-loadout-categories]")?.querySelectorAll("[data-loadout-category]").forEach((button) => {
          button.classList.toggle("active", button === categoryButton);
        });
        renderLoadoutBrowser(categoryButton.closest("[data-visual-loadout-page]"));
        return;
      }
      const slotButton = event.target.closest("[data-loadout-slot]");
      if (slotButton && slotButton.closest("[data-visual-loadout-page]")) {
        setSelectedLoadoutSlot(slotButton.dataset.loadoutSlot || "");
        return;
      }
      const cargoBox = event.target.closest("[data-cargo-container]");
      if (cargoBox && !event.target.closest("[data-remove-cargo]")) {
        setSelectedLoadoutSlot(`cargo:${cargoBox.dataset.cargoContainer || ""}`);
        return;
      }
      const itemButton = event.target.closest("[data-loadout-item]");
      if (itemButton) {
        equipLoadoutItem(itemButton.dataset.loadoutItem || "");
        return;
      }
      const attachButton = event.target.closest("[data-add-attachment]");
      if (attachButton && loadoutState.selected) {
        const slot = loadoutState.selected;
        loadoutState.weaponAttachments[slot] = loadoutState.weaponAttachments[slot] || [];
        const item = attachButton.dataset.addAttachment || "";
        if (!loadoutState.weaponAttachments[slot].includes(item)) loadoutState.weaponAttachments[slot].push(item);
        renderLoadoutState();
        return;
      }
      const removeCargo = event.target.closest("[data-remove-cargo]");
      if (removeCargo) {
        const container = removeCargo.dataset.removeCargo || "";
        const index = Number(removeCargo.dataset.cargoIndex || 0);
        if (loadoutState.cargo[container]) loadoutState.cargo[container].splice(index, 1);
        renderLoadoutState();
        return;
      }
      const clearSelected = event.target.closest("[data-clear-selected-slot]");
      if (clearSelected && loadoutState.selected && !loadoutState.selected.startsWith("cargo:")) {
        delete loadoutState.cloth[loadoutState.selected];
        delete loadoutState.attachments[loadoutState.selected];
        delete loadoutState.weaponAttachments[loadoutState.selected];
        renderLoadoutState();
        return;
      }
      const resetButton = event.target.closest("[data-reset-loadout]");
      if (resetButton) {
        resetVisualLoadout();
        return;
      }
      const uploadPackage = event.target.closest("[data-upload-loadout-package]");
      if (uploadPackage) {
        const form = uploadPackage.closest("[data-loadout-package-form]");
        if (!form) return;
        event.preventDefault();
        renderLoadoutState();
        const originalText = uploadPackage.textContent;
        uploadPackage.disabled = true;
        uploadPackage.textContent = "Uploading...";
        setLiveInjectionResult(form, "Validating, backing up and uploading package...", true);
        const data = new FormData(form);
        data.set("dashboard_mode", "{{ mode }}");
        data.set("allow_create", form.elements.allow_create?.checked ? "true" : "false");
        try {
          const body = await postFormDataJson("/api/admin/loadout-package-inject", data);
          setLiveInjectionResult(form, body.note || "Uploaded package with backup protection.", true);
        } catch (error) {
          setLiveInjectionResult(form, `Upload failed: ${error && error.message ? error.message : error}`, false);
        } finally {
          if (uploadPackage.isConnected) {
            uploadPackage.disabled = false;
            uploadPackage.textContent = originalText;
          }
        }
        return;
      }
      const copyLoadout = event.target.closest("[data-copy-loadout-json]");
      if (copyLoadout) {
        const output = copyLoadout.closest("[data-loadout-package-form]")?.querySelector("[data-loadout-json]");
        if (output && output.value) await navigator.clipboard.writeText(output.value).catch(() => {});
        const result = copyLoadout.closest("[data-loadout-package-form]")?.querySelector("[data-package-result]");
        if (result) result.textContent = output && output.value ? "Copied loadout JSON." : "Build a loadout first.";
      }
    });
    document.addEventListener("dragstart", (event) => {
      const itemButton = event.target.closest("[data-loadout-item]");
      if (!itemButton) return;
      event.dataTransfer.setData("application/x-dayz-class", itemButton.dataset.loadoutItem || "");
      event.dataTransfer.setData("text/plain", itemButton.dataset.loadoutItem || "");
    });
    document.addEventListener("dragover", (event) => {
      const target = event.target.closest("[data-loadout-slot], [data-cargo-container]");
      if (!target || !target.closest("[data-visual-loadout-page]")) return;
      event.preventDefault();
      target.classList.add("drag-over");
    });
    document.addEventListener("dragleave", (event) => {
      const target = event.target.closest("[data-loadout-slot], [data-cargo-container]");
      if (target && target.closest("[data-visual-loadout-page]")) target.classList.remove("drag-over");
    });
    document.addEventListener("drop", (event) => {
      const target = event.target.closest("[data-loadout-slot], [data-cargo-container]");
      if (!target || !target.closest("[data-visual-loadout-page]")) return;
      event.preventDefault();
      target.classList.remove("drag-over");
      const classname = event.dataTransfer.getData("application/x-dayz-class") || event.dataTransfer.getData("text/plain");
      const slot = target.dataset.loadoutSlot || (target.dataset.cargoContainer ? `cargo:${target.dataset.cargoContainer}` : "");
      if (slot) setSelectedLoadoutSlot(slot);
      equipLoadoutItem(classname, slot);
    });
    document.addEventListener("submit", async (event) => {
      const form = event.target.closest("[data-loadout-package-form]");
      if (!form) return;
      event.preventDefault();
      renderLoadoutState();
      const result = form.querySelector("[data-package-result]");
      const button = event.submitter || form.querySelector('button[type="submit"]');
      const originalText = button ? button.textContent : "";
      if (result) result.textContent = "Building package...";
      if (button) {
        button.disabled = true;
        button.textContent = "Building...";
      }
      const token = new URLSearchParams(window.location.search).get("token");
      const route = token ? `${form.dataset.route}?token=${encodeURIComponent(token)}` : form.dataset.route;
      try {
        const response = await fetch(secureDashboardUrl(route), {
          method: "POST",
          headers: {"Accept": "application/zip,application/json", "X-Requested-With": "fetch"},
          credentials: "same-origin",
          body: new FormData(form)
        });
        if (!response.ok) {
          let body = {};
          try { body = await response.json(); } catch (error) {}
          if (result) result.textContent = body.error || "Package rejected.";
          return;
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "MyDayZServerSettings.zip";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        if (result) result.textContent = "Package downloaded.";
      } catch (error) {
        if (result) result.textContent = `Package failed: ${error && error.message ? error.message : error}`;
      } finally {
        if (button && button.isConnected) {
          button.disabled = false;
          button.textContent = originalText;
        }
      }
    });
    document.querySelectorAll("[data-airdrop-map]").forEach((map) => renderAirdropMap(map.closest("form")));
    function prettyXml(xmlDoc) {
      const raw = new XMLSerializer().serializeToString(xmlDoc);
      return raw.replace(/></g, ">\n<");
    }
    function processTypesTool(panel) {
      const input = panel.querySelector("[data-types-input]");
      const output = panel.querySelector("[data-types-output]");
      const result = panel.querySelector("[data-types-result]");
      const xmlText = input ? input.value.trim() : "";
      if (!xmlText) {
        if (result) result.textContent = "Paste types.xml first.";
        return;
      }
      const doc = new DOMParser().parseFromString(xmlText, "application/xml");
      if (doc.querySelector("parsererror")) {
        if (result) result.textContent = "XML parse failed. Fix the pasted XML first.";
        return;
      }
      const action = panel.querySelector("[data-types-action]")?.value || "reduce";
      const factor = Number(panel.querySelector("[data-types-factor]")?.value || 1);
      const filter = String(panel.querySelector("[data-types-filter]")?.value || "").trim().toLowerCase();
      const fields = Array.from(panel.querySelectorAll("[data-types-field]:checked")).map((box) => box.value);
      const typesRoot = doc.querySelector("types");
      const types = Array.from(doc.querySelectorAll("type"));
      let changed = 0;
      function matches(type) {
        if (!filter) return true;
        return (type.getAttribute("name") || "").toLowerCase().includes(filter)
          || Array.from(type.children).some((child) => (`${child.tagName} ${child.getAttribute("name") || ""}`).toLowerCase().includes(filter));
      }
      function updateField(type, field, multiplier) {
        const node = Array.from(type.children).find((child) => child.tagName === field);
        if (!node) return;
        const value = Number(node.textContent || 0);
        if (!Number.isFinite(value)) return;
        node.textContent = String(Math.max(0, Math.round(value * multiplier)));
        changed += 1;
      }
      if (action === "organize" && typesRoot) {
        types.sort((a, b) => String(a.getAttribute("name") || "").localeCompare(String(b.getAttribute("name") || "")));
        types.forEach((type) => typesRoot.appendChild(type));
        changed = types.length;
      } else {
        types.filter(matches).forEach((type) => {
          const multiplier = action === "boost" || action === "tier_boost" ? factor : factor;
          const wanted = action === "lifetime_reduce" ? ["lifetime"] : (fields.length ? fields : ["nominal"]);
          wanted.forEach((field) => updateField(type, field, multiplier));
        });
      }
      if (output) output.value = prettyXml(doc);
      if (result) result.textContent = `${changed} value${changed === 1 ? "" : "s"} updated. Copy or download before uploading.`;
    }
    function toolOutputFor(root, key) {
      return Array.from(root.querySelectorAll("[data-tool-output]")).find((item) => item.dataset.toolOutput === key) || null;
    }
    function setToolResult(form, message, ok) {
      const result = form ? form.querySelector("[data-tool-result]") : null;
      if (!result) return;
      result.classList.remove("success", "error");
      result.classList.add(ok ? "success" : "error");
      result.textContent = message || "";
    }
    async function submitLocalGenerator(form, submitter) {
      if (!form || !form.dataset.route) return;
      const button = submitter || form.querySelector('button[type="submit"]');
      const originalButtonText = button ? button.textContent : "";
      const data = new FormData(form);
      data.set("dashboard_mode", "{{ mode }}");
      setToolResult(form, "Generating...", true);
      if (button) {
        button.disabled = true;
        button.textContent = "Generating...";
      }
      const token = new URLSearchParams(window.location.search).get("token");
      const route = token ? `${form.dataset.route}?token=${encodeURIComponent(token)}` : form.dataset.route;
      try {
        const response = await fetch(secureDashboardUrl(route), {
          method: "POST",
          headers: {"Accept": "application/json", "X-Requested-With": "fetch"},
          credentials: "same-origin",
          body: data
        });
        let body = {};
        try { body = await response.json(); } catch (error) {}
        if (!response.ok || body.ok === false || body.success === false) {
          setToolResult(form, body.error || "Generator rejected the input.", false);
          return;
        }
        const outputGroup = form.querySelector("[data-tool-output-group]");
        const outputs = body.outputs && typeof body.outputs === "object" ? body.outputs : body;
        let filled = 0;
        form.querySelectorAll("[data-tool-output]").forEach((output) => {
          const key = output.dataset.toolOutput;
          if (!key) return;
          const value = outputs[key] ?? body[key] ?? "";
          output.value = value;
          if (value) filled += 1;
        });
        if (outputGroup) outputGroup.hidden = filled === 0;
        const warnings = Array.isArray(body.warnings) && body.warnings.length ? ` ${body.warnings.length} warning${body.warnings.length === 1 ? "" : "s"}.` : "";
        setToolResult(form, `${body.note || "Generated."}${warnings}`, true);
      } catch (error) {
        setToolResult(form, `Request failed: ${error && error.message ? error.message : error}`, false);
      } finally {
        if (button && button.isConnected) {
          button.disabled = false;
          button.textContent = originalButtonText;
        }
      }
    }
    function tokenizedRoute(routePath) {
      const token = new URLSearchParams(window.location.search).get("token");
      return token ? `${routePath}?token=${encodeURIComponent(token)}` : routePath;
    }
    function setLiveInjectionResult(root, message, ok) {
      const result = root ? (root.querySelector("[data-inject-result]") || root.querySelector("[data-package-result]") || root.querySelector("[data-tool-result]")) : null;
      if (!result) return;
      result.classList.remove("success", "error");
      result.classList.add(ok ? "success" : "error");
      result.textContent = message || "";
    }
    async function postFormDataJson(routePath, data) {
      const response = await fetch(secureDashboardUrl(tokenizedRoute(routePath)), {
        method: "POST",
        headers: {"Accept": "application/json", "X-Requested-With": "fetch"},
        credentials: "same-origin",
        body: data
      });
      let body = {};
      try { body = await response.json(); } catch (error) {}
      if (!response.ok || body.ok === false || body.success === false) throw new Error(body.error || "Upload rejected.");
      return body;
    }
    async function uploadXmlOutput(button) {
      const form = button.closest("form");
      if (!form) return;
      const key = button.dataset.outputKey || "generated_xml";
      const output = toolOutputFor(form, key);
      if (!output || !String(output.value || "").trim()) {
        setLiveInjectionResult(form, "Generate XML first.", false);
        return;
      }
      const targetPath = form.elements.target_path ? String(form.elements.target_path.value || "").trim() : "";
      if (!targetPath) {
        setLiveInjectionResult(form, "Set the live server path first.", false);
        return;
      }
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "Uploading...";
      setLiveInjectionResult(form, "Backing up and uploading...", true);
      const data = new FormData();
      data.set("guild_id", form.elements.guild_id?.value || "{{ server.guild_id if server else '' }}");
      data.set("dashboard_mode", "{{ mode }}");
      data.set("target_path", targetPath);
      data.set("content", output.value);
      data.set("file_kind", button.dataset.fileKind || "xml");
      data.set("label", button.dataset.label || "server file");
      data.set("allow_create", form.elements.allow_create?.checked ? "true" : "false");
      try {
        const body = await postFormDataJson("/api/admin/xml-inject", data);
        setLiveInjectionResult(form, body.note || "Uploaded with backup protection.", true);
      } catch (error) {
        setLiveInjectionResult(form, `Upload failed: ${error && error.message ? error.message : error}`, false);
      } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = originalText;
        }
      }
    }
    async function mergeGeneratedConverterXml(button) {
      const form = button.closest("form");
      if (!form) return;
      const eventsXml = toolOutputFor(form, "events_xml")?.value || "";
      const eventspawnsXml = toolOutputFor(form, "eventspawns_xml")?.value || "";
      const eventgroupsXml = toolOutputFor(form, "eventgroups_xml")?.value || "";
      if (!eventsXml.trim() || !eventspawnsXml.trim() || !eventgroupsXml.trim()) {
        setLiveInjectionResult(form, "Generate the three XML snippets first.", false);
        return;
      }
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "Merging...";
      setLiveInjectionResult(form, "Downloading live files, backing up, then merging...", true);
      const data = new FormData();
      data.set("guild_id", form.elements.guild_id?.value || "{{ server.guild_id if server else '' }}");
      data.set("dashboard_mode", "{{ mode }}");
      data.set("events_xml", eventsXml);
      data.set("eventspawns_xml", eventspawnsXml);
      data.set("eventgroups_xml", eventgroupsXml);
      data.set("events_path", form.elements.events_path?.value || "");
      data.set("eventspawns_path", form.elements.eventspawns_path?.value || "");
      data.set("eventgroups_path", form.elements.eventgroups_path?.value || "");
      data.set("allow_create", form.elements.allow_create?.checked ? "true" : "false");
      try {
        const body = await postFormDataJson("/api/admin/dayz-converter-inject", data);
        setLiveInjectionResult(form, body.note || "Merged with backup protection.", true);
      } catch (error) {
        setLiveInjectionResult(form, `Merge failed: ${error && error.message ? error.message : error}`, false);
      } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = originalText;
        }
      }
    }
    document.addEventListener("submit", (event) => {
      const form = event.target && event.target.closest ? event.target.closest("[data-local-generator-form]") : null;
      if (!form) return;
      event.preventDefault();
      submitLocalGenerator(form, event.submitter);
    });
    document.addEventListener("click", async (event) => {
      const toolCopy = event.target.closest("[data-tool-copy]");
      if (toolCopy) {
        const root = toolCopy.closest("[data-local-generator-form]") || document;
        const output = toolOutputFor(root, toolCopy.dataset.toolCopy || "");
        if (output && output.value) {
          await navigator.clipboard.writeText(output.value).catch(() => {});
          setToolResult(root, "Copied output.", true);
        } else {
          setToolResult(root, "Generate output first.", false);
        }
        return;
      }
      const xmlInject = event.target.closest("[data-xml-inject]");
      if (xmlInject) {
        event.preventDefault();
        uploadXmlOutput(xmlInject);
        return;
      }
      const converterInject = event.target.closest("[data-converter-inject]");
      if (converterInject) {
        event.preventDefault();
        mergeGeneratedConverterXml(converterInject);
        return;
      }
      const processButton = event.target.closest("[data-types-process]");
      if (processButton) {
        processTypesTool(processButton.closest("[data-types-tool]"));
        return;
      }
      const copyButton = event.target.closest("[data-types-copy]");
      if (copyButton) {
        const panel = copyButton.closest("[data-types-tool]");
        const output = panel ? panel.querySelector("[data-types-output]") : null;
        if (output && output.value) {
          await navigator.clipboard.writeText(output.value).catch(() => {});
          const result = panel.querySelector("[data-types-result]");
          if (result) result.textContent = "Copied output.";
        }
      }
      const embedEdit = event.target.closest("[data-embed-template-edit]");
      if (embedEdit) {
        const card = embedEdit.closest("[data-embed-template-card]");
        const template = embedTemplateFromCard(card);
        if (!template) return;
        event.preventDefault();
        fillEmbedTemplateForm(template);
        return;
      }
      const embedDelete = event.target.closest("[data-embed-template-delete]");
      if (embedDelete) {
        if (embedDelete.closest("form")) return;
        event.preventDefault();
        if (embedDelete.dataset.confirm && !window.confirm(embedDelete.dataset.confirm)) return;
        const card = embedDelete.closest("[data-embed-template-card]");
        const result = card ? card.querySelector("[data-template-result]") : null;
        const token = new URLSearchParams(window.location.search).get("token");
        const route = `/api/admin/embed-template-action${token ? `?token=${encodeURIComponent(token)}` : ""}`;
        if (result) result.textContent = "Deleting...";
        embedDelete.disabled = true;
        try {
          const response = await fetch(secureDashboardUrl(route), {
            method: "POST",
            headers: {"Content-Type": "application/json", "Accept": "application/json", "X-Requested-With": "fetch"},
            credentials: "same-origin",
            body: JSON.stringify({
              action: "delete",
              template_id: embedDelete.dataset.templateId || card?.dataset.templateId || "",
              guild_id: embedDelete.dataset.guildId || "{{ server.guild_id if server else '' }}",
              dashboard_mode: "{{ mode }}",
            })
          });
          let body = {};
          try { body = await response.json(); } catch (error) {}
          if (!response.ok) {
            if (result) result.textContent = body.error || "Delete rejected";
            return;
          }
          const list = card ? card.closest("[data-embed-template-list]") : null;
          if (card) card.remove();
          syncEmptyEmbedTemplates(list);
        } catch (error) {
          if (result) result.textContent = `Delete failed: ${error && error.message ? error.message : error}`;
        } finally {
          if (embedDelete.isConnected) embedDelete.disabled = false;
        }
        return;
      }
      const recordEdit = event.target.closest("[data-dashboard-record-edit]");
      if (recordEdit) {
        const card = recordEdit.closest("[data-dashboard-record-card]");
        const record = dashboardRecordFromCard(card);
        if (!record) return;
        event.preventDefault();
        fillDashboardRecordForm(recordEdit.dataset.formId || dashboardRecordFormId(card?.dataset.section || ""), record);
        return;
      }
      const recordDelete = event.target.closest("[data-dashboard-record-delete]");
      if (recordDelete) {
        if (recordDelete.closest("form")) return;
        event.preventDefault();
        if (recordDelete.dataset.confirm && !window.confirm(recordDelete.dataset.confirm)) return;
        const card = recordDelete.closest("[data-dashboard-record-card]");
        const result = card ? card.querySelector("[data-dashboard-record-result]") : null;
        const token = new URLSearchParams(window.location.search).get("token");
        const route = `/api/admin/dashboard-record-action${token ? `?token=${encodeURIComponent(token)}` : ""}`;
        if (result) result.textContent = "Deleting...";
        recordDelete.disabled = true;
        try {
          const response = await fetch(secureDashboardUrl(route), {
            method: "POST",
            headers: {"Content-Type": "application/json", "Accept": "application/json", "X-Requested-With": "fetch"},
            credentials: "same-origin",
            body: JSON.stringify({
              action: "delete",
              section: recordDelete.dataset.section || card?.dataset.section || "",
              record_id: recordDelete.dataset.recordId || card?.dataset.recordId || "",
              guild_id: recordDelete.dataset.guildId || "{{ server.guild_id if server else '' }}",
              dashboard_mode: "{{ mode }}",
            })
          });
          let body = {};
          try { body = await response.json(); } catch (error) {}
          if (!response.ok) {
            if (result) result.textContent = body.error || "Delete rejected";
            return;
          }
          const list = card ? card.closest("[data-dashboard-record-list]") : null;
          if (card) card.remove();
          syncEmptyDashboardRecords(list);
        } catch (error) {
          if (result) result.textContent = `Delete failed: ${error && error.message ? error.message : error}`;
        } finally {
          if (recordDelete.isConnected) recordDelete.disabled = false;
        }
        return;
      }
    });
    function formValue(value) {
      const text = String(value || "").trim();
      if (text === "true") return true;
      if (text === "false") return false;
      if (/^-?\\d+$/.test(text)) return Number(text);
      if ((text.startsWith("{") && text.endsWith("}")) || (text.startsWith("[") && text.endsWith("]"))) {
        try { return JSON.parse(text); } catch (error) { return value; }
      }
      return value;
    }
    function embedFieldsToLines(fields) {
      if (!Array.isArray(fields)) return "";
      return fields.map((field) => {
        const name = String(field?.name || "").replace(/[|]/g, "/");
        const value = String(field?.value || "").replace(/[|]/g, "/");
        const inline = field?.inline ? "true" : "false";
        return `${name} | ${value} | ${inline}`;
      }).filter((line) => line.trim()).join("\n");
    }
    function setFormControl(form, name, value) {
      if (!form || !form.elements[name]) return;
      const control = form.elements[name];
      const hasRadioNodeList = typeof RadioNodeList !== "undefined";
      const controls = hasRadioNodeList && control instanceof RadioNodeList ? Array.from(control) : [control];
      controls.forEach((item) => {
        if (!item) return;
        if (item.type === "checkbox") {
          item.checked = Boolean(value);
        } else if (item.tagName === "SELECT") {
          const wanted = String(value ?? "");
          const matching = Array.from(item.options).find((option) => option.value === wanted || option.dataset.channelId === wanted);
          item.value = matching ? matching.value : wanted;
          item.dispatchEvent(new Event("change", {bubbles: true}));
        } else {
          item.value = value ?? "";
          item.dispatchEvent(new Event("input", {bubbles: true}));
        }
      });
    }
    function channelDisplayFromForm(form, name, value, fallback = "no channel") {
      const text = String(value || "").trim();
      if (!text) return fallback;
      const select = form?.elements?.[name];
      if (select && select.options) {
        const match = Array.from(select.options).find((option) => option.value === text || option.dataset.channelId === text || option.textContent.trim() === text);
        if (match) return match.textContent.trim() || fallback;
      }
      if (/^\\d+$/.test(text)) return "Unknown channel";
      return text.startsWith("#") ? text : `#${text}`;
    }
    function embedTemplateFromCard(card) {
      if (!card) return null;
      if (card.__embedTemplate) return card.__embedTemplate;
      const script = card.querySelector("[data-embed-template-json]");
      if (!script) return null;
      try { return JSON.parse(script.textContent || "{}"); } catch (error) { return null; }
    }
    function fillEmbedTemplateForm(template) {
      const form = document.getElementById("embed-template-form");
      if (!form || !template) return;
      const embed = template.embed || {};
      const delivery = template.delivery || {};
      const schedule = template.schedule || {};
      setFormControl(form, "name", template.name || "custom-message");
      setFormControl(form, "template_id", template.template_id || template.id || "");
      setFormControl(form, "content_mode", delivery.content_mode || template.content_mode || "embed");
      setFormControl(form, "channel_key", delivery.channel_key || template.channel_key || "");
      setFormControl(form, "title", embed.title || template.title || "");
      setFormControl(form, "colour", embed.colour || embed.color || template.colour || "#8d963e");
      setFormControl(form, "author_name", embed.author?.name || template.author_name || "");
      setFormControl(form, "author_icon_url", embed.author?.icon_url || template.author_icon_url || "");
      setFormControl(form, "thumbnail_url", embed.thumbnail_url || template.thumbnail_url || "");
      setFormControl(form, "image_url", embed.image_url || template.image_url || "");
      setFormControl(form, "footer_text", embed.footer?.text || template.footer_text || "");
      setFormControl(form, "footer_icon_url", embed.footer?.icon_url || template.footer_icon_url || "");
      setFormControl(form, "mention_mode", delivery.mention_mode || template.mention_mode || "none");
      setFormControl(form, "mention_role_id", delivery.mention_role_id || template.mention_role_id || "");
      setFormControl(form, "schedule_type", schedule.type || template.schedule_type || "manual");
      setFormControl(form, "schedule_time", schedule.time || template.schedule_time || "");
      setFormControl(form, "event_filter", schedule.event_filter || template.event_filter || "");
      setFormControl(form, "event_minimum", schedule.event_minimum ?? template.event_minimum ?? 0);
      setFormControl(form, "interval_minutes", schedule.interval_minutes ?? template.interval_minutes ?? 60);
      setFormControl(form, "timezone", schedule.timezone || template.timezone || "Europe/Dublin");
      setFormControl(form, "button_label", delivery.button_label || template.button_label || "");
      setFormControl(form, "button_url", delivery.button_url || template.button_url || "");
      setFormControl(form, "body", embed.description || template.body || "");
      setFormControl(form, "fields_lines", embedFieldsToLines(embed.fields));
      const submit = form.querySelector('button[type="submit"]');
      if (submit) submit.textContent = "Save Message";
      form.classList.add("dashboard-edit-modal");
      form.scrollIntoView({behavior: "smooth", block: "start"});
    }
    function syncEmptyEmbedTemplates(list) {
      if (!list) return;
      const cards = list.querySelectorAll("[data-embed-template-card]");
      let empty = list.querySelector("[data-empty-embed-templates]");
      if (cards.length) {
        if (empty) empty.remove();
      } else if (!empty) {
        empty = document.createElement("p");
        empty.className = "muted";
        empty.dataset.emptyEmbedTemplates = "";
        empty.textContent = "No saved embed templates for this server yet.";
        list.appendChild(empty);
      }
    }
    function createEmbedTemplateCard(template, form) {
      const card = document.createElement("div");
      card.className = "notification";
      card.dataset.embedTemplateCard = "";
      card.dataset.removeRow = "";
      card.dataset.templateId = template.template_id || template.id || "";
      card.__embedTemplate = template;
      const schedule = template.schedule || {};
      const delivery = template.delivery || {};
      const row = document.createElement("div");
      row.className = "row-between";
      const details = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = template.template_id || template.id || "message";
      const summary = document.createElement("span");
      summary.textContent = `${template.name || "custom-message"} -> ${schedule.type || "manual"}`;
      const small = document.createElement("small");
      small.textContent = `Channel: ${channelDisplayFromForm(form, "channel_key", delivery.channel_key || template.channel_key, "not set")}${schedule.time ? ` | Time: ${schedule.time}` : ""}`;
      details.append(title, summary, small);
      const actions = document.createElement("div");
      actions.className = "inline-actions";
      const id = template.template_id || template.id || "";
      const guildId = form?.elements?.guild_id?.value || template.guild_id || "";
      const dashboardPath = window.location.pathname.startsWith("/owner") ? "/owner" : "/admin";
      const edit = document.createElement("a");
      edit.className = "button";
      edit.href = `${dashboardPath}?section=automations&guild_id=${encodeURIComponent(guildId)}&edit_embed=${encodeURIComponent(id || template.name || "")}#embed-template-form`;
      edit.dataset.embedTemplateEdit = "";
      edit.textContent = "Edit";
      const removeForm = document.createElement("form");
      removeForm.className = "admin-form inline-action";
      removeForm.method = "post";
      removeForm.action = "/api/admin/embed-template-action";
      removeForm.dataset.route = "/api/admin/embed-template-action";
      removeForm.dataset.confirm = `Delete embed template ${id || "message"}?`;
      [
        ["guild_id", guildId],
        ["return_to", `${dashboardPath}?section=automations&guild_id=${encodeURIComponent(guildId)}#embed-template-form`],
        ["dashboard_mode", "{{ mode }}"],
        ["template_id", id],
        ["action", "delete"],
      ].forEach(([name, value]) => {
        const input = document.createElement("input");
        input.className = "hidden-field";
        input.name = name;
        input.value = value;
        removeForm.appendChild(input);
      });
      const remove = document.createElement("button");
      remove.type = "submit";
      remove.dataset.embedTemplateDelete = "";
      remove.dataset.templateId = id;
      remove.dataset.guildId = guildId;
      remove.textContent = "Delete";
      removeForm.appendChild(remove);
      const result = document.createElement("span");
      result.className = "result muted";
      result.dataset.templateResult = "";
      actions.append(edit, removeForm, result);
      row.append(details, actions);
      const script = document.createElement("script");
      script.type = "application/json";
      script.dataset.embedTemplateJson = "";
      script.textContent = JSON.stringify(template);
      card.append(row, script);
      return card;
    }
    function upsertEmbedTemplateCard(template, form) {
      const list = document.querySelector("[data-embed-template-list]");
      if (!list || !template) return;
      const id = template.template_id || template.id || "";
      const card = createEmbedTemplateCard(template, form);
      const existing = id ? list.querySelector(`[data-embed-template-card][data-template-id="${CSS.escape(id)}"]`) : null;
      if (existing) existing.replaceWith(card);
      else list.appendChild(card);
      syncEmptyEmbedTemplates(list);
    }
    const DASHBOARD_RECORD_SAVE_ROUTES = {
      "/api/admin/welcome-automation": {section: "welcome_automations", bodyKey: "automation", message: "Saved welcome automation."},
      "/api/admin/utility-config": {section: "utility_configs", bodyKey: "utility", message: "Saved utility module."},
      "/api/admin/reaction-role-panel": {section: "reaction_role_panels", bodyKey: "panel", message: "Saved reaction role panel."},
    };
    function dashboardRecordId(section, record) {
      if (!record) return "";
      if (section === "welcome_automations") return String(record.automation_id || record.name || "");
      if (section === "utility_configs") return String(record.module || record.name || "");
      if (section === "reaction_role_panels") return String(record.panel_id || record.name || "");
      return String(record.id || record.name || "");
    }
    function dashboardRecordFromCard(card) {
      if (!card) return null;
      if (card.__dashboardRecord) return card.__dashboardRecord;
      const script = card.querySelector("[data-dashboard-record-json]");
      if (!script) return null;
      try { return JSON.parse(script.textContent || "{}"); } catch (error) { return null; }
    }
    function fillDashboardRecordForm(formId, record) {
      const form = document.getElementById(formId);
      if (!form || !record) return;
      Object.entries(record).forEach(([key, value]) => {
        if (value && typeof value === "object") return;
        setFormControl(form, key, value);
      });
      form.classList.add("dashboard-edit-modal");
      form.scrollIntoView({behavior: "smooth", block: "start"});
      const result = form.querySelector(".result");
      if (result) result.textContent = "Loaded for editing.";
    }
    function syncEmptyDashboardRecords(list) {
      if (!list) return;
      const cards = list.querySelectorAll("[data-dashboard-record-card]");
      let empty = list.querySelector("[data-empty-dashboard-records]");
      if (cards.length) {
        if (empty) empty.remove();
      } else if (!empty) {
        empty = document.createElement("p");
        empty.className = "muted";
        empty.dataset.emptyDashboardRecords = "";
        empty.textContent = list.dataset.emptyMessage || "No saved records for this server yet.";
        list.appendChild(empty);
      }
    }
    function dashboardRecordText(section, record, form = null) {
      if (section === "welcome_automations") {
        return {
          title: record.name || dashboardRecordId(section, record) || "welcome automation",
          summary: `${record.enabled === false ? "Off" : "On"} -> ${channelDisplayFromForm(form, "channel_key", record.channel_key, "no channel")}`,
          detail: record.send_hour ? `Send hour: ${record.send_hour}` : "Manual timing",
        };
      }
      if (section === "utility_configs") {
        return {
          title: record.module || record.name || "utility module",
          summary: `${record.enabled === false ? "Off" : "On"} -> ${channelDisplayFromForm(form, "channel_key", record.channel_key, "no channel")}`,
          detail: `Limit: ${record.limit || 0} | XP: ${record.xp_per_message || 0} | Cooldown: ${record.cooldown_seconds || 0}s`,
        };
      }
      if (section === "reaction_role_panels") {
        const roleLines = String(record.roles || "").split(/\r?\n/).filter((line) => line.trim()).length;
        return {
          title: record.name || dashboardRecordId(section, record) || "reaction role panel",
          summary: `Channel: ${channelDisplayFromForm(form, "channel_key", record.channel_key, "no channel")}`,
          detail: `${roleLines} role line${roleLines === 1 ? "" : "s"}`,
        };
      }
      return {title: dashboardRecordId(section, record) || "record", summary: "", detail: ""};
    }
    function dashboardRecordFormId(section) {
      if (section === "welcome_automations") return "welcome-automation-form";
      if (section === "utility_configs") return "utility-config-form";
      if (section === "reaction_role_panels") return "reaction-role-panel-form";
      return "";
    }
    function createDashboardRecordCard(section, record, form) {
      const card = document.createElement("div");
      const id = dashboardRecordId(section, record);
      const text = dashboardRecordText(section, record || {}, form);
      card.className = "notification";
      card.dataset.dashboardRecordCard = "";
      card.dataset.removeRow = "";
      card.dataset.section = section;
      card.dataset.recordId = id;
      card.__dashboardRecord = record;
      const row = document.createElement("div");
      row.className = "row-between";
      const details = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = text.title;
      const summary = document.createElement("span");
      summary.textContent = text.summary;
      const small = document.createElement("small");
      small.textContent = text.detail;
      details.append(title, summary, small);
      const actions = document.createElement("div");
      actions.className = "inline-actions";
      const edit = document.createElement("button");
      edit.type = "button";
      edit.dataset.dashboardRecordEdit = "";
      edit.dataset.formId = dashboardRecordFormId(section);
      edit.textContent = "Edit";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.dataset.dashboardRecordDelete = "";
      remove.dataset.section = section;
      remove.dataset.recordId = id;
      remove.dataset.guildId = form?.elements?.guild_id?.value || record?.guild_id || "";
      remove.dataset.confirm = `Delete ${text.title}?`;
      remove.textContent = "Delete";
      const result = document.createElement("span");
      result.className = "result muted";
      result.dataset.dashboardRecordResult = "";
      actions.append(edit, remove, result);
      row.append(details, actions);
      const script = document.createElement("script");
      script.type = "application/json";
      script.dataset.dashboardRecordJson = "";
      script.textContent = JSON.stringify(record || {});
      card.append(row, script);
      return card;
    }
    function upsertDashboardRecordCard(section, record, form) {
      const list = document.querySelector(`[data-dashboard-record-list][data-section="${CSS.escape(section)}"]`);
      if (!list || !record) return;
      const id = dashboardRecordId(section, record);
      const card = createDashboardRecordCard(section, record, form);
      const existing = id ? list.querySelector(`[data-dashboard-record-card][data-record-id="${CSS.escape(id)}"]`) : null;
      if (existing) existing.replaceWith(card);
      else list.appendChild(card);
      syncEmptyDashboardRecords(list);
    }
    const REFRESH_AFTER_SAVE_ROUTES = new Set([
      "/api/admin/faction",
      "/api/admin/faction-member",
      "/api/admin/zone",
      "/api/admin/member-action",
      "/api/admin/wage",
      "/api/admin/wallet-adjustment",
      "/api/admin/economy-rule",
      "/api/admin/shop-item",
      "/api/admin/shop-bundle",
      "/api/admin/moderation-guard",
      "/api/admin/link-enforcement",
      "/api/admin/on-screen-message",
      "/api/admin/server-control",
      "/api/admin/guild-access",
      "/api/admin/link-server",
      "/api/owner/guild-action",
    ]);
    function shouldRefreshAfterSave(form) {
      if (!form || form.classList.contains("inline-action") || form.dataset.scenarioActionForm) return false;
      const route = String(form.dataset.route || "").split("?")[0];
      if (route === "/api/admin/server-control" || route === "/api/admin/moderation-guard") return false;
      return REFRESH_AFTER_SAVE_ROUTES.has(route);
    }
    function removeInlineActionItem(form) {
      const item = form.closest("[data-scenario-event-row]")
        || form.closest("[data-dashboard-record-card]")
        || form.closest("[data-template-card]")
        || form.closest("tr")
        || form.closest("li")
        || form.closest(".notification")
        || form.closest(".owner-server-card");
      if (!item) return false;
      item.remove();
      return true;
    }
    function scenarioStatusIsPending(text, uploadStatus) {
      const combined = `${text || ""} ${uploadStatus || ""}`.toLowerCase();
      return combined.includes("upload starting")
        || combined.includes("upload queued")
        || combined.includes("upload requested")
        || combined.includes("retry pending")
        || combined.includes("waiting")
        || combined.includes("waiting_for_bot_upload")
        || combined.includes("queued in the bot")
        || combined.includes("queued for the bot worker");
    }
    function scenarioStatusClass(text, uploadStatus) {
      const combined = `${text || ""} ${uploadStatus || ""}`.toLowerCase();
      if (combined.includes("fail") || combined.includes("blocked")) return "bad";
      if (combined.includes("done") || combined.includes("uploaded") || combined.includes("complete")) return "ok";
      if (scenarioStatusIsPending(text, uploadStatus)) return "warn";
      if (combined.includes("pause") || combined.includes("cancel")) return "info";
      return "";
    }
    function setScenarioRowStatus(row, eventData) {
      if (!row || !eventData) return;
      const statusCell = row.querySelector("[data-scenario-status]");
      const status = eventData.status || "";
      const uploadStatus = eventData.upload_status || "";
      const uploadError = eventData.upload_error || "";
      row.dataset.eventUpload = uploadStatus;
      row.dataset.eventSearch = `${row.dataset.eventSearch || ""} ${status} ${uploadStatus} ${uploadError}`.toLowerCase();
      row.classList.remove("status-ok", "status-warn", "status-bad", "status-info");
      const stateClass = scenarioStatusClass(status, uploadStatus);
      if (stateClass) row.classList.add(`status-${stateClass}`);
      if (statusCell) {
        statusCell.textContent = status || "Saved";
        if (scenarioStatusIsPending(status, uploadStatus)) {
          const checking = document.createElement("small");
          checking.className = "muted";
          checking.textContent = "Checking upload status automatically...";
          statusCell.append(document.createElement("br"), checking);
        }
        if (uploadError) {
          const detail = document.createElement("small");
          detail.className = "muted";
          detail.textContent = uploadError;
          statusCell.append(document.createElement("br"), detail);
        }
      }
      row.querySelectorAll('[name="action"][value="upload"]').forEach((input) => {
        const retryForm = input.closest("form");
        if (retryForm) retryForm.hidden = uploadStatus !== "failed";
      });
    }
    function pollScenarioStatusRow(row) {
      if (!row || row.dataset.statusPoll === "done") return;
      const eventId = row.getAttribute("data-scenario-event-row");
      const statusCell = row.querySelector("[data-scenario-status]");
      const currentStatus = statusCell ? statusCell.textContent : "";
      if (!eventId || !scenarioStatusIsPending(currentStatus, row.dataset.eventUpload)) return;
      row.dataset.statusPoll = "active";
      let attempts = 0;
      const poll = async () => {
        attempts += 1;
        const params = new URLSearchParams(window.location.search);
        params.set("event_id", eventId);
        params.set("dashboard_mode", "{{ mode }}");
        try {
          const response = await fetch(secureDashboardUrl(`/api/admin/scenario-event-status?${params.toString()}`), {
            headers: {"Accept": "application/json", "X-Requested-With": "fetch"},
            credentials: "same-origin",
          });
          const body = await response.json().catch(() => ({}));
          if (response.ok && body.event) {
            setScenarioRowStatus(row, body.event);
            if (!scenarioStatusIsPending(body.event.status, body.event.upload_status)) {
              row.dataset.statusPoll = "done";
              return;
            }
          }
        } catch (error) {}
        if (attempts < 120 && row.isConnected) {
          window.setTimeout(poll, attempts < 6 ? 2500 : 5000);
        } else {
          row.dataset.statusPoll = "paused";
          if (statusCell && scenarioStatusIsPending(statusCell.textContent, row.dataset.eventUpload)) {
            const paused = document.createElement("small");
            paused.className = "muted";
            paused.textContent = "Still waiting for the bot worker. This row will update after refresh if the worker completes later.";
            statusCell.append(document.createElement("br"), paused);
          }
        }
      };
      window.setTimeout(poll, 1500);
    }
    function pveEventsUrl() {
      const params = new URLSearchParams(window.location.search);
      params.set("section", "pve");
      params.set("pve_tool", "events");
      if (!params.get("guild_id") && "{{ server.guild_id if server else '' }}") params.set("guild_id", "{{ server.guild_id if server else '' }}");
      return `${window.location.pathname}?${params.toString()}#pve-workshop`;
    }
    document.querySelectorAll("[data-scenario-event-row]").forEach(pollScenarioStatusRow);
    document.querySelectorAll(".admin-form").forEach((form) => {
      if (form.dataset.route) {
        if (!form.getAttribute("method")) form.setAttribute("method", "post");
        if (!form.getAttribute("action")) form.setAttribute("action", secureDashboardUrl(form.dataset.route));
      }
      form.addEventListener("submit", async (event) => {
        if (event.submitter && event.submitter.matches && event.submitter.matches("[data-zone-map-hit]")) return;
        event.preventDefault();
        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
        form.querySelectorAll("[data-item-picker]").forEach((picker) => {
          const output = form.querySelector("[data-picker-output]");
          const selected = picker.querySelector("[data-picker-item]")?.value?.trim();
          if (output && selected && !output.value.trim()) appendPickerLine(picker, output);
        });
        const data = new FormData(form);
        const result = form.querySelector(".result");
        const button = event.submitter || form.querySelector('button[type="submit"]');
        const originalButtonText = button ? button.textContent : "";
        let payload = {};
        data.forEach((value, key) => {
          if (value === "") return;
          const parsed = formValue(value);
          if (payload[key] !== undefined) {
            payload[key] = Array.isArray(payload[key]) ? payload[key].concat([parsed]) : [payload[key], parsed];
          } else {
            payload[key] = parsed;
          }
        });
        payload.dashboard_mode = "{{ mode }}";
        const featureBoxes = form.querySelectorAll('input[name^="feature_"]');
        if (featureBoxes.length) {
          payload.features = {};
          featureBoxes.forEach((box) => {
            payload.features[box.name.replace("feature_", "")] = box.checked;
            delete payload[box.name];
          });
        }
        if (result) {
          result.classList.remove("error", "success");
          result.textContent = "Saving...";
        }
        if (button) {
          button.disabled = true;
          button.textContent = form.dataset.scenarioActionForm ? "Working..." : "Saving...";
        }
        const token = new URLSearchParams(window.location.search).get("token");
        const route = token ? `${form.dataset.route}?token=${encodeURIComponent(token)}` : form.dataset.route;
        const routePath = String(form.dataset.route || "").split("?")[0];
        try {
          const response = await fetch(secureDashboardUrl(route), {
            method: "POST",
            headers: {"Content-Type": "application/json", "Accept": "application/json", "X-Requested-With": "fetch"},
            credentials: "same-origin",
            body: JSON.stringify(payload)
          });
          let body = {};
          try { body = await response.json(); } catch (error) {}
          if (result) {
            result.classList.toggle("success", response.ok);
            result.classList.toggle("error", !response.ok);
            result.textContent = response.ok ? (body.note || "Saved") : (body.error || "Rejected");
          }
          if (response.ok) {
            const preview = form.querySelector("[data-save-preview]");
            if (preview && body.recipe) {
              preview.hidden = false;
              preview.textContent = JSON.stringify(body.recipe.generated_json || body.recipe, null, 2);
            }
          }
          if (response.ok && routePath === "/api/admin/embed-template" && body.template) {
            upsertEmbedTemplateCard(body.template, form);
            if (result) result.textContent = "Saved embed template.";
            return;
          }
          const dashboardRecordRoute = DASHBOARD_RECORD_SAVE_ROUTES[routePath];
          if (response.ok && dashboardRecordRoute && body[dashboardRecordRoute.bodyKey]) {
            upsertDashboardRecordCard(dashboardRecordRoute.section, body[dashboardRecordRoute.bodyKey], form);
            if (result) result.textContent = dashboardRecordRoute.message;
            return;
          }
          if (response.ok && form.dataset.scenarioActionForm) {
            const action = String(payload.action || "").toLowerCase();
            const row = form.closest("[data-scenario-event-row]");
            const statusCell = row ? row.querySelector("[data-scenario-status]") : null;
            if (action === "delete" || action === "cancel") {
              if (row) row.remove();
              return;
            }
            const status = body.event && body.event.status ? body.event.status : (action === "pause" ? "Paused by dashboard" : "Saved");
            if (statusCell) statusCell.textContent = status;
            if (action === "upload" && body.upload && body.upload.ok === false && statusCell) {
              const messages = Array.isArray(body.upload.messages) ? body.upload.messages.slice(-2).join(" | ") : "";
              statusCell.textContent = messages ? `Native CE XML upload failed: ${messages}` : "Native CE XML upload failed";
            }
            if (body.upload_started && row) pollScenarioStatusRow(row);
            return;
          }
          if (response.ok && routePath === "/api/admin/scenario-event") {
            const savedCount = body.created_count || (Array.isArray(body.events) ? body.events.length : 1);
            if (result) result.textContent = body.note || `Saved ${savedCount} event${savedCount === 1 ? "" : "s"}.`;
            const row = body.event ? document.querySelector(`[data-scenario-event-row="${CSS.escape(String(body.event.id || ""))}"]`) : null;
            if (row && body.event) {
              setScenarioRowStatus(row, body.event);
              pollScenarioStatusRow(row);
            } else if (body.event || savedCount) {
              if (result) result.textContent = `${body.note || "Saved event."} Opening Live Events...`;
              window.setTimeout(() => { window.location.href = pveEventsUrl(); }, 900);
            }
            return;
          }
          if (response.ok && form.classList.contains("inline-action")) {
            const action = String(payload.action || "").toLowerCase();
            if (action === "delete") {
              if (removeInlineActionItem(form)) return;
            }
            if (action === "remove" || action === "leave" || action === "purge") {
              if (removeInlineActionItem(form)) return;
            }
            window.location.reload();
          }
          if (response.ok && shouldRefreshAfterSave(form)) {
            if (result) result.textContent = body.note || "Saved. Refreshing...";
            window.setTimeout(() => window.location.reload(), 650);
          }
        } catch (error) {
          const message = window.location.protocol === "http:"
            ? "Open the secure HTTPS dashboard and try again."
            : `Request failed: ${error && error.message ? error.message : error}`;
          if (result) {
            result.classList.remove("success");
            result.classList.add("error");
            result.textContent = message;
          }
          if (form.getAttribute("action") && form.getAttribute("method")) {
            if (result) result.textContent = "Retrying with normal form submit...";
            HTMLFormElement.prototype.submit.call(form);
            return;
          }
          window.alert(message);
        } finally {
          if (button && button.isConnected) {
            button.disabled = false;
            button.textContent = originalButtonText;
          }
        }
      });
    });
    document.querySelectorAll("[data-item-picker]").forEach((picker) => {
      const slotSelect = picker.querySelector("[data-picker-slot]");
      if (picker.dataset.pickerMode === "loadout") {
        if (slotSelect && !slotSelect.value) slotSelect.value = DEFAULT_LOADOUT_SLOT;
        rebuildPickerOptions(picker, slotSelect?.value || DEFAULT_LOADOUT_SLOT);
        if (slotSelect) syncLoadoutPickerSlot(slotSelect);
      } else if (slotSelect && slotSelect.value) {
        picker.dataset.pickerGroup = slotSelect.value;
      } else if (!picker.dataset.pickerGroup) {
        picker.dataset.pickerGroup = "cargo";
      }
      renderVisualPicker(picker);
    });
    document.querySelectorAll("select[data-visual-select]").forEach((select) => renderVisualSelect(select));
    document.querySelectorAll("[data-live-output]").forEach((preview) => syncLiveOutput(preview.closest("form")));
    document.querySelectorAll("[data-wage-target]").forEach((select) => {
      const form = select.closest("form");
      function syncTargetType() {
        const selected = select.selectedOptions && select.selectedOptions[0];
        if (form && form.elements.target_type && selected && selected.dataset.targetType) {
          form.elements.target_type.value = selected.dataset.targetType;
        }
      }
      select.addEventListener("change", syncTargetType);
      syncTargetType();
    });
    document.querySelectorAll("[data-wallet-target]").forEach((select) => {
      const form = select.closest("form");
      function syncWalletTargetType() {
        const selected = select.selectedOptions && select.selectedOptions[0];
        if (form && form.elements.target_type && selected && selected.dataset.targetType) {
          form.elements.target_type.value = selected.dataset.targetType;
        }
      }
      select.addEventListener("change", syncWalletTargetType);
      syncWalletTargetType();
    });
    document.querySelectorAll("[data-wage-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const form = document.getElementById("wage-form");
        if (!form) return;
        form.elements.id.value = button.dataset.id || "";
        form.elements.target_type.value = button.dataset.targetType || "user";
        form.elements.target_id.value = button.dataset.targetId || "";
        form.elements.amount.value = button.dataset.amount || 0;
        form.elements.cadence.value = button.dataset.cadence || "weekly";
        form.elements.active.value = button.dataset.active || "true";
        form.scrollIntoView({behavior: "smooth", block: "center"});
        form.elements.amount.focus();
      });
    });
    document.querySelectorAll("[data-shop-edit]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const form = document.getElementById("shop-edit-form");
        if (!form) return;
        event.preventDefault();
        form.elements.item_name.value = button.dataset.item || "";
        form.elements.price.value = button.dataset.price || 0;
        form.elements.category.value = button.dataset.category || "General";
        form.elements.enabled.value = button.dataset.enabled || "true";
        form.elements.daily_limit.value = button.dataset.limit || 0;
        form.elements.allowed_role_ids.value = button.dataset.roles || "";
        form.elements.blocked_user_ids.value = button.dataset.blocked || "";
        form.classList.add("dashboard-edit-modal");
        form.scrollIntoView({behavior: "smooth", block: "center"});
        form.elements.price.focus();
      });
    });
    document.querySelectorAll("[data-shop-search]").forEach((input) => {
      const section = input.closest("[data-shop-list]") || input.closest("article") || document;
      const category = section.querySelector("[data-shop-category]");
      const count = section.querySelector("[data-shop-count]");
      function filterShop() {
        const query = input.value.trim().toLowerCase();
        const categoryValue = category ? category.value.trim().toLowerCase() : "";
        let visible = 0;
        section.querySelectorAll("[data-shop-row]").forEach((row) => {
          const search = row.dataset.search || "";
          const rowCategory = row.dataset.category || "";
          const matchesText = !query || search.includes(query);
          const matchesCategory = !categoryValue || rowCategory === categoryValue;
          const show = matchesText && matchesCategory;
          row.hidden = !show;
          if (show) visible += 1;
        });
        if (count) count.textContent = visible;
      }
      input.addEventListener("input", filterShop);
      if (category) category.addEventListener("change", filterShop);
      filterShop();
    });
    document.querySelectorAll("[data-event-search]").forEach((input) => {
      const section = input.closest("article") || document;
      const status = section.querySelector("[data-event-status]");
      function filterEvents() {
        const query = input.value.trim().toLowerCase();
        const statusValue = status ? status.value.trim().toLowerCase() : "";
        section.querySelectorAll("[data-event-row]").forEach((row) => {
          const matchesText = !query || row.dataset.eventSearch.includes(query);
          let matchesStatus = true;
          if (statusValue === "active") matchesStatus = row.dataset.eventEnabled === "true";
          if (statusValue === "paused") matchesStatus = row.dataset.eventEnabled !== "true";
          if (statusValue === "permanent") matchesStatus = row.dataset.eventPermanent === "true";
          if (statusValue === "failed") matchesStatus = row.dataset.eventUpload === "failed";
          row.style.display = matchesText && matchesStatus ? "" : "none";
        });
      }
      input.addEventListener("input", filterEvents);
      status?.addEventListener("change", filterEvents);
    });
    document.querySelectorAll("[data-scenario-edit]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const form = document.getElementById("scenario-event-form");
        if (!form) return;
        event.preventDefault();
        form.elements.event_id.value = button.dataset.id || "";
        form.elements.name.value = button.dataset.name || "";
        form.elements.event_type.value = button.dataset.type === "loot_crate" ? "airdrop" : (button.dataset.type || "airdrop");
        if (form.elements.spawn_preset && button.dataset.preset) form.elements.spawn_preset.value = button.dataset.preset;
        form.elements.class_name.value = button.dataset.class || "";
        form.elements.x.value = button.dataset.x || 7500;
        form.elements.y.value = button.dataset.y || 0;
        form.elements.z.value = button.dataset.z || 7500;
        form.elements.count.value = button.dataset.count || 1;
        form.elements.radius.value = button.dataset.radius || 35;
        form.elements.permanent.value = button.dataset.permanent || "false";
        form.elements.restarts.value = button.dataset.restarts || 1;
        form.elements.loot_preset.value = button.dataset.loot || "none";
        form.elements.visual_marker.value = button.dataset.marker || "true";
        if (form.elements.scene_type) form.elements.scene_type.value = button.dataset.scene || "compact_crater";
        form.elements.guard_class.value = button.dataset.guard || "";
        form.elements.guard_count.value = button.dataset.guardCount || 0;
        form.elements.guard_radius.value = button.dataset.guardRadius || 35;
        if (form.elements.gas_lifetime) form.elements.gas_lifetime.value = button.dataset.gasLifetime || 1800;
        if (form.elements.gas_particle) form.elements.gas_particle.value = button.dataset.gasParticle || "server_default";
        form.dispatchEvent(new CustomEvent("scenario-prefill"));
        form.classList.add("dashboard-edit-modal");
        form.scrollIntoView({behavior: "smooth", block: "start"});
        form.elements.class_name.focus();
      });
    });
    document.querySelectorAll("[data-faction-edit]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const form = document.getElementById("faction-edit-form");
        if (!form) return;
        event.preventDefault();
        function chooseValue(select, value, fallbackLabel) {
          if (!select || value === undefined || value === null) return;
          const text = String(value || "").trim();
          if (!text) {
            select.value = "";
            return;
          }
          const option = Array.from(select.options).find((item) => item.value === text || item.dataset.channelId === text);
          if (option) {
            select.value = option.value;
            return;
          }
          const created = new Option(fallbackLabel || text, text);
          created.dataset.legacy = "true";
          select.add(created);
          select.value = text;
        }
        form.elements.name.value = button.dataset.name || "";
        chooseValue(form.elements.leader_id, button.dataset.leader || "", button.dataset.leader || "Stored leader");
        chooseValue(form.elements.role_id, button.dataset.role || "", button.dataset.role || "Stored faction role");
        form.elements.colour.value = button.dataset.colour || "#8d963e";
        if (form.elements.alert_channel_key && button.dataset.channel) {
          chooseValue(form.elements.alert_channel_key, button.dataset.channel, button.dataset.channel);
        }
        const result = form.querySelector(".result");
        if (result) result.textContent = `Editing ${button.dataset.name || "faction"} now.`;
        form.classList.add("dashboard-edit-modal");
        form.scrollIntoView({behavior: "smooth", block: "center"});
        form.elements.name.focus();
      });
    });
    document.querySelectorAll("[data-member-id-select]").forEach((select) => {
      const form = select.closest("form");
      if (!form) return;
      const nameField = form.elements.member_name;
      function syncMemberName() {
        const option = select.selectedOptions[0];
        if (nameField) nameField.value = option ? (option.dataset.memberName || option.textContent || "") : "";
      }
      select.addEventListener("change", syncMemberName);
      syncMemberName();
    });
    document.querySelectorAll("[data-scenario-preset]").forEach((presetSelect) => {
      const form = presetSelect.closest("form");
      if (!form) return;
      const typeSelect = form.querySelector("[data-scenario-type]");
      const classInput = form.querySelector("[data-scenario-class]");
      function normalScenarioType(value) {
        return value === "loot_crate" ? "airdrop" : value;
      }
      function optionMatchesType(item, eventType) {
        const itemType = normalScenarioType(item.dataset.type || "");
        return item.value === "custom" || !itemType || itemType === normalScenarioType(eventType);
      }
      function defaultPresetForType(eventType) {
        if (!typeSelect) return "";
        const typeOption = Array.from(typeSelect.options).find((item) => item.value === normalScenarioType(eventType));
        return typeOption ? (typeOption.dataset.defaultPreset || "") : "";
      }
      function chooseFirstPresetForType(forceDefault = false) {
        if (!typeSelect) return;
        const activeType = normalScenarioType(typeSelect.value);
        const current = presetSelect.selectedOptions[0];
        const options = Array.from(presetSelect.options);
        options.forEach((item) => {
          const visible = optionMatchesType(item, activeType);
          item.hidden = !visible;
          item.disabled = !visible;
        });
        if (!forceDefault && current && !current.disabled && optionMatchesType(current, activeType)) return;
        const preferredValue = defaultPresetForType(activeType);
        const preferred = options.find((item) => item.value === preferredValue && !item.disabled);
        const match = preferred || options.find((item) => optionMatchesType(item, activeType) && !item.disabled);
        if (match) presetSelect.value = match.value;
      }
      function syncScenarioPreset(event) {
        const selectedBeforeFilter = presetSelect.selectedOptions[0];
        if (event && event.target === typeSelect) {
          chooseFirstPresetForType(true);
        } else if (event && event.target === presetSelect && typeSelect && selectedBeforeFilter && selectedBeforeFilter.dataset.type && normalScenarioType(selectedBeforeFilter.dataset.type) !== normalScenarioType(typeSelect.value)) {
          typeSelect.value = normalScenarioType(selectedBeforeFilter.dataset.type);
          chooseFirstPresetForType(false);
        } else if (event && event.type === "scenario-prefill") {
          chooseFirstPresetForType(false);
        } else {
          chooseFirstPresetForType(false);
        }
        const option = presetSelect.selectedOptions[0];
        if (!option) return;
        const customClass = option.value === "custom" || option.value === "custom_vehicle";
        if (classInput) {
          classInput.readOnly = !customClass;
          classInput.placeholder = customClass ? "Type the exact DayZ classname" : "Locked to selected spawn type";
        }
        if (typeSelect && option.dataset.type) typeSelect.value = normalScenarioType(option.dataset.type);
        if (!customClass && option.dataset.class) form.elements.class_name.value = option.dataset.class;
        if (customClass && !form.elements.class_name.value) form.elements.class_name.value = "";
        if (option.dataset.count) form.elements.count.value = option.dataset.count;
        if (option.dataset.radius) form.elements.radius.value = option.dataset.radius;
        if (option.dataset.loot && form.elements.loot_preset) form.elements.loot_preset.value = option.dataset.loot;
        if (option.dataset.gasLifetime && form.elements.gas_lifetime) form.elements.gas_lifetime.value = option.dataset.gasLifetime;
        if (option.dataset.gasParticle && form.elements.gas_particle) form.elements.gas_particle.value = option.dataset.gasParticle;
        if (option.dataset.permanent && form.elements.permanent) form.elements.permanent.value = option.dataset.permanent;
      }
      presetSelect.addEventListener("change", syncScenarioPreset);
      if (typeSelect) typeSelect.addEventListener("change", syncScenarioPreset);
      form.addEventListener("scenario-prefill", syncScenarioPreset);
      form.addEventListener("submit", syncScenarioPreset);
      syncScenarioPreset();
    });
    document.querySelectorAll("[data-scenario-location-preset]").forEach((select) => {
      const form = select.closest("form");
      if (!form) return;
      function syncScenarioLocation() {
        const option = select.selectedOptions[0];
        if (!option || !option.value) return;
        if (form.elements.x && option.dataset.x) form.elements.x.value = option.dataset.x;
        if (form.elements.z && option.dataset.z) form.elements.z.value = option.dataset.z;
        if (form.elements.name && !String(form.elements.name.value || "").trim()) {
          form.elements.name.value = option.value;
        }
      }
      select.addEventListener("change", syncScenarioLocation);
    });
    document.querySelectorAll("[data-zombie-mix-builder]").forEach((builder) => {
      const rows = builder.querySelector("[data-zombie-mix-rows]");
      const hidden = builder.querySelector("[data-zombie-mix-value]");
      const addButton = builder.querySelector("[data-add-zombie-row]");
      const zombieOptions = [
        ["ZmbM_CitizenASkinny_Brown", "Civilian infected"],
        ["ZmbM_SoldierNormal", "Military infected"],
        ["ZmbM_usSoldier_Heavy_Woodland", "Heavy military infected"],
        ["ZmbM_PolicemanFat", "Police infected"],
        ["ZmbM_DoctorFat", "Medical infected"],
        ["ZmbM_FirefighterNormal", "Firefighter infected"],
        ["ZmbM_PrisonerSkinny", "Prisoner infected"],
        ["ZmbF_MilkMaidOld_Green", "Village infected"],
        ["ZmbF_JoggerSkinny_Brown", "Runner infected"]
      ];
      function syncMix() {
        const lines = [];
        rows.querySelectorAll("[data-zombie-row]").forEach((row) => {
          const select = row.querySelector("[data-zombie-class]");
          const count = Math.max(1, Math.min(250, Number(row.querySelector("[data-zombie-count]").value || 1)));
          if (select.value) lines.push(`${count} ${select.value}`);
        });
        hidden.value = lines.join("\n");
      }
      function addRow(className = "ZmbM_SoldierNormal", count = 10) {
        const row = document.createElement("div");
        row.className = "mini-grid";
        row.dataset.zombieRow = "1";
        const options = zombieOptions.map(([value, label]) => `<option value="${value}" ${value === className ? "selected" : ""}>${label}</option>`).join("");
        row.innerHTML = `<label>Type <select data-zombie-class>${options}</select></label><label>Count <input data-zombie-count type="number" min="1" max="250" value="${count}"></label><label>Remove <button type="button" data-remove-zombie-row>Remove</button></label>`;
        rows.appendChild(row);
        row.querySelectorAll("select,input").forEach((input) => input.addEventListener("input", syncMix));
        row.querySelector("[data-remove-zombie-row]").addEventListener("click", () => {
          row.remove();
          syncMix();
        });
        syncMix();
      }
      if (addButton) addButton.addEventListener("click", () => addRow());
      addRow("ZmbM_SoldierNormal", 10);
    });
    document.querySelectorAll("[data-zone-map]").forEach((map) => {
      const form = map.closest("form");
      if (!form) return;
      const size = Number(map.dataset.mapSize || 15360);
      const boundaryPoints = [];
      const radiusInput = form.querySelector("[data-zone-radius]");
      const radiusSlider = form.querySelector("[data-zone-radius-slider]");
      const shapeSelect = form.querySelector("[data-zone-shape]");
      const radiusLabel = form.querySelector("[data-zone-radius-label]");
      const shapeLabel = form.querySelector("[data-zone-shape-label]");
      const boundaryCount = form.querySelector("[data-boundary-count]");
      const boundaryField = form.querySelector("[data-boundary-points]");
      const boundaryLayer = form.querySelector("[data-boundary-layer]");
      const colourInput = form.querySelector("[data-zone-colour]");
      const factionSelect = form.elements.faction_name;
      const saveButton = form.querySelector("[data-zone-save-button]") || form.querySelector('button[type="submit"]');
      const deleteCurrentButton = form.querySelector("[data-zone-delete-current]");
      const result = form.querySelector(".result");
      const popover = map.querySelector("[data-zone-popover]");
      const zoneFields = {
        guildId: form.querySelector('[name="guild_id"]'),
        zoneId: form.querySelector('[name="zone_id"]'),
        name: form.querySelector('[name="name"]'),
        type: form.querySelector('[name="zone_type"]'),
        x: form.querySelector('[name="x"]'),
        y: form.querySelector('[name="y"]'),
        shape: form.querySelector('[name="shape"]'),
        channel: form.querySelector('[name="channel_key"]'),
        role: form.querySelector('[name="role_id"]'),
        faction: form.querySelector('[name="faction_name"]'),
        enabled: form.querySelector('[name="enabled"]'),
        action: form.querySelector('[name="action"]'),
        banType: form.querySelector('[name="ban_type"]'),
        banMinutes: form.querySelector('[name="ban_duration_minutes"]'),
        triggerTerritory: form.querySelector('[name="trigger_territory"]'),
        triggers: form.querySelector('[name="triggers"]'),
        ignored: form.querySelector('[name="ignored_gamertags"]'),
      };
      const mapMetricFields = {
        width: form.querySelector("[data-map-render-width]"),
        height: form.querySelector("[data-map-render-height]"),
        pointerX: form.querySelector("[data-map-pointer-x]"),
        pointerY: form.querySelector("[data-map-pointer-y]"),
        percentX: form.querySelector("[data-map-percent-x]"),
        percentY: form.querySelector("[data-map-percent-y]"),
      };
      const zonePalette = [
        "#ff4d6d",
        "#38bdf8",
        "#a3e635",
        "#f97316",
        "#c084fc",
        "#22c55e",
        "#facc15",
        "#14b8a6",
        "#f472b6",
        "#60a5fa",
      ];

      function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, (char) => ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        }[char]));
      }

      function clampPercent(value) {
        return Math.max(2, Math.min(98, Number(value) || 0));
      }

      function mapHitRect() {
        const hitLayer = map.querySelector("[data-zone-map-hit]") || map.querySelector(".zone-map-hit-layer");
        const rect = (hitLayer || map).getBoundingClientRect();
        if (rect.width && rect.height) return rect;
        return map.getBoundingClientRect();
      }

      function updateMapClickMetrics(event = null) {
        const rect = mapHitRect();
        if (!rect.width || !rect.height) return;
        if (mapMetricFields.width) mapMetricFields.width.value = String(Math.round(rect.width));
        if (mapMetricFields.height) mapMetricFields.height.value = String(Math.round(rect.height));
        if (event && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
          const pointerX = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
          const pointerY = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
          if (mapMetricFields.pointerX) mapMetricFields.pointerX.value = String(pointerX);
          if (mapMetricFields.pointerY) mapMetricFields.pointerY.value = String(pointerY);
          if (mapMetricFields.percentX) mapMetricFields.percentX.value = String((pointerX / rect.width) * 100);
          if (mapMetricFields.percentY) mapMetricFields.percentY.value = String((pointerY / rect.height) * 100);
        }
      }

      function getZonePoint(zone = {}) {
        const x = Number(zone.x ?? zone.center_x ?? (zoneFields.x ? zoneFields.x.value : 0) ?? 0);
        const z = Number(zone.z ?? zone.y ?? zone.center_z ?? zone.center_y ?? (zoneFields.y ? zoneFields.y.value : 0) ?? 0);
        return {
          x,
          z,
          xPercent: Math.max(0, Math.min(100, (x / size) * 100)),
          yPercent: Math.max(0, Math.min(100, 100 - ((z / size) * 100))),
        };
      }

      function hideZonePopover() {
        if (popover) popover.hidden = true;
      }

      function saveZoneFromPopover() {
        applyZonePopoverFields();
        hideZonePopover();
        if (form.requestSubmit) {
          form.requestSubmit(saveButton || undefined);
        } else if (saveButton) {
          saveButton.click();
        }
      }

      function applyZonePopoverFields() {
        if (!popover || popover.hidden) return;
        const popoverFields = {
          name: popover.querySelector('[data-zone-popover-field="name"]'),
          type: popover.querySelector('[data-zone-popover-field="zone_type"]'),
          x: popover.querySelector('[data-zone-popover-field="x"]'),
          y: popover.querySelector('[data-zone-popover-field="y"]'),
          radius: popover.querySelector('[data-zone-popover-field="radius"]'),
          colour: popover.querySelector('[data-zone-popover-field="colour"]'),
          enabled: popover.querySelector('[data-zone-popover-field="enabled"]'),
          action: popover.querySelector('[data-zone-popover-field="action"]'),
        };
        if (zoneFields.name && popoverFields.name) zoneFields.name.value = popoverFields.name.value;
        if (zoneFields.type && popoverFields.type) setSelectValue(zoneFields.type, popoverFields.type.value);
        if (zoneFields.x && popoverFields.x) zoneFields.x.value = popoverFields.x.value;
        if (zoneFields.y && popoverFields.y) zoneFields.y.value = popoverFields.y.value;
        if (zoneFields.enabled && popoverFields.enabled) setSelectValue(zoneFields.enabled, popoverFields.enabled.value);
        if (zoneFields.action && popoverFields.action) setSelectValue(zoneFields.action, popoverFields.action.value);
        if (popoverFields.radius) syncRadius(popoverFields.radius.value);
        if (popoverFields.colour) syncZoneColour(popoverFields.colour.value);
        placeCursorFromForm();
      }

      function showZonePopover(zone = {}, mode = "edit") {
        if (!popover) return;
        const point = getZonePoint(zone);
        const type = zone.zone_type || zone.type || (zoneFields.type ? zoneFields.type.value : "radar");
        const radius = zone.radius ?? zone.radius_m ?? (radiusInput ? radiusInput.value : 250);
        const zoneName = zone.name || (zoneFields.name ? zoneFields.name.value : "");
        const title = mode === "new" ? "New zone draft" : (zoneName || "Zone");
        const colour = zone.display_colour || zone.colour || zone.color || (colourInput ? colourInput.value : zonePalette[0]);
        const enabled = zone.enabled === false ? "false" : (zoneFields.enabled ? zoneFields.enabled.value : "true");
        const action = zone.action || (zoneFields.action ? zoneFields.action.value : "none");
        const option = (value, label, selected) => `<option value="${escapeHtml(value)}" ${String(selected) === String(value) ? "selected" : ""}>${escapeHtml(label)}</option>`;
        popover.style.setProperty("--zone-colour", colour);
        popover.style.left = `${clampPercent(point.xPercent)}%`;
        popover.style.top = `${Math.max(8, Math.min(92, point.yPercent))}%`;
        popover.dataset.side = point.xPercent > 62 ? "left" : "right";
        popover.innerHTML = `
          <strong>${escapeHtml(title)}</strong>
          <span>Edit this zone here, then save or close.</span>
          <div class="zone-popover-grid">
            <label>Name <input data-zone-popover-field="name" value="${escapeHtml(zoneName || title)}"></label>
            <label>Type <select data-zone-popover-field="zone_type">
              ${option("radar", "Radar", type)}
              ${option("safe", "Safe", type)}
              ${option("pvp", "PVP", type)}
              ${option("action", "Action", type)}
              ${option("faction", "Faction", type)}
              ${option("custom", "Custom", type)}
            </select></label>
            <label>X <input data-zone-popover-field="x" type="number" value="${Math.round(point.x)}"></label>
            <label>Z <input data-zone-popover-field="y" type="number" value="${Math.round(point.z)}"></label>
            <label>Radius <input data-zone-popover-field="radius" type="number" min="10" step="10" value="${escapeHtml(radius)}"></label>
            <label>Colour <input data-zone-popover-field="colour" type="color" value="${escapeHtml(colour)}"></label>
            <label>Enabled <select data-zone-popover-field="enabled">${option("true", "On", enabled)}${option("false", "Off", enabled)}</select></label>
            <label>Action <select data-zone-popover-field="action">${option("none", "Notify", action)}${option("manhunt", "Manhunt", action)}${option("ban", "Ban", action)}</select></label>
          </div>
          <div class="zone-popover-actions">
            <button type="button" data-popover-save>${mode === "new" ? "Save Zone" : "Save Changes"}</button>
            ${mode === "edit" ? '<button type="button" data-popover-delete>Delete</button>' : ""}
            <button type="button" data-popover-close>Close</button>
          </div>`;
        popover.hidden = false;
        popover.querySelector("[data-popover-close]")?.addEventListener("click", hideZonePopover);
        popover.querySelector("[data-popover-save]")?.addEventListener("click", saveZoneFromPopover);
        popover.querySelectorAll("[data-zone-popover-field]").forEach((field) => {
          field.addEventListener("input", applyZonePopoverFields);
          field.addEventListener("change", applyZonePopoverFields);
        });
        popover.querySelector("[data-popover-delete]")?.addEventListener("click", (event) => {
          applyZonePopoverFields();
          deleteZone({
            guild_id: zoneFields.guildId ? zoneFields.guildId.value : "",
            zone_id: zone.id || (zoneFields.zoneId ? zoneFields.zoneId.value : ""),
            zone_type: zoneFields.type ? zoneFields.type.value : type,
            name: zoneFields.name ? zoneFields.name.value : zoneName,
            action: "delete",
            dashboard_mode: "{{ mode }}",
          }, event.currentTarget);
        });
      }

      function syncZoneColour(colour) {
        const value = /^#[0-9a-f]{6}$/i.test(String(colour || "")) ? colour : zonePalette[0];
        map.style.setProperty("--zone-colour", value);
        if (colourInput) colourInput.value = value;
      }

      function setSelectValue(select, value) {
        if (!select || value === undefined || value === null) return;
        const text = String(value);
        const option = Array.from(select.options).find((item) => item.value === text || item.dataset.channelId === text);
        if (option) select.value = option.value;
      }

      function setZoneEditingState(zoneName = "") {
        if (saveButton) saveButton.textContent = zoneName ? "Save Zone Changes" : "Save Zone";
        if (deleteCurrentButton) deleteCurrentButton.disabled = !zoneName;
      }

      function clearZoneEditingState() {
        document.querySelectorAll("[data-zone-edit].editing").forEach((item) => item.classList.remove("editing"));
        if (zoneFields.zoneId) zoneFields.zoneId.value = "";
        setZoneEditingState("");
        hideZonePopover();
      }

      function startNewZoneAt(x, z) {
        clearZoneEditingState();
        const zoneX = Math.max(0, Math.min(size, Math.round(Number(x) || 0)));
        const zoneZ = Math.max(0, Math.min(size, Math.round(Number(z) || 0)));
        const zoneType = zoneFields.type && zoneFields.type.value ? zoneFields.type.value : "radar";
        if (zoneFields.zoneId) zoneFields.zoneId.value = "";
        if (zoneFields.x) zoneFields.x.value = zoneX;
        if (zoneFields.y) zoneFields.y.value = zoneZ;
        if (zoneFields.name) zoneFields.name.value = `New ${zoneType} zone`;
        if (zoneFields.enabled) setSelectValue(zoneFields.enabled, "true");
        if (zoneFields.action && !zoneFields.action.value) setSelectValue(zoneFields.action, "none");
        const existingCount = map.querySelectorAll(".zone-dot").length;
        syncZoneColour(zonePalette[existingCount % zonePalette.length]);
        if (result) result.textContent = `New zone draft at X ${zoneX}, Z ${zoneZ}.`;
      }

      function syncRadius(value) {
        const radius = Math.max(10, Number(value || 250));
        if (radiusInput) radiusInput.value = radius;
        if (radiusSlider) radiusSlider.value = Math.min(Number(radiusSlider.max || radius), radius);
        if (radiusLabel) radiusLabel.textContent = `${radius}m`;
        renderCirclePreview();
      }

      function renderCirclePreview() {
        let cursor = map.querySelector(".zone-cursor");
        if (!cursor || !radiusInput) return;
        let circle = map.querySelector(".zone-preview-circle");
        if (!circle) {
          circle = document.createElement("span");
          circle.className = "zone-preview-circle";
          map.appendChild(circle);
        }
        const radius = Math.max(10, Number(radiusInput.value || 250));
        const width = (radius * 2 / size) * map.clientWidth;
        circle.style.width = `${Math.max(12, width)}px`;
        circle.style.height = `${Math.max(12, width)}px`;
        circle.style.left = cursor.style.left;
        circle.style.top = cursor.style.top;
        circle.style.setProperty("--zone-colour", colourInput ? colourInput.value : zonePalette[0]);
        circle.style.display = shapeSelect && shapeSelect.value === "boundary" ? "none" : "";
      }

      function renderBoundary() {
        map.querySelectorAll(".zone-boundary-point").forEach((point) => point.remove());
        if (boundaryField) boundaryField.value = JSON.stringify(boundaryPoints);
        if (boundaryCount) boundaryCount.textContent = boundaryPoints.length;
        if (!boundaryLayer) return;
        boundaryLayer.innerHTML = "";
        const percentPoints = boundaryPoints.map((point) => `${point.xPercent.toFixed(2)},${point.yPercent.toFixed(2)}`).join(" ");
        if (boundaryPoints.length > 1) {
          const node = document.createElementNS("http://www.w3.org/2000/svg", boundaryPoints.length > 2 ? "polygon" : "polyline");
          node.setAttribute("points", percentPoints);
          node.style.setProperty("--zone-colour", colourInput ? colourInput.value : zonePalette[0]);
          boundaryLayer.appendChild(node);
        }
        boundaryPoints.forEach((point) => {
          const marker = document.createElement("span");
          marker.className = "zone-boundary-point";
          marker.style.left = `${point.xPercent}%`;
          marker.style.top = `${point.yPercent}%`;
          marker.style.setProperty("--zone-colour", colourInput ? colourInput.value : zonePalette[0]);
          map.appendChild(marker);
        });
      }

      function loadBoundaryFromField() {
        if (!boundaryField || !boundaryField.value) return;
        let savedPoints = [];
        try { savedPoints = JSON.parse(boundaryField.value || "[]"); } catch (error) { savedPoints = []; }
        if (!Array.isArray(savedPoints)) return;
        boundaryPoints.length = 0;
        savedPoints.forEach((point) => {
          const x = Number(point.x || 0);
          const y = Number((point.z ?? point.y) || 0);
          boundaryPoints.push({
            x,
            y,
            z: y,
            xPercent: Number(point.xPercent || ((x / size) * 100)),
            yPercent: Number(point.yPercent || (100 - ((y / size) * 100)))
          });
        });
        renderBoundary();
      }

      function placeCursorFromForm() {
        if (!zoneFields.x || !zoneFields.y) return;
        const x = Number(zoneFields.x.value || 0);
        const y = Number(zoneFields.y.value || 0);
        let cursor = map.querySelector(".zone-cursor");
        if (!cursor) {
          cursor = document.createElement("span");
          cursor.className = "zone-cursor";
          map.appendChild(cursor);
        }
        cursor.style.left = `${(x / size) * 100}%`;
        cursor.style.top = `${100 - ((y / size) * 100)}%`;
        renderCirclePreview();
      }

      if (colourInput) colourInput.addEventListener("input", () => {
        syncZoneColour(colourInput.value);
        renderCirclePreview();
        renderBoundary();
      });
      if (factionSelect && colourInput) factionSelect.addEventListener("change", () => {
        const option = factionSelect.selectedOptions[0];
        if (option && option.dataset.factionColour) {
          syncZoneColour(option.dataset.factionColour);
          renderCirclePreview();
          renderBoundary();
        }
      });

      if (radiusInput) radiusInput.addEventListener("input", () => syncRadius(radiusInput.value));
      if (radiusSlider) radiusSlider.addEventListener("input", () => syncRadius(radiusSlider.value));
      if (shapeSelect) {
        shapeSelect.addEventListener("change", () => {
          if (shapeLabel) shapeLabel.textContent = shapeSelect.value === "boundary" ? "Boundary" : "Circle";
          renderCirclePreview();
          renderBoundary();
        });
      }
      map.addEventListener("pointerdown", updateMapClickMetrics, true);
      map.addEventListener("click", updateMapClickMetrics, true);
      window.addEventListener("resize", () => updateMapClickMetrics());
      form.querySelector("[data-clear-boundary]")?.addEventListener("click", () => {
        boundaryPoints.length = 0;
        renderBoundary();
      });
      form.querySelector("[data-undo-boundary]")?.addEventListener("click", () => {
        boundaryPoints.pop();
        renderBoundary();
      });
      function draftZoneFromMapClick(event) {
        if (event.target.closest("[data-zone-edit]") || event.target.closest("[data-zone-popover]")) return;
        if (event.target.closest("[data-zone-map-hit]")) {
          updateMapClickMetrics(event);
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
        const rect = mapHitRect();
        if (!rect.width || !rect.height) return;
        const xPercent = Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100));
        const yPercent = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));
        if (mapMetricFields.width) mapMetricFields.width.value = String(Math.round(rect.width));
        if (mapMetricFields.height) mapMetricFields.height.value = String(Math.round(rect.height));
        if (mapMetricFields.pointerX) mapMetricFields.pointerX.value = String(Math.max(0, Math.min(rect.width, event.clientX - rect.left)));
        if (mapMetricFields.pointerY) mapMetricFields.pointerY.value = String(Math.max(0, Math.min(rect.height, event.clientY - rect.top)));
        if (mapMetricFields.percentX) mapMetricFields.percentX.value = String(xPercent);
        if (mapMetricFields.percentY) mapMetricFields.percentY.value = String(yPercent);
        const x = Math.round((xPercent / 100) * size);
        const y = Math.round((1 - (yPercent / 100)) * size);
        startNewZoneAt(x, y);
        let cursor = map.querySelector(".zone-cursor");
        if (!cursor) {
          cursor = document.createElement("span");
          cursor.className = "zone-cursor";
          map.appendChild(cursor);
        }
        cursor.style.left = `${xPercent}%`;
        cursor.style.top = `${yPercent}%`;
        if (shapeSelect && shapeSelect.value === "boundary") {
          const zoneZ = zoneFields.y ? zoneFields.y.value : 0;
          boundaryPoints.push({x: zoneFields.x ? zoneFields.x.value : 0, y: zoneZ, z: zoneZ, xPercent, yPercent});
          renderBoundary();
        }
        renderCirclePreview();
        const readout = form.querySelector("[data-map-readout]");
        if (readout) {
          const mode = shapeSelect && shapeSelect.value === "boundary" ? `Boundary point ${boundaryPoints.length}` : `Circle radius ${radiusInput ? radiusInput.value : 250}m`;
          readout.textContent = `New zone X ${zoneFields.x ? zoneFields.x.value : 0}, Z ${zoneFields.y ? zoneFields.y.value : 0} - ${mode}`;
        }
        showZonePopover({
          name: zoneFields.name ? zoneFields.name.value : "New zone draft",
          zone_type: zoneFields.type ? zoneFields.type.value : "radar",
          x: zoneFields.x ? zoneFields.x.value : x,
          z: zoneFields.y ? zoneFields.y.value : y,
          radius: radiusInput ? radiusInput.value : 250,
          display_colour: colourInput ? colourInput.value : zonePalette[0],
        }, "new");
      }
      map.addEventListener("click", draftZoneFromMapClick, true);
      function zoneRecordKey(zone = {}) {
        return String(zone.id || zone.name || "");
      }
      function findZoneJsonByKey(key) {
        if (!key) return null;
        const scripts = Array.from(document.querySelectorAll("[data-zone-json]"));
        return scripts.find((script) => String(script.dataset.zoneKey || "") === String(key)) || null;
      }
      function zoneFromControl(control) {
        if (!control) return {};
        const rowScript = control.closest("[data-zone-row]")?.querySelector("[data-zone-json]");
        const keyedScript = rowScript || findZoneJsonByKey(control.dataset.zoneKey || "");
        if (keyedScript) {
          try { return JSON.parse(keyedScript.textContent || "{}"); } catch (error) {}
        }
        try { return JSON.parse(control.dataset.zone || "{}"); } catch (error) {}
        return {};
      }
      function markZoneEditing(zone, sourceButton) {
        const key = zoneRecordKey(zone) || String(sourceButton?.dataset.zoneKey || "");
        document.querySelectorAll("[data-zone-edit].editing").forEach((item) => item.classList.remove("editing"));
        document.querySelectorAll("[data-zone-edit]").forEach((item) => {
          if (key && String(item.dataset.zoneKey || "") === key) item.classList.add("editing");
          else if (!key) {
            const itemZone = zoneFromControl(item);
            if (zoneRecordKey(itemZone) === zoneRecordKey(zone)) item.classList.add("editing");
          }
        });
      }
      function fillZoneEditor(zone, sourceButton) {
        if (!zone || !Object.keys(zone).length) return false;
        markZoneEditing(zone, sourceButton);
        if (zoneFields.zoneId) zoneFields.zoneId.value = zone.id || zone.name || "";
        if (zoneFields.name) zoneFields.name.value = zone.name || "";
        setSelectValue(zoneFields.type, zone.zone_type || zone.type || "radar");
        const zoneX = Number(zone.x ?? zone.center_x ?? 0);
        const zoneZ = Number(zone.z ?? zone.y ?? zone.center_z ?? zone.center_y ?? 0);
        if (zoneFields.x) zoneFields.x.value = zoneX;
        if (zoneFields.y) zoneFields.y.value = zoneZ;
        setSelectValue(zoneFields.shape, zone.shape || "circle");
        syncRadius(zone.radius ?? zone.radius_m ?? 250);
        setSelectValue(zoneFields.channel, zone.channel_key || zone.alert_channel_id || zone.report_channel_id || "");
        if (zoneFields.role) zoneFields.role.value = zone.role_id || zone.mention_role_id || "";
        setSelectValue(zoneFields.faction, zone.faction_name || zone.faction || "");
        syncZoneColour(zone.display_colour || sourceButton?.dataset.zoneColour || zone.colour || zone.color || zonePalette[0]);
        setSelectValue(zoneFields.enabled, zone.enabled === false ? "false" : "true");
        setSelectValue(zoneFields.action, zone.action || "none");
        setSelectValue(zoneFields.banType, zone.ban_type || "temp");
        if (zoneFields.banMinutes) zoneFields.banMinutes.value = zone.ban_duration_minutes || 1440;
        setSelectValue(zoneFields.triggerTerritory, zone.trigger_territory || "inside");
        if (zoneFields.triggers) zoneFields.triggers.value = Array.isArray(zone.triggers) ? zone.triggers.join(",") : (zone.triggers || "");
        if (zoneFields.ignored) zoneFields.ignored.value = Array.isArray(zone.ignored_gamertags) ? zone.ignored_gamertags.join(",") : (zone.ignored_gamertags || "");
        boundaryPoints.length = 0;
        const savedPoints = Array.isArray(zone.boundary_points) ? zone.boundary_points : [];
        savedPoints.forEach((point) => {
          const x = Number(point.x || 0);
          const y = Number((point.z ?? point.y) || 0);
          boundaryPoints.push({
            x,
            y,
            z: y,
            xPercent: Number(point.xPercent || ((x / size) * 100)),
            yPercent: Number(point.yPercent || (100 - ((y / size) * 100)))
          });
        });
        renderBoundary();
        let cursor = map.querySelector(".zone-cursor");
        if (!cursor) {
          cursor = document.createElement("span");
          cursor.className = "zone-cursor";
          map.appendChild(cursor);
        }
        cursor.style.left = `${(Number(zoneFields.x ? zoneFields.x.value : 0) / size) * 100}%`;
        cursor.style.top = `${100 - ((Number(zoneFields.y ? zoneFields.y.value : 0) / size) * 100)}%`;
        renderCirclePreview();
        if (shapeLabel && shapeSelect) shapeLabel.textContent = shapeSelect.value === "boundary" ? "Boundary" : "Circle";
        const readout = form.querySelector("[data-map-readout]");
        if (readout) readout.textContent = `Editing ${zone.name || "zone"} - save to update this radar/zone.`;
        setZoneEditingState(zone.name || "zone");
        return true;
      }
      async function deleteZone(payload, button) {
        if (!payload.zone_id && !payload.name) return;
        if (!window.confirm(`Delete ${payload.name || "this zone"} from this server?`)) return;
        const originalText = button ? button.textContent : "";
        if (button) {
          button.disabled = true;
          button.textContent = "Deleting...";
        }
        try {
          const response = await fetch(secureDashboardUrl("/api/admin/zone-action"), {
            method: "POST",
            headers: {"Content-Type": "application/json", "Accept": "application/json", "X-Requested-With": "fetch"},
            credentials: "same-origin",
            body: JSON.stringify(payload),
          });
          const body = await response.json().catch(() => ({}));
          if (!response.ok || body.ok === false) throw new Error(body.error || "Zone delete failed.");
          if (result) result.textContent = body.note || "Zone deleted.";
          const dashboardPath = window.location.pathname.startsWith("/owner") ? "/owner" : "/admin";
          window.location.href = secureDashboardUrl(`${dashboardPath}?section=zones&guild_id=${encodeURIComponent(payload.guild_id)}#zones-list`);
        } catch (error) {
          if (result) result.textContent = error.message || "Zone delete failed.";
          if (button) {
            button.disabled = false;
            button.textContent = originalText;
          }
        }
      }
      if (deleteCurrentButton) {
        deleteCurrentButton.addEventListener("click", async () => {
          const payload = {
            guild_id: zoneFields.guildId ? zoneFields.guildId.value : "",
            zone_id: zoneFields.zoneId ? zoneFields.zoneId.value : "",
            zone_type: zoneFields.type ? zoneFields.type.value : "",
            name: zoneFields.name ? zoneFields.name.value : "",
            action: "delete",
            dashboard_mode: "{{ mode }}",
          };
          await deleteZone(payload, deleteCurrentButton);
        });
      }
      document.addEventListener("click", async (event) => {
        const editButton = event.target.closest("[data-zone-edit]");
        if (editButton) {
          const zone = zoneFromControl(editButton);
          if (!fillZoneEditor(zone, editButton)) return;
          event.preventDefault();
          if (editButton.closest("[data-zone-map]")) {
            showZonePopover(zone, "edit");
          } else {
            showZonePopover(zone, "edit");
            map.scrollIntoView({behavior: "smooth", block: "center"});
          }
          return;
        }
        const deleteButton = event.target.closest("[data-zone-delete]");
        if (deleteButton) {
          if (deleteButton.closest("form")) return;
          event.preventDefault();
          const zone = zoneFromControl(deleteButton);
          await deleteZone({
            guild_id: deleteButton.dataset.guildId || (zoneFields.guildId ? zoneFields.guildId.value : ""),
            zone_id: deleteButton.dataset.zoneId || zone.id || "",
            zone_type: deleteButton.dataset.zoneType || zone.zone_type || zone.type || "",
            name: deleteButton.dataset.zoneName || zone.name || "",
            action: "delete",
            dashboard_mode: "{{ mode }}",
          }, deleteButton);
        }
      });
      setZoneEditingState(zoneFields.zoneId && zoneFields.zoneId.value ? (zoneFields.name ? zoneFields.name.value : "zone") : "");
      syncRadius(radiusInput ? radiusInput.value : 250);
      syncZoneColour(colourInput ? colourInput.value : zonePalette[0]);
      updateMapClickMetrics();
      loadBoundaryFromField();
      if (zoneFields.zoneId && zoneFields.zoneId.value) {
        placeCursorFromForm();
        const readout = form.querySelector("[data-map-readout]");
        if (readout) readout.textContent = `Editing ${zoneFields.name ? zoneFields.name.value : "zone"} - save to update this radar/zone.`;
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = "Save Zone Changes";
      }
    });
    document.querySelectorAll("[data-plan-notice]").forEach((notice) => {
      const today = new Date().toISOString().slice(0, 10);
      const key = `wanderingPlanNotice:${notice.dataset.planKey}:${today}`;
      if (localStorage.getItem(key)) notice.style.display = "none";
      notice.querySelector("[data-dismiss-plan-notice]")?.addEventListener("click", () => {
        localStorage.setItem(key, "1");
        notice.style.display = "none";
      });
    });
  </script>
</body>
</html>
"""

ADMIN_ROUTES = [
    "/api/admin/embed-template",
    "/api/admin/embed-template-action",
    "/api/admin/dashboard-record-action",
    "/api/admin/welcome-automation",
    "/api/admin/utility-config",
    "/api/admin/reaction-role-panel",
    "/api/admin/shop-item",
    "/api/admin/shop-bundle",
    "/api/admin/theme",
    "/api/admin/convert-dayz-xml",
    "/api/admin/loot-tweak",
    "/api/admin/loot-bulk-tweak",
    "/api/admin/loadout-generate",
    "/api/admin/loadout-package",
    "/api/admin/visual-loadout-draft",
    "/api/admin/vehicle-loadout-generate",
    "/api/admin/xml-workshop",
    "/api/admin/scenario-event",
    "/api/admin/scenario-event-action",
    "/api/admin/scenario-event-status",
    "/api/admin/economy-rule",
    "/api/admin/link-server",
    "/api/admin/zone",
    "/api/admin/zone-action",
    "/api/admin/member-action",
    "/api/admin/moderation-guard",
    "/api/admin/link-enforcement",
    "/api/admin/on-screen-message",
    "/api/admin/server-control",
    "/api/admin/faction",
    "/api/admin/faction-action",
    "/api/admin/faction-member",
    "/api/admin/wage",
    "/api/admin/wallet-adjustment",
    "/api/admin/guild-access",
]

SECTION_FEATURES = {
    "leaderboards": "leaderboards",
    "automations": "embeds",
    "factions": "factions",
    "zones": "safe_zones",
    "members": "members",
    "heatmaps": "heatmaps",
    "pve": "pve_quests",
    "economy": "economy",
    "shop": "shop",
    "xml-workshop": "xml_workshop",
    "dayz-converter": "xml_workshop",
    "loot-engine": "xml_workshop",
    "visual-loadout": "xml_workshop",
    "bulk-economy": "xml_workshop",
    "server-rules": "server_rules",
    "moderation": "moderation",
    "server-control": "server_control",
}

ADMIN_ROUTE_FEATURES = {
    "/api/admin/embed-template": "embeds",
    "/api/admin/embed-template-action": "embeds",
    "/api/admin/dashboard-record-action": "embeds",
    "/api/admin/welcome-automation": "embeds",
    "/api/admin/utility-config": "embeds",
    "/api/admin/reaction-role-panel": "embeds",
    "/api/admin/shop-item": "shop",
    "/api/admin/shop-bundle": "shop",
    "/api/admin/scenario-event": "pve_quests",
    "/api/admin/scenario-event-action": "pve_quests",
    "/api/admin/economy-rule": "economy",
    "/api/admin/zone": "safe_zones",
    "/api/admin/zone-action": "safe_zones",
    "/api/admin/member-action": "members",
    "/api/admin/moderation-guard": "moderation",
    "/api/admin/link-enforcement": "server_rules",
    "/api/admin/on-screen-message": "server_rules",
    "/api/admin/server-control": "server_control",
    "/api/admin/faction": "factions",
    "/api/admin/faction-action": "factions",
    "/api/admin/faction-member": "factions",
    "/api/admin/wage": "wages",
    "/api/admin/wallet-adjustment": "economy",
    "/api/admin/convert-dayz-xml": "xml_workshop",
    "/api/admin/loot-tweak": "xml_workshop",
    "/api/admin/loot-bulk-tweak": "xml_workshop",
    "/api/admin/loadout-generate": "xml_workshop",
    "/api/admin/loadout-package": "xml_workshop",
    "/api/admin/visual-loadout-draft": "xml_workshop",
    "/api/admin/loadout-package-inject": "xml_workshop",
    "/api/admin/dayz-converter-inject": "xml_workshop",
    "/api/admin/xml-inject": "xml_workshop",
    "/api/admin/vehicle-loadout-generate": "xml_workshop",
    "/api/admin/xml-workshop": "xml_workshop",
}


def data_path(filename: str) -> str:
    return os.path.join(DATA_ROOT, filename)


def read_json_file(filename: str, default: Any) -> Any:
    path = data_path(filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default
    return default if data is None else data


def write_json_file(filename: str, data: Any) -> None:
    path = data_path(filename)
    os.makedirs(os.path.dirname(path) or DATA_ROOT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def write_split_guild_configs(data: Any) -> None:
    if not isinstance(data, dict):
        return
    for guild_id, config in data.items():
        if not isinstance(config, dict):
            continue
        safe_guild_id = "".join(
            char for char in str(guild_id)
            if char.isalnum() or char in {"-", "_"}
        )
        if not safe_guild_id:
            continue
        write_json_file(os.path.join(GUILD_CONFIG_FOLDER, f"{safe_guild_id}.json"), config)


def merge_guild_config_records(base: Any, override: Any) -> Any:
    if not isinstance(base, dict):
        return override
    if not isinstance(override, dict):
        return base
    merged = dict(base)
    merged.update(override)
    base_events = base.get("scenario_events")
    override_events = override.get("scenario_events")
    base_tombstones = base.get("scenario_event_tombstones")
    override_tombstones = override.get("scenario_event_tombstones")
    tombstones: dict[str, Any] = {}
    if isinstance(base_tombstones, dict):
        tombstones.update(base_tombstones)
    if isinstance(override_tombstones, dict):
        tombstones.update(override_tombstones)
    if tombstones:
        merged["scenario_event_tombstones"] = tombstones

    def event_is_visible(event: Any) -> bool:
        if not isinstance(event, dict):
            return False
        event_id = str(event.get("id") or event.get("name") or "").strip()
        return not event_id or event_id not in tombstones

    if isinstance(override_events, list):
        merged["scenario_events"] = [event for event in override_events if event_is_visible(event)]
    elif isinstance(base_events, list):
        merged["scenario_events"] = [event for event in base_events if event_is_visible(event)]
    return merged


def scenario_event_key(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    return str(event.get("id") or event.get("name") or "").strip()


def scenario_event_tombstones(config: Any) -> dict[str, Any]:
    tombstones = config.get("scenario_event_tombstones") if isinstance(config, dict) else {}
    return tombstones if isinstance(tombstones, dict) else {}


def mark_scenario_event_deleted(config: dict[str, Any], event_id: int, action: str, event: Any = None) -> None:
    tombstones = config.setdefault("scenario_event_tombstones", {})
    if not isinstance(tombstones, dict):
        tombstones = {}
        config["scenario_event_tombstones"] = tombstones
    tombstones[str(event_id)] = {
        "deleted_at": datetime.now(UTC).isoformat(),
        "action": action,
        "name": str(event.get("name") or "") if isinstance(event, dict) else "",
    }


def visible_scenario_events(config: Any) -> list[dict[str, Any]]:
    events = config.get("scenario_events", []) if isinstance(config, dict) else []
    if not isinstance(events, list):
        return []
    tombstones = scenario_event_tombstones(config)
    return [
        event
        for event in events
        if isinstance(event, dict) and scenario_event_key(event) not in tombstones
    ]


def sync_runtime_store(store_name: str, data: Any) -> None:
    if not CUSTOM_STATE_PROVIDER:
        return
    try:
        state = CUSTOM_STATE_PROVIDER()
    except Exception:
        return
    if not isinstance(state, dict):
        return
    target = state.get(store_name)
    if target is None and store_name == "shop":
        target = state.get("shop_items")
    if isinstance(target, dict) and isinstance(data, dict):
        target.clear()
        target.update(data)
    elif isinstance(target, list) and isinstance(data, list):
        target[:] = data


def run_runtime_scenario_xml_upload(guild_id: str) -> dict[str, Any] | None:
    if not CUSTOM_STATE_PROVIDER:
        return None
    try:
        state = CUSTOM_STATE_PROVIDER()
    except Exception as error:
        return {"ok": False, "messages": [f"Dashboard runtime state unavailable: {error}"]}
    uploader = state.get("scenario_xml_uploader") if isinstance(state, dict) else None
    if not callable(uploader):
        return None
    try:
        result = uploader(str(guild_id))
    except Exception as error:
        return {"ok": False, "messages": [f"Native CE XML upload failed: {error}"]}
    if isinstance(result, dict):
        return result
    if isinstance(result, (list, tuple)) and len(result) >= 3:
        return {"ok": bool(result[0]), "built": result[1], "messages": result[2]}
    return {"ok": False, "messages": ["Native CE XML uploader returned an unexpected result."]}


def apply_runtime_scenario_xml_upload(guild_id: str, event_id: int = 0, removed: bool = False) -> dict[str, Any] | None:
    upload_result = run_runtime_scenario_xml_upload(guild_id)
    if upload_result is None:
        return None

    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        return upload_result
    config = guild_configs.setdefault(str(guild_id), {"channels": {}})
    events = config.get("scenario_events", [])
    if not isinstance(events, list):
        events = []
        config["scenario_events"] = events

    built = upload_result.get("built") if isinstance(upload_result.get("built"), dict) else {}
    messages = upload_result.get("messages") if isinstance(upload_result.get("messages"), list) else []
    upload_ok = bool(upload_result.get("ok"))
    now_text = datetime.now(UTC).isoformat()
    status_text = (
        f"Native CE XML uploaded to {built.get('events_path')} and {built.get('spawns_path')}"
        if upload_ok
        else "Native CE XML upload failed: " + (" | ".join(str(message) for message in messages[-4:]) if messages else "no details")
    )

    for event in events:
        if not isinstance(event, dict):
            continue
        is_target = safe_int(event.get("id"), 0) == safe_int(event_id, 0)
        is_dashboard_scenario = (
            str(event.get("created_by") or "") == "dashboard"
            and str(event.get("event_type") or "") != "vehicle_reset_all"
            and str(event.get("upload_status") or "waiting_for_bot_upload") in {"waiting_for_bot_upload", "failed", "uploaded"}
        )
        if event_id and not is_target and not (upload_ok and is_dashboard_scenario):
            continue
        event["updated_at"] = now_text
        if upload_ok:
            event["native_ce_uploaded_at"] = now_text
            event["native_ce_events_path"] = built.get("events_path", "")
            event["native_ce_spawns_path"] = built.get("spawns_path", "")
            event["upload_status"] = "removed" if removed and is_target else "uploaded"
            event["status"] = "Removed from native CE XML" if removed and is_target else "Ready - native CE XML uploaded; restart once to spawn"
            event.pop("upload_error", None)
        else:
            event["upload_attempts"] = int(event.get("upload_attempts") or 0) + 1
            event["upload_status"] = "failed"
            event["upload_error"] = status_text
            event["status"] = "Native CE XML upload failed"

    if removed:
        config["scenario_events_cleanup_pending"] = not upload_ok
        if upload_ok:
            config["scenario_events_cleanup_completed_at"] = now_text
            config.pop("scenario_events_cleanup_error", None)
        else:
            config["scenario_events_cleanup_error"] = status_text

    save_store("guild_configs", guild_configs)
    sync_runtime_store("guild_configs", guild_configs)
    return upload_result


def schedule_runtime_scenario_xml_upload(guild_id: str, event_id: int = 0, removed: bool = False) -> bool:
    if not CUSTOM_STATE_PROVIDER:
        return False

    def upload_worker() -> None:
        try:
            apply_runtime_scenario_xml_upload(guild_id, event_id, removed)
        except Exception as error:
            guild_configs = load_store("guild_configs", {})
            if not isinstance(guild_configs, dict):
                return
            config = guild_configs.setdefault(str(guild_id), {"channels": {}})
            status_text = f"Native CE XML upload failed: {error}"
            events = config.get("scenario_events", [])
            if isinstance(events, list):
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    if event_id and safe_int(event.get("id"), 0) != safe_int(event_id, 0):
                        continue
                    event["updated_at"] = datetime.now(UTC).isoformat()
                    event["upload_status"] = "failed"
                    event["upload_error"] = status_text
                    event["status"] = "Native CE XML upload failed"
            if removed:
                config["scenario_events_cleanup_error"] = status_text
            save_store("guild_configs", guild_configs)
            sync_runtime_store("guild_configs", guild_configs)

    Thread(target=upload_worker, name=f"scenario-upload-{guild_id}-{event_id}", daemon=True).start()
    return True


def run_runtime_messages_xml_upload(guild_id: str) -> dict[str, Any] | None:
    if not CUSTOM_STATE_PROVIDER:
        return None
    try:
        state = CUSTOM_STATE_PROVIDER()
    except Exception as error:
        return {"ok": False, "messages": [f"Dashboard runtime state unavailable: {error}"]}
    uploader = state.get("messages_xml_uploader") if isinstance(state, dict) else None
    if not callable(uploader):
        return None
    try:
        result = uploader(str(guild_id))
    except Exception as error:
        return {"ok": False, "messages": [f"messages.xml upload failed: {error}"]}
    if isinstance(result, dict):
        return result
    if isinstance(result, (list, tuple)) and len(result) >= 2:
        return {"ok": bool(result[0]), "messages": [str(result[1])]}
    return {"ok": False, "messages": ["messages.xml uploader returned an unexpected result."]}


def load_store(name: str, default: Any) -> Any:
    data = read_json_file(FILES[name], default)
    if name == "guild_configs" and isinstance(data, dict):
        # bot.py stores split per-guild configs in guild_data/guilds. The
        # dashboard previously used guilds/, which could leave a stale
        # password copy winning during login after /dashboardcredentials reset.
        # Keep legacy reads for old data, but let the canonical bot folder win.
        for folder in (LEGACY_GUILD_CONFIG_FOLDER, GUILD_CONFIG_FOLDER):
            guild_dir = data_path(folder)
            if not os.path.isdir(guild_dir):
                continue
            for filename in os.listdir(guild_dir):
                if not filename.endswith(".json"):
                    continue
                guild_id = filename[:-5]
                config = read_json_file(os.path.join(folder, filename), None)
                if isinstance(config, dict):
                    data[guild_id] = merge_guild_config_records(data.get(guild_id), config)
    return data


def save_store(name: str, data: Any) -> None:
    write_json_file(FILES[name], data)
    if name == "guild_configs":
        write_split_guild_configs(data)
    sync_runtime_store(name, data)


def dashboard_password_hash(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def verify_dashboard_password(password: str, credentials: dict[str, Any]) -> bool:
    salt = str(credentials.get("password_salt") or "")
    expected = str(credentials.get("password_hash") or "")
    if salt and expected and secrets.compare_digest(dashboard_password_hash(password, salt), expected):
        return True
    # Compatibility for very old credentials generated before salted hashes.
    for key in (
        "password",
        "dashboard_password",
        "plain_password",
        "password_plain",
        "admin_password",
        "access_password",
        "dashboard_secret",
        "secret",
        "dashboard_pass",
        "admin_pass",
    ):
        legacy_plain = str(credentials.get(key) or "")
        if legacy_plain and secrets.compare_digest(str(password or ""), legacy_plain):
            return True
    return False


def dashboard_credentials_for_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    for key in ("dashboard_credentials", "dashboard_login", "dashboard_auth"):
        credentials = config.get(key)
        if isinstance(credentials, dict) and credentials.get("dashboard_id"):
            return credentials
    top_level: dict[str, Any] = {}
    for key in (
        "dashboard_id",
        "password_salt",
        "password_hash",
        "password",
        "dashboard_password",
        "plain_password",
        "password_plain",
        "admin_password",
        "access_password",
        "dashboard_secret",
        "secret",
        "dashboard_pass",
        "admin_pass",
    ):
        if config.get(key):
            top_level[key] = config.get(key)
    if top_level.get("dashboard_id") and (
        top_level.get("password_hash")
        or any(top_level.get(key) for key in (
            "password",
            "dashboard_password",
            "plain_password",
            "password_plain",
            "admin_password",
            "access_password",
            "dashboard_secret",
            "secret",
            "dashboard_pass",
            "admin_pass",
        ))
    ):
        return top_level
    return None


def dashboard_session_secret(credentials: dict[str, Any] | None) -> str:
    if not isinstance(credentials, dict):
        return ""
    password_hash = str(credentials.get("password_hash") or "")
    if password_hash:
        return f"hash:{password_hash}"
    for key in (
        "password",
        "dashboard_password",
        "plain_password",
        "password_plain",
        "admin_password",
        "access_password",
        "dashboard_secret",
        "secret",
        "dashboard_pass",
        "admin_pass",
    ):
        legacy_plain = str(credentials.get(key) or "")
        if legacy_plain:
            return f"legacy:{legacy_plain}"
    return ""


def session_signature(guild_id: str, credentials: dict[str, Any] | str) -> str:
    session_secret = credentials if isinstance(credentials, str) else dashboard_session_secret(credentials)
    return hashlib.sha256(f"{guild_id}:{session_secret}:{DASHBOARD_COOKIE_SECRET}".encode("utf-8")).hexdigest()


def make_session_cookie(guild_id: str, credentials: dict[str, Any]) -> str:
    return f"{guild_id}:{session_signature(guild_id, credentials)}"


def owner_session_signature() -> str:
    return hashlib.sha256(f"owner:{OWNER_DASHBOARD_PASSWORD}:{DASHBOARD_COOKIE_SECRET}".encode("utf-8")).hexdigest()


def make_owner_session_cookie() -> str:
    return f"owner:{owner_session_signature()}"


def verify_owner_login(dashboard_id: str, password: str) -> bool:
    if not OWNER_DASHBOARD_PASSWORD:
        return False
    if not OWNER_DASHBOARD_ID:
        return False
    if str(dashboard_id or "").strip().lower() != OWNER_DASHBOARD_ID:
        return False
    return secrets.compare_digest(str(password or ""), OWNER_DASHBOARD_PASSWORD)


def dashboard_admin_login_enabled(config: dict[str, Any]) -> bool:
    dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    if not isinstance(dashboard, dict):
        return True
    plan_status = str(dashboard.get("plan_status") or dashboard.get("tier") or "trial").strip().lower()
    if plan_status in {"suspended", "none"}:
        return False
    return safe_bool(dashboard.get("enabled"), True)


def dashboard_feature_allowed(config: dict[str, Any], feature: str) -> bool:
    if not feature:
        return True
    dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    if not isinstance(dashboard, dict):
        return True
    plan_status = str(dashboard.get("plan_status") or dashboard.get("tier") or "trial").strip().lower()
    if plan_status in {"suspended", "none"}:
        return False
    features = dashboard.get("features")
    if not isinstance(features, dict) or feature not in features:
        return safe_bool(dashboard.get("enabled"), True)
    return safe_bool(features.get(feature), False)


def find_guild_by_dashboard_id(dashboard_id: str) -> tuple[str | None, dict[str, Any] | None]:
    dashboard_id = str(dashboard_id or "").strip().lower()
    if not dashboard_id:
        return None, None
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        return None, None
    for guild_id, config in guild_configs.items():
        if not isinstance(config, dict):
            continue
        credentials = dashboard_credentials_for_config(config)
        if not isinstance(credentials, dict):
            continue
        if str(credentials.get("dashboard_id") or "").strip().lower() == dashboard_id:
            return str(guild_id), config
    return None, None


def linked_guild_ids_for_config(config: dict[str, Any], primary_guild_id: str) -> list[str]:
    dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    linked = dashboard.get("linked_guild_ids", []) if isinstance(dashboard, dict) else []
    if not isinstance(linked, list):
        linked = []
    guild_ids = [str(primary_guild_id)]
    for linked_id in linked:
        linked_id = str(linked_id).strip()
        if linked_id and linked_id not in guild_ids:
            guild_ids.append(linked_id)
    return guild_ids


def owner_admin_guild_ids(guild_configs: dict[str, Any] | None = None) -> list[str]:
    guild_ids = []
    for item in csv_list(OWNER_ADMIN_GUILD_IDS):
        if item not in guild_ids:
            guild_ids.append(item)
    if not isinstance(guild_configs, dict):
        guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        return guild_ids
    for guild_id, config in guild_configs.items():
        if not isinstance(config, dict):
            continue
        dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
        if safe_bool(dashboard.get("owner_admin_visible"), False):
            guild_id = str(guild_id)
            if guild_id not in guild_ids:
                guild_ids.append(guild_id)
    return guild_ids


def current_auth() -> dict[str, Any] | None:
    provided = request.headers.get("X-Dashboard-Token") or request.args.get("token") or ""
    if ADMIN_TOKEN and secrets.compare_digest(provided, ADMIN_TOKEN):
        return {"kind": "owner", "guild_id": None, "guild_ids": owner_admin_guild_ids(), "label": "all servers"}

    cookie = request.cookies.get("dashboard_session", "")
    if ":" not in cookie:
        return None
    guild_id, signature = cookie.split(":", 1)
    guild_configs = load_store("guild_configs", {})
    if guild_id == "owner" and OWNER_DASHBOARD_PASSWORD:
        if secrets.compare_digest(signature, owner_session_signature()):
            return {"kind": "owner", "guild_id": None, "guild_ids": owner_admin_guild_ids(guild_configs), "label": "all servers"}
        return None
    config = guild_configs.get(guild_id) if isinstance(guild_configs, dict) else None
    if not isinstance(config, dict):
        return None
    if not dashboard_admin_login_enabled(config):
        return None
    credentials = dashboard_credentials_for_config(config)
    if not isinstance(credentials, dict):
        return None
    expected = session_signature(guild_id, credentials)
    if not secrets.compare_digest(signature, expected):
        return None
    return {
        "kind": "guild",
        "guild_id": guild_id,
        "guild_ids": linked_guild_ids_for_config(config, guild_id),
        "label": str(config.get("guild_name") or f"Guild {guild_id}"),
    }


def login_page(error: str = ""):
    return render_template_string(LOGIN_TEMPLATE, error=error)


def require_page_auth(owner_only: bool = False):
    auth = current_auth()
    if not auth:
        return None, redirect("/login")
    if owner_only and auth["kind"] != "owner":
        return None, (jsonify({"ok": False, "error": "owner token required"}), 403)
    return auth, None


def scoped_payload_for_auth(payload: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    if auth["kind"] == "guild":
        payload = dict(payload)
        allowed_guild_ids = [str(item) for item in auth.get("guild_ids", [auth["guild_id"]])]
        requested_guild_id = str(payload.get("guild_id") or auth["guild_id"])
        payload["guild_id"] = requested_guild_id if requested_guild_id in allowed_guild_ids else auth["guild_id"]
    elif auth["kind"] == "owner" and request.path.startswith("/api/admin/"):
        payload = dict(payload)
        if str(payload.get("dashboard_mode") or "").lower() == "owner":
            return payload
        allowed_guild_ids = [str(item) for item in auth.get("guild_ids", [])]
        requested_guild_id = str(payload.get("guild_id") or "")
        if not allowed_guild_ids or requested_guild_id not in allowed_guild_ids:
            payload["_scope_denied"] = True
        else:
            payload["guild_id"] = requested_guild_id
    return payload


def request_payload() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form.to_dict(flat=True)
    return dict(data or {})


AUDITED_DASHBOARD_PREFIXES = ("/api/admin/", "/api/owner/")
DASHBOARD_AUDIT_MAX_QUEUE = 1000
DASHBOARD_AUDIT_IGNORED_KEYS = {
    "_scope_denied",
    "dashboard_mode",
    "return_to",
    "token",
    "csrf",
    "csrf_token",
    "editor_json",
    "json_text",
    "xml_text",
    "content",
    "generated_xml",
    "events_xml",
    "eventspawns_xml",
    "eventgroups_xml",
    "loadout_json",
    "cfggameplay_json",
}


def dashboard_audit_title(path: str, payload: dict[str, Any]) -> str:
    action = str(payload.get("action") or "").strip().lower()
    route = str(path or "").rstrip("/").split("/")[-1].replace("-", " ")
    titles = {
        "channel-config": "Dashboard channel settings updated",
        "dashboard-record-action": "Dashboard panel updated",
        "embed-template": "Embed or welcome panel saved",
        "embed-template-action": "Embed or welcome panel updated",
        "faction": "Faction saved",
        "faction-action": "Faction updated",
        "faction-member": "Faction member updated",
        "guild-access": "Dashboard access updated",
        "guild-action": "Owner guild action completed",
        "link-enforcement": "Link enforcement updated",
        "link-server": "Linked server settings updated",
        "leaderboard": "Leaderboard settings updated",
        "member-action": "Member moderation action queued",
        "moderation-guard": "Moderation guard updated",
        "on-screen-message": "On-screen message queued",
        "reaction-role-panel": "Reaction role panel saved",
        "reset-schedule": "Reset schedule updated",
        "scenario-event": "PVE workshop event saved",
        "scenario-event-action": "PVE workshop event updated",
        "server-control": "Server control updated",
        "shop-bundle": "Shop bundle saved",
        "shop-item": "Shop item saved",
        "shop-item-action": "Shop item updated",
        "theme": "Dashboard theme updated",
        "convert-dayz-xml": "DayZ map XML generated",
        "dayz-converter-inject": "DayZ map XML merged to server",
        "loadout-generate": "Player loadout XML generated",
        "loadout-package": "Player loadout package downloaded",
        "loadout-package-inject": "Player loadout package uploaded",
        "loot-bulk-tweak": "Bulk loot XML generated",
        "loot-tweak": "Loot XML generated",
        "xml-inject": "XML file uploaded to server",
        "utility-config": "Utility panel saved",
        "utility-config-action": "Utility panel updated",
        "vehicle-loadout-generate": "Vehicle loadout XML generated",
        "vehicle-reset": "Vehicle reset schedule updated",
        "wage": "Wage saved",
        "wage-action": "Wage updated",
        "wallet-adjustment": "Wallet adjusted",
        "welcome-automation": "Welcome automation saved",
        "xml-workshop": "XML workshop updated",
        "zone": "Zone saved",
        "zone-action": "Zone updated",
    }
    title = titles.get(str(path or "").rstrip("/").split("/")[-1], f"{route.title()} updated")
    if action in {"delete", "remove"}:
        return title.replace("saved", "deleted").replace("updated", "deleted")
    if action in {"cancel", "pause", "approve", "toggle", "refresh"}:
        return f"{title} ({action})"
    return title


def dashboard_audit_actor(auth: dict[str, Any] | None) -> str:
    if not isinstance(auth, dict):
        return "Dashboard session"
    label = str(auth.get("label") or "").strip()
    if auth.get("kind") == "owner":
        return f"Owner dashboard ({label or 'all servers'})"
    if label:
        return f"Server dashboard ({label})"
    return "Server dashboard"


def compact_audit_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 2:
        return "..."
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in list(value.items())[:12]:
            key_text = str(key)
            if key_text in DASHBOARD_AUDIT_IGNORED_KEYS:
                continue
            if any(secret_key in key_text.lower() for secret_key in SECRET_KEYS):
                compacted[key_text] = "***"
            else:
                compacted[key_text] = compact_audit_value(item, depth=depth + 1)
        if len(value) > 12:
            compacted["more"] = f"{len(value) - 12} more field(s)"
        return compacted
    if isinstance(value, list):
        items = [compact_audit_value(item, depth=depth + 1) for item in value[:6]]
        if len(value) > 6:
            items.append(f"... {len(value) - 6} more")
        return items
    text = str(value)
    if len(text) > 180:
        return text[:177].rstrip() + "..."
    return value


def dashboard_audit_summary(payload: dict[str, Any]) -> str:
    priority_keys = (
        "name",
        "title",
        "server_name",
        "guild_id",
        "action",
        "event_name",
        "zone_name",
        "faction_name",
        "item_name",
        "vehicle_class",
        "channel_id",
        "method",
    )
    parts = []
    for key in priority_keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        text = str(value)
        if len(text) > 70:
            text = text[:67].rstrip() + "..."
        parts.append(f"{key}: {text}")
    return "; ".join(parts[:5])


def enqueue_dashboard_audit_event(response: Any) -> None:
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    if not any(request.path.startswith(prefix) for prefix in AUDITED_DASHBOARD_PREFIXES):
        return
    if not (200 <= int(getattr(response, "status_code", 0) or 0) < 400):
        return

    auth = current_auth()
    if not auth:
        return
    audit_payload = getattr(g, "dashboard_audit_payload", None)
    if not isinstance(audit_payload, dict):
        audit_payload = request_payload()
    payload = scoped_payload_for_auth(audit_payload, auth)
    if payload.get("_scope_denied"):
        return

    guild_id = str(payload.get("guild_id") or auth.get("guild_id") or "").strip()
    if not guild_id:
        return

    event = {
        "id": f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}-{secrets.token_hex(3)}",
        "guild_id": guild_id,
        "method": request.method.upper(),
        "route": request.path,
        "action": str(payload.get("action") or ""),
        "title": dashboard_audit_title(request.path, payload),
        "summary": dashboard_audit_summary(payload),
        "actor": dashboard_audit_actor(auth),
        "actor_kind": str(auth.get("kind") or "dashboard"),
        "payload": compact_audit_value(payload),
        "created_at": datetime.now(UTC).isoformat(),
    }
    queue = load_store("dashboard_audit_queue", [])
    if not isinstance(queue, list):
        queue = []
    queue.append(event)
    if len(queue) > DASHBOARD_AUDIT_MAX_QUEUE:
        queue = queue[-DASHBOARD_AUDIT_MAX_QUEUE:]
    save_store("dashboard_audit_queue", queue)


def require_admin() -> tuple[dict[str, Any] | None, Any | None]:
    auth = current_auth()
    if not auth:
        return None, (jsonify({"ok": False, "error": "dashboard login required"}), 401)
    payload = scoped_payload_for_auth(request_payload(), auth)
    if payload.get("_scope_denied"):
        return None, (jsonify({"ok": False, "error": "server is not in this admin scope"}), 403)
    if auth.get("kind") == "guild":
        guild_id = normalize_guild_id(payload.get("guild_id") or auth.get("guild_id"))
        guild_configs = load_store("guild_configs", {})
        config = guild_configs.get(guild_id) if isinstance(guild_configs, dict) else None
        if not isinstance(config, dict) or not dashboard_admin_login_enabled(config):
            return None, (jsonify({"ok": False, "error": "dashboard access is disabled for this server"}), 403)
        feature = ADMIN_ROUTE_FEATURES.get(request.path)
        if feature and not dashboard_feature_allowed(config, feature):
            return None, (jsonify({"ok": False, "error": f"{feature} is not enabled for this dashboard"}), 403)
    return payload, None


def wants_json_response() -> bool:
    return request.is_json or "application/json" in str(request.headers.get("Accept") or "")


def safe_dashboard_return(value: Any, fallback: str = "/admin?section=pve") -> str:
    target = str(value or "").strip()
    if not (target.startswith("/admin") or target.startswith("/owner")):
        return fallback
    if "\n" in target or "\r" in target:
        return fallback
    return target


def dashboard_section_return(section: str, payload: dict[str, Any] | None = None, anchor: str = "") -> str:
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_part = f"&guild_id={guild_id}" if guild_id and guild_id != "global" else ""
    base_path = "/owner" if str(payload.get("dashboard_mode") or "").lower() == "owner" else "/admin"
    fallback = f"{base_path}?section={section}{guild_part}{anchor}"
    return safe_dashboard_return(payload.get("return_to"), fallback)


def dashboard_api_response(payload: dict[str, Any] | None, body: dict[str, Any], section: str, anchor: str = ""):
    if wants_json_response():
        return jsonify(body)
    return redirect(dashboard_section_return(section, payload, anchor))


def strip_dashboard_control_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    cleaned = dict(payload or {})
    for key in ("return_to", "dashboard_mode"):
        cleaned.pop(key, None)
    return cleaned


def require_owner_payload() -> tuple[dict[str, Any] | None, Any | None]:
    auth = current_auth()
    if not auth:
        return None, (jsonify({"ok": False, "error": "dashboard login required"}), 401)
    if auth.get("kind") != "owner":
        return None, (jsonify({"ok": False, "error": "owner login required"}), 403)
    return request_payload(), None


def normalize_guild_id(value: Any) -> str:
    return str(value or "global").strip() or "global"


def faction_wallet_id(value: Any) -> str:
    key = re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())
    return f"faction:{key or 'unknown'}"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def ensure_wallet_accounts(wallet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(wallet, dict):
        return {}
    if "cash_balance" not in wallet and "bank_balance" not in wallet:
        wallet["cash_balance"] = safe_int(wallet.get("balance", 0))
        wallet["bank_balance"] = 0
    else:
        wallet["cash_balance"] = safe_int(wallet.get("cash_balance", 0))
        wallet["bank_balance"] = safe_int(wallet.get("bank_balance", 0))
    wallet["balance"] = safe_int(wallet.get("cash_balance", 0)) + safe_int(wallet.get("bank_balance", 0))
    return wallet


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def safe_date(value: Any) -> str:
    text = str(value or "").strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def safe_time(value: Any, default: str = "04:00") -> str:
    text = str(value or default).strip()
    try:
        return datetime.strptime(text, "%H:%M").strftime("%H:%M")
    except ValueError:
        return default


def safe_colour(value: Any, default: str = "#d5b45f") -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.lower()
    return default


def csv_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def parse_shop_bundle_items(value: Any) -> list[dict[str, Any]]:
    rows = []
    if isinstance(value, list):
        candidates = value
    else:
        candidates = re.split(r"[\n;]+", str(value or ""))
    for raw in candidates:
        if isinstance(raw, dict):
            item_name = str(raw.get("item") or raw.get("name") or "").strip()
            quantity = safe_int(raw.get("quantity"), 1)
        else:
            text = str(raw or "").strip()
            if not text:
                continue
            match = re.match(r"^(?:(\d+)\s*[xX]\s*)?([A-Za-z0-9_]+)(?:\s*(?:[,xX:])\s*(\d+))?$", text)
            if not match:
                continue
            quantity = safe_int(match.group(1) or match.group(3), 1)
            item_name = match.group(2).strip()
        quantity = max(1, min(999, quantity))
        if item_name and is_shop_sellable_item(item_name, ""):
            rows.append({"item": item_name, "quantity": quantity})
    return rows


def safe_dayz_class(value: Any) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"[A-Za-z0-9_]{2,80}", text) else ""


def disallowed_vehicle_part_class(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    part_terms = (
        "lootdispatch",
        "_hood",
        "_trunk",
        "_wheel",
        "_door",
        "_doors",
        "_battery",
        "_radiator",
        "_sparkplug",
        "_headlight",
        "carbattery",
        "carradiator",
        "truckbattery",
        "sparkplug",
    )
    return any(term in text for term in part_terms)


def xml_attr(value: Any) -> str:
    text = str(value if value is not None else "")
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def dayz_xml_float(value: Any) -> str:
    number = float(value)
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def dayz_xml_chance(value: Any, default: float = 1.0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    number = max(0.0, min(1.0, number))
    return f"{number:.2f}"


def normalize_dayz_angle(value: float) -> float:
    normalized = (float(value) + 180.0) % 360.0 - 180.0
    return 180.0 if normalized == -180.0 else normalized


def xml_vector(values: list[float] | tuple[float, ...]) -> str:
    return " ".join(dayz_xml_float(item) for item in values)


def sanitize_dayz_classname(value: Any) -> str:
    text = re.sub(r"[\s\u200b-\u200d\ufeff]+", "", str(value or "").strip())
    if text.lower() == "m4a1":
        text = "M4A1"
    return text if re.fullmatch(r"[A-Za-z0-9_]{2,120}", text) else ""


def validate_xml_fragment(label: str, xml_text: str) -> None:
    try:
        ET.fromstring(f"<root>{xml_text}</root>")
    except ET.ParseError as error:
        raise ValueError(f"{label} XML validation failed: {error}") from error


def extract_dayz_vector(raw: Any) -> tuple[float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 3:
        return None
    try:
        return (float(raw[0]), float(raw[1]), float(raw[2]))
    except (TypeError, ValueError):
        return None


def convert_dayz_editor_json(data: Any, event_name_value: Any) -> dict[str, Any]:
    event_name = sanitize_dayz_classname(event_name_value)
    if not event_name:
        raise ValueError("Event Name must be a valid DayZ classname style value, for example Event_MyCustomBase.")
    if isinstance(data, dict):
        objects = data.get("EditorObjects")
    else:
        objects = data
    if not isinstance(objects, list):
        raise ValueError("Invalid DayZ Editor JSON format: missing EditorObjects array.")

    warnings: list[str] = []
    valid_objects: list[dict[str, Any]] = []
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            warnings.append(f"Skipped row {index + 1}: object entry is not a JSON object.")
            continue
        item_type = sanitize_dayz_classname(item.get("Type"))
        position = extract_dayz_vector(item.get("Position"))
        orientation = extract_dayz_vector(item.get("Orientation"))
        if not item_type or position is None or orientation is None:
            warnings.append(f"Skipped row {index + 1}: missing or invalid Type, Position or Orientation.")
            continue
        valid_objects.append({
            "source_index": index,
            "type": item_type,
            "position": position,
            "orientation": orientation,
        })
    if not valid_objects:
        raise ValueError("Invalid DayZ Editor JSON format: no valid objects were found.")
    if valid_objects[0]["source_index"] != 0:
        warnings.append("The first exported object was invalid, so the first valid object was used as the parent anchor.")

    parent = valid_objects[0]
    parent_position = parent["position"]
    parent_orientation = parent["orientation"]

    events_xml = "\n".join([
        f'<event name="{xml_attr(event_name)}">',
        "    <nominal>1</nominal>",
        "    <min>1</min>",
        "    <max>1</max>",
        "    <lifetime>3888000</lifetime>",
        "    <restock>0</restock>",
        "    <saferadius>100</saferadius>",
        "    <distanceradius>100</distanceradius>",
        "    <cleanupradius>100</cleanupradius>",
        '    <flags deletable="0" init_random="0" remove_damaged="0"/>',
        "    <position>fixed</position>",
        "    <limit>child</limit>",
        "    <active>1</active>",
        "    <children/>",
        "</event>",
    ])
    eventspawns_xml = "\n".join([
        f'<event name="{xml_attr(event_name)}">',
        f'    <zone pos="{xml_attr(xml_vector(parent_position))}" r="10" />',
        "</event>",
    ])
    group_lines = [
        f'<group name="{xml_attr(event_name)}">',
        "    <!-- Parent Anchor (always zero offsets, original parent rotation) -->",
        f'    <child type="{xml_attr(parent["type"])}" offset="0 0 0" rpy="{xml_attr(xml_vector(parent_orientation))}" a="0" />',
    ]
    if len(valid_objects) > 1:
        group_lines.append("    <!-- Child items use offsets from the parent anchor and relative rotation -->")
    for child in valid_objects[1:]:
        position = child["position"]
        orientation = child["orientation"]
        offset = (
            position[0] - parent_position[0],
            position[1] - parent_position[1],
            position[2] - parent_position[2],
        )
        relative_rotation = (
            normalize_dayz_angle(orientation[0] - parent_orientation[0]),
            normalize_dayz_angle(orientation[1] - parent_orientation[1]),
            normalize_dayz_angle(orientation[2] - parent_orientation[2]),
        )
        group_lines.append(
            f'    <child type="{xml_attr(child["type"])}" offset="{xml_attr(xml_vector(offset))}" rpy="{xml_attr(xml_vector(relative_rotation))}" a="0" />'
        )
    group_lines.append("</group>")
    eventgroups_xml = "\n".join(group_lines)

    validate_xml_fragment("events.xml", events_xml)
    validate_xml_fragment("eventspawns.xml", eventspawns_xml)
    validate_xml_fragment("eventgroups.xml", eventgroups_xml)
    return {
        "events_xml": events_xml,
        "eventspawns_xml": eventspawns_xml,
        "eventgroups_xml": eventgroups_xml,
        "warnings": warnings,
        "object_count": len(valid_objects),
    }


def read_uploaded_or_pasted_text(file_key: str, text_key: str, payload: dict[str, Any]) -> str:
    uploaded = request.files.get(file_key)
    if uploaded and uploaded.filename:
        return uploaded.read().decode("utf-8-sig", errors="replace")
    return str(payload.get(text_key) or "").strip()


def parse_json_payload_text(text: str) -> Any:
    if not text:
        raise ValueError("Upload or paste a JSON file first.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid DayZ Editor JSON format: {error.msg}") from error


def strip_json_trailing_commas(text: str) -> str:
    previous = None
    cleaned = str(text or "").strip()
    pattern = re.compile(r",(\s*[}\]])")
    while cleaned != previous:
        previous = cleaned
        cleaned = pattern.sub(r"\1", cleaned)
    return cleaned


def parse_strict_dashboard_json(text: str, label: str) -> Any:
    cleaned = strip_json_trailing_commas(text)
    if not cleaned:
        raise ValueError(f"{label} is empty.")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} JSON failed validation at line {error.lineno}, column {error.colno}: {error.msg}") from error


def default_cfggameplay_spawngear_config() -> dict[str, Any]:
    return {
        "version": 121,
        "GeneralData": {
            "disableBaseDamage": False,
        },
        "PlayerData": {
            "disablePersonalLight": False,
            "SpawnGear": {
                "useCustomSpawnGear": True,
                "customSpawnGearFilePath": "custom/custom_loadout.json",
            },
        },
    }


def normalize_cfggameplay_for_loadout(raw: Any) -> dict[str, Any]:
    config = raw if isinstance(raw, dict) else {}
    if not config:
        config = default_cfggameplay_spawngear_config()
    config.setdefault("version", 121)
    general = config.setdefault("GeneralData", {})
    if not isinstance(general, dict):
        general = {}
        config["GeneralData"] = general
    general.setdefault("disableBaseDamage", False)
    player = config.setdefault("PlayerData", {})
    if not isinstance(player, dict):
        player = {}
        config["PlayerData"] = player
    player.setdefault("disablePersonalLight", False)
    spawn = player.setdefault("SpawnGear", {})
    if not isinstance(spawn, dict):
        spawn = {}
        player["SpawnGear"] = spawn
    spawn["useCustomSpawnGear"] = True
    spawn["customSpawnGearFilePath"] = "custom/custom_loadout.json"
    return config


def build_loadout_package_zip(loadout_payload: Any, cfggameplay_payload: Any | None = None) -> io.BytesIO:
    if not isinstance(loadout_payload, dict):
        raise ValueError("custom_loadout.json must be a JSON object.")
    player_data = loadout_payload.get("PlayerData")
    if not isinstance(player_data, dict) or not isinstance(player_data.get("SpawnGear"), dict):
        raise ValueError("custom_loadout.json must include PlayerData.SpawnGear.")
    cfggameplay = normalize_cfggameplay_for_loadout(cfggameplay_payload)
    loadout_text = json.dumps(loadout_payload, indent=2, ensure_ascii=False)
    cfggameplay_text = json.dumps(cfggameplay, indent=2, ensure_ascii=False)
    parse_strict_dashboard_json(loadout_text, "custom_loadout.json")
    parse_strict_dashboard_json(cfggameplay_text, "cfggameplay.json")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("custom/custom_loadout.json", loadout_text + "\n")
        archive.writestr("cfggameplay.json", cfggameplay_text + "\n")
    buffer.seek(0)
    return buffer


def sanitize_xml_boolean_flags(xml_text: str) -> str:
    def tag_replacer(match: re.Match[str]) -> str:
        tag = match.group(0)
        return re.sub(
            r"(\b[A-Za-z0-9_:-]+\s*=\s*[\"'])(true|false)([\"'])",
            lambda flag: f"{flag.group(1)}{'1' if flag.group(2).lower() == 'true' else '0'}{flag.group(3)}",
            tag,
            flags=re.IGNORECASE,
        )

    return re.sub(r"<flags\b[^>]*/?>", tag_replacer, str(xml_text or ""), flags=re.IGNORECASE)


def dashboard_canonical_remote_path(path: Any) -> str:
    clean = str(path or "").replace("\\", "/").strip().strip("`'\"<>")
    if not clean:
        return ""
    clean = re.sub(r"/+", "/", clean)
    if not clean.startswith("/"):
        clean = "/" + clean
    for root in ("dayzxb_missions", "dayzps_missions", "dayz_missions"):
        clean = re.sub(rf"(/(?:{root}))(?:/{root})+/", r"\1/", clean)
    for root in ("dayzxb", "dayzps", "dayz"):
        clean = re.sub(rf"(/(?:{root}))(?:/{root})+/", r"\1/", clean)
    return clean.rstrip("/") or "/"


def validate_dashboard_remote_path(path: Any) -> str:
    clean = dashboard_canonical_remote_path(path)
    if not clean or clean == "/":
        raise ValueError("Remote server path is required.")
    if "\x00" in clean or re.search(r"[\r\n\t]", clean):
        raise ValueError("Remote server path contains hidden control characters.")
    if ".." in clean.split("/"):
        raise ValueError("Remote server path cannot contain .. segments.")
    suffix = clean.rsplit("/", 1)[-1].lower()
    if not re.search(r"\.(xml|json|txt|c)$", suffix):
        raise ValueError("Remote server path must target a .xml, .json, .txt or .c file.")
    return clean


def normalize_dashboard_server_platform(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())
    if text in {"ps", "ps4", "ps5", "playstation", "dayzps"}:
        return "playstation"
    if text in {"pc", "steam", "windows", "dayzpc"}:
        return "pc"
    return "xbox"


def dashboard_server_platform_label(value: Any) -> str:
    key = normalize_dashboard_server_platform(value)
    if key == "playstation":
        return "PlayStation"
    if key == "pc":
        return "PC"
    return "Xbox"


def dashboard_server_map_key(config: dict[str, Any] | None) -> str:
    config = config if isinstance(config, dict) else {}
    configured = str(config.get("server_map") or config.get("map") or "").strip().lower()
    guild_name = str(config.get("guild_name") or "").strip().lower()
    text = configured or guild_name
    if any(term in text for term in ("livonia", "livo", "enoch")):
        return "livonia"
    if "sakhal" in text:
        return "sakhal"
    return "chernarus"


def dashboard_mission_folder_for_map(map_key: str) -> str:
    if map_key == "livonia":
        return "dayzOffline.enoch"
    if map_key == "sakhal":
        return "dayzOffline.sakhal"
    return "dayzOffline.chernarusplus"


def dashboard_mission_root_for_platform(platform_key: str) -> str:
    platform_key = normalize_dashboard_server_platform(platform_key)
    if platform_key == "playstation":
        return "/dayzps_missions"
    if platform_key == "pc":
        return "/mpmissions"
    return "/dayzxb_missions"


def dashboard_default_ce_paths(config: dict[str, Any] | None) -> dict[str, str]:
    config = config if isinstance(config, dict) else {}
    map_key = dashboard_server_map_key(config)
    mission_folder = dashboard_mission_folder_for_map(map_key)
    platform_key = normalize_dashboard_server_platform(config.get("server_platform") or config.get("platform"))
    root = dashboard_mission_root_for_platform(platform_key)
    return {
        "events_path": f"{root}/{mission_folder}/db/events.xml",
        "eventspawns_path": f"{root}/{mission_folder}/cfgeventspawns.xml",
        "eventgroups_path": f"{root}/{mission_folder}/cfgeventgroups.xml",
        "types_path": f"{root}/{mission_folder}/db/types.xml",
        "cfggameplay_path": f"{root}/{mission_folder}/cfggameplay.json",
        "custom_loadout_path": f"{root}/{mission_folder}/custom/custom_loadout.json",
    }


def dashboard_is_noftp_dayz_path(path: Any) -> bool:
    clean = dashboard_canonical_remote_path(path)
    prefixes = (
        "/dayz/",
        "/dayz_missions",
        "/dayz_missions/",
        "/dayzps/",
        "/dayzps_missions",
        "/dayzps_missions/",
        "/dayzxb/",
        "/dayzxb_missions",
        "/dayzxb_missions/",
        "/dayzserver/",
        "/dayzxbserver/",
        "/mpmissions/",
    )
    return any(clean == prefix.rstrip("/") or clean.startswith(prefix) for prefix in prefixes)


def dashboard_nitrado_api_headers(config: dict[str, Any]) -> dict[str, str] | None:
    token = config.get("nitrado_token")
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def dashboard_nitrado_api_service_url(config: dict[str, Any], endpoint: str) -> str | None:
    service_id = config.get("service_id")
    if not service_id:
        return None
    endpoint = str(endpoint or "").lstrip("/")
    return f"https://api.nitrado.net/services/{service_id}/gameservers/file_server/{endpoint}"


def dashboard_nitrado_api_file_path(config: dict[str, Any], target_path: Any) -> str:
    clean = dashboard_canonical_remote_path(target_path)
    if not clean:
        return clean
    if clean.startswith("/games/"):
        return clean
    nitrado_user = str(config.get("nitrado_user") or "").strip()
    if nitrado_user and dashboard_is_noftp_dayz_path(clean):
        return f"/games/{nitrado_user}/noftp{clean}"
    if nitrado_user and clean.startswith("/noftp/"):
        return f"/games/{nitrado_user}{clean}"
    return clean


def dashboard_nitrado_api_file_path_candidates(config: dict[str, Any], target_path: Any) -> list[str]:
    clean = dashboard_canonical_remote_path(target_path)
    if not clean:
        return []
    candidates = [dashboard_nitrado_api_file_path(config, clean), clean]
    nitrado_user = str(config.get("nitrado_user") or "").strip()
    if nitrado_user:
        if dashboard_is_noftp_dayz_path(clean):
            candidates.extend([
                f"/games/{nitrado_user}/noftp{clean}",
                f"/games/{nitrado_user}{clean}",
            ])
        elif clean.startswith("/noftp/"):
            candidates.append(f"/games/{nitrado_user}{clean}")
    out: list[str] = []
    for candidate in candidates:
        candidate = dashboard_canonical_remote_path(candidate)
        if candidate and candidate not in out:
            out.append(candidate)
    return out


def dashboard_split_remote_file_path(target_path: Any) -> tuple[str, str]:
    clean = dashboard_canonical_remote_path(target_path)
    folder = os.path.dirname(clean) or "/"
    name = os.path.basename(clean)
    return folder, name


def dashboard_nitrado_response_json(response: Any, label: str) -> tuple[dict[str, Any] | None, str]:
    try:
        data = response.json()
    except Exception:
        body = str(getattr(response, "text", "") or "").strip()
        snippet = body[:300] if body else "<empty response body>"
        status = getattr(response, "status_code", "unknown")
        return None, f"{label} returned non-JSON response ({status}): {snippet}"
    if not isinstance(data, dict):
        return None, f"{label} returned unexpected JSON payload: {type(data).__name__}"
    return data, ""


def dashboard_nitrado_api_token_payload(data: dict[str, Any]) -> tuple[str | None, str | None]:
    if not isinstance(data, dict):
        return None, None
    token_data = data.get("token") or data.get("data", {}).get("token") or {}
    token_url = token_data.get("url") or data.get("url")
    token_value = token_data.get("token") or data.get("token")
    if isinstance(token_value, dict):
        token_value = token_value.get("token")
    return token_url, token_value


def dashboard_download_text_file_from_nitrado(config: dict[str, Any], target_path: Any) -> tuple[bool, str, str | None]:
    headers = dashboard_nitrado_api_headers(config)
    url = dashboard_nitrado_api_service_url(config, "download")
    if not headers or not url:
        return False, "Nitrado API token or service ID is missing.", None
    attempts: list[str] = []
    try:
        for api_path in dashboard_nitrado_api_file_path_candidates(config, target_path):
            for param_name in ("file", "path"):
                response = requests.get(url, headers=headers, params={param_name: api_path}, timeout=15)
                if response.status_code != 200:
                    attempts.append(f"{param_name}={api_path}: {response.status_code} {response.text[:160]}")
                    continue
                response_data, json_error = dashboard_nitrado_response_json(response, f"Nitrado download token for `{api_path}`")
                if json_error:
                    attempts.append(f"{param_name}={api_path}: {json_error}")
                    continue
                token_url, token_value = dashboard_nitrado_api_token_payload(response_data.get("data", response_data))
                if not token_url:
                    attempts.append(f"{param_name}={api_path}: no download URL")
                    continue
                file_response = requests.get(
                    token_url,
                    params={"token": token_value} if token_value else None,
                    timeout=20,
                )
                if file_response.status_code != 200:
                    attempts.append(f"{param_name}={api_path}: file {file_response.status_code} {file_response.text[:160]}")
                    continue
                content = file_response.content.decode("utf-8-sig", errors="replace")
                return True, f"Downloaded `{api_path}`.", content
    except Exception as error:
        return False, f"Nitrado API download failed: {error}", None
    return False, "Nitrado API download failed for all path variants: " + "; ".join(attempts[-6:]), None


def dashboard_ensure_nitrado_api_folder(config: dict[str, Any], folder: Any) -> None:
    headers = dashboard_nitrado_api_headers(config)
    url = dashboard_nitrado_api_service_url(config, "mkdir")
    if not headers or not url:
        return
    folder = dashboard_nitrado_api_file_path(config, folder)
    parent = os.path.dirname(folder.rstrip("/")) or "/"
    name = os.path.basename(folder.rstrip("/"))
    if not name:
        return
    try:
        requests.post(url, headers=headers, data={"path": parent, "name": name}, timeout=20)
    except Exception:
        pass


def dashboard_upload_text_file_to_nitrado(config: dict[str, Any], target_path: Any, text_content: Any) -> tuple[bool, str]:
    headers = dashboard_nitrado_api_headers(config)
    url = dashboard_nitrado_api_service_url(config, "upload")
    if not headers or not url:
        return False, "Nitrado API token or service ID is missing."
    api_target_path = dashboard_nitrado_api_file_path(config, target_path)
    folder, name = dashboard_split_remote_file_path(api_target_path)
    if not name:
        return False, "Remote file name is missing."
    try:
        dashboard_ensure_nitrado_api_folder(config, folder)
        token_response = requests.post(url, headers=headers, data={"path": folder, "file": name}, timeout=20)
        if token_response.status_code not in (200, 201):
            return False, f"Nitrado upload token failed with status {token_response.status_code}: {token_response.text[:300]}"
        token_data, json_error = dashboard_nitrado_response_json(token_response, f"Nitrado upload token for `{api_target_path}`")
        if json_error:
            return False, json_error
        token_url, token_value = dashboard_nitrado_api_token_payload(token_data.get("data", token_data))
        if not token_url or not token_value:
            return False, "Nitrado API did not return an upload URL/token."
        upload_response = requests.post(
            token_url,
            headers={"content-type": "application/binary", "token": token_value},
            data=str(text_content or "").encode("utf-8"),
            timeout=30,
        )
        if upload_response.status_code not in (200, 201, 204):
            return False, f"Nitrado file upload failed with status {upload_response.status_code}: {upload_response.text[:300]}"
        return True, "Uploaded successfully via Nitrado API."
    except Exception as error:
        return False, f"Nitrado API upload failed: {error}"


def validate_live_injection_content(file_kind: Any, text: Any, label: str) -> str:
    kind = str(file_kind or "").strip().lower()
    content = str(text or "").strip()
    if not content:
        raise ValueError(f"{label} content is empty.")
    if kind == "json":
        parsed = parse_strict_dashboard_json(content, label)
        return json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    if kind == "xml":
        content = sanitize_xml_boolean_flags(content)
        try:
            root = ET.fromstring(content)
        except ET.ParseError as error:
            raise ValueError(f"{label} XML failed validation: {error}") from error
        if root.tag == "types":
            validate_types_xml_flags(root)
        return content if content.endswith("\n") else content + "\n"
    raise ValueError("Unsupported live injection file kind.")


def guarded_dashboard_file_injection(
    config: dict[str, Any],
    target_path: Any,
    text_content: Any,
    *,
    file_kind: str,
    label: str,
    allow_create: bool = False,
) -> dict[str, Any]:
    remote_path = validate_dashboard_remote_path(target_path)
    safe_text = validate_live_injection_content(file_kind, text_content, label)
    exists, download_message, existing_text = dashboard_download_text_file_from_nitrado(config, remote_path)
    missing_file = any(term in str(download_message).lower() for term in ("404", "not found", "does not exist", "no such file"))
    backup_path = ""
    if exists and existing_text is not None:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        backup_path = f"{remote_path}.wanderingbot-backup-{stamp}"
        backup_ok, backup_message = dashboard_upload_text_file_to_nitrado(config, backup_path, existing_text)
        if not backup_ok:
            raise ValueError(f"Backup failed before upload: {backup_message}")
    elif not allow_create or not missing_file:
        raise ValueError(f"Live file was not found, so upload was stopped: {download_message}")

    upload_ok, upload_message = dashboard_upload_text_file_to_nitrado(config, remote_path, safe_text)
    if not upload_ok:
        raise ValueError(upload_message)
    return {
        "path": remote_path,
        "backup_path": backup_path,
        "created": not exists,
        "message": upload_message,
    }


def serialize_xml_root(root: ET.Element, *, xml_declaration: bool = True) -> str:
    try:
        ET.indent(root, space="    ")
    except Exception:
        pass
    body = ET.tostring(root, encoding="unicode")
    if not xml_declaration:
        return body if body.endswith("\n") else body + "\n"
    return "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n" + body + "\n"


def merge_named_xml_child(existing_text: str | None, snippet_text: Any, *, root_tag: str, child_tag: str, label: str) -> tuple[str, str]:
    snippet = str(snippet_text or "").strip()
    if not snippet:
        raise ValueError(f"{label} snippet is empty.")
    try:
        child = ET.fromstring(snippet)
    except ET.ParseError as error:
        raise ValueError(f"{label} snippet failed validation: {error}") from error
    if child.tag != child_tag:
        raise ValueError(f"{label} must be a <{child_tag}> snippet, not <{child.tag}>.")
    name = str(child.get("name") or "").strip()
    if not name:
        raise ValueError(f"{label} snippet is missing a name attribute.")

    existing = str(existing_text or "").strip()
    if existing:
        try:
            root = ET.fromstring(existing)
        except ET.ParseError as error:
            raise ValueError(f"Live {label} XML failed validation before merge: {error}") from error
        if root.tag != root_tag:
            raise ValueError(f"Live {label} root must be <{root_tag}>, not <{root.tag}>.")
    else:
        root = ET.Element(root_tag)

    replaced = False
    for node in list(root):
        if node.tag == child_tag and str(node.get("name") or "") == name:
            root.remove(node)
            replaced = True
    root.append(child)
    return serialize_xml_root(root), ("replaced" if replaced else "added")


def guarded_dashboard_xml_merge(
    config: dict[str, Any],
    target_path: Any,
    snippet_text: Any,
    *,
    root_tag: str,
    child_tag: str,
    label: str,
    allow_create: bool = False,
) -> dict[str, Any]:
    remote_path = validate_dashboard_remote_path(target_path)
    exists, download_message, existing_text = dashboard_download_text_file_from_nitrado(config, remote_path)
    missing_file = any(term in str(download_message).lower() for term in ("404", "not found", "does not exist", "no such file"))
    if not exists and (not allow_create or not missing_file):
        raise ValueError(f"Live {label} file was not found, so merge was stopped: {download_message}")
    merged_text, action = merge_named_xml_child(existing_text if exists else None, snippet_text, root_tag=root_tag, child_tag=child_tag, label=label)
    backup_path = ""
    if exists and existing_text is not None:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        backup_path = f"{remote_path}.wanderingbot-backup-{stamp}"
        backup_ok, backup_message = dashboard_upload_text_file_to_nitrado(config, backup_path, existing_text)
        if not backup_ok:
            raise ValueError(f"Backup failed before merge upload: {backup_message}")
    upload_ok, upload_message = dashboard_upload_text_file_to_nitrado(config, remote_path, merged_text)
    if not upload_ok:
        raise ValueError(upload_message)
    return {
        "path": remote_path,
        "backup_path": backup_path,
        "created": not exists,
        "merge_action": action,
        "message": upload_message,
    }


def split_class_list(value: Any, limit: int = 80) -> list[str]:
    rows: list[str] = []
    for raw in re.split(r"[\n,;]+", str(value or "")):
        item = sanitize_dayz_classname(raw)
        if item:
            rows.append(item)
        if len(rows) >= limit:
            break
    return rows


def validate_types_xml_flags(root: ET.Element) -> None:
    for flags in root.iter("flags"):
        for key, value in flags.attrib.items():
            if str(value) not in {"0", "1"}:
                raise ValueError(f'types.xml flag {key} must be "0" or "1", not "{value}".')


def replace_or_insert_simple_xml_tag(block: str, tag: str, value: int) -> str:
    pattern = re.compile(rf"(<{re.escape(tag)}>\s*)[^<]*(\s*</{re.escape(tag)}>)", re.IGNORECASE)
    if pattern.search(block):
        return pattern.sub(lambda match: f"{match.group(1)}{value}{match.group(2)}", block, count=1)
    return re.sub(r"(</type\s*>)", f"    <{tag}>{value}</{tag}>\n\\1", block, count=1, flags=re.IGNORECASE)


def tweak_types_xml(payload: dict[str, Any]) -> dict[str, Any]:
    xml_text = sanitize_xml_boolean_flags(str(payload.get("xml_text") or "").strip())
    if not xml_text:
        raise ValueError("Paste a full types.xml file or one <type> block first.")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise ValueError(f"XML parse failed: {error}") from error
    if root.tag not in {"types", "type"}:
        raise ValueError("Input must be a types.xml file or a single <type> block.")
    validate_types_xml_flags(root)
    item_name = sanitize_dayz_classname(payload.get("item_name"))
    if not item_name and root.tag == "type":
        item_name = sanitize_dayz_classname(root.attrib.get("name"))
    if not item_name:
        raise ValueError("Item classname is required.")
    updates: dict[str, int] = {}
    for tag in ("nominal", "min", "lifetime", "restock"):
        raw = str(payload.get(tag) or "").strip()
        if raw:
            updates[tag] = max(0, safe_int(raw, 0))
    if not updates:
        raise ValueError("Enter at least one numeric field to change.")

    pattern = re.compile(
        rf"(<type\b[^>]*\bname\s*=\s*['\"]{re.escape(item_name)}['\"][^>]*>)(.*?)(</type\s*>)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(xml_text)
    if not match:
        raise ValueError(f"{item_name} was not found in the pasted XML.")
    type_block = "".join(match.groups())
    for tag, value in updates.items():
        type_block = replace_or_insert_simple_xml_tag(type_block, tag, value)
    generated_xml = xml_text[:match.start()] + type_block + xml_text[match.end():]
    try:
        generated_root = ET.fromstring(generated_xml)
        validate_types_xml_flags(generated_root)
    except ET.ParseError as error:
        raise ValueError(f"Generated XML failed validation: {error}") from error
    return {"generated_xml": generated_xml, "changed_fields": sorted(updates)}


def type_matches_bulk_filter(type_node: ET.Element, filter_text: str, match_mode: str) -> bool:
    if not filter_text:
        return True
    name = str(type_node.get("name") or "")
    haystack = name.lower()
    needle = filter_text.lower()
    if match_mode == "startswith":
        return haystack.startswith(needle)
    if match_mode == "endswith":
        return haystack.endswith(needle)
    if match_mode == "regex":
        try:
            return re.search(filter_text, name, flags=re.IGNORECASE) is not None
        except re.error as error:
            raise ValueError(f"Invalid regex filter: {error}") from error
    return needle in haystack


def set_simple_xml_child(type_node: ET.Element, tag: str, value: int) -> bool:
    node = type_node.find(tag)
    if node is None:
        node = ET.SubElement(type_node, tag)
        node.text = str(value)
        return True
    old = str(node.text or "").strip()
    node.text = str(value)
    return old != str(value)


def bulk_tweak_types_xml(payload: dict[str, Any]) -> dict[str, Any]:
    xml_text = sanitize_xml_boolean_flags(str(payload.get("xml_text") or "").strip())
    if not xml_text:
        raise ValueError("Paste a full types.xml file first.")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise ValueError(f"XML parse failed: {error}") from error
    if root.tag not in {"types", "type"}:
        raise ValueError("Input must be a types.xml file or a single <type> block.")
    validate_types_xml_flags(root)

    filter_text = str(payload.get("filter_text") or "").strip()
    match_mode = str(payload.get("match_mode") or "contains").strip().lower()
    if match_mode not in {"contains", "startswith", "endswith", "regex"}:
        match_mode = "contains"
    multiplier_raw = str(payload.get("nominal_multiplier") or "").strip()
    multiplier = None
    if multiplier_raw:
        try:
            multiplier = max(0.0, min(20.0, float(multiplier_raw)))
        except ValueError as error:
            raise ValueError("Multiply nominal must be a number.") from error
    flat_updates: dict[str, int] = {}
    for form_key, tag in (("lifetime_value", "lifetime"), ("restock_value", "restock"), ("min_value", "min")):
        raw = str(payload.get(form_key) or "").strip()
        if raw:
            flat_updates[tag] = max(0, safe_int(raw, 0))
    if multiplier is None and not flat_updates:
        raise ValueError("Choose a nominal multiplier or at least one flat field update.")

    type_nodes = [root] if root.tag == "type" else list(root.findall(".//type"))
    matched = 0
    changed = 0
    for type_node in type_nodes:
        if not type_matches_bulk_filter(type_node, filter_text, match_mode):
            continue
        matched += 1
        if multiplier is not None:
            nominal = type_node.find("nominal")
            if nominal is not None:
                current = safe_int(nominal.text, 0)
                new_value = max(0, int(round(current * multiplier)))
                if set_simple_xml_child(type_node, "nominal", new_value):
                    changed += 1
        for tag, value in flat_updates.items():
            if set_simple_xml_child(type_node, tag, value):
                changed += 1

    if matched <= 0:
        raise ValueError("No <type> entries matched that filter.")
    try:
        ET.indent(root, space="    ")
    except Exception:
        pass
    generated_xml = ET.tostring(root, encoding="unicode")
    try:
        generated_root = ET.fromstring(generated_xml)
        validate_types_xml_flags(generated_root)
    except ET.ParseError as error:
        raise ValueError(f"Generated XML failed validation: {error}") from error
    return {"generated_xml": generated_xml, "matched": matched, "changed": changed}


def build_player_loadout_xml(payload: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    primary = sanitize_dayz_classname(payload.get("item_name"))
    if primary:
        rows.append({
            "item": primary,
            "attachments": split_class_list(payload.get("attachments"), 20),
            "chance": dayz_xml_chance(payload.get("chance"), 1.0),
        })
    for raw in re.split(r"[\n;]+", str(payload.get("items") or "")):
        parts = [part.strip() for part in raw.split("|")]
        if not parts or not parts[0]:
            continue
        item = sanitize_dayz_classname(parts[0])
        if not item:
            continue
        rows.append({
            "item": item,
            "attachments": split_class_list(parts[1] if len(parts) > 1 else "", 20),
            "chance": dayz_xml_chance(parts[2] if len(parts) > 2 else 1.0, 1.0),
        })
    if not rows:
        raise ValueError("Add at least one valid loadout item.")
    lines: list[str] = []
    for row in rows[:80]:
        lines.append(f'<item name="{xml_attr(row["item"])}" chance="{row["chance"]}">')
        for attachment in row["attachments"]:
            lines.append(f'    <attachment name="{xml_attr(attachment)}" chance="1.00" />')
        lines.append("</item>")
    generated_xml = "\n".join(lines)
    validate_xml_fragment("loadout", generated_xml)
    return {"generated_xml": generated_xml, "item_count": len(rows)}


def default_vehicle_spawn_parts(vehicle_class: str) -> dict[str, list[str]]:
    key = vehicle_class.lower()
    mapping = {
        "offroadhatchback": {
            "wheels": ["HatchbackWheel", "HatchbackWheel", "HatchbackWheel", "HatchbackWheel"],
            "doors": ["HatchbackDoors_Driver", "HatchbackDoors_CoDriver", "HatchbackHood", "HatchbackTrunk"],
        },
        "civiliansedan": {
            "wheels": ["CivSedanWheel", "CivSedanWheel", "CivSedanWheel", "CivSedanWheel"],
            "doors": ["CivSedanDoors_Driver", "CivSedanDoors_CoDriver", "CivSedanDoors_BackLeft", "CivSedanDoors_BackRight", "CivSedanHood", "CivSedanTrunk"],
        },
        "truck_01_covered": {
            "wheels": ["Truck_01_Wheel", "Truck_01_Wheel", "Truck_01_WheelDouble", "Truck_01_WheelDouble"],
            "doors": ["Truck_01_Door_1_1", "Truck_01_Door_2_1", "Truck_01_Hood"],
        },
    }
    return mapping.get(key, {
        "wheels": ["HatchbackWheel", "HatchbackWheel", "HatchbackWheel", "HatchbackWheel"],
        "doors": ["HatchbackDoors_Driver", "HatchbackDoors_CoDriver"],
    })


def build_vehicle_spawnabletypes_xml(payload: dict[str, Any]) -> dict[str, Any]:
    vehicle_class = sanitize_dayz_classname(payload.get("vehicle_class"))
    if not vehicle_class:
        raise ValueError("Vehicle classname is required.")
    if disallowed_vehicle_part_class(vehicle_class):
        raise ValueError("Use a whole vehicle classname, not a wheel, door, radiator or other part.")
    parts = default_vehicle_spawn_parts(vehicle_class)
    wheel_chance = dayz_xml_chance(payload.get("wheel_chance"), 0.8)
    door_chance = dayz_xml_chance(payload.get("door_chance"), 0.5)
    radiator_chance = dayz_xml_chance(payload.get("radiator_chance"), 1.0)
    battery_chance = dayz_xml_chance(payload.get("battery_chance"), 1.0)
    fuel_chance = dayz_xml_chance(payload.get("fuel_chance"), 1.0)
    lines = [
        f'<type name="{xml_attr(vehicle_class)}">',
        '    <attachments chance="1.00">',
    ]
    for item in parts["wheels"]:
        lines.append(f'        <item name="{xml_attr(item)}" chance="{wheel_chance}" />')
    for item in parts["doors"]:
        lines.append(f'        <item name="{xml_attr(item)}" chance="{door_chance}" />')
    lines.extend([
        f'        <item name="CarRadiator" chance="{radiator_chance}" />',
        f'        <item name="CarBattery" chance="{battery_chance}" />',
        f'        <item name="SparkPlug" chance="{fuel_chance}" />',
        "    </attachments>",
    ])
    cargo_items = split_class_list(payload.get("cargo_items"), 40)
    if cargo_items:
        lines.append('    <cargo chance="1.00">')
        for item in cargo_items:
            lines.append(f'        <item name="{xml_attr(item)}" chance="1.00" />')
        lines.append("    </cargo>")
    lines.append("</type>")
    generated_xml = "\n".join(lines)
    validate_xml_fragment("cfgspawnabletypes", generated_xml)
    return {"generated_xml": generated_xml, "part_count": len(parts["wheels"]) + len(parts["doors"]) + 3}


def parse_airdrop_positions(value: Any) -> list[dict[str, str]]:
    rows = []
    for raw in re.split(r"[\n;]+", str(value or "")):
        parts = [part.strip() for part in re.split(r"[,\s]+", raw) if part.strip()]
        if len(parts) < 2:
            continue
        try:
            x = f"{float(parts[0]):.2f}".rstrip("0").rstrip(".")
            z = f"{float(parts[1]):.2f}".rstrip("0").rstrip(".")
        except ValueError:
            continue
        rows.append({"x": x, "z": z})
        if len(rows) >= 80:
            break
    return rows


def parse_xml_workshop_items(value: Any, max_rows: int = 80) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        candidates = value
    else:
        candidates = re.split(r"[\n;]+", str(value or ""))
    for raw in candidates:
        if len(rows) >= max_rows:
            break
        if isinstance(raw, dict):
            item_name = safe_dayz_class(raw.get("item") or raw.get("name"))
            quantity = safe_int(raw.get("quantity"), 1)
            quantity_percent = safe_int(raw.get("quantity_percent"), safe_int(raw.get("quantityPercent"), -1))
            damage = str(raw.get("damage") or "pristine").strip().lower()
            slot = str(raw.get("slot") or "").strip()
            attachment_for = str(raw.get("attachment_for") or raw.get("attachmentFor") or "").strip()
        else:
            parts = [part.strip() for part in re.split(r"[|,]", str(raw or "")) if part.strip()]
            if not parts:
                continue
            item_name = safe_dayz_class(parts[0])
            quantity = safe_int(parts[1], 1) if len(parts) > 1 else 1
            quantity_percent = safe_int(parts[2], -1) if len(parts) > 2 else -1
            damage = str(parts[3] if len(parts) > 3 else "pristine").strip().lower()
            slot = str(parts[4] if len(parts) > 4 else "").strip()
            attachment_for = str(parts[5] if len(parts) > 5 else "").strip()
        if not item_name:
            continue
        if damage not in {"pristine", "worn", "damaged", "badly_damaged", "ruined", "random"}:
            damage = "pristine"
        rows.append({
            "item": item_name,
            "quantity": max(1, min(999, quantity)),
            "quantity_percent": max(-1, min(100, quantity_percent)),
            "damage": damage,
            "slot": slot[:40],
            "attachment_for": safe_dayz_class(attachment_for),
        })
    return rows


def safe_custom_json_path(value: Any, fallback_name: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        text = f"./custom/{fallback_name}.json"
    if not text.startswith("./custom/"):
        text = "./custom/" + text.lstrip("/").removeprefix("custom/")
    if not text.lower().endswith(".json"):
        text += ".json"
    safe = re.sub(r"[^A-Za-z0-9_./-]+", "_", text)
    return safe[:160]


def loadout_item_attributes(item: dict[str, Any]) -> dict[str, Any]:
    damage = str(item.get("damage") or "pristine")
    health = {
        "pristine": (1.0, 1.0),
        "worn": (0.7, 1.0),
        "damaged": (0.45, 0.7),
        "badly_damaged": (0.2, 0.45),
        "ruined": (0.0, 0.2),
        "random": (0.2, 1.0),
    }.get(damage, (1.0, 1.0))
    attrs: dict[str, Any] = {"healthMin": health[0], "healthMax": health[1]}
    quantity = safe_int(item.get("quantity_percent"), -1)
    if quantity >= 0:
        attrs["quantityMin"] = quantity / 100
        attrs["quantityMax"] = quantity / 100
    return attrs


def build_player_loadout_json(record: dict[str, Any]) -> dict[str, Any]:
    slot_items: dict[str, list[dict[str, Any]]] = {}
    unsorted = []
    for item in record.get("items", []):
        if not isinstance(item, dict):
            continue
        entry = {
            "itemType": item.get("item"),
            "spawnWeight": max(1, safe_int(item.get("quantity"), 1)),
            "attributes": loadout_item_attributes(item),
        }
        attachment_for = str(item.get("attachment_for") or "")
        if attachment_for:
            entry["attachmentFor"] = attachment_for
        slot = str(item.get("slot") or "").strip()
        if slot:
            slot_items.setdefault(slot, []).append(entry)
        else:
            unsorted.append(entry)
    return {
        "presets": [{
            "name": record.get("name") or "Wandering Bot Loadout",
            "spawnWeight": 1,
            "attachmentSlotItemSets": [
                {"slotName": slot, "discreteItemSets": [{"spawnWeight": 1, "items": items}]}
                for slot, items in sorted(slot_items.items())
            ],
            "discreteUnsortedItemSets": [{"spawnWeight": 1, "items": unsorted}] if unsorted else [],
        }]
    }


def empty_visual_loadout_draft() -> dict[str, Any]:
    return {
        "cloth": {},
        "attachments": {},
        "weaponAttachments": {},
        "children": {},
        "cargo": {"Backpack": [], "Torso": [], "Legs": []},
    }


def normalize_visual_loadout_draft(value: Any) -> dict[str, Any]:
    draft = empty_visual_loadout_draft()
    if not isinstance(value, dict):
        return draft
    for group in ("cloth", "attachments", "weaponAttachments"):
        if isinstance(value.get(group), dict):
            draft[group] = {
                str(key): value
                for key, value in value[group].items()
                if str(key).strip() and str(value).strip()
            }
    children = value.get("children")
    if isinstance(children, dict):
        for parent_key, parent_children in children.items():
            if not isinstance(parent_children, dict):
                continue
            clean_children: dict[str, Any] = {}
            for child_slot, child_value in parent_children.items():
                if isinstance(child_value, dict):
                    nested_clean: dict[str, Any] = {}
                    for nested_slot, nested_value in child_value.items():
                        if isinstance(nested_value, list):
                            nested_clean[str(nested_slot)] = [safe_dayz_class(item) for item in nested_value if safe_dayz_class(item)]
                        else:
                            clean_item = safe_dayz_class(nested_value)
                            if clean_item:
                                nested_clean[str(nested_slot)] = clean_item
                    if nested_clean:
                        clean_children[str(child_slot)] = nested_clean
                elif child_slot == "cargo" and isinstance(child_value, list):
                    clean_children["cargo"] = [safe_dayz_class(item) for item in child_value if safe_dayz_class(item)]
                else:
                    clean_item = safe_dayz_class(child_value)
                    if clean_item:
                        clean_children[str(child_slot)] = clean_item
            if clean_children:
                draft["children"][str(parent_key)] = clean_children
    cargo = value.get("cargo")
    if isinstance(cargo, dict):
        for container in draft["cargo"]:
            rows = cargo.get(container)
            if isinstance(rows, list):
                draft["cargo"][container] = [safe_dayz_class(item) for item in rows if safe_dayz_class(item)]
    return draft


def visual_loadout_slot_meta(slot: Any) -> dict[str, Any] | None:
    key = str(slot or "").strip()
    for item in VISUAL_LOADOUT_SLOTS:
        if item["key"] == key:
            return dict(item)
    for item in VISUAL_LOADOUT_CARGO_SLOTS:
        if item["key"] == key:
            return dict(item)
    return None


def build_visual_loadout_json(draft_value: Any) -> dict[str, Any]:
    draft = normalize_visual_loadout_draft(draft_value)
    weapon_slots = {
        slot: classname
        for slot, classname in draft["attachments"].items()
        if classname
    }
    weapon_attachments = {
        slot: {
            "item": classname,
            "attachments": draft["weaponAttachments"].get(slot, []),
        }
        for slot, classname in weapon_slots.items()
    }
    slot_details: dict[str, Any] = {}
    for slot, classname in {**draft["cloth"], **draft["attachments"]}.items():
        if classname:
            slot_details[slot] = {
                "item": classname,
                "damage": "pristine",
                "quantity": 100,
                "children": draft["children"].get(slot, {}),
            }
    return {
        "PlayerData": {
            "SpawnGear": {
                "unclothed": False,
                "cloth": [item for item in draft["cloth"].values() if item],
                "attachments": [item for item in weapon_slots.values() if item],
                "cargo": [item for rows in draft["cargo"].values() for item in rows if item],
                "slots": {
                    "cloth": draft["cloth"],
                    "weapons": weapon_attachments,
                    "cargo": draft["cargo"],
                    "children": draft["children"],
                    "slotDetails": slot_details,
                },
            }
        }
    }


def visual_loadout_items_for_view(groups: dict[str, Any], slot: str, category: str = "") -> list[dict[str, Any]]:
    category = str(category or "").strip()
    meta = visual_loadout_slot_meta(slot) or VISUAL_LOADOUT_SLOTS[0]
    is_cargo_slot = str(meta.get("key", "")).startswith("cargo:")
    if category:
        if not is_cargo_slot:
            picker = str(meta.get("picker") or "Head")
            slot_items = groups.get(picker) if isinstance(groups.get(picker), list) else []
            if category == "Weapons":
                candidates = slot_items if picker in {"Hands", "Left Shoulder", "Right Shoulder"} else []
            elif category == "Clothing":
                candidates = slot_items
            else:
                candidates = [
                    item for item in slot_items
                    if category.lower() in str(item.get("category") or "").lower()
                    or category.lower().split("/")[0] in str(item.get("name") or "").lower()
                ]
        else:
            all_items = groups.get("player_cargo") if isinstance(groups.get("player_cargo"), list) else groups.get("all")
            all_items = all_items if isinstance(all_items, list) else []
            candidates = [
                item for item in all_items
                if category.lower() in str(item.get("category") or "").lower()
                or category.lower().split("/")[0] in str(item.get("name") or "").lower()
            ]
        return unique_visual_items(candidates, None if is_cargo_slot else 120)
    if str(meta.get("key", "")).startswith("cargo:"):
        return unique_visual_items(groups.get("player_cargo") or groups.get("cargo", []), None)
    return unique_visual_items(groups.get(str(meta.get("picker") or "Head"), []))


def unique_visual_items(items: list[dict[str, Any]], limit: int | None = 120) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("classname") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        row = dict(item)
        row.setdefault("label", name)
        row.setdefault("category", "General")
        row.setdefault("image_url", item_image_url(name))
        row.setdefault("fallback_image_url", f"/item-thumb/{urllib.parse.quote(str(row.get('category') or 'General'))}")
        row["capacity"] = visual_item_capacity(name)
        row["size"] = visual_item_size(name)
        rows.append(row)
    rows = sorted(rows, key=lambda item: str(item.get("name") or "").lower())
    return rows if limit is None else rows[:limit]


def visual_item_capacity(item_name: Any) -> int:
    text = str(item_name or "").lower()
    for term, capacity in VISUAL_LOADOUT_CAPACITY_HINTS.items():
        if term in text:
            return capacity
    return 0


def visual_item_size(item_name: Any) -> int:
    text = str(item_name or "").lower()
    for term, size in VISUAL_LOADOUT_SIZE_HINTS.items():
        if term in text:
            return size
    return 1


def visual_item_detail(item_name: Any, groups: dict[str, Any]) -> dict[str, Any]:
    name = safe_dayz_class(item_name)
    if not name:
        return {}
    all_items = groups.get("all") if isinstance(groups.get("all"), list) else []
    match = next((item for item in all_items if str(item.get("name") or "").lower() == name.lower()), None)
    detail = dict(match) if isinstance(match, dict) else {"name": name, "label": name, "category": "General"}
    detail.setdefault("name", name)
    detail.setdefault("label", name)
    detail.setdefault("category", "General")
    detail.setdefault("image_url", item_image_url(name))
    detail.setdefault("fallback_image_url", f"/item-thumb/{urllib.parse.quote(str(detail.get('category') or 'General'))}")
    detail["capacity"] = visual_item_capacity(name)
    detail["size"] = visual_item_size(name)
    return detail


def visual_items_matching(groups: dict[str, Any], names: list[str], fallback_category: str) -> list[dict[str, Any]]:
    all_items = groups.get("all") if isinstance(groups.get("all"), list) else []
    rows: list[dict[str, Any]] = []
    for name in names:
        match = next((item for item in all_items if str(item.get("name") or "").lower() == name.lower()), None)
        if isinstance(match, dict):
            rows.append(match)
        else:
            rows.append({
                "name": name,
                "label": name,
                "category": fallback_category,
                "image_url": item_image_url(name),
                "fallback_image_url": f"/item-thumb/{urllib.parse.quote(fallback_category)}",
            })
    return unique_visual_items(rows)


def visual_compatible_child_slots(item_name: Any, groups: dict[str, Any]) -> list[dict[str, Any]]:
    name = safe_dayz_class(item_name)
    text = name.lower()
    if not name:
        return []
    slots: list[dict[str, Any]] = []

    def add(slot_key: str, label: str, choices: list[str], category: str, mode: str = "single") -> None:
        rows = visual_items_matching(groups, choices, category)
        if rows:
            slots.append({"key": slot_key, "label": label, "mode": mode, "items": rows})

    def add_player_cargo(slot_key: str, label: str, mode: str = "multi") -> None:
        rows = unique_visual_items(groups.get("player_cargo") or groups.get("cargo", []), None)
        if rows:
            slots.append({"key": slot_key, "label": label, "mode": mode, "items": rows})

    if any(term in text for term in ("helmet", "ballistichelmet", "tacticalhelmet", "combathelmet", "mich")):
        add("nvg", "NVG / head attachment", ["NVGoggles", "NVGHeadstrap", "UniversalLight"], "Attachments")
        add("battery", "Battery", ["Battery9V"], "Attachments")
    if "nvg" in text:
        add("battery", "Battery", ["Battery9V"], "Attachments")
    if "platecarrier" in text:
        add("pouches", "Pouches", ["PlateCarrierPouches"], "Attachments")
        add("holster", "Holster", ["PlateCarrierHolster"], "Attachments")
        add("grenades", "Grenades", ["M67Grenade", "RGD5Grenade", "FlashGrenade", "M18SmokeGrenade_Red", "M18SmokeGrenade_Green"], "Explosives", "multi")
    if "belt" in text or "holster" in text:
        add("canteen", "Canteen", ["Canteen"], "Containers")
        add("sheath", "Knife / sheath", ["CombatKnife", "HuntingKnife", "KitchenKnife", "StoneKnife"], "Tools")
        add("holster", "Pistol / holster", ["MakarovIJ70", "FNX45", "Glock19", "Deagle", "CZ75", "Colt1911"], "Weapons")
    if any(term in text for term in ("m4a1", "akm", "ak74", "ak101", "sks", "mosin", "svd", "fal", "vss", "aug", "pistol", "fnx", "glock", "deagle", "cz75", "1911")):
        if "m4a1" in text:
            add("magazine", "Magazine", ["Mag_STANAG_30Rnd", "Mag_STANAGCoupled_30Rnd", "Mag_CMAG_40Rnd"], "Ammunition")
            add("optic", "Optic", ["ACOGOptic", "M68Optic", "M4_T3NRDSOptic", "ReflexOptic", "BUISOptic"], "Attachments")
            add("handguard", "Handguard", ["M4_RISHndgrd", "M4_MPHndgrd", "M4_PlasticHndgrd"], "Attachments")
            add("buttstock", "Buttstock", ["M4_OEBttstck", "M4_MPBttstck", "M4_CQBBttstck"], "Attachments")
            add("muzzle", "Suppressor", ["M4_Suppressor"], "Attachments")
            add("ammo", "Ammo", ["AmmoBox_556x45_20Rnd", "Ammo_556x45"], "Ammunition")
        elif "akm" in text:
            add("magazine", "Magazine", ["Mag_AKM_30Rnd", "Mag_AKM_Drum75Rnd"], "Ammunition")
            add("optic", "Optic", ["KobraOptic", "PSO1Optic", "PistolOptic"], "Attachments")
            add("muzzle", "Suppressor", ["AK_Suppressor"], "Attachments")
            add("ammo", "Ammo", ["AmmoBox_762x39_20Rnd", "Ammo_762x39"], "Ammunition")
        elif "ak74" in text or "ak101" in text:
            mag = "Mag_AK101_30Rnd" if "ak101" in text else "Mag_AK74_30Rnd"
            ammo_box = "AmmoBox_556x45_20Rnd" if "ak101" in text else "AmmoBox_545x39_20Rnd"
            ammo_loose = "Ammo_556x45" if "ak101" in text else "Ammo_545x39"
            add("magazine", "Magazine", [mag], "Ammunition")
            add("optic", "Optic", ["KobraOptic", "PSO1Optic"], "Attachments")
            add("muzzle", "Suppressor", ["AK_Suppressor"], "Attachments")
            add("ammo", "Ammo", [ammo_box, ammo_loose], "Ammunition")
        elif "svd" in text:
            add("magazine", "Magazine", ["Mag_SVD_10Rnd"], "Ammunition")
            add("optic", "Optic", ["PSO1Optic"], "Attachments")
            add("ammo", "Ammo", ["AmmoBox_762x54_20Rnd", "Ammo_762x54"], "Ammunition")
        elif "sks" in text or "mosin" in text:
            add("optic", "Optic", ["PUScope", "HuntingOptic"], "Attachments")
            add("ammo", "Ammo", ["AmmoBox_762x39_20Rnd", "Ammo_762x39", "AmmoBox_762x54_20Rnd", "Ammo_762x54"], "Ammunition")
        else:
            add("magazine", "Magazine", ["Mag_FNX45_15Rnd", "Mag_Glock_15Rnd", "Mag_CZ75_15Rnd", "Mag_1911_7Rnd"], "Ammunition")
            add("ammo", "Ammo", ["AmmoBox_45ACP_25rnd", "AmmoBox_9x19_25rnd", "Ammo_45ACP", "Ammo_9x19"], "Ammunition")
    capacity = visual_item_capacity(name)
    if capacity > 0:
        add_player_cargo("cargo", f"Cargo ({capacity} slot estimate)")
    return slots


def visual_loadout_selected_rows(draft_value: Any, groups: dict[str, Any]) -> list[dict[str, Any]]:
    draft = normalize_visual_loadout_draft(draft_value)
    rows: list[dict[str, Any]] = []
    for slot in VISUAL_LOADOUT_SLOTS:
        item_name = draft["attachments"].get(slot["key"]) if slot["group"] == "attachments" else draft["cloth"].get(slot["key"])
        if not item_name:
            continue
        detail = visual_item_detail(item_name, groups)
        children = draft["children"].get(slot["key"], {})
        child_slots = visual_compatible_child_slots(item_name, groups)
        for child_slot in child_slots:
            selected_child = children.get(child_slot.get("key"))
            if isinstance(selected_child, list):
                child_slot["current_values"] = selected_child
            elif isinstance(selected_child, str) and selected_child:
                child_slot["current_values"] = [selected_child]
            else:
                child_slot["current_values"] = []
            if isinstance(selected_child, str) and selected_child:
                child_slot["selected"] = selected_child
                child_slot["selected_detail"] = visual_item_detail(selected_child, groups)
                child_slot["nested_slots"] = visual_compatible_child_slots(selected_child, groups)
                child_slot["nested_children"] = children.get(f"{child_slot.get('key')}:children", {})
                for nested_slot in child_slot["nested_slots"]:
                    nested_value = child_slot["nested_children"].get(nested_slot.get("key")) if isinstance(child_slot["nested_children"], dict) else None
                    if isinstance(nested_value, list):
                        nested_slot["current_values"] = nested_value
                    elif isinstance(nested_value, str) and nested_value:
                        nested_slot["current_values"] = [nested_value]
                    else:
                        nested_slot["current_values"] = []
        rows.append({
            "slot": slot,
            "item": detail,
            "children": children,
            "child_slots": child_slots,
        })
    return rows


def visual_loadout_slot_cards(draft_value: Any, groups: dict[str, Any]) -> list[dict[str, Any]]:
    draft = normalize_visual_loadout_draft(draft_value)
    cards: list[dict[str, Any]] = []
    for slot in VISUAL_LOADOUT_SLOTS:
        item_name = draft["attachments"].get(slot["key"]) if slot["group"] == "attachments" else draft["cloth"].get(slot["key"])
        cards.append({
            "slot": slot,
            "item": visual_item_detail(item_name, groups) if item_name else {},
        })
    return cards


def build_spawnable_cargo_xml(type_name: str, items: list[dict[str, Any]]) -> str:
    safe_type = safe_dayz_class(type_name) or "Classname"
    lines = [f'<type name="{safe_type}">']
    for item in items:
        if not isinstance(item, dict):
            continue
        item_name = safe_dayz_class(item.get("item"))
        if not item_name:
            continue
        lines.append('    <cargo chance="1.00">')
        lines.append(f'        <item name="{item_name}" chance="1.00" />')
        lines.append('    </cargo>')
    lines.append("</type>")
    return "\n".join(lines)


def build_airdrop_xml_package(record: dict[str, Any]) -> dict[str, str]:
    event_name = safe_dayz_class(record.get("event_name")) or "Static_WanderingAirdrop"
    container_class = safe_dayz_class(record.get("container_class")) or "StaticObj_Misc_WoodenCrate_5x"
    positions = record.get("positions")
    if not isinstance(positions, list) or not positions:
        positions = [{"x": "10869", "z": "10937"}]
    items = record.get("items") if isinstance(record.get("items"), list) else []
    nominal = max(1, safe_int(record.get("nominal"), 1))
    min_count = max(1, safe_int(record.get("min_count"), 1))
    max_count = max(min_count, safe_int(record.get("max_count"), 1))
    secondary_event = safe_dayz_class(record.get("secondary_event"))
    events_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        "<events>",
        f'    <event name="{xml_attr(event_name)}">',
        f'        <nominal>{nominal}</nominal>',
        f'        <min>{min_count}</min>',
        f'        <max>{max_count}</max>',
        f'        <lifetime>{max(1, safe_int(record.get("lifetime"), 1800))}</lifetime>',
        f'        <restock>{max(0, safe_int(record.get("restock"), 3600))}</restock>',
        f'        <saferadius>{max(0, safe_int(record.get("saferadius"), 0))}</saferadius>',
        f'        <distanceradius>{max(0, safe_int(record.get("distanceradius"), 1000))}</distanceradius>',
        f'        <cleanupradius>{max(0, safe_int(record.get("cleanupradius"), 1500))}</cleanupradius>',
    ]
    if secondary_event:
        events_lines.append(f"        <secondary>{xml_attr(secondary_event)}</secondary>")
    events_lines.extend([
        '        <flags deletable="1" init_random="0" remove_damaged="0" />',
        "        <position>fixed</position>",
        "        <limit>child</limit>",
        "        <active>1</active>",
        "        <children>",
        f'            <child lootmax="0" lootmin="0" max="1" min="1" type="{xml_attr(container_class)}" />',
        "        </children>",
        "    </event>",
        "</events>",
    ])
    events = "\n".join(events_lines)
    spawn_radius = max(1, safe_int(record.get("spawn_radius"), 20))
    spawns = "\n".join([
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        "<eventposdef>",
        f'    <event name="{xml_attr(event_name)}">',
        f'        <zone smin="1" smax="1" dmin="1" dmax="1" r="{spawn_radius}" />',
        *[f'        <pos x="{xml_attr(pos.get("x"))}" z="{xml_attr(pos.get("z"))}" a="0" y="0" />' for pos in positions if isinstance(pos, dict)],
        "    </event>",
        "</eventposdef>",
    ])
    spawnable_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        "<spawnabletypes>",
        f'    <type name="{xml_attr(container_class)}">',
    ]
    for item in items:
        if not isinstance(item, dict):
            continue
        item_name = safe_dayz_class(item.get("item"))
        if not item_name:
            continue
        spawnable_lines.extend([
            '        <cargo chance="1.00">',
            f'            <item name="{xml_attr(item_name)}" chance="1.00" />',
            "        </cargo>",
        ])
    spawnable_lines.extend(["    </type>", "</spawnabletypes>"])
    return {"events": events, "spawns": spawns, "spawnable": "\n".join(spawnable_lines)}


def xml_workshop_summary(config: dict[str, Any]) -> dict[str, Any]:
    workshop = config.get("xml_workshop")
    if not isinstance(workshop, dict):
        workshop = {}
    recipes = workshop.get("recipes") if isinstance(workshop.get("recipes"), dict) else {}
    return {
        "settings": workshop.get("settings") if isinstance(workshop.get("settings"), dict) else {},
        "airdrop_recipes": recipes.get("airdrops") if isinstance(recipes.get("airdrops"), list) else [],
        "container_recipes": recipes.get("containers") if isinstance(recipes.get("containers"), list) else [],
        "player_loadouts": recipes.get("players") if isinstance(recipes.get("players"), list) else [],
        "vehicle_loadouts": recipes.get("vehicles") if isinstance(recipes.get("vehicles"), list) else [],
        "updated_at": str(workshop.get("updated_at") or ""),
        "status": str(workshop.get("status") or "Draft recipes only; no live XML upload has run."),
    }


def parse_zombie_mix(value: Any) -> list[dict[str, Any]]:
    rows = []
    for raw in re.split(r"[\n,;]+", str(value or "")):
        text = raw.strip()
        if not text:
            continue
        match = re.match(r"^(?:(\d+)\s*[xX]?\s+)?([A-Za-z0-9_]+)(?:\s*[xX]\s*(\d+))?$", text)
        if not match:
            continue
        count = safe_int(match.group(1) or match.group(3), 1)
        class_name = str(match.group(2) or "").strip()
        if class_name.startswith(("ZmbM_", "ZmbF_")):
            rows.append({"class": class_name, "count": max(1, min(250, count))})
    total = 0
    capped = []
    for row in rows:
        if total >= 250:
            break
        count = min(int(row["count"]), 250 - total)
        capped.append({"class": row["class"], "count": count})
        total += count
    return capped


def local_dashboard_time() -> str:
    return datetime.now(DASHBOARD_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S UK")


def local_dashboard_clock() -> str:
    return datetime.now(DASHBOARD_TIMEZONE).strftime("%H:%M")


def discord_guild_channels(guild_id: str) -> list[dict[str, str]]:
    if not DISCORD_TOKEN or not guild_id:
        return []
    now = datetime.now(UTC)
    cached = DISCORD_CHANNEL_CACHE.get(str(guild_id))
    if cached and (now - cached[0]).total_seconds() < DISCORD_CHANNEL_CACHE_SECONDS:
        return cached[1]
    request = urllib.request.Request(
        f"https://discord.com/api/v10/guilds/{guild_id}/channels",
        headers={"Authorization": f"Bot {DISCORD_TOKEN}", "User-Agent": "WanderingBotDashboard/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    channels = []
    allowed_types = {0, 5, 10, 11, 12, 15}
    for item in payload:
        if not isinstance(item, dict) or item.get("type") not in allowed_types:
            continue
        channel_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not channel_id or not name:
            continue
        channels.append(
            {
                "id": channel_id,
                "name": name,
                "key": "",
                "value": channel_id,
                "label": f"#{name}",
                "position": safe_int(item.get("position"), 0),
            }
        )
    channels.sort(key=lambda channel: (safe_int(channel.get("position"), 0), channel["name"].lower()))
    DISCORD_CHANNEL_CACHE[str(guild_id)] = (now, channels)
    return channels


def discord_guild_roles(guild_id: str) -> list[dict[str, str]]:
    if not DISCORD_TOKEN or not guild_id:
        return []
    now = datetime.now(UTC)
    cached = DISCORD_ROLE_CACHE.get(str(guild_id))
    if cached and (now - cached[0]).total_seconds() < DISCORD_CHANNEL_CACHE_SECONDS:
        return cached[1]
    request = urllib.request.Request(
        f"https://discord.com/api/v10/guilds/{guild_id}/roles",
        headers={"Authorization": f"Bot {DISCORD_TOKEN}", "User-Agent": "WanderingBotDashboard/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    roles = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        role_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not role_id or not name or name == "@everyone":
            continue
        roles.append(
            {
                "id": role_id,
                "name": name,
                "value": role_id,
                "label": f"@{name}",
                "position": safe_int(item.get("position"), 0),
            }
        )
    roles.sort(key=lambda role: (-safe_int(role.get("position"), 0), role["name"].lower()))
    DISCORD_ROLE_CACHE[str(guild_id)] = (now, roles)
    return roles


def discord_guild_members(guild_id: str, limit: int = 1000) -> list[dict[str, str]]:
    if not DISCORD_TOKEN or not guild_id:
        return []
    now = datetime.now(UTC)
    cached = DISCORD_MEMBER_CACHE.get(str(guild_id))
    if cached and (now - cached[0]).total_seconds() < DISCORD_CHANNEL_CACHE_SECONDS:
        return cached[1]
    request = urllib.request.Request(
        f"https://discord.com/api/v10/guilds/{guild_id}/members?limit={max(1, min(1000, int(limit or 1000)))}",
        headers={"Authorization": f"Bot {DISCORD_TOKEN}", "User-Agent": "WanderingBotDashboard/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    members = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        user_id = str(user.get("id") or "").strip()
        username = str(user.get("global_name") or user.get("username") or "").strip()
        nick = str(item.get("nick") or "").strip()
        label_name = nick or username or user_id
        if not user_id or not label_name:
            continue
        members.append(
            {
                "id": user_id,
                "name": label_name,
                "username": username,
                "nick": nick,
                "value": user_id,
                "label": f"{label_name} ({user_id})",
            }
        )
    members.sort(key=lambda member: member["name"].lower())
    DISCORD_MEMBER_CACHE[str(guild_id)] = (now, members)
    return members


def runtime_discord_member_count(guild_id: str, guild_counts: Any) -> int | None:
    if not isinstance(guild_counts, dict):
        return None
    target = normalize_guild_id(guild_id)
    raw = guild_counts.get(target)
    if raw is None:
        for key, value in guild_counts.items():
            if normalize_guild_id(key) == target:
                raw = value
                break
    if raw is None:
        return None
    if isinstance(raw, dict):
        for key in ("member_count", "approximate_member_count", "count", "members", "total"):
            if key in raw:
                value = safe_int(raw.get(key), -1)
                return value if value >= 0 else None
        return None
    value = safe_int(raw, -1)
    return value if value >= 0 else None


def discord_guild_member_count(guild_id: str) -> int | None:
    if not DISCORD_TOKEN or not guild_id:
        return None
    guild_id = normalize_guild_id(guild_id)
    now = datetime.now(UTC)
    cached = DISCORD_GUILD_COUNT_CACHE.get(guild_id)
    if cached and (now - cached[0]).total_seconds() < DISCORD_CHANNEL_CACHE_SECONDS:
        return cached[1]
    request = urllib.request.Request(
        f"https://discord.com/api/v10/guilds/{guild_id}?with_counts=true",
        headers={"Authorization": f"Bot {DISCORD_TOKEN}", "User-Agent": "WanderingBotDashboard/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("approximate_member_count", "member_count"):
        count = safe_int(payload.get(key), -1)
        if count >= 0:
            DISCORD_GUILD_COUNT_CACHE[guild_id] = (now, count)
            return count
    return None


def discord_member_action(guild_id: str, member_id: str, action: str, reason: str) -> tuple[bool, str]:
    if not DISCORD_TOKEN:
        return False, "DISCORD_TOKEN is not configured for dashboard member actions."
    guild_id = str(guild_id or "").strip()
    member_id = str(member_id or "").strip()
    if not guild_id or not member_id:
        return False, "guild_id and member_id are required."
    if action == "discord_kick":
        url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{member_id}"
        method = "DELETE"
    elif action == "discord_ban":
        url = f"https://discord.com/api/v10/guilds/{guild_id}/bans/{member_id}?delete_message_seconds=0"
        method = "PUT"
    else:
        return False, "unsupported Discord member action."
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "User-Agent": "WanderingBotDashboard/1.0",
        "X-Audit-Log-Reason": urllib.parse.quote(str(reason or "Wandering Bot dashboard action")[:512]),
    }
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if 200 <= response.status < 300:
                return True, "Discord action completed."
            return False, f"Discord returned HTTP {response.status}."
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = error.read().decode("utf-8")[:250]
        except Exception:
            detail = ""
        return False, f"Discord returned HTTP {error.code}. {detail}".strip()
    except (OSError, urllib.error.URLError) as error:
        return False, f"Discord request failed: {error}"


def public_channels(channels: Any, guild_id: str = "") -> list[dict[str, str]]:
    if not isinstance(channels, dict):
        channels = {}
    live_channels = discord_guild_channels(str(guild_id)) if guild_id else []
    live_by_id = {str(channel["id"]): channel for channel in live_channels}
    rows = []
    seen_ids = set()
    for key, value in sorted(channels.items(), key=lambda item: str(item[0]).lower()):
        channel_id = str(value).strip()
        if not channel_id:
            continue
        live = live_by_id.get(channel_id, {})
        name = str(live.get("name") or key).strip()
        display_label = f"#{name}" if name == str(key) else f"#{name} ({key})"
        rows.append(
            {
                "key": str(key),
                "id": channel_id,
                "name": name,
                "value": str(key),
                "label": f"#{name} ({key})" if live else f"{key} · {channel_id}",
                "configured": "true",
            }
        )
        rows[-1]["label"] = display_label
        seen_ids.add(channel_id)
    for live in live_channels:
        channel_id = str(live.get("id") or "")
        if channel_id in seen_ids:
            continue
        rows.append(
            {
                "key": "",
                "id": channel_id,
                "name": str(live.get("name") or ""),
                "value": channel_id,
                "label": f"#{live.get('name')}",
                "configured": "false",
            }
        )
    return rows


def channel_label_from_channels(channels: Any, value: Any, default: str = "no channel") -> str:
    selection = str(value or "").strip()
    if not selection:
        return default
    if not isinstance(channels, list):
        channels = []
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        candidates = {
            str(channel.get("id") or ""),
            str(channel.get("key") or ""),
            str(channel.get("value") or ""),
            str(channel.get("name") or ""),
            str(channel.get("label") or ""),
        }
        if selection in candidates:
            label = str(channel.get("label") or "").strip()
            if label:
                return label
            name = str(channel.get("name") or channel.get("key") or "").strip()
            return f"#{name}" if name else default
    if selection.isdigit():
        return "Unknown channel"
    return selection if selection.startswith("#") else f"#{selection}"


def enrich_faction_channel_labels(factions: dict[str, Any], channels: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(factions, dict):
        return {}
    enriched = {}
    for name, faction in factions.items():
        record = dict(faction) if isinstance(faction, dict) else {}
        record["alert_channel_label"] = channel_label_from_channels(channels, record.get("alert_channel_key") or record.get("alert_channel_id"), "-")
        enriched[str(name)] = record
    return enriched


def resolve_channel_selection(config: dict[str, Any], value: Any) -> tuple[str, str]:
    selection = str(value or "").strip()
    channels = config.get("channels", {}) if isinstance(config.get("channels"), dict) else {}
    if selection in channels:
        return selection, str(channels.get(selection) or "")
    if selection.isdigit():
        for key, channel_id in channels.items():
            if str(channel_id) == selection:
                return str(key), selection
        return "", selection
    return selection, str(channels.get(selection) or "")


def discord_bot_leave_guild(guild_id: str) -> tuple[bool, str]:
    if not DISCORD_TOKEN:
        return False, "DISCORD_TOKEN is not configured, so the dashboard cannot make the bot leave Discord guilds."

    request_obj = urllib.request.Request(
        f"https://discord.com/api/v10/users/@me/guilds/{guild_id}",
        method="DELETE",
        headers={
            "Authorization": f"Bot {DISCORD_TOKEN}",
            "User-Agent": "WanderingBotDashboard/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=20) as response:
            if response.status in {200, 202, 204}:
                return True, f"Bot leave requested for guild {guild_id}."
            return False, f"Discord returned status {response.status}."
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return True, f"Bot is already not in guild {guild_id}."
        body = error.read().decode("utf-8", errors="ignore")[:240]
        return False, f"Discord leave failed ({error.code}): {body}"
    except Exception as error:
        return False, f"Discord leave failed: {error}"


def remove_guild_dashboard_data(guild_id: str, config: dict[str, Any]) -> None:
    removed = load_store("removed_guilds", [])
    if not isinstance(removed, list):
        removed = []
    removed.append({
        "guild_id": guild_id,
        "guild_name": str(config.get("guild_name") or ""),
        "removed_at": datetime.now(UTC).isoformat(),
        "config": redact(config),
    })
    save_store("removed_guilds", removed[-100:])

    for store_name in [
        "guild_configs",
        "player_stats",
        "online_players",
        "factions",
        "wages",
        "shop",
        "heatmap",
        "pve_challenges",
        "pve_ai_campaigns",
        "pve_workshop_schedules",
        "swear_jar",
        "longshot_records",
    ]:
        store = load_store(store_name, {})
        if isinstance(store, dict) and guild_id in store:
            store.pop(guild_id, None)
            save_store(store_name, store)

    wallets = load_store("wallets", {})
    if isinstance(wallets, dict):
        wallets = {
            key: value for key, value in wallets.items()
            if str(key) != guild_id and not str(key).startswith(f"{guild_id}:")
        }
        save_store("wallets", wallets)

    delivery_queue = load_store("delivery_queue", [])
    if isinstance(delivery_queue, list):
        delivery_queue = [
            item for item in delivery_queue
            if not (isinstance(item, dict) and str(item.get("guild_id") or "") == guild_id)
        ]
        save_store("delivery_queue", delivery_queue)


def is_shop_sellable_item(item_name: Any, category: Any = "") -> bool:
    name = str(item_name or "").strip()
    lower = name.lower()
    category_lower = str(category or "").lower()
    if not name:
        return False
    blocked_prefixes = (
        "animal_",
        "zmb",
        "land_wreck",
        "land_wreck_",
        "land_misc_wreck",
        "wreck_",
        "static_",
    )
    blocked_fragments = (
        "wreck",
        "doors_",
        "door_",
        "hood_",
        "trunk_",
        "wheel_ruined",
        "zombie",
        "infected",
    )
    vehicle_classes = (
        "civilian",
        "civsedan",
        "hatchback",
        "offroadhatchback",
        "sedan",
        "truck",
        "bus",
        "ada",
        "olga",
        "sarka",
        "gunter",
        "humvee",
        "boat",
    )
    if lower.startswith(blocked_prefixes):
        return False
    if any(fragment in lower for fragment in blocked_fragments):
        return False
    if category_lower in {"vehicles", "vehicle", "animals", "infected", "zombies"}:
        return False
    if any(lower.startswith(vehicle) for vehicle in vehicle_classes):
        return False
    return True


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if any(secret_key in str(key).lower() for secret_key in SECRET_KEYS):
                cleaned[key] = "***"
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def guild_players(player_stats: Any, guild_id: str) -> list[dict[str, Any]]:
    players = []
    if not isinstance(player_stats, dict):
        return players
    for name, stats in player_stats.items():
        if not isinstance(stats, dict):
            continue
        stat_guild_id = str(stats.get("guild_id") or "")
        if stat_guild_id and stat_guild_id != guild_id:
            continue
        players.append(
            {
                "name": str(name),
                "discord_id": str(stats.get("discord_id") or stats.get("user_id") or stats.get("member_id") or ""),
                "discord_name": str(stats.get("discord_name") or stats.get("display_name") or stats.get("username") or stats.get("member_name") or ""),
                "gamertag": str(stats.get("gamertag") or stats.get("player_name") or name),
                "kills": safe_int(stats.get("kills")),
                "deaths": safe_int(stats.get("deaths")),
                "builds": safe_int(stats.get("builds")),
                "time_online_seconds": safe_int(stats.get("time_online_seconds")),
                "multikill_best": safe_int(stats.get("multikill_best")),
                "kill_streak": safe_int(stats.get("best_spree") or stats.get("kill_streak")),
                "longest_shot_distance": safe_int(stats.get("longest_shot_distance")),
                "flags_raised": safe_int(stats.get("flags_raised")),
                "animal_deaths": safe_int(stats.get("animal_deaths")),
                "zombie_deaths": safe_int(stats.get("zombie_deaths")),
            }
        )
    return sorted(players, key=lambda item: (-item["kills"], item["deaths"], item["name"].lower()))


def faction_name_for_member(factions: dict[str, Any], player_name: str, discord_id: str = "") -> str:
    player_key = str(player_name or "").strip().lower()
    discord_key = str(discord_id or "").strip()
    for faction_name, faction in factions.items():
        if not isinstance(faction, dict):
            continue
        for member in faction.get("members", []) if isinstance(faction.get("members", []), list) else []:
            if isinstance(member, dict):
                member_id = str(member.get("user_id") or member.get("discord_id") or member.get("id") or "").strip()
                member_name = str(member.get("name") or member.get("gamertag") or "").strip().lower()
            else:
                member_id = str(member).strip()
                member_name = str(member).strip().lower()
            if discord_key and member_id == discord_key:
                return str(faction.get("name") or faction_name)
            if player_key and member_name == player_key:
                return str(faction.get("name") or faction_name)
    return ""


def member_records_for_guild(players: list[dict[str, Any]], online: list[str], factions: dict[str, Any]) -> list[dict[str, Any]]:
    online_names = {str(name).strip().lower() for name in online}
    members = []
    for player in players:
        name = str(player.get("name") or player.get("gamertag") or "").strip()
        if not name:
            continue
        discord_id = str(player.get("discord_id") or "").strip()
        discord_name = str(player.get("discord_name") or "").strip()
        members.append(
            {
                "name": name,
                "discord_id": discord_id,
                "discord_name": discord_name,
                "faction": faction_name_for_member(factions, name, discord_id),
                "online": name.lower() in online_names,
                "kills": safe_int(player.get("kills")),
                "deaths": safe_int(player.get("deaths")),
                "time_online_seconds": safe_int(player.get("time_online_seconds")),
            }
        )
    members.sort(key=lambda item: (not item["online"], item["name"].lower()))
    return members


def format_seconds(seconds: Any) -> str:
    total = safe_int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def medal_class(index: int) -> str:
    return {1: "gold", 2: "silver", 3: "bronze"}.get(index, "")


def player_display_name(player: Any, fallback: str = "Unknown survivor") -> str:
    if not isinstance(player, dict):
        return fallback
    for key in ("name", "gamertag", "discord_name", "player_name", "username", "discord_id"):
        value = str(player.get(key) or "").strip()
        if value:
            return value
    return fallback


def stat_board(title: str, players: list[dict[str, Any]], key: str, suffix: str, limit: int = 10) -> dict[str, Any]:
    rows = [player for player in players if safe_int(player.get(key)) > 0]
    rows.sort(key=lambda item: (-safe_int(item.get(key)), player_display_name(item).lower()))
    return {
        "title": title,
        "rows": [
            {"name": player_display_name(row), "value": f"{safe_int(row.get(key))} {suffix}".strip(), "medal": medal_class(index)}
            for index, row in enumerate(rows[:limit], start=1)
        ],
    }


def time_board(players: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [player for player in players if safe_int(player.get("time_online_seconds")) > 0]
    rows.sort(key=lambda item: (-safe_int(item.get("time_online_seconds")), player_display_name(item).lower()))
    return {
        "title": "⏱️ Most Time Played",
        "rows": [
            {"name": player_display_name(row), "value": format_seconds(row.get("time_online_seconds")), "medal": medal_class(index)}
            for index, row in enumerate(rows[:10], start=1)
        ],
    }


def longshot_board(players: list[dict[str, Any]], longshot_records: Any, guild_id: str) -> dict[str, Any]:
    best: dict[str, int] = {}
    for player in players:
        distance = safe_int(player.get("longest_shot_distance"))
        if distance > 0:
            name = player_display_name(player)
            best[name] = max(best.get(name, 0), distance)
    records = guild_block(longshot_records, guild_id, [])
    for record in list_records(records):
        if not isinstance(record, dict):
            continue
        name = str(record.get("killer") or record.get("player") or "Unknown")
        distance = safe_int(record.get("distance") or record.get("meters"))
        if distance > 0:
            best[name] = max(best.get(name, 0), distance)
    rows = sorted(best.items(), key=lambda item: (-item[1], item[0].lower()))[:10]
    return {
        "title": "🎯 Longest Shot",
        "rows": [
            {"name": name, "value": f"{distance}m", "medal": medal_class(index)}
            for index, (name, distance) in enumerate(rows, start=1)
        ],
    }


def swear_board(swear_jar: Any, players: list[dict[str, Any]]) -> dict[str, Any]:
    known_names = {str(player.get("discord_id", "")): player_display_name(player) for player in players if player.get("discord_id")}
    rows = []
    if isinstance(swear_jar, dict):
        for key, entry in swear_jar.items():
            if isinstance(entry, dict):
                count = safe_int(entry.get("count") or entry.get("swears") or entry.get("total"))
                name = str(entry.get("name") or known_names.get(str(key)) or key)
            else:
                count = safe_int(entry)
                name = str(known_names.get(str(key)) or key)
            if count > 0:
                rows.append({"name": name, "count": count})
    rows.sort(key=lambda item: (-item["count"], item["name"].lower()))
    return {
        "title": "🤬 Most Swearing",
        "rows": [
            {"name": row["name"], "value": f"{row['count']} swears", "medal": medal_class(index)}
            for index, row in enumerate(rows[:10], start=1)
        ],
    }


def leaderboard_categories(players: list[dict[str, Any]], swear_jar: Any, longshot_records: Any, guild_id: str) -> list[dict[str, Any]]:
    return [
        stat_board("☠️ Most Kills", players, "kills", "kills"),
        stat_board("💀 Most Deaths", players, "deaths", "deaths"),
        time_board(players),
        stat_board("🔨 Most Built", players, "builds", "parts"),
        stat_board("🔫 Highest Kill Streak", players, "kill_streak", "kills w/o dying"),
        longshot_board(players, longshot_records, guild_id),
        swear_board(swear_jar, players),
        stat_board("🚩 Most Flags Raised", players, "flags_raised", "flags"),
        stat_board("🐺 Most Deaths By Animal", players, "animal_deaths", "deaths"),
        stat_board("🧟 Most Deaths By Zombies", players, "zombie_deaths", "deaths"),
    ]


def dashboard_access(config: dict[str, Any]) -> dict[str, Any]:
    access = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    features = access.get("features") if isinstance(access.get("features"), dict) else {}
    plan_status = str(access.get("plan_status") or access.get("tier") or "none").lower()
    if plan_status not in {"trial", "subscription", "lifetime", "suspended", "none"}:
        plan_status = "none"
    return {
        "enabled": bool(access.get("enabled", False)),
        "tier": str(access.get("tier") or "none"),
        "plan_status": plan_status,
        "trial_ends_at": str(access.get("trial_ends_at") or ""),
        "subscription_ends_at": str(access.get("subscription_ends_at") or ""),
        "trial_notice_enabled": safe_bool(access.get("trial_notice_enabled"), True),
        "owner_note": str(access.get("owner_note") or ""),
        "owner_admin_visible": safe_bool(access.get("owner_admin_visible"), False),
        "allowed_role_ids": [str(item) for item in access.get("allowed_role_ids", []) if item],
        "allowed_user_ids": [str(item) for item in access.get("allowed_user_ids", []) if item],
        "features": {
            "economy": bool(features.get("economy", False)),
            "embeds": bool(features.get("embeds", False)),
            "factions": bool(features.get("factions", False)),
            "heatmaps": bool(features.get("heatmaps", False)),
            "leaderboards": bool(features.get("leaderboards", True)),
            "members": bool(features.get("members", False)),
            "pve_quests": bool(features.get("pve_quests", False)),
            "quest_workshop": bool(features.get("quest_workshop", False)),
            "safe_zones": bool(features.get("safe_zones", False)),
            "server_rules": bool(features.get("server_rules", False)),
            "server_control": bool(features.get("server_control", False)),
            "shop": bool(features.get("shop", False)),
            "wages": bool(features.get("wages", False)),
            "xml_workshop": bool(features.get("xml_workshop", False)),
        },
    }


def count_records(value: Any) -> int:
    if isinstance(value, (dict, list)):
        return len(value)
    return 0


def guild_block(data: Any, guild_id: str, default: Any) -> Any:
    if isinstance(data, dict):
        return data.get(guild_id, default)
    return default


def wage_cadence_seconds(cadence: Any) -> int:
    return {
        "daily": 24 * 3600,
        "weekly": 7 * 24 * 3600,
        "monthly": 30 * 24 * 3600,
    }.get(str(cadence or "").lower(), 7 * 24 * 3600)


def wage_target_label(wage: dict[str, Any], members: list[dict[str, str]], roles: list[dict[str, str]], factions: dict[str, Any]) -> str:
    target_type = str(wage.get("target_type") or "user")
    target_id = str(wage.get("target_id") or "")
    if target_type == "user":
        match = next((member for member in members if str(member.get("id")) == target_id), None)
        return str((match or {}).get("label") or wage.get("target_label") or target_id or "Unknown member")
    if target_type == "role":
        match = next((role for role in roles if str(role.get("id")) == target_id), None)
        return str((match or {}).get("label") or wage.get("target_label") or target_id or "Unknown role")
    if target_type == "faction":
        faction = factions.get(target_id) if isinstance(factions, dict) else None
        if isinstance(faction, dict):
            return str(faction.get("name") or wage.get("target_label") or target_id or "Unknown faction")
        return str(wage.get("target_label") or target_id or "Unknown faction")
    return str(wage.get("target_label") or target_id or "Unknown target")


def enriched_wage_records(wage_records: Any, members: list[dict[str, str]], roles: list[dict[str, str]], factions: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(wage_records, list):
        return []
    enriched = []
    for wage in wage_records:
        if not isinstance(wage, dict):
            continue
        record = dict(wage)
        record["target_label"] = wage_target_label(record, members, roles, factions)
        enriched.append(record)
    return enriched


def list_records(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def dashboard_admin_records(dashboard_admin: Any, section: str, guild_id: str) -> list[dict[str, Any]]:
    if not isinstance(dashboard_admin, dict):
        return []
    section_data = dashboard_admin.get(section, {})
    if not isinstance(section_data, dict):
        return []
    return [item for item in list_records(section_data.get(guild_id, {})) if isinstance(item, dict)]


VALID_DASHBOARD_THEMES = {
    "default", "forest", "amber", "steel", "highland", "daylight", "sandstorm",
    "midnight", "bloodmoon", "radioactive", "arctic", "toxic", "violet", "rose",
    "command",
}

COMMAND_SECTION_META = {
    "overview": {"kicker": "Operations", "title": "Command Overview", "body": "Live server state, active events, zones, economy and loadout readiness in one control room."},
    "leaderboards": {"kicker": "Progression", "title": "Leaderboards", "body": "Review player rankings, activity totals and competitive server stats."},
    "automations": {"kicker": "Comms", "title": "Embeds & Welcome", "body": "Build automated Discord panels, announcements and welcome flows for the selected server."},
    "factions": {"kicker": "Groups", "title": "Factions", "body": "Manage faction records, balances, wages and server-linked group data."},
    "zones": {"kicker": "Territory", "title": "Zones & Map", "body": "Draft radar, safe and PVP zones with map-first editing and coordinate readouts."},
    "members": {"kicker": "Roster", "title": "Members", "body": "Inspect linked members, wallet state, faction status and dashboard-facing player data."},
    "heatmaps": {"kicker": "Intel", "title": "Heatmaps", "body": "Read activity hotspots and movement signals from your server logs."},
    "pve": {"kicker": "Live Ops", "title": "PVE Workshop", "body": "Queue, upload and track airdrops, hordes, animal packs, vehicles and CE XML event scenes."},
    "economy": {"kicker": "Banking", "title": "Economy", "body": "Control private money, faction treasury tools and transfer records."},
    "shop": {"kicker": "Trading", "title": "Manage Shop", "body": "Edit prices, bundles, stock behaviour and shop item visibility for the selected server."},
    "xml-workshop": {"kicker": "Files", "title": "XML Workshop", "body": "Generate console-safe XML packages for loot, events, containers, vehicles and loadouts."},
    "dayz-converter": {"kicker": "Maps", "title": "Map Converter", "body": "Convert editor and map data into server-ready XML structures."},
    "loot-engine": {"kicker": "Loot", "title": "Loot Engine", "body": "Build curated loot pools, container cargo and pristine item templates."},
    "visual-loadout": {"kicker": "Spawn Gear", "title": "Visual Loadout", "body": "Assemble player loadouts with body slots, cargo, child attachments and exportable server files."},
    "bulk-economy": {"kicker": "Economy", "title": "Bulk Economy", "body": "Run wider economy edits and batch wallet or faction updates."},
    "server-rules": {"kicker": "Rules", "title": "Server Rules", "body": "Publish and maintain server rules for players and Discord panels."},
    "moderation": {"kicker": "Safety", "title": "Moderation", "body": "Handle admin actions, audit entries and moderation tooling."},
    "server-control": {"kicker": "Console", "title": "Server Control", "body": "Use server-side controls and operational actions for the selected Nitrado service."},
    "help": {"kicker": "Guide", "title": "Help", "body": "Quick references for dashboard tools, uploads, live events and setup notes."},
    "access": {"kicker": "Servers", "title": "Servers & Login", "body": "Link servers together, switch between dashboards and manage owner access controls when available."},
    "owner": {"kicker": "Owner", "title": "Owner Console", "body": "Global owner-only operations across Wandering Bot servers."},
}


def dashboard_theme_from_config(config: dict[str, Any]) -> str:
    return "command"


def item_image_url(item_name: Any) -> str:
    item = safe_dayz_class(item_name)
    if not item:
        return ""
    return f"https://db.mydayz.eu/wp-content/uploads/2025/08/{urllib.parse.quote(item)}.png.webp"


def item_thumb_fallback(category: Any = "General") -> str:
    return f"/item-thumb/{urllib.parse.quote(str(category or 'General'))}"


def shop_category_map(shop: Any) -> dict[str, list[dict[str, Any]]]:
    categories: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(shop, dict):
        return categories
    for item_name, data in sorted(shop.items(), key=lambda item: str(item[0]).lower()):
        if not isinstance(data, dict):
            data = {}
        is_bundle = str(data.get("type") or "").lower() == "bundle"
        category = str(data.get("category") or ("Bundles" if is_bundle else "General"))
        if not is_bundle and not is_shop_sellable_item(item_name, category):
            continue
        bundle_items = parse_shop_bundle_items(data.get("bundle_items", [])) if is_bundle else []
        categories.setdefault(category, []).append(
            {
                "name": str(item_name),
                "category": category,
                "image_url": item_image_url(item_name),
                "fallback_image_url": item_thumb_fallback(category),
                "type": "bundle" if is_bundle else "item",
                "price": safe_int(data.get("price")),
                "enabled": bool(data.get("enabled", True)),
                "daily_limit": safe_int(data.get("daily_limit")),
                "allowed_role_ids": [str(item) for item in data.get("allowed_role_ids", [])] if isinstance(data.get("allowed_role_ids"), list) else [],
                "blocked_user_ids": [str(item) for item in data.get("blocked_user_ids", [])] if isinstance(data.get("blocked_user_ids"), list) else [],
                "bundle_items": bundle_items,
                "bundle_summary": ", ".join(f"{row['quantity']}x {row['item']}" for row in bundle_items),
            }
        )
    return dict(sorted(categories.items(), key=lambda item: item[0].lower()))


def flat_shop_items(shop: Any) -> list[dict[str, Any]]:
    items = []
    for category_items in shop_category_map(shop).values():
        items.extend(category_items)
    return sorted(items, key=lambda item: (str(item.get("category", "")).lower(), str(item.get("name", "")).lower()))


def count_shop_items(shop: Any) -> int:
    if not isinstance(shop, dict):
        return 0
    total = 0
    for item_name, data in shop.items():
        if not isinstance(data, dict):
            data = {}
        is_bundle = str(data.get("type") or "").lower() == "bundle"
        category = str(data.get("category") or ("Bundles" if is_bundle else "General"))
        if is_bundle or is_shop_sellable_item(item_name, category):
            total += 1
    return total


def item_matches_terms(item: dict[str, Any], terms: tuple[str, ...]) -> bool:
    text = f"{item.get('name', '')} {item.get('category', '')}".lower()
    return any(term in text for term in terms)


def item_name_matches_terms(item: dict[str, Any], terms: tuple[str, ...]) -> bool:
    text = str(item.get("name", "")).lower()
    return any(term in text for term in terms)


def item_not_matching_terms(item: dict[str, Any], terms: tuple[str, ...]) -> bool:
    return not item_matches_terms(item, terms)


def xml_picker_groups(items: list[dict[str, Any]]) -> dict[str, Any]:
    def fallback_item(name: str, category: str) -> dict[str, Any]:
        return {
            "name": name,
            "category": category,
            "label": name,
            "image_url": item_image_url(name),
            "fallback_image_url": "",
        }

    whole_vehicle_names = {
        "offroadhatchback",
        "offroadhatchback_sand",
        "offroadhatchback_red",
        "offroadhatchback_white",
        "civiliansedan",
        "hatchback_02",
        "sedan_02",
        "truck_01",
        "truck_01_covered",
        "truck_01_cargo",
        "offroad_02",
        "boat_01",
        "vehicleoffroadhatchback",
        "vehicleciviliansedan",
        "vehiclehatchback_02",
        "vehiclesedan_02",
        "vehicletruck_01",
        "vehicletruck_01_covered",
        "vehicletruck_01_cargo",
        "vehicleoffroad_02",
        "vehicleboat_01",
    }
    whole_vehicle_aliases = {
        "ada": "OffroadHatchback",
        "ada4x4": "OffroadHatchback",
        "olga": "CivilianSedan",
        "olga24": "CivilianSedan",
        "gunter": "Hatchback_02",
        "sarka": "Sedan_02",
        "m3s": "Truck_01_Covered",
        "humvee": "Offroad_02",
    }
    vehicle_part_terms = (
        "hood",
        "trunk",
        "wheel",
        "door",
        "battery",
        "radiator",
        "sparkplug",
        "tire",
        "tyre",
        "headlight",
        "mirror",
    )
    container_terms = ("bag", "backpack", "barrel", "crate", "sea chest", "seachest", "case", "container", "drybag", "protectorcase")
    head_terms = ("helmet", "cap", "beanie", "balaclava", "head", "beret", "ushanka", "boonie", "cowboyhat", "leatherhat", "baseballcap")
    eye_terms = ("glasses", "eyewear", "nvg", "goggles")
    mask_terms = ("mask", "respirator", "bandana", "balaclava")
    body_terms = ("jacket", "shirt", "hoodie", "coat", "torso", "body", "sweater")
    vest_terms = ("vest", "platecarrier", "chest")
    hips_terms = ("belt", "holster", "hips", "sheath")
    legs_terms = ("pants", "trousers", "skirt", "legs")
    feet_terms = ("boots", "shoes", "sneakers", "feet")
    gloves_terms = ("glove", "gloves")
    armband_terms = ("armband",)
    firearm_terms = (
        "weapon",
        "firearm",
        "rifle",
        "gun",
        "pistol",
        "shotgun",
        "smg",
        "akm",
        "ak74",
        "ak101",
        "m4a1",
        "mosin",
        "sks",
        "svd",
        "fal",
        "aug",
        "vss",
        "vikh",
        "crossbow",
    )
    hands_terms = firearm_terms + ("tool", "hammer", "hatchet", "saw", "shovel", "pickaxe", "wrench", "knife", "axe", "sword", "melee")
    excluded_loot_terms = (
        "animal",
        "infected",
        "zombie",
        "wreck",
        "lootdispatch",
        "offroadhatchback",
        "civiliansedan",
        "hatchback_02",
        "sedan_02",
        "truck_01",
        "offroad_02",
        "boat_01",
        "hood",
        "trunk",
        "wheel",
        "door",
        "battery",
        "radiator",
        "sparkplug",
    )
    player_cargo_storage_terms = (
        "backpack",
        "alicebag",
        "assaultbag",
        "courierbag",
        "drybag",
        "huntingbag",
        "improvisedbag",
        "mountainbag",
        "taloonbag",
        "barrel",
        "crate",
        "seachest",
        "sea chest",
        "protectorcase",
        "container",
        "cartent",
        "largetent",
        "mediumtent",
        "partytent",
        "tent",
    )
    player_cargo_building_names = {
        "woodenlog",
        "woodenplank",
        "metalplate",
        "sheetmetal",
        "stone",
        "smallstone",
        "fencekit",
        "watchtowerkit",
        "territoryflagkit",
        "flagpolekit",
    }

    known_vehicles = [
        fallback_item("OffroadHatchback", "Vehicles"),
        fallback_item("CivilianSedan", "Vehicles"),
        fallback_item("Hatchback_02", "Vehicles"),
        fallback_item("Sedan_02", "Vehicles"),
        fallback_item("Truck_01_Covered", "Vehicles"),
        fallback_item("Offroad_02", "Vehicles"),
        fallback_item("Boat_01", "Vehicles"),
    ]
    known_containers = [
        fallback_item("AliceBag_Black", "Containers"),
        fallback_item("AliceBag_Camo", "Containers"),
        fallback_item("DryBag_Black", "Containers"),
        fallback_item("DryBag_Camo", "Containers"),
        fallback_item("SeaChest", "Containers"),
        fallback_item("Barrel_Green", "Containers"),
        fallback_item("WoodenCrate", "Containers"),
        fallback_item("StaticObj_Misc_WoodenCrate_5x", "Containers"),
        fallback_item("ProtectorCase", "Containers"),
    ]

    def unique_named(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = set()
        unique = []
        for item in values:
            name = str(item.get("name", "")).strip()
            key = name.lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return sorted(unique, key=lambda item: str(item.get("name", "")).lower())

    def is_whole_vehicle(item: dict[str, Any]) -> bool:
        name = str(item.get("name", "")).strip().lower()
        category = str(item.get("category", "")).lower()
        if not name:
            return False
        bad_category_terms = ("lootdispatch", "vehicleparts", "vehicle_parts", "parts")
        if any(term in category for term in bad_category_terms):
            return False
        if any(term in name for term in vehicle_part_terms):
            return False
        if category and "vehicle" not in category and name not in whole_vehicle_names:
            return False
        if name in whole_vehicle_names:
            return True
        return whole_vehicle_aliases.get(name, "").lower() in whole_vehicle_names

    def group_or_fallback(group_items: list[dict[str, Any]], fallback_names: list[str], category: str) -> list[dict[str, Any]]:
        if group_items:
            return group_items
        return [fallback_item(name, category) for name in fallback_names]

    def is_player_cargo_item(item: dict[str, Any]) -> bool:
        name = str(item.get("name", "")).strip()
        lower = name.lower()
        category = str(item.get("category", "")).lower()
        if not name:
            return False
        if is_whole_vehicle(item) or any(term in lower for term in vehicle_part_terms):
            return False
        if lower in player_cargo_building_names or lower.startswith(("woodenlog", "woodenplank", "metalplate", "sheetmetal")):
            return False
        if any(term in lower for term in player_cargo_storage_terms):
            return False
        if any(term in category for term in ("container", "storage", "vehicle", "animal", "infected", "zombie")):
            return False
        return item_not_matching_terms(item, excluded_loot_terms)

    groups = {
        "all": items,
        "cargo": [item for item in items if item_not_matching_terms(item, excluded_loot_terms)],
        "player_cargo": [item for item in items if is_player_cargo_item(item)],
        "containers": [item for item in items if item_matches_terms(item, container_terms)],
        "vehicles": [item for item in items if is_whole_vehicle(item)],
        "Head": group_or_fallback([item for item in items if item_name_matches_terms(item, head_terms)], ["BallisticHelmet", "BaseballCap_Black", "BoonieHat_Green"], "Clothes"),
        "Eyes": group_or_fallback([item for item in items if item_name_matches_terms(item, eye_terms)], ["SportGlasses_Black", "NVGoggles"], "Clothes"),
        "Mask": group_or_fallback([item for item in items if item_name_matches_terms(item, mask_terms)], ["BalaclavaMask_Black", "SurgicalMask"], "Clothes"),
        "Body": group_or_fallback([item for item in items if item_name_matches_terms(item, body_terms)], ["HikingJacket_Black", "TShirt_Black", "Hoodie_Black"], "Clothes"),
        "Vest": group_or_fallback([item for item in items if item_name_matches_terms(item, vest_terms)], ["PlateCarrierVest", "HighCapacityVest_Black"], "Clothes"),
        "Back": group_or_fallback([item for item in items if item_name_matches_terms(item, ("backpack", "bag", "drybag", "alicebag", "mountainbag", "taloonbag", "courierbag", "improvisedbag"))], ["AliceBag_Black", "DryBag_Black", "MountainBag_Blue"], "Containers"),
        "Hips": group_or_fallback([item for item in items if item_name_matches_terms(item, hips_terms)], ["MilitaryBelt", "CivilianBelt"], "Clothes"),
        "Legs": group_or_fallback([item for item in items if item_name_matches_terms(item, legs_terms)], ["CargoPants_Black", "Jeans_Black"], "Clothes"),
        "Feet": group_or_fallback([item for item in items if item_name_matches_terms(item, feet_terms)], ["MilitaryBoots_Black", "AthleticShoes_Black"], "Clothes"),
        "Hands": group_or_fallback([item for item in items if item_name_matches_terms(item, hands_terms)], ["M4A1", "AKM", "Hatchet", "CombatKnife"], "Weapons"),
        "Left Shoulder": group_or_fallback([item for item in items if item_name_matches_terms(item, firearm_terms)], ["M4A1", "AKM", "Mosin9130", "SKS"], "Weapons"),
        "Right Shoulder": group_or_fallback([item for item in items if item_name_matches_terms(item, firearm_terms)], ["M4A1", "AKM", "Mosin9130", "SKS"], "Weapons"),
        "Gloves": group_or_fallback([item for item in items if item_name_matches_terms(item, gloves_terms)], ["TacticalGloves_Black", "WorkingGloves_Black"], "Clothes"),
        "Armband": group_or_fallback([item for item in items if item_name_matches_terms(item, armband_terms)], ["Armband_Black", "Armband_Red", "Armband_Green"], "Clothes"),
    }
    groups["vehicles"] = unique_named(groups["vehicles"] + known_vehicles)
    groups["containers"] = unique_named(groups["containers"] + known_containers)
    groups["cargo"] = groups["cargo"] or items
    groups["player_cargo"] = groups["player_cargo"] or groups["cargo"]
    groups["Unsorted"] = groups["cargo"]
    return groups


def is_shop_record(value: Any) -> bool:
    return isinstance(value, dict) and any(
        key in value
        for key in ("price", "category", "enabled", "daily_limit", "allowed_role_ids", "blocked_user_ids", "type", "bundle_items")
    )


def shop_for_guild(shop: Any, guild_id: str) -> dict[str, Any]:
    if not isinstance(shop, dict):
        return {}
    block = shop.get(str(guild_id))
    if isinstance(block, dict) and not is_shop_record(block):
        return block
    return {str(name): data for name, data in shop.items() if is_shop_record(data)}


def faction_records_for_guild(factions: Any, guild_id: str) -> dict[str, Any]:
    records: dict[str, Any] = {}
    if not isinstance(factions, dict):
        return records

    nested = factions.get(str(guild_id))
    if isinstance(nested, dict):
        for name, faction in nested.items():
            record = dict(faction) if isinstance(faction, dict) else {}
            record.setdefault("name", str(name))
            records[str(record.get("name") or name)] = record

    prefix = f"{guild_id}:"
    for key, faction in factions.items():
        if not str(key).startswith(prefix):
            continue
        record = dict(faction) if isinstance(faction, dict) else {}
        name = str(record.get("name") or str(key)[len(prefix):] or key)
        record.setdefault("name", name)
        records.setdefault(name, record)

    return records


def wallet_records_for_guild(wallets: Any, guild_id: str) -> list[dict[str, Any]]:
    records = []
    if not isinstance(wallets, dict):
        return records
    prefix = f"{guild_id}:"
    for key, wallet in wallets.items():
        if str(key).startswith(prefix) and isinstance(wallet, dict):
            records.append(dict(wallet))
        elif isinstance(wallet, dict) and str(wallet.get("guild_id")) == str(guild_id):
            records.append(dict(wallet))
    return records


def map_size_for(server_map: str) -> int:
    name = str(server_map or "").strip().lower()
    if "livonia" in name or name == "enoch":
        return 12800
    return 15360


def map_key_for(server_map: str) -> str:
    name = str(server_map or "").strip().lower()
    if "livonia" in name or name == "enoch":
        return "livonia"
    return "chernarus"


def dashboard_airdrop_location_presets(server_map: str) -> list[dict[str, Any]]:
    key = map_key_for(server_map)
    presets = DASHBOARD_AIRDROP_LOCATION_PRESETS.get(key) or DASHBOARD_AIRDROP_LOCATION_PRESETS["chernarus"]
    return [dict(item) for item in presets]


def dashboard_airdrop_preset_location(server_map: str, name: Any) -> dict[str, Any] | None:
    wanted = str(name or "").strip().lower()
    if not wanted:
        return None
    for location in dashboard_airdrop_location_presets(server_map):
        if str(location.get("name") or "").strip().lower() == wanted:
            return location
    return None


def parse_scenario_batch_locations(raw: Any, map_size: int) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for line in str(raw or "").replace("\r", "\n").splitlines():
        text = line.strip()
        if not text:
            continue
        parts = [part.strip() for part in re.split(r"[,;|\t]+", text) if part.strip()]
        if len(parts) < 2:
            continue
        numbers: list[tuple[int, str]] = []
        names: list[str] = []
        for part in parts:
            if re.fullmatch(r"-?\d+(?:\.\d+)?", part):
                numbers.append((safe_int(part, 0), part))
            else:
                names.append(part)
        if len(numbers) < 2:
            continue
        x = max(0, min(map_size, numbers[0][0]))
        z = max(0, min(map_size, numbers[1][0]))
        name = " ".join(names).strip() or f"{x}, {z}"
        key = (x, z, name.lower())
        if key in seen:
            continue
        seen.add(key)
        locations.append({"name": name[:80], "x": x, "z": z})
    return locations


def map_image_file_for(server_map: str) -> str:
    return MAP_IMAGE_FILES.get(map_key_for(server_map), MAP_IMAGE_FILES["chernarus"])


def map_image_available_for(server_map: str) -> bool:
    key = map_key_for(server_map)
    return os.path.exists(map_image_file_for(server_map)) or bool(DEFAULT_MAP_IMAGE_SOURCES.get(key))


def normalized_zones(config: dict[str, Any], server_map: str, factions: dict[str, Any] | None = None, channels: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    map_size = map_size_for(server_map)
    zones = []
    for zone in list_records(config.get("zones", [])):
        if isinstance(zone, dict):
            zones.append(dict(zone))
    for zone in list_records(config.get("safe_zones", [])):
        if isinstance(zone, dict):
            zone = dict(zone)
            zone.setdefault("zone_type", "safe")
            zones.append(zone)
    for zone in list_records(config.get("radar_zones", [])):
        if isinstance(zone, dict):
            zone = dict(zone)
            zone.setdefault("zone_type", "radar")
            zones.append(zone)
    normalized = []
    seen = set()
    def first_present(*values: Any) -> Any:
        return next((value for value in values if value not in (None, "")), 0)

    for zone in zones:
        if not isinstance(zone, dict):
            continue
        x = max(0, min(map_size, safe_int(first_present(zone.get("x"), zone.get("center_x"), zone.get("pos_x")))))
        z = max(
            0,
            min(
                map_size,
                safe_int(
                    first_present(
                        zone.get("z"),
                        zone.get("center_z"),
                        zone.get("pos_z"),
                        zone.get("y"),
                        zone.get("center_y"),
                        zone.get("pos_y"),
                    )
                ),
            ),
        )
        y = z
        radius = max(25, safe_int(zone.get("radius") or zone.get("radius_m") or 250))
        shape = str(zone.get("shape") or ("boundary" if zone.get("boundary_points") else "circle")).lower()
        if shape not in {"circle", "boundary"}:
            shape = "circle"
        raw_points = zone.get("boundary_points") if isinstance(zone.get("boundary_points"), list) else []
        boundary_points = []
        for point in raw_points:
            if not isinstance(point, dict):
                continue
            point_x = max(0, min(map_size, safe_int(point.get("x"))))
            point_z = max(0, min(map_size, safe_int(first_present(point.get("z"), point.get("y")))))
            boundary_points.append({"x": point_x, "y": point_z, "z": point_z})
        points_percent = " ".join(
            f"{round((point['x'] / map_size) * 100, 2)},{round(100 - ((point['y'] / map_size) * 100), 2)}"
            for point in boundary_points
        )
        zone_type = str(zone.get("zone_type") or zone.get("type") or "radar").lower()
        if zone_type not in {"safe", "pvp", "radar", "action", "faction", "custom"}:
            zone_type = "custom"
        faction_name = str(zone.get("faction_name") or zone.get("faction") or "").strip()
        faction_colour = ""
        if faction_name and isinstance(factions, dict):
            faction = factions.get(faction_name) or factions.get(faction_name.lower())
            if not faction:
                faction = next(
                    (
                        item
                        for key, item in factions.items()
                        if str(key).lower() == faction_name.lower()
                        or str(item.get("name", "") if isinstance(item, dict) else "").lower() == faction_name.lower()
                    ),
                    {},
                )
            if isinstance(faction, dict):
                faction_colour = str(faction.get("colour") or faction.get("color") or "")
        fallback_colours = {
            "safe": "#22c55e",
            "pvp": "#ef4444",
            "radar": "#38bdf8",
            "action": "#f97316",
            "faction": "#a855f7",
            "custom": "#facc15",
        }
        raw_colour = str(zone.get("colour") or zone.get("color") or "").strip()
        colour = safe_colour(raw_colour or faction_colour, fallback_colours.get(zone_type, "#38bdf8"))
        zone_palette = [
            "#38bdf8",
            "#f97316",
            "#a855f7",
            "#22c55e",
            "#facc15",
            "#ef4444",
            "#14b8a6",
            "#60a5fa",
            "#f472b6",
            "#84cc16",
            "#fb7185",
            "#06b6d4",
        ]
        defaultish = {"", "#d5b45f", "#8d963e", "#6ec6e0", "#b978ff", "#ff7b68", "#9dff3a", "#ff9f43", "#75d89a", fallback_colours.get(zone_type, "").lower()}
        if faction_colour:
            display_colour = safe_colour(faction_colour, colour)
        elif raw_colour.lower() in defaultish:
            display_colour = zone_palette[len(normalized) % len(zone_palette)]
        else:
            display_colour = colour
        zone_id = str(zone.get("id") or zone.get("name") or f"zone-{len(normalized) + 1}")
        channel_value = str(zone.get("channel_key") or zone.get("alert_channel_id") or zone.get("report_channel_id") or "")
        dedupe_key = (zone_type, zone_id, x, y, radius)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "id": zone_id,
                "name": str(zone.get("name") or zone.get("label") or "Unnamed zone"),
                "zone_type": zone_type,
                "colour": colour,
                "display_colour": display_colour,
                "faction_name": faction_name,
                "x": x,
                "y": y,
                "z": y,
                "radius": radius,
                "shape": shape,
                "boundary_points": boundary_points,
                "points_percent": points_percent,
                "channel_key": str(zone.get("channel_key") or ""),
                "channel_label": channel_label_from_channels(channels or [], channel_value, "default"),
                "alert_channel_id": str(zone.get("alert_channel_id") or ""),
                "report_channel_id": str(zone.get("report_channel_id") or ""),
                "role_id": str(zone.get("role_id") or ""),
                "mention_role_id": str(zone.get("mention_role_id") or ""),
                "action": str(zone.get("action") or "none"),
                "enabled": bool(zone.get("enabled", True)),
                "x_percent": round((x / map_size) * 100, 2) if map_size else 0,
                "y_percent": round(100 - ((y / map_size) * 100), 2) if map_size else 0,
                "radius_percent": round(max(1.2, min(75.0, ((radius * 2) / map_size) * 100)), 3) if map_size else 3,
                "dot_size": max(34, min(72, int((radius / map_size) * 420))),
            }
        )
    return normalized


def heatmap_summary(heatmap: Any, guild_id: str) -> dict[str, Any]:
    raw = guild_block(heatmap, guild_id, {}) if isinstance(heatmap, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    modes = raw.get("__modes__", {}) if isinstance(raw.get("__modes__"), dict) else {}
    pvp = {key: value for key, value in raw.items() if not str(key).startswith("__") and isinstance(value, int)}
    if pvp:
        modes = dict(modes)
        modes.setdefault("pvp", pvp)
    if not modes:
        modes = {"all": pvp}
    summary_modes = {}
    total = 0
    for mode, counts in modes.items():
        if not isinstance(counts, dict):
            continue
        rows = sorted(
            ({"name": str(zone), "count": safe_int(count)} for zone, count in counts.items()),
            key=lambda item: item["count"],
            reverse=True,
        )[:8]
        max_count = max([row["count"] for row in rows] or [1])
        for row in rows:
            row["percent"] = max(5, min(100, int((row["count"] / max_count) * 100))) if row["count"] else 0
        total += sum(row["count"] for row in rows)
        summary_modes[str(mode)] = rows
    return {"total": total, "modes": summary_modes}


def pve_summary(challenges: Any, campaigns: Any, schedules: Any, guild_id: str, channels: list[dict[str, str]]) -> dict[str, Any]:
    active = []
    for quest in list_records(guild_block(challenges, guild_id, [])):
        if not isinstance(quest, dict):
            continue
        active.append(
            {
                "title": str(quest.get("title") or quest.get("name") or quest.get("quest_code") or "Untitled quest"),
                "difficulty": str(quest.get("difficulty") or quest.get("tier") or "Normal"),
                "reward_pennies": safe_int(quest.get("reward_pennies") or quest.get("reward")),
                "reward_type": str(quest.get("reward_type") or "pennies"),
            }
        )
    campaign_records = list_records(guild_block(campaigns, guild_id, []))
    schedule_records = list_records(guild_block(schedules, guild_id, []))
    reward_types = sorted({quest["reward_type"] for quest in active if quest.get("reward_type")})
    quest_channels = len([channel for channel in channels if "pve" in channel.get("key", "") or "quest" in channel.get("key", "")])
    return {
        "active": active,
        "campaigns": len(campaign_records),
        "schedules": len(schedule_records),
        "reward_types": reward_types,
        "quest_channels": quest_channels,
    }


def owner_notifications(servers: list[dict[str, Any]], delivery_queue: Any, dashboard_admin: Any) -> list[dict[str, str]]:
    notes = []
    for server in servers:
        if not server.get("active"):
            notes.append({"title": f"{server.get('guild_name')} inactive", "body": "The bot is marked as removed or inactive for this guild."})
        if not server.get("dashboard_access", {}).get("enabled"):
            notes.append({"title": f"{server.get('guild_name')} admin dashboard locked", "body": "Normal server-admin login is disabled. Owner login can still open and manage this server."})
    queued = count_records(delivery_queue)
    if queued:
        notes.append({"title": "Shop deliveries waiting", "body": f"{queued} delivery records are queued for the next restart."})
    if isinstance(dashboard_admin, dict):
        saved_messages = sum(count_records(block) for block in dashboard_admin.get("embed_templates", {}).values()) if isinstance(dashboard_admin.get("embed_templates"), dict) else 0
        if saved_messages:
            notes.append({"title": "Saved embed templates", "body": f"{saved_messages} auto-message/embed templates are configured across dashboards."})
    return notes[:10]


def load_dashboard_state(active_section: str = "overview") -> dict[str, Any]:
    runtime_state = CUSTOM_STATE_PROVIDER() if CUSTOM_STATE_PROVIDER else {}
    if not isinstance(runtime_state, dict):
        runtime_state = {}

    active_section = str(active_section or "overview").strip().lower()
    full_sections = {"overview", "owner", "access"}
    needs_full = active_section in full_sections
    needs_player_counts = True
    needs_shop_counts = True
    needs_players = needs_full or active_section in {"leaderboards", "members", "economy"}
    needs_shop = needs_full or active_section in {"shop", "xml-workshop", "loot-engine", "visual-loadout", "bulk-economy"}
    needs_wallets = needs_full or active_section in {"economy", "members"}
    needs_factions = needs_full or active_section in {"factions", "zones", "members", "economy"}
    needs_wages = needs_full or active_section == "economy"
    needs_delivery = needs_full or active_section == "pve"
    needs_admin_records = needs_full or active_section == "automations"
    needs_heatmap = needs_full or active_section == "heatmaps"
    needs_pve = needs_full or active_section == "pve"
    needs_leaderboard_extras = needs_full or active_section == "leaderboards"
    needs_discord_roles = needs_full or active_section in {"factions", "economy", "xml-workshop", "loot-engine", "visual-loadout", "bulk-economy", "server-rules", "shop", "access"}
    needs_discord_members = needs_full or active_section in {"factions", "members", "economy"}

    guild_configs = runtime_state.get("guild_configs") or load_store("guild_configs", {})
    player_stats = (runtime_state.get("player_stats") or load_store("player_stats", {})) if needs_players or needs_player_counts else {}
    online_players = runtime_state.get("online_players") or load_store("online_players", {})
    # Shop edits are written through the dashboard to shop.json first. Prefer
    # that canonical file for shop-facing pages so a refresh cannot show stale
    # runtime_state["shop_items"] after a price/category edit.
    if needs_shop or needs_shop_counts:
        if active_section in {"shop", "xml-workshop", "loot-engine", "visual-loadout", "bulk-economy"}:
            shop = load_store("shop", {})
        else:
            shop = runtime_state.get("shop_items") or runtime_state.get("shop") or load_store("shop", {})
    else:
        shop = {}
    wallets = (runtime_state.get("wallets") or load_store("wallets", {})) if needs_wallets else {}
    factions = (runtime_state.get("factions") or load_store("factions", {})) if needs_factions else {}
    wages = (runtime_state.get("wages") or load_store("wages", {})) if needs_wages else {}
    delivery_queue = (runtime_state.get("delivery_queue") or load_store("delivery_queue", [])) if needs_delivery else []
    dashboard_admin = load_store("dashboard_admin", {}) if needs_admin_records else {}
    heatmap = (runtime_state.get("territory_heat") or runtime_state.get("heatmap") or load_store("heatmap", {})) if needs_heatmap else {}
    pve_challenges = (runtime_state.get("pve_challenges") or load_store("pve_challenges", {})) if needs_pve else {}
    pve_ai_campaigns = (runtime_state.get("pve_ai_campaigns") or load_store("pve_ai_campaigns", {})) if needs_pve else {}
    pve_workshop_schedules = (runtime_state.get("pve_workshop_schedules") or load_store("pve_workshop_schedules", {})) if needs_pve else {}
    swear_jar = (runtime_state.get("swear_jar") or load_store("swear_jar", {})) if needs_leaderboard_extras else {}
    longshot_records = (runtime_state.get("longshot_records") or load_store("longshot_records", {})) if needs_leaderboard_extras else {}
    shop_categories = shop_category_map(shop) if needs_shop else {}
    shop_items = flat_shop_items(shop) if needs_shop else []

    if not isinstance(guild_configs, dict):
        guild_configs = {}
    if not isinstance(online_players, dict):
        online_players = {}
    discord_guild_counts = runtime_state.get("discord_guild_counts") or {}
    if not isinstance(discord_guild_counts, dict):
        discord_guild_counts = {}

    servers = []
    total_online = 0
    total_players = 0
    total_kills = 0
    dashboard_enabled = 0

    for guild_id, config in sorted(guild_configs.items(), key=lambda item: str(item[1].get("guild_name", item[0])).lower() if isinstance(item[1], dict) else str(item[0])):
        if not isinstance(config, dict):
            continue
        guild_id = normalize_guild_id(guild_id)
        players = guild_players(player_stats, guild_id) if needs_players else []
        player_count = len(players) if needs_players else (len(guild_players(player_stats, guild_id)) if needs_player_counts else 0)
        online = sorted(str(player) for player in online_players.get(guild_id, []) if player)
        access = dashboard_access(config)
        server_map = str(config.get("server_map") or config.get("map") or "chernarus")
        server_platform = normalize_dashboard_server_platform(config.get("server_platform") or config.get("platform"))
        channels = public_channels(config.get("channels", {}), guild_id)
        server_factions = faction_records_for_guild(factions, guild_id) if needs_factions else {}
        server_factions = enrich_faction_channel_labels(server_factions, channels) if server_factions else {}
        server_members = member_records_for_guild(players, online, server_factions) if needs_players or needs_discord_members else []
        zones = normalized_zones(config, server_map, server_factions, channels)
        safe_zones = config.get("safe_zones") or []
        if not isinstance(safe_zones, list):
            safe_zones = []
        server_shop = shop_for_guild(shop, guild_id) if needs_shop or needs_shop_counts else {}
        server_shop_item_count = count_shop_items(server_shop) if needs_shop or needs_shop_counts else 0
        server_shop_categories = shop_category_map(server_shop) if needs_shop else {}
        server_shop_items = flat_shop_items(server_shop) if needs_shop else []
        server_wallets = wallet_records_for_guild(wallets, guild_id) if needs_wallets else []
        discord_roles = discord_guild_roles(guild_id) if needs_discord_roles else []
        discord_members = discord_guild_members(guild_id) if needs_discord_members else []
        server_wages = enriched_wage_records(guild_block(wages, guild_id, []), discord_members, discord_roles, server_factions) if needs_wages else []
        discord_member_count = runtime_discord_member_count(guild_id, discord_guild_counts) if needs_discord_members else None
        if discord_member_count is None and needs_discord_members:
            discord_member_count = discord_guild_member_count(guild_id)
        if discord_member_count is None:
            discord_member_count = len(discord_members) if discord_members else len(server_members)
        server_heatmap = heatmap_summary(heatmap, guild_id) if needs_heatmap else {"total": 0, "modes": {}}
        server_pve = pve_summary(pve_challenges, pve_ai_campaigns, pve_workshop_schedules, guild_id, channels) if needs_pve else {"active": [], "campaigns": 0, "schedules": 0, "reward_types": [], "quest_channels": 0}
        totals = {
            "kills": sum(player["kills"] for player in players),
            "deaths": sum(player["deaths"] for player in players),
            "builds": sum(player["builds"] for player in players),
            "players": player_count,
        }
        total_online += len(online)
        total_players += player_count
        total_kills += totals["kills"]
        dashboard_enabled += 1 if access["enabled"] else 0
        servers.append(
            {
                "guild_id": guild_id,
                "guild_name": str(config.get("guild_name") or f"Guild {guild_id}"),
                "active": not bool(config.get("bot_removed")),
                "map": server_map,
                "map_key": map_key_for(server_map),
                "map_size": map_size_for(server_map),
                "map_image_available": map_image_available_for(server_map),
                "platform": server_platform,
                "platform_label": dashboard_server_platform_label(server_platform),
                "online": online,
                "leaders": players,
                "leaderboards": leaderboard_categories(players, swear_jar, longshot_records, guild_id),
                "members": redact(server_members),
                "discord_members": redact(discord_members),
                "discord_member_count": discord_member_count,
                "discord_roles": redact(discord_roles),
                "channels": channels,
                "totals": totals,
                "safe_zones": redact(safe_zones),
                "zones": redact(zones),
                "scenario_events": redact(visible_scenario_events(config)),
                "dashboard_access": access,
                "factions": redact(server_factions),
                "wages": redact(server_wages),
                "wallets": redact(server_wallets),
                "shop_items": redact(server_shop_items),
                "shop_item_count": server_shop_item_count,
                "shop_categories": redact(server_shop_categories),
                "xml_workshop": redact(xml_workshop_summary(config)),
                "chat_rules": redact(config.get("chat_rules", [])),
                "embed_templates": redact(dashboard_admin_records(dashboard_admin, "embed_templates", guild_id)),
                "welcome_automations": redact(dashboard_admin_records(dashboard_admin, "welcome_automations", guild_id)),
                "utility_configs": redact(dashboard_admin_records(dashboard_admin, "utility_configs", guild_id)),
                "reaction_role_panels": redact(dashboard_admin_records(dashboard_admin, "reaction_role_panels", guild_id)),
                "heatmap": server_heatmap,
                "pve": server_pve,
                "config": redact(config),
            }
        )

    admin_embed_templates = dashboard_admin.get("embed_templates", {}) if isinstance(dashboard_admin, dict) else {}
    admin_welcome = dashboard_admin.get("welcome_automations", {}) if isinstance(dashboard_admin, dict) else {}
    admin_utility = dashboard_admin.get("utility_configs", {}) if isinstance(dashboard_admin, dict) else {}
    admin_reaction_roles = dashboard_admin.get("reaction_role_panels", {}) if isinstance(dashboard_admin, dict) else {}

    return {
        "summary": {
            "guilds": len(servers),
            "online": total_online,
            "players": total_players,
            "kills": total_kills,
            "dashboard_enabled": dashboard_enabled,
            "shop_items": sum(safe_int(server.get("shop_item_count")) for server in servers),
            "wallets": sum(count_records(server.get("wallets")) for server in servers) or count_records(wallets),
            "delivery_queue": count_records(delivery_queue),
            "factions": sum(count_records(server.get("factions")) for server in servers),
            "wages": sum(count_records(server.get("wages")) for server in servers),
            "embed_templates": count_records(admin_embed_templates),
            "welcome_automations": count_records(admin_welcome),
            "utility_configs": count_records(admin_utility),
            "reaction_role_panels": count_records(admin_reaction_roles),
            "heatmap_points": sum(server.get("heatmap", {}).get("total", 0) for server in servers),
            "pve_active": sum(count_records(server.get("pve", {}).get("active")) for server in servers),
            "pve_campaigns": sum(safe_int(server.get("pve", {}).get("campaigns")) for server in servers),
        },
        "servers": servers,
        "shop": redact(shop),
        "shop_items": redact(shop_items),
        "shop_categories": redact(shop_categories),
        "wallets": redact(wallets),
        "delivery_queue": redact(delivery_queue),
        "dashboard_admin": redact(dashboard_admin),
        "owner_notifications": owner_notifications(servers, delivery_queue, dashboard_admin),
        "generated_at": local_dashboard_time(),
        "generated_clock": local_dashboard_clock(),
    }


def filter_state_for_auth(state: dict[str, Any], auth: dict[str, Any], mode: str = "admin") -> dict[str, Any]:
    if auth["kind"] == "owner" and mode == "owner":
        return state
    allowed_guild_ids = [str(item) for item in auth.get("guild_ids", [auth.get("guild_id")]) if item]
    servers = [server for server in state["servers"] if str(server.get("guild_id")) in allowed_guild_ids]
    summary = dict(state["summary"])
    if servers:
        summary.update(
            {
                "guilds": len(servers),
                "online": sum(len(server.get("online", [])) for server in servers),
                "players": sum(safe_int(server.get("totals", {}).get("players")) for server in servers),
                "kills": sum(safe_int(server.get("totals", {}).get("kills")) for server in servers),
                "dashboard_enabled": sum(1 for server in servers if server.get("dashboard_access", {}).get("enabled")),
                "shop_items": sum(safe_int(server.get("shop_item_count")) for server in servers),
                "wallets": sum(count_records(server.get("wallets")) for server in servers),
                "factions": sum(count_records(server.get("factions")) for server in servers),
                "wages": sum(count_records(server.get("wages")) for server in servers),
                "heatmap_points": sum(server.get("heatmap", {}).get("total", 0) for server in servers),
                "pve_active": sum(count_records(server.get("pve", {}).get("active")) for server in servers),
                "pve_campaigns": sum(safe_int(server.get("pve", {}).get("campaigns")) for server in servers),
            }
        )
    else:
        summary.update({"guilds": 0, "online": 0, "players": 0, "kills": 0, "dashboard_enabled": 0, "factions": 0, "wages": 0, "heatmap_points": 0, "pve_active": 0, "pve_campaigns": 0})
    scoped = dict(state)
    scoped["summary"] = summary
    scoped["servers"] = servers
    return scoped


def page(mode: str, auth: dict[str, Any]):
    active_section = str(request.args.get("section") or "overview").strip().lower()
    valid_sections = {"overview", "leaderboards", "automations", "factions", "zones", "members", "heatmaps", "pve", "economy", "shop", "xml-workshop", "dayz-converter", "loot-engine", "visual-loadout", "bulk-economy", "server-rules", "moderation", "server-control", "help", "access", "owner"}
    if auth.get("kind") != "owner" and active_section == "owner":
        active_section = "overview"
    if auth.get("kind") == "owner" and mode != "owner" and active_section == "owner":
        active_section = "overview"
    if active_section not in valid_sections:
        active_section = "overview"
    state = load_dashboard_state(active_section)
    state = filter_state_for_auth(state, auth, mode)
    focused_guild_id = str(request.args.get("guild_id") or "").strip()
    if focused_guild_id and mode in {"admin", "overview", "owner"}:
        state = dict(state)
        focused = [server for server in state["servers"] if str(server.get("guild_id")) == focused_guild_id]
        others = [server for server in state["servers"] if str(server.get("guild_id")) != focused_guild_id]
        if focused:
            state["servers"] = focused + others
    selected_server = state["servers"][0] if state.get("servers") else {}
    selected_config = selected_server.get("config", {}) if isinstance(selected_server, dict) else {}
    dashboard_theme = dashboard_theme_from_config(selected_config) if isinstance(selected_config, dict) else "default"

    def section_allowed(section: str) -> bool:
        if auth.get("kind") == "owner":
            return True
        feature = SECTION_FEATURES.get(section)
        return dashboard_feature_allowed(selected_config, feature) if feature else True

    if not section_allowed(active_section):
        active_section = "overview"
    command_section = COMMAND_SECTION_META.get(active_section, COMMAND_SECTION_META["overview"])
    pve_tool = str(request.args.get("pve_tool") or "events").strip().lower()
    if pve_tool not in {"events", "builder", "quests"}:
        pve_tool = "events"
    if active_section == "pve" and request.args.get("edit_event"):
        pve_tool = "builder"
    xml_tool = str(request.args.get("xml_tool") or "player-loadout").strip().lower()
    if xml_tool not in {"loot", "airdrop", "container", "player-loadout", "vehicle-loadout", "saved"}:
        xml_tool = "player-loadout"
    ce_defaults = dashboard_default_ce_paths(selected_config if isinstance(selected_config, dict) else {})
    server_map = str(selected_config.get("server_map") or selected_config.get("map") or "chernarus") if isinstance(selected_config, dict) else "chernarus"
    airdrop_location_presets = dashboard_airdrop_location_presets(server_map)
    picker_source_items = selected_server.get("shop_items", []) if active_section in {"xml-workshop", "loot-engine", "visual-loadout", "bulk-economy"} and isinstance(selected_server, dict) else []
    picker_groups = xml_picker_groups(picker_source_items)
    visual_player_cargo_names = [
        str(item.get("name") or "").strip()
        for item in (picker_groups.get("player_cargo") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    visual_loadout_slot = str(request.args.get("loadout_slot") or "Headgear").strip()
    if not visual_loadout_slot_meta(visual_loadout_slot):
        visual_loadout_slot = "Headgear"
    visual_loadout_category = str(request.args.get("loadout_category") or "").strip()
    if visual_loadout_category not in {item["key"] for item in VISUAL_LOADOUT_CATEGORY_FILTERS}:
        visual_loadout_category = ""
    visual_loadout_items = visual_loadout_items_for_view(picker_groups, visual_loadout_slot, visual_loadout_category)
    visual_loadout_draft = normalize_visual_loadout_draft(selected_config.get("visual_loadout_draft") if isinstance(selected_config, dict) else {})
    visual_loadout_json_text = json.dumps(build_visual_loadout_json(visual_loadout_draft), indent=2, ensure_ascii=False)
    visual_loadout_equipped_rows = visual_loadout_selected_rows(visual_loadout_draft, picker_groups)
    visual_loadout_slot_card_rows = visual_loadout_slot_cards(visual_loadout_draft, picker_groups)
    return render_template_string(
        PAGE_TEMPLATE,
        mode=mode,
        active_section=active_section,
        command_section=command_section,
        pve_tool=pve_tool,
        xml_tool=xml_tool,
        dashboard_theme=dashboard_theme,
        section_allowed=section_allowed,
        channel_label=channel_label_from_channels,
        view_title={"overview": "Operations Dashboard", "admin": "Admin Control Panel", "owner": "Owner Console"}[mode],
        auth=auth,
        refresh_seconds=DASHBOARD_REFRESH_SECONDS,
        public_url=DASHBOARD_PUBLIC_URL,
        summary=state["summary"],
        servers=state["servers"],
        shop_items=state.get("shop_items", []),
        shop_categories=state.get("shop_categories", {}),
        xml_picker_groups=picker_groups,
        ce_defaults=ce_defaults,
        airdrop_location_presets=airdrop_location_presets,
        visual_loadout_slots=VISUAL_LOADOUT_SLOTS,
        visual_loadout_cargo_slots=VISUAL_LOADOUT_CARGO_SLOTS,
        visual_loadout_categories=VISUAL_LOADOUT_CATEGORY_FILTERS,
        visual_player_cargo_names=visual_player_cargo_names,
        visual_loadout_slot=visual_loadout_slot,
        visual_loadout_category=visual_loadout_category,
        visual_loadout_items=visual_loadout_items,
        visual_loadout_draft=visual_loadout_draft,
        visual_loadout_json_text=visual_loadout_json_text,
        visual_loadout_selected_rows=visual_loadout_equipped_rows,
        visual_loadout_slot_cards=visual_loadout_slot_card_rows,
        owner_notifications=state.get("owner_notifications", []),
        generated_at=state["generated_at"],
        generated_clock=state.get("generated_clock") or "",
        admin_routes=ADMIN_ROUTES,
        all_routes=sorted(str(rule) for rule in APP.url_map.iter_rules()),
    )


def save_dashboard_admin(section: str, payload: dict[str, Any], key_name: str = "id") -> dict[str, Any]:
    data = load_store("dashboard_admin", {})
    if not isinstance(data, dict):
        data = {}
    block = data.setdefault(section, {})
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_block_data = block.setdefault(guild_id, {})
    item_id = str(payload.get(key_name) or payload.get("name") or f"{section}-{int(datetime.now(UTC).timestamp())}")
    record = dict(payload)
    record[key_name] = item_id
    record["guild_id"] = guild_id
    record["updated_at"] = datetime.now(UTC).isoformat()
    guild_block_data[item_id] = record
    save_store("dashboard_admin", data)
    return record


def delete_dashboard_admin_record(section: str, guild_id: Any, item_id: Any) -> bool:
    data = load_store("dashboard_admin", {})
    if not isinstance(data, dict):
        return False
    block = data.get(section)
    if not isinstance(block, dict):
        return False
    normalized_guild_id = normalize_guild_id(guild_id)
    guild_block_data = block.get(normalized_guild_id)
    target_id = str(item_id or "")
    if isinstance(guild_block_data, dict):
        if target_id not in guild_block_data:
            return False
        guild_block_data.pop(target_id, None)
        save_store("dashboard_admin", data)
        return True
    if isinstance(guild_block_data, list):
        before = len(guild_block_data)
        block[normalized_guild_id] = [
            record
            for record in guild_block_data
            if not (
                isinstance(record, dict)
                and str(
                    record.get("template_id")
                    or record.get("automation_id")
                    or record.get("panel_id")
                    or record.get("module")
                    or record.get("id")
                    or record.get("name")
                    or ""
                )
                == target_id
            )
        ]
        if len(block[normalized_guild_id]) == before:
            return False
        save_store("dashboard_admin", data)
        return True
    return False


def parse_embed_fields(lines: Any) -> list[dict[str, Any]]:
    fields = []
    for raw_line in str(lines or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2:
            continue
        fields.append(
            {
                "name": parts[0][:256],
                "value": parts[1][:1024],
                "inline": str(parts[2]).lower() in {"true", "yes", "1", "inline"} if len(parts) > 2 else False,
            }
        )
    return fields[:25]


def normalize_embed_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload or {})
    fields = parse_embed_fields(payload.pop("fields_lines", ""))
    payload["embed"] = {
        "title": str(payload.get("title") or "")[:256],
        "description": str(payload.get("body") or payload.get("description") or "")[:4000],
        "colour": str(payload.get("colour") or payload.get("color") or "#8d963e"),
        "author": {
            "name": str(payload.get("author_name") or ""),
            "icon_url": str(payload.get("author_icon_url") or ""),
        },
        "thumbnail_url": str(payload.get("thumbnail_url") or ""),
        "image_url": str(payload.get("image_url") or ""),
        "footer": {
            "text": str(payload.get("footer_text") or ""),
            "icon_url": str(payload.get("footer_icon_url") or ""),
        },
        "fields": fields,
    }
    payload["delivery"] = {
        "content_mode": str(payload.get("content_mode") or "embed"),
        "channel_key": str(payload.get("channel_key") or ""),
        "mention_mode": str(payload.get("mention_mode") or "none"),
        "mention_role_id": str(payload.get("mention_role_id") or ""),
        "button_label": str(payload.get("button_label") or ""),
        "button_url": str(payload.get("button_url") or ""),
    }
    payload["schedule"] = {
        "type": str(payload.get("schedule_type") or "manual"),
        "time": str(payload.get("schedule_time") or ""),
        "interval_minutes": safe_int(payload.get("interval_minutes"), 0),
        "timezone": str(payload.get("timezone") or "Europe/Dublin"),
        "event_filter": str(payload.get("event_filter") or ""),
        "event_minimum": safe_int(payload.get("event_minimum"), 0),
    }
    payload["trigger"] = {
        "type": payload["schedule"]["type"],
        "filter": payload["schedule"]["event_filter"],
        "minimum": payload["schedule"]["event_minimum"],
    }
    payload["enabled"] = bool(payload.get("enabled", True))
    return payload


@APP.get("/healthz")
def healthz():
    return jsonify({"ok": True, "generated_at": datetime.now(UTC).isoformat(), "build_commit": BUILD_COMMIT})


@APP.get("/brand-image")
def brand_image():
    if os.path.exists(BOT_IMAGE_FILE):
        return send_file(BOT_IMAGE_FILE)
    return ("", 404)


@APP.get("/brand-character")
def brand_character():
    if os.path.exists(BOT_CHARACTER_FILE):
        return send_file(BOT_CHARACTER_FILE)
    if os.path.exists(BOT_IMAGE_FILE):
        return send_file(BOT_IMAGE_FILE)
    return ("", 404)


@APP.get("/map-image/<map_key>")
def map_image(map_key: str):
    key = map_key_for(map_key)
    path = MAP_IMAGE_FILES.get(key, "")
    if path and os.path.exists(path):
        return send_file(path)
    source = DEFAULT_MAP_IMAGE_SOURCES.get(key)
    if source:
        try:
            with urllib.request.urlopen(source, timeout=8) as response:
                image_bytes = response.read()
                content_type = response.headers.get("content-type") or "image/jpeg"
        except (urllib.error.URLError, OSError):
            return redirect(source)
        return APP.response_class(image_bytes, mimetype=content_type)
    return ("", 404)


@APP.get("/item-thumb/<category>")
def item_thumb(category: str):
    label = str(category or "Item").strip()[:18] or "Item"
    colours = {
        "weapons": ("#2a3240", "#79c7dd"),
        "medical": ("#2f1620", "#ff719e"),
        "food": ("#2f2612", "#ffb45d"),
        "building": ("#1e2d1b", "#b6ff4d"),
        "tools": ("#1a2630", "#a7e5ff"),
        "clothing": ("#21182d", "#d6a2ff"),
        "containers": ("#2d2418", "#d9b779"),
        "bundles": ("#10210c", "#7cff5b"),
    }
    bg, fg = colours.get(label.lower(), ("#172016", "#d5b45f"))
    initial = re.sub(r"[^A-Za-z0-9]", "", label[:1].upper()) or "I"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
<rect width="96" height="96" rx="14" fill="{bg}"/>
<circle cx="48" cy="36" r="17" fill="{fg}" opacity=".88"/>
<rect x="22" y="58" width="52" height="12" rx="6" fill="{fg}" opacity=".55"/>
<text x="48" y="43" text-anchor="middle" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#071008">{initial}</text>
</svg>"""
    return APP.response_class(svg, mimetype="image/svg+xml")


def zone_draft_from_image_click(mode: str):
    auth, error = require_page_auth(owner_only=(mode == "owner"))
    if error:
        return error
    requested_guild_id = normalize_guild_id(request.args.get("guild_id") or auth.get("guild_id"))
    allowed_guild_ids = [str(item) for item in auth.get("guild_ids", [auth.get("guild_id")]) if item]
    if auth.get("kind") != "owner" and requested_guild_id not in allowed_guild_ids:
        requested_guild_id = normalize_guild_id(auth.get("guild_id"))
    if auth.get("kind") == "owner" and allowed_guild_ids and requested_guild_id not in allowed_guild_ids:
        requested_guild_id = allowed_guild_ids[0]
    guild_configs = load_store("guild_configs", {})
    config = guild_configs.get(requested_guild_id) if isinstance(guild_configs, dict) else {}
    if not isinstance(config, dict):
        config = {}
    map_size = map_size_for(str(config.get("server_map") or config.get("map") or "chernarus"))
    has_native_click = any(key in request.args for key in ("zone_click.x", "zone_click.y", "zone_click_x", "zone_click_y"))
    has_click = has_native_click or any(key in request.args for key in ("map_pointer_x", "map_pointer_y", "map_percent_x", "map_percent_y"))
    click_x = safe_float(request.args.get("zone_click.x") or request.args.get("zone_click_x"))
    click_y = safe_float(request.args.get("zone_click.y") or request.args.get("zone_click_y"))
    pointer_x = safe_float(request.args.get("map_pointer_x"), -1)
    pointer_y = safe_float(request.args.get("map_pointer_y"), -1)
    percent_x = safe_float(request.args.get("map_percent_x"), -1)
    percent_y = safe_float(request.args.get("map_percent_y"), -1)
    render_width = safe_float(request.args.get("map_render_width"), 0)
    render_height = safe_float(request.args.get("map_render_height"), 0)
    click_scale = max(1.0, safe_float(request.args.get("map_click_scale"), 10))
    if request.args.get("map_click_override") == "1":
        zone_x = max(0, min(map_size, safe_int(request.args.get("x") or request.args.get("draft_x"))))
        zone_z = max(0, min(map_size, safe_int(request.args.get("y") or request.args.get("z") or request.args.get("draft_z"))))
    elif has_click:
        if 0 <= percent_x <= 100 and 0 <= percent_y <= 100:
            zone_x = max(0, min(map_size, round((percent_x / 100) * map_size)))
            zone_z = max(0, min(map_size, round((1 - (percent_y / 100)) * map_size)))
        elif pointer_x >= 0 and pointer_y >= 0 and render_width > 0 and render_height > 0:
            zone_x = max(0, min(map_size, round((pointer_x / render_width) * map_size)))
            zone_z = max(0, min(map_size, round(map_size - ((pointer_y / render_height) * map_size))))
        elif has_native_click and render_width > 0 and render_height > 0 and click_x <= render_width + 2 and click_y <= render_height + 2:
            zone_x = max(0, min(map_size, round((click_x / render_width) * map_size)))
            zone_z = max(0, min(map_size, round(map_size - ((click_y / render_height) * map_size))))
        elif has_native_click and click_scale > 1:
            zone_x = max(0, min(map_size, round(click_x * click_scale)))
            zone_z = max(0, min(map_size, round(map_size - (click_y * click_scale))))
        elif has_native_click and 0 <= click_x <= map_size and 0 <= click_y <= map_size:
            zone_x = max(0, min(map_size, round(click_x)))
            zone_z = max(0, min(map_size, round(map_size - click_y)))
        else:
            zone_x = max(0, min(map_size, safe_int(request.args.get("x") or request.args.get("draft_x"))))
            zone_z = max(0, min(map_size, safe_int(request.args.get("y") or request.args.get("z") or request.args.get("draft_z"))))
    else:
        zone_x = max(0, min(map_size, safe_int(request.args.get("x") or request.args.get("draft_x"))))
        zone_z = max(0, min(map_size, safe_int(request.args.get("y") or request.args.get("z") or request.args.get("draft_z"))))
    zone_type = str(request.args.get("zone_type") or "radar").strip().lower()
    if zone_type not in {"safe", "pvp", "radar", "action", "faction", "custom"}:
        zone_type = "radar"
    shape = str(request.args.get("shape") or request.args.get("draft_shape") or "circle").strip().lower()
    if shape not in {"circle", "boundary"}:
        shape = "circle"
    radius = max(10, safe_int(request.args.get("draft_radius") or request.args.get("radius"), 250))
    colour = safe_colour(request.args.get("colour"))
    boundary_points: list[dict[str, int]] = []
    raw_boundary_points = request.args.get("boundary_points") or request.args.get("draft_points") or "[]"
    try:
        loaded_points = json.loads(raw_boundary_points)
    except (TypeError, json.JSONDecodeError):
        loaded_points = []
    if isinstance(loaded_points, list):
        for point in loaded_points:
            if not isinstance(point, dict):
                continue
            point_x = max(0, min(map_size, safe_int(point.get("x"))))
            point_z_value = next((value for value in (point.get("z"), point.get("y")) if value not in (None, "")), 0)
            point_z = max(0, min(map_size, safe_int(point_z_value)))
            boundary_points.append({"x": point_x, "y": point_z, "z": point_z})
    boundary_action = str(request.args.get("boundary_action") or "").strip().lower()
    if boundary_action == "clear":
        boundary_points = []
    elif boundary_action == "undo":
        boundary_points = boundary_points[:-1]
    elif shape == "boundary" and has_click:
        boundary_points.append({"x": zone_x, "y": zone_z, "z": zone_z})
    else:
        boundary_points = []
    if boundary_points:
        zone_x = boundary_points[-1]["x"]
        zone_z = boundary_points[-1]["z"]
    draft_points = json.dumps(boundary_points, separators=(",", ":"))
    draft_points_percent = " ".join(
        f"{((point['x'] / map_size) * 100):.2f},{(100 - ((point['z'] / map_size) * 100)):.2f}"
        for point in boundary_points
    )
    base_path = "/owner" if mode == "owner" else "/admin"
    query = urllib.parse.urlencode(
        {
            "section": "zones",
            "guild_id": requested_guild_id,
            "draft_x": zone_x,
            "draft_z": zone_z,
            "draft_type": zone_type,
            "draft_name": f"New {zone_type} zone",
            "draft_shape": shape,
            "draft_radius": radius,
            "draft_colour": colour,
            "draft_points": draft_points,
            "draft_points_percent": draft_points_percent,
            "draft_point_count": len(boundary_points),
        }
    )
    return redirect(f"{base_path}?{query}#zone-edit-form")


@APP.get("/admin/zone-draft")
def admin_zone_draft():
    return zone_draft_from_image_click("admin")


@APP.get("/owner/zone-draft")
def owner_zone_draft():
    return zone_draft_from_image_click("owner")


@APP.get("/")
def index():
    auth, error = require_page_auth()
    if error:
        return error
    return page("overview", auth)


@APP.get("/admin")
def admin():
    auth, error = require_page_auth()
    if error:
        return error
    return page("admin", auth)


@APP.get("/owner")
def owner():
    auth, error = require_page_auth(owner_only=True)
    if error:
        return error
    return page("owner", auth)


@APP.get("/login")
def login_get():
    if current_auth():
        return redirect("/")
    return login_page()


@APP.post("/login")
def login_post():
    dashboard_id = str(request.form.get("dashboard_id") or "").strip()
    password = str(request.form.get("password") or "")

    if verify_owner_login(dashboard_id, password):
        response = make_response(redirect("/owner"))
        response.set_cookie(
            "dashboard_session",
            make_owner_session_cookie(),
            httponly=True,
            secure=FORCE_HTTPS,
            samesite="Lax",
            max_age=60 * 60 * 24 * 30,
        )
        return response

    guild_id, config = find_guild_by_dashboard_id(dashboard_id)
    if not guild_id or not isinstance(config, dict):
        return login_page("Dashboard ID or password is incorrect."), 401
    if not dashboard_admin_login_enabled(config):
        return login_page("Dashboard access is currently disabled for this server."), 403
    credentials = dashboard_credentials_for_config(config)
    if not isinstance(credentials, dict) or not verify_dashboard_password(password, credentials):
        return login_page("Dashboard ID or password is incorrect."), 401
    response = make_response(redirect("/admin"))
    response.set_cookie(
        "dashboard_session",
        make_session_cookie(guild_id, credentials),
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response


@APP.get("/logout")
def logout():
    response = make_response(redirect("/login"))
    response.delete_cookie("dashboard_session")
    return response


@APP.get("/api/summary")
def api_summary():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    return jsonify(filter_state_for_auth(load_dashboard_state(), auth))


@APP.get("/api/admin")
def api_admin_index():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    routes = ADMIN_ROUTES if auth.get("kind") == "owner" else [route for route in ADMIN_ROUTES if route != "/api/admin/guild-access"]
    return jsonify({"ok": True, "routes": routes})


@APP.post("/api/admin/embed-template")
def api_embed_template():
    payload, error = require_admin()
    if error:
        return error
    save_payload = strip_dashboard_control_fields(payload)
    record = save_dashboard_admin("embed_templates", normalize_embed_payload(save_payload), "template_id")
    return dashboard_api_response(
        payload,
        {"ok": True, "template": record, "note": "Saved embed template."},
        "automations",
        "#embed-template-form",
    )


@APP.post("/api/admin/embed-template-action")
def api_embed_template_action():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    action = str(payload.get("action") or "").strip().lower()
    template_id = str(payload.get("template_id") or payload.get("id") or "").strip()
    guild_id = normalize_guild_id(payload.get("guild_id"))
    if action != "delete":
        return jsonify({"ok": False, "error": "unsupported embed template action"}), 400
    if not template_id:
        return jsonify({"ok": False, "error": "template_id is required"}), 400
    if not delete_dashboard_admin_record("embed_templates", guild_id, template_id):
        return jsonify({"ok": False, "error": "embed template not found for this server"}), 404
    return dashboard_api_response(
        payload,
        {"ok": True, "deleted": template_id, "note": "Deleted embed template."},
        "automations",
        "#embed-template-form",
    )


@APP.post("/api/admin/dashboard-record-action")
def api_dashboard_record_action():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    action = str(payload.get("action") or "").strip().lower()
    section = str(payload.get("section") or "").strip()
    record_id = str(payload.get("record_id") or payload.get("id") or payload.get("name") or "").strip()
    guild_id = normalize_guild_id(payload.get("guild_id"))
    allowed_sections = {"welcome_automations", "utility_configs", "reaction_role_panels"}
    if section not in allowed_sections:
        return jsonify({"ok": False, "error": "unsupported dashboard record section"}), 400
    if action != "delete":
        return jsonify({"ok": False, "error": "unsupported dashboard record action"}), 400
    if not record_id:
        return jsonify({"ok": False, "error": "record_id is required"}), 400
    if not delete_dashboard_admin_record(section, guild_id, record_id):
        return jsonify({"ok": False, "error": "record not found for this server"}), 404
    return dashboard_api_response(
        payload,
        {"ok": True, "deleted": record_id, "section": section, "note": "Deleted dashboard record."},
        "automations",
        "#automations",
    )


@APP.post("/api/admin/welcome-automation")
def api_welcome_automation():
    payload, error = require_admin()
    if error:
        return error
    record = save_dashboard_admin("welcome_automations", strip_dashboard_control_fields(payload), "automation_id")
    return dashboard_api_response(
        payload,
        {"ok": True, "automation": record, "note": "Saved welcome automation."},
        "automations",
        "#welcome-automation-form",
    )


@APP.post("/api/admin/utility-config")
def api_utility_config():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    module = str(payload.get("module") or payload.get("name") or "utility").strip()
    payload["module"] = module
    payload["name"] = module
    record = save_dashboard_admin("utility_configs", payload, "module")
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "utility": record, "note": "Saved utility module."},
        "automations",
        "#utility-config-form",
    )


@APP.post("/api/admin/reaction-role-panel")
def api_reaction_role_panel():
    payload, error = require_admin()
    if error:
        return error
    record = save_dashboard_admin("reaction_role_panels", strip_dashboard_control_fields(payload), "panel_id")
    return dashboard_api_response(
        payload,
        {"ok": True, "panel": record, "note": "Saved reaction role panel."},
        "automations",
        "#reaction-role-panel-form",
    )


@APP.post("/api/admin/shop-item")
def api_shop_item():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    item_name = str(payload.get("item_name") or payload.get("name") or "").strip()
    if not item_name:
        return jsonify({"ok": False, "error": "item_name is required"}), 400
    if not is_shop_sellable_item(item_name, payload.get("category")):
        return jsonify({"ok": False, "error": "that class is not a shop item"}), 400
    guild_id = normalize_guild_id(payload.get("guild_id"))
    shop = load_store("shop", {})
    if not isinstance(shop, dict):
        shop = {}
    guild_shop = shop.setdefault(guild_id, {})
    if not isinstance(guild_shop, dict) or is_shop_record(guild_shop):
        guild_shop = {}
        shop[guild_id] = guild_shop
    legacy = shop.get(item_name, {}) if isinstance(shop.get(item_name), dict) else {}
    existing = guild_shop.get(item_name, legacy) if isinstance(guild_shop.get(item_name, legacy), dict) else {}
    existing.update(
        {
            "price": safe_int(payload.get("price", existing.get("price", 0))),
            "category": str(payload.get("category") or existing.get("category") or "General"),
            "enabled": safe_bool(payload.get("enabled", existing.get("enabled", True)), True),
            "daily_limit": safe_int(payload.get("daily_limit", existing.get("daily_limit", 0))),
            "allowed_role_ids": csv_list(payload.get("allowed_role_ids", existing.get("allowed_role_ids", []))),
            "blocked_user_ids": csv_list(payload.get("blocked_user_ids", existing.get("blocked_user_ids", []))),
            "guild_id": guild_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    guild_shop[item_name] = existing
    save_store("shop", shop)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "item": {item_name: existing}, "note": "Saved shop item."},
        "shop",
        "#shop-edit-form",
    )


@APP.post("/api/admin/shop-bundle")
def api_shop_bundle():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    bundle_name = str(payload.get("bundle_name") or payload.get("item_name") or payload.get("name") or "").strip()
    if not bundle_name:
        return jsonify({"ok": False, "error": "bundle_name is required"}), 400
    bundle_items = parse_shop_bundle_items(payload.get("bundle_items") or payload.get("items"))
    if not bundle_items:
        return jsonify({"ok": False, "error": "add at least one valid bundle item"}), 400
    guild_id = normalize_guild_id(payload.get("guild_id"))
    shop = load_store("shop", {})
    if not isinstance(shop, dict):
        shop = {}
    guild_shop = shop.setdefault(guild_id, {})
    if not isinstance(guild_shop, dict) or is_shop_record(guild_shop):
        guild_shop = {}
        shop[guild_id] = guild_shop
    existing = guild_shop.get(bundle_name, {}) if isinstance(guild_shop.get(bundle_name), dict) else {}
    existing.update(
        {
            "type": "bundle",
            "price": safe_int(payload.get("price", existing.get("price", 0))),
            "category": str(payload.get("category") or existing.get("category") or "Bundles"),
            "enabled": safe_bool(payload.get("enabled", existing.get("enabled", True)), True),
            "daily_limit": safe_int(payload.get("daily_limit", existing.get("daily_limit", 0))),
            "allowed_role_ids": csv_list(payload.get("allowed_role_ids", existing.get("allowed_role_ids", []))),
            "blocked_user_ids": csv_list(payload.get("blocked_user_ids", existing.get("blocked_user_ids", []))),
            "bundle_items": bundle_items,
            "guild_id": guild_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    guild_shop[bundle_name] = existing
    save_store("shop", shop)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "bundle": {bundle_name: existing}, "note": "Saved shop bundle."},
        "shop",
        "#shop-bundle-form",
    )


@APP.post("/api/admin/theme")
def api_admin_theme():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    theme = str(payload.get("theme") or "default").strip().lower()
    if theme not in VALID_DASHBOARD_THEMES:
        return jsonify({"ok": False, "error": "unknown dashboard theme"}), 400
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    dashboard = config.setdefault("dashboard", {})
    if not isinstance(dashboard, dict):
        dashboard = {}
        config["dashboard"] = dashboard
    dashboard["theme"] = theme
    dashboard["theme_updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "theme": theme})


@APP.post("/api/admin/convert-dayz-xml")
@APP.post("/api/convert-dayz-xml")
def api_convert_dayz_xml():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    try:
        if isinstance(payload.get("editor_json"), (dict, list)):
            data = payload.get("editor_json")
        else:
            data = parse_json_payload_text(read_uploaded_or_pasted_text("dayz_json", "json_text", payload))
        result = convert_dayz_editor_json(data, payload.get("event_name"))
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return jsonify({
        "ok": True,
        "success": True,
        **result,
        "note": f"Generated XML for {result.get('object_count', 0)} object(s).",
    })


@APP.post("/api/admin/loot-tweak")
def api_loot_tweak():
    payload, error = require_admin()
    if error:
        return error
    try:
        result = tweak_types_xml(strip_dashboard_control_fields(payload or {}))
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return jsonify({"ok": True, "success": True, **result, "note": "Generated tweaked types.xml output."})


@APP.post("/api/admin/loot-bulk-tweak")
def api_loot_bulk_tweak():
    payload, error = require_admin()
    if error:
        return error
    try:
        result = bulk_tweak_types_xml(strip_dashboard_control_fields(payload or {}))
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return jsonify({
        "ok": True,
        "success": True,
        **result,
        "note": f"Bulk tweak complete: {result.get('matched', 0)} type(s), {result.get('changed', 0)} value(s) changed.",
    })


@APP.post("/api/admin/loadout-generate")
def api_loadout_generate():
    payload, error = require_admin()
    if error:
        return error
    try:
        result = build_player_loadout_xml(strip_dashboard_control_fields(payload or {}))
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return jsonify({"ok": True, "success": True, **result, "note": "Generated player loadout XML."})


@APP.post("/api/admin/vehicle-loadout-generate")
def api_vehicle_loadout_generate():
    payload, error = require_admin()
    if error:
        return error
    try:
        result = build_vehicle_spawnabletypes_xml(strip_dashboard_control_fields(payload or {}))
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return jsonify({"ok": True, "success": True, **result, "note": "Generated vehicle spawnabletypes XML."})


@APP.post("/api/admin/loadout-package")
def api_loadout_package():
    payload, error = require_admin()
    if error:
        return error
    payload = strip_dashboard_control_fields(payload or {})
    try:
        loadout_payload = parse_strict_dashboard_json(str(payload.get("loadout_json") or ""), "custom_loadout.json")
        cfg_text = str(payload.get("cfggameplay_json") or "").strip()
        cfg_payload = parse_strict_dashboard_json(cfg_text, "cfggameplay.json") if cfg_text else None
        package = build_loadout_package_zip(loadout_payload, cfg_payload)
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return send_file(
        package,
        mimetype="application/zip",
        as_attachment=True,
        download_name="MyDayZServerSettings.zip",
    )


@APP.post("/api/admin/visual-loadout-draft")
def api_visual_loadout_draft():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    slot = str(payload.get("slot") or "Headgear").strip()
    child_slot = str(payload.get("child_slot") or "").strip()
    nested_slot = str(payload.get("nested_slot") or "").strip()
    action = str(payload.get("action") or "add").strip().lower()
    item_name = safe_dayz_class(payload.get("item"))
    return_to = safe_dashboard_return(
        payload.get("return_to"),
        f"/admin?section=visual-loadout&guild_id={guild_id}&loadout_slot={urllib.parse.quote(slot or 'Headgear')}#visual-loadout",
    )
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    draft = normalize_visual_loadout_draft(config.get("visual_loadout_draft"))
    if action == "clear":
        draft = empty_visual_loadout_draft()
    elif action == "remove":
        meta = visual_loadout_slot_meta(slot)
        if slot.startswith("cargo:"):
            container = slot.split(":", 1)[1]
            index = safe_int(payload.get("index"), -1)
            rows = draft["cargo"].get(container, [])
            if 0 <= index < len(rows):
                rows.pop(index)
        elif meta and meta.get("group") == "attachments":
            draft["attachments"].pop(slot, None)
            draft["weaponAttachments"].pop(slot, None)
            draft["children"].pop(slot, None)
        elif meta:
            draft["cloth"].pop(slot, None)
            draft["children"].pop(slot, None)
    elif action == "add_child":
        if not item_name or not child_slot:
            if wants_json_response():
                return jsonify({"ok": False, "error": "item and child_slot are required"}), 400
            return redirect(return_to)
        parent_item = draft["attachments"].get(slot) or draft["cloth"].get(slot)
        if not parent_item:
            if wants_json_response():
                return jsonify({"ok": False, "error": "select a parent item before adding children"}), 400
            return redirect(return_to)
        allowed_slots = visual_compatible_child_slots(parent_item, xml_picker_groups(flat_shop_items(shop_for_guild(load_store("shop", {}), guild_id))))
        allowed = next((row for row in allowed_slots if row.get("key") == child_slot), None)
        allowed_names = {str(option.get("name") or "").lower() for option in (allowed or {}).get("items", [])}
        if not allowed or item_name.lower() not in allowed_names:
            if wants_json_response():
                return jsonify({"ok": False, "error": "that child item is not compatible with the selected parent"}), 400
            return redirect(return_to)
        parent_children = draft["children"].setdefault(slot, {})
        if allowed.get("mode") == "multi" or child_slot == "cargo":
            rows = parent_children.setdefault(child_slot, [])
            if isinstance(rows, list):
                rows.append(item_name)
            else:
                parent_children[child_slot] = [item_name]
        else:
            parent_children[child_slot] = item_name
    elif action == "add_grandchild":
        if not item_name or not child_slot or not nested_slot:
            if wants_json_response():
                return jsonify({"ok": False, "error": "item, child_slot, and nested_slot are required"}), 400
            return redirect(return_to)
        parent_children = draft["children"].setdefault(slot, {})
        selected_child = parent_children.get(child_slot)
        if not isinstance(selected_child, str) or not selected_child:
            if wants_json_response():
                return jsonify({"ok": False, "error": "select the child item before adding its children"}), 400
            return redirect(return_to)
        nested_slots = visual_compatible_child_slots(selected_child, xml_picker_groups(flat_shop_items(shop_for_guild(load_store("shop", {}), guild_id))))
        allowed = next((row for row in nested_slots if row.get("key") == nested_slot), None)
        allowed_names = {str(option.get("name") or "").lower() for option in (allowed or {}).get("items", [])}
        if not allowed or item_name.lower() not in allowed_names:
            if wants_json_response():
                return jsonify({"ok": False, "error": "that nested item is not compatible with the selected child"}), 400
            return redirect(return_to)
        nested_key = f"{child_slot}:children"
        nested_children = parent_children.setdefault(nested_key, {})
        if isinstance(nested_children, dict):
            if allowed.get("mode") == "multi" or nested_slot == "cargo":
                rows = nested_children.setdefault(nested_slot, [])
                if isinstance(rows, list):
                    rows.append(item_name)
                else:
                    nested_children[nested_slot] = [item_name]
            else:
                nested_children[nested_slot] = item_name
    elif action == "add":
        if not item_name:
            if wants_json_response():
                return jsonify({"ok": False, "error": "item is required"}), 400
            return redirect(return_to)
        meta = visual_loadout_slot_meta(slot) or VISUAL_LOADOUT_SLOTS[0]
        if str(meta.get("key", "")).startswith("cargo:"):
            container = str(meta.get("container") or "Backpack")
            draft["cargo"].setdefault(container, [])
            draft["cargo"][container].append(item_name)
        elif meta.get("group") == "attachments":
            draft["attachments"][str(meta.get("key"))] = item_name
            draft["weaponAttachments"].setdefault(str(meta.get("key")), [])
            draft["children"].pop(str(meta.get("key")), None)
        else:
            draft["cloth"][str(meta.get("key"))] = item_name
            draft["children"].pop(str(meta.get("key")), None)
    else:
        if wants_json_response():
            return jsonify({"ok": False, "error": "action must be add, add_child, add_grandchild, remove, or clear"}), 400
        return redirect(return_to)
    config["visual_loadout_draft"] = draft
    config["visual_loadout_draft_updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    sync_runtime_store("guild_configs", guild_configs)
    if wants_json_response():
        return jsonify({
            "ok": True,
            "draft": draft,
            "loadout_json": build_visual_loadout_json(draft),
            "note": "Updated visual loadout draft.",
        })
    return redirect(return_to)


def dashboard_config_from_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_configs = load_store("guild_configs", {})
    config = guild_configs.get(guild_id) if isinstance(guild_configs, dict) else None
    if not isinstance(config, dict):
        raise ValueError("No server config was found for this dashboard session.")
    return guild_id, config


@APP.post("/api/admin/xml-inject")
def api_xml_inject():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    try:
        _guild_id, config = dashboard_config_from_payload(payload)
        result = guarded_dashboard_file_injection(
            config,
            payload.get("target_path"),
            payload.get("content") or payload.get("generated_xml"),
            file_kind=str(payload.get("file_kind") or "xml"),
            label=str(payload.get("label") or "server file"),
            allow_create=safe_bool(payload.get("allow_create"), False),
        )
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return jsonify({
        "ok": True,
        "success": True,
        "result": result,
        "note": f"Uploaded {result['path']} with backup protection.",
    })


@APP.post("/api/admin/loadout-package-inject")
def api_loadout_package_inject():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    try:
        _guild_id, config = dashboard_config_from_payload(payload)
        defaults = dashboard_default_ce_paths(config)
        loadout_payload = parse_strict_dashboard_json(str(payload.get("loadout_json") or ""), "custom_loadout.json")
        if not isinstance(loadout_payload, dict):
            raise ValueError("custom_loadout.json must be a JSON object.")
        player_data = loadout_payload.get("PlayerData")
        if not isinstance(player_data, dict) or not isinstance(player_data.get("SpawnGear"), dict):
            raise ValueError("custom_loadout.json must include PlayerData.SpawnGear.")
        cfg_text = str(payload.get("cfggameplay_json") or "").strip()
        cfg_payload = parse_strict_dashboard_json(cfg_text, "cfggameplay.json") if cfg_text else None
        cfggameplay = normalize_cfggameplay_for_loadout(cfg_payload)
        loadout_text = json.dumps(loadout_payload, indent=2, ensure_ascii=False) + "\n"
        cfggameplay_text = json.dumps(cfggameplay, indent=2, ensure_ascii=False) + "\n"
        allow_create = safe_bool(payload.get("allow_create"), True)
        uploads = [
            guarded_dashboard_file_injection(
                config,
                payload.get("loadout_path") or defaults["custom_loadout_path"],
                loadout_text,
                file_kind="json",
                label="custom_loadout.json",
                allow_create=allow_create,
            ),
            guarded_dashboard_file_injection(
                config,
                payload.get("cfggameplay_path") or defaults["cfggameplay_path"],
                cfggameplay_text,
                file_kind="json",
                label="cfggameplay.json",
                allow_create=allow_create,
            ),
        ]
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return jsonify({
        "ok": True,
        "success": True,
        "uploads": uploads,
        "note": "Uploaded custom loadout and cfggameplay.json with backup protection.",
    })


@APP.post("/api/admin/dayz-converter-inject")
def api_dayz_converter_inject():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    try:
        _guild_id, config = dashboard_config_from_payload(payload)
        defaults = dashboard_default_ce_paths(config)
        allow_create = safe_bool(payload.get("allow_create"), False)
        uploads = [
            guarded_dashboard_xml_merge(
                config,
                payload.get("events_path") or defaults["events_path"],
                payload.get("events_xml"),
                root_tag="events",
                child_tag="event",
                label="events.xml",
                allow_create=allow_create,
            ),
            guarded_dashboard_xml_merge(
                config,
                payload.get("eventspawns_path") or defaults["eventspawns_path"],
                payload.get("eventspawns_xml"),
                root_tag="eventposdef",
                child_tag="event",
                label="cfgeventspawns.xml",
                allow_create=allow_create,
            ),
            guarded_dashboard_xml_merge(
                config,
                payload.get("eventgroups_path") or defaults["eventgroups_path"],
                payload.get("eventgroups_xml"),
                root_tag="eventgroupdef",
                child_tag="group",
                label="cfgeventgroups.xml",
                allow_create=allow_create,
            ),
        ]
    except ValueError as error:
        return jsonify({"ok": False, "success": False, "error": str(error)}), 400
    return jsonify({
        "ok": True,
        "success": True,
        "uploads": uploads,
        "note": "Merged DayZ event XML into live server files with backup protection.",
    })


@APP.post("/api/admin/xml-workshop")
def api_xml_workshop():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    workshop = config.setdefault("xml_workshop", {})
    if not isinstance(workshop, dict):
        workshop = {}
        config["xml_workshop"] = workshop
    recipes = workshop.setdefault("recipes", {})
    if not isinstance(recipes, dict):
        recipes = {}
        workshop["recipes"] = recipes
    kind = str(payload.get("recipe_kind") or "settings").strip().lower()
    now_text = datetime.now(UTC).isoformat()

    if kind == "settings":
        default_damage = str(payload.get("default_damage") or "pristine").strip().lower()
        if default_damage not in {"pristine", "worn", "random"}:
            default_damage = "pristine"
        quantity_mode = str(payload.get("quantity_mode") or "full").strip().lower()
        if quantity_mode not in {"full", "vanilla", "custom"}:
            quantity_mode = "full"
        record = {
            "default_damage": default_damage,
            "quantity_mode": quantity_mode,
            "full_magazines": safe_bool(payload.get("full_magazines"), False),
            "full_liquids": safe_bool(payload.get("full_liquids"), False),
            "full_meds": safe_bool(payload.get("full_meds"), False),
            "weapon_attachments": safe_bool(payload.get("weapon_attachments"), False),
            "notes": str(payload.get("notes") or "").strip()[:500],
            "updated_at": now_text,
        }
        workshop["settings"] = record
        workshop["status"] = "Loot rule draft saved. Live XML upload is disabled until injector preview/diff is added."
        save_store("guild_configs", guild_configs)
        return dashboard_api_response(
            raw_payload,
            {"ok": True, "settings": record, "note": workshop["status"]},
            "xml-workshop",
            "#xml-workshop",
        )

    target_key = {
        "airdrop": "airdrops",
        "container": "containers",
        "player_loadout": "players",
        "vehicle_loadout": "vehicles",
    }.get(kind)
    if not target_key:
        return jsonify({"ok": False, "error": "recipe_kind must be settings, airdrop, container, player_loadout, or vehicle_loadout"}), 400

    recipe_name = str(payload.get("recipe_name") or payload.get("name") or "").strip()
    if not recipe_name:
        return jsonify({"ok": False, "error": "recipe_name is required"}), 400
    items = parse_xml_workshop_items(payload.get("items"))
    if not items and kind != "airdrop":
        return jsonify({"ok": False, "error": "add at least one valid item line"}), 400
    record = {
        "id": re.sub(r"[^a-z0-9_]+", "_", recipe_name.lower()).strip("_")[:80] or f"{target_key}_{len(recipes.get(target_key, [])) + 1}",
        "name": recipe_name[:120],
        "items": items,
        "updated_at": now_text,
    }
    if kind == "container":
        record.update({
            "container_class": safe_dayz_class(payload.get("container_class")),
            "damage": str(payload.get("damage") or "pristine").strip().lower(),
            "capacity_hint": max(0, safe_int(payload.get("capacity_hint"), 0)),
        })
        if not record["container_class"]:
            return jsonify({"ok": False, "error": "container_class must be a valid DayZ classname"}), 400
        record["generated_xml"] = build_spawnable_cargo_xml(record["container_class"], items)
    elif kind == "airdrop":
        duration_mode = str(payload.get("duration_mode") or "permanent").strip().lower()
        if duration_mode not in {"permanent", "temporary"}:
            duration_mode = "permanent"
        placement_mode = str(payload.get("placement_mode") or "manual").strip().lower()
        if placement_mode not in {"manual", "random_inland", "random_military"}:
            placement_mode = "manual"
        positions = parse_airdrop_positions(payload.get("positions"))
        if not positions:
            return jsonify({"ok": False, "error": "pick at least one airdrop position on the map or use random placement"}), 400
        record.update({
            "event_name": safe_dayz_class(payload.get("event_name")) or "Static_WanderingAirdrop",
            "container_class": safe_dayz_class(payload.get("container_class")) or "StaticObj_Misc_WoodenCrate_5x",
            "positions": positions,
            "duration_mode": duration_mode,
            "temporary_restarts": max(1, safe_int(payload.get("temporary_restarts"), 2)),
            "placement_mode": placement_mode,
            "random_count": max(2, min(6, safe_int(payload.get("random_count"), 2))),
            "nominal": max(1, safe_int(payload.get("nominal"), 1)),
            "min_count": max(1, safe_int(payload.get("min_count"), 1)),
            "max_count": max(1, safe_int(payload.get("max_count"), 1)),
            "lifetime": max(1, safe_int(payload.get("lifetime"), 1800)),
            "restock": max(0, safe_int(payload.get("restock"), 3600)),
            "saferadius": max(0, safe_int(payload.get("saferadius"), 0)),
            "distanceradius": max(0, safe_int(payload.get("distanceradius"), 1000)),
            "cleanupradius": max(0, safe_int(payload.get("cleanupradius"), 1500)),
            "lootmin": max(0, safe_int(payload.get("lootmin"), 40)),
            "lootmax": max(0, safe_int(payload.get("lootmax"), 40)),
            "spawn_radius": max(1, safe_int(payload.get("spawn_radius"), 20)),
            "secondary_event": safe_dayz_class(payload.get("secondary_event")),
        })
        record["max_count"] = max(record["min_count"], record["max_count"])
        record["generated_xml"] = build_airdrop_xml_package(record)
    elif kind == "player_loadout":
        record["role_ids"] = csv_list(payload.get("role_ids"))
        record["custom_path"] = safe_custom_json_path(payload.get("custom_path"), record["id"])
        record["cfggameplay_reference"] = record["custom_path"]
        record["generated_json"] = build_player_loadout_json(record)
    elif kind == "vehicle_loadout":
        record.update({
            "vehicle_class": safe_dayz_class(payload.get("vehicle_class")),
            "vehicle_mode": str(payload.get("vehicle_mode") or "full_with_cargo").strip(),
        })
        if not record["vehicle_class"]:
            return jsonify({"ok": False, "error": "vehicle_class must be a valid DayZ classname"}), 400
        if disallowed_vehicle_part_class(record["vehicle_class"]):
            return jsonify({"ok": False, "error": "pick a whole vehicle class, not a hood, trunk, wheel, or vehicle part"}), 400
        record["generated_xml"] = build_spawnable_cargo_xml(record["vehicle_class"], items)

    collection = recipes.setdefault(target_key, [])
    if not isinstance(collection, list):
        collection = []
        recipes[target_key] = collection
    collection[:] = [item for item in collection if not isinstance(item, dict) or item.get("id") != record["id"]]
    collection.append(record)
    workshop["updated_at"] = now_text
    workshop["status"] = "Recipe draft saved. The guarded XML injector will use this later for preview and upload."
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "recipe": record, "note": workshop["status"]},
        "xml-workshop",
        "#xml-workshop",
    )


@APP.post("/api/admin/scenario-event")
def api_scenario_event():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    return_to = safe_dashboard_return(payload.get("return_to"), f"/admin?section=pve&guild_id={guild_id}#pve-workshop")
    event_type = str(payload.get("event_type") or "airdrop").strip().lower()
    if event_type == "loot_crate":
        event_type = "airdrop"
    allowed_types = {"airdrop", "animal_pack", "zombie_horde", "loot_crate", "vehicle_spawn", "vehicle_reset_point", "vehicle_reset_all", "gas_zone"}
    if event_type not in allowed_types:
        return jsonify({"ok": False, "error": "unsupported scenario event type"}), 400

    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    events = config.setdefault("scenario_events", [])
    if not isinstance(events, list):
        events = []
        config["scenario_events"] = events

    requested_event_id = safe_int(payload.get("event_id") or payload.get("id"), 0)
    existing_index = None
    existing_event: dict[str, Any] = {}
    existing_ids = []
    for index, event in enumerate(events):
        if isinstance(event, dict):
            current_id = safe_int(event.get("id"), 0)
            existing_ids.append(current_id)
            if requested_event_id > 0 and current_id == requested_event_id:
                existing_index = index
                existing_event = dict(event)
    for deleted_id in scenario_event_tombstones(config):
        deleted_int = safe_int(deleted_id, 0)
        if deleted_int > 0:
            existing_ids.append(deleted_int)
    next_event_id = max(existing_ids or [0]) + 1
    restarts = safe_int(payload.get("restarts"), 1)
    permanent = safe_bool(payload.get("permanent"), False) or restarts <= 0
    server_map = str(config.get("server_map") or config.get("map") or "chernarus")
    map_size = map_size_for(server_map)
    spawn_preset = str(payload.get("spawn_preset") or "").strip()
    if spawn_preset in {"gas_permanent", "gas_red_permanent"}:
        permanent = True
    default_preset_by_type = {
        "airdrop": "military_crate",
        "animal_pack": "bear",
        "zombie_horde": "civilian_zombie",
        "vehicle_spawn": "m3s",
        "gas_zone": "gas_temp",
    }
    preset = SCENARIO_SPAWN_PRESETS.get(spawn_preset, {})
    if event_type == "vehicle_spawn" and not preset:
        preset = SCENARIO_VEHICLE_PRESETS.get(spawn_preset, {})
    if spawn_preset not in {"custom", "custom_vehicle"}:
        preset_type = "vehicle_spawn" if event_type == "vehicle_spawn" and preset in SCENARIO_VEHICLE_PRESETS.values() else str(preset.get("event_type") or "")
        if preset_type == "loot_crate":
            preset_type = "airdrop"
        if not preset or (preset_type and preset_type != event_type):
            spawn_preset = default_preset_by_type.get(event_type, spawn_preset)
            preset = SCENARIO_SPAWN_PRESETS.get(spawn_preset, {})
            if event_type == "vehicle_spawn" and not preset:
                preset = SCENARIO_VEHICLE_PRESETS.get(spawn_preset, {})
    if preset:
        event_type = str(preset.get("event_type") or event_type)
        if event_type == "loot_crate":
            event_type = "airdrop"
    class_name = str(payload.get("class_name") or "").strip()
    if preset and spawn_preset not in {"custom", "custom_vehicle"} and preset.get("class"):
        class_name = str(preset.get("class") or class_name)
    if not class_name:
        defaults = {
            "airdrop": "WoodenCrate",
            "loot_crate": "WoodenCrate",
            "animal_pack": "Animal_UrsusArctos",
            "zombie_horde": "ZmbM_SoldierNormal",
            "vehicle_spawn": "OffroadHatchback",
            "vehicle_reset_point": "OffroadHatchback",
            "vehicle_reset_all": "ALL_VEHICLES",
            "gas_zone": "ContaminatedArea_Dynamic",
        }
        class_name = defaults[event_type]

    if event_type == "vehicle_reset_all":
        x = map_size // 2
        z = map_size // 2
        radius = int(map_size * 1.5)
    else:
        x = max(0, min(map_size, safe_int(payload.get("x"), map_size // 2)))
        z = max(0, min(map_size, safe_int(payload.get("z"), payload.get("y") or map_size // 2)))
        radius = max(0, min(30000, safe_int(payload.get("radius"), 35)))
    scene_type = str(payload.get("scene_type") or "compact_crater").strip().lower()
    scene_min_radius = {
        "compact_crater": 35,
        "helicopter_crash": 100,
        "cargo_plane_wreck": 120,
        "convoy_wreck": 80,
    }
    if scene_type not in scene_min_radius:
        scene_type = "compact_crater"
    if event_type in {"airdrop", "loot_crate"} and safe_bool(payload.get("visual_marker"), False):
        radius = max(radius, scene_min_radius[scene_type])
    if event_type == "gas_zone":
        radius = max(30, radius)
    location_name = str(payload.get("location") or "").strip()
    saved_location_name = str(payload.get("saved_location") or "").strip()
    saved_location = dashboard_airdrop_preset_location(server_map, saved_location_name)
    if saved_location and event_type != "vehicle_reset_all":
        x = max(0, min(map_size, safe_int(saved_location.get("x"), x)))
        z = max(0, min(map_size, safe_int(saved_location.get("z"), z)))
        location_name = str(saved_location.get("name") or saved_location_name or location_name).strip()
    batch_locations = [] if existing_index is not None or event_type == "vehicle_reset_all" else parse_scenario_batch_locations(payload.get("batch_locations"), map_size)
    location_records = batch_locations or [{"name": location_name or "Dashboard", "x": x, "z": z}]

    vehicle_cargo_mode = str(payload.get("vehicle_cargo_mode") or "normal_with_loot").strip()
    loot_preset = str(payload.get("loot_preset") or preset.get("loot_preset") or "none")
    if event_type == "vehicle_spawn" and vehicle_cargo_mode in {"normal_no_loot", "native_only"}:
        loot_preset = "none"
    loot = list(SCENARIO_LOOT_PRESETS.get(loot_preset, []))
    extra_loot = csv_list(payload.get("loot_items", []))
    for item in extra_loot:
        if item not in loot:
            loot.append(item)
    zombie_mix = parse_zombie_mix(payload.get("zombie_mix"))
    event_count = max(1, min(250, safe_int(payload.get("count"), safe_int(preset.get("count"), 1))))
    if event_type == "zombie_horde" and zombie_mix:
        event_count = min(250, sum(safe_int(item.get("count"), 1) for item in zombie_mix))
    if event_type == "gas_zone":
        event_count = 1
    gas_lifetime_default = 3888000 if permanent else 1800
    gas_lifetime = max(60, min(3888000, safe_int(payload.get("gas_lifetime"), gas_lifetime_default)))
    gas_particle = str(payload.get("gas_particle") or preset.get("gas_particle") or "server_default").strip().lower()
    if gas_particle in {"red", "red_debug", "debug_red"}:
        gas_particle = "debug"
    elif gas_particle in {"green", "restore", "restore_normal"}:
        gas_particle = "normal"
    elif gas_particle not in {"debug", "normal"}:
        gas_particle = "server_default"

    base_name = str(payload.get("name") or "").strip()
    label_name = str(preset.get("label") or event_type.replace("_", " ").title()).strip()
    created_events: list[dict[str, Any]] = []
    tombstones = config.get("scenario_event_tombstones")
    for location_index, location in enumerate(location_records):
        current_event_id = requested_event_id if existing_index is not None else next_event_id + location_index
        if isinstance(tombstones, dict):
            tombstones.pop(str(current_event_id), None)
        event = dict(existing_event) if existing_index is not None else {}
        loc_name = str(location.get("name") or location_name or "Dashboard").strip()
        if base_name and len(location_records) > 1:
            display_name = f"{base_name} - {loc_name}" if loc_name.lower() not in base_name.lower() else base_name
        elif base_name:
            display_name = base_name
        else:
            display_name = f"{loc_name} {label_name}" if loc_name and loc_name != "Dashboard" else f"{label_name} #{current_event_id}"
        event.update({
            "id": current_event_id,
            "name": display_name,
            "event_type": event_type,
            "location": loc_name or "Dashboard",
            "x": max(0, min(map_size, safe_int(location.get("x"), x))),
            "y": safe_int(payload.get("y"), 0),
            "z": max(0, min(map_size, safe_int(location.get("z"), z))),
            "class_name": class_name,
            "map": map_key_for(server_map),
            "preset": spawn_preset or "custom",
            "count": event_count,
            "radius": radius,
            "loot_preset": loot_preset,
            "loot": loot,
            "zombie_mix": zombie_mix if event_type == "zombie_horde" else [],
            "reset_method": str(payload.get("reset_method") or "bridge"),
            "vehicle_condition": str(payload.get("vehicle_condition") or "full").strip(),
            "vehicle_cargo_mode": vehicle_cargo_mode,
            "visual_marker": safe_bool(payload.get("visual_marker"), False),
            "marker_class": "StaticObj_Misc_WoodenCrate_5x" if safe_bool(payload.get("visual_marker"), False) else "",
            "scene_type": scene_type if event_type in {"airdrop", "loot_crate"} else "compact_crater",
            "guard_class": str(payload.get("guard_class") or "").strip(),
            "guard_count": max(0, min(80, safe_int(payload.get("guard_count"), 0))),
            "guard_radius": max(0, min(500, safe_int(payload.get("guard_radius"), 35))),
            "gas_lifetime": gas_lifetime,
            "gas_particle": gas_particle if event_type == "gas_zone" else "server_default",
            "permanent": permanent,
            "remaining_restarts": 0 if permanent else max(1, min(365, restarts)),
            "enabled": True,
            "status": "Saved - native CE XML upload requested",
            "upload_status": "waiting_for_bot_upload",
            "created_by": existing_event.get("created_by") or "dashboard",
            "created_at": existing_event.get("created_at") or datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        })
        if event_type == "vehicle_reset_all":
            event["exclude"] = csv_list(payload.get("excluded_classes", []))
        if existing_index is None:
            events.append(event)
        else:
            events[existing_index] = event
        created_events.append(event)
    save_store("guild_configs", guild_configs)
    sync_runtime_store("guild_configs", guild_configs)

    upload_started = False
    if event_type != "vehicle_reset_all" and CUSTOM_STATE_PROVIDER:
        for event in created_events:
            event["status"] = "Native CE XML upload requested"
            upload_started = schedule_runtime_scenario_xml_upload(guild_id, safe_int(event.get("id"), 0)) or upload_started
        save_store("guild_configs", guild_configs)
        sync_runtime_store("guild_configs", guild_configs)

    event = created_events[0] if created_events else {}
    g.dashboard_audit_payload = {
        "name": event.get("name"),
        "event_type": event.get("event_type"),
        "spawn_preset": event.get("preset"),
        "class_name": event.get("class_name"),
        "count": event.get("count"),
        "created_count": len(created_events),
        "x": event.get("x"),
        "z": event.get("z"),
        "radius": event.get("radius"),
        "runs": "forever" if event.get("permanent") else event.get("remaining_restarts"),
        "upload_status": event.get("upload_status"),
        "status": event.get("status"),
        "event_id": event.get("id"),
        "guild_id": guild_id,
    }
    if not wants_json_response():
        return redirect(return_to)
    count_text = f"{len(created_events)} events" if len(created_events) != 1 else "1 event"
    upload_note = "native CE XML upload requested" if upload_started else "native CE XML queued for the bot worker"
    return jsonify({
        "ok": True,
        "event": event,
        "events": created_events,
        "created_count": len(created_events),
        "updated": existing_index is not None,
        "upload_started": upload_started,
        "note": f"Saved {count_text}; {upload_note}.",
    })


@APP.get("/api/admin/scenario-event-status")
def api_scenario_event_status():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    payload = scoped_payload_for_auth(
        {
            "guild_id": request.args.get("guild_id"),
            "dashboard_mode": request.args.get("dashboard_mode"),
        },
        auth,
    )
    if payload.get("_scope_denied"):
        return jsonify({"ok": False, "error": "server is not in this admin scope"}), 403
    guild_id = normalize_guild_id(payload.get("guild_id") or auth.get("guild_id"))
    event_id = safe_int(request.args.get("event_id") or request.args.get("id"), 0)
    if event_id <= 0:
        return jsonify({"ok": False, "error": "event_id is required"}), 400
    guild_configs = load_store("guild_configs", {})
    config = guild_configs.get(guild_id) if isinstance(guild_configs, dict) else {}
    events = config.get("scenario_events", []) if isinstance(config, dict) else []
    if not isinstance(events, list):
        events = []
    for event in events:
        if isinstance(event, dict) and safe_int(event.get("id"), 0) == event_id:
            return jsonify({
                "ok": True,
                "event": event,
                "status": event.get("status") or "",
                "upload_status": event.get("upload_status") or "",
                "upload_error": event.get("upload_error") or "",
            })
    return jsonify({"ok": False, "error": "event not found"}), 404


@APP.post("/api/admin/scenario-event-action")
def api_scenario_event_action():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    event_id = safe_int(payload.get("event_id") or payload.get("id"), 0)
    action = str(payload.get("action") or "approve").strip().lower()
    return_to = safe_dashboard_return(payload.get("return_to"), f"/admin?section=pve&guild_id={guild_id}#pve-workshop")
    if action not in {"approve", "upload", "pause", "cancel", "delete"}:
        return jsonify({"ok": False, "error": "action must be upload, approve, pause, cancel, or delete"}), 400
    if event_id <= 0:
        return jsonify({"ok": False, "error": "event_id is required"}), 400

    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        return jsonify({"ok": False, "error": "guild config store is unavailable"}), 500
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    events = config.get("scenario_events", [])
    if not isinstance(events, list):
        events = []
        config["scenario_events"] = events

    for index, event in enumerate(events):
        if not isinstance(event, dict) or safe_int(event.get("id"), 0) != event_id:
            continue
        if action in {"delete", "cancel"}:
            removed = events.pop(index)
            mark_scenario_event_deleted(config, event_id, action, removed)
            config["scenario_events_cleanup_pending"] = True
            config["scenario_events_cleanup_requested_at"] = datetime.now(UTC).isoformat()
            save_store("guild_configs", guild_configs)
            sync_runtime_store("guild_configs", guild_configs)
            if not wants_json_response():
                return redirect(return_to)
            return jsonify({
                "ok": True,
                "deleted": removed,
                "cancelled": action == "cancel",
                "cleanup_queued": True,
                "upload": None,
                "note": "event removed; native CE XML cleanup is queued in the bot background worker",
            })
        event["enabled"] = action in {"approve", "upload"}
        event["status"] = {
            "approve": "Accepted / bot auto-upload queued",
            "upload": "Retry queued for native CE XML upload",
            "pause": "Paused by dashboard",
        }[action]
        if action in {"approve", "upload"}:
            event["upload_status"] = "waiting_for_bot_upload"
            event["upload_attempts"] = 0
            event.pop("xml_uploaded_at", None)
            event.pop("bridge_uploaded_at", None)
            event.pop("bridge_surface_fixed_at", None)
            event.pop("native_ce_uploaded_at", None)
            event.pop("upload_error", None)
        event["updated_at"] = datetime.now(UTC).isoformat()
        save_store("guild_configs", guild_configs)
        sync_runtime_store("guild_configs", guild_configs)

        if action in {"approve", "upload", "pause"}:
            upload_started = schedule_runtime_scenario_xml_upload(guild_id, event_id, removed=(action == "pause"))
            if upload_started:
                if action == "pause":
                    event["status"] = "Native CE XML removal starting"
                else:
                    event["status"] = "Native CE XML upload starting"
                save_store("guild_configs", guild_configs)
                sync_runtime_store("guild_configs", guild_configs)
                if not wants_json_response():
                    return redirect(return_to)
                return jsonify({"ok": True, "event": event, "upload_started": True})
        if not wants_json_response():
            return redirect(return_to)
        return jsonify({"ok": True, "event": event})

    if action in {"delete", "cancel"}:
        mark_scenario_event_deleted(config, event_id, action)
        config["scenario_events"] = [
            event
            for event in events
            if not isinstance(event, dict) or safe_int(event.get("id"), 0) != event_id
        ]
        config["scenario_events_cleanup_pending"] = True
        config["scenario_events_cleanup_requested_at"] = datetime.now(UTC).isoformat()
        save_store("guild_configs", guild_configs)
        sync_runtime_store("guild_configs", guild_configs)
        if not wants_json_response():
            return redirect(return_to)
        return jsonify({
            "ok": True,
            "missing": True,
            "deleted": None,
            "cancelled": action == "cancel",
            "note": "scenario event was already gone for this guild",
            "cleanup_queued": True,
            "upload": None,
        })

    if not wants_json_response():
        return redirect(return_to)
    return jsonify({"ok": False, "error": "scenario event not found for this guild"}), 404


@APP.post("/api/admin/economy-rule")
def api_economy_rule():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    keyword = str(payload.get("keyword") or payload.get("condition") or "").strip().lower()
    event_type = str(payload.get("event_type") or "chat_keyword").strip().lower()
    kind = str(payload.get("kind") or "reward").strip().lower()
    amount = safe_int(payload.get("amount"))
    if kind not in {"reward", "punishment"}:
        return jsonify({"ok": False, "error": "kind must be reward or punishment"}), 400
    if amount <= 0:
        return jsonify({"ok": False, "error": "amount must be above 0"}), 400
    if not keyword:
        keyword = event_type
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    rules = config.setdefault("chat_rules", [])
    if not isinstance(rules, list):
        rules = []
        config["chat_rules"] = rules
    rule = {
        "kind": kind,
        "keyword": keyword,
        "event_type": event_type,
        "amount": amount,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    rules.append(rule)
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "rule": rule, "note": "Saved economy rule."},
        "economy",
        "#economy-rule-form",
    )


@APP.post("/api/admin/link-server")
def api_link_server():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    raw_payload = request_payload() or {}
    payload = strip_dashboard_control_fields(raw_payload)
    dashboard_id = str(payload.get("dashboard_id") or "").strip()
    password = str(payload.get("password") or "")
    target_guild_id, target_config = find_guild_by_dashboard_id(dashboard_id)
    if not target_guild_id or not isinstance(target_config, dict):
        return jsonify({"ok": False, "error": "dashboard ID or password is incorrect"}), 401
    credentials = dashboard_credentials_for_config(target_config)
    if not isinstance(credentials, dict) or not verify_dashboard_password(password, credentials):
        return jsonify({"ok": False, "error": "dashboard ID or password is incorrect"}), 401
    if auth["kind"] == "owner":
        return dashboard_api_response(
            raw_payload,
            {"ok": True, "linked_guild_id": target_guild_id, "message": "owner already has access to every server"},
            "access",
            "#linked-servers",
        )
    primary_guild_id = str(auth["guild_id"])
    if target_guild_id == primary_guild_id:
        return dashboard_api_response(
            raw_payload,
            {"ok": True, "linked_guild_id": target_guild_id, "message": "server already belongs to this dashboard"},
            "access",
            "#linked-servers",
        )
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        return jsonify({"ok": False, "error": "guild config store is unavailable"}), 500
    primary_config = guild_configs.get(primary_guild_id)
    if not isinstance(primary_config, dict):
        return jsonify({"ok": False, "error": "current dashboard config is missing"}), 404
    dashboard = primary_config.setdefault("dashboard", {})
    if not isinstance(dashboard, dict):
        dashboard = {}
        primary_config["dashboard"] = dashboard
    linked = dashboard.setdefault("linked_guild_ids", [])
    if not isinstance(linked, list):
        linked = []
        dashboard["linked_guild_ids"] = linked
    if target_guild_id not in [str(item) for item in linked]:
        linked.append(target_guild_id)
    dashboard["linked_updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "linked_guild_id": target_guild_id, "server": str(target_config.get("guild_name") or target_guild_id)},
        "access",
        "#linked-servers",
    )


@APP.post("/api/admin/zone")
def api_zone():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "zone name is required"}), 400
    zone_type = str(payload.get("zone_type") or payload.get("type") or "radar").strip().lower()
    if zone_type not in {"safe", "pvp", "radar", "action", "faction", "custom"}:
        return jsonify({"ok": False, "error": "zone_type must be safe, pvp, radar, action, faction, or custom"}), 400
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    map_size = map_size_for(str(config.get("server_map") or config.get("map") or "chernarus"))
    x = max(0, min(map_size, safe_int(payload.get("x"))))
    z_value = next((value for value in (payload.get("z"), payload.get("y")) if value not in (None, "")), 0)
    z = max(0, min(map_size, safe_int(z_value)))
    y = z
    radius = max(1, safe_int(payload.get("radius"), 250))
    shape = str(payload.get("shape") or "circle").strip().lower()
    if shape not in {"circle", "boundary"}:
        return jsonify({"ok": False, "error": "shape must be circle or boundary"}), 400
    raw_boundary_points = payload.get("boundary_points", [])
    if isinstance(raw_boundary_points, str):
        try:
            raw_boundary_points = json.loads(raw_boundary_points)
        except json.JSONDecodeError:
            raw_boundary_points = []
    boundary_points = []
    if isinstance(raw_boundary_points, list):
        for point in raw_boundary_points:
            if not isinstance(point, dict):
                continue
            point_x = max(0, min(map_size, safe_int(point.get("x"))))
            point_z_value = next((value for value in (point.get("z"), point.get("y")) if value not in (None, "")), 0)
            point_z = max(0, min(map_size, safe_int(point_z_value)))
            boundary_points.append({"x": point_x, "y": point_z, "z": point_z})
    if shape == "boundary" and len(boundary_points) < 3:
        return jsonify({"ok": False, "error": "draw at least 3 boundary points before saving"}), 400
    zone_id = str(payload.get("zone_id") or payload.get("id") or name.lower().replace(" ", "-"))
    channel_key, channel_id = resolve_channel_selection(config, payload.get("channel_key"))
    role_id = str(payload.get("role_id") or "").strip()
    faction_name = str(payload.get("faction_name") or payload.get("faction") or "").strip()
    colour = safe_colour(payload.get("colour") or payload.get("color"))
    record = {
        "id": zone_id,
        "name": name,
        "zone_type": zone_type,
        "colour": colour,
        "faction_name": faction_name,
        "x": x,
        "y": y,
        "z": y,
        "radius": radius,
        "shape": shape,
        "boundary_points": boundary_points,
        "channel_key": channel_key,
        "alert_channel_id": channel_id if zone_type == "radar" else None,
        "report_channel_id": channel_id if zone_type in {"safe", "pvp", "action"} else None,
        "role_id": role_id,
        "mention_role_id": role_id,
        "triggers": csv_list(payload.get("triggers", ["detection", "login"])) if zone_type == "radar" else csv_list(payload.get("triggers", ["kill", "build", "trespass"])),
        "ignored_gamertags": csv_list(payload.get("ignored_gamertags", [])),
        "trigger_territory": str(payload.get("trigger_territory") or "inside"),
        "action": str(payload.get("action") or ("none" if zone_type == "radar" else "ban")),
        "ban_type": str(payload.get("ban_type") or "temp"),
        "ban_duration_minutes": max(1, safe_int(payload.get("ban_duration_minutes"), 1440)),
        "escalate_to_perm_after": max(1, safe_int(payload.get("escalate_to_perm_after"), 3)),
        "enabled": safe_bool(payload.get("enabled"), True),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if zone_type == "radar":
        radar_record = dict(record)
        radar_record["cooldown_seconds"] = max(1, safe_int(payload.get("cooldown_seconds"), 600))
        target = config.setdefault("radar_zones", [])
    elif zone_type in {"safe", "pvp"}:
        radar_record = dict(record)
        if zone_type == "pvp" and radar_record["action"] == "none":
            radar_record["action"] = "ban"
        target = config.setdefault("safe_zones", [])
    else:
        radar_record = dict(record)
        target = config.setdefault("zones", [])
    if not isinstance(target, list):
        target = []
        if zone_type == "radar":
            config["radar_zones"] = target
        elif zone_type in {"safe", "pvp"}:
            config["safe_zones"] = target
        else:
            config["zones"] = target
    replaced = False
    for index, zone in enumerate(target):
        if isinstance(zone, dict) and str(zone.get("id") or zone.get("name")) == zone_id:
            target[index] = radar_record
            replaced = True
            break
    if not replaced:
        target.append(radar_record)
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "zone": radar_record, "note": "Saved zone for this server."},
        "zones",
        "#zone-edit-form",
    )


@APP.post("/api/admin/zone-action")
def api_zone_action():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    action = str(payload.get("action") or "delete").strip().lower()
    if action != "delete":
        return jsonify({"ok": False, "error": "unsupported zone action"}), 400
    zone_id = str(payload.get("zone_id") or payload.get("id") or "").strip()
    name = str(payload.get("name") or "").strip()
    zone_type = str(payload.get("zone_type") or payload.get("type") or "").strip().lower()
    if not zone_id and not name:
        return jsonify({"ok": False, "error": "zone_id or name is required"}), 400
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        return jsonify({"ok": False, "error": "guild config store is unavailable"}), 500
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    list_names = ["radar_zones", "safe_zones", "zones"]
    if zone_type == "radar":
        list_names = ["radar_zones", "safe_zones", "zones"]
    elif zone_type in {"safe", "pvp"}:
        list_names = ["safe_zones", "radar_zones", "zones"]
    deleted = []
    for list_name in list_names:
        records = config.get(list_name, [])
        if not isinstance(records, list):
            continue
        kept = []
        for zone in records:
            if not isinstance(zone, dict):
                kept.append(zone)
                continue
            current_id = str(zone.get("id") or "").strip()
            current_name = str(zone.get("name") or zone.get("label") or "").strip()
            matches = (zone_id and current_id == zone_id) or (name and current_name.lower() == name.lower())
            if matches:
                deleted.append(zone)
            else:
                kept.append(zone)
        config[list_name] = kept
    if not deleted:
        return jsonify({"ok": False, "error": "zone was not found for this guild"}), 404
    config["updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "deleted": deleted, "note": "Zone deleted for this server only."},
        "zones",
        "#zones-list",
    )


MODERATION_ACTIONS = {"log", "delete", "warn", "timeout", "kick", "ban"}
MODERATION_DEFAULT_SCAM_PHRASES = [
    "free nitro",
    "steam gift",
    "crypto",
    "airdrop",
    "wallet connect",
    "verify your account",
    "giveaway",
    "discord staff",
    "support ticket",
    "click here",
    "http://",
    "https://",
]


def lines_or_csv(value: Any, default: list[str] | None = None) -> list[str]:
    if isinstance(value, list):
        candidates = value
    else:
        candidates = re.split(r"[\n,]+", str(value or ""))
    seen = set()
    cleaned = []
    for item in candidates:
        text = str(item or "").strip()
        key = text.lower()
        if text and key not in seen:
            cleaned.append(text[:180])
            seen.add(key)
    if cleaned:
        return cleaned
    return list(default or [])


def moderation_action(value: Any, default: str) -> str:
    action = str(value or default).strip().lower()
    return action if action in MODERATION_ACTIONS else default


@APP.post("/api/admin/moderation-guard")
def api_moderation_guard():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    guard_previous = config.get("moderation_guard", {})
    if not isinstance(guard_previous, dict):
        guard_previous = {}
    guard = {
        "enabled": safe_bool(payload.get("enabled"), safe_bool(guard_previous.get("enabled"), False)),
        "delete_messages": safe_bool(payload.get("delete_messages"), safe_bool(guard_previous.get("delete_messages"), True)),
        "admin_bypass": safe_bool(payload.get("admin_bypass"), safe_bool(guard_previous.get("admin_bypass"), True)),
        "staff_bypass": safe_bool(payload.get("staff_bypass"), safe_bool(guard_previous.get("staff_bypass"), True)),
        "watch_discord_invites": safe_bool(payload.get("watch_discord_invites"), safe_bool(guard_previous.get("watch_discord_invites"), True)),
        "watch_external_links": safe_bool(payload.get("watch_external_links"), safe_bool(guard_previous.get("watch_external_links"), False)),
        "watch_scam_words": safe_bool(payload.get("watch_scam_words"), safe_bool(guard_previous.get("watch_scam_words"), True)),
        "watch_blocked_phrases": safe_bool(payload.get("watch_blocked_phrases"), safe_bool(guard_previous.get("watch_blocked_phrases"), True)),
        "watch_spam": safe_bool(payload.get("watch_spam"), safe_bool(guard_previous.get("watch_spam"), True)),
        "watch_repeated_messages": safe_bool(payload.get("watch_repeated_messages"), safe_bool(guard_previous.get("watch_repeated_messages"), True)),
        "watch_mass_mentions": safe_bool(payload.get("watch_mass_mentions"), safe_bool(guard_previous.get("watch_mass_mentions"), True)),
        "spam_message_count": max(1, min(50, safe_int(payload.get("spam_message_count"), safe_int(guard_previous.get("spam_message_count"), 5)))),
        "spam_window_seconds": max(2, min(600, safe_int(payload.get("spam_window_seconds"), safe_int(guard_previous.get("spam_window_seconds"), 12)))),
        "repeat_message_count": max(2, min(20, safe_int(payload.get("repeat_message_count"), safe_int(guard_previous.get("repeat_message_count"), 3)))),
        "repeat_window_seconds": max(5, min(3600, safe_int(payload.get("repeat_window_seconds"), safe_int(guard_previous.get("repeat_window_seconds"), 30)))),
        "mass_mention_limit": max(1, min(100, safe_int(payload.get("mass_mention_limit"), safe_int(guard_previous.get("mass_mention_limit"), 5)))),
        "timeout_minutes": max(1, min(10080, safe_int(payload.get("timeout_minutes"), safe_int(guard_previous.get("timeout_minutes"), 10)))),
        "action_first": moderation_action(payload.get("action_first"), str(guard_previous.get("action_first") or "warn")),
        "action_second": moderation_action(payload.get("action_second"), str(guard_previous.get("action_second") or "timeout")),
        "action_third": moderation_action(payload.get("action_third"), str(guard_previous.get("action_third") or "timeout")),
        "invite_allowlist": lines_or_csv(payload.get("invite_allowlist"), guard_previous.get("invite_allowlist") or ["dayzwanderingbot.com"]),
        "blocked_phrases": lines_or_csv(payload.get("blocked_phrases"), guard_previous.get("blocked_phrases") or []),
        "scam_phrases": lines_or_csv(payload.get("scam_phrases"), guard_previous.get("scam_phrases") or MODERATION_DEFAULT_SCAM_PHRASES),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    config["moderation_guard"] = guard

    cheat_previous = config.get("cheat_check", {})
    if not isinstance(cheat_previous, dict):
        cheat_previous = {}
    cheat = dict(cheat_previous)
    cheat["enabled"] = safe_bool(payload.get("cheat_check_enabled"), safe_bool(cheat_previous.get("enabled"), True))
    cheat["auto_ban"] = safe_bool(payload.get("cheat_check_auto_ban"), safe_bool(cheat_previous.get("auto_ban"), False))
    cheat["clear_chain_on_teleport"] = safe_bool(payload.get("cheat_clear_chain_on_teleport"), safe_bool(cheat_previous.get("clear_chain_on_teleport"), True))
    cheat["chain_window_seconds"] = max(10, min(900, safe_int(payload.get("cheat_chain_window_seconds"), safe_int(cheat_previous.get("chain_window_seconds"), 200))))
    cheat["cluster_window_seconds"] = max(10, min(900, safe_int(payload.get("cheat_cluster_window_seconds"), safe_int(cheat_previous.get("cluster_window_seconds"), 180))))
    cheat["cluster_min_kills"] = max(2, min(20, safe_int(payload.get("cheat_cluster_min_kills"), safe_int(cheat_previous.get("cluster_min_kills"), 3))))
    cheat["cluster_max_radius"] = max(5, min(1000, safe_int(payload.get("cheat_cluster_max_radius"), safe_int(cheat_previous.get("cluster_max_radius"), 50))))
    cheat["updated_at"] = datetime.now(UTC).isoformat()
    config["cheat_check"] = cheat

    stack_previous = config.get("stack_watch", {})
    if not isinstance(stack_previous, dict):
        stack_previous = {}
    stack = dict(stack_previous)
    stack["enabled"] = safe_bool(payload.get("stack_watch_enabled"), safe_bool(stack_previous.get("enabled"), True))
    stack["objects"] = lines_or_csv(
        payload.get("stack_watch_objects"),
        stack_previous.get("objects") or ["GardenPlot", "Fireplace", "FireplaceIndoor", "OvenIndoor", "FenceKit", "WatchtowerKit", "TerritoryFlagKit"],
    )
    stack["window_seconds"] = max(10, min(1800, safe_int(payload.get("stack_watch_window_seconds"), safe_int(stack_previous.get("window_seconds"), 180))))
    stack["radius_meters"] = max(1, min(100, safe_int(payload.get("stack_watch_radius_meters"), safe_int(stack_previous.get("radius_meters"), 8))))
    stack["min_count"] = max(1, min(20, safe_int(payload.get("stack_watch_min_count"), safe_int(stack_previous.get("min_count"), 2))))
    stack["alert_each_watched"] = safe_bool(payload.get("stack_watch_alert_each"), safe_bool(stack_previous.get("alert_each_watched"), True))
    stack["channel_key"] = str(payload.get("stack_watch_channel_key") or stack_previous.get("channel_key") or "admin_logs").strip()[:80]
    stack["area_x"] = str(payload.get("stack_watch_area_x") if payload.get("stack_watch_area_x") is not None else stack_previous.get("area_x", "")).strip()[:40]
    stack["area_z"] = str(payload.get("stack_watch_area_z") if payload.get("stack_watch_area_z") is not None else stack_previous.get("area_z", "")).strip()[:40]
    stack["area_radius_meters"] = max(0, min(30000, safe_int(payload.get("stack_watch_area_radius_meters"), safe_int(stack_previous.get("area_radius_meters"), 0))))
    stack["min_height"] = str(payload.get("stack_watch_min_height") if payload.get("stack_watch_min_height") is not None else stack_previous.get("min_height", "")).strip()[:40]
    stack["max_height"] = str(payload.get("stack_watch_max_height") if payload.get("stack_watch_max_height") is not None else stack_previous.get("max_height", "")).strip()[:40]
    stack["updated_at"] = datetime.now(UTC).isoformat()
    config["stack_watch"] = stack

    config["updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    sync_runtime_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "moderation_guard": guard, "cheat_check": cheat, "stack_watch": stack, "note": "Moderation guard saved for this server only."},
        "moderation",
        "#moderation-guard",
    )


@APP.post("/api/admin/link-enforcement")
def api_link_enforcement():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    action = str(payload.get("action") or "notify").strip().lower()
    if action not in {"notify", "kick", "temp_ban", "perm_ban"}:
        return jsonify({"ok": False, "error": "action must be notify, kick, temp_ban, or perm_ban"}), 400
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    notification_key, notification_id = resolve_channel_selection(config, payload.get("notification_channel_key") or "public_shame")
    record = {
        "enabled": bool(payload.get("enabled", False)),
        "grace_minutes": max(1, safe_int(payload.get("grace_minutes"), 30)),
        "action": action,
        "temp_ban_minutes": max(1, safe_int(payload.get("temp_ban_minutes"), 60)),
        "restart_on_ban": bool(payload.get("restart_on_ban", True)),
        "notification_channel_key": notification_key,
        "notification_channel_id": notification_id,
        "reason": str(payload.get("reason") or "Discord membership and gamertag link required.")[:500],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    config["discord_link_enforcement"] = record
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "enforcement": record, "note": "Saved Discord link enforcement."},
        "moderation",
        "#link-enforcement-form",
    )


@APP.post("/api/admin/on-screen-message")
def api_on_screen_message():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    message_id = str(payload.get("message_id") or payload.get("name") or "").strip()
    if not message_id:
        return jsonify({"ok": False, "error": "message_id is required"}), 400
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    messages = config.setdefault("onscreen_messages", {})
    if not isinstance(messages, dict):
        messages = {}
        config["onscreen_messages"] = messages
    record = {
        "message_id": message_id,
        "enabled": safe_bool(payload.get("enabled"), True),
        "trigger": str(payload.get("trigger") or "scheduled"),
        "delay_seconds": max(0, safe_int(payload.get("delay_seconds"), 30)),
        "repeat_minutes": max(0, safe_int(payload.get("repeat_minutes"), 30)),
        "display_seconds": max(1, safe_int(payload.get("display_seconds"), 10)),
        "colour": str(payload.get("colour") or "#d5b45f"),
        "text": str(payload.get("text") or "")[:1000],
        "requires_restart": True,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    messages[message_id] = record
    pending = config.setdefault("pending_server_file_changes", [])
    if isinstance(pending, list) and "messages.xml" not in pending:
        pending.append("messages.xml")
    save_store("guild_configs", guild_configs)
    sync_runtime_store("guild_configs", guild_configs)
    upload_result = run_runtime_messages_xml_upload(guild_id)
    if upload_result is not None:
        messages = upload_result.get("messages") if isinstance(upload_result.get("messages"), list) else []
        if upload_result.get("ok"):
            return dashboard_api_response(
                raw_payload,
                {
                    "ok": True,
                    "message": record,
                    "note": "messages.xml uploaded. Restart the DayZ server for it to take effect.",
                    "upload": upload_result,
                },
                "server-control",
                "#on-screen-message-form",
            )
        return jsonify({
            "ok": False,
            "message": record,
            "error": "messages.xml upload failed: " + (" | ".join(str(message) for message in messages[-4:]) if messages else "no details"),
            "upload": upload_result,
        }), 502
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "message": record, "note": "messages.xml saved and queued for upload; restart required after upload"},
        "server-control",
        "#on-screen-message-form",
    )


@APP.post("/api/admin/server-control")
def api_server_control():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})

    if "restart_schedule_enabled" in payload:
        config["restart_schedule_enabled"] = safe_bool(payload.get("restart_schedule_enabled"), True)
    if "restart_interval_hours" in payload:
        config["restart_interval_hours"] = max(1, min(24, safe_int(payload.get("restart_interval_hours"), 4)))
    if "restart_start_hour" in payload:
        config["restart_start_hour"] = max(0, min(23, safe_int(payload.get("restart_start_hour"), 0)))
    if "restart_warning_minutes" in payload:
        warnings = []
        for item in csv_list(payload.get("restart_warning_minutes", [])):
            minute = safe_int(item, 0)
            if minute > 0 and minute not in warnings:
                warnings.append(minute)
        config["restart_warning_minutes"] = warnings or [30, 15, 10, 5, 1]
    if "restart_channel_key" in payload:
        restart_key, restart_id = resolve_channel_selection(config, payload.get("restart_channel_key"))
        config["restart_channel_key"] = restart_key
        config["restart_channel_id"] = restart_id

    if "base_damage_state" in payload:
        config["base_damage_state"] = "off" if str(payload.get("base_damage_state")).lower() == "off" else "on"
    if "container_damage_state" in payload:
        config["container_damage_state"] = "off" if str(payload.get("container_damage_state")).lower() == "off" else "on"
    if "damage_schedule_enabled" in payload:
        config["damage_schedule_enabled"] = safe_bool(payload.get("damage_schedule_enabled"), False)
    damage_schedule_keys = {
        "damage_schedule_enabled",
        "damage_first_date",
        "damage_time",
        "damage_timezone",
        "damage_interval_value",
        "damage_interval_unit",
        "damage_day_of_week",
        "damage_day_of_month",
    }
    if damage_schedule_keys.intersection(payload.keys()):
        interval_unit = str(payload.get("damage_interval_unit") or config.get("damage_interval_unit") or "days").strip().lower()
        if interval_unit not in {"hours", "days", "weeks", "months"}:
            interval_unit = "days"
        interval_value = max(1, min(999, safe_int(payload.get("damage_interval_value"), safe_int(config.get("damage_interval_value"), 7))))
        first_date = safe_date(payload.get("damage_first_date") or config.get("damage_first_date"))
        damage_time = safe_time(payload.get("damage_time") or config.get("damage_time") or "04:00")
        timezone = str(payload.get("damage_timezone") or config.get("damage_timezone") or "Europe/Dublin").strip()[:80]
        day_of_week = str(payload.get("damage_day_of_week") or "").strip().lower()
        if day_of_week not in {"", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}:
            day_of_week = ""
        day_of_month = safe_int(payload.get("damage_day_of_month"), 0)
        day_of_month = day_of_month if 1 <= day_of_month <= 31 else 0
        schedule = {
            "enabled": safe_bool(payload.get("damage_schedule_enabled"), bool(config.get("damage_schedule_enabled", False))),
            "base_state": str(config.get("base_damage_state") or "on"),
            "container_state": str(config.get("container_damage_state") or "on"),
            "first_date": first_date,
            "time": damage_time,
            "timezone": timezone,
            "interval_value": interval_value,
            "interval_unit": interval_unit,
            "day_of_week": day_of_week,
            "day_of_month": day_of_month,
            "next_run_local": f"{first_date}T{damage_time}:00" if first_date else "",
            "updated_at": datetime.now(UTC).isoformat(),
        }
        config["damage_schedule"] = schedule
        config["damage_first_date"] = first_date
        config["damage_time"] = damage_time
        config["damage_timezone"] = timezone
        config["damage_interval_value"] = interval_value
        config["damage_interval_unit"] = interval_unit
        config["damage_day_of_week"] = day_of_week
        config["damage_day_of_month"] = day_of_month
    if "vehicle_reset_schedule_enabled" in payload:
        config["vehicle_reset_schedule_enabled"] = safe_bool(payload.get("vehicle_reset_schedule_enabled"), False)
    if "vehicle_reset_method" in payload:
        method = str(payload.get("vehicle_reset_method") or "cfgignorelist").strip().lower()
        if method == "economy_xml":
            method = "cfgignorelist"
        config["vehicle_reset_method"] = method if method in {"cfgignorelist", "bridge"} else "cfgignorelist"
    if "vehicle_reset_restarts" in payload:
        config["vehicle_reset_restarts"] = max(1, min(365, safe_int(payload.get("vehicle_reset_restarts"), 7)))
    vehicle_schedule_keys = {
        "vehicle_reset_schedule_enabled",
        "vehicle_reset_method",
        "vehicle_reset_first_date",
        "vehicle_reset_time",
        "vehicle_reset_timezone",
        "vehicle_reset_interval_value",
        "vehicle_reset_interval_unit",
        "vehicle_reset_day_of_week",
        "vehicle_reset_day_of_month",
    }
    if vehicle_schedule_keys.intersection(payload.keys()):
        interval_unit = str(payload.get("vehicle_reset_interval_unit") or config.get("vehicle_reset_interval_unit") or "days").strip().lower()
        if interval_unit not in {"hours", "days", "weeks", "months"}:
            interval_unit = "days"
        interval_value = max(1, min(999, safe_int(payload.get("vehicle_reset_interval_value"), safe_int(config.get("vehicle_reset_interval_value"), 7))))
        first_date = safe_date(payload.get("vehicle_reset_first_date") or config.get("vehicle_reset_first_date"))
        reset_time = safe_time(payload.get("vehicle_reset_time") or config.get("vehicle_reset_time") or "04:00")
        timezone = str(payload.get("vehicle_reset_timezone") or config.get("vehicle_reset_timezone") or "Europe/Dublin").strip()[:80]
        day_of_week = str(payload.get("vehicle_reset_day_of_week") or "").strip().lower()
        if day_of_week not in {"", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}:
            day_of_week = ""
        day_of_month = safe_int(payload.get("vehicle_reset_day_of_month"), 0)
        day_of_month = day_of_month if 1 <= day_of_month <= 31 else 0
        schedule = {
            "enabled": safe_bool(payload.get("vehicle_reset_schedule_enabled"), bool(config.get("vehicle_reset_schedule_enabled", False))),
            "method": str(config.get("vehicle_reset_method") or "cfgignorelist"),
            "first_date": first_date,
            "time": reset_time,
            "timezone": timezone,
            "interval_value": interval_value,
            "interval_unit": interval_unit,
            "day_of_week": day_of_week,
            "day_of_month": day_of_month,
            "next_run_local": f"{first_date}T{reset_time}:00" if first_date else "",
            "updated_at": datetime.now(UTC).isoformat(),
        }
        config["vehicle_reset_schedule"] = schedule
        config["vehicle_reset_first_date"] = first_date
        config["vehicle_reset_time"] = reset_time
        config["vehicle_reset_timezone"] = timezone
        config["vehicle_reset_interval_value"] = interval_value
        config["vehicle_reset_interval_unit"] = interval_unit
        config["vehicle_reset_day_of_week"] = day_of_week
        config["vehicle_reset_day_of_month"] = day_of_month

    config["updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    saved_parts = []
    if {
        "restart_schedule_enabled",
        "restart_interval_hours",
        "restart_start_hour",
        "restart_warning_minutes",
        "restart_channel_key",
    }.intersection(payload.keys()):
        saved_parts.append("restart schedule")
    if {"base_damage_state", "container_damage_state"}.intersection(payload.keys()) or damage_schedule_keys.intersection(payload.keys()):
        saved_parts.append("damage settings")
    if vehicle_schedule_keys.intersection(payload.keys()):
        saved_parts.append("vehicle reset schedule")
    note = "Saved " + (", ".join(saved_parts) if saved_parts else "server control") + " for this server."
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "server_control": redact(config), "note": note},
        "server-control",
        "#server-control",
    )


@APP.post("/api/admin/faction")
def api_faction():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    name = str(payload.get("name") or payload.get("faction") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400
    factions = load_store("factions", {})
    if not isinstance(factions, dict):
        factions = {}
    block = factions.setdefault(guild_id, {})
    faction = block.get(name, {}) if isinstance(block.get(name), dict) else {}
    guild_configs = load_store("guild_configs", {})
    config = guild_configs.get(guild_id) if isinstance(guild_configs, dict) else {}
    if not isinstance(config, dict):
        config = {}
    alert_key, alert_id = resolve_channel_selection(config, payload.get("alert_channel_key") or payload.get("alert_channel_id") or faction.get("alert_channel_key") or faction.get("alert_channel_id"))
    faction.update(
        {
            "name": name,
            "leader_id": str(payload.get("leader_id") or faction.get("leader_id") or ""),
            "role_id": str(payload.get("role_id") or faction.get("role_id") or ""),
            "alert_channel_id": alert_id,
            "alert_channel_key": alert_key,
            "colour": str(payload.get("colour") or payload.get("color") or faction.get("colour") or "#8d963e"),
            "members": faction.get("members", []),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    block[name] = faction
    save_store("factions", factions)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "faction": faction, "note": "Saved faction for this server."},
        "factions",
        "#factions-radar",
    )


@APP.post("/api/admin/faction-action")
def api_faction_action():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    action = str(payload.get("action") or "delete").strip().lower()
    if action != "delete":
        return jsonify({"ok": False, "error": "unsupported faction action"}), 400
    name = str(payload.get("name") or payload.get("faction") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400
    factions = load_store("factions", {})
    if not isinstance(factions, dict):
        return jsonify({"ok": False, "error": "faction store is unavailable"}), 500
    deleted = None
    block = factions.get(guild_id)
    if isinstance(block, dict):
        for key in list(block.keys()):
            faction = block.get(key)
            faction_name = str(faction.get("name") if isinstance(faction, dict) else key)
            if str(key).lower() == name.lower() or faction_name.lower() == name.lower():
                deleted = block.pop(key)
                break
    prefix = f"{guild_id}:"
    for key in list(factions.keys()):
        if not str(key).startswith(prefix):
            continue
        faction = factions.get(key)
        faction_name = str(faction.get("name") if isinstance(faction, dict) else str(key)[len(prefix):])
        if faction_name.lower() == name.lower() or str(key)[len(prefix):].lower() == name.lower():
            deleted = factions.pop(key)
            break
    if deleted is None:
        return jsonify({"ok": False, "error": "faction was not found for this guild"}), 404
    save_store("factions", factions)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "deleted": deleted, "note": "Faction deleted for this server only."},
        "factions",
        "#factions-radar",
    )


@APP.post("/api/admin/faction-member")
def api_faction_member():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    name = str(payload.get("name") or payload.get("faction") or "").strip()
    member_id = str(payload.get("member_id") or payload.get("user_id") or "").strip()
    if not name or not member_id:
        return jsonify({"ok": False, "error": "name and member_id are required"}), 400
    factions = load_store("factions", {})
    if not isinstance(factions, dict):
        factions = {}
    faction = factions.setdefault(guild_id, {}).setdefault(name, {"name": name, "members": []})
    members = faction.setdefault("members", [])
    action = str(payload.get("action") or "add").lower()
    if action in {"remove", "delete"}:
        faction["members"] = [member for member in members if str(member.get("user_id", member) if isinstance(member, dict) else member) != member_id]
    elif member_id not in [str(member.get("user_id", member) if isinstance(member, dict) else member) for member in members]:
        members.append({"user_id": member_id, "name": str(payload.get("member_name") or ""), "added_at": datetime.now(UTC).isoformat()})
    faction["updated_at"] = datetime.now(UTC).isoformat()
    save_store("factions", factions)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "faction": faction, "note": "Updated faction member list."},
        "factions",
        "#factions-radar",
    )


@APP.post("/api/admin/member-action")
def api_member_action():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    action = str(payload.get("action") or "").strip().lower()
    member_id = str(payload.get("member_id") or payload.get("user_id") or "").strip()
    player_name = str(payload.get("player_name") or payload.get("name") or "").strip()
    reason = str(payload.get("reason") or "Dashboard member action").strip()
    if action not in {"discord_kick", "discord_ban", "dayz_temp_ban", "dayz_perm_ban"}:
        return jsonify({"ok": False, "error": "unsupported member action"}), 400
    if action in {"discord_kick", "discord_ban"}:
        ok, message = discord_member_action(guild_id, member_id, action, reason)
        status = 200 if ok else 400
        if wants_json_response() or not ok:
            return jsonify({"ok": ok, "message": message}), status
        return dashboard_api_response(
            raw_payload,
            {"ok": ok, "message": message},
            "members",
            "#members-list",
        )
    if not player_name:
        return jsonify({"ok": False, "error": "player_name is required for DayZ/Nitrado ban actions"}), 400
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    actions = config.setdefault("dashboard_member_actions", [])
    if not isinstance(actions, list):
        actions = []
        config["dashboard_member_actions"] = actions
    record = {
        "id": max([safe_int(item.get("id"), 0) for item in actions if isinstance(item, dict)] or [0]) + 1,
        "action": action,
        "player_name": player_name,
        "member_id": member_id,
        "reason": reason,
        "status": "queued",
        "created_by": "dashboard",
        "created_at": datetime.now(UTC).isoformat(),
    }
    actions.append(record)
    config["updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "action": record, "note": "queued for this guild's bot/Nitrado workflow"},
        "members",
        "#members-list",
    )


@APP.post("/api/owner/guild-action")
def api_owner_guild_action():
    payload, error = require_owner_payload()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = str(payload.get("guild_id") or "").strip()
    action = str(payload.get("action") or "leave").strip().lower()
    if not guild_id:
        return jsonify({"ok": False, "error": "guild_id is required"}), 400
    if action not in {"leave", "leave_and_remove", "show_in_owner_admin", "hide_from_owner_admin"}:
        return jsonify({"ok": False, "error": "unsupported owner guild action"}), 400

    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.get(guild_id)
    if not isinstance(config, dict):
        config = {"guild_name": f"Guild {guild_id}", "channels": {}}

    if action in {"show_in_owner_admin", "hide_from_owner_admin"}:
        dashboard = config.setdefault("dashboard", {})
        if not isinstance(dashboard, dict):
            dashboard = {}
            config["dashboard"] = dashboard
        dashboard["owner_admin_visible"] = action == "show_in_owner_admin"
        dashboard["owner_admin_visible_updated_at"] = datetime.now(UTC).isoformat()
        guild_configs[guild_id] = config
        save_store("guild_configs", guild_configs)
        return dashboard_api_response(
            raw_payload,
            {"ok": True, "guild_id": guild_id, "owner_admin_visible": dashboard["owner_admin_visible"]},
            "owner",
            "#owner-servers",
        )

    left, message = discord_bot_leave_guild(guild_id)
    if not left:
        return jsonify({"ok": False, "error": message}), 502

    if action == "leave_and_remove":
        remove_guild_dashboard_data(guild_id, config)
        return dashboard_api_response(
            raw_payload,
            {"ok": True, "message": f"{message} Dashboard data removed.", "removed": True},
            "owner",
            "#owner-servers",
        )

    config["dashboard_removed_at"] = datetime.now(UTC).isoformat()
    config["dashboard_removed_reason"] = "owner requested bot leave guild"
    guild_configs[guild_id] = config
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "message": message, "removed": False},
        "owner",
        "#owner-servers",
    )


@APP.post("/api/admin/wage")
def api_wage():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    wages = load_store("wages", {})
    if not isinstance(wages, dict):
        wages = {}
    block = wages.setdefault(guild_id, [])
    wage_id = str(payload.get("id") or payload.get("wage_id") or f"wage-{int(datetime.now(UTC).timestamp())}")
    action = str(payload.get("action") or "upsert").lower()
    if action in {"cancel", "delete", "remove"}:
        wages[guild_id] = [wage for wage in block if str(wage.get("id")) != wage_id]
        save_store("wages", wages)
        return dashboard_api_response(
            raw_payload,
            {"ok": True, "wage_id": wage_id, "active": False, "note": "Deleted wage."},
            "economy",
            "#wage-form",
        )
    record = next((wage for wage in block if str(wage.get("id")) == wage_id), None)
    is_new_record = record is None
    if record is None:
        record = {"id": wage_id}
        block.append(record)
    cadence = str(payload.get("cadence") or record.get("cadence") or "weekly")
    target_type = str(payload.get("target_type") or record.get("target_type") or "user")
    target_id = str(payload.get("target_id") or record.get("target_id") or "")
    if is_new_record or not record.get("next_pay_iso") or cadence != str(record.get("cadence") or ""):
        record["next_pay_iso"] = (datetime.now(UTC) + timedelta(seconds=wage_cadence_seconds(cadence))).isoformat()
    target_label = wage_target_label(
        {"target_type": target_type, "target_id": target_id, "target_label": record.get("target_label")},
        discord_guild_members(guild_id),
        discord_guild_roles(guild_id),
        faction_records_for_guild(load_store("factions", {}), guild_id),
    )
    record.update(
        {
            "target_type": target_type,
            "target_id": target_id,
            "target_label": target_label,
            "amount": safe_int(payload.get("amount", record.get("amount", 0))),
            "cadence": cadence,
            "active": safe_bool(payload.get("active", record.get("active", True))),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    save_store("wages", wages)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "wage": record, "note": "Saved wage."},
        "economy",
        "#wage-form",
    )


@APP.post("/api/admin/wallet-adjustment")
def api_wallet_adjustment():
    payload, error = require_admin()
    if error:
        return error
    raw_payload = payload or {}
    payload = strip_dashboard_control_fields(raw_payload)
    target_type = str(payload.get("target_type") or payload.get("wallet_type") or "user").strip().lower()
    target_id = str(payload.get("target_id") or payload.get("user_id") or payload.get("member_id") or "").strip()
    if target_type not in {"user", "faction"}:
        return jsonify({"ok": False, "error": "target_type must be user or faction"}), 400
    if not target_id:
        return jsonify({"ok": False, "error": "target is required"}), 400
    amount = safe_int(payload.get("amount"))
    account = str(payload.get("account") or "cash").strip().lower()
    if account not in {"cash", "bank"}:
        account = "cash"
    guild_id = normalize_guild_id(payload.get("guild_id"))
    wallets = load_store("wallets", {})
    if not isinstance(wallets, dict):
        wallets = {}
    if target_type == "faction":
        user_id = faction_wallet_id(target_id)
        key = f"{guild_id}:{user_id}"
        legacy = wallets.get(user_id, {}) if isinstance(wallets.get(user_id), dict) else {}
        wallet = wallets.setdefault(
            key,
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "wallet_type": "faction",
                "faction_name": target_id,
                "name": f"Faction: {target_id}",
                "cash_balance": safe_int(legacy.get("cash_balance", legacy.get("balance", 0))),
                "bank_balance": safe_int(legacy.get("bank_balance", 0)),
                "daily_transactions": safe_int(legacy.get("daily_transactions", 0)),
            },
        )
        wallet["wallet_type"] = "faction"
        wallet["faction_name"] = target_id
        wallet["name"] = f"Faction: {target_id}"
    else:
        user_id = target_id
        key = f"{guild_id}:{user_id}"
        legacy = wallets.get(user_id, {}) if isinstance(wallets.get(user_id), dict) else {}
        wallet = wallets.setdefault(
            key,
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "name": str(payload.get("name") or legacy.get("name") or ""),
                "cash_balance": safe_int(legacy.get("cash_balance", legacy.get("balance", 0))),
                "bank_balance": safe_int(legacy.get("bank_balance", 0)),
                "daily_transactions": safe_int(legacy.get("daily_transactions", 0)),
            },
        )
    wallet["guild_id"] = guild_id
    wallet["user_id"] = user_id
    ensure_wallet_accounts(wallet)
    balance_key = "bank_balance" if account == "bank" else "cash_balance"
    wallet[balance_key] = safe_int(wallet.get(balance_key)) + amount
    ensure_wallet_accounts(wallet)
    wallet["updated_at"] = datetime.now(UTC).isoformat()
    wallet.setdefault("adjustments", []).append(
        {
            "amount": amount,
            "account": account,
            "reason": str(payload.get("reason") or "dashboard adjustment"),
            "guild_id": guild_id,
            "target_type": target_type,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    save_store("wallets", wallets)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "wallet": redact(wallet), "note": "Adjusted wallet."},
        "economy",
        "#wallet-adjustment-form",
    )


@APP.post("/api/admin/guild-access")
def api_guild_access():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    if auth.get("kind") != "owner":
        return jsonify({"ok": False, "error": "owner login required"}), 403
    raw_payload = request_payload() or {}
    payload = strip_dashboard_control_fields(raw_payload)
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    access = config.setdefault("dashboard", {})
    if not isinstance(access, dict):
        access = {}
        config["dashboard"] = access
    access["enabled"] = safe_bool(payload.get("enabled"), safe_bool(access.get("enabled"), True))
    access["tier"] = str(payload.get("tier") or access.get("tier") or "owner")
    plan_status = str(payload.get("plan_status") or access.get("plan_status") or access.get("tier") or "trial").strip().lower()
    if plan_status not in {"trial", "subscription", "lifetime", "suspended", "none"}:
        plan_status = "trial"
    access["plan_status"] = plan_status
    access["trial_ends_at"] = str(payload.get("trial_ends_at") or access.get("trial_ends_at") or "")
    access["subscription_ends_at"] = str(payload.get("subscription_ends_at") or access.get("subscription_ends_at") or "")
    access["trial_notice_enabled"] = safe_bool(payload.get("trial_notice_enabled"), safe_bool(access.get("trial_notice_enabled"), True))
    access["owner_note"] = str(payload.get("owner_note") or access.get("owner_note") or "")
    role_ids = payload.get("allowed_role_ids", access.get("allowed_role_ids", []))
    user_ids = payload.get("allowed_user_ids", access.get("allowed_user_ids", []))
    if isinstance(role_ids, str):
        role_ids = [item.strip() for item in role_ids.split(",") if item.strip()]
    if isinstance(user_ids, str):
        user_ids = [item.strip() for item in user_ids.split(",") if item.strip()]
    access["allowed_role_ids"] = [str(item) for item in role_ids if item]
    access["allowed_user_ids"] = [str(item) for item in user_ids if item]
    features = payload.get("features", access.get("features", {}))
    access["features"] = features if isinstance(features, dict) else {}
    access["updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    return dashboard_api_response(
        raw_payload,
        {"ok": True, "dashboard": access, "note": "Saved dashboard access."},
        "access",
        "#access",
    )


def configure_dashboard_state_provider(provider):
    """Let bot.py provide live in-memory state while the dashboard is embedded."""
    global CUSTOM_STATE_PROVIDER
    CUSTOM_STATE_PROVIDER = provider


def run_dashboard_server():
    try:
        from waitress import serve

        serve(
            APP,
            host=DASHBOARD_HOST,
            port=DASHBOARD_PORT,
            threads=8,
            trusted_proxy="*",
            trusted_proxy_headers={
                "x-forwarded-for",
                "x-forwarded-host",
                "x-forwarded-port",
                "x-forwarded-proto",
            },
        )
    except Exception as error:
        print(f"[DASHBOARD] Waitress unavailable, falling back to Flask dev server: {error}")
        APP.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, use_reloader=False)


def start_dashboard_server():
    thread = Thread(target=run_dashboard_server, name="wandering-dashboard", daemon=True)
    thread.start()
    print(f"[DASHBOARD] Web dashboard listening on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    return thread


if __name__ == "__main__":
    run_dashboard_server()
