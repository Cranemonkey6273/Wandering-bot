import os
import re
import asyncio
import discord
import json

from ftplib import FTP_TLS
from datetime import datetime, UTC, timedelta
from discord.ext import commands, tasks
from supabase import create_client
from openai import AsyncOpenAI

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ================= CHANNEL IDS =================

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))

# ================= FTP =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"
LOCAL_LOG_FILE = "live.ADM"

# ================= SAVE FILE =================

STATE_FILE = "adm_state.json"

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ================= OPENAI =================

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ================= SUPABASE =================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ================= GLOBALS =================

processed_lines = set()
MAX_PROCESSED_LINES = 10000

adm_state = {
    "file": None,
    "last_line": 0,
    "last_text": "",
    "last_modified": "",
    "last_logged_file": ""
}

LAST_CHANGE_TIME = datetime.now(UTC)
LIVE_MODE = False

current_adm = None
current_adm_size = 0

online_players = set()
player_hits = {}
player_sessions = {}
territory_heat = {}

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

IGNORE_PATTERNS = [
    "[CE]",
    "LootRespawner",
    "PRIDummy",
    "causing search overtime",
    "Ammo_40mm_Explosive",
    "ConstructionHelmet",
    "script",
    "crash",
    "weather",
    "storage",
    "economy",
    "infected"
]

# ================= STATE SAVE =================


def save_state():

    try:

        with open(STATE_FILE, "w") as f:

            json.dump(adm_state, f)

    except Exception as e:

        print(f"STATE SAVE ERROR: {e}")


def load_state():

    global adm_state

    try:

        if os.path.exists(STATE_FILE):

            with open(STATE_FILE, "r") as f:

                adm_state = json.load(f)

            print("STATE LOADED")

    except Exception as e:

        print(f"STATE LOAD ERROR: {e}")


# ================= HELPERS =================


def should_ignore(line):

    lower = line.lower()

    for pattern in IGNORE_PATTERNS:

        if pattern.lower() in lower:
            return True

    return False


def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    return embed


def connect_ftp():

    ftp = FTP_TLS()

    ftp.connect(
        FTP_HOST,
        FTP_PORT,
        timeout=30
    )

    ftp.login(
        FTP_USER,
        FTP_PASS
    )

    try:
        ftp.prot_p()

    except Exception as e:
        print(f"FTP TLS WARNING: {e}")

    ftp.set_pasv(True)

    return ftp


# ================= EVENT CLASSIFIER =================


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
        "hit by" in lower
        or "hit player" in lower
    ):
        return "hit"

    if (
        "placed" in lower
        or "packed" in lower
        or "built" in lower
        or "mounted" in lower
        or "folded" in lower
    ):
        return "build"

    if (
        "unconscious" in lower
        or "regained consciousness" in lower
        or "bled out" in lower
    ):
        return "combat"

    if (
        "destroyed" in lower
        or "dismantled" in lower
        or "breached" in lower
        or "explosive" in lower
    ):
        return "raid"

    return None


# ================= ACTIVE ADM FINDER =================


def extract_filename_datetime(filename):

    match = re.search(
        r'_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.ADM$',
        filename
    )

    if not match:
        return None

    iso = (
        f"{match.group(1)} "
        f"{match.group(2).replace('-', ':')}"
    )

    try:

        return datetime.strptime(
            iso,
            "%Y-%m-%d %H:%M:%S"
        )

    except Exception:

        return None


