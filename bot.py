import discord
import os
import time
import threading
import asyncio
import re
import math
import requests
from supabase import create_client

# ================== CONFIG ==================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

CHANNEL_ID = 1501126258140909580

SUPABASE_URL = "https://bqqeorqzezcgzqflqoms.supabase.co"
SUPABASE_KEY = "sb_publishable_fTUe0hG1Amm3cZ13155ljQ_EQYxmYPz"

NITRADO_TOKEN = "hoAZfsBJmKrY1kOGykAusZ309VDRVxINN_hNAG5NlqWOC5r63-45tH6Ws2OM7h9FC7oPjUgiDO6_-g8-BCKfwJ96FH-uMVgqEayY"
SERVICE_ID = "ni12248929_1"

LOG_FILE = "server.ADM"

# ================== INIT ==================
client = discord.Client(intents=discord.Intents.default())
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

players = {}
last_size = 0

# ================== DOWNLOAD LOG ==================
def download_log():
    try:
    files = res["data"]["entries"]

    adm_files = [f for f in files if f["path"].endswith(".ADM")]

    if not adm_files:
        print("❌ No ADM logs found")
        return

    latest = sorted(adm_files, key=lambda x: x["modified"])[-1]["path"]

    download_url = f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/download?file={latest}"

    res = requests.get(download_url, headers=headers).json()

    if "data" not in res:
        print("❌ DOWNLOAD ERROR:", res)
        return

    file_url = res["data"]["token"]["url"]
    file_data = requests.get(file_url).text

    with open(LOG_FILE, "w") as f:
        f.write(file_data)

    print("✅ Log downloaded:", latest)

except Exception as e:
    print("❌ LOG DOWNLOAD ERROR:", e)

# ================== AUTO UPDATE ==================
def log_updater():
    while True:
        download_log()
        time.sleep(5)

# ================== PARSING ==================
def get_player(line):
    name = re.search(r'Player "(.+?)"', line)
    pid = re.search(r'id=([A-Z0-9]+)', line)
    return (
        name.group(1) if name else "Unknown",
        pid.group(1) if pid else None
    )

def get_coords(line):
    m = re.search(r'pos=<(.+?)>', line)
    if m:
        return tuple(map(float, m.group(1).split(",")))
    return None

def distance(a, b):
    if not a or not b:
        return "Unknown"
    return f"{round(math.dist(a, b), 2)}m"

# ================== DATABASE ==================
def save_kill(killer, victim, dist):
    try:
        supabase.table("kills").insert({
            "killer": killer,
            "victim": victim,
            "distance": float(dist.replace("m","")) if dist != "Unknown" else None
        }).execute()
        print("💾 Saved to DB")
    except Exception as e:
        print("❌ DB ERROR:", e)

# ================== DISCORD ==================
async def send_kill(victim, killer, dist):
    ch = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="☠️ Killfeed",
        description=f"{killer} killed {victim}",
        color=0xff0000
    )

    embed.add_field(name="Distance", value=dist)
    embed.set_footer(text="Wandering System")

    await ch.send(embed=embed)

# ================== TRACK LOG ==================
def track_logs():
    global last_size

    print("📡 Tracking log...")

    while True:
        if not os.path.exists(LOG_FILE):
            time.sleep(1)
            continue

        size = os.path.getsize(LOG_FILE)

        if size < last_size:
            last_size = 0

        if size > last_size:
            with open(LOG_FILE, "r") as f:
                f.seek(last_size)

                new_lines = f.readlines()
                last_size = f.tell()

                for line in new_lines:
                    line = line.strip()
                    print("RAW:", line)

                    name, pid = get_player(line)

                    if pid:
                        if pid not in players:
                            players[pid] = {}

                        players[pid]["name"] = name

                        coords = get_coords(line)
                        if coords:
                            players[pid]["coords"] = coords

                        if "hit" in line.lower():
                            players[pid]["attacker"] = name

                        if "died" in line.lower():
                            victim = players[pid].get("name", "Unknown")
                            killer = players[pid].get("attacker", "Unknown")

                            v_coords = players[pid].get("coords")
                            k_coords = None

                            for p in players.values():
                                if p.get("name") == killer:
                                    k_coords = p.get("coords")

                            dist = distance(v_coords, k_coords)

                            save_kill(killer, victim, dist)

                            asyncio.run_coroutine_threadsafe(
                                send_kill(victim, killer, dist),
                                client.loop
                            )

        time.sleep(1)

# ================== START ==================
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

    threading.Thread(target=log_updater, daemon=True).start()
    threading.Thread(target=track_logs, daemon=True).start()

client.run(DISCORD_TOKEN)
