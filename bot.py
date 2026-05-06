import os
import re
import asyncio
import requests
import discord
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
LAST_LOG_FILE = "last_log.txt"

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

    if match:

        date_part = match.group(1)
        hour = match.group(2)
        minute = match.group(3)
        second = match.group(4)

        return f"{date_part} {hour}:{minute}:{second}"

    return "0000"

# ================= DOWNLOAD LOG =================

def download_latest_log():

    global current_log_file
    global last_size

    try:

        res = requests.get(
            f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list",
            headers=headers,
            params={"dir": FTP_LOG_PATH}
        ).json()

        # ================= API FAILURE FALLBACK =================

        if "data" not in res:

            print("❌ FILE LIST ERROR:", res)

            if os.path.exists(LAST_LOG_FILE):

                with open(LAST_LOG_FILE, "r") as f:
                    log_path = f.read().strip()

                print(f"♻️ Using cached ADM: {log_path}")

            else:
                return False

        else:

            files = res["data"]["entries"]

            adm_files = [
                f for f in files
                if f["name"].endswith(".ADM")
            ]

            if not adm_files:
                print("❌ No ADM logs found")
                return False

            # ================= GET TRUE NEWEST FILE =================

            latest = max(
                adm_files,
                key=lambda x: extract_date(x["name"])
            )

            log_path = latest["path"]

            # ================= NEW LOG DETECTION =================

            if current_log_file != log_path:

                print(f"🆕 New ADM detected: {log_path}")

                current_log_file = log_path

                last_size = 0
                save_last_position(0)

            with open(LAST_LOG_FILE, "w") as f:
                f.write(log_path)

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

        # ================= FILE SHRUNK / RESET =================

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

            # ================= CONNECTING =================

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

            # ================= CONNECTED =================

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

                embed.add_field(
                    name="📍 Last Location",
                    value=location,
                    inline=False
                )

                await channel.send(embed=embed)

            # ================= EMOTES =================

            elif " performed " in line:

                action_match = re.search(
                    r'performed ([^ ]+)',
                    line
                )

                action = (
                    action_match.group(1)
                    if action_match
                    else "Action"
                )

                embed = discord.Embed(
                    title="🎭 PLAYER ACTION",
                    color=0xaa00ff
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                embed.add_field(
                    name="🎬 Action",
                    value=action,
                    inline=False
                )

                embed.add_field(
                    name="📍 Location",
                    value=location,
                    inline=False
                )

                await channel.send(embed=embed)

            # ================= BUILDING =================

            elif "Built " in line:

                build_match = re.search(
                    r'Built (.*?) on',
                    line
                )

                build = (
                    build_match.group(1)
                    if build_match
                    else "Structure"
                )

                embed = discord.Embed(
                    title="🛠️ BUILDING",
                    color=0xffaa00
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                embed.add_field(
                    name="🧱 Structure",
                    value=build,
                    inline=False
                )

                embed.add_field(
                    name="📍 Location",
                    value=location,
                    inline=False
                )

                await channel.send(embed=embed)

            # ================= ITEM PLACEMENT =================

            elif " placed " in line:

                item_match = re.search(
                    r'placed (.*?)<',
                    line
                )

                item = (
                    item_match.group(1)
                    if item_match
                    else "Item"
                )

                embed = discord.Embed(
                    title="📦 ITEM PLACED",
                    color=0x00aaff
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                embed.add_field(
                    name="📦 Item",
                    value=item,
                    inline=False
                )

                embed.add_field(
                    name="📍 Location",
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