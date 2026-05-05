import discord
import os
import time
import threading
import asyncio
import re

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580

client = discord.Client(intents=discord.Intents.default())

# ===== PLAYER MEMORY =====
players = {}

# ===== GET LOG =====
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
    weapons = ["m4", "ak", "mosin", "sk", "pistol", "shotgun"]
    for w in weapons:
        if w in line.lower():
            return w.upper()
    return "Unknown"

# ===== DISCORD =====

async def send_kill(victim, killer, weapon, coords):
    ch = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="💀 KILLFEED",
        description=f"**{killer} killed {victim}**",
        color=0xff0000
    )

    embed.add_field(name="🔫 Weapon", value=weapon, inline=True)

    if coords:
        embed.add_field(name="📍 Location", value=coords, inline=False)

    embed.set_footer(text="Wandering Survival System")

    await ch.send(embed=embed)


async def send_uncon(player):
    ch = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="🧍 UNCONSCIOUS",
        description=f"**{player} is unconscious**",
        color=0xffa500
    )

    await ch.send(embed=embed)


async def send_hit(attacker, victim, weapon):
    ch = client.get_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="🔫 HIT EVENT",
        description=f"**{attacker} hit {victim}**",
        color=0x800080
    )

    embed.add_field(name="Weapon", value=weapon, inline=True)

    await ch.send(embed=embed)

# ===== CORE TRACKER =====

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

            if pid and pid not in players:
                players[pid] = {
                    "name": name,
                    "last_attacker": None,
                    "weapon": None,
                    "coords": None
                }

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

                    asyncio.run_coroutine_threadsafe(
                        send_hit(attacker, name, weapon),
                        client.loop
                    )

            # ===== UNCON =====
            if "unconscious" in line.lower():
                asyncio.run_coroutine_threadsafe(
                    send_uncon(name),
                    client.loop
                )

            # ===== DEATH =====
            if "died" in line.lower():
                if pid and pid in players:
                    victim = players[pid]["name"]
                    killer = players[pid]["last_attacker"] or "Unknown"
                    weapon = players[pid]["weapon"] or "Unknown"
                    coords = players[pid]["coords"]

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