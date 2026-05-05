import discord
import os
import time
import asyncio
import threading

# ================= CONFIG =================
KILLFEED_CHANNEL_ID = 1501126258140909580  # your channel
LOG_FILE = "DayZServer_X1_x64_2026-05-04_22-18-27.ADM"  # update if needed

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ================= DISCORD SEND =================
async def send_message(msg):
    await client.wait_until_ready()
    channel = client.get_channel(KILLFEED_CHANNEL_ID)
    if channel:
        await channel.send(msg)

# ================= EVENT DETECTION =================
def detect_event(line):
    line_lower = line.lower()

    # 💀 Death detection
    if "died" in line_lower or "committed suicide" in line_lower:
        return "death"

    # 🧱 Build / placement detection
    if any(word in line_lower for word in [
        "placed", "built", "constructed"
    ]):
        return "build"

    return None

# ================= LOG TRACKER =================
def track_logs():
    print("TRACKER STARTED")

    try:
        with open(LOG_FILE, "r") as f:
            f.seek(0)  # LIVE MODE

            while True:
                line = f.readline()

                if not line:
                    time.sleep(0.5)
                    continue

                line = line.strip()
                event = detect_event(line)

                if event == "death":
                    print("💀", line)
                    asyncio.run_coroutine_threadsafe(
                        send_message(f"💀 {line}"),
                        client.loop
                    )

                elif event == "build":
                    print("🧱", line)
                    asyncio.run_coroutine_threadsafe(
                        send_message(f"🧱 {line}"),
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