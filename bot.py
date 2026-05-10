import os
import re
import json
import asyncio
import requests
import discord

from supabase import create_client
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
# SUPABASE
# =========================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# CHANNEL IDS
# =========================

ONLINE_CHANNEL_ID = int(os.getenv("ONLINE_CHANNEL_ID", "0"))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", "0"))
RADAR_CHANNEL_ID = int(os.getenv("RADAR_CHANNEL_ID", "0"))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", "0"))
EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", "0"))

RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", "0"))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", "0"))
PLACE_CHANNEL_ID = int(os.getenv("PLACE_CHANNEL_ID", "0"))

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
STATE_FILE = "adm_state.json"
SWEAR_JAR_FILE = "swear_jar.json"
PLAYER_STATS_FILE = "player_stats.json"
HEATMAP_FILE = "heatmap.json"

# =========================
# GLOBALS
# =========================

adm_state = {
    "last_modified": "",
    "last_line": 0,
    "last_text": ""
}

processed_lines = set()
online_players = set()
territory_heat = {}
player_stats = {}
swear_jar = {}

# =========================
# RADAR SYSTEM
# =========================

RADAR_ZONES = []

def load_radar_zones():
    global RADAR_ZONES

    try:
        response = (
            supabase.table("radar_zones")
            .select("*")
            .eq("enabled", True)
            .execute()
        )

        RADAR_ZONES = []

        for zone in response.data:
            RADAR_ZONES.append({
                "name": zone["name"],
                "x": zone["x"],
                "z": zone["z"],
                "radius": zone["radius"]
            })

        print(
            f"LOADED {len(RADAR_ZONES)} RADAR ZONES FROM SUPABASE"
        )

    except Exception as error:
        print("RADAR ZONE LOAD ERROR")
        print(error)

player_last_radar_ping = {}

player_positions = {}

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "wanker",
    "bollocks"
]

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

# =========================
# SAVE STATE
# =========================

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(adm_state, f)
    except Exception as error:
        print("STATE SAVE ERROR")
        print(error)


def load_state():
    global adm_state

    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                adm_state = json.load(f)
            print("STATE LOADED")
    except Exception as error:
        print("STATE LOAD ERROR")
        print(error)

# =========================
# SWEAR JAR
# =========================

def load_swear_jar():
    global swear_jar

    try:
        if os.path.exists(SWEAR_JAR_FILE):
            with open(SWEAR_JAR_FILE, "r") as f:
                swear_jar = json.load(f)
            print("SWEAR JAR LOADED")
    except Exception as error:
        print("SWEAR JAR LOAD ERROR")
        print(error)


def save_swear_jar():
    try:
        with open(SWEAR_JAR_FILE, "w") as f:
            json.dump(swear_jar, f, indent=4)
    except Exception as error:
        print("SWEAR JAR SAVE ERROR")
        print(error)

# =========================
# PLAYER STATS
# =========================

def load_player_stats():
    global player_stats

    try:
        if os.path.exists(PLAYER_STATS_FILE):
            with open(PLAYER_STATS_FILE, "r") as f:
                player_stats = json.load(f)
            print("PLAYER STATS LOADED")
    except Exception as error:
        print("PLAYER STATS LOAD ERROR")
        print(error)


def save_player_stats():
    try:
        with open(PLAYER_STATS_FILE, "w") as f:
            json.dump(player_stats, f, indent=4)
    except Exception as error:
        print("PLAYER STATS SAVE ERROR")
        print(error)

# =========================
# HEATMAP
# =========================

def load_heatmap():
    global territory_heat

    try:
        if os.path.exists(HEATMAP_FILE):
            with open(HEATMAP_FILE, "r") as f:
                territory_heat = json.load(f)
            print("HEATMAP LOADED")
    except Exception as error:
        print("HEATMAP LOAD ERROR")
        print(error)


def save_heatmap():
    try:
        with open(HEATMAP_FILE, "w") as f:
            json.dump(territory_heat, f, indent=4)
    except Exception as error:
        print("HEATMAP SAVE ERROR")
        print(error)

# =========================
# HELPERS
# =========================

def update_player_status(player_name, status):

    try:

        existing = (
            supabase
            .table("online_players")
            .select("*")
            .eq("player_name", player_name)
            .execute()
        )

        if existing.data:

            (
                supabase
                .table("online_players")
                .update({
                    "status": status,
                    "last_seen": datetime.now(UTC).isoformat()
                })
                .eq("player_name", player_name)
                .execute()
            )

        else:

            (
                supabase
                .table("online_players")
                .insert({
                    "player_name": player_name,
                    "status": status,
                    "last_seen": datetime.now(UTC).isoformat()
                })
                .execute()
            )

    except Exception as error:

        print("PLAYER STATUS ERROR")
        print(error)


