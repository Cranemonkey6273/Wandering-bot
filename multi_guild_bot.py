# =========================================================
# WANDERING BOT V2 - MULTI GUILD EDITION
# =========================================================

import os
import re
import json
import asyncio
import requests
import discord

from datetime import datetime

try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc

from discord.ext import commands, tasks
from discord import app_commands

# =========================================================
# DISCORD
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================================================
# CONSTANTS
# =========================================================

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

GUILD_CONFIG_FILE = "guild_configs.json"
GUILD_DATA_FOLDER = "guild_data"

# =========================================================
# GLOBALS
# =========================================================

guild_configs = {}
processed_lines = set()

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
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as error:
        print(error)


def load_json(path):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as error:
        print(error)

    return {}


def save_guild_configs():
    save_json(GUILD_CONFIG_FILE, guild_configs)


def load_guild_configs():
    global guild_configs
    guild_configs = load_json(GUILD_CONFIG_FILE)


def get_guild_folder(guild_id):

    folder = os.path.join(
        GUILD_DATA_FOLDER,
        str(guild_id)
    )

    ensure_folder(folder)

    return folder


def get_adm_file(guild_id):

    return os.path.join(
        get_guild_folder(guild_id),
        "latest.ADM"
    )


def get_state_file(guild_id):

    return os.path.join(
        get_guild_folder(guild_id),
        "state.json"
    )


def load_state(guild_id):
    return load_json(get_state_file(guild_id))


def save_state(guild_id, state):
    save_json(get_state_file(guild_id), state)

# =========================================================
# EVENT HELPERS
# =========================================================

def parse_kill_event(line):

    match = re.search(
        r'Player "([^"]+)" killed Player "([^"]+)" with ([^ ]+)',
        line,
        re.IGNORECASE,
    )

    if not match:
        return None

    return {
        "killer": match.group(1),
        "victim": match.group(2),
        "weapon": match.group(3),
    }


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
# AUTO DISCORD SETUP
# =========================================================

