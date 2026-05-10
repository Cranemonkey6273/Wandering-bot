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


async def parse

    lower = line.lower()

    # ================= PLAYER CONNECT =================

    if (
        'player ' in lower
        and ' connecting' in lower
    ):
        return "connect"

    if (
        'player ' in lower
        and 'has connected' in lower
    ):
        return "connect"

    # ================= PLAYER DISCONNECT =================

    if (
        'player ' in lower
        and 'disconnected' in lower
    ):
        return "disconnect"

    # ================= UNCON =================

    if "is unconscious" in lower:
        return "uncon"

    if "regained consciousness" in lower:
        return "recon"

    # ================= FLAG EVENTS =================

    if "hoisted flag" in lower:
        return "flag_hoist"

    if "lowered flag" in lower:
        return "flag_lower"

    # ================= DISMANTLE =================

    if (
        'player "' in lower
        and 'dismantled' in lower
    ):
        return "dismantle"

    # ================= PLACE =================

    if (
        'player "' in lower
        and ' placed ' in lower
    ):
        return "place"

    # ================= BUILD =================

    if (
        'player "' in lower
        and (
            ' built ' in lower
            or ' mounted ' in lower
        )
    ):
        return "build"

    # ================= RAID =================

    if (
        "destroyed" in lower
        or "explosive" in lower
    ):
        return "raid"

    # ================= KILL =================

    if " killed " in lower:
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

    save_state()

    killfeed_channel = bot.get_channel(KILLFEED_CHANNEL_ID)
    raid_channel = bot.get_channel(RAID_CHANNEL_ID)
    build_channel = bot.get_channel(BUILD_CHANNEL_ID)
    connect_channel = bot.get_channel(CONNECT_CHANNEL_ID)
    radar_channel = bot.get_channel(RADAR_CHANNEL_ID)

    for raw_line in new_lines:

        line = raw_line.strip()

        # ================= RADAR =================

        position_match = POSITION_REGEX.search(line)

        if position_match and radar_channel:

            player_name = position_match.group(1)

            x = float(position_match.group(2))
            z = float(position_match.group(3))

            player_positions[player_name] = {
                "x": x,
                "z": z
            }

            for zone in RADAR_ZONES:

                dist = distance(
                    x,
                    z,
                    zone["x"],
                    zone["z"]
                )

                if dist <= zone["radius"]:

                    key = f"{player_name}_{zone['name']}"

                    now = datetime.now().timestamp()

                    if key not in player_last_radar_ping:
                        player_last_radar_ping[key] = 0

                    cooldown = (
                        now
                        - player_last_radar_ping[key]
                    )

                    if cooldown >= 300:

                        player_last_radar_ping[key] = now

                        nearest_zone, nearest_dist = (
                            get_nearest_zone(x, z)
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
                            name="📍 Radar Zone",
                            value=zone["name"],
                            inline=True
                        )

                        embed.add_field(
                            name="📏 Distance",
                            value=f"{dist:.1f}m",
                            inline=True
                        )

                        embed.add_field(
                            name="🗺️ Nearest Area",
                            value=f"{nearest_zone} ({nearest_dist}m)",
                            inline=False
                        )

                        izurvive_url = (
                            f"https://dayz.ginfo.gg/chernarusplus/"
                            f"#c={int(x)};{int(z)};3"
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

                        embed.set_thumbnail(url=BOT_IMAGE)

                        await radar_channel.send(
                            embed=style_embed(embed)
                        )

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

        if (
            event_type == "connect"
            and connect_channel
        ):

            player_match = re.search(
                r'Player "([^"]+)"',
                line,
                re.IGNORECASE
            )

            player_name = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            online_players.add(player_name)

            embed = discord.Embed(
                title="🟢 Survivor Connected",
                color=0x2ECC71
            )

            embed.add_field(
                name="Player",
                value=player_name,
                inline=False
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= DISCONNECT =================

        elif (
            event_type == "disconnect"
            and connect_channel
        ):

            player_match = re.search(
                r'Player "([^"]+)"',
                line,
                re.IGNORECASE
            )

            player_name = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            online_players.discard(player_name)

            embed = discord.Embed(
                title="🔴 Survivor Disconnected",
                color=0xE74C3C
            )

            embed.add_field(
                name="Player",
                value=player_name,
                inline=False
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= PLACE =================

        elif (
            event_type == "place"
            and build_channel
        ):

            place_match = re.search(
                r'Player "([^"]+)".*?placed\s+(.+)',
                line,
                re.IGNORECASE
            )

            if place_match:

                player_name = place_match.group(1)

                placed_item = (
                    place_match.group(2)
                    .split("<")[0]
                    .strip()
                )

                embed = discord.Embed(
                    title="📦 ITEM PLACED",
                    description=(
                        f"**{player_name}** placed "
                        f"**{placed_item}**"
                    ),
                    color=0x3498DB
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                await build_channel.send(
                    embed=style_embed(embed)
                )

        # ================= BUILD =================

        elif (
            event_type == "build"
            and build_channel
        ):

            build_match = re.search(
                r'Player "([^"]+)".*?(built|mounted)\s+(.+)',
                line,
                re.IGNORECASE
            )

            if build_match:

                player_name = build_match.group(1)

                build_item = (
                    build_match.group(3)
                    .split("<")[0]
                    .strip()
                )

                embed = discord.Embed(
                    title="🔨 BUILD EVENT",
                    description=(
                        f"**{player_name}** built "
                        f"**{build_item}**"
                    ),
                    color=0x57F287
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                await build_channel.send(
                    embed=style_embed(embed)
                )

        # ================= DISMANTLE =================

        elif (
            event_type == "dismantle"
            and raid_channel
        ):

            dismantle_match = re.search(
                r'Player "([^"]+)".*?dismantled\s+(.+)',
                line,
                re.IGNORECASE
            )

            if dismantle_match:

                player_name = dismantle_match.group(1)

                dismantled_item = (
                    dismantle_match.group(2)
                    .split("<")[0]
                    .strip()
                )

                embed = discord.Embed(
                    title="🪓 DISMANTLE EVENT",
                    description=(
                        f"**{player_name}** dismantled "
                        f"**{dismantled_item}**"
                    ),
                    color=0xE67E22
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                await raid_channel.send(
                    embed=style_embed(embed)
                )

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
