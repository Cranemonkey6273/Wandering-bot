import discord
import os
import time
import threading
import asyncio
import re

# ===== CONFIG =====
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580

def get_log_file():
    files = [f for f in os.listdir() if f.endswith(".ADM")]
    return sorted(files)[-1] if files else None

LOG_FILE = get_log_file()

intents = discord.Intents.default()
client = discord.Client(intents=intents)

print("FILES:", os.listdir())
print("USING LOG:", LOG_FILE)

# ===== PARSERS =====

def extract_player(line):
    match = re.search(r'Player "(.+?)"', line)
    return match.group(1) if match else "Unknown"

def extract_coords(line):
    match = re.search(r'pos=<(.+?)>', line)
    return match.group(1) if match else None

def extract_object(line):
    match = re.search(r'(built|placed) ([^ ]+)', line.lower())
    return match.group(2) if match else "Unknown"

def extract_tool(line):
    tools = ["hatchet", "shovel", "hammer", "sledgehammer"]
    for tool in tools:
        if tool in line.lower():
            return tool.title()
    return "Unknown"

# ===== EVENT DETECTION =====
def detect_event(line):
    l = line.lower()

    if "suicide" in l:
        return "suicide"

    if "died" in l:
        return "death"

    if "unconscious" in l:
        return "uncon"

    if "consciousness" in l:
        return "wake"

    if any(w in l for w in ["infected", "zombie"]):
        return "zombie"

    if any(w in l for w in ["bear", "wolf", "animal"]):
        return "animal"

    if any(w in l for w in ["hit by player", "killed by player"]):
        return "pvp"

    if any(w in l for w in ["built", "placed", "constructed"]):
        return "build"

    if any(w in l for w in ["damage", "hit", "bleed", "fall"]):
        return "damage"

    return None

# ===== EMBEDS =====

async def send_build(line):
    channel = client.get_channel(CHANNEL_ID)

    player = extract_player(line)
    coords = extract_coords(line)
    obj = extract_object(line)
    tool = extract_tool(line)

    embed = discord.Embed(
        title="🧱 BUILD EVENT",
        description=f"**{player} is building {obj}**",
        color=0x00ff88
    )

    embed.add_field(name="🛠 Tool", value=tool, inline=True)

    if coords:
        embed.add_field(name="📍 Location", value=coords, inline=False)

    embed.set_footer(text="Wandering Survival System")

    await channel.send(embed=embed)


async def send_damage(title, emoji, color, line):
    channel = client.get_channel(CHANNEL_ID)
    player = extract_player(line)

    embed = discord.Embed(
        title=f"{emoji} {title}",
        description=f"**{player}**",
        color=color
    )

    embed.add_field(name="📋 Log", value=f"```{line[:200]}```", inline=False)

    embed.set_footer(text="Wandering Survival System")

    await channel.send(embed=embed)


# ===== LOG TRACKER =====

def track_logs():
    global LOG_FILE

    print("TRACKER STARTED")

    while not LOG_FILE:
        print("Waiting for log file...")
        time.sleep(2)
        LOG_FILE = get_log_file()

    print("Log file found:", LOG_FILE)

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

            if not event:
                continue

            if event == "build":
                asyncio.run_coroutine_threadsafe(
                    send_build(line),
                    client.loop
                )

            elif event == "death":
                asyncio.run_coroutine_threadsafe(
                    send_damage("Player Died", "💀", 0xff0000, line),
                    client.loop
                )

            elif event == "suicide":
                asyncio.run_coroutine_threadsafe(
                    send_damage("Suicide", "☠️", 0x550000, line),
                    client.loop
                )

            elif event == "uncon":
                asyncio.run_coroutine_threadsafe(
                    send_damage("Unconscious", "🧍", 0xffa500, line),
                    client.loop
                )

            elif event == "wake":
                asyncio.run_coroutine_threadsafe(
                    send_damage("Regained Consciousness", "💓", 0x00ff00, line),
                    client.loop
                )

            elif event == "zombie":
                asyncio.run_coroutine_threadsafe(
                    send_damage("Hit by Zombie", "🧟", 0x228B22, line),
                    client.loop
                )

            elif event == "animal":
                asyncio.run_coroutine_threadsafe(
                    send_damage("Hit by Animal", "🐻", 0x8B0000, line),
                    client.loop
                )

            elif event == "pvp":
                asyncio.run_coroutine_threadsafe(
                    send_damage("Player Combat", "🔫", 0x800080, line),
                    client.loop
                )

            elif event == "damage":
                asyncio.run_coroutine_threadsafe(
                    send_damage("Damage Event", "👊", 0xffa500, line),
                    client.loop
                )


# ===== READY =====

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Bot is live")

    threading.Thread(target=track_logs, daemon=True).start()


# ===== RUN =====
client.run(TOKEN)