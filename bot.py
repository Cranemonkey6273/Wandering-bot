import os
import re
import asyncio
import discord
from ftplib import FTP_TLS
from datetime import datetime
from supabase import create_client

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

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

        # ================= NEW FILE DETECTION =================

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

    embed.set_thumbnail(
        url="https://i.imgur.com/8B7QFQF.png"
    )

    embed.set_footer(
        text="☣️ Wandering Bot • Live DayZ Intelligence"
    )

    return embed

# ================= PARSE LOG =================

async def parse_new_lines():

    global last_size

    channel = client.get_channel(CHANNEL_ID)

    if not channel:

        print("❌ Discord channel not found")
        return

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

            if pos_match:

                x = round(float(pos_match.group(1)), 1)
                y = round(float(pos_match.group(2)), 1)

                location = f"{x}, {y}"

            embed = discord.Embed()

            # ================= CONNECTING =================

            if " is connecting" in line:

                embed.color = 0xffcc00

                embed.description = (
                    "```ansi\n"
                    "\u001b[1;33m🟡 PLAYER CONNECTING 🟡\u001b[0m\n"
                    "```\n"
                    f"👤 **Player**\n"
                    f"> `{player}`\n\n"
                    f"⏰ **Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await channel.send(embed=embed)

            # ================= CONNECTED =================

            elif " is connected" in line:

                embed.color = 0x00ff66

                embed.description = (
                    "```ansi\n"
                    "\u001b[1;32m🟢 PLAYER CONNECTED 🟢\u001b[0m\n"
                    "```\n"
                    f"👤 **Player**\n"
                    f"> `{player}`\n\n"
                    f"📍 **Spawn Location**\n"
                    f"> `{location}`\n\n"
                    f"⏰ **Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await channel.send(embed=embed)

            # ================= DISCONNECTED =================

            elif " has been disconnected" in line:

                embed.color = 0xff3333

                embed.description = (
                    "```ansi\n"
                    "\u001b[1;31m🔴 PLAYER DISCONNECTED 🔴\u001b[0m\n"
                    "```\n"
                    f"👤 **Player**\n"
                    f"> `{player}`\n\n"
                    f"📍 **Last Seen**\n"
                    f"> `{location}`\n\n"
                    f"⏰ **Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await channel.send(embed=embed)

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

                embed.color = 0xff9900

                embed.description = (
                    "```ansi\n"
                    "\u001b[1;33m🛠 ITEM PLACED 🛠\u001b[0m\n"
                    "```\n"
                    f"👤 **Player**\n"
                    f"> `{player}`\n\n"
                    f"📦 **Placed Item**\n"
                    f"> `{placed_item}`\n\n"
                    f"📍 **Location**\n"
                    f"> `{location}`\n\n"
                    f"⏰ **Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await channel.send(embed=embed)

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

                embed.color = 0x9966ff

                embed.description = (
                    "```ansi\n"
                    "\u001b[1;35m⚒ BUILD EVENT ⚒\u001b[0m\n"
                    "```\n"
                    f"👤 **Player**\n"
                    f"> `{player}`\n\n"
                    f"🏗️ **Action**\n"
                    f"> `{build_action}`\n\n"
                    f"📍 **Location**\n"
                    f"> `{location}`\n\n"
                    f"⏰ **Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await channel.send(embed=embed)

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

                embed.color = 0x00ccff

                embed.description = (
                    "```ansi\n"
                    "\u001b[1;36m📦 ITEM FOLDED 📦\u001b[0m\n"
                    "```\n"
                    f"👤 **Player**\n"
                    f"> `{player}`\n\n"
                    f"📁 **Item**\n"
                    f"> `{folded_item}`\n\n"
                    f"📍 **Location**\n"
                    f"> `{location}`\n\n"
                    f"⏰ **Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await channel.send(embed=embed)

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

                embed.color = 0xcc6600

                embed.description = (
                    "```ansi\n"
                    "\u001b[1;33m🎒 ITEM PACKED 🎒\u001b[0m\n"
                    "```\n"
                    f"👤 **Player**\n"
                    f"> `{player}`\n\n"
                    f"📦 **Item**\n"
                    f"> `{packed_item}`\n\n"
                    f"📍 **Location**\n"
                    f"> `{location}`\n\n"
                    f"⏰ **Time**\n"
                    f"> `{timestamp}`"
                )

                embed = style_embed(embed)

                await channel.send(embed=embed)

    except Exception as e:

        print("❌ PARSE ERROR:", e)

# ================= LOOP =================

async def tracker_loop():

    await client.wait_until_ready()

    print("🚀 Tracker started")

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