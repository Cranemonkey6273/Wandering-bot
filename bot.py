# =========================
# WANDERING BOT V2
# MULTI GUILD EDITION
# =========================

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

# =========================
# ENV
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# FILES
# =========================

GUILD_CONFIG_FILE = "guild_configs.json"
SWEAR_JAR_FILE = "swear_jar.json"
PLAYER_STATS_FILE = "player_stats.json"
HEATMAP_FILE = "heatmap.json"

# =========================
# GLOBALS
# =========================

guild_configs = {}
swear_jar = {}
player_stats = {}
territory_heat = {}

processed_lines = set()
online_players = set()

# =========================
# RADAR
# =========================

RADAR_ZONES = [
    {"name": "NEAF", "x": 12100, "z": 12500, "radius": 500},
    {"name": "TISY", "x": 1700, "z": 14100, "radius": 700},
    {"name": "KOMETA", "x": 10350, "z": 2450, "radius": 500},
]

player_last_radar_ping = {}
player_positions = {}

# =========================
# SWEARS
# =========================

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "bollocks",
]

# =========================
# HELPERS
# =========================

def style_embed(embed):
    embed.timestamp = datetime.now(UTC)
    return embed


def save_json(filename, data):
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as error:
        print(f"SAVE ERROR: {filename}")
        print(error)


def load_json(filename):
    try:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
    except Exception as error:
        print(f"LOAD ERROR: {filename}")
        print(error)

    return {}


def save_guild_configs():
    save_json(GUILD_CONFIG_FILE, guild_configs)


def load_all_data():
    global guild_configs
    global swear_jar
    global player_stats
    global territory_heat

    guild_configs = load_json(GUILD_CONFIG_FILE)
    swear_jar = load_json(SWEAR_JAR_FILE)
    player_stats = load_json(PLAYER_STATS_FILE)
    territory_heat = load_json(HEATMAP_FILE)


def ensure_player(player_name):
    if player_name not in player_stats:
        player_stats[player_name] = {
            "kills": 0,
            "deaths": 0,
            "raids": 0,
            "builds": 0,
        }


def distance(x1, z1, x2, z2):
    return ((x2 - x1) ** 2 + (z2 - z1) ** 2) ** 0.5


# =========================
# AUTO GUILD SETUP
# =========================

