"""Flask dashboard for Wandering Bot.

The dashboard reads and writes the same JSON files used by ``bot.py``. It is
deliberately conservative: secrets are never rendered, and admin routes mutate
local JSON state only so the Discord bot can pick up changes on its next read.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import hashlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from threading import Thread
from typing import Any
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, make_response, redirect, render_template_string, request, send_file


DATA_ROOT = (
    os.getenv("WANDERING_DATA_DIR")
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    or os.getenv("RAILWAY_VOLUME_PATH")
    or "."
)
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
BOT_IMAGE_FILE = os.getenv("WANDERING_BOT_IMAGE_FILE", os.path.join(APP_ROOT, "wanderingbot.png"))
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
    "military_crate": {"label": "Military crate", "class": "StaticObj_Misc_WoodenCrate_5x", "event_type": "airdrop", "loot_preset": "military_high"},
    "wooden_crate": {"label": "Wooden crate", "class": "StaticObj_Misc_WoodenCrate_5x", "event_type": "loot_crate", "loot_preset": "survival"},
    "sea_chest": {"label": "Sea chest", "class": "SeaChest", "event_type": "loot_crate", "loot_preset": "survival"},
    "green_barrel": {"label": "Green barrel", "class": "Barrel_Green", "event_type": "loot_crate", "loot_preset": "survival"},
    "medical_crate": {"label": "Medical crate", "class": "WoodenCrate", "event_type": "loot_crate", "loot_preset": "medical"},
    "building_crate": {"label": "Building crate", "class": "WoodenCrate", "event_type": "loot_crate", "loot_preset": "building"},
    "food_crate": {"label": "Food crate", "class": "WoodenCrate", "event_type": "loot_crate", "loot_preset": "food"},
    "custom": {"label": "Custom classname", "class": "", "event_type": "custom"},
}
SCENARIO_LOOT_PRESETS = {
    "none": [],
    "military_high": ["M4A1", "AKM", "SVD", "PlateCarrierVest", "NVGoggles", "BandageDressing"],
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
    "dashboard_admin": "dashboard_admin.json",
    "heatmap": "heatmap.json",
    "pve_challenges": "pve_challenges.json",
    "pve_ai_campaigns": "pve_ai_campaigns.json",
    "pve_workshop_schedules": "pve_workshop_schedules.json",
    "swear_jar": "swear_jar.json",
    "longshot_records": "longshot_records.json",
    "removed_guilds": "removed_guilds.json",
}

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
    body[data-theme="forest"] { --bg: #07100b; --panel: #18251a; --panel-2: #26351f; --panel-3: #101910; --line: rgba(143, 201, 128, .34); --text: #f1f7e9; --muted: #c8d8bb; --olive: #7ca45a; --gold: #c8d46a; --accent: #9fcd73; }
    body[data-theme="amber"] { --bg: #120d06; --panel: #241b10; --panel-2: #342514; --panel-3: #1a130b; --line: rgba(225, 178, 94, .36); --text: #fff1d8; --muted: #dec8a4; --olive: #a47d3a; --gold: #e3b65f; --accent: #e3b65f; }
    body[data-theme="steel"] { --bg: #071014; --panel: #142027; --panel-2: #1f3038; --panel-3: #0d171c; --line: rgba(134, 191, 210, .34); --text: #edf7fb; --muted: #b9ced6; --olive: #5b8ea0; --gold: #79c7dd; --accent: #79c7dd; }
    body[data-theme="highland"] { --bg: #0f0d0b; --panel: #211d18; --panel-2: #302a21; --panel-3: #17130f; --line: rgba(198, 169, 121, .35); --text: #f8eddd; --muted: #d4c0a4; --olive: #8b7652; --gold: #d9b779; --accent: #d9b779; }
    body[data-theme="daylight"] { color-scheme: light; --bg: #e9edde; --panel: #fbfff5; --panel-2: #dfe8ce; --panel-3: #f4f8eb; --line: rgba(74, 98, 55, .32); --text: #182013; --muted: #4e6044; --dim: #6f7d65; --olive: #718948; --gold: #9f7c2c; --accent: #6f8f3f; }
    body[data-theme="sandstorm"] { color-scheme: light; --bg: #efe3c9; --panel: #fff7e7; --panel-2: #e6d0a3; --panel-3: #f6eddc; --line: rgba(121, 87, 43, .34); --text: #261b0f; --muted: #6b5132; --dim: #8d7652; --olive: #8d7b39; --gold: #b77c2c; --accent: #b77c2c; }
    body[data-theme="midnight"] { --bg: #05070d; --panel: #121726; --panel-2: #202940; --panel-3: #0b1020; --line: rgba(130, 153, 216, .34); --text: #f3f7ff; --muted: #bec8e4; --olive: #6878b8; --gold: #94b4ff; --accent: #94b4ff; }
    body[data-theme="bloodmoon"] { --bg: #100607; --panel: #241012; --panel-2: #38191a; --panel-3: #180a0c; --line: rgba(226, 92, 92, .34); --text: #fff0ed; --muted: #dfb7b2; --olive: #a94444; --gold: #ffb45d; --accent: #ff866d; }
    body[data-theme="radioactive"] { --bg: #061006; --panel: #10210c; --panel-2: #18300f; --panel-3: #0a1708; --line: rgba(159, 255, 74, .32); --text: #f2ffe8; --muted: #c4ddb1; --olive: #5f9b36; --gold: #b6ff4d; --accent: #7cff5b; }
    body[data-theme="arctic"] { --bg: #071014; --panel: #10212a; --panel-2: #183444; --panel-3: #0b1820; --line: rgba(164, 225, 255, .34); --text: #edfaff; --muted: #bbd9e6; --olive: #4f91a8; --gold: #a7e5ff; --accent: #6fd3ff; }
    body[data-theme="toxic"] { --bg: #0e0f05; --panel: #1b2109; --panel-2: #2a3210; --panel-3: #111606; --line: rgba(211, 231, 82, .34); --text: #fbffd9; --muted: #d3dca0; --olive: #8fa23b; --gold: #e1f25a; --accent: #c6ef3e; }
    body[data-theme="violet"] { --bg: #0c0712; --panel: #1c1228; --panel-2: #2b1b3d; --panel-3: #130c1d; --line: rgba(196, 151, 255, .32); --text: #fbf4ff; --muted: #d5c0e8; --olive: #7951aa; --gold: #d6a2ff; --accent: #b889ff; }
    body[data-theme="rose"] { --bg: #13070c; --panel: #26111a; --panel-2: #3a1a27; --panel-3: #1a0b11; --line: rgba(255, 144, 181, .34); --text: #fff2f6; --muted: #e3b8c7; --olive: #9e4c68; --gold: #ff9abc; --accent: #ff719e; }
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
    .admin-panel form { margin-top: .75rem; }
    .result { min-height: 1.25rem; }
    .owner-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
    .owner-tile { border: 1px solid var(--line); border-radius: .5rem; padding: .85rem; background: var(--panel-3); }
    .owner-tile strong { display: block; color: var(--gold); font-size: 1.35rem; }
    .table { width: 100%; border-collapse: collapse; margin-top: .75rem; }
    .table th, .table td { border-bottom: 1px solid var(--line); padding: .55rem; text-align: left; color: var(--muted); }
    .table th { color: var(--text); font-size: .8rem; text-transform: uppercase; }
    .section-nav { position: sticky; top: 5rem; z-index: 2; display: flex; flex-wrap: wrap; gap: .5rem; padding: .65rem; border: 1px solid var(--line); border-radius: .5rem; background: rgba(5, 8, 6, .9); backdrop-filter: blur(14px); }
    .mobile-section-picker { display: none; position: sticky; top: 4.5rem; z-index: 2; padding: .6rem; border: 1px solid var(--line); border-radius: .5rem; background: rgba(5, 8, 6, .92); backdrop-filter: blur(14px); }
    .mobile-section-picker label { font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
    .section-panel { min-width: 0; padding: 1rem; scroll-margin-top: 8rem; }
    body[data-section="leaderboards"] { --accent: #f1c40f; }
    body[data-section="automations"] { --accent: #6fd3ff; }
    body[data-section="factions"] { --accent: #d6a2ff; }
    body[data-section="zones"] { --accent: #75d89a; }
    body[data-section="members"] { --accent: #ff9abc; }
    body[data-section="heatmaps"] { --accent: #ff866d; }
    body[data-section="pve"] { --accent: #e1f25a; }
    body[data-section="economy"] { --accent: #d5b45f; }
    body[data-section="shop"] { --accent: #79c7dd; }
    body[data-section="xml-workshop"] { --accent: #7cff5b; }
    body[data-section="server-rules"] { --accent: #ff9f43; }
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
    .item-table button { padding: .35rem .5rem; font-size: .85rem; }
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
    .item-picker { border: 1px solid var(--line); border-radius: .5rem; padding: .65rem; background: #070b08; display: grid; gap: .55rem; min-width: 0; overflow: hidden; }
    .item-picker label { min-width: 0; }
    .item-picker-controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr)); gap: .45rem; align-items: end; min-width: 0; }
    .item-picker-controls button { align-self: end; min-width: 5rem; }
    .item-picker-preview { display: flex; gap: .5rem; align-items: center; color: var(--muted); min-width: 0; }
    .shop-picker-list { max-height: 18rem; overflow: auto; border: 1px solid var(--line); border-radius: .5rem; padding: .5rem; background: #070b08; display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: .35rem; }
    .shop-picker-card { display: grid; grid-template-columns: 2rem minmax(0, 1fr); gap: .45rem; align-items: center; text-align: left; background: #0a0f0b; border: 1px solid var(--line); border-radius: .45rem; padding: .35rem; color: var(--muted); min-width: 0; }
    .shop-picker-card img, .item-thumb { width: 2rem; height: 2rem; border-radius: .4rem; object-fit: cover; border: 1px solid var(--line); background: var(--panel-2); }
    .shop-picker-card strong { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .shop-picker-card span { color: var(--muted); font-size: .78rem; }
    .item-table .item-name-cell { display: flex; align-items: center; gap: .55rem; min-width: 0; }
    .item-table .item-name-cell strong { overflow-wrap: anywhere; }
    .loadout-builder { display: grid; grid-template-columns: minmax(16rem, .75fr) minmax(16rem, 1fr); gap: .75rem; }
    .loadout-slots { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .45rem; }
    .loadout-slot { border: 1px dashed var(--line); border-radius: 999px; padding: .45rem .6rem; background: #070b08; color: var(--muted); font-size: .85rem; }
    .loadout-slot.active { border-style: solid; border-color: var(--gold); color: var(--text); background: rgba(213,180,95,.12); }
    .zone-builder-form { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .zone-tools { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; }
    .zone-tool-actions { display: flex; flex-wrap: wrap; align-items: end; gap: .5rem; }
    .zone-map { position: relative; width: 100%; min-height: 34rem; aspect-ratio: 1 / .62; border: 1px solid var(--line); border-radius: .5rem; overflow: hidden; background:
      var(--map-image),
      radial-gradient(circle at 22% 68%, rgba(213,180,95,.18), transparent 10%),
      radial-gradient(circle at 38% 38%, rgba(141,150,62,.34), transparent 18%),
      radial-gradient(circle at 62% 55%, rgba(52,152,219,.12), transparent 13%),
      linear-gradient(135deg, #182315, #071008 68%);
      background-size: cover, auto, auto, auto, auto;
      background-position: center, center, center, center, center;
      cursor: crosshair;
    }
    .zone-map::before { content: ""; position: absolute; inset: 0; background-image: linear-gradient(rgba(243,236,217,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(243,236,217,.08) 1px, transparent 1px); background-size: 12.5% 12.5%; }
    .zone-map::after { content: "Click map to set X/Y"; position: absolute; right: .75rem; bottom: .65rem; color: var(--dim); font-size: .85rem; background: rgba(5,8,6,.72); border: 1px solid var(--line); border-radius: .35rem; padding: .3rem .45rem; }
    .zone-dot { position: absolute; transform: translate(-50%, -50%); border: 2px solid var(--zone-colour, var(--gold)); background: color-mix(in srgb, var(--zone-colour, var(--gold)) 26%, transparent); border-radius: 50%; display: grid; place-items: center; color: var(--text); font-size: .75rem; font-weight: 900; pointer-events: none; box-shadow: 0 0 0 2px rgba(5,8,6,.3), 0 0 18px color-mix(in srgb, var(--zone-colour, var(--gold)) 42%, transparent); }
    .zone-dot.safe { --zone-colour: #75d89a; }
    .zone-dot.pvp { --zone-colour: #ed3853; }
    .zone-dot.radar { --zone-colour: #d5b45f; }
    .zone-dot.action { --zone-colour: #ff9f43; }
    .zone-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; }
    .zone-cursor { position: absolute; transform: translate(-50%, -50%); width: 1.2rem; height: 1.2rem; border: 2px solid #fff; border-radius: 50%; box-shadow: 0 0 0 .45rem rgba(213,180,95,.26); background: var(--gold); pointer-events: none; z-index: 2; }
    .zone-preview-circle { position: absolute; transform: translate(-50%, -50%); border: 2px solid var(--zone-colour, var(--accent)); border-radius: 50%; background: color-mix(in srgb, var(--zone-colour, var(--accent)) 18%, transparent); pointer-events: none; z-index: 1; }
    .zone-boundary-layer { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; }
    .zone-boundary-layer polygon { fill: color-mix(in srgb, var(--zone-colour, var(--accent)) 18%, transparent); stroke: var(--zone-colour, var(--accent)); stroke-width: 2.5; }
    .zone-boundary-layer polyline { fill: none; stroke: var(--zone-colour, var(--accent)); stroke-width: 2.5; stroke-dasharray: 7 5; }
    .zone-boundary-point { position: absolute; transform: translate(-50%, -50%); width: .9rem; height: .9rem; border: 2px solid var(--bg); border-radius: 50%; background: var(--zone-colour, var(--accent)); pointer-events: none; z-index: 2; }
    .zone-swatch { display: inline-block; width: .85rem; height: .85rem; border-radius: 50%; border: 1px solid rgba(255,255,255,.55); background: var(--zone-colour, var(--gold)); vertical-align: middle; margin-right: .35rem; }
    .map-missing { position: absolute; left: .75rem; top: .75rem; z-index: 2; max-width: min(34rem, calc(100% - 1.5rem)); border: 1px solid rgba(237,56,83,.4); border-radius: .45rem; background: rgba(5,8,6,.84); color: #ffd8df; padding: .55rem .7rem; font-size: .9rem; }
    .trial-notice { display: flex; align-items: center; justify-content: space-between; gap: .75rem; border: 1px solid rgba(213,180,95,.45); border-radius: .5rem; padding: .7rem .85rem; background: rgba(213,180,95,.13); color: var(--text); }
    .trial-notice span { color: var(--muted); }
    .map-readout { margin-top: .4rem; color: var(--gold); font-size: .9rem; }
    .help-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem; }
    .help-card { border: 1px solid var(--line); border-radius: .5rem; padding: 1rem; background: #070b08; }
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
      .hero, .grid, .columns, .stats, form, .zone-builder-form, .zone-options, .zone-tools, .route-list, .panel-grid, .owner-grid, .option-grid, .leader-row, .leader-category-grid, .check-grid, .mini-grid, .heat-row, .category-grid, .help-grid, .owner-server-card { grid-template-columns: 1fr; }
      .owner-server-actions { justify-content: flex-start; }
      .zone-map { min-height: 22rem; }
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
      p, li, .tool-note { font-size: .92rem; }
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
      .zone-map { min-height: 18rem; aspect-ratio: 1 / .86; }
      .zone-map::after { font-size: .76rem; right: .45rem; bottom: .45rem; }
      .map-missing { font-size: .8rem; }
      .leader-row { gap: .4rem; }
      .leader-name { white-space: normal; }
      .item-table { min-width: 40rem; }
      .item-table th, .item-table td { padding: .55rem .5rem; font-size: .88rem; }
      .item-picker-controls { grid-template-columns: 1fr; }
      .table-scroll .item-table { min-width: 40rem; }
      .category-link, .option-card, .help-card { padding: .75rem; }
      .trial-notice { align-items: stretch; flex-direction: column; }
    }
    @media (max-width: 430px) {
      .scenario-actions, .owner-server-actions { grid-template-columns: 1fr; }
      .item-table { min-width: 36rem; }
      .table-scroll .item-table { min-width: 36rem; }
      .zone-map { min-height: 15rem; }
      .pill { font-size: .76rem; }
    }
  </style>
</head>
<body data-theme="{{ dashboard_theme if dashboard_theme != 'default' else '' }}">
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
      <a href="/logout">Logout</a>
    </nav>
    <div class="theme-picker" aria-label="Theme picker">
      <label>Theme
        <select data-theme-select>
          <option value="default">Wandering</option>
          <option value="forest">Forest</option>
          <option value="amber">Amber</option>
          <option value="steel">Steel</option>
          <option value="highland">Highland</option>
          <option value="daylight">Daylight</option>
          <option value="sandstorm">Sandstorm</option>
          <option value="midnight">Midnight</option>
          <option value="bloodmoon">Blood Moon</option>
          <option value="radioactive">Radioactive</option>
          <option value="arctic">Arctic</option>
          <option value="toxic">Toxic</option>
          <option value="violet">Violet</option>
          <option value="rose">Rose</option>
        </select>
      </label>
      <button type="button" data-theme-choice="default" title="Wandering"></button>
      <button type="button" data-theme-choice="forest" title="Forest"></button>
      <button type="button" data-theme-choice="amber" title="Amber"></button>
      <button type="button" data-theme-choice="steel" title="Steel"></button>
      <button type="button" data-theme-choice="highland" title="Highland"></button>
      <button type="button" data-theme-choice="daylight" title="Daylight"></button>
      <button type="button" data-theme-choice="sandstorm" title="Sandstorm"></button>
      <button type="button" data-theme-choice="midnight" title="Midnight"></button>
      <button type="button" data-theme-choice="bloodmoon" title="Blood Moon"></button>
      <button type="button" data-theme-choice="radioactive" title="Radioactive"></button>
      <button type="button" data-theme-choice="arctic" title="Arctic"></button>
      <button type="button" data-theme-choice="toxic" title="Toxic"></button>
      <button type="button" data-theme-choice="violet" title="Violet"></button>
      <button type="button" data-theme-choice="rose" title="Rose"></button>
    </div>
  </header>
  <main>
    <section class="hero">
      <div>
        <p class="muted">{{ generated_at }}</p>
        <h1>{{ view_title }}</h1>
        <p class="muted">Live readout for {{ auth.label }}. Server dashboards are scoped by private ID/password and cannot access another guild.</p>
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
        <a class="server-tab {{ 'active' if server and item.guild_id == server.guild_id else '' }}" href="/admin?guild_id={{ item.guild_id }}">{{ item.guild_name }} · {{ item.map|upper }}</a>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    <section class="section-nav" aria-label="Dashboard sections">
      <a class="tab-link" href="/admin?section=overview{{ server_qs }}">Overview</a>
      {% if servers|length > 1 %}<a class="tab-link" href="/admin?section=overview{{ server_qs }}#servers">Servers</a>{% endif %}
      {% if section_allowed('leaderboards') %}<a class="tab-link" href="/admin?section=leaderboards{{ server_qs }}">Leaderboards</a>{% endif %}
      {% if section_allowed('automations') %}<a class="tab-link" href="/admin?section=automations{{ server_qs }}">Embeds & Welcome</a>{% endif %}
      {% if section_allowed('factions') %}<a class="tab-link" href="/admin?section=factions{{ server_qs }}">Factions</a>{% endif %}
      {% if section_allowed('zones') %}<a class="tab-link" href="/admin?section=zones{{ server_qs }}">Zones</a>{% endif %}
      {% if section_allowed('members') %}<a class="tab-link" href="/admin?section=members{{ server_qs }}">Members</a>{% endif %}
      {% if section_allowed('heatmaps') %}<a class="tab-link" href="/admin?section=heatmaps{{ server_qs }}">Heatmaps</a>{% endif %}
      {% if section_allowed('pve') %}<a class="tab-link" href="/admin?section=pve{{ server_qs }}">PVE & Workshop</a>{% endif %}
      {% if section_allowed('economy') %}<a class="tab-link" href="/admin?section=economy{{ server_qs }}">Economy</a>{% endif %}
      {% if section_allowed('shop') %}<a class="tab-link" href="/admin?section=shop{{ server_qs }}">Manage Shop</a>{% endif %}
      {% if section_allowed('xml-workshop') %}<a class="tab-link" href="/admin?section=xml-workshop{{ server_qs }}">XML Workshop</a>{% endif %}
      {% if section_allowed('server-rules') %}<a class="tab-link" href="/admin?section=server-rules{{ server_qs }}">Server Rules</a>{% endif %}
      {% if section_allowed('server-control') %}<a class="tab-link" href="/admin?section=server-control{{ server_qs }}">Server Control</a>{% endif %}
      <a class="tab-link" href="/admin?section=help{{ server_qs }}">Help</a>
      {% if auth.kind == "owner" %}<a class="tab-link" href="/owner?section=owner">Owner Control</a>{% endif %}
      {% if auth.kind == "owner" and mode == "owner" %}<a class="tab-link" href="/owner?section=access{{ server_qs }}">Access</a>{% endif %}
    </section>
    <section class="mobile-section-picker" aria-label="Dashboard section picker">
      <label>
        Jump to section
        <select onchange="if (this.value) window.location.href = this.value;">
          <option value="/admin?section=overview{{ server_qs }}" {{ 'selected' if active_section == 'overview' else '' }}>Overview</option>
          {% if servers|length > 1 %}<option value="/admin?section=overview{{ server_qs }}#servers">Servers</option>{% endif %}
          {% if section_allowed('leaderboards') %}<option value="/admin?section=leaderboards{{ server_qs }}" {{ 'selected' if active_section == 'leaderboards' else '' }}>Leaderboards</option>{% endif %}
          {% if section_allowed('automations') %}<option value="/admin?section=automations{{ server_qs }}" {{ 'selected' if active_section == 'automations' else '' }}>Embeds & Welcome</option>{% endif %}
          {% if section_allowed('factions') %}<option value="/admin?section=factions{{ server_qs }}" {{ 'selected' if active_section == 'factions' else '' }}>Factions</option>{% endif %}
          {% if section_allowed('zones') %}<option value="/admin?section=zones{{ server_qs }}" {{ 'selected' if active_section == 'zones' else '' }}>Zones</option>{% endif %}
          {% if section_allowed('members') %}<option value="/admin?section=members{{ server_qs }}" {{ 'selected' if active_section == 'members' else '' }}>Members</option>{% endif %}
          {% if section_allowed('heatmaps') %}<option value="/admin?section=heatmaps{{ server_qs }}" {{ 'selected' if active_section == 'heatmaps' else '' }}>Heatmaps</option>{% endif %}
          {% if section_allowed('pve') %}<option value="/admin?section=pve{{ server_qs }}" {{ 'selected' if active_section == 'pve' else '' }}>PVE & Workshop</option>{% endif %}
          {% if section_allowed('economy') %}<option value="/admin?section=economy{{ server_qs }}" {{ 'selected' if active_section == 'economy' else '' }}>Economy</option>{% endif %}
          {% if section_allowed('shop') %}<option value="/admin?section=shop{{ server_qs }}" {{ 'selected' if active_section == 'shop' else '' }}>Manage Shop</option>{% endif %}
          {% if section_allowed('xml-workshop') %}<option value="/admin?section=xml-workshop{{ server_qs }}" {{ 'selected' if active_section == 'xml-workshop' else '' }}>XML Workshop</option>{% endif %}
          {% if section_allowed('server-rules') %}<option value="/admin?section=server-rules{{ server_qs }}" {{ 'selected' if active_section == 'server-rules' else '' }}>Server Rules</option>{% endif %}
          {% if section_allowed('server-control') %}<option value="/admin?section=server-control{{ server_qs }}" {{ 'selected' if active_section == 'server-control' else '' }}>Server Control</option>{% endif %}
          <option value="/admin?section=help{{ server_qs }}" {{ 'selected' if active_section == 'help' else '' }}>Help</option>
          {% if auth.kind == "owner" %}<option value="/owner?section=owner" {{ 'selected' if active_section == 'owner' else '' }}>Owner Control</option>{% endif %}
          {% if auth.kind == "owner" and mode == "owner" %}<option value="/owner?section=access{{ server_qs }}" {{ 'selected' if active_section == 'access' else '' }}>Access</option>{% endif %}
        </select>
      </label>
    </section>

    {% if active_section == "overview" %}
    <section class="category-grid" aria-label="Main categories">
      <a class="category-link" href="/admin?section=leaderboards{{ server_qs }}"><strong>Leaderboard</strong><span>Live kills, deaths, builds and rankings.</span></a>
      <a class="category-link" href="/admin?section=automations{{ server_qs }}"><strong>Embeds & Welcome</strong><span>Auto messages, welcomes and reaction roles.</span></a>
      <a class="category-link" href="/admin?section=factions{{ server_qs }}"><strong>Factions</strong><span>Faction setup, leaders, roles and members.</span></a>
      <a class="category-link" href="/admin?section=zones{{ server_qs }}"><strong>Zones</strong><span>Safe zones, PVP zones, radar pings and ban/action rules.</span></a>
      <a class="category-link" href="/admin?section=members{{ server_qs }}"><strong>Members</strong><span>Server player list, Discord IDs, kick and ban actions.</span></a>
      <a class="category-link" href="/admin?section=economy{{ server_qs }}"><strong>Economy</strong><span>Wallets, wages, rewards and punishments.</span></a>
      <a class="category-link" href="/admin?section=shop{{ server_qs }}"><strong>Manage Shop</strong><span>Items, prices, limits, availability and role restrictions.</span></a>
      <a class="category-link" href="/admin?section=xml-workshop{{ server_qs }}"><strong>XML Workshop</strong><span>Loot quality, filled bags, loadouts and vehicle cargo recipes.</span></a>
      <a class="category-link" href="/admin?section=server-rules{{ server_qs }}"><strong>Server Rules</strong><span>Discord link enforcement, Nitrado bans and on-screen server messages.</span></a>
      <a class="category-link" href="/admin?section=server-control{{ server_qs }}"><strong>Server Control</strong><span>Restart schedules and base/container damage toggles.</span></a>
      <a class="category-link" href="/admin?section=pve{{ server_qs }}"><strong>PVE & Workshop</strong><span>Quest board, campaigns and workshop status.</span></a>
      <a class="category-link" href="/admin?section=heatmaps{{ server_qs }}"><strong>Heatmaps</strong><span>PVP, PVE, infected, animal and build activity.</span></a>
      <a class="category-link" href="/admin?section=help{{ server_qs }}"><strong>Help</strong><span>Walkthroughs, setup notes and what each control does.</span></a>
      {% if auth.kind == "owner" and mode == "owner" %}<a class="category-link" href="/owner?section=access{{ server_qs }}"><strong>Access</strong><span>Credentials, linked servers and enabled modules.</span></a>{% endif %}
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
                <form class="admin-form inline-action" data-route="/api/owner/guild-action">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="action" value="hide_from_owner_admin">
                  <button type="submit">Hide From My Admin</button> <span class="result muted"></span>
                </form>
                {% else %}
                <form class="admin-form inline-action" data-route="/api/owner/guild-action">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="action" value="show_in_owner_admin">
                  <button type="submit">Show In My Admin</button> <span class="result muted"></span>
                </form>
                {% endif %}
                {% if not owned.dashboard_access.enabled %}
                <form class="admin-form inline-action" data-route="/api/admin/guild-access">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="enabled" value="true">
                  <input class="hidden-field" name="tier" value="owner">
                  <input class="hidden-field" name="plan_status" value="lifetime">
                  <button type="submit">Enable Admin Access</button> <span class="result muted"></span>
                </form>
                {% else %}
                <form class="admin-form inline-action" data-route="/api/admin/guild-access" data-confirm="This locks normal admin dashboard login for {{ owned.guild_name }}. Your owner login will still work. Continue?">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="enabled" value="false">
                  <input class="hidden-field" name="tier" value="{{ owned.dashboard_access.tier or 'none' }}">
                  <input class="hidden-field" name="plan_status" value="{{ owned.dashboard_access.plan_status or 'none' }}">
                  <button type="submit">Lock Admin Access</button> <span class="result muted"></span>
                </form>
                {% endif %}
                <form class="admin-form inline-action" data-route="/api/owner/guild-action" data-confirm="This will make the bot leave {{ owned.guild_name }}. Continue?">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
                  <input class="hidden-field" name="action" value="leave">
                  <button type="submit">Leave Discord</button> <span class="result muted"></span>
                </form>
                <form class="admin-form inline-action" data-route="/api/owner/guild-action" data-confirm="This will make the bot leave {{ owned.guild_name }} and remove this guild from dashboard data. Continue?">
                  <input class="hidden-field" name="guild_id" value="{{ owned.guild_id }}">
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
        <datalist id="xml-item-options">
          {% for item in (server.shop_items if server else []) %}<option value="{{ item.name }}">{{ item.category }}</option>{% endfor %}
        </datalist>
        <article class="admin-panel full" data-types-tool>
          <h3>Types XML Tools</h3>
          <p class="tool-note">Paste a types.xml file, choose a tool, then generate a safe edited copy. This does not overwrite the server file until the guarded uploader is used.</p>
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
          <h3>Embed & Timed Message Builder</h3>
          <form class="admin-form" data-route="/api/admin/embed-template">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Purpose
              <select name="name">
                <option value="timed-reminder">Timed reminder</option>
                <option value="server-rules">Server rules</option>
                <option value="restart-warning">Restart warning</option>
                <option value="event-announcement">Event announcement</option>
                <option value="shop-notice">Shop notice</option>
                <option value="staff-alert">Staff alert</option>
                <option value="giveaway">Giveaway</option>
                <option value="level-up">Level up notice</option>
                <option value="server-stats">Server stats panel</option>
                <option value="birthday">Birthday message</option>
                <option value="moderation">Moderation message</option>
                <option value="custom-command">Custom command response</option>
                <option value="custom-message">Custom message</option>
              </select>
            </label>
            <label>Message key <input name="template_id" value="server-rules" placeholder="unique name for this embed"></label>
            <label>Message type
              <select name="content_mode"><option value="embed">Embed</option><option value="text">Plain text</option><option value="both">Text + embed</option></select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}">{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Title <input name="title" value="Server Rules"></label>
            <label>Colour <input name="colour" type="color" value="#8d963e"></label>
            <label>Author name <input name="author_name" placeholder="optional"></label>
            <label>Author icon URL <input name="author_icon_url" placeholder="https://..."></label>
            <label>Thumbnail URL <input name="thumbnail_url" placeholder="https://..."></label>
            <label>Large image URL <input name="image_url" placeholder="https://..."></label>
            <label>Footer text <input name="footer_text" value="Wandering Bot"></label>
            <label>Footer icon URL <input name="footer_icon_url" placeholder="https://..."></label>
            <label>Mention
              <select name="mention_mode"><option value="none">No mention</option><option value="everyone">@everyone</option><option value="here">@here</option><option value="role">Role mention</option></select>
            </label>
            <label>Role ID to mention <input name="mention_role_id" placeholder="optional role id"></label>
            <label>Schedule / trigger
              <select name="schedule_type">
                <option value="manual">Manual / save only</option>
                <option value="timer">Timer</option>
                <option value="daily">Daily at time</option>
                <option value="weekly">Weekly at time</option>
                <option value="interval">Repeat every X minutes</option>
                <option value="member_join">Member joins</option>
                <option value="member_leave">Member leaves</option>
                <option value="level_up">Level up</option>
                <option value="birthday">Member birthday</option>
                <option value="stats_refresh">Server stats refresh</option>
                <option value="player_kill">Player kills another player</option>
                <option value="player_death">Player dies</option>
                <option value="zombie_death">Player killed by infected</option>
                <option value="animal_death">Player killed by animal</option>
                <option value="longshot">Longshot recorded</option>
                <option value="flag_raise">Territory flag raised</option>
                <option value="flag_lower">Territory flag lowered</option>
                <option value="player_join_server">Player joins DayZ server</option>
                <option value="player_leave_server">Player leaves DayZ server</option>
                <option value="chat_keyword">Discord message contains keyword</option>
                <option value="wallet_change">Wallet balance changes</option>
                <option value="shop_purchase">Shop purchase queued</option>
                <option value="quest_complete">PVE quest completed</option>
                <option value="radar_enter">Player enters radar zone</option>
                <option value="safe_zone_enter">Player enters safe zone</option>
              </select>
            </label>
            <label>Time / day <input name="schedule_time" placeholder="10:00, Monday 18:00, etc."></label>
            <label>Player/event filter <input name="event_filter" placeholder="keyword, player name, weapon, zone, any"></label>
            <label>Minimum value <input name="event_minimum" type="number" value="0" placeholder="distance, kills, amount, etc."></label>
            <label>Interval minutes <input name="interval_minutes" type="number" value="60"></label>
            <label>Timezone <input name="timezone" value="Europe/Dublin"></label>
            <label>Button label <input name="button_label" placeholder="optional link button"></label>
            <label>Button URL <input name="button_url" placeholder="https://..."></label>
            <label class="full">Message <textarea name="body">Respect the server, no exploits, and keep it fair.</textarea></label>
            <label class="full">Embed fields <textarea name="fields_lines">Server Rule | No exploits, duping, or glitch abuse. | false
Respect | Keep chat and gameplay fair. | false</textarea></label>
            <div class="full embed-preview">
              <strong>Embed preview shape</strong>
              <span>Title, description, colour, author, thumbnail/image, footer, custom fields, link button and trigger settings are saved together.</span>
              <small>Fields use: Name | Value | inline true/false</small>
            </div>
            <div class="full"><button type="submit">Save Message</button> <span class="result muted"></span></div>
          </form>
          <div class="stack" style="margin-top:.75rem">
            {% for template in (server.embed_templates if server else []) %}
            <div class="notification"><strong>{{ template.template_id }}</strong><span>{{ template.name }} -> {{ template.schedule.type if template.schedule else 'manual' }}</span></div>
            {% else %}
            <p class="muted">No saved embed templates for this server yet.</p>
            {% endfor %}
          </div>
        </article>
        <article class="admin-panel">
          <h3>Welcome, Goodbye & Birthday</h3>
          <form class="admin-form" data-route="/api/admin/welcome-automation">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>When should it send?
              <select name="name">
                <option value="new-survivor-welcome">New survivor joins Discord</option>
                <option value="member-goodbye">Member leaves Discord</option>
                <option value="birthday">Member birthday</option>
                <option value="first-time-seen">New gamertag appears in ADM</option>
                <option value="returning-player">Returning player reconnects</option>
              </select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if channel.key == 'welcome' %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Assign birthday role ID <input name="birthday_role_id" placeholder="optional role id"></label>
            <label>Send hour <input name="send_hour" value="10:00"></label>
            <label class="full">Message <textarea name="message">Welcome survivor. Read the rules, link your gamer tag, and good luck out there.</textarea></label>
            <div class="full"><button type="submit">Save Welcome</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Utilities & Server Growth</h3>
          <form class="admin-form" data-route="/api/admin/utility-config">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Module
              <select name="module">
                <option value="server_stats">Server statistics counters</option>
                <option value="leveling">Leveling and XP</option>
                <option value="profile_card">Custom profile/rank card</option>
                <option value="giveaways">Giveaways</option>
                <option value="birthdays">Birthday notifications</option>
                <option value="custom_commands">Custom commands</option>
                <option value="moderation">Moderation helpers</option>
                <option value="invite_tracker">Invite tracker</option>
                <option value="transcripts">Ticket transcripts</option>
              </select>
            </label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Output channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}">{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Limit / max count <input name="limit" type="number" value="10"></label>
            <label>XP per message <input name="xp_per_message" type="number" value="15"></label>
            <label>Cooldown seconds <input name="cooldown_seconds" type="number" value="60"></label>
            <label>Card accent colour <input name="card_colour" type="color" value="#8d963e"></label>
            <label>Background image URL <input name="background_url" placeholder="https://..."></label>
            <label class="full">Settings note <textarea name="notes">Configure this module for this server.</textarea></label>
            <div class="full"><button type="submit">Save Utility</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Reaction Roles</h3>
          <form class="admin-form" data-route="/api/admin/reaction-role-panel">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Panel type
              <select name="name">
                <option value="server-roles">Server roles</option>
                <option value="platform-roles">Platform roles</option>
                <option value="event-pings">Event pings</option>
                <option value="faction-alerts">Faction alert roles</option>
              </select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}">{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label class="full">Role lines <textarea name="roles">Verified | yes | 1234567890
Trader pings | coin | 1234567890
Event pings | bell | 1234567890</textarea></label>
            <div class="full"><button type="submit">Save Panel</button> <span class="result muted"></span></div>
          </form>
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
          <form class="admin-form" data-route="/api/admin/faction" id="faction-edit-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Faction name <input name="name" value="The Wanderers"></label>
            <label>Leader Discord ID <input name="leader_id" placeholder="Discord user id"></label>
            <label>Faction role ID <input name="role_id" placeholder="Discord role id"></label>
            <label>Alert channel
              <select name="alert_channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if channel.key == 'factions_chat' %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Colour <input name="colour" type="color" value="#8d963e"></label>
            <div class="full"><button type="submit">Save Faction</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Faction Member</h3>
          <form class="admin-form" data-route="/api/admin/faction-member">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Faction <input name="name" value="The Wanderers"></label>
            <label>Member Discord ID <input name="member_id" placeholder="Discord user id"></label>
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
                <td>{{ faction.alert_channel_key or faction.alert_channel_id or '-' }}</td>
                <td>
                  <button type="button" data-faction-edit data-name="{{ faction.name or faction_name }}" data-leader="{{ faction.leader_id or faction.leader or '' }}" data-role="{{ faction.role_id or faction.discord_role_id or '' }}" data-channel="{{ faction.alert_channel_key or faction.alert_channel_id or '' }}" data-colour="{{ faction.colour or faction.color or '#8d963e' }}">Edit</button>
                  <form class="admin-form inline-action" data-route="/api/admin/faction-action" data-confirm="Delete faction {{ faction.name or faction_name }} from this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
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
          <form class="admin-form zone-builder-form" data-route="/api/admin/zone" id="zone-edit-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="zone_id" value="">
            <div class="server-lock full"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Zone name <input name="name" value="North West Airfield"></label>
            <label>Zone type
              <select name="zone_type"><option value="radar">Radar ping zone</option><option value="safe">Safe zone</option><option value="pvp">PVP zone</option><option value="action">Ban / action zone</option><option value="faction">Faction territory</option><option value="custom">Custom marker</option></select>
            </label>
            <label>X coordinate <input name="x" type="number" value="7500"></label>
            <label>Y coordinate <input name="y" type="number" value="7500"></label>
            <label>Shape
              <select name="shape" data-zone-shape><option value="circle">Circle</option><option value="boundary">Draw boundary</option></select>
            </label>
            <label>Radius meters <input name="radius" type="number" min="10" max="{{ server.map_size if server else 15360 }}" step="10" value="250" data-zone-radius></label>
            <label class="full">Radius slider <input name="radius_slider" type="range" min="10" max="3000" step="10" value="250" data-zone-radius-slider></label>
            <label>Ping / report channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.value }}" data-channel-id="{{ channel.id }}" {% if channel.key == 'radar' or channel.key == 'pvp_intel' %}selected{% endif %}>{{ channel.label }}</option>{% endfor %}
              </select>
            </label>
            <label>Ping role ID <input name="role_id" placeholder="optional Discord role id"></label>
            <label>Faction colour source
              <select name="faction_name">
                <option value="">No faction colour</option>
                {% for faction_name, faction in (server.factions.items() if server and server.factions else []) %}<option value="{{ faction.name or faction_name }}" data-faction-colour="{{ faction.colour or faction.color or '#8d963e' }}">{{ faction.name or faction_name }}</option>{% endfor %}
              </select>
            </label>
            <label>Zone colour <input name="colour" type="color" value="#d5b45f" data-zone-colour></label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Action on violation
              <select name="action"><option value="none">Notify only</option><option value="manhunt">Start manhunt</option><option value="ban">Ban through Nitrado</option></select>
            </label>
            <label>Ban type <select name="ban_type"><option value="temp">Temp ban</option><option value="perm">Perm ban</option></select></label>
            <label>Temp ban minutes <input name="ban_duration_minutes" type="number" value="1440"></label>
            <label>Trigger territory <select name="trigger_territory"><option value="inside">Inside zone</option><option value="outside">Outside zone</option></select></label>
            <label class="full">Triggers <input name="triggers" value="detection,login,kill,build" placeholder="detection, login, kill, build, flag_raise"></label>
            <label class="full">Ignored gamertags <input name="ignored_gamertags" placeholder="comma-separated names that should not ping radar"></label>
            <input class="hidden-field" name="boundary_points" data-boundary-points value="">
            <div class="full embed-preview">
              <strong>Map controls</strong>
              <span>Circle mode sets the center and radius. Boundary mode lets you click multiple points around an area; save when the outline covers the place you want.</span>
            </div>
            <div class="full zone-tools">
              <div class="mini-card"><strong data-zone-radius-label>250m</strong><span class="muted">Circle radius</span></div>
              <div class="mini-card"><strong data-zone-shape-label>Circle</strong><span class="muted">Drawing mode</span></div>
              <div class="mini-card"><strong data-boundary-count>0</strong><span class="muted">Boundary points</span></div>
              <div class="zone-tool-actions">
                <button type="button" data-clear-boundary>Clear Boundary</button>
                <button type="button" data-undo-boundary>Undo Point</button>
              </div>
            </div>
            <div class="full zone-map" data-zone-map data-map-size="{{ server.map_size if server else 15360 }}" {% if server %}style="--map-image: url('/map-image/{{ server.map_key }}');"{% endif %}>
              {% if server and not server.map_image_available %}
              <div class="map-missing">Real {{ server.map|upper }} map image is not installed yet. Add <code>{{ server.map_key }}_map.jpg</code> beside the bot, or set the Railway map image variable, and this builder will use it automatically.</div>
              {% endif %}
              <svg class="zone-boundary-layer" data-boundary-layer viewBox="0 0 100 100" preserveAspectRatio="none"></svg>
              {% for zone in (server.zones if server else []) %}
              {% if zone.shape == "boundary" and zone.points_percent %}
              <svg class="zone-boundary-layer" viewBox="0 0 100 100" preserveAspectRatio="none" style="--zone-colour: {{ zone.colour }};"><polygon points="{{ zone.points_percent }}"></polygon></svg>
              {% else %}
              <span class="zone-dot {{ zone.zone_type }}" title="{{ zone.name }}" style="--zone-colour: {{ zone.colour }}; left: {{ zone.x_percent }}%; top: {{ zone.y_percent }}%; width: {{ zone.dot_size }}px; height: {{ zone.dot_size }}px;">{{ loop.index }}</span>
              {% endif %}
              {% endfor %}
            </div>
            <div class="full map-readout" data-map-readout>Click the map to choose a coordinate.</div>
            <div class="full"><button type="submit">Save Zone</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel full">
          <h3>Existing Zones</h3>
          <table class="item-table">
            <thead><tr><th>#</th><th>Name</th><th>Type</th><th>Center</th><th>Radius</th><th>Action</th><th>Channel</th><th>Actions</th></tr></thead>
            <tbody>
              {% for zone in (server.zones if server else []) %}
              <tr>
                <td>{{ loop.index }}</td>
                <td><span class="zone-swatch" style="--zone-colour: {{ zone.colour }};"></span>{{ zone.name }}</td>
                <td>{{ zone.zone_type }}</td>
                <td>{{ zone.x }}, {{ zone.y }}</td>
                <td>{{ zone.radius }}m</td>
                <td>{{ zone.action or 'notify' }}</td>
                <td>{{ zone.channel_key or zone.alert_channel_id or zone.report_channel_id or 'default' }}</td>
                <td>
                  <button type="button" data-zone-edit data-zone='{{ zone|tojson|forceescape }}'>Edit</button>
                  <form class="admin-form inline-action" data-route="/api/admin/zone-action" data-confirm="Delete zone {{ zone.name }} from this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="zone_id" value="{{ zone.id }}">
                    <input class="hidden-field" name="zone_type" value="{{ zone.zone_type }}">
                    <input class="hidden-field" name="name" value="{{ zone.name }}">
                    <input class="hidden-field" name="action" value="delete">
                    <button type="submit">Delete</button> <span class="result muted"></span>
                  </form>
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
        <span class="pill">{{ server.members|length if server else 0 }} members</span>
      </div>
      <div class="panel-grid">
        <article class="admin-panel full">
          <h3>Server Members</h3>
          <table class="item-table">
            <thead><tr><th>Player</th><th>Discord ID</th><th>Faction</th><th>Online</th><th>Kills</th><th>Deaths</th><th>Actions</th></tr></thead>
            <tbody>
              {% for member in (server.members if server else []) %}
              <tr>
                <td>{{ member.name }}</td>
                <td>{{ member.discord_id or '-' }}</td>
                <td>{{ member.faction or '-' }}</td>
                <td>{{ 'Online' if member.online else 'Offline' }}</td>
                <td>{{ member.kills }}</td>
                <td>{{ member.deaths }}</td>
                <td>
                  <form class="admin-form inline-action" data-route="/api/admin/member-action" data-confirm="Kick {{ member.name }} from Discord for this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="member_id" value="{{ member.discord_id }}">
                    <input class="hidden-field" name="player_name" value="{{ member.name }}">
                    <input class="hidden-field" name="action" value="discord_kick">
                    <button type="submit" {% if not member.discord_id %}disabled{% endif %}>Kick</button> <span class="result muted"></span>
                  </form>
                  <form class="admin-form inline-action" data-route="/api/admin/member-action" data-confirm="Ban {{ member.name }} from Discord for this server?">
                    <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                    <input class="hidden-field" name="member_id" value="{{ member.discord_id }}">
                    <input class="hidden-field" name="player_name" value="{{ member.name }}">
                    <input class="hidden-field" name="action" value="discord_ban">
                    <button type="submit" {% if not member.discord_id %}disabled{% endif %}>Discord Ban</button> <span class="result muted"></span>
                  </form>
                  <form class="admin-form inline-action" data-route="/api/admin/member-action" data-confirm="Queue a DayZ/Nitrado ban for {{ member.name }} on this server?">
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
    <section class="section-panel" id="pve-workshop">
      <div class="section-head">
        <div>
          <h2>PVE Quests & Workshop</h2>
          <p class="tool-note">Track active quests, AI campaigns, scheduled workshop posts, and reward delivery information from the dashboard.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
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
        <article class="admin-panel">
          <h3>Quest Workshop</h3>
          <div class="mini-grid">
            <div class="mini-card"><span class="muted">Campaigns</span><strong>{{ server.pve.campaigns if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Schedules</span><strong>{{ server.pve.schedules if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Rewards</span><strong>{{ server.pve.reward_types|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Quest channels</span><strong>{{ server.pve.quest_channels if server else 0 }}</strong></div>
          </div>
          <p class="tool-note" style="margin-top:.75rem">Use the Discord quest-workshop channel for AI generation. This dashboard shows the state and lets you control whether each guild has the module enabled.</p>
        </article>
        <article class="admin-panel">
          <h3>Airdrop / Spawn Event</h3>
          <form class="admin-form" action="/api/admin/scenario-event" method="post" data-route="/api/admin/scenario-event" id="scenario-event-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="event_id" value="">
            <input class="hidden-field" name="return_to" value="/admin?section=pve{{ server_qs }}#pve-workshop">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Event type
              <select name="event_type" data-scenario-type>
                <option value="airdrop">Airdrop crate</option>
                <option value="animal_pack">Animal pack</option>
                <option value="zombie_horde">Zombie horde</option>
                <option value="loot_crate">Loot crate</option>
                <option value="vehicle_spawn">Vehicle spawn</option>
              </select>
            </label>
            <label>Spawn type
              <select name="spawn_preset" data-scenario-preset>
                <option value="military_crate" data-type="airdrop" data-class="StaticObj_Misc_WoodenCrate_5x" data-count="1" data-radius="35" data-loot="military_high">Military airdrop crate</option>
                <option value="wooden_crate" data-type="loot_crate" data-class="StaticObj_Misc_WoodenCrate_5x" data-count="1" data-radius="20" data-loot="survival">Wooden crate</option>
                <option value="sea_chest" data-type="loot_crate" data-class="SeaChest" data-count="1" data-radius="20" data-loot="survival">Sea chest</option>
                <option value="green_barrel" data-type="loot_crate" data-class="Barrel_Green" data-count="1" data-radius="20" data-loot="survival">Green barrel</option>
                <option value="medical_crate" data-type="loot_crate" data-class="WoodenCrate" data-count="1" data-radius="20" data-loot="medical">Medical loot crate</option>
                <option value="building_crate" data-type="loot_crate" data-class="WoodenCrate" data-count="1" data-radius="20" data-loot="building">Building loot crate</option>
                <option value="food_crate" data-type="loot_crate" data-class="WoodenCrate" data-count="1" data-radius="20" data-loot="food">Food loot crate</option>
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
                <option value="custom">Custom classname</option>
              </select>
            </label>
            <label>Event name <input name="name" placeholder="Optional display name"></label>
            <label>Classname <input name="class_name" value="StaticObj_Misc_WoodenCrate_5x" placeholder="Only needed for Custom classname"></label>
            <label>X coordinate <input name="x" type="number" value="7500"></label>
            <label>Z coordinate <input name="z" type="number" value="7500"></label>
            <label>Y height <input name="y" type="number" value="0" placeholder="ignored by console CE XML"></label>
            <label>How many animals / crates / infected <input name="count" type="number" min="1" max="250" value="1"></label>
            <label>Spread radius <input name="radius" type="number" value="35"></label>
            <div class="full" data-zombie-mix-builder>
              <h4>Zombie Horde Mix</h4>
              <input type="hidden" name="zombie_mix" data-zombie-mix-value>
              <div data-zombie-mix-rows></div>
              <button type="button" data-add-zombie-row>Add Zombie Type</button>
            </div>
            <label>Event length
              <select name="permanent">
                <option value="false">One restart only</option>
                <option value="true">Permanent until deleted</option>
              </select>
            </label>
            <label>Runs for restarts <input name="restarts" type="number" value="1" placeholder="Used only for one-time events"></label>
            <label>Loot preset
              <select name="loot_preset"><option value="none">None</option><option value="military_high">Military high tier</option><option value="military_basic">Military basic</option><option value="medical">Medical</option><option value="survival">Survival</option><option value="building">Building</option><option value="food">Food</option><option value="vehicle_car">Vehicle kit</option><option value="vehicle_truck">Truck build kit</option></select>
            </label>
            <label>Vehicle condition
              <select name="vehicle_condition"><option value="full">Full fuel, fluids, and common parts</option><option value="random_parts">Random common parts</option><option value="no_parts">Body only / missing parts</option></select>
            </label>
            <label>Vehicle cargo
              <select name="vehicle_cargo_mode"><option value="normal_with_loot">Full vehicle with selected loot</option><option value="normal_no_loot">Full vehicle with no bot-added loot</option><option value="native_only">Use my server files only</option></select>
            </label>
            <label class="full">Extra loot items <input name="loot_items" placeholder="Optional extras only, comma-separated"></label>
            <label>Visual marker <select name="visual_marker"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Guard class <input name="guard_class" value="ZmbM_SoldierNormal" placeholder="optional infected guard classname"></label>
            <label>Guard count <input name="guard_count" type="number" value="0"></label>
            <label>Guard radius <input name="guard_radius" type="number" value="35"></label>
            <div class="full embed-preview"><strong>Status</strong><span>Queued means accepted. Console events upload through events.xml and cfgeventspawns.xml, so no init.c access is needed. Counts are capped at 250 per event for server safety.</span></div>
            <div class="full"><button type="submit">Save / Queue Event</button> <span class="result muted"></span></div>
          </form>
          <p class="tool-note" style="margin-top:.75rem">Queued events are saved to the same bot config used by `/events`. For console servers, the bot merges them into the native CE XML files and they apply after a server restart.</p>
        </article>
        <article class="admin-panel">
          <h3>Vehicle Reset</h3>
          <form class="admin-form" action="/api/admin/scenario-event" method="post" data-route="/api/admin/scenario-event">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="return_to" value="/admin?section=pve{{ server_qs }}#pve-workshop">
            <input class="hidden-field" name="event_type" value="vehicle_reset_all">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Reset method
              <select name="reset_method"><option value="economy_xml">Economy XML full wipe</option><option value="bridge">Bridge radius delete</option></select>
            </label>
            <label>Vehicle class <input name="class_name" value="ALL_VEHICLES"></label>
            <label>X coordinate <input name="x" type="number" value="7500"></label>
            <label>Z coordinate <input name="z" type="number" value="7500"></label>
            <label>Delete radius <input name="radius" type="number" value="30000"></label>
            <label>Runs for restarts <input name="restarts" type="number" value="1"></label>
            <div class="full"><button type="submit">Queue Vehicle Reset</button> <span class="result muted"></span></div>
          </form>
          <p class="tool-note" style="margin-top:.75rem">Economy XML full wipe changes vehicles init to 0 for the wipe cycle, then restores it to 1. The server must restart for DayZ file changes to take effect.</p>
          <hr>
          <h4>Timed Vehicle Reset</h4>
          <form class="admin-form" data-route="/api/admin/server-control">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            {% set vr = server.config.vehicle_reset_schedule if server and server.config.vehicle_reset_schedule else {} %}
            {% set vr_first_date = (vr.first_date or server.config.vehicle_reset_first_date or '') if server else '' %}
            {% set vr_time = (vr.time or server.config.vehicle_reset_time or '04:00') if server else '04:00' %}
            {% set vr_timezone = (vr.timezone or server.config.vehicle_reset_timezone or 'Europe/Dublin') if server else 'Europe/Dublin' %}
            {% set vr_interval_value = (vr.interval_value or server.config.vehicle_reset_interval_value or 7) if server else 7 %}
            {% set vr_interval_unit = (vr.interval_unit or server.config.vehicle_reset_interval_unit or 'days') if server else 'days' %}
            {% set vr_weekday = (vr.day_of_week or server.config.vehicle_reset_day_of_week or '') if server else '' %}
            {% set vr_month_day = (vr.day_of_month or server.config.vehicle_reset_day_of_month or '') if server else '' %}
            <label>Schedule <select name="vehicle_reset_schedule_enabled"><option value="false" {% if not server or not server.config.vehicle_reset_schedule_enabled %}selected{% endif %}>Off</option><option value="true" {% if server and server.config.vehicle_reset_schedule_enabled %}selected{% endif %}>On</option></select></label>
            <label>Method <select name="vehicle_reset_method"><option value="economy_xml" {% if not server or server.config.vehicle_reset_method != 'bridge' %}selected{% endif %}>Economy XML full wipe</option><option value="bridge" {% if server and server.config.vehicle_reset_method == 'bridge' %}selected{% endif %}>Bridge radius delete</option></select></label>
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
            <div class="full"><button type="submit">Save Vehicle Reset Schedule</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel full">
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
                <td>{{ event.id }}</td><td>{{ event.event_type }}</td><td>{{ event.name }}</td><td>{% if event.zombie_mix %}{% for item in event.zombie_mix[:3] %}{{ item.count }}x {{ item.class }}{% if not loop.last %}<br>{% endif %}{% endfor %}{% if event.zombie_mix|length > 3 %}<br><small class="muted">+ {{ event.zombie_mix|length - 3 }} more</small>{% endif %}{% else %}{{ event.class_name }}{% endif %}</td><td>{{ event.x }}, {{ event.z }}</td><td>{{ 'forever' if event.permanent else event.remaining_restarts }}</td><td data-scenario-status>{{ event.status or 'Accepted / waiting for restart' }}{% if event.upload_error %}<br><small class="muted">{{ event.upload_error }}</small>{% endif %}</td>
                <td>
                  <div class="scenario-actions">
                    <button type="button" data-scenario-edit data-id="{{ event.id }}" data-type="{{ event.event_type }}" data-name="{{ event.name }}" data-class="{{ event.class_name }}" data-x="{{ event.x }}" data-y="{{ event.y }}" data-z="{{ event.z }}" data-count="{{ event.count }}" data-radius="{{ event.radius }}" data-permanent="{{ 'true' if event.permanent else 'false' }}" data-restarts="{{ event.remaining_restarts }}" data-loot="{{ event.loot_preset }}" data-marker="{{ 'true' if event.visual_marker else 'false' }}" data-guard="{{ event.guard_class }}" data-guard-count="{{ event.guard_count }}" data-guard-radius="{{ event.guard_radius }}">Edit</button>
                    {% for action, label in [('upload', 'Upload XML'), ('approve', 'Approve'), ('pause', 'Pause'), ('cancel', 'Cancel'), ('delete', 'Delete')] %}
                    <form class="admin-form inline-action" action="/api/admin/scenario-event-action" method="post" data-route="/api/admin/scenario-event-action" data-scenario-action-form="true" {% if action in ['cancel', 'delete'] %}data-confirm="{{ 'Delete' if action == 'delete' else 'Cancel' }} event {{ event.name }} for this server? This will also rebuild native CE XML without that event when possible."{% endif %}>
                      <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
                      <input class="hidden-field" name="event_id" value="{{ event.id }}">
                      <input class="hidden-field" name="action" value="{{ action }}">
                      <input class="hidden-field" name="return_to" value="/admin?section=pve{{ server_qs }}#pve-workshop">
                      <button type="submit">{{ label }}</button><span class="result muted"></span>
                    </form>
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
          <form class="admin-form" data-route="/api/admin/wage">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Pay who?
              <select name="target_type"><option value="user">One player</option><option value="role">Discord role</option><option value="faction">Whole faction</option></select>
            </label>
            <label>Target ID or faction name <input name="target_id" placeholder="user id, role id, or faction"></label>
            <label>Amount <input name="amount" type="number" value="250"></label>
            <label>Cadence <select name="cadence"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
            <label>Active <select name="active"><option value="true">On</option><option value="false">Off</option></select></label>
            <div class="full"><button type="submit">Save Wage</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Wallet Adjustment</h3>
          <form class="admin-form" data-route="/api/admin/wallet-adjustment">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Player Discord ID <input name="user_id" placeholder="Discord user id"></label>
            <label>Amount <input name="amount" type="number" value="100"></label>
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
        <article class="admin-panel">
          <h3>Reward / Punishment Rule</h3>
          <form class="admin-form" data-route="/api/admin/economy-rule">
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
          <form class="admin-form" data-route="/api/admin/shop-item" id="shop-edit-form">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <label>Item name <input name="item_name" value="NailsBox"></label>
            <label>Price <input name="price" type="number" value="100"></label>
            <label>Category
              <select name="category">
                <option value="Building">Building</option>
                <option value="Weapons">Weapons</option>
                <option value="Medical">Medical</option>
                <option value="Food">Food</option>
                <option value="Tools">Tools</option>
                <option value="Clothing">Clothing</option>
                <option value="General">General</option>
              </select>
            </label>
            <label>Available <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Daily purchase limit <input name="daily_limit" type="number" value="0" placeholder="0 = server default"></label>
            <label>Role IDs allowed <input name="allowed_role_ids" placeholder="optional comma-separated role IDs"></label>
            <label class="full">Blocked player IDs <input name="blocked_user_ids" placeholder="optional comma-separated Discord user IDs"></label>
            <div class="full"><button type="submit">Save Item</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Build Shop Bundle</h3>
          <form class="admin-form" data-route="/api/admin/shop-bundle" id="shop-bundle-form">
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
            <label>Search items <input data-shop-search placeholder="type item/category/status"></label>
            <label>Category
              <select data-shop-category>
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
                <td><button type="button" data-shop-edit data-item="{{ item.name }}" data-price="{{ item.price }}" data-category="{{ item.category }}" data-enabled="{{ 'true' if item.enabled else 'false' }}" data-limit="{{ item.daily_limit }}" data-roles="{{ item.allowed_role_ids|join(',') }}" data-blocked="{{ item.blocked_user_ids|join(',') }}">Edit</button></td>
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
                <td><button type="button" data-shop-edit data-item="{{ item.name }}" data-price="{{ item.price }}" data-category="{{ item.category }}" data-enabled="{{ 'true' if item.enabled else 'false' }}" data-limit="{{ item.daily_limit }}" data-roles="{{ item.allowed_role_ids|join(',') }}" data-blocked="{{ item.blocked_user_ids|join(',') }}">Edit</button></td>
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
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Loot Quality Rules</h3>
          <form class="admin-form" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="recipe_kind" value="settings">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Default item damage
              <select name="default_damage">
                <option value="pristine">Pristine</option>
                <option value="worn">Worn</option>
                <option value="random">Random</option>
              </select>
            </label>
            <label>Food, drink, mags, meds quantity
              <select name="quantity_mode">
                <option value="full">Full / 100%</option>
                <option value="vanilla">Keep vanilla</option>
                <option value="custom">Use recipe values</option>
              </select>
            </label>
            <label class="check"><input type="checkbox" name="full_magazines" checked> Magazines spawn full</label>
            <label class="check"><input type="checkbox" name="full_liquids" checked> Bottles and canteens spawn full</label>
            <label class="check"><input type="checkbox" name="full_meds" checked> Tablets and meds spawn full</label>
            <label class="check"><input type="checkbox" name="weapon_attachments" checked> Weapons use attachment recipes</label>
            <label class="full">Notes <input name="notes" placeholder="What this rule pack is for"></label>
            <div class="full embed-preview"><strong>Safe mode</strong><span>This saves the intent only. The injector must download current XML, validate it, show a diff, keep one latest backup, then upload.</span></div>
            <div class="full"><button type="submit">Save Loot Rules</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Filled Bag / Container Generator</h3>
          <form class="admin-form" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="recipe_kind" value="container">
            <label>Recipe name <input name="recipe_name" value="Starter Builder Bag"></label>
            <label>Container classname <input name="container_class" list="xml-item-options" value="DryBag_Black"></label>
            <label>Spawn damage <select name="damage"><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
            <label>Maximum cargo slots <input name="capacity_hint" type="number" value="0" placeholder="optional"></label>
            <div class="full item-picker" data-item-picker data-picker-mode="xml">
              <div class="item-picker-controls">
                <label>Find item <input data-picker-item list="xml-item-options" placeholder="Search item classname"></label>
                <label>Qty <input data-picker-qty type="number" min="1" max="999" value="1"></label>
                <label>Fill <select data-picker-quantity><option value="-1">Native</option><option value="100">Full</option><option value="75">75%</option><option value="50">50%</option><option value="25">25%</option></select></label>
                <label>Damage <select data-picker-damage><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
                <button type="button" data-picker-add>Add</button>
              </div>
              <div class="item-picker-preview"><img class="item-thumb" data-picker-image src="/item-thumb/General" alt=""><span data-picker-label>Choose items without typing classnames by hand.</span></div>
            </div>
            <label class="full">Items inside
              <textarea name="items" data-picker-output placeholder="Nail, 32, -1, pristine&#10;Hatchet, 1, -1, pristine"></textarea>
            </label>
            <div class="full"><button type="submit">Save Container Recipe</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Player Loadout</h3>
          <form class="admin-form" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="recipe_kind" value="player_loadout">
            <label>Loadout name <input name="recipe_name" value="Fresh Spawn Plus"></label>
            <label>Custom file path <input name="custom_path" value="./custom/WanderingLoadout.json"></label>
            <label>Role restriction <input name="role_ids" placeholder="optional Discord role IDs"></label>
            <div class="full loadout-builder">
              <div>
                <h4>Player Slots</h4>
                <div class="loadout-slots">
                  {% for slot in ["Head", "Eyes", "Mask", "Body", "Vest", "Back", "Hips", "Legs", "Feet", "Hands", "Gloves", "Armband"] %}
                  <span class="loadout-slot">{{ slot }}</span>
                  {% endfor %}
                </div>
              </div>
              <div>
                <h4>Item Line Format</h4>
                <p class="tool-note">Item, amount, quantity %, damage, slot, attachment-for. Example: WaterBottle, 1, 100, pristine, Back</p>
              </div>
            </div>
            <div class="full item-picker" data-item-picker data-picker-mode="loadout">
              <div class="item-picker-controls">
                <label>Find item <input data-picker-item list="xml-item-options" placeholder="Search item classname"></label>
                <label>Qty <input data-picker-qty type="number" min="1" max="999" value="1"></label>
                <label>Fill <select data-picker-quantity><option value="-1">Native</option><option value="100">Full</option><option value="75">75%</option><option value="50">50%</option></select></label>
                <label>Slot <select data-picker-slot><option value="">Unsorted</option><option>Head</option><option>Eyes</option><option>Mask</option><option>Body</option><option>Vest</option><option>Back</option><option>Hips</option><option>Legs</option><option>Feet</option><option>Hands</option><option>Gloves</option><option>Armband</option></select></label>
                <button type="button" data-picker-add>Add</button>
              </div>
              <label>Attachment for weapon/item <input data-picker-attachment list="xml-item-options" placeholder="optional parent classname"></label>
              <label>Damage <select data-picker-damage><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
              <div class="item-picker-preview"><img class="item-thumb" data-picker-image src="/item-thumb/General" alt=""><span data-picker-label>Pick gear, slot, quantity and damage.</span></div>
            </div>
            <label class="full">Loadout items
              <textarea name="items" data-picker-output placeholder="BandageDressing, 2, -1, pristine, Body&#10;WaterBottle, 1, 100, pristine, Back&#10;Mag_STANAG_30Rnd, 2, 100, pristine"></textarea>
            </label>
            <div class="full embed-preview"><strong>cfggameplay.json</strong><span>This loadout will be referenced from PlayerData.spawnGearPresetFiles using the custom file path above.</span></div>
            <div class="full"><button type="submit">Save Player Loadout</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Vehicle Loadout</h3>
          <form class="admin-form" data-route="/api/admin/xml-workshop">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="recipe_kind" value="vehicle_loadout">
            <label>Vehicle recipe <input name="recipe_name" value="Builder Truck"></label>
            <label>Vehicle classname <input name="vehicle_class" list="xml-item-options" value="Truck_01_Covered"></label>
            <label>Mode <select name="vehicle_mode"><option value="full_with_cargo">Full vehicle with cargo</option><option value="full_no_cargo">Full vehicle, no cargo</option><option value="native">Use native files</option></select></label>
            <div class="full item-picker" data-item-picker data-picker-mode="xml">
              <div class="item-picker-controls">
                <label>Find cargo item <input data-picker-item list="xml-item-options" placeholder="Search item classname"></label>
                <label>Qty <input data-picker-qty type="number" min="1" max="999" value="1"></label>
                <label>Fill <select data-picker-quantity><option value="-1">Native</option><option value="100">Full</option><option value="75">75%</option><option value="50">50%</option></select></label>
                <label>Damage <select data-picker-damage><option value="pristine">Pristine</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="random">Random</option></select></label>
                <button type="button" data-picker-add>Add</button>
              </div>
              <div class="item-picker-preview"><img class="item-thumb" data-picker-image src="/item-thumb/General" alt=""><span data-picker-label>Build vehicle cargo from server item data.</span></div>
            </div>
            <label class="full">Cargo items
              <textarea name="items" data-picker-output placeholder="WoodenPlank, 20, -1, pristine&#10;Nail, 99, -1, pristine"></textarea>
            </label>
            <div class="full"><button type="submit">Save Vehicle Loadout</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel full">
          <h3>Saved XML Recipes</h3>
          <div class="mini-grid">
            <div class="mini-card"><span class="muted">Containers</span><strong>{{ server.xml_workshop.container_recipes|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Player loadouts</span><strong>{{ server.xml_workshop.player_loadouts|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Vehicle loadouts</span><strong>{{ server.xml_workshop.vehicle_loadouts|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Status</span><strong>Draft</strong></div>
          </div>
          <p class="tool-note" style="margin-top:.75rem">{{ server.xml_workshop.status if server else 'No recipes saved yet.' }}</p>
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
          <form class="admin-form" data-route="/api/admin/link-enforcement">
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
          <form class="admin-form" data-route="/api/admin/on-screen-message">
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
          <p class="tool-note">Restart timing and damage settings are separate controls for this server only. Vehicle resets live in PVE & Workshop. File and gameplay changes need a server restart before DayZ applies them.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Restart Schedule</h3>
          <form class="admin-form" data-route="/api/admin/server-control">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Restart schedule <select name="restart_schedule_enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Every hours <input name="restart_interval_hours" type="number" min="1" max="24" value="{{ (server.config.restart_interval_hours if server else 4) or 4 }}"></label>
            <label>Start hour UTC <input name="restart_start_hour" type="number" min="0" max="23" value="{{ (server.config.restart_start_hour if server else 0) or 0 }}"></label>
            <label>Warning minutes <input name="restart_warning_minutes" value="{{ (server.config.restart_warning_minutes|join(',') if server and server.config.restart_warning_minutes else '30,15,10,5,1') }}"></label>
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
          <form class="admin-form" data-route="/api/admin/server-control">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Base damage <select name="base_damage_state"><option value="on" {% if not server or server.config.base_damage_state != 'off' %}selected{% endif %}>On</option><option value="off" {% if server and server.config.base_damage_state == 'off' %}selected{% endif %}>Off</option></select></label>
            <label>Container damage <select name="container_damage_state"><option value="on" {% if not server or server.config.container_damage_state != 'off' %}selected{% endif %}>On</option><option value="off" {% if server and server.config.container_damage_state == 'off' %}selected{% endif %}>Off</option></select></label>
            <div class="full embed-preview"><strong>Damage Only</strong><span>These toggles are saved separately from vehicle resets so changing raid damage will not change the reset schedule.</span></div>
            <div class="full"><button type="submit">Save Damage Settings</button> <span class="result muted"></span></div>
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
          <h3>Zones</h3>
          <ol>
            <li>Open Zones and pick the server at the top of the dashboard.</li>
            <li>Click the map to fill the X/Y coordinates, then set the radius.</li>
            <li>Use Radar when you only want a channel or role ping.</li>
            <li>Use Safe/PVP when the zone needs actions such as notify, manhunt, or Nitrado ban.</li>
            <li>Existing `/addradarzone` and `/server zone` entries are loaded here automatically.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Radar Pings</h3>
          <ol>
            <li>Choose Radar ping zone.</li>
            <li>Pick the channel that should receive alerts.</li>
            <li>Add a Discord role ID if a role should be pinged.</li>
            <li>Add ignored gamertags for admins, owners, or faction members who should not trigger it.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Server Rules</h3>
          <ol>
            <li>Use Discord Link Enforcement to require players to join Discord and link their gamertag.</li>
            <li>Notify is safest, temp ban and perm ban push to Nitrado ban files.</li>
            <li>Restart after ban forces Nitrado to apply the ban immediately.</li>
            <li>On-screen message changes are file changes and apply after restart.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Themes</h3>
          <ol>
            <li>Use the colour circles in the top bar to change the dashboard look.</li>
            <li>The choice is saved in this browser.</li>
            <li>The theme only changes dashboard colours, not bot behaviour.</li>
          </ol>
        </article>
      </div>
    </section>
    {% endif %}

    {% if auth.kind == "owner" and mode in ["admin", "owner"] and active_section == "access" %}
    <section class="section-panel" id="access">
      <div class="section-head">
        <div>
          <h2>Dashboard Access</h2>
          <p class="tool-note">Server identity is locked to the logged-in guild. Use Discord `/dashboardcredentials reset:true` to change the private password.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Feature Access</h3>
          <form class="admin-form" data-route="/api/admin/guild-access">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
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
        <article class="admin-panel">
          <h3>Link Another Server</h3>
          <form class="admin-form" data-route="/api/admin/link-server">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Current dashboard group</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Other dashboard ID <input name="dashboard_id" autocomplete="off" placeholder="private dashboard id"></label>
            <label>Other dashboard password <input name="password" type="password" autocomplete="new-password" placeholder="private dashboard password"></label>
            <div class="full"><button type="submit">Link Server</button> <span class="result muted"></span></div>
          </form>
          <p class="tool-note" style="margin-top:.75rem">This verifies the other server's private dashboard login before it appears in this dashboard group.</p>
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
      <article class="card"><h3>Automations</h3><p class="muted">{{ summary.embed_templates }} message templates, {{ summary.welcome_automations }} welcomes and {{ summary.reaction_role_panels }} role panels.</p></article>
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
          <section><h3>Channels</h3><ul>{% for channel in server.channels[:6] %}<li><span>{{ channel.label }}</span><span>{{ channel.id }}</span></li>{% else %}<li>No channels found</li>{% endfor %}</ul></section>
          <section><h3>Totals</h3><ul><li><span>Kills</span><span>{{ server.totals.kills }}</span></li><li><span>Deaths</span><span>{{ server.totals.deaths }}</span></li><li><span>Safe zones</span><span>{{ server.safe_zones|length }}</span></li><li><span>Factions</span><span>{{ server.factions|length }}</span></li></ul></section>
        </div>
      </article>
      {% else %}
      <article class="card"><h2>No guilds configured</h2><p class="muted">Run the Discord setup flow, then refresh this dashboard.</p></article>
      {% endfor %}
    </section>
    {% endif %}
  </main>
  <script>
    const DASHBOARD_PUBLIC_URL = "{{ public_url }}";
    const DASHBOARD_THEME = "{{ dashboard_theme }}";
    const ITEM_LOOKUP = {{ (server.shop_items if server else [])|tojson }};
    document.body.dataset.section = "{{ active_section }}";
    function secureDashboardUrl(path) {
      const fallback = window.location.origin;
      const base = DASHBOARD_PUBLIC_URL || fallback;
      try {
        return new URL(path || window.location.href, base).toString();
      } catch (error) {
        return path;
      }
    }
    if (window.location.protocol === "http:" && !["localhost", "127.0.0.1", "0.0.0.0"].includes(window.location.hostname)) {
      window.location.replace(secureDashboardUrl(window.location.pathname + window.location.search + window.location.hash));
    }
    function applyTheme(theme) {
      const safeTheme = theme || "default";
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
      if (label) label.textContent = name ? `${name}${info.category ? ` · ${info.category}` : ""}` : "Pick an item to preview it.";
    }
    applyTheme(DASHBOARD_THEME || localStorage.getItem("wanderingDashboardTheme") || "default");
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
      const pickerButton = event.target.closest("[data-picker-add]");
      if (pickerButton) {
        const picker = pickerButton.closest("[data-item-picker]");
        const form = picker ? picker.closest("form") : null;
        const output = form ? form.querySelector("[data-picker-output]") : null;
        const itemInput = picker ? picker.querySelector("[data-picker-item]") : null;
        const item = itemInput ? itemInput.value.trim() : "";
        if (!item || !output) return;
        const qty = Math.max(1, Math.min(999, Number(picker.querySelector("[data-picker-qty]")?.value || 1) || 1));
        const mode = picker.dataset.pickerMode || "xml";
        const quantity = picker.querySelector("[data-picker-quantity]")?.value || "-1";
        const damage = picker.querySelector("[data-picker-damage]")?.value || "pristine";
        const slot = picker.querySelector("[data-picker-slot]")?.value || "";
        const attachment = picker.querySelector("[data-picker-attachment]")?.value || "";
        const line = mode === "bundle"
          ? `${qty}x ${item}`
          : [item, qty, quantity, damage, slot, attachment].filter((part, index) => index < 4 || String(part || "").trim()).join(", ");
        output.value = output.value.trim() ? `${output.value.trim()}\n${line}` : line;
        itemInput.value = "";
        if (picker) syncPickerPreview(picker);
        itemInput.focus();
      }
    });
    document.addEventListener("input", (event) => {
      if (event.target.matches("[data-picker-item]")) syncPickerPreview(event.target.closest("[data-item-picker]"));
    });
    document.addEventListener("change", (event) => {
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
    document.addEventListener("click", async (event) => {
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
    document.querySelectorAll(".admin-form").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
        if (window.location.protocol === "http:" && !["localhost", "127.0.0.1", "0.0.0.0"].includes(window.location.hostname)) {
          const result = form.querySelector(".result");
          if (result) result.textContent = "Opening secure dashboard...";
          window.location.replace(secureDashboardUrl(window.location.pathname + window.location.search + window.location.hash));
          return;
        }
        const data = new FormData(form);
        const result = form.querySelector(".result");
        const button = event.submitter || form.querySelector('button[type="submit"]');
        const originalButtonText = button ? button.textContent : "";
        let payload = {};
        data.forEach((value, key) => {
          if (value !== "") payload[key] = formValue(value);
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
        if (result) result.textContent = "Saving...";
        if (button) {
          button.disabled = true;
          button.textContent = form.dataset.scenarioActionForm ? "Working..." : "Saving...";
        }
        const token = new URLSearchParams(window.location.search).get("token");
        const route = token ? `${form.dataset.route}?token=${encodeURIComponent(token)}` : form.dataset.route;
        try {
          const response = await fetch(secureDashboardUrl(route), {
            method: "POST",
            headers: {"Content-Type": "application/json", "Accept": "application/json", "X-Requested-With": "fetch"},
            credentials: "same-origin",
            body: JSON.stringify(payload)
          });
          let body = {};
          try { body = await response.json(); } catch (error) {}
          if (result) result.textContent = response.ok ? "Saved" : (body.error || "Rejected");
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
            return;
          }
          if (response.ok && form.classList.contains("inline-action")) {
            const action = String(payload.action || "").toLowerCase();
            if (action === "delete") {
              const row = form.closest("[data-scenario-event-row]");
              if (row) row.remove();
              return;
            }
            window.location.reload();
          }
        } catch (error) {
          const message = window.location.protocol === "http:"
            ? "Open the secure HTTPS dashboard and try again."
            : `Request failed: ${error && error.message ? error.message : error}`;
          if (result) result.textContent = message;
          window.alert(message);
        } finally {
          if (button && button.isConnected) {
            button.disabled = false;
            button.textContent = originalButtonText;
          }
        }
      });
    });
    document.querySelectorAll("[data-shop-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const form = document.getElementById("shop-edit-form");
        if (!form) return;
        form.elements.item_name.value = button.dataset.item || "";
        form.elements.price.value = button.dataset.price || 0;
        form.elements.category.value = button.dataset.category || "General";
        form.elements.enabled.value = button.dataset.enabled || "true";
        form.elements.daily_limit.value = button.dataset.limit || 0;
        form.elements.allowed_role_ids.value = button.dataset.roles || "";
        form.elements.blocked_user_ids.value = button.dataset.blocked || "";
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
      button.addEventListener("click", () => {
        const form = document.getElementById("scenario-event-form");
        if (!form) return;
        form.elements.event_id.value = button.dataset.id || "";
        form.elements.name.value = button.dataset.name || "";
        form.elements.event_type.value = button.dataset.type || "airdrop";
        form.elements.class_name.value = button.dataset.class || "";
        form.elements.x.value = button.dataset.x || 7500;
        form.elements.y.value = button.dataset.y || 0;
        form.elements.z.value = button.dataset.z || 7500;
        form.elements.count.value = button.dataset.count || 1;
        form.elements.radius.value = button.dataset.radius || 35;
        form.elements.permanent.value = button.dataset.permanent || "false";
        form.elements.restarts.value = button.dataset.restarts || 1;
        form.elements.loot_preset.value = button.dataset.loot || "none";
        form.elements.visual_marker.value = button.dataset.marker || "false";
        form.elements.guard_class.value = button.dataset.guard || "";
        form.elements.guard_count.value = button.dataset.guardCount || 0;
        form.elements.guard_radius.value = button.dataset.guardRadius || 35;
        form.scrollIntoView({behavior: "smooth", block: "start"});
        form.elements.class_name.focus();
      });
    });
    document.querySelectorAll("[data-faction-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const form = document.getElementById("faction-edit-form");
        if (!form) return;
        form.elements.name.value = button.dataset.name || "";
        form.elements.leader_id.value = button.dataset.leader || "";
        form.elements.role_id.value = button.dataset.role || "";
        form.elements.colour.value = button.dataset.colour || "#8d963e";
        if (form.elements.alert_channel_key && button.dataset.channel) {
          const option = Array.from(form.elements.alert_channel_key.options).find((item) => item.value === button.dataset.channel || item.dataset.channelId === button.dataset.channel);
          if (option) form.elements.alert_channel_key.value = option.value;
        }
        form.scrollIntoView({behavior: "smooth", block: "center"});
        form.elements.name.focus();
      });
    });
    document.querySelectorAll("[data-scenario-preset]").forEach((presetSelect) => {
      const form = presetSelect.closest("form");
      if (!form) return;
      const typeSelect = form.querySelector("[data-scenario-type]");
      function chooseFirstPresetForType() {
        if (!typeSelect) return;
        const current = presetSelect.selectedOptions[0];
        if (current && (current.dataset.type === typeSelect.value || current.value === "custom")) return;
        const match = Array.from(presetSelect.options).find((item) => item.dataset.type === typeSelect.value);
        if (match) presetSelect.value = match.value;
      }
      function syncScenarioPreset() {
        chooseFirstPresetForType();
        const option = presetSelect.selectedOptions[0];
        if (!option || option.value === "custom") return;
        if (typeSelect && option.dataset.type) typeSelect.value = option.dataset.type;
        if (option.dataset.class) form.elements.class_name.value = option.dataset.class;
        if (option.dataset.count) form.elements.count.value = option.dataset.count;
        if (option.dataset.radius) form.elements.radius.value = option.dataset.radius;
        if (option.dataset.loot && form.elements.loot_preset) form.elements.loot_preset.value = option.dataset.loot;
      }
      presetSelect.addEventListener("change", syncScenarioPreset);
      if (typeSelect) typeSelect.addEventListener("change", syncScenarioPreset);
      syncScenarioPreset();
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

      function syncZoneColour(colour) {
        const value = /^#[0-9a-f]{6}$/i.test(String(colour || "")) ? colour : "#d5b45f";
        map.style.setProperty("--zone-colour", value);
        if (colourInput) colourInput.value = value;
      }

      function setSelectValue(select, value) {
        if (!select || value === undefined || value === null) return;
        const text = String(value);
        const option = Array.from(select.options).find((item) => item.value === text || item.dataset.channelId === text);
        if (option) select.value = option.value;
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
        circle.style.setProperty("--zone-colour", colourInput ? colourInput.value : "#d5b45f");
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
          node.style.setProperty("--zone-colour", colourInput ? colourInput.value : "#d5b45f");
          boundaryLayer.appendChild(node);
        }
        boundaryPoints.forEach((point) => {
          const marker = document.createElement("span");
          marker.className = "zone-boundary-point";
          marker.style.left = `${point.xPercent}%`;
          marker.style.top = `${point.yPercent}%`;
          marker.style.setProperty("--zone-colour", colourInput ? colourInput.value : "#d5b45f");
          map.appendChild(marker);
        });
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
      form.querySelector("[data-clear-boundary]")?.addEventListener("click", () => {
        boundaryPoints.length = 0;
        renderBoundary();
      });
      form.querySelector("[data-undo-boundary]")?.addEventListener("click", () => {
        boundaryPoints.pop();
        renderBoundary();
      });
      map.addEventListener("click", (event) => {
        const rect = map.getBoundingClientRect();
        const xPercent = ((event.clientX - rect.left) / rect.width) * 100;
        const yPercent = ((event.clientY - rect.top) / rect.height) * 100;
        const x = Math.round((xPercent / 100) * size);
        const y = Math.round((1 - (yPercent / 100)) * size);
        form.elements.x.value = Math.max(0, Math.min(size, x));
        form.elements.y.value = Math.max(0, Math.min(size, y));
        let cursor = map.querySelector(".zone-cursor");
        if (!cursor) {
          cursor = document.createElement("span");
          cursor.className = "zone-cursor";
          map.appendChild(cursor);
        }
        cursor.style.left = `${xPercent}%`;
        cursor.style.top = `${yPercent}%`;
        if (shapeSelect && shapeSelect.value === "boundary") {
          boundaryPoints.push({x: form.elements.x.value, y: form.elements.y.value, xPercent, yPercent});
          renderBoundary();
        }
        renderCirclePreview();
        const readout = form.querySelector("[data-map-readout]");
        if (readout) {
          const mode = shapeSelect && shapeSelect.value === "boundary" ? `Boundary point ${boundaryPoints.length}` : `Circle radius ${radiusInput ? radiusInput.value : 250}m`;
          readout.textContent = `Selected X ${form.elements.x.value}, Y ${form.elements.y.value} - ${mode}`;
        }
      });
      document.querySelectorAll("[data-zone-edit]").forEach((button) => {
        button.addEventListener("click", () => {
          let zone = {};
          try { zone = JSON.parse(button.dataset.zone || "{}"); } catch (error) { zone = {}; }
          if (!zone || !Object.keys(zone).length) return;
          form.elements.zone_id.value = zone.id || zone.name || "";
          form.elements.name.value = zone.name || "";
          setSelectValue(form.elements.zone_type, zone.zone_type || zone.type || "radar");
          form.elements.x.value = zone.x || 0;
          form.elements.y.value = zone.y || 0;
          setSelectValue(form.elements.shape, zone.shape || "circle");
          syncRadius(zone.radius || 250);
          setSelectValue(form.elements.channel_key, zone.channel_key || zone.alert_channel_id || zone.report_channel_id || "");
          form.elements.role_id.value = zone.role_id || zone.mention_role_id || "";
          setSelectValue(form.elements.faction_name, zone.faction_name || zone.faction || "");
          syncZoneColour(zone.colour || zone.color || "#d5b45f");
          setSelectValue(form.elements.enabled, zone.enabled === false ? "false" : "true");
          setSelectValue(form.elements.action, zone.action || "none");
          setSelectValue(form.elements.ban_type, zone.ban_type || "temp");
          form.elements.ban_duration_minutes.value = zone.ban_duration_minutes || 1440;
          setSelectValue(form.elements.trigger_territory, zone.trigger_territory || "inside");
          form.elements.triggers.value = Array.isArray(zone.triggers) ? zone.triggers.join(",") : (zone.triggers || "");
          form.elements.ignored_gamertags.value = Array.isArray(zone.ignored_gamertags) ? zone.ignored_gamertags.join(",") : (zone.ignored_gamertags || "");
          boundaryPoints.length = 0;
          const savedPoints = Array.isArray(zone.boundary_points) ? zone.boundary_points : [];
          savedPoints.forEach((point) => {
            const x = Number(point.x || 0);
            const y = Number(point.y || 0);
            boundaryPoints.push({
              x,
              y,
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
          cursor.style.left = `${(Number(form.elements.x.value || 0) / size) * 100}%`;
          cursor.style.top = `${100 - ((Number(form.elements.y.value || 0) / size) * 100)}%`;
          renderCirclePreview();
          if (shapeLabel && shapeSelect) shapeLabel.textContent = shapeSelect.value === "boundary" ? "Boundary" : "Circle";
          const readout = form.querySelector("[data-map-readout]");
          if (readout) readout.textContent = `Editing ${zone.name || "zone"} - save to update this radar/zone.`;
          form.scrollIntoView({behavior: "smooth", block: "center"});
          form.elements.name.focus();
        });
      });
      syncRadius(radiusInput ? radiusInput.value : 250);
      syncZoneColour(colourInput ? colourInput.value : "#d5b45f");
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
    "/api/admin/welcome-automation",
    "/api/admin/utility-config",
    "/api/admin/reaction-role-panel",
    "/api/admin/shop-item",
    "/api/admin/shop-bundle",
    "/api/admin/theme",
    "/api/admin/xml-workshop",
    "/api/admin/scenario-event",
    "/api/admin/scenario-event-action",
    "/api/admin/economy-rule",
    "/api/admin/link-server",
    "/api/admin/zone",
    "/api/admin/zone-action",
    "/api/admin/member-action",
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
    "server-rules": "server_rules",
    "server-control": "server_control",
}

ADMIN_ROUTE_FEATURES = {
    "/api/admin/embed-template": "embeds",
    "/api/admin/welcome-automation": "embeds",
    "/api/admin/reaction-role-panel": "embeds",
    "/api/admin/shop-item": "shop",
    "/api/admin/shop-bundle": "shop",
    "/api/admin/scenario-event": "pve_quests",
    "/api/admin/scenario-event-action": "pve_quests",
    "/api/admin/economy-rule": "economy",
    "/api/admin/zone": "safe_zones",
    "/api/admin/zone-action": "safe_zones",
    "/api/admin/member-action": "members",
    "/api/admin/link-enforcement": "server_rules",
    "/api/admin/on-screen-message": "server_rules",
    "/api/admin/server-control": "server_control",
    "/api/admin/faction": "factions",
    "/api/admin/faction-action": "factions",
    "/api/admin/faction-member": "factions",
    "/api/admin/wage": "wages",
    "/api/admin/wallet-adjustment": "economy",
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
        write_json_file(os.path.join("guilds", f"{safe_guild_id}.json"), config)


def merge_guild_config_records(base: Any, override: Any) -> Any:
    if not isinstance(base, dict):
        return override
    if not isinstance(override, dict):
        return base
    merged = dict(base)
    merged.update(override)
    base_events = base.get("scenario_events")
    override_events = override.get("scenario_events")
    if isinstance(base_events, list) and isinstance(override_events, list):
        events_by_id = {}
        for event in base_events + override_events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("id") or event.get("name") or len(events_by_id))
            existing = events_by_id.get(event_id)
            if not existing:
                events_by_id[event_id] = event
                continue
            event_time = str(event.get("updated_at") or event.get("created_at") or "")
            existing_time = str(existing.get("updated_at") or existing.get("created_at") or "")
            if event_time >= existing_time:
                events_by_id[event_id] = event
        merged["scenario_events"] = list(events_by_id.values())
    elif isinstance(override_events, list):
        merged["scenario_events"] = override_events
    elif isinstance(base_events, list):
        merged["scenario_events"] = base_events
    return merged


def sync_runtime_store(store_name: str, data: Any) -> None:
    if not CUSTOM_STATE_PROVIDER:
        return
    try:
        state = CUSTOM_STATE_PROVIDER()
    except Exception:
        return
    target = state.get(store_name) if isinstance(state, dict) else None
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
        guild_dir = data_path("guilds")
        if os.path.isdir(guild_dir):
            for filename in os.listdir(guild_dir):
                if not filename.endswith(".json"):
                    continue
                guild_id = filename[:-5]
                config = read_json_file(os.path.join("guilds", filename), None)
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
    if not salt or not expected:
        return False
    return secrets.compare_digest(dashboard_password_hash(password, salt), expected)


def session_signature(guild_id: str, password_hash: str) -> str:
    return hashlib.sha256(f"{guild_id}:{password_hash}:{DASHBOARD_COOKIE_SECRET}".encode("utf-8")).hexdigest()


def make_session_cookie(guild_id: str, credentials: dict[str, Any]) -> str:
    password_hash = str(credentials.get("password_hash") or "")
    return f"{guild_id}:{session_signature(guild_id, password_hash)}"


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
        credentials = config.get("dashboard_credentials")
        if not isinstance(credentials, dict):
            credentials = config.get("dashboard_login")
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
    credentials = config.get("dashboard_credentials")
    if not isinstance(credentials, dict):
        credentials = config.get("dashboard_login")
    if not isinstance(credentials, dict):
        return None
    expected = session_signature(guild_id, str(credentials.get("password_hash") or ""))
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
    if not target.startswith("/admin"):
        return fallback
    if "\n" in target or "\r" in target:
        return fallback
    return target


def require_owner_payload() -> tuple[dict[str, Any] | None, Any | None]:
    auth = current_auth()
    if not auth:
        return None, (jsonify({"ok": False, "error": "dashboard login required"}), 401)
    if auth.get("kind") != "owner":
        return None, (jsonify({"ok": False, "error": "owner login required"}), 403)
    return request_payload(), None


def normalize_guild_id(value: Any) -> str:
    return str(value or "global").strip() or "global"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
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


def xml_workshop_summary(config: dict[str, Any]) -> dict[str, Any]:
    workshop = config.get("xml_workshop")
    if not isinstance(workshop, dict):
        workshop = {}
    recipes = workshop.get("recipes") if isinstance(workshop.get("recipes"), dict) else {}
    return {
        "settings": workshop.get("settings") if isinstance(workshop.get("settings"), dict) else {},
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
    return datetime.now(DASHBOARD_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")


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
        members.append(
            {
                "name": name,
                "discord_id": discord_id,
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


def stat_board(title: str, players: list[dict[str, Any]], key: str, suffix: str, limit: int = 10) -> dict[str, Any]:
    rows = [player for player in players if safe_int(player.get(key)) > 0]
    rows.sort(key=lambda item: (-safe_int(item.get(key)), str(item.get("name", "")).lower()))
    return {
        "title": title,
        "rows": [
            {"name": row["name"], "value": f"{safe_int(row.get(key))} {suffix}".strip(), "medal": medal_class(index)}
            for index, row in enumerate(rows[:limit], start=1)
        ],
    }


def time_board(players: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [player for player in players if safe_int(player.get("time_online_seconds")) > 0]
    rows.sort(key=lambda item: (-safe_int(item.get("time_online_seconds")), str(item.get("name", "")).lower()))
    return {
        "title": "⏱️ Most Time Played",
        "rows": [
            {"name": row["name"], "value": format_seconds(row.get("time_online_seconds")), "medal": medal_class(index)}
            for index, row in enumerate(rows[:10], start=1)
        ],
    }


def longshot_board(players: list[dict[str, Any]], longshot_records: Any, guild_id: str) -> dict[str, Any]:
    best: dict[str, int] = {}
    for player in players:
        distance = safe_int(player.get("longest_shot_distance"))
        if distance > 0:
            best[player["name"]] = max(best.get(player["name"], 0), distance)
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
    known_names = {str(player.get("discord_id", "")): player["name"] for player in players if player.get("discord_id")}
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
}


def dashboard_theme_from_config(config: dict[str, Any]) -> str:
    dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    theme = str(dashboard.get("theme") or config.get("dashboard_theme") or "default").strip().lower()
    return theme if theme in VALID_DASHBOARD_THEMES else "default"


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


def map_image_file_for(server_map: str) -> str:
    return MAP_IMAGE_FILES.get(map_key_for(server_map), MAP_IMAGE_FILES["chernarus"])


def map_image_available_for(server_map: str) -> bool:
    key = map_key_for(server_map)
    return os.path.exists(map_image_file_for(server_map)) or bool(DEFAULT_MAP_IMAGE_SOURCES.get(key))


def normalized_zones(config: dict[str, Any], server_map: str, factions: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        x = max(0, min(map_size, safe_int(zone.get("x") or zone.get("center_x") or zone.get("pos_x"))))
        y = max(0, min(map_size, safe_int(zone.get("y") or zone.get("center_y") or zone.get("pos_y"))))
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
            point_y = max(0, min(map_size, safe_int(point.get("y"))))
            boundary_points.append({"x": point_x, "y": point_y})
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
            "safe": "#75d89a",
            "pvp": "#ed3853",
            "radar": "#d5b45f",
            "action": "#ff9f43",
            "faction": "#8d963e",
            "custom": "#d5b45f",
        }
        colour = safe_colour(zone.get("colour") or zone.get("color") or faction_colour, fallback_colours.get(zone_type, "#d5b45f"))
        zone_id = str(zone.get("id") or zone.get("name") or f"zone-{len(normalized) + 1}")
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
                "faction_name": faction_name,
                "x": x,
                "y": y,
                "radius": radius,
                "shape": shape,
                "boundary_points": boundary_points,
                "points_percent": points_percent,
                "channel_key": str(zone.get("channel_key") or ""),
                "alert_channel_id": str(zone.get("alert_channel_id") or ""),
                "report_channel_id": str(zone.get("report_channel_id") or ""),
                "role_id": str(zone.get("role_id") or ""),
                "mention_role_id": str(zone.get("mention_role_id") or ""),
                "action": str(zone.get("action") or "none"),
                "enabled": bool(zone.get("enabled", True)),
                "x_percent": round((x / map_size) * 100, 2) if map_size else 0,
                "y_percent": round(100 - ((y / map_size) * 100), 2) if map_size else 0,
                "dot_size": max(14, min(56, int((radius / map_size) * 320))),
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


def load_dashboard_state() -> dict[str, Any]:
    runtime_state = CUSTOM_STATE_PROVIDER() if CUSTOM_STATE_PROVIDER else {}
    if not isinstance(runtime_state, dict):
        runtime_state = {}

    guild_configs = runtime_state.get("guild_configs") or load_store("guild_configs", {})
    player_stats = runtime_state.get("player_stats") or load_store("player_stats", {})
    online_players = runtime_state.get("online_players") or load_store("online_players", {})
    shop = runtime_state.get("shop_items") or runtime_state.get("shop") or load_store("shop", {})
    wallets = runtime_state.get("wallets") or load_store("wallets", {})
    factions = runtime_state.get("factions") or load_store("factions", {})
    wages = runtime_state.get("wages") or load_store("wages", {})
    delivery_queue = runtime_state.get("delivery_queue") or load_store("delivery_queue", [])
    dashboard_admin = load_store("dashboard_admin", {})
    heatmap = runtime_state.get("territory_heat") or runtime_state.get("heatmap") or load_store("heatmap", {})
    pve_challenges = runtime_state.get("pve_challenges") or load_store("pve_challenges", {})
    pve_ai_campaigns = runtime_state.get("pve_ai_campaigns") or load_store("pve_ai_campaigns", {})
    pve_workshop_schedules = runtime_state.get("pve_workshop_schedules") or load_store("pve_workshop_schedules", {})
    swear_jar = runtime_state.get("swear_jar") or load_store("swear_jar", {})
    longshot_records = runtime_state.get("longshot_records") or load_store("longshot_records", {})
    shop_categories = shop_category_map(shop)
    shop_items = flat_shop_items(shop)

    if not isinstance(guild_configs, dict):
        guild_configs = {}
    if not isinstance(online_players, dict):
        online_players = {}

    servers = []
    total_online = 0
    total_players = 0
    total_kills = 0
    dashboard_enabled = 0

    for guild_id, config in sorted(guild_configs.items(), key=lambda item: str(item[1].get("guild_name", item[0])).lower() if isinstance(item[1], dict) else str(item[0])):
        if not isinstance(config, dict):
            continue
        guild_id = normalize_guild_id(guild_id)
        players = guild_players(player_stats, guild_id)
        online = sorted(str(player) for player in online_players.get(guild_id, []) if player)
        access = dashboard_access(config)
        server_map = str(config.get("server_map") or config.get("map") or "chernarus")
        server_factions = faction_records_for_guild(factions, guild_id)
        server_members = member_records_for_guild(players, online, server_factions)
        zones = normalized_zones(config, server_map, server_factions)
        safe_zones = config.get("safe_zones") or []
        if not isinstance(safe_zones, list):
            safe_zones = []
        server_shop = shop_for_guild(shop, guild_id)
        server_shop_categories = shop_category_map(server_shop)
        server_shop_items = flat_shop_items(server_shop)
        server_wallets = wallet_records_for_guild(wallets, guild_id)
        server_wages = guild_block(wages, guild_id, [])
        channels = public_channels(config.get("channels", {}), guild_id)
        server_heatmap = heatmap_summary(heatmap, guild_id)
        server_pve = pve_summary(pve_challenges, pve_ai_campaigns, pve_workshop_schedules, guild_id, channels)
        totals = {
            "kills": sum(player["kills"] for player in players),
            "deaths": sum(player["deaths"] for player in players),
            "builds": sum(player["builds"] for player in players),
            "players": len(players),
        }
        total_online += len(online)
        total_players += len(players)
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
                "online": online,
                "leaders": players,
                "leaderboards": leaderboard_categories(players, swear_jar, longshot_records, guild_id),
                "members": redact(server_members),
                "channels": channels,
                "totals": totals,
                "safe_zones": redact(safe_zones),
                "zones": redact(zones),
                "scenario_events": redact(config.get("scenario_events", [])) if isinstance(config.get("scenario_events", []), list) else [],
                "dashboard_access": access,
                "factions": redact(server_factions),
                "wages": redact(server_wages),
                "wallets": redact(server_wallets),
                "shop_items": redact(server_shop_items),
                "shop_categories": redact(server_shop_categories),
                "xml_workshop": redact(xml_workshop_summary(config)),
                "chat_rules": redact(config.get("chat_rules", [])),
                "embed_templates": redact(dashboard_admin_records(dashboard_admin, "embed_templates", guild_id)),
                "heatmap": server_heatmap,
                "pve": server_pve,
                "config": redact(config),
            }
        )

    admin_embed_templates = dashboard_admin.get("embed_templates", {}) if isinstance(dashboard_admin, dict) else {}
    admin_welcome = dashboard_admin.get("welcome_automations", {}) if isinstance(dashboard_admin, dict) else {}
    admin_reaction_roles = dashboard_admin.get("reaction_role_panels", {}) if isinstance(dashboard_admin, dict) else {}

    return {
        "summary": {
            "guilds": len(servers),
            "online": total_online,
            "players": total_players,
            "kills": total_kills,
            "dashboard_enabled": dashboard_enabled,
            "shop_items": sum(count_records(server.get("shop_items")) for server in servers),
            "wallets": sum(count_records(server.get("wallets")) for server in servers) or count_records(wallets),
            "delivery_queue": count_records(delivery_queue),
            "factions": sum(count_records(server.get("factions")) for server in servers),
            "wages": sum(count_records(server.get("wages")) for server in servers),
            "embed_templates": count_records(admin_embed_templates),
            "welcome_automations": count_records(admin_welcome),
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
                "shop_items": sum(count_records(server.get("shop_items")) for server in servers),
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
    state = load_dashboard_state()
    state = filter_state_for_auth(state, auth, mode)
    active_section = str(request.args.get("section") or "overview").strip().lower()
    valid_sections = {"overview", "leaderboards", "automations", "factions", "zones", "members", "heatmaps", "pve", "economy", "shop", "xml-workshop", "server-rules", "server-control", "help", "access", "owner"}
    if auth.get("kind") != "owner" and active_section in {"access", "owner"}:
        active_section = "overview"
    if auth.get("kind") == "owner" and mode != "owner" and active_section in {"access", "owner"}:
        active_section = "overview"
    if active_section not in valid_sections:
        active_section = "overview"
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
    return render_template_string(
        PAGE_TEMPLATE,
        mode=mode,
        active_section=active_section,
        dashboard_theme=dashboard_theme,
        section_allowed=section_allowed,
        view_title={"overview": "Operations Dashboard", "admin": "Admin Control Panel", "owner": "Owner Console"}[mode],
        auth=auth,
        refresh_seconds=DASHBOARD_REFRESH_SECONDS,
        public_url=DASHBOARD_PUBLIC_URL,
        summary=state["summary"],
        servers=state["servers"],
        shop_items=state.get("shop_items", []),
        shop_categories=state.get("shop_categories", {}),
        owner_notifications=state.get("owner_notifications", []),
        generated_at=state["generated_at"],
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
    credentials = config.get("dashboard_credentials")
    if not isinstance(credentials, dict):
        credentials = config.get("dashboard_login")
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
    record = save_dashboard_admin("embed_templates", normalize_embed_payload(payload or {}), "template_id")
    return jsonify({"ok": True, "template": record})


@APP.post("/api/admin/welcome-automation")
def api_welcome_automation():
    payload, error = require_admin()
    if error:
        return error
    record = save_dashboard_admin("welcome_automations", payload or {}, "automation_id")
    return jsonify({"ok": True, "automation": record})


@APP.post("/api/admin/utility-config")
def api_utility_config():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    module = str(payload.get("module") or payload.get("name") or "utility").strip()
    payload["module"] = module
    payload["name"] = module
    record = save_dashboard_admin("utility_configs", payload, "module")
    return jsonify({"ok": True, "utility": record})


@APP.post("/api/admin/reaction-role-panel")
def api_reaction_role_panel():
    payload, error = require_admin()
    if error:
        return error
    record = save_dashboard_admin("reaction_role_panels", payload or {}, "panel_id")
    return jsonify({"ok": True, "panel": record})


@APP.post("/api/admin/shop-item")
def api_shop_item():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    return jsonify({"ok": True, "item": {item_name: existing}})


@APP.post("/api/admin/shop-bundle")
def api_shop_bundle():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    return jsonify({"ok": True, "bundle": {bundle_name: existing}})


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


@APP.post("/api/admin/xml-workshop")
def api_xml_workshop():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
        return jsonify({"ok": True, "settings": record, "note": workshop["status"]})

    target_key = {
        "container": "containers",
        "player_loadout": "players",
        "vehicle_loadout": "vehicles",
    }.get(kind)
    if not target_key:
        return jsonify({"ok": False, "error": "recipe_kind must be settings, container, player_loadout, or vehicle_loadout"}), 400

    recipe_name = str(payload.get("recipe_name") or payload.get("name") or "").strip()
    if not recipe_name:
        return jsonify({"ok": False, "error": "recipe_name is required"}), 400
    items = parse_xml_workshop_items(payload.get("items"))
    if not items:
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

    collection = recipes.setdefault(target_key, [])
    if not isinstance(collection, list):
        collection = []
        recipes[target_key] = collection
    collection[:] = [item for item in collection if not isinstance(item, dict) or item.get("id") != record["id"]]
    collection.append(record)
    workshop["updated_at"] = now_text
    workshop["status"] = "Recipe draft saved. The guarded XML injector will use this later for preview and upload."
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "recipe": record, "note": workshop["status"]})


@APP.post("/api/admin/scenario-event")
def api_scenario_event():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    return_to = safe_dashboard_return(payload.get("return_to"), f"/admin?section=pve&guild_id={guild_id}#pve-workshop")
    event_type = str(payload.get("event_type") or "airdrop").strip().lower()
    allowed_types = {"airdrop", "animal_pack", "zombie_horde", "loot_crate", "vehicle_spawn", "vehicle_reset_point", "vehicle_reset_all"}
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
    event_id = requested_event_id if existing_index is not None else max(existing_ids or [0]) + 1
    restarts = safe_int(payload.get("restarts"), 1)
    permanent = safe_bool(payload.get("permanent"), False) or restarts <= 0
    server_map = str(config.get("server_map") or config.get("map") or "chernarus")
    map_size = map_size_for(server_map)
    spawn_preset = str(payload.get("spawn_preset") or "").strip()
    preset = SCENARIO_SPAWN_PRESETS.get(spawn_preset, {})
    if event_type == "vehicle_spawn" and not preset:
        preset = SCENARIO_VEHICLE_PRESETS.get(spawn_preset, {})
    if preset:
        event_type = str(preset.get("event_type") or event_type)
    class_name = str(payload.get("class_name") or "").strip()
    if preset and spawn_preset != "custom":
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

    event = dict(existing_event)
    event.update({
        "id": event_id,
        "name": str(payload.get("name") or f"{preset.get('label') or event_type.replace('_', ' ').title()} #{event_id}"),
        "event_type": event_type,
        "location": str(payload.get("location") or "Dashboard"),
        "x": x,
        "y": safe_int(payload.get("y"), 0),
        "z": z,
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
        "visual_marker": safe_bool(payload.get("visual_marker"), event_type == "airdrop"),
        "marker_class": "Land_Wreck_Caravan_MGreen" if safe_bool(payload.get("visual_marker"), event_type == "airdrop") else "",
        "guard_class": str(payload.get("guard_class") or "").strip(),
        "guard_count": max(0, min(80, safe_int(payload.get("guard_count"), 0))),
        "guard_radius": max(0, min(500, safe_int(payload.get("guard_radius"), 35))),
        "permanent": permanent,
        "remaining_restarts": 0 if permanent else max(1, min(365, restarts)),
        "enabled": True,
        "status": "Accepted / waiting for native CE XML upload",
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
    save_store("guild_configs", guild_configs)
    sync_runtime_store("guild_configs", guild_configs)
    if not wants_json_response():
        return redirect(return_to)
    return jsonify({"ok": True, "event": event, "updated": existing_index is not None, "note": "queued for bot restart/event processing"})


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
                "note": "event removed from dashboard; native CE XML cleanup queued for the bot background uploader",
            })
        event["enabled"] = action in {"approve", "upload"}
        event["status"] = {
            "approve": "Accepted / waiting for native CE XML upload",
            "upload": "Queued for native CE XML upload now",
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

        if action in {"upload", "pause", "cancel"}:
            upload_result = run_runtime_scenario_xml_upload(guild_id)
            if upload_result is not None:
                guild_configs = load_store("guild_configs", {})
                config = guild_configs.setdefault(guild_id, {"channels": {}})
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
                returned_event = None
                for queued_event in events:
                    if not isinstance(queued_event, dict):
                        continue
                    is_target = safe_int(queued_event.get("id"), 0) == event_id
                    is_pending_dashboard_event = (
                        queued_event.get("enabled", True)
                        and str(queued_event.get("created_by") or "") == "dashboard"
                        and str(queued_event.get("event_type") or "") != "vehicle_reset_all"
                        and str(queued_event.get("upload_status") or "waiting_for_bot_upload") in {"waiting_for_bot_upload", "failed", "uploaded"}
                    )
                    if action != "upload" and not is_target:
                        continue
                    if action == "upload" and not is_target and not (upload_ok and is_pending_dashboard_event):
                        continue
                    queued_event["updated_at"] = now_text
                    if upload_ok:
                        if action in {"pause", "cancel"}:
                            queued_event["upload_status"] = "removed"
                            queued_event["status"] = "Removed from native CE XML"
                        else:
                            queued_event["native_ce_uploaded_at"] = now_text
                            queued_event["native_ce_events_path"] = built.get("events_path", "")
                            queued_event["native_ce_spawns_path"] = built.get("spawns_path", "")
                            queued_event["upload_status"] = "uploaded"
                            queued_event["status"] = "Native CE XML uploaded / waiting for restart"
                            queued_event.pop("upload_error", None)
                    else:
                        queued_event["upload_attempts"] = int(queued_event.get("upload_attempts") or 0) + 1
                        queued_event["upload_status"] = "failed"
                        queued_event["upload_error"] = status_text
                        queued_event["status"] = "Native CE XML upload failed"
                    if is_target:
                        returned_event = queued_event
                save_store("guild_configs", guild_configs)
                if not wants_json_response():
                    return redirect(return_to)
                return jsonify({"ok": True, "event": returned_event or event, "upload": upload_result})
        if not wants_json_response():
            return redirect(return_to)
        return jsonify({"ok": True, "event": event})

    if action in {"delete", "cancel"}:
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
        })

    if not wants_json_response():
        return redirect(return_to)
    return jsonify({"ok": False, "error": "scenario event not found for this guild"}), 404


@APP.post("/api/admin/economy-rule")
def api_economy_rule():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    return jsonify({"ok": True, "rule": rule})


@APP.post("/api/admin/link-server")
def api_link_server():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    payload = request_payload()
    dashboard_id = str(payload.get("dashboard_id") or "").strip()
    password = str(payload.get("password") or "")
    target_guild_id, target_config = find_guild_by_dashboard_id(dashboard_id)
    if not target_guild_id or not isinstance(target_config, dict):
        return jsonify({"ok": False, "error": "dashboard ID or password is incorrect"}), 401
    credentials = target_config.get("dashboard_credentials")
    if not isinstance(credentials, dict):
        credentials = target_config.get("dashboard_login")
    if not isinstance(credentials, dict) or not verify_dashboard_password(password, credentials):
        return jsonify({"ok": False, "error": "dashboard ID or password is incorrect"}), 401
    if auth["kind"] == "owner":
        return jsonify({"ok": True, "linked_guild_id": target_guild_id, "message": "owner already has access to every server"})
    primary_guild_id = str(auth["guild_id"])
    if target_guild_id == primary_guild_id:
        return jsonify({"ok": True, "linked_guild_id": target_guild_id, "message": "server already belongs to this dashboard"})
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
    return jsonify({"ok": True, "linked_guild_id": target_guild_id, "server": str(target_config.get("guild_name") or target_guild_id)})


@APP.post("/api/admin/zone")
def api_zone():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    y = max(0, min(map_size, safe_int(payload.get("y"))))
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
            boundary_points.append(
                {
                    "x": max(0, min(map_size, safe_int(point.get("x")))),
                    "y": max(0, min(map_size, safe_int(point.get("y")))),
                }
            )
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
    return jsonify({"ok": True, "zone": radar_record})


@APP.post("/api/admin/zone-action")
def api_zone_action():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    return jsonify({"ok": True, "deleted": deleted, "note": "zone deleted for this guild only"})


@APP.post("/api/admin/link-enforcement")
def api_link_enforcement():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    return jsonify({"ok": True, "enforcement": record})


@APP.post("/api/admin/on-screen-message")
def api_on_screen_message():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
            return jsonify({
                "ok": True,
                "message": record,
                "note": "messages.xml uploaded. Restart the DayZ server for it to take effect.",
                "upload": upload_result,
            })
        return jsonify({
            "ok": False,
            "message": record,
            "error": "messages.xml upload failed: " + (" | ".join(str(message) for message in messages[-4:]) if messages else "no details"),
            "upload": upload_result,
        }), 502
    return jsonify({"ok": True, "message": record, "note": "messages.xml saved and queued for upload; restart required after upload"})


@APP.post("/api/admin/server-control")
def api_server_control():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    if "vehicle_reset_schedule_enabled" in payload:
        config["vehicle_reset_schedule_enabled"] = safe_bool(payload.get("vehicle_reset_schedule_enabled"), False)
    if "vehicle_reset_method" in payload:
        method = str(payload.get("vehicle_reset_method") or "economy_xml").strip().lower()
        config["vehicle_reset_method"] = method if method in {"economy_xml", "bridge"} else "economy_xml"
    if "vehicle_reset_restarts" in payload:
        config["vehicle_reset_restarts"] = max(1, min(365, safe_int(payload.get("vehicle_reset_restarts"), 7)))
    vehicle_schedule_keys = {
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
            "method": str(config.get("vehicle_reset_method") or "economy_xml"),
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
    return jsonify({"ok": True, "server_control": redact(config), "note": "saved for this guild only"})


@APP.post("/api/admin/faction")
def api_faction():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    return jsonify({"ok": True, "faction": faction})


@APP.post("/api/admin/faction-action")
def api_faction_action():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    return jsonify({"ok": True, "deleted": deleted, "note": "faction deleted for this guild only"})


@APP.post("/api/admin/faction-member")
def api_faction_member():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
    return jsonify({"ok": True, "faction": faction})


@APP.post("/api/admin/member-action")
def api_member_action():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
        return jsonify({"ok": ok, "message": message}), status
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
    return jsonify({"ok": True, "action": record, "note": "queued for this guild's bot/Nitrado workflow"})


@APP.post("/api/owner/guild-action")
def api_owner_guild_action():
    payload, error = require_owner_payload()
    if error:
        return error
    payload = payload or {}
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
        return jsonify({"ok": True, "guild_id": guild_id, "owner_admin_visible": dashboard["owner_admin_visible"]})

    left, message = discord_bot_leave_guild(guild_id)
    if not left:
        return jsonify({"ok": False, "error": message}), 502

    if action == "leave_and_remove":
        remove_guild_dashboard_data(guild_id, config)
        return jsonify({"ok": True, "message": f"{message} Dashboard data removed.", "removed": True})

    config["dashboard_removed_at"] = datetime.now(UTC).isoformat()
    config["dashboard_removed_reason"] = "owner requested bot leave guild"
    guild_configs[guild_id] = config
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "message": message, "removed": False})


@APP.post("/api/admin/wage")
def api_wage():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
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
        return jsonify({"ok": True, "wage_id": wage_id, "active": False})
    record = next((wage for wage in block if str(wage.get("id")) == wage_id), None)
    if record is None:
        record = {"id": wage_id}
        block.append(record)
    record.update(
        {
            "target_type": str(payload.get("target_type") or record.get("target_type") or "user"),
            "target_id": str(payload.get("target_id") or record.get("target_id") or ""),
            "amount": safe_int(payload.get("amount", record.get("amount", 0))),
            "cadence": str(payload.get("cadence") or record.get("cadence") or "weekly"),
            "active": bool(payload.get("active", record.get("active", True))),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    save_store("wages", wages)
    return jsonify({"ok": True, "wage": record})


@APP.post("/api/admin/wallet-adjustment")
def api_wallet_adjustment():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    user_id = str(payload.get("user_id") or payload.get("member_id") or "").strip()
    if not user_id:
        return jsonify({"ok": False, "error": "user_id is required"}), 400
    amount = safe_int(payload.get("amount"))
    guild_id = normalize_guild_id(payload.get("guild_id"))
    wallets = load_store("wallets", {})
    if not isinstance(wallets, dict):
        wallets = {}
    key = f"{guild_id}:{user_id}"
    legacy = wallets.get(user_id, {}) if isinstance(wallets.get(user_id), dict) else {}
    wallet = wallets.setdefault(
        key,
        {
            "guild_id": guild_id,
            "user_id": user_id,
            "name": str(payload.get("name") or legacy.get("name") or ""),
            "balance": safe_int(legacy.get("balance", 0)),
            "daily_transactions": safe_int(legacy.get("daily_transactions", 0)),
        },
    )
    wallet["guild_id"] = guild_id
    wallet["user_id"] = user_id
    wallet["balance"] = safe_int(wallet.get("balance")) + amount
    wallet["updated_at"] = datetime.now(UTC).isoformat()
    wallet.setdefault("adjustments", []).append(
        {
            "amount": amount,
            "reason": str(payload.get("reason") or "dashboard adjustment"),
            "guild_id": guild_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    save_store("wallets", wallets)
    return jsonify({"ok": True, "wallet": redact(wallet)})


@APP.post("/api/admin/guild-access")
def api_guild_access():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    if auth.get("kind") != "owner":
        return jsonify({"ok": False, "error": "owner login required"}), 403
    payload = request_payload()
    payload = payload or {}
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
    return jsonify({"ok": True, "dashboard": access})


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
