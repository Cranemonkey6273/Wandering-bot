import discord
import os
import time
import threading
import asyncio
import re
import json
import math
import requests
from supabase import create_client

# ================= CONFIG =================
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580

SUPABASE_URL = "https://bqqeorqzezcgzqflqoms.supabase.co"
SUPABASE_KEY = "sb_publishable_fTUe0hG1Amm3cZ13155ljQ_EQYxmYPz"

NITRADO_TOKEN = "hoAZfsBJmKrY1kOGykAusZ309VDRVxINN_hNAG5NlqWOC5r63-45tH6Ws2OM7h9FC7oPjUgiDO6_-g8-BCKfwJ96FH-uMVgqEayY"
SERVICE_ID = "ni12248929_1"

LOG_FILE = "server.ADM"

# ================= INIT =================
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = discord.Client(intents=discord.Intents.default())

players = {}

# ================= NITRADO LOG DOWNLOAD =================
def download_log():
    try:
        headers = {"Authorization": f"Bearer {NITRADO_TOKEN}"}

        url = f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list"
        res = requests.get(url, headers=headers).json()

        files = res["data"]["entries"]
        adm_files = [f for f in files if f["path"].endswith(".ADM")]

        if not adm_files:
            print("❌ No ADM files found")
            return

        latest = sorted(adm_files, key=lambda x: x["modified"])[-1]["path"]

        download_url = f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/download?file={latest}"
        res = requests.get(download_url, headers=headers).json()

        file_url = res["data"]["token"]["url"]
        file_data = requests.get(file_url).text

        with open(LOG_FILE, "w") as f:
            f.write(file_data)

        print("✅ Log updated")

    except Exception as e:
        print("❌ LOG DOWNLOAD ERROR:", e)

# ================= AUTO UPDATE =================
def log_updater():
    while True:
        download_log()
        time.sleep(5)

# ================= PARSING =================
def parse_player(line):
    name = re.search(r'Player "(.+?)"', line)
    pid = re.search(r'id=([A-Z0-9]+)', line)
    return (
        name.group(1) if name else "Unknown",
        pid.group(1) if pid else None
    )

def parse_coords(line):
    m = re.search(r'pos=<(.+?)>', line)
    if m:
        return tuple(map(float, m.group(1).split(",")))
    return None

def parse_weapon(line):
    weapons = ["m4", "ak", "mosin", "sk", "pistol", "shotgun"]
    for w in weapons:
        if w in line.lower():
            return w.upper()
    return "Unknown"

def calculate_distance(c1, c2):
    if not c1 or not c2:
        return "Unknown"
    return f"{round(math.dist(c1, c2), 2)}m"

# ================= DATABASE =================
def save_kill(killer, victim, weapon, distance):
    try:
        print("🔥 SAVING:", killer, victim)
        supabase.table("kills").insert({
            "killer": killer,
            "victim": victim,
            "weapon": weapon,
            "distance": float(distance.replace("m","")) if distance != "Unknown" else None
        }).execute()
    except Exception as e:
        print("❌ DB ERROR:", e)

# ================= DISCORD =================
async def send_kill(victim, killer, weapon, distance):
    ch = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="☠️ KILLFEED",
        description=f"**{killer} killed {victim}**",
        color=0x8B0000
    )

    embed.add_field(name="🔫 Weapon", value=weapon, inline=True)
    embed.add_field(name="📏 Distance", value=distance, inline=True)

    embed.set_footer(text="🔥 Wandering Survival System")

    await ch.send(embed=embed)

# ================= TRACKER =================
def track_logs():
    print("📡 TRACKING LOG:", LOG_FILE)

    with open(LOG_FILE, "r") as f:
        f.seek(0, 2)

        while True:
            line = f.readline()

            if not line:
                time.sleep(0.5)
                continue

            line = line.strip()
            print("RAW:", line)

            name, pid = parse_player(line)

            if pid not in players:
                players[pid] = {}

            players[pid]["name"] = name

            coords = parse_coords(line)
            if coords:
                players[pid]["coords"] = coords

            if "hit" in line.lower():
                attacker, _ = parse_player(line)
                players[pid]["attacker"] = attacker
                players[pid]["weapon"] = parse_weapon(line)

            if "died" in line.lower():
                victim = players[pid].get("name", "Unknown")
                killer = players[pid].get("attacker", "Unknown")
                weapon = players[pid].get("weapon", "Unknown")

                victim_coords = players[pid].get("coords")

                killer_coords = None
                for p in players.values():
                    if p.get("name") == killer:
                        killer_coords = p.get("coords")

                distance = calculate_distance(victim_coords, killer_coords)

                save_kill(killer, victim, weapon, distance)

                asyncio.run_coroutine_threadsafe(
                    send_kill(victim, killer, weapon, distance),
                    client.loop
                )

# ================= READY =================
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

    threading.Thread(target=log_updater, daemon=True).start()
    threading.Thread(target=track_logs, daemon=True).start()

# ================= RUN =================
client.run(TOKEN)