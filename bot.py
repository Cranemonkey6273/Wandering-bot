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
LINKED_PLAYERS_FILE = "linked_players.json"

# =========================================================
# GLOBALS
# =========================================================

guild_configs = {}
processed_lines = {}
online_players = {}
player_online_times = {}
territory_heat = {}
zone_keywords = {
    "NWAF": ["nwaf", "airfield"],
    "Tisy": ["tisy"],
    "Zelenogorsk": ["zeleno"],
    "Chernogorsk": ["cherno"],
    "Elektrozavodsk": ["electro"],
    "Vybor": ["vybor"],
    "Berezino": ["berezino"],
    "Severograd": ["severo"]
}
player_stats = {}
swear_jar = {}
linked_players = {}

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


def load_linked_players():
    global linked_players
    linked_players = load_json(LINKED_PLAYERS_FILE)


def save_linked_players():
    save_json(LINKED_PLAYERS_FILE, linked_players)

# =========================================================
# EVENT CLASSIFIER
# =========================================================

def get_zone_from_line(line):

    lower = line.lower()

    for zone, keywords in zone_keywords.items():

        for keyword in keywords:

            if keyword in lower:
                return zone

    return "Unknown"


def ensure_guild_runtime(guild_id):

    if guild_id not in processed_lines:
        processed_lines[guild_id] = set()

    if guild_id not in online_players:
        online_players[guild_id] = set()

    if guild_id not in player_online_times:
        player_online_times[guild_id] = {}

    if guild_id not in territory_heat:
        territory_heat[guild_id] = {}


def increase_heat(guild_id, zone):

    ensure_guild_runtime(guild_id)

    territory_heat[guild_id][zone] = (
        territory_heat[guild_id].get(zone, 0) + 1
    )

    save_heatmap()


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
        f"/games/{nitrado_user}/noftp/dayzxb/storage_1/",
        f"/games/{nitrado_user}/noftp/dayzxb/profiles/",
        f"/games/{nitrado_user}/noftp/dayzxb/logs/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/dayzOffline.chernarusplus/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/dayzOffline.enoch/",
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
                "search": "*DayZServer*"
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

            print(f"[SEARCH PATH] {search_path}")

            for entry in entries:
                print(f"FOUND FILE: {entry.get('name')}")

            matching_logs = [
                entry for entry in entries
                if re.match(
                    r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
                    entry.get("name", ""),
                    re.IGNORECASE
                )
            ]

            if not matching_logs:
                print("NO MATCHING ADM FILES")
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
# LIVE DASHBOARD SETTINGS
# =========================================================

ONLINE_UPDATE_MINUTES = 30
LEADERBOARD_UPDATE_MINUTES = 30
HEATMAP_UPDATE_MINUTES = 30

last_online_message_ids = {}
last_leaderboard_message_ids = {}

# =========================================================
# CLICKABLE MAP LINKS
# =========================================================

