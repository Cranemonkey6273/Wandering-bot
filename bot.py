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

# =========================
# ENV VARIABLES
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NITRADO_TOKEN = os.getenv("NITRADO_API_TOKEN")

SERVICE_ID = "18965708"
NITRADO_USER = "ni12248929_1"
PLATFORM = "dayzxb"

# =========================
# CHANNEL IDS
# =========================

KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
PLACE_CHANNEL_ID = int(os.getenv("PLACE_CHANNEL_ID", 0))
DISMANTLE_CHANNEL_ID = int(os.getenv("DISMANTLE_CHANNEL_ID", 0))
FLAG_CHANNEL_ID = int(os.getenv("FLAG_CHANNEL_ID", 0))
UNCON_CHANNEL_ID = int(os.getenv("UNCON_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))
RADAR_CHANNEL_ID = int(os.getenv("RADAR_CHANNEL_ID", 0))

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================
# FILES
# =========================

LOCAL_LOG_FILE = "live.ADM"

# =========================
# GLOBALS
# =========================

adm_state = {
    "last_modified": "",
    "last_line": 0
}

processed_lines = set()
online_players = set()

# =========================
# RADAR SYSTEM
# =========================

RADAR_ZONES = [
    {"name": "TEST", "x": 7500, "z": 7500, "radius": 20000},
    {"name": "NEAF", "x": 12100, "z": 12500, "radius": 500},
    {"name": "TISY", "x": 1700, "z": 14100, "radius": 700},
    {"name": "KOMETA", "x": 10350, "z": 2450, "radius": 500},
]

player_last_radar_ping = {}

BOT_IMAGE = (
    "https://media.discordapp.net/"
    "attachments/1499787777636831324/"
    "1501685742433206342/"
    "7A382429-B666-4A9F-B890-17C0F7981709.png"
)

# =========================
# HELPERS
# =========================

def style_embed(embed):
    embed.timestamp = datetime.now(UTC)
    return embed


def classify_event(line):

    lower = line.lower()

    if "disconnected" in lower:
        return "disconnect"

    if "connecting" in lower or "connected" in lower:
        return "connect"

    if "regained consciousness" in lower:
        return "recon"

    if "unconscious" in lower:
        return "uncon"

    if "lowered flag" in lower:
        return "flag_lower"

    if "hoisted flag" in lower:
        return "flag_hoist"

    if "dismantled" in lower:
        return "dismantle"

    if "placed" in lower:
        return "place"

    if "built" in lower or "mounted" in lower:
        return "build"

    if "destroyed" in lower or "explosive" in lower:
        return "raid"

    if "killed" in lower:
        return "kill"

    return None


def parse_kill_event(line):

    match = re.search(
        r'Player "([^"]+)" killed Player "([^"]+)" with ([^ ]+)',
        line,
        re.IGNORECASE
    )

    if not match:
        return None

    return {
        "killer": match.group(1),
        "victim": match.group(2),
        "weapon": match.group(3)
    }

# =========================
# RADAR POSITION PARSER
# =========================

POSITION_REGEX = re.compile(
    r'Player "([^"]+)".*?pos=<([\d\.\-]+),\s*([\d\.\-]+),\s*([\d\.\-]+)>',
    re.IGNORECASE
)

# =========================
# API
# =========================

def ping_latest_adm_log():

    url = (
        f"https://api.nitrado.net/services/"
        f"{SERVICE_ID}/gameservers/file_server/list"
    )

    headers = {
        "Authorization": f"Bearer {NITRADO_TOKEN}",
        "Accept": "application/json"
    }

    params = {
        "dir": (
            f"/games/{NITRADO_USER}/"
            f"noftp/{PLATFORM}/config/"
        ),
        "search": "*DayZServer*"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20
        )

        if response.status_code != 200:
            return None

        data = response.json()

        entries = data.get("data", {}).get("entries", [])

        if not entries:
            return None

        return sorted(
            entries,
            key=lambda x: x.get("modified_at", ""),
            reverse=True
        )[0]

    except Exception as error:
        print(error)
        return None


def download_latest_adm(latest_log):

    try:

        download_url = (
            f"https://api.nitrado.net/services/"
            f"{SERVICE_ID}/gameservers/file_server/download"
        )

        headers = {
            "Authorization": f"Bearer {NITRADO_TOKEN}"
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

        data = response.json()

        token_url = (
            data
            .get("data", {})
            .get("token", {})
            .get("url")
        )

        if not token_url:
            return False

        file_response = requests.get(
            token_url,
            timeout=30
        )

        with open(LOCAL_LOG_FILE, "wb") as f:
            f.write(file_response.content)

        return True

    except Exception as error:
        print(error)
        return False

# =========================
# ADM PARSER
# =========================

async def parse_adm():

    if not os.path.exists(LOCAL_LOG_FILE):
        return

    with open(
        LOCAL_LOG_FILE,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

    start_index = adm_state.get("last_line", 0)
    new_lines = lines[start_index:]

    adm_state["last_line"] = len(lines)

    killfeed_channel = bot.get_channel(KILLFEED_CHANNEL_ID)
    raid_channel = bot.get_channel(RAID_CHANNEL_ID)
    build_channel = bot.get_channel(BUILD_CHANNEL_ID)
    place_channel = bot.get_channel(PLACE_CHANNEL_ID)
    dismantle_channel = bot.get_channel(DISMANTLE_CHANNEL_ID)
    flag_channel = bot.get_channel(FLAG_CHANNEL_ID)
    uncon_channel = bot.get_channel(UNCON_CHANNEL_ID)
    connect_channel = bot.get_channel(CONNECT_CHANNEL_ID)
    radar_channel = bot.get_channel(RADAR_CHANNEL_ID)

    for raw_line in new_lines:

        line = raw_line.strip()

        if not line:
            continue

        # ================= RADAR =================

        position_match = POSITION_REGEX.search(line)

        if position_match and radar_channel:

            player_name = position_match.group(1)

            x = float(position_match.group(2))
            z = float(position_match.group(3))

            for zone in RADAR_ZONES:

                dist = (
                    (
                        (zone["x"] - x) ** 2
                        +
                        (zone["z"] - z) ** 2
                    ) ** 0.5
                )

                if dist <= zone["radius"]:

                    key = f"{player_name}_{zone['name']}"
                    now = datetime.now().timestamp()

                    if key not in player_last_radar_ping:
                        player_last_radar_ping[key] = 0

                    cooldown = (
                        now -
                        player_last_radar_ping[key]
                    )

                    if cooldown >= 300:

                        player_last_radar_ping[key] = now

                        izurvive_url = (
                            f"https://dayz.ginfo.gg/chernarusplus/"
                            f"#c={int(x)};{int(z)};3"
                        )

                        embed = discord.Embed(
                            title="📡 RADAR PING",
                            color=0x00FFFF
                        )

                        embed.add_field(
                            name="👤 Player",
                            value=player_name,
                            inline=False
                        )

                        embed.add_field(
                            name="📍 Zone",
                            value=zone["name"],
                            inline=True
                        )

                        embed.add_field(
                            name="📏 Distance",
                            value=f"{dist:.1f}m",
                            inline=True
                        )

                        embed.add_field(
                            name="📌 Coordinates",
                            value=(
                                f"X: {x:.1f}\n"
                                f"Z: {z:.1f}\n\n"
                                f"[🗺️ Open Map]({izurvive_url})"
                            ),
                            inline=False
                        )

                        embed.set_thumbnail(
                            url=BOT_IMAGE
                        )

                        await radar_channel.send(
                            embed=style_embed(embed)
                        )

        # ================= EVENTS =================

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

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            online_players.add(player_name)

            embed = discord.Embed(
                title="🟢 Survivor Connected",
                description=player_name,
                color=0x2ECC71
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= DISCONNECT =================

        elif event_type == "disconnect" and connect_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            online_players.discard(player_name)

            embed = discord.Embed(
                title="🔴 Survivor Disconnected",
                description=player_name,
                color=0xE74C3C
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= PLACE =================

        elif event_type == "place" and place_channel:

            place_match = re.search(
                r'Player "([^"]+)".*?placed ([^<]+)',
                line,
                re.IGNORECASE
            )

            if place_match:
                player_name = place_match.group(1)
                item = place_match.group(2).strip()
            else:
                player_name = "Unknown"
                item = "Object"

            embed = discord.Embed(
                title="📦 ITEM PLACED",
                description=(
                    f"**{player_name}** "
                    f"placed **{item}**"
                ),
                color=0x3498DB
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await place_channel.send(
                embed=style_embed(embed)
            )

        # ================= BUILD =================

        elif event_type == "build" and build_channel:

            embed = discord.Embed(
                title="🔨 BUILD EVENT",
                description=line,
                color=0x57F287
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await build_channel.send(
                embed=style_embed(embed)
            )

        # ================= DISMANTLE =================

        elif event_type == "dismantle" and dismantle_channel:

            embed = discord.Embed(
                title="🪓 DISMANTLED",
                description=line,
                color=0xE67E22
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await dismantle_channel.send(
                embed=style_embed(embed)
            )

        # ================= FLAG HOIST =================

        elif event_type == "flag_hoist" and flag_channel:

            embed = discord.Embed(
                title="🚩 FLAG HOISTED",
                description=line,
                color=0x2ECC71
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await flag_channel.send(
                embed=style_embed(embed)
            )

        # ================= FLAG LOWER =================

        elif event_type == "flag_lower" and flag_channel:

            embed = discord.Embed(
                title="🏴 FLAG LOWERED",
                description=line,
                color=0xE74C3C
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await flag_channel.send(
                embed=style_embed(embed)
            )

        # ================= UNCON =================

        elif event_type == "uncon" and uncon_channel:

            embed = discord.Embed(
                title="😵 PLAYER UNCONSCIOUS",
                description=line,
                color=0xE67E22
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await uncon_channel.send(
                embed=style_embed(embed)
            )

        # ================= REGAINED =================

        elif event_type == "recon" and uncon_channel:

            embed = discord.Embed(
                title="🩺 PLAYER RECOVERED",
                description=line,
                color=0x2ECC71
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await uncon_channel.send(
                embed=style_embed(embed)
            )

        # ================= RAID =================

        elif event_type == "raid" and raid_channel:

            embed = discord.Embed(
                title="🚨 RAID EVENT",
                description=line,
                color=0xFF0000
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await raid_channel.send(
                embed=style_embed(embed)
            )

        # ================= KILL =================

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

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await killfeed_channel.send(
                embed=style_embed(embed)
            )

# =========================
# LOOP
# =========================

@tasks.loop(minutes=3)
async def adm_loop():

    latest_log = await asyncio.to_thread(
        ping_latest_adm_log
    )

    if not latest_log:
        return

    modified_at = latest_log.get("modified_at")

    if modified_at == adm_state.get("last_modified"):
        return

    download_success = await asyncio.to_thread(
        download_latest_adm,
        latest_log
    )

    if not download_success:
        return

    adm_state["last_modified"] = modified_at

    await parse_adm()

# =========================
# READY
# =========================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    try:
        adm_loop.start()
    except RuntimeError:
        pass

# =========================
# ONLINE COMMAND
# =========================

@bot.command()
async def online(ctx):

    if online_players:

        player_list = "\n".join(
            sorted(online_players)
        )

    else:

        player_list = "No players online."

    embed = discord.Embed(
        title=(
            f"🟢 ONLINE PLAYERS "
            f"({len(online_players)})"
        ),
        description=player_list,
        color=0x2ECC71
    )

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================
# START
# =========================

bot.run(DISCORD_TOKEN)
