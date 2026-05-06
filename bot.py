import os
import re
import asyncio
import discord
from ftplib import FTP_TLS
from datetime import datetime, UTC
from supabase import create_client

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ================= FEED CHANNELS =================

CONNECTION_CHANNEL_ID = int(os.getenv("CONNECTION_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
DEPLOY_CHANNEL_ID = int(os.getenv("DEPLOY_CHANNEL_ID", 0))
PACKING_CHANNEL_ID = int(os.getenv("PACKING_CHANNEL_ID", 0))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

# ================= FILE SETTINGS =================

LOG_FILE = "server.ADM"
POSITION_FILE = "last_position.txt"

LOG_DIRECTORY = "/dayzxb/config"

BOT_IMAGE = "wanderingbot.png"

# ================= DISCORD =================

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ================= SUPABASE =================

supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= POSITION TRACKING =================

def load_last_position():

    if os.path.exists(POSITION_FILE):

        with open(POSITION_FILE, "r") as f:
            return int(f.read())

    return 0


def save_last_position(position):

    with open(POSITION_FILE, "w") as f:
        f.write(str(position))

# ================= GLOBAL TRACKING =================

last_size = load_last_position()
current_log_file = None

# ================= DATE EXTRACTION =================

def extract_date(file_name):

    match = re.search(
        r'(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})',
        file_name
    )

    if not match:
        return datetime.min

    return datetime.strptime(
        f"{match.group(1)} "
        f"{match.group(2)}:"
        f"{match.group(3)}:"
        f"{match.group(4)}",
        "%Y-%m-%d %H:%M:%S"
    )

# ================= CLEAN BUILD TEXT =================

def clean_build_action(action):

    replacements = {
        "wall_metal_up": "Metal Upper Wall Built",
        "wall_metal_down": "Metal Lower Wall Built",
        "wall_wood_up": "Wood Upper Wall Built",
        "wall_wood_down": "Wood Lower Wall Built",
        "wall_base_up": "Upper Frame Constructed",
        "wall_base_down": "Lower Frame Constructed",
        "base on Fence": "Fence Foundation Built"
    }

    for old, new in replacements.items():
        action = action.replace(old, new)

    return action

# ================= IZURVIVE LINK =================

def create_map_link(x, y):

    return (
        f"https://www.izurvive.com/chernarusplussatmap/"
        f"#location={x};{y}"
    )

# ================= LOCATION DISPLAY =================

def create_location_display(location, map_link):

    if map_link:
        return f"🗺️ [{location}]({map_link})"

    return f"`{location}`"

# ================= FTP CONNECTION =================

def connect_ftp():

    ftp = FTP_TLS()

    ftp.connect(FTP_HOST, FTP_PORT, timeout=30)

    ftp.login(FTP_USER, FTP_PASS)

    ftp.prot_p()

    return ftp

# ================= FIND NEWEST ADM =================

def find_latest_adm():

    try:

        print(f"🔍 FTP Searching: {LOG_DIRECTORY}")

        ftp = connect_ftp()

        ftp.cwd(LOG_DIRECTORY)

        files = ftp.nlst()

        adm_files = []

        for file in files:

            if file.endswith(".ADM"):

                print(f"📄 Found ADM: {file}")

                adm_files.append(file)

        ftp.quit()

        if not adm_files:
            return None

        newest_file = max(
            adm_files,
            key=lambda x: extract_date(x)
        )

        return f"{LOG_DIRECTORY}/{newest_file}"

    except Exception as e:

        print("❌ FTP SEARCH ERROR:", e)
        return None

# ================= DOWNLOAD LOG =================

def download_latest_log():

    global current_log_file
    global last_size

    try:

        log_path = find_latest_adm()

        if not log_path:

            print("❌ No ADM logs found")
            return False

        print(f"✅ Latest ADM log found: {log_path}")

        if current_log_file != log_path:

            print(f"🆕 New ADM detected: {log_path}")

            current_log_file = log_path

            last_size = 0
            save_last_position(0)

        ftp = connect_ftp()

        with open(LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {log_path}",
                f.write
            )

        ftp.quit()

        print(f"✅ Log downloaded: {log_path}")

        print(f"📦 Downloaded file size: {os.path.getsize(LOG_FILE)} bytes")

        return True

    except Exception as e:

        print("❌ DOWNLOAD ERROR:", e)
        return False

# ================= EMBED STYLE =================

def style_embed(embed):

    if os.path.exists(BOT_IMAGE):

        embed.set_author(
            name="☣️ Wandering Bot Intelligence",
            icon_url="attachment://wanderingbot.png"
        )

        embed.set_thumbnail(
            url="attachment://wanderingbot.png"
        )

    else:

        embed.set_author(
            name="☣️ Wandering Bot Intelligence"
        )

    embed.set_footer(
        text="☣️ Live DayZ Intelligence • Wandering Bot"
    )

    embed.timestamp = datetime.now(UTC)

    return embed

# ================= SEND EMBED =================

async def send_embed(channel, embed):

    if not channel:
        print("❌ Channel not found")
        return

    try:

        if os.path.exists(BOT_IMAGE):

            file = discord.File(
                BOT_IMAGE,
                filename="wanderingbot.png"
            )

            await channel.send(
                embed=embed,
                file=file
            )

        else:

            await channel.send(embed=embed)

    except Exception as e:

        print(f"❌ SEND EMBED ERROR: {e}")

# ================= PARSE LOG =================

async def parse_new_lines():

    global last_size

    connection_channel = client.get_channel(CONNECTION_CHANNEL_ID)
    killfeed_channel = client.get_channel(KILLFEED_CHANNEL_ID)
    raid_channel = client.get_channel(RAID_CHANNEL_ID)
    build_channel = client.get_channel(BUILD_CHANNEL_ID)
    deploy_channel = client.get_channel(DEPLOY_CHANNEL_ID)
    packing_channel = client.get_channel(PACKING_CHANNEL_ID)

    try:

        if not os.path.exists(LOG_FILE):

            print("❌ Local log file missing")
            return

        current_file_size = os.path.getsize(LOG_FILE)

        if current_file_size < last_size:

            print("♻️ LOG RESET DETECTED")

            last_size = 0
            save_last_position(0)

        with open(
            LOG_FILE,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            f.seek(last_size)

            new_lines = f.readlines()

            last_size = f.tell()

            save_last_position(last_size)

        if not new_lines:

            print("⏳ No new log lines")
            return

        for line in new_lines:

            line = line.strip()

            if not line:
                continue

            ignored_phrases = [
                "PlayerList log",
                "#####",
                "AdminLog started"
            ]

            if any(x in line for x in ignored_phrases):
                continue

            timestamp_match = re.match(
                r'(\d{2}:\d{2}:\d{2})',
                line
            )

            timestamp = (
                timestamp_match.group(1)
                if timestamp_match
                else "Unknown"
            )

            print(f"[{timestamp}] {line}")

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            pos_match = re.search(
                r'pos=<([\d.]+), ([\d.]+), ([\d.]+)>',
                line
            )

            location = "Unknown"
            map_link = None
            location_display = "`Unknown`"

            if pos_match:

                x = round(float(pos_match.group(1)), 1)
                y = round(float(pos_match.group(2)), 1)

                location = f"{x}, {y}"

                map_link = create_map_link(x, y)

                location_display = create_location_display(
                    location,
                    map_link
                )

            # ================= KILL FEED =================

            if " killed by Player " in line:

                killer_match = re.search(
                    r'Player "([^"]+)" .* killed by Player "([^"]+)"',
                    line
                )

                if killer_match:

                    victim = killer_match.group(1)
                    killer = killer_match.group(2)

                    embed = discord.Embed(
                        color=0x8B0000
                    )

                    embed.description = (
                        "```fix\n"
                        "☠ PLAYER KILLED ☠\n"
                        "```\n"
                        f"🔫 **Killer**\n"
                        f"> `{killer}`\n\n"
                        f"💀 **Victim**\n"
                        f"> `{victim}`\n\n"
                        f"📍 **Combat Zone**\n"
                        f"> {location_display}\n\n"
                        f"🕒 **Time Of Death**\n"
                        f"> `{timestamp}`"
                    )

                    embed = style_embed(embed)

                    await send_embed(killfeed_channel, embed)

                    continue

            # ================= RAID ALERT =================

            if (
                "destroyed" in line.lower()
                or "dismantled" in line.lower()
                or "damaged" in line.lower()
            ):

                embed = discord.Embed(
                    color=0xff0000
                )

                embed.description = (
                    "```fix\n"
                    "🚨 RAID ALERT 🚨\n"
                    "```\n"
                    f"👤 **Player**\n"
                    f"> `{player}`\n\n"
                    f"💥 **Raid Activity**\n"
                    f"> `{line}`\n\n"
                    f"📍 **Raid Location**\n"
                    f"> {location_display}\n\n"
                    f"🕒 **Alert Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await send_embed(raid_channel, embed)

                continue

            # ================= PLAYER CONNECTING =================

            if " is connecting" in line:

                embed = discord.Embed(
                    color=0x8B8000
                )

                embed.description = (
                    "```fix\n"
                    "📡 SURVIVOR SIGNAL DETECTED\n"
                    "```\n"
                    f"👤 **Survivor**\n"
                    f"> `{player}`\n\n"
                    f"🕒 **Connection Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await send_embed(connection_channel, embed)

            # ================= PLAYER CONNECTED =================

            elif " is connected" in line:

                embed = discord.Embed(
                    color=0x556B2F
                )

                embed.description = (
                    "```fix\n"
                    "☣ SURVIVOR ENTERED CHERNARUS ☣\n"
                    "```\n"
                    f"👤 **Survivor**\n"
                    f"> `{player}`\n\n"
                    f"📍 **Location Intel**\n"
                    f"> {location_display}\n\n"
                    f"🕒 **Arrival Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await send_embed(connection_channel, embed)

            # ================= PLAYER DISCONNECTED =================

            elif " has been disconnected" in line:

                embed = discord.Embed(
                    color=0x8B2E2E
                )

                embed.description = (
                    "```fix\n"
                    "☠ SURVIVOR LOST SIGNAL ☠\n"
                    "```\n"
                    f"👤 **Survivor**\n"
                    f"> `{player}`\n\n"
                    f"📍 **Last Known Position**\n"
                    f"> {location_display}\n\n"
                    f"🕒 **Disconnect Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await send_embed(connection_channel, embed)

            # ================= ITEM PLACED =================

            elif "placed" in line.lower():

                placed_match = re.search(
                    r'placed (.+)',
                    line,
                    re.IGNORECASE
                )

                placed_item = (
                    placed_match.group(1)
                    if placed_match
                    else "Unknown Item"
                )

                embed = discord.Embed(
                    color=0xA67C52
                )

                embed.description = (
                    "```fix\n"
                    "⚒ DEPLOYMENT EVENT ⚒\n"
                    "```\n"
                    f"👤 **Survivor**\n"
                    f"> `{player}`\n\n"
                    f"📦 **Deployed Object**\n"
                    f"> `{placed_item}`\n\n"
                    f"📍 **Deployment Zone**\n"
                    f"> {location_display}\n\n"
                    f"🕒 **Event Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await send_embed(deploy_channel, embed)

            # ================= BUILD EVENT =================

            elif "built" in line.lower():

                build_match = re.search(
                    r'Built (.+)',
                    line
                )

                build_action = (
                    build_match.group(1)
                    if build_match
                    else "Unknown Build"
                )

                build_action = clean_build_action(build_action)

                embed = discord.Embed(
                    color=0x4B5320
                )

                embed.description = (
                    "```fix\n"
                    "🛠 BASE CONSTRUCTION 🛠\n"
                    "```\n"
                    f"👤 **Builder**\n"
                    f"> `{player}`\n\n"
                    f"🏗 **Construction Action**\n"
                    f"> `{build_action}`\n\n"
                    f"📍 **Build Coordinates**\n"
                    f"> {location_display}\n\n"
                    f"🕒 **Construction Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await send_embed(build_channel, embed)

            # ================= ITEM FOLDED =================

            elif "folded" in line.lower():

                folded_match = re.search(
                    r'folded (.+)',
                    line,
                    re.IGNORECASE
                )

                folded_item = (
                    folded_match.group(1)
                    if folded_match
                    else "Unknown Item"
                )

                embed = discord.Embed(
                    color=0x3B4C59
                )

                embed.description = (
                    "```fix\n"
                    "📦 STRUCTURE RECOVERED 📦\n"
                    "```\n"
                    f"👤 **Survivor**\n"
                    f"> `{player}`\n\n"
                    f"📁 **Recovered Object**\n"
                    f"> `{folded_item}`\n\n"
                    f"📍 **Recovery Position**\n"
                    f"> {location_display}\n\n"
                    f"🕒 **Recovery Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await send_embed(packing_channel, embed)

            # ================= ITEM PACKED =================

            elif "packed" in line.lower():

                packed_match = re.search(
                    r'packed (.+)',
                    line,
                    re.IGNORECASE
                )

                packed_item = (
                    packed_match.group(1)
                    if packed_match
                    else "Unknown Item"
                )

                embed = discord.Embed(
                    color=0x70543E
                )

                embed.description = (
                    "```fix\n"
                    "🎒 CAMP PACKED 🎒\n"
                    "```\n"
                    f"👤 **Survivor**\n"
                    f"> `{player}`\n\n"
                    f"📦 **Packed Equipment**\n"
                    f"> `{packed_item}`\n\n"
                    f"📍 **Pack-Up Location**\n"
                    f"> {location_display}\n\n"
                    f"🕒 **Event Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await send_embed(packing_channel, embed)

    except Exception as e:

        print("❌ PARSE ERROR:", e)

# ================= LOOP =================

async def tracker_loop():

    await client.wait_until_ready()

    print("🚀 Wandering Bot Tracker Started")

    while not client.is_closed():

        success = download_latest_log()

        if success:

            await parse_new_lines()

        await asyncio.sleep(30)

# ================= EVENTS =================

@client.event
async def on_ready():

    print(f"✅ Logged in as {client.user}")

    client.loop.create_task(tracker_loop())

# ================= START =================

client.run(DISCORD_TOKEN)