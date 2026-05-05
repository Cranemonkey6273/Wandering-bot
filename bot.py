import discord
import os
import time
import asyncio
import threading

# ================= CONFIG =================
KILLFEED_CHANNEL_ID = 1501126258140909580  # your channel ID
LOG_FILE = "DayZServer_X1_x64_2026-05-04_22-18-27.ADM"  # your ADM file name

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ================= DISCORD SEND =================
async def send_killfeed(message):
    await client.wait_until_ready()
    channel = client.get_channel(KILLFEED_CHANNEL_ID)
    if channel:
        await channel.send(message)

# ================= LOG TRACKER =================
def track_logs():
    print("TRACKER STARTED")

    try:
        with open(LOG_FILE, "r") as f:
            f.seek(0, 2)  # go to end of file

            while True:
                line = f.readline()

                if not line:
                    time.sleep(0.5)
                    continue

                # Detect death lines
                if "died" in line or "committed suicide" in line:
                    print("DEATH EVENT:", line.strip())

                    asyncio.run_coroutine_threadsafe(
                        send_killfeed(f"💀 {line.strip()}"),
                        client.loop
                    )

    except Exception as e:
        print("Log tracking error:", e)

# ================= BOT READY =================
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")
    print("STARTING TRACKER...")

    threading.Thread(target=track_logs, daemon=True).start()

# ================= START BOT =================
client.run(os.getenv("DISCORD_TOKEN"))