def find_active_adm():

    global current_adm
    global current_adm_size

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = ftp.nlst()

        adm_candidates = []

        for file in files:

            if not re.match(
                r'^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$',
                file
            ):
                continue

            file_datetime = extract_filename_datetime(file)

            if not file_datetime:
                continue

            try:

                ftp.voidcmd("TYPE I")

                size = ftp.size(file)

                if size <= 0:
                    continue

                temp_lines = []

                try:

                    ftp.retrlines(
                        f"RETR {file}",
                        temp_lines.append
                    )

                except Exception:
                    continue

                if not temp_lines:
                    continue

                recent_lines = temp_lines[-150:]

                recent_text = "\n".join(recent_lines).lower()

                if (
                    "termination successfully completed"
                    in recent_text
                ):
                    continue

                gameplay_patterns = [
                    "connecting",
                    "connected",
                    "disconnected",
                    "killed",
                    "placed",
                    "packed",
                    "built",
                    "mounted",
                    "folded",
                    "hit by",
                    "unconscious",
                    "bled out",
                    "regained consciousness"
                ]

                gameplay_found = any(
                    x in recent_text
                    for x in gameplay_patterns
                )

                if not gameplay_found:
                    continue

                adm_candidates.append({
                    "name": file,
                    "datetime": file_datetime,
                    "size": size
                })

            except Exception as e:

                print(f"FAILED ADM: {file} | {e}")

        ftp.quit()

        if not adm_candidates:

            print("NO VALID ACTIVE ADM FOUND")

            return current_adm

        adm_candidates.sort(
            key=lambda x: x["datetime"],
            reverse=True
        )

        best = adm_candidates[0]

        newest_adm = (
            f"{SEARCH_DIR}/{best['name']}"
        )

        newest_datetime = best["datetime"]

        if current_adm is None:

            current_adm = newest_adm
            current_adm_size = best["size"]

            adm_state["last_logged_file"] = current_adm

            save_state()

            print(f"INITIAL ACTIVE ADM: {current_adm}")

            return current_adm

        current_filename = os.path.basename(current_adm)

        current_datetime = extract_filename_datetime(
            current_filename
        )

        if (
            current_datetime is None
            or newest_datetime > current_datetime
        ):

            print(f"NEWER ADM DETECTED | SWITCHING -> {newest_adm}")

            current_adm = newest_adm
            current_adm_size = best["size"]

            adm_state["file"] = None
            adm_state["last_modified"] = ""
            adm_state["last_logged_file"] = current_adm

            # ================= IMPORTANT =================
            # Sync to END of newly created ADM
            # Prevents replaying old startup events
            # Nitrado writes old events before new ADM becomes live
            # =================================================

            try:

                ftp_sync = connect_ftp()
                ftp_sync.cwd(SEARCH_DIR)

                sync_lines = []

                ftp_sync.retrlines(
                    f"RETR {best['name']}",
                    sync_lines.append
                )

                ftp_sync.quit()

                adm_state["last_line"] = len(sync_lines)

                if sync_lines:
                    adm_state["last_text"] = sync_lines[-1].strip()
                else:
                    adm_state["last_text"] = ""

            except Exception as e:

                print(f"NEW ADM SYNC ERROR: {e}")

                adm_state["last_line"] = 0
                adm_state["last_text"] = ""

            save_state()

            return current_adm

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return current_adm


# ================= DOWNLOAD ADM =================


def download_adm():

    global adm_state

    try:

        active_adm = find_active_adm()

        if not active_adm:
            return False

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        filename = os.path.basename(active_adm)

        modified = ftp.sendcmd(f"MDTM {filename}")

        timestamp = modified[4:].strip()

        if adm_state["file"] == active_adm and adm_state["last_modified"] == timestamp:

            ftp.quit()
            return False

        with open(LOCAL_LOG_FILE, "wb") as f:
            ftp.retrbinary(f"RETR {filename}", f.write)

        ftp.quit()

        adm_state["file"] = active_adm
        adm_state["last_modified"] = timestamp

        save_state()

        print(f"ADM UPDATED: {filename}")

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False


# ================= ADM PARSER =================