@bot.event
async def on_guild_join(guild):

    print(f"JOINED GUILD: {guild.name}")

    guild_id = str(guild.id)

    if guild_id in guild_configs:
        return

    category = await guild.create_category(
        "📡 WANDERING BOT"
    )

    killfeed = await guild.create_text_channel(
        "🔥・killfeed",
        category=category
    )

    deaths = await guild.create_text_channel(
        "☠️・deaths",
        category=category
    )

    connections = await guild.create_text_channel(
        "🚪・connections",
        category=category
    )

    raids = await guild.create_text_channel(
        "🏴・raids",
        category=category
    )

    building = await guild.create_text_channel(
        "🔨・building",
        category=category
    )

    radar = await guild.create_text_channel(
        "📡・radar",
        category=category
    )

    ai = await guild.create_text_channel(
        "🧠・ai-alerts",
        category=category
    )

    guild_configs[guild_id] = {
        "guild_name": guild.name,
        "nitrado_token": "",
        "service_id": "",
        "channels": {
            "killfeed": killfeed.id,
            "deaths": deaths.id,
            "connections": connections.id,
            "raids": raids.id,
            "building": building.id,
            "radar": radar.id,
            "ai": ai.id,
        }
    }

    save_guild_configs()

    embed = discord.Embed(
        title="📡 WANDERING BOT DEPLOYED",
        description=(
            "Your DayZ systems are now online.\n\n"
            "Run `/setup` to connect your Nitrado server."
        ),
        color=0x00FFFF
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await killfeed.send(
        embed=style_embed(embed)
    )

# =========================================================
# SLASH COMMAND
# =========================================================

@bot.tree.command(
    name="setup",
    description="Connect your Nitrado server"
)
@app_commands.describe(
    nitrado_token="Your Nitrado API token",
    service_id="Your Nitrado service ID"
)
async def setup_command(
    interaction: discord.Interaction,
    nitrado_token: str,
    service_id: str
):

    await interaction.response.defer(
        ephemeral=True
    )

    guild_id = str(interaction.guild.id)

    if guild_id not in guild_configs:

        await interaction.followup.send(
            "Guild config not found.",
            ephemeral=True
        )
        return

    guild_configs[guild_id]["nitrado_token"] = nitrado_token
    guild_configs[guild_id]["service_id"] = service_id

    save_guild_configs()

    embed = discord.Embed(
        title="✅ SERVER CONNECTED",
        description="Nitrado server linked successfully.",
        color=0x57F287
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await interaction.followup.send(
        embed=style_embed(embed)),
        ephemeral=True

# =========================================================
# API ADM SEARCH
# =========================================================

def ping_latest_adm_log(config):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    if not token or not service_id:
        return None

    url = (
        f"https://api.nitrado.net/services/{service_id}/gameservers/file_server/list"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    params = {
        "dir": "/games/ni12248929_1/noftp/dayzxb/config/",
        "search": "*DayZServer*",
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20
        )

        print(f"[PING] HTTP STATUS: {response.status_code}")

        if response.status_code != 200:
            print(response.text)
            return None

        data = response.json()

        if data.get("status") != "success":
            print(data)
            return None

        entries = data.get(
            "data",
            {}
        ).get(
            "entries",
            []
        )

        matching_logs = [
            entry
            for entry in entries
            if re.match(
                r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
                entry.get("name", ""),
                re.IGNORECASE,
            )
        ]

        if not matching_logs:
            print("NO ADM LOGS FOUND")
            return None

        matching_logs.sort(
            key=lambda x: x.get("modified_at", ""),
            reverse=True
        )

        latest = matching_logs[0]

        print(f"LATEST ADM FOUND: {latest.get('name')}")

        return latest

    except Exception as error:
        print("ADM SEARCH ERROR")
        print(error)
        return None

# =========================================================
# DOWNLOAD ADM
# =========================================================

def download_latest_adm(
    guild_id,
    config,
    latest_log
):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    try:

        download_url = (
            f"https://api.nitrado.net/services/{service_id}/gameservers/file_server/download"
        )

        headers = {
            "Authorization": f"Bearer {token}"
        }

        params = {
            "file": latest_log.get("path")
        }

        response = requests.get(
            download_url,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return False

        data = response.json()

        token_url = data.get(
            "data",
            {}
        ).get(
            "token",
            {}
        ).get("url")

        if not token_url:
            return False

        file_response = requests.get(
            token_url,
            timeout=30
        )

        with open(get_adm_file(guild_id), "wb") as f:
            f.write(file_response.content)

        return True

    except Exception as error:
        print(error)
        return False

# =========================================================
# PARSE ADM
# =========================================================

async def parse_adm(
    guild_id,
    config
):

    adm_file = get_adm_file(guild_id)

    if not os.path.exists(adm_file):
        return

    state = load_state(guild_id)

    last_line = state.get("last_line", 0)

    with open(
        adm_file,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

    new_lines = lines[last_line:]

    state["last_line"] = len(lines)

    save_state(guild_id, state)

    channels = config.get("channels", {})

    killfeed_channel = bot.get_channel(
        channels.get("killfeed")
    )

    connections_channel = bot.get_channel(
        channels.get("connections")
    )

    raids_channel = bot.get_channel(
        channels.get("raids")
    )

    for raw_line in new_lines:

        line = raw_line.strip()

        if not line:
            continue

        line_hash = f"{guild_id}_{hash(line)}"

        if line_hash in processed_lines:
            continue

        processed_lines.add(line_hash)

        event_type = classify_event(line)

        if not event_type:
            continue

        print(f"[{guild_id}] {event_type}")

        # =====================================================
        # CONNECT
        # =====================================================

        if event_type == "connect" and connections_channel:

            match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                match.group(1)
                if match else "Unknown"
            )

            embed = discord.Embed(
                title="🟢 Survivor Connected",
                description=player_name,
                color=0x2ECC71
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await connections_channel.send(
                embed=style_embed(embed)
            )

        # =====================================================
        # DISCONNECT
        # =====================================================

        elif event_type == "disconnect" and connections_channel:

            match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                match.group(1)
                if match else "Unknown"
            )

            embed = discord.Embed(
                title="🔴 Survivor Disconnected",
                description=player_name,
                color=0xE74C3C
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await connections_channel.send(
                embed=style_embed(embed)
            )

        # =====================================================
        # KILLS
        # =====================================================

        elif event_type == "kill" and killfeed_channel:

            kill_data = parse_kill_event(line)

            if kill_data:

                embed = discord.Embed(
                    title="☠️ PLAYER KILL",
                    color=0x992D22
                )

                embed.add_field(
                    name="🔫 Killer",
                    value=kill_data["killer"],
                    inline=True
                )

                embed.add_field(
                    name="💀 Victim",
                    value=kill_data["victim"],
                    inline=True
                )

                embed.add_field(
                    name="🪖 Weapon",
                    value=kill_data["weapon"],
                    inline=False
                )

            else:

                embed = discord.Embed(
                    title="☠️ KILL EVENT",
                    description=line,
                    color=0x992D22
                )

            embed.set_thumbnail(url=BOT_IMAGE)

            await killfeed_channel.send(
                embed=style_embed(embed)
            )

        # =====================================================
        # RAIDS
        # =====================================================

        elif event_type == "raid" and raids_channel:

            embed = discord.Embed(
                title="🚨 RAID EVENT",
                description=line,
                color=0xFF0000
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await raids_channel.send(
                embed=style_embed(embed)
            )

# =========================================================
# MAIN LOOP
# =========================================================

@tasks.loop(minutes=3)
async def adm_loop():

    for guild_id, config in guild_configs.items():

        try:

            if not config.get("nitrado_token"):
                continue

            latest_log = await asyncio.to_thread(
                ping_latest_adm_log,
                config
            )

            if not latest_log:
                continue

            state = load_state(guild_id)

            modified_at = latest_log.get("modified_at")

            if modified_at == state.get("last_modified"):
                continue

            success = await asyncio.to_thread(
                download_latest_adm,
                guild_id,
                config,
                latest_log
            )

            if not success:
                continue

            state["last_modified"] = modified_at

            save_state(
                guild_id,
                state
            )

            await parse_adm(
                guild_id,
                config
            )

        except Exception as error:
            print(error)

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    ensure_folder(GUILD_DATA_FOLDER)

    load_guild_configs()

    synced = await bot.tree.sync()

    print(f"SYNCED {len(synced)} SLASH COMMANDS")

    if not adm_loop.is_running():
        adm_loop.start()

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)