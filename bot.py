# =========================================================
# WANDERING BOT ALPHA - MULTI GUILD EDITION
# =========================================================

import os
import re
import json
import asyncio
import requests
import discord

from datetime import datetime, UTC
from discord.ext import commands, tasks
from discord import app_commands

# =========================================================
# DISCORD
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================================================
# GLOBAL CONFIG
# =========================================================

BOT_IMAGE = (
    "https://media.discordapp.net/"
    "attachments/1499787777636831324/"
    "1501685742433206342/"
    "7A382429-B666-4A9F-B890-17C0F7981709.png"
)

GUILD_CONFIG_FILE = "guild_configs.json"
GUILD_DATA_FOLDER = "guild_data"
PLAYER_STATS_FILE = "player_stats.json"
HEATMAP_FILE = "heatmap.json"
SWEAR_JAR_FILE = "swear_jar.json"

# =========================================================
# GLOBALS
# =========================================================

guild_configs = {}
processed_lines = set()
online_players = set()
territory_heat = {}
player_stats = {}
swear_jar = {}

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "bollocks",
    "wanker"
]

# =========================================================
# HELPERS
# =========================================================

def style_embed(embed):
    embed.timestamp = datetime.now(UTC)
    return embed


def ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

# =========================================================
# LOADERS
# =========================================================

def load_guild_configs():
    global guild_configs
    guild_configs = load_json(GUILD_CONFIG_FILE)


def save_guild_configs():
    save_json(GUILD_CONFIG_FILE, guild_configs)


def load_player_stats():
    global player_stats
    player_stats = load_json(PLAYER_STATS_FILE)


def save_player_stats():
    save_json(PLAYER_STATS_FILE, player_stats)


def load_heatmap():
    global territory_heat
    territory_heat = load_json(HEATMAP_FILE)


def save_heatmap():
    save_json(HEATMAP_FILE, territory_heat)


def load_swear_jar():
    global swear_jar
    swear_jar = load_json(SWEAR_JAR_FILE)


def save_swear_jar():
    save_json(SWEAR_JAR_FILE, swear_jar)

# =========================================================
# EVENT CLASSIFIER
# =========================================================

def classify_event(line):

    lower = line.lower()

    if "disconnected" in lower:
        return "disconnect"

    if "connecting" in lower or "connected" in lower:
        return "connect"

    if "killed" in lower:
        return "kill"

    if "placed" in lower or "built" in lower:
        return "build"

    if "destroyed" in lower or "dismantled" in lower:
        return "raid"

    return None

# =========================================================
# MULTI GUILD API SEARCH
# =========================================================

def ping_latest_adm_log(config):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")
    nitrado_user = config.get("nitrado_user")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    search_paths = [
        f"/games/{nitrado_user}/noftp/dayzxb/config/",
        f"/games/{nitrado_user}/noftp/dayzxb/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/",
        f"/games/{nitrado_user}/noftp/"
    ]

    for search_path in search_paths:

        try:

            url = (
                f"https://api.nitrado.net/services/"
                f"{service_id}/gameservers/file_server/list"
            )

            params = {
                "dir": search_path,
                "search": "DayZServer"
            }

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=20
            )

            print("[PING STATUS]", response.status_code)

            if response.status_code != 200:
                continue

            data = response.json()

            entries = (
                data
                .get("data", {})
                .get("entries", [])
            )

            matching_logs = [
                entry for entry in entries
                if entry.get("name", "").lower().endswith(".adm")
            ]

            if not matching_logs:
                continue

            matching_logs.sort(
                key=lambda x: x.get("modified_at", ""),
                reverse=True
            )

            latest = matching_logs[0]

            print("LATEST ADM FOUND:", latest.get("path"))

            return latest

        except Exception as error:
            print(error)

    return None

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    ensure_folder(GUILD_DATA_FOLDER)

    load_guild_configs()
    load_player_stats()
    load_heatmap()
    load_swear_jar()

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)
