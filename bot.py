import discord, os
from openai import OpenAI
from economy import get_balance, add_money
from heatmap import record_kill, get_hotspots

intents = discord.Intents.all()
client = discord.Client(intents=intents)

ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
import time

def track_logs():
    print("TRACKER STARTED")
    
import os
print("FILES:", os.listdir())

    try:
        with open("DayZServer_X1_x64_2026-05-04_22-18-27.ADM", "r") as f:
            f.seek(0)

            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue

                if "died" in line:
                    print("DEATH EVENT:", line)

    except Exception as e:
        print("Log tracking error:", e)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")

    import threading

    print("STARTING TRACKER...")  # 👈 ADD THIS
    threading.Thread(target=track_logs, daemon=True).start()


client.run(os.getenv("DISCORD_TOKEN"))
