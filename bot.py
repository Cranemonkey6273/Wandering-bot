import discord
import os
import time
import threading
import asyncio
import re
import json
import math
from supabase import create_client

# ===== CONFIG =====
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580

SUPABASE_URL = "PASTE_URL_HERE"
SUPABASE_KEY = "PASTE_KEY_HERE"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

client = discord.Client(intents=discord.Intents.default())

DATA_FILE = "players.json"

# ===== LOAD / SAVE =====
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(players, f, indent=2)

players = load_data()

# ===== GET LOG FILE =====
def get_log_file():
    files = [f for f in os.listdir() if f.endswith(".ADM")]
    if not files:
        print("❌ NO ADM FILE FOUND")
        return None
    latest = sorted(files)[-1]
    print("✅ USING LOG FILE:", latest)
    return latest

LOG_FILE = get_log_file()

# ===== PARSERS =====
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
        coords = m.group(1).split(",")
        return tuple(map(float, coords))
    return None

def parse_weapon(line):
    weapons = ["m4", "ak", "mosin", "sk", "pistol", "shotgun", "rifle"]
    for w in weapons:
        if w in line.lower():
            return w.upper()
    return "Unknown"

# ===== DISTANCE =====
def calculate_distance(c1, c2):
    if not c1 or not c2:
        return "Unknown"
    return f"{round(math.dist(c1, c2), 2)}m"

# ===== TIME =====
def format_time(seconds):
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes}m {seconds}s"

# ===== DATABASE =====
def save_kill_to_db(killer, victim, weapon, distance):
    try:
        print("🔥 SAVING TO DATABASE:", killer, victim)
        supabase.table("kills").insert({
            "killer": killer,
            "victim": victim,
            "weapon": weapon,
            "distance": float(distance.replace("m","")) if distance != "Unknown" else None
        }).execute()
    except Exception as e:
        print("❌ DB ERROR:", e)

# ===== DISCORD =====
async def send_kill(victim, killer, weapon, coords, distance, survival):
    ch = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="☠️ KILLFEED",
        description=f"**{killer} killed {victim}**",
        color=0x8B0000
    )

    embed.add_field(name="🔫 Weapon", value=weapon, inline=True)
    embed.add_field(name="📏 Distance", value=distance, inline=True)
    embed.add_field(name="⏱ Survival", value=survival, inline=True)

    if coords:
        embed.add_field(name="📍 Location", value=str(coords), inline=False)

    embed.set_footer(text="🔥 Wandering Elite Survival System")

    await ch.send(embed=embed)

# ===== TRACK LOGS =====
def track_logs():
    global LOG_FILE

    while not LOG_FILE:
        print("⏳ WAITING FOR LOG FILE...")
        time.sleep(2)
        LOG_FILE = get_log_file()

    print("📡 TRACKING:", LOG_FILE)

    with open(LOG_FILE, "r") as f:
        f.seek(0, 2)

        while True:
            line = f.readline()

            if not line:
                time.sleep(0.5)
                continue

            line = line.strip()
            print("RAW:", line)  # 🔥 IMPORTANT DEBUG

            name, pid = parse_player(line)

            if pid:
                p = players.setdefault(pid, {})
                p["name"] = name

            coords = parse_coords(line)
            if pid and coords:
                players[pid]["coords"] = coords

            # HIT
            if "hit" in line.lower():
                attacker, _ = parse_player(line)
                weapon = parse_weapon(line)

                if pid:
                    players[pid]["last_attacker"] = attacker
                    players[pid]["weapon"] = weapon

            # DEATH
            if "died" in line.lower():
                if pid in players:
                    victim_data = players[pid]

                    victim = victim_data.get("name", "Unknown")
                    killer = victim_data.get("last_attacker", "Unknown")
                    weapon = victim_data.get("weapon", "Unknown")
                    coords = victim_data.get("coords")

                    survival = "Unknown"

                    killer_coords = None
                    for p in players.values():
                        if p.get("name") == killer:
                            killer_coords = p.get("coords")

                    distance = calculate_distance(coords, killer_coords)

                    save_kill_to_db(killer, victim, weapon, distance)

                    asyncio.run_coroutine_threadsafe(
                        send_kill(victim, killer, weapon, coords, distance, survival),
                        client.loop
                    )

# ===== READY =====
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    threading.Thread(target=track_logs, daemon=True).start()

# ===== RUN =====
client.run(TOKEN)