def style_embed(embed):
    embed.timestamp = datetime.now(UTC)
    return embed


def extract_timestamp(filename):

    match = re.search(
        r"_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.ADM$",
        filename,
        re.IGNORECASE
    )

    if not match:
        return datetime.fromtimestamp(0)

    date_part = match.group(1)

    time_part = match.group(2).replace("-", ":")

    return datetime.fromisoformat(
        f"{date_part}T{time_part}"
    )


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


def ensure_player(player_name):

    if player_name not in player_stats:

        player_stats[player_name] = {
            "kills": 0,
            "deaths": 0,
            "raids": 0,
            "builds": 0
        }


def get_zone_from_line(line):

    lower = line.lower()

    if "nwaf" in lower or "airfield" in lower:
        return "NWAF"

    if "tisy" in lower:
        return "Tisy"

    if "zeleno" in lower:
        return "Zelenogorsk"

    if "cherno" in lower:
        return "Chernogorsk"

    if "electro" in lower:
        return "Elektrozavodsk"

    if "vybor" in lower:
        return "Vybor"

    return "Unknown"


def increase_heat(zone):

    territory_heat[zone] = (
        territory_heat.get(zone, 0) + 1
    )

    save_heatmap()

# =========================
# RADAR HELPERS
# =========================

def distance(x1, z1, x2, z2):
    return ((x2 - x1) ** 2 + (z2 - z1) ** 2) ** 0.5


def get_nearest_zone(x, z):
    closest_zone = None
    closest_distance = float("inf")

    for zone in RADAR_ZONES:
        dist = distance(x, z, zone["x"], zone["z"])
        if dist < closest_distance:
            closest_distance = dist
            closest_zone = zone["name"]

    return closest_zone, round(closest_distance)

# =========================
# API ADM CHECK
# =========================

def ping_latest_adm_log():
    url = (
        f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list"
    )

    headers = {
        "Authorization": f"Bearer {NITRADO_TOKEN}",
        "Accept": "application/json",
    }

    params = {
        "dir": f"/games/{NITRADO_USER}/noftp/{PLATFORM}/config/",
        "search": "*DayZServer*",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)

        if response.status_code != 200:
            print(response.text)
            return None

        data = response.json()

        entries = data.get("data", {}).get("entries", [])

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
            return None

        matching_logs.sort(
            key=lambda entry: extract_timestamp(entry.get("name", "")),
            reverse=True,
        )

        return matching_logs[0]

    except Exception as error:
        print("API ERROR")
        print(error)
        return None

# =========================
# DOWNLOAD ADM
# =========================

