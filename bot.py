# =========================================================
# WANDERING BOT V3 - INTELLIGENCE + FACTIONS + AI
# =========================================================

import os
import json
import asyncio
import discord

from datetime import datetime
from discord.ext import commands, tasks
from discord import app_commands

# =========================================================
# OPENAI (AI LAYER)
# =========================================================

from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================================================
# BOT INIT
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================================================
# STORAGE
# =========================================================

guild_configs = {}

online_players = {}
player_stats = {}
swear_counts = {}

# =========================================================
# SWEARS
# =========================================================

SWEARS = ["fuck", "shit", "cunt", "bitch"]

def check_swears(text, user):

    text = text.lower()

    count = sum(word in text for word in SWEARS)

    if count > 0:
        swear_counts[user] = swear_counts.get(user, 0) + count

# =========================================================
# CONFIG HELPERS
# =========================================================

def save_config():
    with open("guild_configs.json", "w") as f:
        json.dump(guild_configs, f, indent=4)

def load_config():
    global guild_configs
    try:
        with open("guild_configs.json", "r") as f:
            guild_configs = json.load(f)
    except:
        guild_configs = {}

# =========================================================
# FACTION ROLE CHECK
# =========================================================

def has_permission(member, role_type, config):

    allowed = config.get("roles", {}).get(role_type, [])

    return any(role.id in allowed for role in member.roles)

# =========================================================
# AI CHAT SYSTEM
# =========================================================

async def ai_response(user, message):

    prompt = f"""
You are a DayZ survival assistant bot.

Style:
- slightly funny
- slightly sarcastic
- helpful
- gives survival tips
- max 2-3 sentences

User: {user}
Message: {message}
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return res.choices[0].message.content

# =========================================================
# CONNECT / DISCONNECT TRACKING
# =========================================================

def handle_connect(player):
    online_players[player] = datetime.utcnow()

    player_stats.setdefault(player, {
        "kills": 0,
        "deaths": 0,
        "builds": 0
    })

def handle_disconnect(player):
    online_players.pop(player, None)

# =========================================================
# SET ROLES (FACTIONS SYSTEM)
# =========================================================

@bot.tree.command(name="set_roles")
async def set_roles(interaction: discord.Interaction, role_type: str, role: discord.Role):

    gid = str(interaction.guild.id)
    config = guild_configs.setdefault(gid, {})

    roles = config.setdefault("roles", {
        "admin_roles": [],
        "faction_roles": [],
        "moderator_roles": []
    })

    if role.id not in roles[role_type]:
        roles[role_type].append(role.id)

    save_config()

    await interaction.response.send_message(
        f"✅ {role.name} added to {role_type}",
        ephemeral=True
    )

# =========================================================
# FACTION COMMAND
# =========================================================

@bot.tree.command(name="create_faction")
async def create_faction(interaction: discord.Interaction, name: str):

    config = guild_configs.get(str(interaction.guild.id))

    if not config or not has_permission(interaction.user, "faction_roles", config):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return

    await interaction.response.send_message(f"🏴 Faction {name} created", ephemeral=True)

# =========================================================
# SWEAR JAR
# =========================================================

@bot.tree.command(name="swearjar")
async def swearjar(interaction: discord.Interaction):

    top = sorted(swear_counts.items(), key=lambda x: x[1], reverse=True)

    text = "\n".join([f"{u}: {c}" for u, c in top[:10]]) or "Clean server"

    await interaction.response.send_message(text)

# =========================================================
# AI CHAT HOOK
# =========================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    check_swears(message.content, str(message.author))

    if bot.user in message.mentions:

        reply = await ai_response(message.author.name, message.content)

        await message.channel.send(reply)

    await bot.process_commands(message)

# =========================================================
# LIVE ENGINE (25 MIN)
# =========================================================

@tasks.loop(minutes=25)
async def live_engine():

    for guild in bot.guilds:

        config = guild_configs.get(str(guild.id))
        if not config:
            continue

        channels = config.get("channels", {})

        # =====================
        # ONLINE
        # =====================

        online_channel = bot.get_channel(channels.get("online"))

        embed = discord.Embed(
            title="🟢 ONLINE PLAYERS",
            description="\n".join(online_players.keys()) or "None",
            color=0x2ECC71
        )

        if online_channel:
            await online_channel.send(embed=embed)

        # =====================
        # LEADERBOARD
        # =====================

        lb_channel = bot.get_channel(channels.get("leaderboard"))

        sorted_players = sorted(
            player_stats.items(),
            key=lambda x: x[1]["kills"],
            reverse=True
        )

        text = "\n".join(
            [f"🏆 {p[0]} - {p[1]['kills']} kills" for p in sorted_players[:10]]
        ) or "No data"

        embed_lb = discord.Embed(
            title="🏆 LEADERBOARD",
            description=text,
            color=0xF1C40F
        )

        if lb_channel:
            await lb_channel.send(embed=embed_lb)

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    load_config()

    try:
        await bot.tree.sync()
    except:
        pass

    if not live_engine.is_running():
        live_engine.start()

    print(f"LOGGED IN AS {bot.user}")

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)