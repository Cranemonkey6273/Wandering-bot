import discord
import os
import time
import threading
import asyncio

# ===== CONFIG =====
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580  # your channel
LOG_FILE = "DayZServer_X1_x64_2026-05-04_22-18-27.ADM"  # update if name changes

intents = discord.Intents.default()
client = discord.Client(intents=intents)

print("FILES:", os.listdir())  # debug: confirm log exists

# ===== EVENT DETECTION =====
def detect_event(line):
    line_lower = line.lower()

    if any(w in line_lower for w in ["died", "suicide", "killed"]):
        return "death"

    if any(w in line_lower for w in ["placed", "built", "constructed"]):
        return "build"

    if any(w in line_lower for w in ["unconscious", "consciousness", "fell", "hit", "damage"]):
        return "damage"

    return None


# ===== DISCORD SENDERS =====
async def send_killfeed(line):
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return

    victim = "Unknown"
    try:
        parts = line.split('"')
        if len(parts) >= 2:
            victim = parts[1]
    except:
        pass

    title = f"💀 {victim} died"
    if "suicide" in line.lower():
        title += " (Suicide)"

    embed = discord.Embed(
        title=title,
        description="━━━━━━━━━━━━━━━━━━",
        color=0xff0000
    )

    embed.add_field(
        name="📍 Event Log",
        value=f"```{line[:200]}```",
        inline=False
    )

    embed.set_footer(text="Wandering Survival Feed")

    await channel.send(embed=embed)


async def send_buildfeed(line):
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        return

    player = "Unknown"
    try:
        parts = line.split('"')
        if len(parts) >= 2:
            player = parts[1]
    except:
        pass

    embed = discord.Embed(
        title="🧱 Construction Event",
        description="━━━━━━━━━━━━━━━━━━",
        color=0x8B4513
    )

    embed.add_field(name="🏗️ Builder", value=player, inline=True)
    embed.add_field(name="📍 Details", value=f"```{line[:200]}```", inline=False)

    embed.set_footer(text="Wandering Survival Feed")

    await channel.send(embed=embed)


async def send_damagefeed(line):
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        return

    player = "Unknown"
    try:
        parts = line.split('"')
        if len(parts) >= 2:
            player = parts[1]
    except:
        pass

    embed = discord.Embed(
        title="👊 Damage Event",
        description="━━━━━━━━━━━━━━━━━━",
        color=0xffa500
    )

    embed.add_field(name="🧍 Player", value=player, inline=True)
    embed.add_field(name="📍 Details", value=f"```{line[:200]}```", inline=False)

    embed.set_footer(text="Wandering Survival Feed")

    await channel.send(embed=embed)


# ===== LOG TRACKER =====
def track_logs():
    print("TRACKER STARTED")

    # Wait for file (prevents crash/restart loop)
    while not os.path.exists(LOG_FILE):
        print("Waiting for log file...")
        time.sleep(2)

    print("Log file found!")

    try:
        with open(LOG_FILE, "r") as f:
            f.seek(0, 2)  # live mode

            while True:
                line = f.readline()

                if not line:
                    time.sleep(0.5)
                    continue

                line = line.strip()
                print("RAW:", line)

                event = detect_event(line)

                if event == "death":
                    print("💀 DEATH:", line)
                    asyncio.run_coroutine_threadsafe(
                        send_killfeed(line),
                        client.loop
                    )

                elif event == "build":
                    print("🧱 BUILD:", line)
                    asyncio.run_coroutine_threadsafe(
                        send_buildfeed(line),
                        client.loop
                    )

                elif event == "damage":
                    print("👊 DAMAGE:", line)
                    asyncio.run_coroutine_threadsafe(
                        send_damagefeed(line),
                        client.loop
                    )

    except Exception as e:
        print("Log tracking error:", e)


# ===== DISCORD READY =====
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")

    print("STARTING TRACKER...")
    threading.Thread(target=track_logs, daemon=True).start()


# ===== RUN =====
client.run(TOKEN)