import os
import re
import asyncio
import discord
import json
import requests

from ftplib import FTP_TLS
from datetime import datetime, UTC
from discord.ext import commands, tasks
from supabase import create_client
from openai import AsyncOpenAI

================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

================= CHANNEL IDS =================

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))

================= FTP =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"
LOCAL_LOG_FILE = "live.ADM"

================= SAVE FILE =================

STATE_FILE = "adm_state.json"

================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
command_prefix="!",
intents=intents
)

================= OPENAI =================

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

================= SUPABASE =================

supabase = create_client(
SUPABASE_URL,
SUPABASE_KEY
)

================= GLOBALS =================

processed_lines = set()
MAX_PROCESSED_LINES = 10000

adm_state = {
"file": None,
"last_line": 0,
"last_text": "",
"last_modified": "",
"last_logged_file": ""
}

LAST_CHANGE_TIME = datetime.now(UTC)
LIVE_MODE = False

current_adm = None
current_adm_size = 0

online_players = set()
player_sessions = {}
territory_heat = {}

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

IGNORE_PATTERNS = [
"[CE]",
"LootRespawner",
"PRIDummy",
"causing search overtime",
"Ammo_40mm_Explosive",
"ConstructionHelmet",
"script",
"crash",
"weather",
"storage",
"economy",
"infected"
]

================= STATE SAVE =================

def save_state():

try:

    with open(STATE_FILE, "w") as f:
        json.dump(adm_state, f)

except Exception as e:
    print(f"STATE SAVE ERROR: {e}")

def load_state():

global adm_state

try:

    if os.path.exists(STATE_FILE):

        with open(STATE_FILE, "r") as f:
            adm_state = json.load(f)

        print("STATE LOADED")

except Exception as e:
    print(f"STATE LOAD ERROR: {e}")
================= HELPERS =================

def should_ignore(line):

lower = line.lower()

for pattern in IGNORE_PATTERNS:

    if pattern.lower() in lower:
        return True

return False

def style_embed(embed):

embed.timestamp = datetime.now(UTC)

return embed

def connect_ftp():

ftp = FTP_TLS()

ftp.connect(
    FTP_HOST,
    FTP_PORT,
    timeout=30
)

ftp.login(
    FTP_USER,
    FTP_PASS
)

try:
    ftp.prot_p()

except Exception as e:
    print(f"FTP TLS WARNING: {e}")

ftp.set_pasv(True)

return ftp
