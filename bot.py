import discord
import os
import time
import threading
import asyncio
import re

# ===== CONFIG =====
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580

# ===== MEMORY =====
players = {}  # id -> {name, last_hit_by, last_weapon}

# ===== GET LOG =====
def get_log_file():
    files = [f for f in os.listdir() if f.endswith(".ADM")]
    return sorted(files)[-1] if files else None

LOG_FILE = get_log_file()

intents = discord.Intents.default()
client = discord.Client(intents=intents)

print("USING LOG:", LOG_FILE)

# ===== PARSERS =====

def get_player_info(line):
    name_match = re.search(r'Player "(.+?)"', line)
    id_match = re.search(r'id=([A-Z0-9]+)', line)

    name = name_match.group(1) if name_match else "Unknown"
    pid = id_match.group(1) if id_match else None

    return name, pid

def get_coords(line):
    match = re.search(r'pos=<(.+?)>', line)
    return match.group(1) if match else None

def get_weapon(line):
    weapons = ["m4", "ak", "mosin", "sk", "shotgun", "pistol"]
    for w in weapons:
        if w in line.lower():
            return w.upper()
    return "Unknown"

# ===== DETECTION =====

def detect_event(line):
    l = line.lower()

    if "hit" in l:
        return "hit"

    if "died" in l:
        return "death"

    if "suicide" in l:
        return "suicide"

    if "built" in l or "placed" in l:
        return "build"

    return None

# ===== DISCORD =====

async def send_kill(victim, killer, weapon):
    channel = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="💀 KILL EVENT",
        description=f"**{killer} killed {victim}**",
        color=0xff0000
    )

    embed.add_field(name="🔫 Weapon", value=weapon, inline=True)
    embed.set_footer(text="Wandering Survival System")

    await channel.send(embed=embed)


async def send_build(player, line):
    channel = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="🧱 BUILD",
        description=f"**{player} built something**",
        color=0x00ff88
    )

    embed.add_field(name="📋", value=f"```{line[:200]}```", inline=False)

    await channel.send(embed=embed)

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

            event = detect_event(line)
            name, pid = get_player_info(line)

            if pid and pid not in players:
                players[pid] = {
                    "name": name,
                    "last_hit_by": None,
                    "weapon": None
                }

            # ===== HIT TRACKING =====
            if event == "hit":
                attacker_match = re.search(r'Player "(.+?)"', line)
                weapon = get_weapon(line)

                if pid:
                    players[pid]["last_hit_by"] = attacker_match.group(1) if attacker_match else "Unknown"
                    players[pid]["weapon"] = weapon

            # ===== DEATH =====
            elif event == "death":
                if pid and pid in players:
                    victim = players[pid]["name"]
                    killer = players[pid]["last_hit_by"] or "Unknown"
                    weapon = players[pid]["weapon"] or "Unknown"

                    asyncio.run_coroutine_threadsafe(
                        send_kill(victim, killer, weapon),
                        client.loop
                    )

            # ===== BUILD =====
            elif event == "build":
                asyncio.run_coroutine_threadsafe(
                    send_build(name, line),
                    client.loop
                )

# ===== READY =====

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    threading.Thread(target=track_logs, daemon=True).start()

# ===== RUN =====

client.run(TOKEN)