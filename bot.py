import os
import re
import random
import asyncio
import discord

from ftplib import FTP_TLS
from datetime import datetime, UTC
from discord.ext import commands, tasks
from discord import app_commands
from supabase import create_client
from openai import AsyncOpenAI

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ================= CHANNEL IDS =================

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))

KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))

BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
DEPLOY_CHANNEL_ID = int(os.getenv("DEPLOY_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))

# ================= FTP =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"

LOCAL_LOG_FILE = "live.ADM"

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ================= OPENAI =================

client = AsyncOpenAI(
    api_key=OPENAI_API_KEY
)

# ================= SUPABASE =================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ================= GLOBALS =================

processed_lines = set()
MAX_PROCESSED_LINES = 5000

current_adm = None
current_adm_size = 0

online_players = set()

# TRACK LIVE ADM STATE
last_line_count = 0
last_growth_time = datetime.now(UTC)

# TRACK STALE FILES
growth_fail_count = 0

# TRACK DEAD / TERMINATED ADMS
dead_adms = set()

# ================= SWEAR TRACKER =================

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "wanker",
    "bastard",
    "twat"
]

swear_tracker = {}

# ================= ECONOMY =================

SHOP_ITEMS = {
    "water": 10,
    "beans": 20,
    "ammo": 50,
    "medkit": 100,
    "armor": 300,
    "rifle": 600
}

# ================= FILTERS =================

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

# ================= HELPERS =================

def should_ignore(line):

    lower = line.lower()

    for pattern in IGNORE_PATTERNS:

        if pattern.lower() in lower:
            return True

    return False


# ================= HELPERS =================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    return embed


BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"


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

    ftp.prot_p()

    return ftp


# ================= LIVE ADM FINDER =================

def find_active_adm():

    global current_adm
    global current_adm_size
    global last_line_count
    global last_growth_time
    global growth_fail_count
    global dead_adms

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = []

        ftp.retrlines(
            "NLST",
            files.append
        )

        files = sorted(files)

        adm_files = []

        for file in files:

            if not file.endswith(".ADM"):
                continue

            full_path = f"{SEARCH_DIR}/{file}"

            # SKIP DEAD FILES
            if full_path in dead_adms:
                continue

            match = re.search(
                r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})",
                file
            )

            if not match:
                continue

            try:

                dt_str = (
                    match.group(1)
                    + " "
                    + match.group(2).replace("-", ":")
                )

                file_dt = datetime.strptime(
                    dt_str,
                    "%Y-%m-%d %H:%M:%S"
                )

                ftp.voidcmd("TYPE I")

                size = ftp.size(file)

                adm_files.append({
                    "name": file,
                    "datetime": file_dt,
                    "size": size
                })

                print(
                    f"FOUND ADM: {file} | "
                    f"SIZE: {size}"
                )

            except Exception as e:

                print(
                    f"ADM PARSE ERROR: {e}"
                )

        if not adm_files:

            ftp.quit()

            print("NO VALID ADM FILES FOUND")

            return None

        # SORT BY NEWEST FIRST
        adm_files.sort(
            key=lambda x: x["datetime"],
            reverse=True
        )

        best_adm = adm_files[0]

        best_path = (
            f"{SEARCH_DIR}/{best_adm['name']}"
        )

        best_size = best_adm["size"]

        print(
            f"BEST ADM CANDIDATE: "
            f"{best_path} | SIZE: {best_size}"
        )

        # FIRST RUN
        if current_adm is None:

            current_adm = best_path
            current_adm_size = best_size

            growth_fail_count = 0
            last_line_count = 0

            processed_lines.clear()

            last_growth_time = datetime.now(UTC)

            print(
                f"INITIAL ADM: {current_adm}"
            )

            ftp.quit()

            return current_adm

        # FIND CURRENT FILE
        current_file = None

        for adm in adm_files:

            full_path = (
                f"{SEARCH_DIR}/{adm['name']}"
            )

            if full_path == current_adm:

                current_file = adm
                break

        # CHECK CURRENT FILE GROWTH
        if current_file:

            latest_size = current_file["size"]

            if latest_size > current_adm_size:

                print(
                    f"ACTIVE ADM GROWING: "
                    f"{latest_size}"
                )

                current_adm_size = latest_size

                last_growth_time = datetime.now(UTC)

                growth_fail_count = 0

                ftp.quit()

                return current_adm

            else:

                growth_fail_count += 1

                print(
                    f"ADM NOT GROWING | "
                    f"FAIL COUNT: {growth_fail_count}"
                )

                # CHECK FOR TERMINATION TEXT
                try:

                    temp_lines = []

                    ftp.retrlines(
                        f"RETR {os.path.basename(current_adm)}",
                        temp_lines.append
                    )

                    recent_text = "\n".join(
                        temp_lines[-30:]
                    )

                    if (
                        "Termination successfully completed"
                        in recent_text
                    ):

                        print(
                            f"MARKING DEAD ADM: "
                            f"{current_adm}"
                        )

                        dead_adms.add(current_adm)

                        current_adm = None
                        current_adm_size = 0

                        growth_fail_count = 0
                        last_line_count = 0

                        processed_lines.clear()

                        ftp.quit()

                        return find_active_adm()

                except Exception as e:

                    print(
                        f"TERMINATION CHECK ERROR: {e}"
                    )

        # SWITCH TO NEWER FILE ONLY
        if best_path != current_adm and current_file:

            current_dt = current_file["datetime"]

            if best_adm["datetime"] > current_dt:

                print(
                    f"SWITCHING TO NEW ADM: "
                    f"{best_path}"
                )

                current_adm = best_path
                current_adm_size = best_size

                growth_fail_count = 0
                last_line_count = 0

                processed_lines.clear()

                last_growth_time = datetime.now(UTC)

                ftp.quit()

                return current_adm

        # FAILSAFE
        time_since_growth = (
            datetime.now(UTC)
            - last_growth_time
        ).total_seconds()

        if time_since_growth > 14400:

            print(
                "ADM DEAD OVER 4 HOURS "
                "- FORCING RESET"
            )

            current_adm = None
            current_adm_size = 0

            growth_fail_count = 0
            last_line_count = 0

            processed_lines.clear()

        ftp.quit()

        print(f"ACTIVE ADM: {current_adm}")

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return None


