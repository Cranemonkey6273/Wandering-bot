import discord, os
from openai import OpenAI
from log_parser import parse_logs
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
    try:
        with open("server.ADM", "r") as f:
            f.seek(0)

            while True:
                line = f.readline()
                if not line:
                    time.sleep(1)
                    continue

                data = parse_line(line)

                if data:
                    player = data["player"]
                    x, y, z = data["coords"]

                    print(f"DEATH EVENT: {player} at {x}, {y}")

    except Exception as e:
        print("Log tracking error:", e)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")

    import threading

    print("STARTING TRACKER...")  # 👈 ADD THIS
    threading.Thread(target=track_logs, daemon=True).start()

    # ===== ECONOMY =====
    elif message.content.startswith("!balance"):
        bal = get_balance(user_id)
        await message.channel.send(f"💰 Balance: {bal}")

    # ===== HEATMAP =====
    elif message.content.startswith("!heatmap"):
        data = get_hotspots()
        await message.channel.send(f"🔥 PvP Hotspots:\n{data}")

client.run(os.getenv("DISCORD_TOKEN"))