@bot.event
async def on_guild_join(guild):

    print(f"JOINED NEW GUILD: {guild.name}")

    existing = guild_configs.get(str(guild.id))

    if existing:
        return

    category = await guild.create_category("📡 WANDERING BOT")

    killfeed_channel = await guild.create_text_channel(
        "🔥・killfeed",
        category=category
    )

    deaths_channel = await guild.create_text_channel(
        "☠️・deaths",
        category=category
    )

    connections_channel = await guild.create_text_channel(
        "🚪・connections",
        category=category
    )

    raids_channel = await guild.create_text_channel(
        "🏴・raids",
        category=category
    )

    building_channel = await guild.create_text_channel(
        "🔨・building",
        category=category
    )

    radar_channel = await guild.create_text_channel(
        "📡・radar",
        category=category
    )

    ai_channel = await guild.create_text_channel(
        "🧠・ai-alerts",
        category=category
    )

    guild_configs[str(guild.id)] = {
        "guild_name": guild.name,
        "nitrado_token": "",
        "service_id": "",
        "channels": {
            "killfeed": killfeed_channel.id,
            "deaths": deaths_channel.id,
            "connections": connections_channel.id,
            "raids": raids_channel.id,
            "building": building_channel.id,
            "radar": radar_channel.id,
            "ai": ai_channel.id,
        }
    }

    save_guild_configs()

    embed = discord.Embed(
        title="📡 WANDERING BOT DEPLOYED",
        description=(
            "Your DayZ Discord systems are now online.\n\n"
            "Next step:\n"
            "Use `/setup` to connect your Nitrado server."
        ),
        color=0x00FFFF
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await killfeed_channel.send(embed=style_embed(embed))


# =========================
# SETUP COMMAND
# =========================

@bot.tree.command(name="setup", description="Connect your Nitrado server")
@app_commands.describe(
    nitrado_token="Your Nitrado API token",
    service_id="Your Nitrado service ID"
)
async def setup_command(
    interaction: discord.Interaction,
    nitrado_token: str,
    service_id: str
):

    guild_id = str(interaction.guild.id)

    if guild_id not in guild_configs:
        await interaction.response.send_message(
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

    await interaction.response.send_message(
        embed=style_embed(embed),
        ephemeral=True
    )


# =========================
# NITRADO API
# =========================

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
        "dir": "/",
        "search": ".ADM",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20
        )

        if response.status_code != 200:
            print(response.text)
            return None

        data = response.json()

        entries = data.get("data", {}).get("entries", [])

        matching_logs = [
            entry for entry in entries
            if entry.get("name", "").endswith(".ADM")
        ]

        if not matching_logs:
            return None

        matching_logs.sort(
            key=lambda x: x.get("modified_at", ""),
            reverse=True
        )

        return matching_logs[0]

    except Exception as error:
        print(error)
        return None


# =========================
# DOWNLOAD ADM
# =========================

def download_adm(config, latest_log, guild_id):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    try:

        url = (
            f"https://api.nitrado.net/services/{service_id}/gameservers/file_server/download"
        )

        headers = {
            "Authorization": f"Bearer {token}"
        }

        params = {
            "file": latest_log.get("path")
        }

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return None

        data = response.json()

        token_url = data.get(
            "data",
            {}
        ).get(
            "token",
            {}
        ).get("url")

        if not token_url:
            return None

        file_response = requests.get(token_url, timeout=30)

        local_file = f"{guild_id}.ADM"

        with open(local_file, "wb") as f:
            f.write(file_response.content)

        return local_file

    except Exception as error:
        print(error)
        return None


# =========================
# EVENT PARSER
# =========================

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

    if "destroyed" in lower or "explosive" in lower:
        return "raid"

    return None


# =========================
# MULTI GUILD ADM LOOP
# =========================

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

            local_file = await asyncio.to_thread(
                download_adm,
                config,
                latest_log,
                guild_id
            )

            if not local_file:
                continue

            await parse_adm(
                guild_id,
                config,
                local_file
            )

        except Exception as error:
            print(f"GUILD LOOP ERROR: {guild_id}")
            print(error)


# =========================
# PARSE ADM
# =========================

async def parse_adm(guild_id, config, local_file):

    if not os.path.exists(local_file):
        return

    channels = config.get("channels", {})

    killfeed_channel = bot.get_channel(
        channels.get("killfeed")
    )

    raids_channel = bot.get_channel(
        channels.get("raids")
    )

    connections_channel = bot.get_channel(
        channels.get("connections")
    )

    radar_channel = bot.get_channel(
        channels.get("radar")
    )

    with open(
        local_file,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()[-50:]

    for raw_line in lines:

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

        print(f"[{guild_id}] EVENT: {event_type}")

        # =====================
        # CONNECTS
        # =====================

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

        # =====================
        # DISCONNECTS
        # =====================

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

        # =====================
        # KILLS
        # =====================

        elif event_type == "kill" and killfeed_channel:

            kill_match = re.search(
                r'Player "([^"]+)" killed Player "([^"]+)" with ([^ ]+)',
                line,
                re.IGNORECASE
            )

            if kill_match:

                killer = kill_match.group(1)
                victim = kill_match.group(2)
                weapon = kill_match.group(3)

                ensure_player(killer)
                ensure_player(victim)

                player_stats[killer]["kills"] += 1
                player_stats[victim]["deaths"] += 1

                save_json(
                    PLAYER_STATS_FILE,
                    player_stats
                )

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

                embed.set_thumbnail(url=BOT_IMAGE)

                await killfeed_channel.send(
                    embed=style_embed(embed)
                )

        # =====================
        # RAIDS
        # =====================

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


# =========================
# SWEAR JAR
# =========================

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
                "balance": 0,
            }

        swear_jar[user_id]["count"] += len(found_words)
        swear_jar[user_id]["balance"] += len(found_words) * 100

        save_json(
            SWEAR_JAR_FILE,
            swear_jar
        )

        embed = discord.Embed(
            title="💸 SWEAR JAR",
            description=(
                f"{message.author.mention} "
                f"was fined £{len(found_words) * 100}"
            ),
            color=0xE67E22
        )

        await message.channel.send(
            embed=style_embed(embed)
        )

    await bot.process_commands(message)


# =========================
# COMMANDS
# =========================

@bot.command()
async def online(ctx):

    if online_players:
        players = "\n".join(
            f"• {x}" for x in online_players
        )
    else:
        players = "No players online."

    embed = discord.Embed(
        title="🟢 ONLINE PLAYERS",
        description=players,
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def topkills(ctx):

    if not player_stats:
        await ctx.send("No stats available.")
        return

    sorted_players = sorted(
        player_stats.items(),
        key=lambda x: x[1]["kills"],
        reverse=True
    )

    lines = [
        f"{i}. {player} - {stats['kills']} kills"
        for i, (player, stats)
        in enumerate(sorted_players[:10], start=1)
    ]

    embed = discord.Embed(
        title="☠️ TOP KILLS",
        description="\n".join(lines),
        color=0x992D22
    )

    await ctx.send(embed=style_embed(embed))


# =========================
# READY
# =========================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    load_all_data()

    try:
        synced = await bot.tree.sync()
        print(f"SYNCED {len(synced)} SLASH COMMANDS")
    except Exception as error:
        print(error)

    if not adm_loop.is_running():
        adm_loop.start()


# =========================
# START
# =========================

bot.run(DISCORD_TOKEN)