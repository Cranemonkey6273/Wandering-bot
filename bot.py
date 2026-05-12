import os
import discord
from discord.ext import commands

from modules.core.guilds import load_guilds, guilds
from modules.commands.setup import setup_command

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.command()
async def setup(ctx):
    await setup_command(ctx)

@bot.event
async def on_ready():
    print(f"Alpha Bot Online: {bot.user}")
    load_guilds()
    print("Guild system loaded")
    print("SYSTEM READY")

bot.run(os.getenv('DISCORD_TOKEN'))