import os
import re
import asyncio
import discord
from ftplib import FTP
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

LOG_DIRECTORY = "/games/ni12248929_2/ftproot/dayzxb/config"

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

    ftp = FTP()

    ftp.connect(FTP_HOST, FTP_PORT, timeout=30)

    ftp.login(FTP_USER, FTP_PASS)

    return ftp

# ================= FIND NEWEST ADM =================

def find_latest_adm():

    try:

        ftp = connect_ftp()

        print(f"🔍 FTP Searching: {LOG_DIRECTORY}")

        ftp.cwd(LOG_DIRECTORY)

        files = ftp.nlst()

        adm_files = []

        for file in files:

            if file.endswith(".ADM"):

                print(f"📄 Found ADM: {file}")

                adm_files.append(file)

        if not adm_files:

            ftp.quit()
            return None

        newest_file = max(
            adm_files,
            key=lambda x: extract_date(x)
        )

        ftp.quit()

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

        filename = os.path.basename(log_path)

        ftp.cwd(LOG_DIRECTORY)

        with open(LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {filename}",
                f.write
            )

        ftp.quit()

        print(f"✅ Log downloaded: {log_path}")

        print(f"📦 Downloaded file size: {os.path.getsize(LOG_FILE)} bytes")

        return True

    except Exception as e:

        print("❌ DOWNLOAD ERROR:", e)
        return False

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

        # ================= FILE RESET DETECTION =================

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

            print("NEW:", line)

            # ================= PLAYER NAME =================

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            # ================= COORDS =================

            pos_match = re.search(
                r'pos=<([\d.]+), ([\d.]+), ([\d.]+)>',
                line
            )

            location = "Unknown"

            if pos_match:

                x = pos_match.group(1)
                y = pos_match.group(2)

                location = f"X:{x} Y:{y}"

            # ================= PLAYER CONNECTING =================

            if " is connecting" in line:

                embed = discord.Embed(
                    title="🟡 PLAYER CONNECTING",
                    color=0xffcc00
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                await channel.send(embed=embed)

            # ================= PLAYER CONNECTED =================

            elif " is connected" in line:

                embed = discord.Embed(
                    title="🟢 PLAYER CONNECTED",
                    color=0x00ff00
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                embed.add_field(
                    name="📍 Location",
                    value=location,
                    inline=False
                )

                await channel.send(embed=embed)

            # ================= PLAYER DISCONNECTED =================

            elif " has been disconnected" in line:

                embed = discord.Embed(
                    title="🔴 PLAYER DISCONNECTED",
                    color=0xff0000
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                embed.add_field(
                    name="📍 Last Location",
                    value=location,
                    inline=False
                )

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