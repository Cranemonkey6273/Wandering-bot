import os
import re
import json
import asyncio
import requests
import discord

from datetime import datetime, UTC
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

KILLFEED_CHANNEL_ID = int(
    os.getenv("KILLFEED_CHANNEL_ID", 0)
)

RAID_CHANNEL_ID = int(
    os.getenv("RAID_CHANNEL_ID", 0)
)

BUILD_CHANNEL_ID = int(
    os.getenv("BUILD_CHANNEL_ID", 0)
)

CONNECT_CHANNEL_ID = int(
    os.getenv("CONNECT_CHANNEL_ID", 0)
)

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

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "wanker",
    "bollocks"
]

BOT_IMAGE = (
    "https://media.discordapp.net/"
    "attachments/1499787777636831324/"
    "1501685742433206342/"
    "7A382429-B666-4A9F-B890-17C0F7981709.png"
)

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

            with open(
                SWEAR_JAR_FILE,
                "r"
            ) as f:

                swear_jar = json.load(f)

            print("SWEAR JAR LOADED")

    except Exception as error:

        print("SWEAR JAR LOAD ERROR")
        print(error)


def save_swear_jar():

    try:

        with open(
            SWEAR_JAR_FILE,
            "w"
        ) as f:

            json.dump(
                swear_jar,
                f,
                indent=4
            )

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

            with open(
                PLAYER_STATS_FILE,
                "r"
            ) as f:

                player_stats = json.load(f)

            print("PLAYER STATS LOADED")

    except Exception as error:

        print("PLAYER STATS LOAD ERROR")
        print(error)


def save_player_stats():

    try:

        with open(
            PLAYER_STATS_FILE,
            "w"
        ) as f:

            json.dump(
                player_stats,
                f,
                indent=4
            )

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

            with open(
                HEATMAP_FILE,
                "r"
            ) as f:

                territory_heat = json.load(f)

            print("HEATMAP LOADED")

    except Exception as error:

        print("HEATMAP LOAD ERROR")
        print(error)


def save_heatmap():

    try:

        with open(
            HEATMAP_FILE,
            "w"
        ) as f:

            json.dump(
                territory_heat,
                f,
                indent=4
            )

    except Exception as error:

        print("HEATMAP SAVE ERROR")
        print(error)

