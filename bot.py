import discord
import os
import threading
import time

# ===== DISCORD SETUP =====
intents = discord.Intents.all()
client = discord.Client(intents=intents)

# ===== FIND LATEST ADM FILE =====
def get_latest_log():
    files = [f for f in os.listdir() if f.endswith(".ADM")]
    if not files:
        print("❌ No ADM files found")
        return None
    latest = max(files, key=os.path.getctime)
    print(f"📂 Using log file: {latest}")
    return latest

# ===== TRACK LOGS =====
def track_logs():
    print("TRACKER STARTED")

    log_file = get_latest_log()
    if not log_file:
        return

    try:
        with open(log_file, "r") as f:
            f.seek(0)  # go to end of file

            while True:
                line = f.readline()

                if not line:
                    time.sleep(0.5)
                    continue

                line = line.strip()
                print("LOG:", line)

                # 🔥 DEATH DETECTION (FIXED)
                if any(word in line.lower() for word in ["died", "killed", "suicide"]):
                    print("💀 DEATH EVENT:", line)

    except Exception as e:
        print("Log tracking error:", e)

# ===== BOT READY EVENT =====
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")

    print("STARTING TRACKER...")
    threading.Thread(target=track_logs, daemon=True).start()

# ===== RUN BOT =====
client.run(os.getenv("DISCORD_TOKEN"))