import os
import re
import asyncio
import requests
import discord
from datetime import datetime
from supabase import create_client

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

NITRADO_TOKEN = os.getenv("NITRADO_TOKEN")
SERVICE_ID = os.getenv("SERVICE_ID")

FTP_LOG_PATH = os.getenv("FTP_LOG_PATH")

headers = {
    "Authorization": f"Bearer {NITRADO_TOKEN}"
}

LOG_FILE = "server.ADM"
POSITION_FILE = "last_position.txt"

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

# ================= GET FILE LIST =================

def get_files(directory):

    try:

        res = requests.get(
            f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list",
            headers=headers,
            params={"dir": directory}
        ).json()

        if "data" not in res:
            return []

        return res["data"]["entries"]

    except Exception as e:
        print("❌ DIRECTORY ERROR:", e)
        return []

# ================= FIND NEWEST ADM =================

def find_latest_adm():

    directory = "/games/ni12248929_2/ftproot/dayzxb/config"

    print(f"🔍 Searching: {directory}")

    files = get_files(directory)

    newest_file = None
    newest_date = datetime.min

    for file in files:

        name = file.get("name", "")

        if not name.endswith(".ADM"):
            continue

        print(f"📄 Found ADM: {name}")

        file_date = extract_date(name)

        if file_date > newest_date:

            newest_date = file_date
            newest_file = file["path"]

    # ================= MANUAL FALLBACK =================

    forced_latest = (
        "/games/ni12248929_2/ftproot/dayzxb/config/"
        "DayZServer_X1_x64_2026-05-06_14-38-13.ADM"
    )

    fallback_date = datetime.strptime(
        "2026-05-06 14:38:13",
        "%Y-%m-%d %H:%M:%S"
    )

    if newest_file is None or newest_date < fallback_date:

        print("⚠️ API missing newest ADM, forcing latest known file")

        newest_file = forced_latest

    return newest_file

# ================= DOWNLOAD LOG =================

def download_latest_log():

    global current_log_file
    global last_size

    try:

        log_path = find_latest_adm()

        if not log_path:

            print("❌ No ADM logs found")
            return False

        if current_log_file != log_path:

            print(f"🆕 New ADM detected: {log_path}")

            current_log_file = log_path

            last_size = 0
            save_last_position(0)

        print(f"✅ Latest ADM log found: {log_path}")

        # ================= GET DOWNLOAD URL =================

        download = requests.get(
            f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/download",
            headers=headers,
            params={"file": log_path}
        ).json()

        if "data" not in download:
            print("❌ DOWNLOAD ERROR:", download)
            return False

        download_url = download["data"]["token"]["url"]

        # ================= FORCE FRESH DOWNLOAD =================

        file_data = requests.get(
            download_url,
            headers={
                "Cache-Control": "no-cache"
            },
            params={
                "_": str(asyncio.get_event_loop().time())
            }
        )

        print(f"📦 Downloaded file size: {len(file_data.content)} bytes")

        with open(LOG_FILE, "wb") as f:
            f.write(file_data.content)

        print(f"✅ Log downloaded: {log_path}")

        return True

    except Exception as e:
        print("❌ DOWNLOAD EXCEPTION:", e)
        return False

# ================= PARSE LOG =================

async def parse_new_lines():

    global last_size

    channel = client.get_channel(CHANNEL_ID)

    if not channel:
        print("❌ Discord channel not found")
        return

    try:

        current_file_size = os.path.getsize(LOG_FILE)

        if current_file_size < last_size:

            print("♻️ ADM reset detected")

            last_size = 0
            save_last_position(0)

        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:

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

                x = pos_match.group(1)
                y = pos_match.group(2)

                location = f"X:{x} Y:{y}"

            # ================= CONNECTED =================

            if " is connected" in line:

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

            # ================= DISCONNECTED =================

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