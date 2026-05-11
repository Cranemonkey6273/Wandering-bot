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
# AUTO GUILD SETUP
# =========================================================

@bot.event
async def on_guild_join(guild):

    guild_id = str(guild.id)

    if guild_id in guild_configs:
        return

    category = await guild.create_category(
        "📡 WANDERING BOT"
    )

    async def make_channel(name):

        return await guild.create_text_channel(
            name,
            category=category
        )

    killfeed = await make_channel("🔥・killfeed")
    raids = await make_channel("🏴・raids")
    builds = await make_channel("🔨・building")
    connections = await make_channel("🚪・connections")

    guild_configs[guild_id] = {
        "guild_name": guild.name,
        "nitrado_token": "",
        "service_id": "",
        "nitrado_user": "",
        "channels": {
            "killfeed": killfeed.id,
            "raids": raids.id,
            "building": builds.id,
            "connections": connections.id
        }
    }

    save_guild_configs()

# =========================================================
# /SETUP COMMAND
# =========================================================

@bot.tree.command(
    name="setup",
    description="Connect your Nitrado server"
)
@app_commands.describe(
    nitrado_token="Your Nitrado API token",
    service_id="Your Nitrado service ID",
    nitrado_user="Example: ni12248929_2"
)
async def setup_command(
    interaction: discord.Interaction,
    nitrado_token: str,
    service_id: str,
    nitrado_user: str
):

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)

    if guild_id not in guild_configs:

        guild_configs[guild_id] = {
            "guild_name": interaction.guild.name,
            "channels": {}
        }

    guild_configs[guild_id]["nitrado_token"] = nitrado_token
    guild_configs[guild_id]["service_id"] = service_id
    guild_configs[guild_id]["nitrado_user"] = nitrado_user.strip()

    save_guild_configs()

    await interaction.followup.send(
        "✅ Server connected successfully.",
        ephemeral=True
    )

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
            f"https://api.nitrado.net/services/"
            f"{service_id}/gameservers/file_server/download"
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

        token_url = (
            data
            .get("data", {})
            .get("token", {})
            .get("url")
        )

        if not token_url:
            return False

        file_response = requests.get(token_url)

        adm_path = os.path.join(
            GUILD_DATA_FOLDER,
            f"{guild_id}.ADM"
        )

        with open(adm_path, "wb") as f:
            f.write(file_response.content)

        return True

    except Exception as error:

        print(error)

        return False

# =========================================================
# ADM PARSER
# =========================================================

