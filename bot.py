import os
import re
import time
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

# ================= INIT =================

client = discord.Client(intents=discord.Intents.default())

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

last_size = 0

# ================= DOWNLOAD LOG =================

def download_latest_log():

    try:
        # GET FILE LIST
        res = requests.get(
            f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list",
            headers=headers,
            params={"dir": FTP_LOG_PATH}
        ).json()

        if "data" not in res:
            print("❌ FILE LIST ERROR:", res)
            return False

        files = res["data"]["entries"]

        adm_files = [
            f for f in files
            if f["name"].endswith(".ADM")
        ]

        if not adm_files:
            print("❌ No ADM logs found")
            return False

        # SORT NEWEST FIRST
        adm_files.sort(
            key=lambda x: x["name"],
            reverse=True
        )

        latest = adm_files[0]

        log_path = latest["path"]

        print(f"✅ Latest ADM log found: {log_path}")

        # DOWNLOAD FILE
        download = requests.get(
            f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/download",
            headers=headers,
            params={"file": log_path}
        ).json()

        if "data" not in download:
            print("❌ DOWNLOAD ERROR:", download)
            return False

        download_url = download["data"]["token"]["url"]

        file_data = requests.get(download_url)

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
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:

            f.seek(last_size)

            new_lines = f.readlines()

            last_size = f.tell()

        for line in new_lines:

            line = line.strip()

            if not line:
                continue

            print("NEW:", line)

            # ================= KILLS =================

            if " killed " in line:

                await channel.send(f"💀 {line}")

            # ================= SUICIDES =================

            elif " committed suicide" in line:

                await channel.send(f"☠️ {line}")

            # ================= PLACEMENTS =================

            elif " placed " in line:

                await channel.send(f"📦 {line}")

            # ================= BUILDING =================

            elif "Built " in line:

                await channel.send(f"🛠️ {line}")

            # ================= CONNECTIONS =================

            elif "is connected" in line:

                await channel.send(f"🟢 {line}")

            elif "has been disconnected" in line:

                await channel.send(f"🔴 {line}")

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

        await asyncio.sleep(10)


# ================= EVENTS =================

@client.event
async def on_ready():

    print(f"✅ Logged in as {client.user}")

    client.loop.create_task(tracker_loop())


# ================= START =================

import asyncio

client.run(DISCORD_TOKEN)