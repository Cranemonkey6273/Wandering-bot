import discord
import os
import time
import threading
import asyncio
import re
import json

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580

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

# ===== PLAYER =====
def get_player(pid):
    if pid not in players:
        players[pid] = {
            "name": "Unknown",
            "kills": 0,
            "deaths": 0,
            "streak": 0,
            "last_attacker": None,
            "weapon": None,
            "coords": None,
            "last_seen": time.time()
        }
    return players[pid]

# ===== LOG FILE =====
def get_log_file():
    files = [f for f in os.listdir() if f.endswith(".ADM")]
    return sorted(files)[-1] if files else None

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
    return m.group(1) if m else None

def parse_weapon(line):
    weapons = ["m4", "ak", "mosin", "sk", "pistol", "shotgun", "rifle"]
    for w in weapons:
        if w in line.lower():
            return w.upper()
    return "Unknown"

# ===== TIME FORMAT =====
def format_time(seconds):
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes}m {seconds}s"

# ===== DISCORD =====
async def send_kill(victim, killer, weapon, coords, survival):
    ch = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="☠️ KILLFEED",
        description=f"**{killer} eliminated {victim}**",
        color=0x8B0000
    )

    embed.add_field(name="⏱ Survival Time", value=survival, inline=True)
    embed.add_field(name="🔫 Weapon", value=weapon, inline=True)

    if coords:
        embed.add_field(name="📍 Location", value=coords, inline=False)

    # stats
    for pid, p in players.items():
        if p["name"] == killer:
            embed.add_field(
                name=f"{killer}",
                value=f"Kills: {p['kills']} | Streak: {p['streak']}",
                inline=True
            )
        if p["name"] == victim:
            embed.add_field(
                name=f"{victim}",
                value=f"Deaths: {p['deaths']}",
                inline=True
            )

    embed.set_footer(text="Wandering Survival System")

    await ch.send(embed=embed)

# ===== TRACKER =====
def track_logs():
    global LOG_FILE

    while not LOG_FILE:
        print("Waiting for log...")
        time.sleep(2)
        LOG_FILE = get_log_file()

    print("Tracking:", LOG_FILE)

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

            if pid:
                p = get_player(pid)
                p["name"] = name

            coords = parse_coords(line)
            if pid and coords:
                players[pid]["coords"] = coords

            # ===== HIT =====
            if "hit" in line.lower():
                attacker, _ = parse_player(line)
                weapon = parse_weapon(line)

                if pid:
                    players[pid]["last_attacker"] = attacker
                    players[pid]["weapon"] = weapon

            # ===== DEATH =====
            if "died" in line.lower():
                if pid and pid in players:
                    victim_data = players[pid]

                    victim = victim_data["name"]
                    killer = victim_data["last_attacker"] or "Unknown"
                    weapon = victim_data["weapon"] or "Unknown"
                    coords = victim_data["coords"]

                    # survival time
                    survival_seconds = time.time() - victim_data["last_seen"]
                    survival = format_time(survival_seconds)

                    # update victim
                    victim_data["deaths"] += 1
                    victim_data["streak"] = 0
                    victim_data["last_seen"] = time.time()

                    # update killer
                    for p in players.values():
                        if p["name"] == killer:
                            p["kills"] += 1
                            p["streak"] += 1

                    save_data()

                    asyncio.run_coroutine_threadsafe(
                        send_kill(victim, killer, weapon, coords, survival),
                        client.loop
                    )

# ===== READY =====
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    threading.Thread(target=track_logs, daemon=True).start()

# ===== RUN =====
client.run(TOKEN)