async def parse_adm(guild_id, config):

    adm_path = os.path.join(
        GUILD_DATA_FOLDER,
        f"{guild_id}.ADM"
    )

    if not os.path.exists(adm_path):
        return

    with open(
        adm_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

    channels = config.get("channels", {})

    killfeed_channel = bot.get_channel(
        channels.get("killfeed")
    )

    raid_channel = bot.get_channel(
        channels.get("raids")
    )

    build_channel = bot.get_channel(
        channels.get("building")
    )

    connect_channel = bot.get_channel(
        channels.get("connections")
    )

    for raw_line in lines[-250:]:

        line = raw_line.strip()

        if not line:
            continue

        line_hash = hash(line)

        if line_hash in processed_lines:
            continue

        processed_lines.add(line_hash)

        event_type = classify_event(line)

        if not event_type:
            continue

        print(f"EVENT: {event_type} | {line}")

        # ================= CONNECT =================

        if event_type == "connect" and connect_channel:

            embed = discord.Embed(
                title="🟢 Survivor Connected",
                description=line,
                color=0x2ECC71
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= DISCONNECT =================

        elif event_type == "disconnect" and connect_channel:

            embed = discord.Embed(
                title="🔴 Survivor Disconnected",
                description=line,
                color=0xE74C3C
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= BUILD =================

        elif event_type == "build" and build_channel:

            embed = discord.Embed(
                title="🏗️ BUILD EVENT",
                description=line,
                color=0xF1C40F
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await build_channel.send(
                embed=style_embed(embed)
            )

        # ================= RAID =================

        elif event_type == "raid" and raid_channel:

            embed = discord.Embed(
                title="🚨 RAID EVENT",
                description=line,
                color=0xFF0000
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await raid_channel.send(
                embed=style_embed(embed)
            )

        # ================= KILLFEED =================

        elif event_type == "kill" and killfeed_channel:

            embed = discord.Embed(
                title="☠️ PLAYER KILL",
                description=line,
                color=0x992D22
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await killfeed_channel.send(
                embed=style_embed(embed)
            )

# =========================================================
# ADM LOOP
# =========================================================

@tasks.loop(minutes=3)
async def adm_loop():

    for guild_id, config in guild_configs.items():

        try:

            latest_log = await asyncio.to_thread(
                ping_latest_adm_log,
                config
            )

            if not latest_log:
                continue

            success = await asyncio.to_thread(
                download_latest_adm,
                guild_id,
                config,
                latest_log
            )

            if not success:
                continue

            await parse_adm(
                guild_id,
                config
            )

            print(f"NEW ADM FOR {guild_id}")

        except Exception as error:

            print(error)

# =========================================================
# SWEAR JAR
# =========================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    lower = message.content.lower()

    found_words = [
        word for word in SWEAR_WORDS
        if word in lower
    ]

    if found_words:

        user_id = str(message.author.id)

        if user_id not in swear_jar:

            swear_jar[user_id] = {
                "name": str(message.author),
                "count": 0,
                "balance": 0
            }

        swear_jar[user_id]["count"] += len(found_words)

        swear_jar[user_id]["balance"] += (
            len(found_words) * 100
        )

        save_swear_jar()

        embed = discord.Embed(
            title="💸 SWEAR JAR",
            description=(
                f"{message.author.mention} "
                f"was fined £{len(found_words) * 100}"
            ),
            color=0xE67E22
        )

        embed.add_field(
            name="Total Swears",
            value=str(
                swear_jar[user_id]["count"]
            ),
            inline=True
        )

        embed.add_field(
            name="Debt",
            value=f"£{swear_jar[user_id]['balance']}",
            inline=True
        )

        await message.channel.send(
            embed=style_embed(embed)
        )

    await bot.process_commands(message)

# =========================================================
# COMMANDS
# =========================================================

@bot.command()
async def online(ctx):

    if online_players:

        player_list = "
".join(
            f"• {player}"
            for player in sorted(online_players)
        )

    else:

        player_list = "No players online."

    embed = discord.Embed(
        title=f"🟢 ONLINE PLAYERS ({len(online_players)})",
        description=player_list,
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def swearjar(ctx):

    if not swear_jar:

        await ctx.send(
            "Swear jar is empty."
        )

        return

    sorted_users = sorted(
        swear_jar.values(),
        key=lambda x: x["balance"],
        reverse=True
    )

    leaderboard = []

    for index, user in enumerate(
        sorted_users[:10],
        start=1
    ):

        leaderboard.append(
            f"{index}. {user['name']} - £{user['balance']} ({user['count']} swears)"
        )

    embed = discord.Embed(
        title="💸 SWEAR JAR LEADERBOARD",
        description="
".join(leaderboard),
        color=0xF1C40F
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def heatmap(ctx):

    if not territory_heat:

        await ctx.send(
            "No territory activity yet."
        )

        return

    sorted_zones = sorted(
        territory_heat.items(),
        key=lambda x: x[1],
        reverse=True
    )

    lines = []

    for zone, count in sorted_zones:

        lines.append(
            f"🔥 {zone} - {count}"
        )

    embed = discord.Embed(
        title="🗺️ TERRITORY HEATMAP",
        description="
".join(lines),
        color=0xE74C3C
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def topkills(ctx):

    if not player_stats:

        await ctx.send(
            "No stats available."
        )

        return

    sorted_players = sorted(
        player_stats.items(),
        key=lambda x: x[1].get("kills", 0),
        reverse=True
    )

    lines = []

    for index, (player, stats) in enumerate(
        sorted_players[:10],
        start=1
    ):

        lines.append(
            f"{index}. {player} - {stats.get('kills', 0)} kills"
        )

    embed = discord.Embed(
        title="☠️ TOP KILLS",
        description="
".join(lines),
        color=0x992D22
    )

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# ADMIN SERVER CONTROLS
# =========================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def restartserver(ctx):

    embed = discord.Embed(
        title="🔄 SERVER RESTART REQUESTED",
        description="Restart command sent to server.",
        color=0xE67E22
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

    print("SERVER RESTART REQUESTED")


@bot.command()
@commands.has_permissions(administrator=True)
async def togglebasedamage(ctx, state: str):

    state = state.lower()

    if state not in ["on", "off"]:

        await ctx.send(
            "Usage: !togglebasedamage on/off"
        )

        return

    embed = discord.Embed(
        title="🛡️ BASE DAMAGE SETTINGS",
        description=f"Base damage turned {state.upper()}.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

    print(f"BASE DAMAGE {state.upper()}")

# =========================================================
# SCHEDULED RESTART LOOP
# =========================================================

RESTART_HOURS = [
    0,
    4,
    8,
    12,
    16,
    20
]

last_restart_hour = None

@tasks.loop(minutes=1)
async def scheduled_restart_loop():

    global last_restart_hour

    now = datetime.now(UTC)

    current_hour = now.hour

    if current_hour not in RESTART_HOURS:
        return

    if last_restart_hour == current_hour:
        return

    last_restart_hour = current_hour

    print(f"SCHEDULED RESTART TRIGGERED {current_hour}:00")

    for guild_id, config in guild_configs.items():

        try:

            channels = config.get("channels", {})

            announce_channel = bot.get_channel(
                channels.get("connections")
            )

            if announce_channel:

                embed = discord.Embed(
                    title="⚠️ SCHEDULED RESTART",
                    description="Server restart triggered automatically.",
                    color=0xE74C3C
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                await announce_channel.send(
                    embed=style_embed(embed)
                )

        except Exception as error:

            print(error)

# =========================================================
# AI ALERT SYSTEM
# =========================================================

AI_KEYWORDS = [
    "raid",
    "explosive",
    "helicrash",
    "admin",
    "cheater",
    "speedhack",
    "base damage"
]

async def send_ai_alert(guild_id, config, line):

    channels = config.get("channels", {})

    ai_channel = bot.get_channel(
        channels.get("connections")
    )

    if not ai_channel:
        return

    embed = discord.Embed(
        title="🧠 AI ALERT",
        description=line,
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ai_channel.send(
        embed=style_embed(embed)
    )

# =========================================================
# LIVE SERVER STATUS
# =========================================================

@bot.command()
async def serverstatus(ctx):

    total_guilds = len(guild_configs)

    total_players = len(online_players)

    embed = discord.Embed(
        title="📡 WANDERING BOT STATUS",
        color=0x3498DB
    )

    embed.add_field(
        name="Connected Servers",
        value=str(total_guilds),
        inline=True
    )

    embed.add_field(
        name="Tracked Players",
        value=str(total_players),
        inline=True
    )

    embed.add_field(
        name="ADM Parser",
        value="🟢 ONLINE",
        inline=False
    )

    embed.add_field(
        name="API Status",
        value="🟢 CONNECTED",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# PLAYER LOOKUP
# =========================================================

@bot.command()
async def playerstats(ctx, *, player_name: str):

    if player_name not in player_stats:

        await ctx.send(
            "Player not found."
        )

        return

    stats = player_stats[player_name]

    embed = discord.Embed(
        title=f"📊 PLAYER STATS - {player_name}",
        color=0x1ABC9C
    )

    embed.add_field(
        name="Kills",
        value=str(stats.get("kills", 0)),
        inline=True
    )

    embed.add_field(
        name="Deaths",
        value=str(stats.get("deaths", 0)),
        inline=True
    )

    embed.add_field(
        name="Raids",
        value=str(stats.get("raids", 0)),
        inline=True
    )

    embed.add_field(
        name="Builds",
        value=str(stats.get("builds", 0)),
        inline=True
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# AUTO START TASKS
# =========================================================

async def start_background_tasks():

    try:

        if not adm_loop.is_running():
            adm_loop.start()

        if not scheduled_restart_loop.is_running():
            scheduled_restart_loop.start()

    except RuntimeError:
        pass

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
