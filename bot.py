import discord
import os
import threading
import time
import re

# ===== CONFIG =====
CHANNEL_ID = 123456789012345678  # 🔥 PUT YOUR CHANNEL ID HERE

intents = discord.Intents.default()
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

# ===== PARSING FUNCTIONS =====
def extract_player(line):
    match = re.search(r'Player "(.+?)"', line)
    return match.group(1) if match else "Unknown"

def extract_coords(line):
    match = re.search(r'pos=<([\d\.]+), ([\d\.]+),', line)
    if match:
        return f"{int(float(match.group(1)))}, {int(float(match.group(2)))}"
    return "Unknown"

def extract_time(line):
    match = re.search(r'^(\d{2}:\d{2}:\d{2})', line)
    return match.group(1) if match else "Unknown"

# ===== TRACK LOGS =====
def track_logs():
    print("TRACKER STARTED")

    log_file = get_latest_log()
    if not log_file:
        return

    try:
        with open(log_file, "r") as f:
            f.seek(0, 2)  # LIVE MODE

            while True:
                line = f.readline()

                if not line:
                    time.sleep(0.5)
                    continue

                line = line.strip()
                print("LOG:", line)

                if "committed suicide" in line.lower():
                    player = extract_player(line)
                    coords = extract_coords(line)
                    time_of_death = extract_time(line)

                    embed = discord.Embed(
                        title="💀 SURVIVOR LOST",
                        description=f"☠️ **{player}** took their own life",
                        color=0x8B0000
                    )

                    embed.add_field(name="📍 Location", value=coords, inline=True)
                    embed.add_field(name="🕒 Time", value=time_of_death, inline=True)
                    embed.set_footer(text="⚠️ The wasteland claims another soul...")

                    client.loop.create_task(send_to_discord(embed))

                elif "died" in line.lower():
                    player = extract_player(line)
                    coords = extract_coords(line)
                    time_of_death = extract_time(line)

                    embed = discord.Embed(
                        title="💀 SURVIVOR DOWN",
                        description=f"☠️ **{player}** has fallen",
                        color=0xB22222
                    )

                    embed.add_field(name="📍 Location", value=coords, inline=True)
                    embed.add_field(name="🕒 Time", value=time_of_death, inline=True)
                    embed.set_footer(text="🩸 Blood stains the land of Chernarus")

                    client.loop.create_task(send_to_discord(embed))

    except Exception as e:
        print("Log tracking error:", e)

# ===== SEND TO DISCORD =====
async def send_to_discord(embed):
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    if channel:
        await channel.send(embed=embed)
    else:
        print("❌ Channel not found")

# ===== BOT READY =====
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")

    print("STARTING TRACKER...")
    threading.Thread(target=track_logs, daemon=True).start()

# ===== RUN =====
client.run(os.getenv("DISCORD_TOKEN"))