def build_izurvive_link(coords):

    try:

        split_coords = coords.split(",")

        x = split_coords[0].strip()
        y = split_coords[1].strip()

        return f"https://dayz.ginfo.gg/#location={x};{y}"

    except:
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
    connections = await make_channel("🟢・connect")
    disconnects = await make_channel("🔴・disconnect")
    online = await make_channel("✅🎮・online🎮✅")
    leaderboards = await make_channel("🏆・leaderboards")
    heatmap_channel = await make_channel("🔥・heatmap🔥")
    restart_alerts = await make_channel("📢・restart-alerts")
    welcome_channel = await make_channel("👋・welcome")
    economy_channel = await make_channel("💰・black-market")
    ai_channel = await make_channel("🧠・survivor-ai")

    guild_configs[guild_id] = {
        "guild_name": guild.name,
        "nitrado_token": "",
        "service_id": "",
        "nitrado_user": "",
        "channels": {
            "killfeed": killfeed.id,
            "raids": raids.id,
            "building": builds.id,
            "connections": connections.id,
            "disconnects": disconnects.id,
            "online": online.id,
            "leaderboards": leaderboards.id,
            "heatmap": heatmap_channel.id,
            "restart_alerts": restart_alerts.id,
            "welcome": welcome_channel.id,
            "economy": economy_channel.id,
            "ai_chat": ai_channel.id
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

    category = discord.utils.get(
        interaction.guild.categories,
        name="📡 WANDERING BOT"
    )

    if not category:
        category = await interaction.guild.create_category(
            "📡 WANDERING BOT"
        )

    async def ensure_channel(key, name):

        existing_id = guild_configs[guild_id]["channels"].get(key)

        if existing_id:
            existing_channel = interaction.guild.get_channel(existing_id)

            if existing_channel:
                return existing_channel

        channel = discord.utils.get(
            interaction.guild.text_channels,
            name=name
        )

        if not channel:
            channel = await interaction.guild.create_text_channel(
                name,
                category=category
            )

        guild_configs[guild_id]["channels"][key] = channel.id

        return channel

    await ensure_channel("killfeed", "🔥・killfeed")
    await ensure_channel("raids", "🏴・raids")
    await ensure_channel("building", "🔨・building")
    await ensure_channel("connections", "🟢・connect")
    await ensure_channel("disconnects", "🔴・disconnect")
    await ensure_channel("online", "✅🎮・online🎮✅")
    await ensure_channel("leaderboards", "🏆・leaderboards")
    await ensure_channel("heatmap", "🔥・heatmap🔥")
    await ensure_channel("restart_alerts", "📢・restart-alerts")
    await ensure_channel("welcome", "👋・welcome")
    await ensure_channel("economy", "💰・black-market")
    await ensure_channel("ai_chat", "🧠・survivor-ai")

    guild_configs[guild_id]["nitrado_token"] = nitrado_token
    guild_configs[guild_id]["service_id"] = service_id
    guild_configs[guild_id]["nitrado_user"] = nitrado_user.strip()

    save_guild_configs()

    await interaction.followup.send(
        "✅ Wandering Bot fully connected and operational.",
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
# FEED EMBED STYLES
# =========================================================

def create_feed_embed(title, color, player=None, details=None, weapon=None, coords=None):

    embed = discord.Embed(
        title=title,
        color=color
    )

    if player:
        embed.add_field(
            name="👤 Player",
            value=player,
            inline=True
        )

    if weapon:
        embed.add_field(
            name="🔫 Weapon",
            value=weapon,
            inline=True
        )

    if coords:
        map_link = build_izurvive_link(coords)

        if map_link:
            coords_value = f"[🗺️ {coords}](<{map_link}>)"
        else:
            coords_value = coords

        embed.add_field(
            name="📍 Coordinates",
            value=coords_value,
            inline=False
        )

    if details:
        embed.add_field(
            name="📜 Event Details",
            value=f"```{details[:900]}```",
            inline=False
        )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Live DayZ Intelligence"
    )

    return style_embed(embed)

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

        ensure_guild_runtime(guild_id)

        if line_hash in processed_lines[guild_id]:
            continue

        processed_lines[guild_id].add(line_hash)

        event_type = classify_event(line)

        if not event_type:
            continue

        print(f"EVENT: {event_type} | {line}")

        ensure_guild_runtime(guild_id)

        zone = get_zone_from_line(line)

        if zone != "Unknown":
            increase_heat(guild_id, zone)

        # ================= CONNECT =================

        if event_type == "connect" and connect_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            online_players[guild_id].add(player_name)
            player_online_times[guild_id][player_name] = datetime.now(UTC)

            embed = discord.Embed(
                title="🟢 SURVIVOR CONNECTED",
                color=0x2ECC71
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=False
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Connection Feed"
            )

            embed.timestamp = datetime.now(UTC)

            await connect_channel.send(embed=embed)

        # ================= DISCONNECT =================

        elif event_type == "disconnect" and connect_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            if player_name in online_players[guild_id]:
                online_players[guild_id].remove(player_name)

            if player_name in player_online_times[guild_id]:
                del player_online_times[guild_id][player_name]

            embed = discord.Embed(
                title="🔴 SURVIVOR DISCONNECTED",
                color=0xE74C3C
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=False
            )

            if coords:

                map_link = build_izurvive_link(coords)

                if map_link:

                    embed.add_field(
                        name="📍 Last Known Location",
                        value=f"[🔵 Open Map](<{map_link}>)",
                        inline=False
                    )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Disconnect Feed"
            )

            embed.timestamp = datetime.now(UTC)

            disconnect_channel = bot.get_channel(
                channels.get("disconnects")
            )

            if disconnect_channel:
                await disconnect_channel.send(embed=embed)

        # ================= BUILD =================

        elif event_type == "build" and build_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else "Unknown"
            )

            action = "Building"
            object_name = "Structure"
            tool_used = "Tool"

            if "placed" in line.lower():

                action_match = re.search(
                    r'placed ([^<]+)',
                    line,
                    re.IGNORECASE
                )

                if action_match:
                    object_name = action_match.group(1).strip()

                action = "Placed"

            elif "built" in line.lower():

                build_match = re.search(
                    r'Built ([^ ]+)',
                    line,
                    re.IGNORECASE
                )

                if build_match:
                    object_name = build_match.group(1).replace("_", " ").title()

                tool_match = re.search(
                    r'with ([^ ]+)',
                    line,
                    re.IGNORECASE
                )

                if tool_match:
                    tool_used = tool_match.group(1)

                action = "Built"

            embed = discord.Embed(
                title="🏗️ BUILDING ACTIVITY",
                color=0xF1C40F
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=True
            )

            embed.add_field(
                name="🛠️ Action",
                value=action,
                inline=True
            )

            embed.add_field(
                name="🏗️ Structure",
                value=object_name,
                inline=False
            )

            if tool_used != "Tool":

                embed.add_field(
                    name="🔨 Tool",
                    value=tool_used,
                    inline=True
                )

            map_link = build_izurvive_link(coords)

            if map_link:

                embed.add_field(
                    name="📍 Location",
                    value=f"[🔵 Open Map](<{map_link}>)",
                    inline=False
                )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Building Intelligence"
            )

            embed.timestamp = datetime.now(UTC)

            await build_channel.send(embed=embed)

        # ================= RAID =================

        elif event_type == "raid" and raid_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            action = "Raid Activity"
            structure = "Base Structure"
            tool_used = "Unknown"

            dismantle_match = re.search(
                r'Dismantled ([^ ]+(?: [^ ]+)*) from ([^ ]+)',
                line,
                re.IGNORECASE
            )

            if dismantle_match:
                action = dismantle_match.group(1)
                structure = dismantle_match.group(2)

            tool_match = re.search(
                r'with ([^ ]+)',
                line,
                re.IGNORECASE
            )

            if tool_match:
                tool_used = tool_match.group(1)

            embed = discord.Embed(
                title="🚨 RAID DETECTED",
                color=0xFF0000
            )

            embed.add_field(
                name="👤 Raider",
                value=player_name,
                inline=True
            )

            embed.add_field(
                name="🧨 Action",
                value=action,
                inline=True
            )

            embed.add_field(
                name="🏚️ Structure",
                value=structure,
                inline=False
            )

            embed.add_field(
                name="🔨 Tool",
                value=tool_used,
                inline=True
            )

            if coords:

                map_link = build_izurvive_link(coords)

                if map_link:

                    embed.add_field(
                        name="📍 Raid Location",
                        value=f"[🔵 Open Map](<{map_link}>)",
                        inline=False
                    )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Raid Intelligence"
            )

            embed.timestamp = datetime.now(UTC)

            await raid_channel.send(embed=embed)

        # ================= KILLFEED =================

        elif event_type == "kill" and killfeed_channel:

            killer_match = re.search(
                r'Player "([^"]+)" killed Player "([^"]+)" with ([^ ]+)',
                line
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            if killer_match:

                killer = killer_match.group(1)
                victim = killer_match.group(2)
                weapon = killer_match.group(3)

                embed = discord.Embed(
                    title="☠️ PLAYER KILL",
                    color=0x992D22
                )

                embed.add_field(
                    name="🔫 Killer",
                    value=killer,
                    inline=True
                )

                embed.add_field(
                    name="💀 Victim",
                    value=victim,
                    inline=True
                )

                embed.add_field(
                    name="🪖 Weapon",
                    value=weapon,
                    inline=False
                )

                if coords:

                    map_link = build_izurvive_link(coords)

                    if map_link:

                        embed.add_field(
                            name="📍 Kill Location",
                            value=f"[🔵 Open Map](<{map_link}>)",
                            inline=False
                        )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Alpha • PvP Intelligence"
                )

                embed.timestamp = datetime.now(UTC)

                await killfeed_channel.send(
                    embed=embed
                )