# =========================
# HELPERS
# =========================

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

    if (
        "nwaf" in lower
        or "airfield" in lower
    ):
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
# API ADM CHECK
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
            f"/games/{NITRADO_USER}"
            f"/noftp/{PLATFORM}"
            f"/config/"
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

        print(
            "[PING] HTTP Status:",
            response.status_code
        )

        if response.status_code != 200:

            print(response.text)

            return None

        data = response.json()

        if data.get("status") != "success":

            print(data)

            return None

        entries = (
            data
            .get("data", {})
            .get("entries", [])
        )

        matching_logs = [

            entry for entry in entries

            if re.match(
                r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
                entry.get("name", ""),
                re.IGNORECASE
            )
        ]

        if not matching_logs:

            print("NO ADM LOGS FOUND")

            return None

        matching_logs.sort(
            key=lambda entry: extract_timestamp(
                entry.get("name", "")
            ),
            reverse=True
        )

        latest_log = matching_logs[0]

        return latest_log

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

        if response.status_code != 200:

            print("DOWNLOAD FAILED")

            print(response.text)

            return False

        data = response.json()

        token_url = (
            data
            .get("data", {})
            .get("token", {})
            .get("url")
        )

        if not token_url:

            print("NO DOWNLOAD URL")

            return False

        file_response = requests.get(
            token_url,
            timeout=30
        )

        with open(
            LOCAL_LOG_FILE,
            "wb"
        ) as f:

            f.write(file_response.content)

        print("ADM DOWNLOADED")

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

    if "disconnected" in lower:
        return "disconnect"

    if (
        "connecting" in lower
        or "connected" in lower
    ):
        return "connect"

    if "killed" in lower:
        return "kill"

    if (
        "placed" in lower
        or "built" in lower
        or "mounted" in lower
    ):
        return "build"

    if (
        "destroyed" in lower
        or "dismantled" in lower
        or "explosive" in lower
    ):
        return "raid"

    return None

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

    start_index = adm_state.get(
        "last_line",
        0
    )

    new_lines = lines[start_index:]

    adm_state["last_line"] = len(lines)

    save_state()

    killfeed_channel = bot.get_channel(
        KILLFEED_CHANNEL_ID
    )

    raid_channel = bot.get_channel(
        RAID_CHANNEL_ID
    )

    build_channel = bot.get_channel(
        BUILD_CHANNEL_ID
    )

    connect_channel = bot.get_channel(
        CONNECT_CHANNEL_ID
    )

    for raw_line in new_lines:

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

        print(
            f"EVENT: {event_type} | {line}"
        )

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

            player_name = "Unknown"

            if player_match:
                player_name = player_match.group(1)

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

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

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

            player_name = "Unknown"

            if player_match:
                player_name = player_match.group(1)

            if player_name in online_players:
                online_players.remove(player_name)

            embed = discord.Embed(
                title="🔴 Survivor Disconnected",
                color=0xE74C3C
            )

            embed.add_field(
                name="Player",
                value=player_name,
                inline=False
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= BUILD =================

        elif (
            event_type == "build"
            and build_channel
        ):

            zone = get_zone_from_line(line)

            increase_heat(zone)

            player_match = re.search(
                r'Player "([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match:

                player_name = player_match.group(1)

                ensure_player(player_name)

                player_stats[player_name]["builds"] += 1

                save_player_stats()

            embed = discord.Embed(
                title="🏗️ BUILD EVENT",
                description=line,
                color=0xF1C40F
            )

            embed.add_field(
                name="📍 Zone",
                value=zone,
                inline=False
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await build_channel.send(
                embed=style_embed(embed)
            )

        # ================= RAID =================

        elif (
            event_type == "raid"
            and raid_channel
        ):

            zone = get_zone_from_line(line)

            increase_heat(zone)

            player_match = re.search(
                r'Player "([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match:

                player_name = player_match.group(1)

                ensure_player(player_name)

                player_stats[player_name]["raids"] += 1

                save_player_stats()

            embed = discord.Embed(
                title="🚨 RAID EVENT",
                description=line,
                color=0xFF0000
            )

            embed.add_field(
                name="📍 Zone",
                value=zone,
                inline=False
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await raid_channel.send(
                embed=style_embed(embed)
            )

        # ================= KILLFEED =================

        elif (
            event_type == "kill"
            and killfeed_channel
        ):

            zone = get_zone_from_line(line)

            increase_heat(zone)

            kill_data = parse_kill_event(line)

            if kill_data:

                killer = kill_data["killer"]
                victim = kill_data["victim"]

                ensure_player(killer)
                ensure_player(victim)

                player_stats[killer]["kills"] += 1
                player_stats[victim]["deaths"] += 1

                save_player_stats()

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
                    value=kill_data["weapon"],
                    inline=False
                )

                embed.add_field(
                    name="📍 Zone",
                    value=zone,
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

        swear_jar[user_id]["balance"] += (
            len(found_words) * 100
        )

        save_swear_jar()

        embed = discord.Embed(
            title="💸 SWEAR JAR",
            description=(
                f"{message.author.mention} "
                f"was fined "
                f"£{len(found_words) * 100}"
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
            value=(
                f"£"
                f"{swear_jar[user_id]['balance']}"
            ),
            inline=True
        )

        await message.channel.send(
            embed=style_embed(embed)
        )

    await bot.process_commands(message)

# =========================
# LOOP
# =========================

@tasks.loop(minutes=3)
async def adm_loop():

    print("CHECKING ADM...")

    latest_log = await asyncio.to_thread(
        ping_latest_adm_log
    )

    if not latest_log:

        print("NO ADM FOUND")

        return

    modified_at = latest_log.get(
        "modified_at"
    )

    if (
        modified_at
        == adm_state.get("last_modified")
    ):

        print("ADM NOT MODIFIED")

        return

    print("NEW ADM UPDATE FOUND")

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

    load_state()
    load_swear_jar()
    load_player_stats()
    load_heatmap()

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
        title=(
            f"🟢 ONLINE PLAYERS "
            f"({len(online_players)})"
        ),
        description=player_list,
        color=0x2ECC71
    )

    embed.set_thumbnail(
        url=BOT_IMAGE
    )

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
            f"{index}. "
            f"{user['name']} "
            f"- £{user['balance']} "
            f"({user['count']} swears)"
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
async def topkills(ctx):

    if not player_stats:

        await ctx.send(
            "No stats available."
        )

        return

    sorted_players = sorted(
        player_stats.items(),
        key=lambda x: x[1]["kills"],
        reverse=True
    )

    lines = []

    for index, (
        player,
        stats
    ) in enumerate(
        sorted_players[:10],
        start=1
    ):

        lines.append(
            f"{index}. "
            f"{player} - "
            f"{stats['kills']} kills"
        )

    embed = discord.Embed(
        title="☠️ TOP KILLS",
        description="\n".join(lines),
        color=0x992D22
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
        description="\n".join(lines),
        color=0xE74C3C
    )

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================
# START
# =========================

bot.run(DISCORD_TOKEN)