# ================= DOWNLOAD ADM =================

def download_adm():

    try:

        active_adm = find_active_adm()

        if not active_adm:
            return False

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        ftp.voidcmd("TYPE I")

        filename = os.path.basename(
            active_adm
        )

        if os.path.exists(LOCAL_LOG_FILE):
            os.remove(LOCAL_LOG_FILE)

        with open(
            LOCAL_LOG_FILE,
            "wb"
        ) as f:

            ftp.retrbinary(
                f"RETR {filename}",
                f.write
            )

        ftp.quit()

        print("ADM DOWNLOADED")

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False


# ================= PLAYER DATA =================

async def ensure_player(discord_id, username):

    result = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    if not result.data:

        supabase.table(
            "player_data"
        ).insert({
            "discord_id": discord_id,
            "username": username,
            "scrap": 1000,
            "bank": 0,
            "kills": 0,
            "deaths": 0,
            "xp": 0,
            "level": 1,
            "bounty": 0,
            "vehicles": 0,
            "faction": "",
            "territory": "",
            "heat": 0,
            "killstreak": 0
        }).execute()


async def get_player(discord_id):

    result = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    if result.data:
        return result.data[0]

    return None


# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    world_events.start()
    adm_loop.start()
    dynamic_economy.start()
    territory_income.start()
    ai_radio.start()

    print(f"✅ Logged in as {bot.user}")


# ================= MESSAGE SWEAR TRACKER =================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    lower = message.content.lower()

    count = 0

    for swear in SWEAR_WORDS:
        count += lower.count(swear)

    if count > 0:

        user_id = str(message.author.id)

        if user_id not in swear_tracker:

            swear_tracker[user_id] = {
                "name": message.author.name,
                "count": 0
            }

        swear_tracker[user_id]["count"] += count

    await bot.process_commands(message)