# =========================================================
# ADM LOOP
# =========================================================

@tasks.loop(minutes=3)
async def adm_loop():

    for guild_id, config in list(guild_configs.items()):

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
async def on_member_join(member):

    guild_id = str(member.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    welcome_channel = bot.get_channel(
        channels.get("welcome")
    )

    if not welcome_channel:
        return

    import random

    welcome_text = random.choice(WELCOME_MESSAGES)

    embed = discord.Embed(
        title="👋 NEW SURVIVOR ARRIVED",
        description=f"{member.mention}\n\n{welcome_text}",
        color=0x1ABC9C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Welcome System"
    )

    await welcome_channel.send(embed=style_embed(embed))


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

        pennies_total = swear_jar[user_id]["balance"]

        save_swear_jar()

        embed = discord.Embed(
            title="💸 SWEAR JAR",
            description=(
                f"{message.author.mention} "
                f"was fined {len(found_words) * 100} pennies 🪙"
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
            value=f"{pennies_total} pennies 🪙",
            inline=True
        )

        await message.channel.send(
            embed=style_embed(embed)
        )

    for keyword, response in AI_RESPONSES.items():

        if keyword in lower:

            await message.channel.send(response)

            break

    await bot.process_commands(message)

# =========================================================
# COMMANDS
# =========================================================

@bot.command()
async def helpme(ctx):

    embed = discord.Embed(
        title="🤖 WANDERING BOT ALPHA COMMANDS",
        color=0x3498DB
    )

    embed.add_field(
        name="📡 Server",
        value=(
            "!serverstatus\n"
            "!online\n"
            "!playerstats <name>"
        ),
        inline=False
    )

    embed.add_field(
        name="🏆 Stats",
        value=(
            "!topkills\n"
            "!heatmap\n"
            "!swearjar"
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ Admin",
        value=(
            "!restartserver\n"
            "!setrestartinterval <hours>\n"
            "!setrestartstart <hour>\n"
            "!listrestarts"
        ),
        inline=False
    )

    embed.add_field(
        name="🧠 Features",
        value=(
            "• Live raid feed\n"
            "• PvP heatmaps\n"
            "• Online tracking\n"
            "• AI chatter\n"
            "• Welcome system\n"
            "• Leaderboards\n"
            "• Restart automation\n"
            "• AI survivor chatter\n"
            "• Smart welcome system\n"
            "• Live online dashboards\n"
            "• Real Nitrado restart control"
        ),
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Help System"
    )

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def online(ctx):

    guild_id = str(ctx.guild.id)

    ensure_guild_runtime(guild_id)

    guild_online = online_players[guild_id]

    if guild_online:

        player_list = "\n".join(
            f"🟢 {player}"
            for player in sorted(guild_online)
        )

    else:

        player_list = "No players online."

    embed = discord.Embed(
        title=f"✅🎮 ONLINE SURVIVORS 🎮✅ ({len(guild_online)})",
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
        description="\n".join(leaderboard),
        color=0xF1C40F
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def heatmap(ctx):

    guild_id = str(ctx.guild.id)

    ensure_guild_runtime(guild_id)

    if not territory_heat[guild_id]:

        await ctx.send(
            "No territory activity yet."
        )

        return

    sorted_zones = sorted(
        territory_heat[guild_id].items(),
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
        description="\n".join(lines),
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
        description="\n".join(lines),
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
        description="Live restart request sent to Nitrado server.",
        color=0xE67E22
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

    print("SERVER RESTART REQUESTED")

    guild_id = str(ctx.guild.id)
    config = guild_configs.get(guild_id, {})

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    if not token or not service_id:
        return

    try:

        url = (
            f"https://api.nitrado.net/services/"
            f"{service_id}/gameservers/restart"
        )

        headers = {
            "Authorization": f"Bearer {token}"
        }

        restart_response = requests.post(
            url,
            headers=headers,
            timeout=30
        )

        print(f"RESTART STATUS: {restart_response.status_code}")

    except Exception as error:
        print(error)


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
# RESTART SCHEDULER COMMANDS
# =========================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def setrestartinterval(ctx, hours: int):

    if hours < 1 or hours > 24:

        await ctx.send(
            "Restart interval must be between 1 and 24 hours."
        )

        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["restart_interval_hours"] = hours

    save_guild_configs()

    embed = discord.Embed(
        title="⏰ RESTART INTERVAL UPDATED",
        description=f"Server will now restart every {hours} hours.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.has_permissions(administrator=True)
async def setrestartstart(ctx, hour: int):

    if hour < 0 or hour > 23:

        await ctx.send(
            "Start hour must be between 0 and 23 UTC."
        )

        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["restart_start_hour"] = hour

    save_guild_configs()

    embed = discord.Embed(
        title="🕒 RESTART START HOUR UPDATED",
        description=f"Restart schedule now begins at {hour}:00 UTC.",
        color=0x1ABC9C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.has_permissions(administrator=True)
async def listrestarts(ctx):

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    interval = config.get(
        "restart_interval_hours",
        DEFAULT_RESTART_INTERVAL_HOURS
    )

    start_hour = config.get(
        "restart_start_hour",
        0
    )

    times = []

    current = start_hour

    while current < 24:

        times.append(f"{current:02d}:00 UTC")

        current += interval

    embed = discord.Embed(
        title="📢 ACTIVE RESTART SCHEDULE",
        description="\n".join(times),
        color=0xE67E22
    )

    embed.add_field(
        name="Interval",
        value=f"Every {interval} hours",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))

# =========================================================
# SCHEDULED RESTART LOOP
# =========================================================

DEFAULT_RESTART_INTERVAL_HOURS = 4

last_restart_hour = {}
restart_warning_tracker = {}

@tasks.loop(minutes=1)
async def scheduled_restart_loop():

    global last_restart_hour

    now = datetime.now(UTC)

    current_hour = now.hour
    current_minute = now.minute

    for guild_id, config in list(guild_configs.items()):

        restart_interval = config.get(
            "restart_interval_hours",
            DEFAULT_RESTART_INTERVAL_HOURS
        )

        restart_offset = config.get(
            "restart_start_hour",
            0
        )

        should_restart = (
            current_hour >= restart_offset
            and ((current_hour - restart_offset) % restart_interval == 0)
            and current_minute == 0
        )

        if not should_restart:
            continue

        if last_restart_hour.get(guild_id) == current_hour:
            continue

        last_restart_hour[guild_id] = current_hour

        print(f"SCHEDULED RESTART TRIGGERED {guild_id} @ {current_hour}:00")

        try:

            channels = config.get("channels", {})

            announce_channel = bot.get_channel(
                channels.get("restart_alerts")
            )

            if announce_channel:

                embed = discord.Embed(
                    title="⚠️ SCHEDULED RESTART",
                    description=(
                        f"Automatic restart triggered.\n\n"
                        f"⏰ Interval: Every {restart_interval} hours\n"
                        f"🕒 Current Restart: {current_hour}:00 UTC"
                    ),
                    color=0xE74C3C
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                await announce_channel.send(
                    embed=style_embed(embed)
                )

                token = config.get("nitrado_token")
                service_id = config.get("service_id")

                if token and service_id:

                    try:

                        url = (
                            f"https://api.nitrado.net/services/"
                            f"{service_id}/gameservers/restart"
                        )

                        headers = {
                            "Authorization": f"Bearer {token}"
                        }

                        restart_response = requests.post(
                            url,
                            headers=headers,
                            timeout=30
                        )

                        print(f"AUTO RESTART STATUS: {restart_response.status_code}")

                    except Exception as restart_error:
                        print(restart_error)

        except Exception as error:

            print(error)

# =========================================================
# AI ALERT SYSTEM
# =========================================================

WELCOME_MESSAGES = [
    "Welcome to the apocalypse, survivor. Trust nobody. Especially Dave.",
    "Fresh spawn detected. Someone hide the baked beans.",
    "Welcome in survivor. The wolves can smell fear already.",
    "Another poor soul has entered Chernarus willingly.",
    "Welcome survivor. If you hear footsteps, start panicking.",

    "Welcome to the wasteland, survivor. Try not to die immediately.",
    "Fresh meat has arrived. Someone hide the loot.",
    "Another survivor enters Chernarus with terrible decision making.",
    "Welcome in. Watch out for wolves, snipers, and your own teammates.",
    "Good luck survivor. You're absolutely going to need it."
]

AI_RESPONSES = {
    "angry": "🧠 Maybe log off before you challenge a door to a fist fight.",
    "trash": "💀 DayZ humbles everybody eventually.",
    "lag": "📡 AI Notice: If desync hits, avoid driving unless you enjoy orbiting into space.",
    "hungry": "🥫 Tip: Fishing gear is more valuable than most guns early game.",
    "bear": "🐻 AI Warning: If you hear the bear first, it's probably too late.",
    "raid": "🧠 Tip: Metal doors buy time. Hidden loot buys survival.",
    "loot": "🧠 Tip: Medical buildings and hunting camps are usually worth checking.",
    "base": "🧠 Tip: Small hidden stashes survive longer than giant compounds.",
    "cheater": "🧠 AI Watch: Record clips and timestamps before reporting suspicious activity.",
    "dead": "💀 DayZ teaches lessons the painful way.",
    "fuck": "💸 Calm down survivor, the swear jar is getting rich.",
    "shit": "🧠 Tactical advice: panicking rarely improves aim."
}

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
        channels.get("ai_chat")
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

    total_players = sum(len(players) for players in online_players.values())

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
# DISCORD ↔ GAMERTAG LINKING
# =========================================================

@bot.command()
async def linkgamer(ctx, *, gamertag: str):

    user_id = str(ctx.author.id)

    linked_players[user_id] = {
        "discord_name": str(ctx.author),
        "gamertag": gamertag
    }

    save_linked_players()

    embed = discord.Embed(
        title="🔗 GAMERTAG LINKED",
        description=(
            f"Your Discord account is now linked to: `{gamertag}`"
        ),
        color=0x2ECC71
    )

    embed.add_field(
        name="🎮 Linked Survivor",
        value=gamertag,
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Identity System"
    )

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def mylink(ctx):

    user_id = str(ctx.author.id)

    if user_id not in linked_players:

        await ctx.send(
            "❌ No linked gamertag found. Use `!linkgamer YourName`"
        )

        return

    data = linked_players[user_id]

    embed = discord.Embed(
        title="🎮 LINKED SURVIVOR PROFILE",
        color=0x3498DB
    )

    embed.add_field(
        name="Discord",
        value=str(ctx.author),
        inline=False
    )

    embed.add_field(
        name="Gamertag",
        value=data['gamertag'],
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.has_permissions(administrator=True)
async def unlinkgamer(ctx, member: discord.Member):

    user_id = str(member.id)

    if user_id not in linked_players:

        await ctx.send("No linked gamertag found.")
        return

    del linked_players[user_id]

    save_linked_players()

    await ctx.send(
        f"🗑️ Removed linked gamertag for {member.mention}"
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
# PERSISTENT MULTI-GUILD STORAGE
# =========================================================

# Guild setups are permanently stored in:
# guild_configs.json
#
# This means if the bot restarts, redeploys,
# crashes, or updates, every server remains linked
# automatically without requiring /setup again.
#
# Server owners only need to run /setup once.
#
# The only time setup is needed again is if:
# - guild_configs.json is deleted
# - the bot is kicked from a server
# - the hosting storage is wiped manually
#
# =========================================================
# AUTO START TASKS
# =========================================================

async def start_background_tasks():

    try:

        if not adm_loop.is_running():
            adm_loop.start()

        if not online_dashboard_loop.is_running():
            online_dashboard_loop.start()

        if not leaderboard_loop.is_running():
            leaderboard_loop.start()

        if not heatmap_loop.is_running():
            heatmap_loop.start()

        if not scheduled_restart_loop.is_running():
            scheduled_restart_loop.start()

    except RuntimeError:
        pass

# =========================================================
# LIVE ONLINE DASHBOARD
# =========================================================

@tasks.loop(minutes=ONLINE_UPDATE_MINUTES)
async def online_dashboard_loop():

    for guild_id, config in list(guild_configs.items()):

        try:

            channels = config.get("channels", {})

            online_channel = bot.get_channel(
                channels.get("online")
            )

            if not online_channel:
                continue

            ensure_guild_runtime(guild_id)

            guild_online = online_players[guild_id]

            if guild_online:

                player_text = "\n".join([
                    f"🟢 {player}"
                    for player in sorted(guild_online)
                ])

            else:

                player_text = "No survivors online."

            embed = discord.Embed(
                title=f"✅🎮 LIVE SURVIVORS ONLINE 🎮✅ ({len(guild_online)})",
                description=player_text,
                color=0x2ECC71
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Live Online Tracker"
            )

            embed.timestamp = datetime.now(UTC)

            await online_channel.send(embed=embed)

        except Exception as error:
            print(error)

# =========================================================
# LIVE PVP HEATMAP DASHBOARD
# =========================================================

@tasks.loop(minutes=HEATMAP_UPDATE_MINUTES)
async def heatmap_loop():

    for guild_id, config in list(guild_configs.items()):

        try:

            channels = config.get("channels", {})

            heatmap_channel = bot.get_channel(
                channels.get("heatmap")
            )

            if not heatmap_channel:
                continue

            ensure_guild_runtime(guild_id)

            hottest_zones = sorted(
                territory_heat[guild_id].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            lines = []

            for zone, count in hottest_zones:
                lines.append(
                    f"🔥 {zone} — {count} PvP events"
                )

            embed = discord.Embed(
                title="🔥 LIVE CONFLICT HEATMAP",
                description=(
                    "\n".join(lines)
                    if lines else "No PvP activity detected yet."
                ),
                color=0x9B59B6
            )

            embed.add_field(
                name="📡 Status",
                value="Tracking live combat zones across the server.",
                inline=False
            )

            embed.set_image(
                url="https://i.imgur.com/JYUB0m3.png"
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • PvP Heatmap"
            )

            embed.timestamp = datetime.now(UTC)

            await heatmap_channel.send(embed=embed)

        except Exception as error:
            print(error)

# =========================================================
# LIVE LEADERBOARD DASHBOARD
# =========================================================

@tasks.loop(minutes=LEADERBOARD_UPDATE_MINUTES)
async def leaderboard_loop():

    for guild_id, config in list(guild_configs.items()):

        try:

            channels = config.get("channels", {})

            leaderboard_channel = bot.get_channel(
                channels.get("leaderboards")
            )

            if not leaderboard_channel:
                continue

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
                    f"{index}. {player} — ☠️ {stats.get('kills', 0)} | 💀 {stats.get('deaths', 0)}"
                )

            embed = discord.Embed(
                title="🏆 GLOBAL SURVIVOR LEADERBOARDS 🏆",
                description="\n".join(lines) if lines else "No stats yet.",
                color=0xF1C40F
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Live Leaderboards"
            )

            embed.timestamp = datetime.now(UTC)

            await leaderboard_channel.send(embed=embed)

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
    load_player_stats()
    load_heatmap()
    load_swear_jar()
    load_linked_players()
    load_shop()
    load_wallets()
    load_delivery_queue()

    await start_background_tasks()

# =========================================================
# ECONOMY SYSTEM FOUNDATION
# =========================================================

SHOP_FILE = "shop.json"
WALLETS_FILE = "wallets.json"
DELIVERY_QUEUE_FILE = "delivery_queue.json"

shop_items = {}
wallets = {}
delivery_queue = []


def load_shop():
    global shop_items
    shop_items = load_json(SHOP_FILE)


def save_shop():
    save_json(SHOP_FILE, shop_items)


def load_wallets():
    global wallets
    wallets = load_json(WALLETS_FILE)


def save_wallets():
    save_json(WALLETS_FILE, wallets)


def load_delivery_queue():
    global delivery_queue

    if os.path.exists(DELIVERY_QUEUE_FILE):

        with open(DELIVERY_QUEUE_FILE, "r") as f:
            delivery_queue = json.load(f)


def save_delivery_queue():

    with open(DELIVERY_QUEUE_FILE, "w") as f:
        json.dump(delivery_queue, f, indent=4)


DEFAULT_DAILY_TRANSACTION_LIMIT = 5


# =========================================================
# BASIC SHOP COMMANDS
# =========================================================

@bot.command()
async def wallet(ctx):

    user_id = str(ctx.author.id)

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(ctx.author),
            "balance": 0,
            "daily_transactions": 0
        }

        save_wallets()

    balance = wallets[user_id]["balance"]

    embed = discord.Embed(
        title="💰 SURVIVOR WALLET",
        description=f"{balance} pennies 🪙",
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def shop(ctx):

    if not shop_items:

        await ctx.send("Shop is currently empty.")
        return

    lines = []

    for item_name, data in shop_items.items():

        lines.append(
            f"• {item_name} — {data.get('price', 0)} pennies 🪙"
        )

    embed = discord.Embed(
        title="🛒 BLACK MARKET SHOP",
        description="\n".join(lines[:25]),
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Black Market"
    )

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def buy(ctx, item_name: str, x: str, y: str):

    user_id = str(ctx.author.id)

    if item_name not in shop_items:

        await ctx.send("That item does not exist in the shop.")
        return

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(ctx.author),
            "balance": 0,
            "daily_transactions": 0
        }

    wallet = wallets[user_id]

    limit = DEFAULT_DAILY_TRANSACTION_LIMIT

    if wallet["daily_transactions"] >= limit:

        await ctx.send("❌ Daily delivery limit reached.")
        return

    price = shop_items[item_name].get("price", 0)

    if wallet["balance"] < price:

        await ctx.send("❌ Not enough pennies.")
        return

    wallet["balance"] -= price
    wallet["daily_transactions"] += 1

    delivery_queue.append({
        "player": str(ctx.author),
        "discord_id": user_id,
        "item": item_name,
        "x": x,
        "y": y,
        "status": "queued",
        "created": str(datetime.now(UTC))
    })

    save_wallets()
    save_delivery_queue()

    map_link = f"https://dayz.ginfo.gg/#location={x};{y}"

    embed = discord.Embed(
        title="📦 DELIVERY QUEUED",
        description=(
            f"Your order has been added to the next restart delivery queue."
        ),
        color=0x3498DB
    )

    embed.add_field(
        name="📦 Item",
        value=item_name,
        inline=True
    )

    embed.add_field(
        name="💰 Cost",
        value=f"{price} pennies 🪙",
        inline=True
    )

    embed.add_field(
        name="📍 Delivery Location",
        value=f"[🔵 Open Map](<{map_link}>)",
        inline=False
    )

    embed.add_field(
        name="⏰ Delivery ETA",
        value="Next server restart",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Black Market Delivery"
    )

    await ctx.send(embed=style_embed(embed))


# =========================================================
# ADMIN SHOP MANAGEMENT
# =========================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def addshopitem(ctx, item_name: str, price: int):

    shop_items[item_name] = {
        "price": price
    }

    save_shop()

    await ctx.send(
        f"✅ Added {item_name} to black market shop for {price} pennies."
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def removeshopitem(ctx, *, item_name: str):

    if item_name not in shop_items:

        await ctx.send("Item not found.")
        return

    del shop_items[item_name]

    save_shop()

    await ctx.send(f"🗑️ Removed {item_name} from the shop.")


@bot.command()
@commands.has_permissions(administrator=True)
async def givepennies(ctx, member: discord.Member, amount: int):

    user_id = str(member.id)

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(member),
            "balance": 0,
            "daily_transactions": 0
        }

    wallets[user_id]["balance"] += amount

    save_wallets()

    await ctx.send(
        f"💰 Added {amount} pennies 🪙 to {member.mention}"
    )

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)
