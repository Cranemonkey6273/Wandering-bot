import discord
import os
import time
import threading
import asyncio
import re

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580

client = discord.Client(intents=discord.Intents.default())

# ===== PLAYER DATA =====
players = {}

def get_player(pid):
    if pid not in players:
        players[pid] = {
            "name": "Unknown",
            "kills": 0,
            "deaths": 0,
            "streak": 0,
            "last_attacker": None,
            "weapon": None,
            "coords": None
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

# ===== DISCORD OUTPUT =====

async def send_kill(victim, killer, weapon, coords):
    ch = client.get_channel(CHANNEL_ID)

    killer_data = None
    victim_data = None

    # find players by name
    for pid, data in players.items():
        if data["name"] == killer:
            killer_data = data
        if data["name"] == victim:
            victim_data = data

    embed = discord.Embed(
        title="💀 KILLFEED",
        description=f"**{killer} killed {victim}**",
        color=0xff0000
    )

    embed.add_field(name="🔫 Weapon", value=weapon, inline=True)

    if coords:
        embed.add_field(name="📍 Location", value=coords, inline=False)

    if killer_data:
        embed.add_field(
            name=f"{killer} Stats",
            value=f"Kills: {killer_data['kills']}\nStreak: {killer_data['streak']}",
            inline=True
        )

    if victim_data:
        embed.add_field(
            name=f"{victim} Stats",
            value=f"Deaths: {victim_data['deaths']}",
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

                    # update stats
                    victim_data["deaths"] += 1
                    victim_data["streak"] = 0

                    # update killer stats
                    for p in players.values():
                        if p["name"] == killer:
                            p["kills"] += 1
                            p["streak"] += 1

                    asyncio.run_coroutine_threadsafe(
                        send_kill(victim, killer, weapon, coords),
                        client.loop
                    )

# ===== READY =====

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    threading.Thread(target=track_logs, daemon=True).start()

# ===== RUN =====

client.run(TOKEN)