async def parse_adm():

    global processed_lines

    if not os.path.exists(LOCAL_LOG_FILE):
        return

    with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    start_index = adm_state.get("last_line", 0)

    last_text = adm_state.get("last_text", "")

    if last_text:

        found_index = None

        for i, line in enumerate(lines):
            if last_text in line:
                found_index = i

        if found_index is not None:
            start_index = found_index + 1

    new_lines = lines[start_index:]

    adm_state["last_line"] = len(lines)

    if lines:
        adm_state["last_text"] = lines[-1].strip()

    save_state()

    print(f"NEW ADM LINES: {len(new_lines)}")

    killfeed_channel = bot.get_channel(KILLFEED_CHANNEL_ID)
    connect_channel = bot.get_channel(CONNECT_CHANNEL_ID)
    build_channel = bot.get_channel(BUILD_CHANNEL_ID)
    raid_channel = bot.get_channel(RAID_CHANNEL_ID)

    for raw_line in new_lines:

        line = raw_line.strip()

        if not line:
            continue

        if should_ignore(line):
            continue

        line_hash = hash(line)

        if line_hash in processed_lines:
            continue

        processed_lines.add(line_hash)

        if len(processed_lines) > MAX_PROCESSED_LINES:
            processed_lines.clear()

        event_type = classify_event(line)

        if not event_type:
            continue

        print(f"EVENT: {event_type} | {line}")

        if event_type == "connect" and connect_channel:

            player_match = re.search(r'Player\s+"([^"]+)"', line, re.IGNORECASE)

            if player_match:

                player_name = player_match.group(1)

                online_players.add(player_name)
                player_sessions[player_name] = datetime.now(UTC)

                embed = discord.Embed(
                    title="🟢 Survivor Connected",
                    description=f"`{player_name}`",
                    color=0x2ECC71
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                await connect_channel.send(embed=style_embed(embed))

        elif event_type == "disconnect" and connect_channel:

            player_match = re.search(r'Player\s+"([^"]+)"', line, re.IGNORECASE)

            if player_match:

                player_name = player_match.group(1)

                online_players.discard(player_name)

                session_hours = 0

                if player_name in player_sessions:
                    session_length = (datetime.now(UTC) - player_sessions[player_name]).total_seconds()
                    session_hours = round(session_length / 3600, 2)

                embed = discord.Embed(
                    title="🔴 Survivor Disconnected",
                    description=(
                        f"`{player_name}`\n"
                        f"⏱️ Session: {session_hours} hrs"
                    ),
                    color=0xE74C3C
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                await connect_channel.send(embed=style_embed(embed))

        elif event_type == "build" and build_channel:

            embed = discord.Embed(
                title="🏗️ BUILD EVENT",
                description=line,
                color=0xF1C40F
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await build_channel.send(embed=style_embed(embed))

        elif event_type == "combat" and killfeed_channel:

            embed = discord.Embed(
                title="⚔️ COMBAT EVENT",
                description=line,
                color=0xE67E22
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await killfeed_channel.send(embed=style_embed(embed))

        elif event_type == "raid" and raid_channel:

            coords_match = re.search(r'pos=<([^>]+)>', line, re.IGNORECASE)

            coords = coords_match.group(1) if coords_match else "Unknown"

            territory_heat[coords] = territory_heat.get(coords, 0) + 1

            embed = discord.Embed(
                title="🚨 RAID DETECTED",
                description=line,
                color=0xFF0000
            )

            embed.add_field(name="🔥 Territory Heat", value=str(territory_heat[coords]), inline=False)

            embed.set_thumbnail(url=BOT_IMAGE)

            await raid_channel.send(embed=style_embed(embed))


# ================= TASK LOOP =================


@tasks.loop(seconds=5)
async def adm_loop():

    global LAST_CHANGE_TIME
    global LIVE_MODE

    now = datetime.now(UTC)

    success = await asyncio.to_thread(download_adm)

    if success:

        LAST_CHANGE_TIME = now
        LIVE_MODE = True

        await parse_adm()

    else:

        idle_time = (now - LAST_CHANGE_TIME).total_seconds()

        if idle_time >= 240:
            LIVE_MODE = False


# ================= READY =================


@bot.event
async def on_ready():

    load_state()

    if os.path.exists(LOCAL_LOG_FILE):

        with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            existing_lines = f.readlines()

        if adm_state["last_line"] == 0:

            adm_state["last_line"] = len(existing_lines)

            if existing_lines:
                adm_state["last_text"] = existing_lines[-1].strip()

            save_state()

            print(f"STARTUP SYNCED TO {len(existing_lines)} LINES")

    await bot.tree.sync()

    try:
        adm_loop.start()
    except RuntimeError:
        pass

    print(f"✅ Logged in as {bot.user}")


# ================= ONLINE =================


@bot.tree.command(name="online", description="View online players")
async def online(interaction: discord.Interaction):

    if online_players:
        players = "\n".join(f"• {x}" for x in sorted(online_players))
    else:
        players = "No players online."

    embed = discord.Embed(
        title=f"🟢 Online Players ({len(online_players)})",
        description=players,
        color=0x2ECC71
    )

    await interaction.response.send_message(embed=style_embed(embed))


# ================= START =================

bot.run(DISCORD_TOKEN)