# ================= ADM PARSER =================

async def parse_adm():

    global processed_lines
    global last_line_count

    if not os.path.exists(LOCAL_LOG_FILE):

        print("LOCAL ADM MISSING")
        return

    try:

        with open(
            LOCAL_LOG_FILE,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            lines = f.readlines()

    except Exception as e:

        print(f"ADM READ ERROR: {e}")
        return

    total_lines = len(lines)

    print(f"ADM TOTAL LINES: {total_lines}")

    # ONLY PROCESS NEW LINES
    new_lines = lines[last_line_count:]

    print(
        f"NEW LINES FOUND: {len(new_lines)}"
    )

    last_line_count = total_lines

    killfeed_channel = bot.get_channel(KILLFEED_CHANNEL_ID)
    raid_channel = bot.get_channel(RAID_CHANNEL_ID)
    build_channel = bot.get_channel(BUILD_CHANNEL_ID)
    deploy_channel = bot.get_channel(DEPLOY_CHANNEL_ID)
    connect_channel = bot.get_channel(CONNECT_CHANNEL_ID)

    for raw_line in new_lines:

        line = raw_line.strip()

        if not line:
            continue

        line_hash = hash(line)

        if line_hash in processed_lines:
            continue

        processed_lines.add(line_hash)

        if len(processed_lines) > MAX_PROCESSED_LINES:
            processed_lines.clear()

        if should_ignore(line):
            continue

        lower = line.lower()

        if (
            "is connecting" in lower
            or "connecting" in lower
        ):

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match and connect_channel:

                player_name = player_match.group(1)

                embed = discord.Embed(
                    description=(
                        f"🛰️ {player_name} connecting\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0x9C8A00
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await connect_channel.send(embed=embed)

        elif (
            "is connected" in lower
            or "connected" in lower
        ):

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match and connect_channel:

                player_name = player_match.group(1)

                online_players.add(player_name)

                embed = discord.Embed(
                    description=(
                        f"☣️ {player_name} connected\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0x4E7F3D
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await connect_channel.send(embed=embed)

        elif (
            "has been disconnected" in lower
            or "disconnected" in lower
        ):

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match and connect_channel:

                player_name = player_match.group(1)

                online_players.discard(player_name)

                embed = discord.Embed(
                    description=(
                        f"❌ {player_name} disconnected\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0x8E2E2E
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await connect_channel.send(embed=embed)

        elif any(x in lower for x in [
            "built",
            "wall_base",
            "watchtower",
            "territory",
            "fence",
            "gate"
        ]):

            if build_channel:

                embed = discord.Embed(
                    description=(
                        f"🔨 Build Event\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0x2ECC71
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await build_channel.send(embed=embed)

        elif any(x in lower for x in [
            "placed",
            "deployed",
            "seachest",
            "barrel"
        ]):

            if deploy_channel:

                embed = discord.Embed(
                    description=(
                        f"📦 Deploy Event\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0xF1C40F
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await deploy_channel.send(embed=embed)

        elif any(x in lower for x in [
            "destroyed",
            "breached",
            "explosive",
            "raid"
        ]):

            if raid_channel:

                embed = discord.Embed(
                    description=(
                        f"💥 Raid Alert\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0xE74C3C
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await raid_channel.send(embed=embed)

        elif (
            "killed by player" in lower
            or "hit by player" in lower
            or "killed" in lower
        ):

            victim_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            killer_match = re.search(
                r'by Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if (
                victim_match
                and killer_match
                and killfeed_channel
            ):

                victim = victim_match.group(1)
                killer = killer_match.group(1)

                reward = random.randint(100, 500)

                embed = discord.Embed(
                    description=(
                        f"☠️ {killer} killed {victim}\n"
                        f"💰 Reward: {reward}\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0xC0392B
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await killfeed_channel.send(embed=embed)


# ================= TASKS =================

@tasks.loop(seconds=60)
async def adm_loop():

    success = await asyncio.to_thread(
        download_adm
    )

    if success:
        await parse_adm()


@tasks.loop(minutes=20)
async def world_events():

    channel = bot.get_channel(EVENT_CHANNEL_ID)

    if not channel:
        return

    events = [
        "🚁 Helicopter crash reported.",
        "☣️ Toxic gas spreading.",
        "📻 Convoy entering Chernarus.",
        "💥 Heavy fighting near NWAF.",
        "🏴 Faction conflict escalating.",
        "📦 Supply crate detected."
    ]

    embed = discord.Embed(
        title="📡 World Event",
        description=random.choice(events),
        color=0x9B59B6
    )

    await channel.send(
        embed=style_embed(embed)
    )


@tasks.loop(minutes=60)
async def dynamic_economy():

    for item in SHOP_ITEMS:

        SHOP_ITEMS[item] += random.randint(-5, 20)

        if SHOP_ITEMS[item] < 5:
            SHOP_ITEMS[item] = 5


@tasks.loop(hours=2)
async def territory_income():

    results = supabase.table(
        "player_data"
    ).select("*").neq(
        "territory",
        ""
    ).execute()

    for player in results.data:

        income = random.randint(100, 300)

        supabase.table(
            "player_data"
        ).update({
            "scrap": player["scrap"] + income
        }).eq(
            "discord_id",
            player["discord_id"]
        ).execute()


@tasks.loop(minutes=25)
async def ai_radio():

    channel = bot.get_channel(EVENT_CHANNEL_ID)

    if not channel:
        return

    chatter = [
        "📻 Gunfire heard near Tisy.",
        "📻 Survivors spotted near Vybor.",
        "📻 Trader convoy requesting escort.",
        "📻 Black market trader active tonight.",
        "📻 Toxic storm approaching."
    ]

    embed = discord.Embed(
        title="📻 Radio Chatter",
        description=random.choice(chatter),
        color=0x3498DB
    )

    await channel.send(
        embed=style_embed(embed)
    )


# ================= COMMANDS =================

@bot.tree.command(
    name="balance",
    description="View stats"
)
async def balance(interaction: discord.Interaction):

    await interaction.response.defer()

    await ensure_player(
        str(interaction.user.id),
        interaction.user.name
    )

    player = await get_player(
        str(interaction.user.id)
    )

    embed = discord.Embed(
        title="💰 Survivor Stats",
        description=(
            f"Pennies: {player['scrap']}\n"
            f"Level: {player['level']}\n"
            f"XP: {player['xp']}\n"
            f"Kills: {player['kills']}\n"
            f"Deaths: {player['deaths']}\n"
            f"Bounty: {player['bounty']}\n"
            f"Vehicles: {player['vehicles']}\n"
            f"Faction: {player['faction']}\n"
            f"Territory: {player['territory']}"
        ),
        color=0xFFD700
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )


@bot.tree.command(
    name="swears",
    description="View your swear count"
)
async def swears(interaction: discord.Interaction):

    user_id = str(interaction.user.id)

    count = swear_tracker.get(
        user_id,
        {}
    ).get(
        "count",
        0
    )

    embed = discord.Embed(
        title="🤬 Swear Counter",
        description=f"You have sworn {count} times.",
        color=0xE74C3C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await interaction.response.send_message(
        embed=embed
    )


@bot.tree.command(
    name="swearlb",
    description="Swear leaderboard"
)
async def swearlb(interaction: discord.Interaction):

    sorted_users = sorted(
        swear_tracker.items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )

    desc = ""

    for i, (_, data) in enumerate(
        sorted_users[:10],
        start=1
    ):

        desc += (
            f"{i}. "
            f"{data['name']} — "
            f"{data['count']} swears\n"
        )

    if not desc:
        desc = "No swears tracked yet."

    embed = discord.Embed(
        title="🏆 Swear Leaderboard",
        description=desc,
        color=0xF39C12
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await interaction.response.send_message(
        embed=embed
    )


# ================= START =================

bot.run(DISCORD_TOKEN)
