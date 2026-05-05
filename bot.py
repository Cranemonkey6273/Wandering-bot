import discord
import os
import time
import threading
import asyncio

# ===== CONFIG =====
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580  # YOUR CHANNEL ID
LOG_FILE = "DayZServer_X1_x64_2026-05-04_22-18-27.ADM"  # YOUR LOG FILE NAME

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ===== EVENT DETECTION =====
def detect_event(line):
    line_lower = line.lower()

    if any(word in line_lower for word in ["died", "suicide", "killed"]):
        return "death"

    if any(word in line_lower for word in ["placed", "built", "constructed"]):
        return "build"

    return None


# ===== EMBED SENDERS =====
async def send_killfeed(line):
    channel = client.get_channel(CHANNEL_ID)

    # Extract player name (basic)
    victim = "Unknown"
    try:
        parts = line.split('"')
        if len(parts) >= 2:
            victim = parts[1]
    except:
        pass

    is_suicide = "suicide" in line.lower()

    if is_suicide:
        title = f"💀 {victim} died (Suicide)"
    else:
        title = f"💀 {victim} died"

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

    player = "Unknown"
    try:
        parts = line.split('"')
        if len(parts) >= 2:
            player = parts[1]
    except:
        pass

    embed = discord.Embed(
        title=f"🧱 Construction Event",
        description="━━━━━━━━━━━━━━━━━━",
        color=0x8B4513
    )

    embed.add_field(
        name="🏗️ Builder",
        value=player,
        inline=True
    )

    embed.add_field(
        name="📍 Details",
        value=f"```{line[:200]}```",
        inline=False
    )

    embed.set_footer(text="Wandering Survival Feed")

    await channel.send(embed=embed)


# ===== LOG TRACKER =====
def track_logs():
    print("TRACKER STARTED")

    try:
        with open(LOG_FILE, "r") as f:
            f.seek(0, 2)  # START AT END (LIVE MODE)

            while True:
                line = f.readline()

                if not line:
                    time.sleep(0.5)
                    continue

                line = line.strip()
                print("RAW:", line)

                event = detect_event(line)

                if event == "death":
                    print("DEATH EVENT:", line)
                    asyncio.run_coroutine_threadsafe(
                        send_killfeed(line),
                        client.loop
                    )

                elif event == "build":
                    print("BUILD EVENT:", line)
                    asyncio.run_coroutine_threadsafe(
                        send_buildfeed(line),
                        client.loop
                    )

    except Exception as e:
        print("Log tracking error:", e)


# ===== DISCORD EVENTS =====
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")

    print("STARTING TRACKER...")
    threading.Thread(target=track_logs, daemon=True).start()


# ===== RUN =====
client.run(TOKEN)