def download_latest_adm(latest_log):
    try:
        download_url = (
            f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/download"
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

        if response.status_code != 200:
            return False

        data = response.json()
        token_url = data.get("data", {}).get("token", {}).get("url")

        if not token_url:
            return False

        file_response = requests.get(token_url, timeout=30)

        with open(LOCAL_LOG_FILE, "wb") as f:
            f.write(file_response.content)

        return True

    except Exception as error:
        print("DOWNLOAD ERROR")
        print(error)
        return False

# =========================
# EVENT CLASSIFIER
# =========================

def classify_event(line):
    lower = line.lower()

    if "deloot not placed" in lower:
        return None

    if "disconnected" in lower:
        return "disconnect"

    if "connecting" in lower or "has connected" in lower:
        return "connect"

    if "unconscious" in lower:
        return "unconscious"

    if "regained consciousness" in lower:
        return "conscious"

    if "built" in lower:
        return "build"

    if "placed" in lower:
        return "place"

    if "dismantled" in lower:
        return "dismantle"

    if "hoisted" in lower:
        return "flag_hoist"

    if "lowered" in lower:
        return "flag_lower"

    if "destroyed" in lower or "explosive" in lower:
        return "raid"

    if "killed" in lower:
        return "kill"

    return None

POSITION_REGEX = re.compile(
    r'Player "([^"]+)".*?pos=<([\d\.\-]+),\s*([\d\.\-]+),\s*([\d\.\-]+)>',
    re.IGNORECASE,
)

# =========================
# ADM PARSER
# =========================

async def parse_adm():

    if not os.path.exists(LOCAL_LOG_FILE):
        return

    with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
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
    place_channel = bot.get_channel(PLACE_CHANNEL_ID)

    for raw_line in new_lines:

        line = raw_line.strip()

        if not line:
            continue

        position_match = POSITION_REGEX.search(line)

        if position_match and radar_channel:
            player_name = position_match.group(1)
            x = float(position_match.group(2))
            z = float(position_match.group(3))

            for zone in RADAR_ZONES:
                dist = distance(x, z, zone["x"], zone["z"])

                if dist <= zone["radius"]:
                    key = f"{player_name}_{zone['name']}"

                    now = datetime.now().timestamp()

                    if key not in player_last_radar_ping:
                        player_last_radar_ping[key] = 0

                    cooldown = now - player_last_radar_ping[key]

                    if cooldown >= 300:
                        player_last_radar_ping[key] = now

                        map_url = f"https://dayz.ginfo.gg/chernarusplus/#c={int(x)};{int(z)};3"

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
                            name="📌 Coordinates",
                            value=f"X: {x:.1f}\nZ: {z:.1f}\n\n[🗺️ Open Map]({map_url})",
                            inline=False
                        )

                        embed.set_thumbnail(url=BOT_IMAGE)

                        await radar_channel.send(
                            embed=style_embed(embed)
                        )

        line_hash = hash(line)

        if line_hash in processed_lines:
            continue

        processed_lines.add(line_hash)

        event_type = classify_event(line)

        if not event_type:
            continue

        print(f"EVENT: {event_type} | {line}")

        if event_type == "connect" and connect_channel:

    player_match = re.search(r'Player "([^"]+)"', line)
    player_name = player_match.group(1) if player_match else "Unknown"

    online_players.add(player_name)
    update_player_status(player_name, "online")

    embed = discord.Embed(
        title="🟢 SURVIVOR CONNECTED",
        description=f"**{player_name}** joined the server.",
        color=0x39FF14
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await connect_channel.send(
        embed=style_embed(embed)
    )

# =========================================

elif event_type == "disconnect" and connect_channel:

    player_match = re.search(r'Player "([^"]+)"', line)
    player_name = player_match.group(1) if player_match else "Unknown"

    online_players.discard(player_name)
    update_player_status(player_name, "offline")

    coord_match = POSITION_REGEX.search(line)

    if coord_match:
        x = float(coord_match.group(2))
        z = float(coord_match.group(3))

        map_url = f"https://dayz.ginfo.gg/chernarusplus/#c={int(x)};{int(z)};3"

        coord_text = (
            f"**X:** {x:.1f}\n"
            f"**Z:** {z:.1f}\n\n"
            f"[🗺️ Open Map]({map_url})"
        )

    else:
        coord_text = "Coordinates unavailable."

    embed = discord.Embed(
        title="🔴 SURVIVOR DISCONNECTED",
        description=f"**{player_name}** left the server.",
        color=0xFF3131
    )

    embed.add_field(
        name="📍 Last Known Location",
        value=coord_text,
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await connect_channel.send(
        embed=style_embed(embed)
    )

# =========================================

# =========================================

elif event_type == "unconscious" and event_channel:

    player_match = re.search(
        r'Player "([^"]+)"',
        line
    )

    player_name = (
        player_match.group(1)
        if player_match else "Unknown"
    )

    coord_match = POSITION_REGEX.search(line)

    if coord_match:
        x = float(coord_match.group(2))
        z = float(coord_match.group(3))

        map_url = (
            f"https://dayz.ginfo.gg/chernarusplus/#c={int(x)};{int(z)};3"
        )

        coord_text = (
            f"**X:** {x:.1f}\n"
            f"**Z:** {z:.1f}\n\n"
            f"[🗺️ Open Map]({map_url})"
        )

    else:
        coord_text = "Unknown"

    embed = discord.Embed(
        title="🩸 PLAYER UNCONSCIOUS",
        description=f"**{player_name}** has been knocked unconscious.",
        color=0xFFD000
    )

    embed.add_field(
        name="📍 Location",
        value=coord_text,
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await event_channel.send(
        embed=style_embed(embed)
    )

# =========================================

elif event_type == "conscious" and event_channel:

    player_match = re.search(
        r'Player "([^"]+)"',
        line
    )

    player_name = (
        player_match.group(1)
        if player_match else "Unknown"
    )

    embed = discord.Embed(
        title="💚 PLAYER RECOVERED",
        description=f"**{player_name}** regained consciousness.",
        color=0x00FFCC
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await event_channel.send(
        embed=style_embed(embed)
    )

# =========================================

elif event_type == "build" and build_channel:

    build_match = re.search(
        r'Player "([^"]+)".*?built ([^<]+)',
        line,
        re.IGNORECASE
    )

    if build_match:

        player_name = build_match.group(1)
        build_item = build_match.group(2).strip()

        coord_match = POSITION_REGEX.search(line)

        if coord_match:
            x = float(coord_match.group(2))
            z = float(coord_match.group(3))
        else:
            x = 0
            z = 0

        map_url = f"https://dayz.ginfo.gg/chernarusplus/#c={int(x)};{int(z)};3"

        embed = discord.Embed(
            title="🔨 BUILD EVENT",
            description=f"**{player_name}** built **{build_item}**",
            color=0x57F287
        )

        embed.add_field(
            name="📍 Coordinates",
            value=(
                f"**X:** {x:.1f}\n"
                f"**Z:** {z:.1f}\n\n"
                f"[🗺️ Open Map]({map_url})"
            ),
            inline=False
        )

        embed.set_thumbnail(url=BOT_IMAGE)

        await build_channel.send(
            embed=style_embed(embed)
        )

# =========================================

elif event_type == "dismantle" and raid_channel:

    dismantle_match = re.search(
        r'Player "([^"]+)".*?Dismantled ([^ ]+) from ([^ ]+) with ([^ ]+)',
        line,
        re.IGNORECASE
    )

    if dismantle_match:

        player_name = dismantle_match.group(1)
        dismantled_piece = dismantle_match.group(2)
        dismantled_from = dismantle_match.group(3)
        tool_used = dismantle_match.group(4)

        coord_match = POSITION_REGEX.search(line)

        if coord_match:
            x = float(coord_match.group(2))
            z = float(coord_match.group(3))

            map_url = f"https://dayz.ginfo.gg/chernarusplus/#c={int(x)};{int(z)};3"

            coord_text = (
                f"**X:** {x:.1f}\n"
                f"**Z:** {z:.1f}\n\n"
                f"[🗺️ Open Map]({map_url})"
            )

        else:
            coord_text = "Coordinates unavailable."

        embed = discord.Embed(
            title="🪓 DISMANTLED",
            description=(
                f"**{player_name}** dismantled "
                f"**{dismantled_piece}** from "
                f"**{dismantled_from}** using "
                f"**{tool_used}**"
            ),
            color=0xFF9900
        )

        embed.add_field(
            name="📍 Location",
            value=coord_text,
            inline=False
        )

        embed.set_thumbnail(url=BOT_IMAGE)

        await raid_channel.send(
            embed=style_embed(embed)
        )

# =========================================

elif event_type == "kill" and killfeed_channel:

    kill_match = re.search(
        r'Player "([^"]+)".*?killed by Player "([^"]+)".*?with ([^ ]+).*?from ([\d\.]+)',
        line,
        re.IGNORECASE
    )

    if kill_match:

        victim = kill_match.group(1)
        killer = kill_match.group(2)
        weapon = kill_match.group(3)
        distance = kill_match.group(4)

        coord_match = POSITION_REGEX.search(line)

        if coord_match:
            x = float(coord_match.group(2))
            z = float(coord_match.group(3))

            map_url = f"https://dayz.ginfo.gg/chernarusplus/#c={int(x)};{int(z)};3"

            coord_text = (
                f"**X:** {x:.1f}\n"
                f"**Z:** {z:.1f}\n\n"
                f"[🗺️ Open Map]({map_url})"
            )
        else:
            coord_text = "Unknown"

        embed = discord.Embed(
            title="☠️ PLAYER KILL",
            color=0xBB00FF
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
            value=f"{weapon} ({distance}m)",
            inline=False
        )

        embed.add_field(
            name="📍 Location",
            value=coord_text,
            inline=False
        )

        embed.set_thumbnail(url=BOT_IMAGE)

        await killfeed_channel.send(
            embed=style_embed(embed)
        )

# =========================
# MESSAGE EVENT
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
                "balance": 0
            }

        swear_jar[user_id]["count"] += len(found_words)
        swear_jar[user_id]["balance"] += len(found_words) * 100

        save_swear_jar()

    await bot.process_commands(message)

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

    save_state()

    await parse_adm()

# =========================
# READY
# =========================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    print("========== CHANNEL DEBUG ==========")
    print("ONLINE:", bot.get_channel(ONLINE_CHANNEL_ID))
    print("KILLFEED:", bot.get_channel(KILLFEED_CHANNEL_ID))
    print("RADAR:", bot.get_channel(RADAR_CHANNEL_ID))
    print("BUILD:", bot.get_channel(BUILD_CHANNEL_ID))
    print("EVENT:", bot.get_channel(EVENT_CHANNEL_ID))
    print("RAID:", bot.get_channel(RAID_CHANNEL_ID))
    print("CONNECT:", bot.get_channel(CONNECT_CHANNEL_ID))
    print("PLACE:", bot.get_channel(PLACE_CHANNEL_ID))
    print("===================================")

    load_state()
    load_swear_jar()
    load_player_stats()
    load_heatmap()
    load_radar_zones()

    try:
        adm_loop.start()
    except RuntimeError:
        pass

# =========================
# COMMANDS
# =========================

@bot.command()
async def online(ctx):

    if online_players:
        player_list = "\n".join(
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

    await ctx.send(embed=style_embed(embed))

# =========================
# START
# =========================

bot.run(DISCORD_TOKEN)
