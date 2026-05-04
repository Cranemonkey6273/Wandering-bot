import discord, os
from openai import OpenAI
from log_parser import parse_line
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

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")
    process_logs()

@client.event
async def on_message(message):
    print(f"Message received: {message.content}")  # ✅ FIXED

    if message.author == client.user:
        return

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

    # ===== ECONOMY =====
    elif message.content.startswith("!balance"):
        bal = get_balance(user_id)
        await message.channel.send(f"💰 Balance: {bal}")

    # ===== HEATMAP =====
    elif message.content.startswith("!heatmap"):
        data = get_hotspots()
        await message.channel.send(f"🔥 PvP Hotspots:\n{data}")

client.run(os.getenv("DISCORD_TOKEN"))
