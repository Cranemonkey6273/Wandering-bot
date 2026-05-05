import discord
import os
import time
import threading
from openai import OpenAI

# ===== DISCORD SETUP =====
intents = discord.Intents.all()
client = discord.Client(intents=intents)

# ===== OPENAI =====
ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== SYSTEM PROMPT =====
SYSTEM_PROMPT = """
You are Wandering Bot, an advanced DayZ survival AI.

STRICT RULES:
ONLY talk about DayZ
Help with survival, PvP, loot, and server gameplay
Be immersive and tactical

Server info:
Modded stamina
Custom loadouts
Vehicles enabled
Active PvP zones
"""

# ===== LOG TRACKER =====
def track_logs():
    print("TRACKER STARTED")

    print("FILES:", os.listdir())  # debug

    try:
        with open("DayZServer_X1_x64_2026-05-04_22-18-27.ADM", "r") as f:
            f.seek(0)

            while True:
                line = f.readline()

                if not line:
                    time.sleep(0.5)
                    continue

                print("LOG:", line)

                if "died" in line.lower():
                    print("DEATH EVENT:", line)

    except Exception as e:
        print("Log tracking error:", e)

# ===== BOT READY =====
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")

    print("STARTING TRACKER...")
    threading.Thread(target=track_logs, daemon=True).start()

# ===== MESSAGE HANDLER =====
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    print(f"Message received: {message.content}")

    if message.content.startswith("!ask"):
        prompt = message.content[5:]

        response = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )

        reply = response.choices[0].message.content
        await message.channel.send(reply)

# ===== RUN BOT =====
client.run(os.getenv("DISCORD_TOKEN"))