# =========================================================
# WANDERING BOT ALPHA - MULTI GUILD EDITION
# =========================================================

import os
import re
import json
import asyncio
import requests
import tempfile
from ftplib import FTP_TLS
import discord

from datetime import datetime, UTC
from discord.ext import commands, tasks
from discord import app_commands

# =========================================================
# DISCORD
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents
)

# =========================================================
# GLOBAL CONFIG
# =========================================================

BOT_IMAGE = (
    "https://media.discordapp.net/"
    "attachments/1499787777636831324/"
    "1501685742433206342/"
    "7A382429-B666-4A9F-B890-17C0F7981709.png"
)

GUILD_CONFIG_FILE = "guild_configs.json"
GUILD_DATA_FOLDER = "guild_data"
PLAYER_STATS_FILE = "player_stats.json"
HEATMAP_FILE = "heatmap.json"
SWEAR_JAR_FILE = "swear_jar.json"
LINKED_PLAYERS_FILE = "linked_players.json"

# =========================================================
# GLOBALS
# =========================================================

guild_configs = {}
processed_lines = {}
online_players = {}
player_online_times = {}
territory_heat = {}
zone_keywords = {
    "NWAF": ["nwaf", "airfield"],
    "Tisy": ["tisy"],
    "Zelenogorsk": ["zeleno"],
    "Chernogorsk": ["cherno"],
    "Elektrozavodsk": ["electro"],
    "Vybor": ["vybor"],
    "Berezino": ["berezino"],
    "Severograd": ["severo"]
}
player_stats = {}
longshot_records = {}
swear_jar = {}
player_chat_tracker = {}
linked_players = {}
last_funny_message_time = {}
last_funny_index = {}

DEFAULT_ADMIN_ROLES = [
    "Admin",
    "Administrator",
    "Owner"
]

SWEAR_REWARD_MIN = 300
SWEAR_REWARD_MAX = 800
SWEAR_REDEMPTION_MESSAGES_REQUIRED = 15
SWEAR_REDEMPTION_THRESHOLD = 20

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "bollocks",
    "wanker"
]

# =========================================================
# PERMISSION SYSTEM
# =========================================================

def has_staff_permissions(ctx):

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    allowed_roles = config.get(
        "admin_roles",
        DEFAULT_ADMIN_ROLES
    )

    user_roles = [
        role.name for role in ctx.author.roles
    ]

    return any(
        role in allowed_roles
        for role in user_roles
    )

# =========================================================
# HELPERS
# =========================================================

def style_embed(embed):
    embed.timestamp = datetime.now(UTC)
    return embed


def ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


class SlashContextAdapter:
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.guild = interaction.guild
        self.author = interaction.user
        self.channel = interaction.channel
        self.message = type("Msg", (), {"content": f"/{interaction.command.name}"})()

    async def send(self, content=None, embed=None):
        if not self.interaction.response.is_done():
            await self.interaction.response.send_message(content=content, embed=embed, ephemeral=True)
        else:
            await self.interaction.followup.send(content=content, embed=embed, ephemeral=True)


async def run_legacy_as_slash(interaction: discord.Interaction, legacy_name: str, *args, **kwargs):
    ctx = SlashContextAdapter(interaction)
    cmd = bot.get_command(legacy_name)
    if not cmd:
        await ctx.send(f"❌ Command `{legacy_name}` not found.")
        return
    await cmd.callback(ctx, *args, **kwargs)

# =========================================================
# LOADERS
# =========================================================

def load_guild_configs():
    global guild_configs
    guild_configs = load_json(GUILD_CONFIG_FILE)


def save_guild_configs():
    save_json(GUILD_CONFIG_FILE, guild_configs)


def load_player_stats():
    global player_stats
    player_stats = load_json(PLAYER_STATS_FILE)


def save_player_stats():
    save_json(PLAYER_STATS_FILE, player_stats)


def load_heatmap():
    global territory_heat
    territory_heat = load_json(HEATMAP_FILE)


def save_heatmap():
    save_json(HEATMAP_FILE, territory_heat)


def load_swear_jar():
    global swear_jar
    swear_jar = load_json(SWEAR_JAR_FILE)


def save_swear_jar():
    save_json(SWEAR_JAR_FILE, swear_jar)


def load_linked_players():
    global linked_players
    linked_players = load_json(LINKED_PLAYERS_FILE)


def save_linked_players():
    save_json(LINKED_PLAYERS_FILE, linked_players)

# =========================================================
# EVENT CLASSIFIER
# =========================================================

def get_zone_from_line(line):

    lower = line.lower()

    for zone, keywords in zone_keywords.items():

        for keyword in keywords:

            if keyword in lower:
                return zone

    return "Unknown"


def ensure_guild_runtime(guild_id):

    if guild_id not in processed_lines:
        processed_lines[guild_id] = set()

    if guild_id not in online_players:
        online_players[guild_id] = set()

    if guild_id not in player_online_times:
        player_online_times[guild_id] = {}

    if guild_id not in territory_heat:
        territory_heat[guild_id] = {}


def increase_heat(guild_id, zone):

    ensure_guild_runtime(guild_id)

    territory_heat[guild_id][zone] = (
        territory_heat[guild_id].get(zone, 0) + 1
    )

    save_heatmap()


def classify_event(line):

    lower = line.lower()

    if "disconnected" in lower:
        return "disconnect"

    if "connecting" in lower or "connected" in lower:
        return "connect"

    if "killed by infected" in lower or "killed by zombie" in lower:
        return "zombie_kill"

    if "hit by infected" in lower or "attacked by infected" in lower or "hit by zombie" in lower:
        return "zombie_hit"

    if "killed" in lower:
        return "kill"

    if "placed" in lower or "built" in lower:
        return "build"

    if "destroyed" in lower or "dismantled" in lower:
        return "raid"

    return None

# =========================================================
# MULTI GUILD API SEARCH
# =========================================================

def ping_latest_adm_log(config):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")
    nitrado_user = config.get("nitrado_user")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    search_paths = [
        f"/games/{nitrado_user}/noftp/dayzxb/config/",
        f"/games/{nitrado_user}/noftp/dayzxb/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/",
        f"/games/{nitrado_user}/noftp/dayzxb/storage_1/",
        f"/games/{nitrado_user}/noftp/dayzxb/profiles/",
        f"/games/{nitrado_user}/noftp/dayzxb/logs/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/dayzOffline.chernarusplus/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/dayzOffline.enoch/",
        f"/games/{nitrado_user}/noftp/"
    ]

    for search_path in search_paths:

        try:

            url = (
                f"https://api.nitrado.net/services/"
                f"{service_id}/gameservers/file_server/list"
            )

            params = {
                "dir": search_path,
                "search": "*DayZServer*"
            }

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=20
            )

            print("[PING STATUS]", response.status_code)

            if response.status_code != 200:
                continue

            data = response.json()

            entries = (
                data
                .get("data", {})
                .get("entries", [])
            )

            print(f"[SEARCH PATH] {search_path}")

            for entry in entries:
                print(f"FOUND FILE: {entry.get('name')}")

            matching_logs = [
                entry for entry in entries
                if re.match(
                    r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
                    entry.get("name", ""),
                    re.IGNORECASE
                )
            ]

            if not matching_logs:
                print("NO MATCHING ADM FILES")
                continue

            matching_logs.sort(
                key=lambda x: x.get("modified_at", ""),
                reverse=True
            )

            latest = matching_logs[0]

            print("LATEST ADM FOUND:", latest.get("path"))

            return latest

        except Exception as error:
            print(error)

    return None

# =========================================================
# LIVE DASHBOARD SETTINGS
# =========================================================

ONLINE_UPDATE_MINUTES = 30
LEADERBOARD_UPDATE_MINUTES = 30
HEATMAP_UPDATE_MINUTES = 30

last_online_message_ids = {}
last_leaderboard_message_ids = {}
last_heatmap_message_ids = {}

# =========================================================
# CLICKABLE MAP LINKS
# =========================================================

def build_izurvive_link(coords):

    try:

        split_coords = coords.split(",")

        x = split_coords[0].strip()
        y = split_coords[1].strip()

        return f"https://dayz.ginfo.gg/#location={x};{y}"

    except:
        return None


ZONE_POINTS = {
    "NWAF": (330, 120), "Tisy": (220, 70), "Zelenogorsk": (170, 220),
    "Chernogorsk": (120, 290), "Elektrozavodsk": (360, 300), "Vybor": (210, 140),
    "Berezino": (430, 150), "Severograd": (360, 95)
}


def generate_guild_heatmap_image(guild_id: str):
    import math
    import struct
    import zlib

    width = 512
    height = 384
    pixels = [
        [(18, 18, 25, 255) for _ in range(width)]
        for _ in range(height)
    ]

    def blend_pixel(px, py, color):
        if px < 0 or px >= width or py < 0 or py >= height:
            return

        sr, sg, sb, sa = color
        dr, dg, db, da = pixels[py][px]
        alpha = sa / 255
        inv_alpha = 1 - alpha

        pixels[py][px] = (
            int(sr * alpha + dr * inv_alpha),
            int(sg * alpha + dg * inv_alpha),
            int(sb * alpha + db * inv_alpha),
            da,
        )

    def draw_heat_circle(cx, cy, radius, color):
        radius_sq = radius * radius

        for py in range(cy - radius, cy + radius + 1):
            for px in range(cx - radius, cx + radius + 1):
                dx = px - cx
                dy = py - cy
                dist_sq = dx * dx + dy * dy

                if dist_sq > radius_sq:
                    continue

                distance = math.sqrt(dist_sq)
                fade = max(0.0, 1.0 - (distance / radius))
                alpha = int(color[3] * fade)
                blend_pixel(px, py, (color[0], color[1], color[2], alpha))

    def draw_cross(cx, cy):
        for offset in range(-5, 6):
            blend_pixel(cx + offset, cy, (255, 255, 255, 230))
            blend_pixel(cx, cy + offset, (255, 255, 255, 230))

    def png_chunk(chunk_type, data):
        chunk = chunk_type + data
        return (
            struct.pack(">I", len(data))
            + chunk
            + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        )

    zone_counts = territory_heat.get(guild_id, {})
    max_count = max(zone_counts.values()) if zone_counts else 1

    for zone, count in zone_counts.items():
        if zone not in ZONE_POINTS:
            continue

        x, y = ZONE_POINTS[zone]
        intensity = max(0.2, min(1.0, count / max_count))

        draw_heat_circle(x, y, 70, (255, 45, 0, int(45 * intensity)))
        draw_heat_circle(x, y, 48, (255, 80, 0, int(90 * intensity)))
        draw_heat_circle(x, y, 25, (255, 180, 0, int(170 * intensity)))
        draw_cross(x, y)

    raw = bytearray()

    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend([r, g, b, a])

    png_data = b"".join([
        b"\x89PNG\r\n\x1a\n",
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
        png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
        png_chunk(b"IEND", b""),
    ])

    fd, path = tempfile.mkstemp(prefix=f"heat_{guild_id}_", suffix=".png")
    os.close(fd)

    with open(path, "wb") as f:
        f.write(png_data)

    return path
# =========================================================
# AUTO GUILD SETUP
# =========================================================

@bot.event
async def on_guild_join(guild):

    guild_id = str(guild.id)

    if guild_id in guild_configs:
        return

    category = await guild.create_category("📡┃WANDERING BOT┃📡")
    staff_category = await guild.create_category("🛡️┃STAFF OPS┃🛡️")
    economy_category = await guild.create_category("💰┃ECONOMY┃💰")

    async def make_channel(name, *, cat=None):

        return await guild.create_text_channel(
            name,
            category=cat or category
        )

    killfeed = await make_channel("🔥・killfeed")
    raids = await make_channel("🏴・raids")
    builds = await make_channel("🔨・building")
    connections = await make_channel("🟢・connect")
    disconnects = await make_channel("🔴・disconnect")
    online = await make_channel("✅🎮・online🎮✅")
    leaderboards = await make_channel("🏆・leaderboards")
    heatmap_channel = await make_channel("🔥・heatmap🔥")
    longshot_channel = await make_channel("🎯・longshots")
    restart_alerts = await make_channel("📢・restart-alerts")
    welcome_channel = await make_channel("👋・welcome")
    general_chat = await make_channel("💬・survivor-chat")
    factions_chat = await make_channel("🏴・factions")
    faction_list = await make_channel("📜・faction-list")
    help_channel = await make_channel("❓・help-desk")
    clips_channel = await make_channel("🎬・dayz-clips")
    economy_channel = await make_channel("💰・black-market")
    ai_channel = await make_channel("🧠・survivor-ai")
    admin_logs = await make_channel("🛡️・admin-logs・🛡️", cat=staff_category)
    command_logs = await make_channel("📜・command-logs・📜", cat=staff_category)
    purchase_logs = await make_channel("💳・purchase-logs・💳", cat=staff_category)
    vehicle_rentals = await make_channel("🚗・vehicle-rentals・🚗", cat=economy_category)
    rental_logs = await make_channel("🛻・rental-logs・🛻", cat=economy_category)
    faction_tickets = await make_channel("🎫・faction-tickets")
    faction_staff = await make_channel("🛡️・faction-staff")
    zombie_feed = await make_channel("🧟・zombie-feed")
    owner_overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.owner: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    company_announcements = await guild.create_text_channel(
        "📢・wandering-company-announcements・📢",
        category=staff_category,
        overwrites=owner_overwrites
    )

    guild_configs[guild_id] = {
        "guild_name": guild.name,
        "guild_owner": str(guild.owner),
        "admin_roles": DEFAULT_ADMIN_ROLES.copy(),
        "nitrado_token": "",
        "service_id": "",
        "nitrado_user": "",
        "ftp_user": "",
        "ftp_password": "",
        "channels": {
            "killfeed": killfeed.id,
            "raids": raids.id,
            "building": builds.id,
            "connections": connections.id,
            "disconnects": disconnects.id,
            "online": online.id,
            "leaderboards": leaderboards.id,
            "heatmap": heatmap_channel.id,
            "longshots": longshot_channel.id,
            "restart_alerts": restart_alerts.id,
            "welcome": welcome_channel.id,
            "general_chat": general_chat.id,
            "factions_chat": factions_chat.id,
            "faction_list": faction_list.id,
            "help_channel": help_channel.id,
            "clips_channel": clips_channel.id,
            "economy": economy_channel.id,
            "ai_chat": ai_channel.id,
            "admin_logs": admin_logs.id,
            "command_logs": command_logs.id,
            "purchase_logs": purchase_logs.id,
            "vehicle_rentals": vehicle_rentals.id,
            "rental_logs": rental_logs.id,
            "faction_tickets": faction_tickets.id,
            "faction_staff": faction_staff.id,
            "zombie_feed": zombie_feed.id
            ,
            "company_announcements": company_announcements.id
        }
    }

    try:
        await send_owner_notification(
            "➕ Bot Added to New Server",
            f"Server: **{guild.name}** (`{guild.id}`)\nOwner: **{guild.owner}**"
        )
    except Exception:
        pass

    save_guild_configs()

# =========================================================
# /SETUP COMMAND
# =========================================================

@bot.tree.command(
    name="setup",
    description="Connect your Nitrado server"
)
@app_commands.describe(
    nitrado_token="Your Nitrado API token",
    service_id="Your Nitrado service ID",
    nitrado_user="Example: ni12248929_2",
    ftp_user="Your Nitrado FTP username",
    ftp_password="Your Nitrado FTP password"
)
async def setup_command(
    interaction: discord.Interaction,
    nitrado_token: str,
    service_id: str,
    nitrado_user: str,
    ftp_user: str,
    ftp_password: str
):

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)

    if guild_id not in guild_configs:

        guild_configs[guild_id] = {
            "guild_name": interaction.guild.name,
            "admin_roles": DEFAULT_ADMIN_ROLES.copy(),
            "channels": {}
        }

    category = discord.utils.get(
        interaction.guild.categories,
        name="📡 WANDERING BOT"
    )

    if not category:
        category = await interaction.guild.create_category(
            "📡 WANDERING BOT"
        )

    async def ensure_channel(key, name):

        existing_id = guild_configs[guild_id]["channels"].get(key)

        if existing_id:
            existing_channel = interaction.guild.get_channel(existing_id)

            if existing_channel:
                return existing_channel

        channel = discord.utils.get(
            interaction.guild.text_channels,
            name=name
        )

        if not channel:
            channel = await interaction.guild.create_text_channel(
                name,
                category=category
            )

        guild_configs[guild_id]["channels"][key] = channel.id

        return channel

    await ensure_channel("killfeed", "🔥・killfeed")
    await ensure_channel("raids", "🏴・raids")
    await ensure_channel("building", "🔨・building")
    await ensure_channel("connections", "🟢・connect")
    await ensure_channel("disconnects", "🔴・disconnect")
    await ensure_channel("online", "✅🎮・online🎮✅")
    await ensure_channel("leaderboards", "🏆・leaderboards")
    await ensure_channel("heatmap", "🔥・heatmap🔥")
    await ensure_channel("longshots", "🎯・longshots")
    await ensure_channel("restart_alerts", "📢・restart-alerts")
    await ensure_channel("welcome", "👋・welcome")
    await ensure_channel("general_chat", "💬・survivor-chat")
    await ensure_channel("factions_chat", "🏴・factions")
    await ensure_channel("faction_list", "📜・faction-list")
    await ensure_channel("help_channel", "❓・help-desk")
    await ensure_channel("clips_channel", "🎬・dayz-clips")
    await ensure_channel("economy", "💰・black-market")
    await ensure_channel("ai_chat", "🧠・survivor-ai")
    await ensure_channel("admin_logs", "🛡️・admin-logs")
    await ensure_channel("command_logs", "📜・command-logs")
    await ensure_channel("purchase_logs", "💳・purchase-logs")
    await ensure_channel("vehicle_rentals", "🚗・vehicle-rentals")
    await ensure_channel("rental_logs", "🛻・rental-logs")
    await ensure_channel("faction_tickets", "🎫・faction-tickets")
    await ensure_channel("faction_staff", "🛡️・faction-staff")
    await ensure_channel("zombie_feed", "🧟・zombie-feed")

    guild_configs[guild_id]["nitrado_token"] = nitrado_token
    guild_configs[guild_id]["service_id"] = service_id
    guild_configs[guild_id]["nitrado_user"] = nitrado_user.strip()
    guild_configs[guild_id]["ftp_user"] = ftp_user
    guild_configs[guild_id]["ftp_password"] = ftp_password

    save_guild_configs()

    help_channel = bot.get_channel(
        guild_configs[guild_id]["channels"].get("help_channel")
    )

    if help_channel:

        setup_embed = discord.Embed(
            title="🤖 WANDERING BOT SETUP & COMMAND GUIDE",
            description=(
                "Welcome to Wandering Bot Alpha.\n\n"
                "Below are the most important commands and systems available on your server."
            ),
            color=0x3498DB
        )

        setup_embed.add_field(
            name="📡 Core Server Commands",
            value=(
                "`!online` — Show live online survivors\n"
                "`!serverstatus` — Bot/server status\n"
                "`!heatmap` — PvP heatmap\n"
                "`!topkills` — Kill leaderboard\n"
                "`!toplongshots` — Longshot leaderboard"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="💰 Economy Commands",
            value=(
                "`!wallet` — Check pennies\n"
                "`!shop` — Open black market\n"
                "`!buy item x y` — Buy restart delivery\n"
                "`!rentvehicle vehicle hours x y` — Rent vehicles"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="🛡️ Staff Commands",
            value=(
                "`!restartserver` — Restart DayZ server\n"
                "`!togglebasedamage on/off`\n"
                "`!purge amount`\n"
                "`!setradarchannel #channel`\n"
                "`!radarping x y reason`"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="🏴 Factions & Tickets",
            value=(
                "`!factionticket Name` — Create faction request\n"
                "`!factionapprove ID` — Approve faction ticket"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="🎮 Identity Commands",
            value=(
                "`!linkgamer Gamertag` — Link Xbox gamertag\n"
                "`!mylink` — View linked account"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="🧠 Automated Features",
            value=(
                "• Live killfeed\n"
                "• Raid detection\n"
                "• Heatmaps\n"
                "• AI chatter\n"
                "• Restart scheduling\n"
                "• Delivery spawning\n"
                "• Radar intelligence\n"
                "• Welcome messages\n"
                "• Swear jar economy"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="⚙️ Final Setup Step",
            value=(
                "Add the provided `SpawnWanderingDeliveries();` code into your DayZ `init.c` file to enable restart item spawning."
            ),
            inline=False
        )

        setup_embed.set_thumbnail(url=BOT_IMAGE)

        setup_embed.set_footer(
            text="Wandering Bot Alpha • Automated Help System"
        )

        await help_channel.send(embed=style_embed(setup_embed))

    await interaction.followup.send(
        "✅ Wandering Bot fully connected and operational.",
        ephemeral=True
    )

# =========================================================
# NITRADO XML DELIVERY BRIDGE
# =========================================================

def upload_delivery_xml_to_nitrado(config, xml_path):

    try:

        ftp_host = "ftp.nitrado.net"
        ftp_user = config.get("ftp_user")
        ftp_pass = config.get("ftp_password")

        if not ftp_user or not ftp_pass:

            print("FTP DETAILS NOT CONFIGURED")
            return False

        ftp = FTP_TLS(ftp_host)

        ftp.login(ftp_user, ftp_pass)
        ftp.prot_p()

        target_path = (
            "/dayzxb/custom/deliveries.xml"
        )

        with open(xml_path, "rb") as xml_file:

            ftp.storbinary(
                f"STOR {target_path}",
                xml_file
            )

        ftp.quit()

        print("DELIVERY XML UPLOADED TO NITRADO")

        return True

    except Exception as error:

        print(error)
        return False

# =========================================================
# DOWNLOAD ADM
# =========================================================

def download_latest_adm(
    guild_id,
    config,
    latest_log
):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    try:

        download_url = (
            f"https://api.nitrado.net/services/"
            f"{service_id}/gameservers/file_server/download"
        )

        headers = {
            "Authorization": f"Bearer {token}"
        }

        params = {
            "file": latest_log.get("path")
        }

        response = requests.get(
            download_url,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return False

        data = response.json()

        token_url = (
            data
            .get("data", {})
            .get("token", {})
            .get("url")
        )

        if not token_url:
            return False

        file_response = requests.get(token_url)

        adm_path = os.path.join(
            GUILD_DATA_FOLDER,
            f"{guild_id}.ADM"
        )

        with open(adm_path, "wb") as f:
            f.write(file_response.content)

        return True

    except Exception as error:

        print(error)

        return False

# =========================================================
# FEED EMBED STYLES
# =========================================================

def create_feed_embed(title, color, player=None, details=None, weapon=None, coords=None):

    embed = discord.Embed(
        title=title,
        color=color
    )

    if player:
        embed.add_field(
            name="👤 Player",
            value=player,
            inline=True
        )

    if weapon:
        embed.add_field(
            name="🔫 Weapon",
            value=weapon,
            inline=True
        )

    if coords:
        map_link = build_izurvive_link(coords)

        if map_link:
            coords_value = f"[🗺️ {coords}](<{map_link}>)"
        else:
            coords_value = coords

        embed.add_field(
            name="📍 Coordinates",
            value=coords_value,
            inline=False
        )

    if details:
        embed.add_field(
            name="📜 Event Details",
            value=f"```{details[:900]}```",
            inline=False
        )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Live DayZ Intelligence"
    )

    return style_embed(embed)

# =========================================================
# ADM PARSER
# =========================================================

async def parse_adm(guild_id, config):

    adm_path = os.path.join(
        GUILD_DATA_FOLDER,
        f"{guild_id}.ADM"
    )

    if not os.path.exists(adm_path):
        return

    with open(
        adm_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

    channels = config.get("channels", {})

    killfeed_channel = bot.get_channel(
        channels.get("killfeed")
    )

    raid_channel = bot.get_channel(
        channels.get("raids")
    )

    build_channel = bot.get_channel(
        channels.get("building")
    )

    connect_channel = bot.get_channel(
        channels.get("connections")
    )

    disconnect_channel = bot.get_channel(
        channels.get("disconnects")
    )

    for raw_line in lines[-250:]:

        line = raw_line.strip()

        if not line:
            continue

        line_hash = hash(line)

        ensure_guild_runtime(guild_id)

        if line_hash in processed_lines[guild_id]:
            continue

        processed_lines[guild_id].add(line_hash)

        event_type = classify_event(line)

        if not event_type:
            continue

        print(f"EVENT: {event_type} | {line}")

        ensure_guild_runtime(guild_id)

        zone = get_zone_from_line(line)

        if zone != "Unknown":
            increase_heat(guild_id, zone)

        # ================= CONNECT =================

        if event_type == "connect" and connect_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            online_players[guild_id].add(player_name)
            player_online_times[guild_id][player_name] = datetime.now(UTC)

            embed = discord.Embed(
                title="🟢 SURVIVOR CONNECTED",
                color=0x2ECC71
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=False
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Connection Feed"
            )

            embed.timestamp = datetime.now(UTC)

            await connect_channel.send(embed=embed)

            # Welcome channel messaging for in-game connects removed.
            # Welcome messages are only for Discord member joins.

        # ================= DISCONNECT =================

        elif event_type == "disconnect" and disconnect_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            if player_name in online_players[guild_id]:
                online_players[guild_id].remove(player_name)

            if player_name in player_online_times[guild_id]:
                del player_online_times[guild_id][player_name]

            embed = discord.Embed(
                title="🔴 SURVIVOR DISCONNECTED",
                color=0xE74C3C
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=False
            )

            if coords:

                map_link = build_izurvive_link(coords)

                if map_link:

                    embed.add_field(
                        name="📍 Last Known Location",
                        value=f"[🔵 Open Map](<{map_link}>)",
                        inline=False
                    )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Disconnect Feed"
            )

            embed.timestamp = datetime.now(UTC)

            disconnect_channel = bot.get_channel(
                channels.get("disconnects")
            )

            if disconnect_channel:
                await disconnect_channel.send(embed=embed)

        # ================= BUILD =================

        elif event_type == "build" and build_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else "Unknown"
            )

            action = "Building"
            object_name = "Structure"
            tool_used = "Tool"

            if "placed" in line.lower():

                action_match = re.search(
                    r'placed ([^<]+)',
                    line,
                    re.IGNORECASE
                )

                if action_match:
                    object_name = action_match.group(1).strip()

                action = "Placed"

            elif "built" in line.lower():

                build_match = re.search(
                    r'Built ([^ ]+)',
                    line,
                    re.IGNORECASE
                )

                if build_match:
                    object_name = build_match.group(1).replace("_", " ").title()

                tool_match = re.search(
                    r'with ([^ ]+)',
                    line,
                    re.IGNORECASE
                )

                if tool_match:
                    tool_used = tool_match.group(1)

                action = "Built"

            embed = discord.Embed(
                title="🏗️ BUILDING ACTIVITY",
                color=0xF1C40F
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=True
            )

            embed.add_field(
                name="🛠️ Action",
                value=action,
                inline=True
            )

            embed.add_field(
                name="🏗️ Structure",
                value=object_name,
                inline=False
            )

            if tool_used != "Tool":

                embed.add_field(
                    name="🔨 Tool",
                    value=tool_used,
                    inline=True
                )

            map_link = build_izurvive_link(coords)

            if map_link:

                embed.add_field(
                    name="📍 Location",
                    value=f"[🔵 Open Map](<{map_link}>)",
                    inline=False
                )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Building Intelligence"
            )

            embed.timestamp = datetime.now(UTC)

            await build_channel.send(embed=embed)

        # ================= RAID =================

        elif event_type == "raid" and raid_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            action = "Raid Activity"
            structure = "Base Structure"
            tool_used = "Unknown"

            dismantle_match = re.search(
                r'Dismantled ([^ ]+(?: [^ ]+)*) from ([^ ]+)',
                line,
                re.IGNORECASE
            )

            if dismantle_match:
                action = dismantle_match.group(1)
                structure = dismantle_match.group(2)

            tool_match = re.search(
                r'with ([^ ]+)',
                line,
                re.IGNORECASE
            )

            if tool_match:
                tool_used = tool_match.group(1)

            embed = discord.Embed(
                title="🚨 RAID DETECTED",
                color=0xFF0000
            )

            embed.add_field(
                name="👤 Raider",
                value=player_name,
                inline=True
            )

            embed.add_field(
                name="🧨 Action",
                value=action,
                inline=True
            )

            embed.add_field(
                name="🏚️ Structure",
                value=structure,
                inline=False
            )

            embed.add_field(
                name="🔨 Tool",
                value=tool_used,
                inline=True
            )

            if coords:

                map_link = build_izurvive_link(coords)

                if map_link:

                    embed.add_field(
                        name="📍 Raid Location",
                        value=f"[🔵 Open Map](<{map_link}>)",
                        inline=False
                    )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Raid Intelligence"
            )

            embed.timestamp = datetime.now(UTC)

            await raid_channel.send(embed=embed)

                # ================= ZOMBIES =================

        elif event_type == "zombie_hit":

            zombie_channel = bot.get_channel(
                channels.get("zombie_feed")
            )

            if zombie_channel:

                player_match = re.search(
                    r'Player "([^"]+)"',
                    line
                )

                player_name = (
                    player_match.group(1)
                    if player_match else "Unknown"
                )

                embed = discord.Embed(
                    title="🧟 INFECTED ATTACK",
                    description=f"**{player_name}** was attacked by infected.",
                    color=0x2ECC71
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot • Zombie Activity"
                )

                embed.timestamp = datetime.now(UTC)

                await zombie_channel.send(
                    embed=style_embed(embed)
                )

        elif event_type == "zombie_kill":

            zombie_channel = bot.get_channel(
                channels.get("zombie_feed")
            )

            if zombie_channel:

                player_match = re.search(
                    r'Player "([^"]+)"',
                    line
                )

                player_name = (
                    player_match.group(1)
                    if player_match else "Unknown"
                )

                embed = discord.Embed(
                    title="☠️ KILLED BY INFECTED",
                    description=f"**{player_name}** was overwhelmed by zombies.",
                    color=0xE74C3C
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot • Zombie Fatality"
                )

                embed.timestamp = datetime.now(UTC)

                await zombie_channel.send(
                    embed=style_embed(embed)
                )

        # ================= KILLFEED =================

        elif event_type == "kill" and killfeed_channel:

            killer_match = re.search(
                r'Player "([^"]+)" killed Player "([^"]+)" with ([^ ]+)',
                line
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            if killer_match:

                killer = killer_match.group(1)
                victim = killer_match.group(2)
                weapon = killer_match.group(3)

                distance_match = re.search(
                    r'from ([0-9]+\.?[0-9]*)m',
                    line,
                    re.IGNORECASE
                )

                distance = (
                    float(distance_match.group(1))
                    if distance_match else 0
                )

                embed = discord.Embed(
                    title="☠️ PLAYER KILL",
                    color=0x992D22
                )

                embed.add_field(
                    name="🔫 Killer",
                    value=killer,
                    inline=True
                )

                embed.add_field(
                    name="💀 Victim",
                    value=victim,
                    inline=True
                )

                if distance > 0:

                    embed.add_field(
                        name="🎯 Distance",
                        value=f"{distance}m",
                        inline=True
                    )

                embed.add_field(
                    name="🪖 Weapon",
                    value=weapon,
                    inline=False
                )

                if coords:

                    map_link = build_izurvive_link(coords)

                    if map_link:

                        embed.add_field(
                            name="📍 Kill Location",
                            value=f"[🔵 Open Map](<{map_link}>)",
                            inline=False
                        )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Alpha • PvP Intelligence"
                )

                embed.timestamp = datetime.now(UTC)

                await killfeed_channel.send(
                    embed=embed
                )

                guild_longshot = longshot_records.get(guild_id, {
                    "killer": "None",
                    "distance": 0,
                    "weapon": "Unknown"
                })

                if distance > guild_longshot.get("distance", 0):

                    longshot_records[guild_id] = {
                        "killer": killer,
                        "victim": victim,
                        "distance": distance,
                        "weapon": weapon
                    }

                    longshot_channel = bot.get_channel(
                        channels.get("longshots")
                    )

                    if longshot_channel:

                        longshot_embed = discord.Embed(
                            title="🎯 NEW SERVER LONGSHOT RECORD",
                            description=(
                                f"{killer} just set a new longshot record!"
                            ),
                            color=0xF1C40F
                        )

                        longshot_embed.add_field(
                            name="🎯 Distance",
                            value=f"{distance}m",
                            inline=True
                        )

                        longshot_embed.add_field(
                            name="🔫 Weapon",
                            value=weapon,
                            inline=True
                        )

                        longshot_embed.add_field(
                            name="💀 Victim",
                            value=victim,
                            inline=True
                        )

                        if coords:

                            map_link = build_izurvive_link(coords)

                            if map_link:

                                longshot_embed.add_field(
                                    name="📍 Kill Location",
                                    value=f"[🔵 Open Map](<{map_link}>)",
                                    inline=False
                                )

                        longshot_embed.set_thumbnail(url=BOT_IMAGE)

                        longshot_embed.set_footer(
                            text="Wandering Bot Alpha • Longshot Tracking"
                        )

                        longshot_embed.timestamp = datetime.now(UTC)

                        await longshot_channel.send(
                            embed=style_embed(longshot_embed)
                        )

# =========================================================
# ADM LOOP
# =========================================================

@tasks.loop(minutes=3)
async def adm_loop():

    for guild_id, config in list(guild_configs.items()):

        try:

            latest_log = await asyncio.to_thread(
                ping_latest_adm_log,
                config
            )

            if not latest_log:
                continue

            success = await asyncio.to_thread(
                download_latest_adm,
                guild_id,
                config,
                latest_log
            )

            if not success:
                continue

            await parse_adm(
                guild_id,
                config
            )

            print(f"NEW ADM FOR {guild_id}")

        except Exception as error:

            print(error)

# =========================================================
# SWEAR JAR
# =========================================================

@bot.event
async def on_member_join(member):

    guild_id = str(member.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    welcome_channel = bot.get_channel(
        channels.get("welcome")
    )

    if not welcome_channel:
        return

    import random

    welcome_text = random.choice(WELCOME_MESSAGES)

    embed = discord.Embed(
        title="👋 NEW SURVIVOR ARRIVED",
        description=(
            f"{member.mention}\n\n{welcome_text}\n\n"
            "🔗 Please link your gamertag with `/linkgamer` in the required channel.\n"
            "Example: `/linkgamer gamertag: YourXboxName`"
        ),
        color=0x1ABC9C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Welcome System"
    )

    await welcome_channel.send(embed=style_embed(embed))


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    lower = message.content.lower()

    found_words = [
        word for word in SWEAR_WORDS
        if word in lower
    ]

    if found_words:

        user_id = str(message.author.id)

        if user_id not in swear_jar:

            swear_jar[user_id] = {
                "name": str(message.author),
                "count": 0,
                "balance": 0
            }

        swear_jar[user_id]["count"] += len(found_words)

        swear_jar[user_id]["balance"] += (
            len(found_words) * 100
        )

        pennies_total = swear_jar[user_id]["balance"]

        save_swear_jar()

        embed = discord.Embed(
            title="💸 SWEAR JAR",
            description=(
                f"{message.author.mention} "
                f"was fined {len(found_words) * 100} pennies 🪙"
            ),
            color=0xE67E22
        )

        embed.add_field(
            name="Total Swears",
            value=str(
                swear_jar[user_id]["count"]
            ),
            inline=True
        )

        embed.add_field(
            name="Debt",
            value=f"{pennies_total} pennies 🪙",
            inline=True
        )

        await message.channel.send(
            embed=style_embed(embed)
        )

    for keyword, response in AI_RESPONSES.items():

        if keyword in lower:

            await message.channel.send(response)

            break

    user_id = str(message.author.id)
    now_ts = datetime.now(UTC).timestamp()

    if user_id not in player_chat_tracker:

        player_chat_tracker[user_id] = {
            "recent_messages": 0,
            "recent_swears": 0,
            "clean_messages": 0,
            "eligible": False
        }

    # low-frequency fun chatter with anti-repeat + anti-spam guards
    if now_ts - last_funny_message_time.get(user_id, 0) > 900:
        import random
        if random.random() < 0.04:
            idx = random.randrange(len(FUNNY_ROTATION))
            if idx == last_funny_index.get(user_id, -1):
                idx = (idx + 1) % len(FUNNY_ROTATION)
            last_funny_index[user_id] = idx
            last_funny_message_time[user_id] = now_ts
            await message.channel.send(FUNNY_ROTATION[idx])

    tracker = player_chat_tracker[user_id]

    tracker["recent_messages"] += 1

    if found_words:

        tracker["recent_swears"] += len(found_words)
        tracker["clean_messages"] = 0

        if tracker["recent_swears"] >= SWEAR_REDEMPTION_THRESHOLD:
            tracker["eligible"] = True

    else:

        tracker["clean_messages"] += 1

        if (
            tracker["eligible"]
            and tracker["clean_messages"] >= SWEAR_REDEMPTION_MESSAGES_REQUIRED
        ):

            import random

            reward = random.randint(
                SWEAR_REWARD_MIN,
                SWEAR_REWARD_MAX
            )

            if user_id not in wallets:

                wallets[user_id] = {
                    "name": str(message.author),
                    "balance": 0,
                    "daily_transactions": 0
                }

            wallets[user_id]["balance"] += reward

            tracker["eligible"] = False
            tracker["recent_swears"] = 0
            tracker["clean_messages"] = 0
            tracker["recent_messages"] = 0

            save_wallets()

            redemption_messages = [
                f"🧼 {message.author.mention} finally cleaned up their language. Miracles do happen. +{reward} pennies 🪙",
                f"💰 Good behaviour detected from {message.author.mention}. Survivor rehabilitation successful. +{reward} pennies 🪙",
                f"🧠 AI Notice: {message.author.mention} survived {SWEAR_REDEMPTION_MESSAGES_REQUIRED} messages without swearing. Reward issued. +{reward} pennies 🪙",
                f"📻 Chernarus Radio: {message.author.mention} has temporarily stopped speaking like a lunatic. +{reward} pennies 🪙",
                f"🏆 Redemption Arc Complete: {message.author.mention} earned {reward} pennies for not swearing constantly."
            ]

            redemption_embed = discord.Embed(
                title="✨ SWEAR JAR REDEMPTION",
                description=random.choice(redemption_messages),
                color=0x2ECC71
            )

            redemption_embed.set_thumbnail(url=BOT_IMAGE)

            redemption_embed.set_footer(
                text="Wandering Bot Alpha • Behaviour System"
            )

            await message.channel.send(
                embed=style_embed(redemption_embed)
            )

    # Prefix commands disabled; slash commands only mode.

# =========================================================
# OWNER MONITORING SYSTEM
# =========================================================

BOT_OWNER_GUILD_ID = os.getenv("BOT_OWNER_GUILD_ID")
BOT_OWNER_CHANNEL_ID = os.getenv("BOT_OWNER_CHANNEL_ID")


async def send_owner_notification(title, description):

    try:

        if not BOT_OWNER_CHANNEL_ID:
            return

        owner_channel = bot.get_channel(
            int(BOT_OWNER_CHANNEL_ID)
        )

        if not owner_channel:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x9B59B6
        )

        embed.set_thumbnail(url=BOT_IMAGE)

        embed.set_footer(
            text="Wandering Bot Alpha • Owner Monitoring"
        )

        await owner_channel.send(
            embed=style_embed(embed)
        )

    except Exception as error:
        print(error)


@bot.listen("on_command")
async def log_command_usage(ctx):

    try:

        guild_id = str(ctx.guild.id)

        config = guild_configs.get(guild_id, {})

        channels = config.get("channels", {})

        command_log_channel = bot.get_channel(
            channels.get("command_logs")
        )

        if command_log_channel:

            embed = discord.Embed(
                title="📜 COMMAND USED",
                color=0x3498DB
            )

            embed.add_field(
                name="👤 User",
                value=str(ctx.author),
                inline=False
            )

            embed.add_field(
                name="💬 Command",
                value=ctx.message.content,
                inline=False
            )

            await command_log_channel.send(
                embed=style_embed(embed)
            )

    except Exception as error:
        print(error)


@bot.event
async def on_command_error(ctx, error):

    try:

        guild_id = str(ctx.guild.id)

        config = guild_configs.get(guild_id, {})

        channels = config.get("channels", {})

        admin_log_channel = bot.get_channel(
            channels.get("admin_logs")
        )

        if admin_log_channel:

            embed = discord.Embed(
                title="⚠️ FAILED COMMAND",
                color=0xE74C3C
            )

            embed.add_field(
                name="👤 User",
                value=str(ctx.author),
                inline=False
            )

            embed.add_field(
                name="💬 Attempted Command",
                value=ctx.message.content,
                inline=False
            )

            embed.add_field(
                name="🧠 Error",
                value=str(error)[:1000],
                inline=False
            )

            await admin_log_channel.send(
                embed=style_embed(embed)
            )

    except Exception as inner_error:
        print(inner_error)

# =========================================================
# COMMANDS
# =========================================================

@bot.command()
async def helpme(ctx):

    embed = discord.Embed(
        title="🤖 WANDERING BOT ALPHA COMMANDS",
        color=0x3498DB
    )

    embed.add_field(
        name="📡 Server",
        value=(
            "!serverstatus\n"
            "!online\n"
            "!playerstats <name>"
        ),
        inline=False
    )

    embed.add_field(
        name="🏆 Stats",
        value=(
            "!topkills\n"
            "!toplongshots\n"
            "!heatmap\n"
            "!swearjar"
        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ Admin",
        value=(
            "!restartserver\n"
            "!setrestartinterval <hours>\n"
            "!setrestartstart <hour>\n"
            "!listrestarts"
        ),
        inline=False
    )

    embed.add_field(
        name="🧠 Features",
        value=(
            "• Live raid feed\n"
            "• PvP heatmaps\n"
            "• Online tracking\n"
            "• AI chatter\n"
            "• Welcome system\n"
            "• Leaderboards\n"
            "• Restart automation\n"
            "• AI survivor chatter\n"
            "• Smart welcome system\n"
            "• Live online dashboards\n"
            "• Real Nitrado restart control"
        ),
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Help System"
    )

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def online(ctx):

    guild_id = str(ctx.guild.id)

    ensure_guild_runtime(guild_id)

    guild_online = online_players[guild_id]

    if guild_online:

        player_list = "\n".join(
            f"🟢 {player}"
            for player in sorted(guild_online)
        )

    else:

        player_list = "No players online."

    embed = discord.Embed(
        title=f"✅🎮 ONLINE SURVIVORS 🎮✅ ({len(guild_online)})",
        description=player_list,
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def swearjar(ctx):

    if not swear_jar:

        await ctx.send(
            "Swear jar is empty."
        )

        return

    sorted_users = sorted(
        swear_jar.values(),
        key=lambda x: x["balance"],
        reverse=True
    )

    leaderboard = []

    for index, user in enumerate(
        sorted_users[:10],
        start=1
    ):

        leaderboard.append(
            f"{index}. {user['name']} - £{user['balance']} ({user['count']} swears)"
        )

    embed = discord.Embed(
        title="💸 SWEAR JAR LEADERBOARD",
        description="\n".join(leaderboard),
        color=0xF1C40F
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def heatmap(ctx):

    guild_id = str(ctx.guild.id)

    ensure_guild_runtime(guild_id)

    if not territory_heat[guild_id]:

        await ctx.send(
            "No territory activity yet."
        )

        return

    sorted_zones = sorted(
        territory_heat[guild_id].items(),
        key=lambda x: x[1],
        reverse=True
    )

    lines = []

    for zone, count in sorted_zones:

        lines.append(
            f"🔥 {zone} - {count}"
        )

    embed = discord.Embed(
        title="🗺️ TERRITORY HEATMAP",
        description="\n".join(lines),
        color=0xE74C3C
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def toplongshots(ctx):

    if not longshot_records:

        await ctx.send(
            "No longshot records yet."
        )

        return

    sorted_records = sorted(
        longshot_records.items(),
        key=lambda x: x[1].get("distance", 0),
        reverse=True
    )

    lines = []

    for index, (guild_id, data) in enumerate(
        sorted_records[:10],
        start=1
    ):

        guild_name = guild_configs.get(
            guild_id,
            {}
        ).get("guild_name", "Unknown Server")

        lines.append(
            f"{index}. {data.get('killer')} — 🎯 {data.get('distance')}m — {guild_name}"
        )

    embed = discord.Embed(
        title="🎯 GLOBAL LONGSHOT LEADERBOARD",
        description="\n".join(lines),
        color=0xF1C40F
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Longshot Intelligence"
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def topkills(ctx):

    if not player_stats:

        await ctx.send(
            "No stats available."
        )

        return

    sorted_players = sorted(
        player_stats.items(),
        key=lambda x: x[1].get("kills", 0),
        reverse=True
    )

    lines = []

    for index, (player, stats) in enumerate(
        sorted_players[:10],
        start=1
    ):

        lines.append(
            f"{index}. {player} - {stats.get('kills', 0)} kills"
        )

    embed = discord.Embed(
        title="☠️ TOP KILLS",
        description="\n".join(lines),
        color=0x992D22
    )

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# CUSTOM ROLE CONFIGURATION
# =========================================================

@bot.command()
async def setadminrole(ctx, *, role_name: str):

    if not ctx.author.guild_permissions.administrator:
        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["admin_roles"] = [role_name]

    save_guild_configs()

    embed = discord.Embed(
        title="🛡️ PRIMARY ADMIN ROLE SET",
        description=f"Primary bot admin role is now: `{role_name}`",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def addstaffrole(ctx, *, role_name: str):

    if not ctx.author.guild_permissions.administrator:
        return

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    roles = config.get(
        "admin_roles",
        DEFAULT_ADMIN_ROLES.copy()
    )

    if role_name not in roles:
        roles.append(role_name)

    guild_configs[guild_id]["admin_roles"] = roles

    save_guild_configs()

    embed = discord.Embed(
        title="➕ STAFF ROLE ADDED",
        description=f"`{role_name}` can now use admin bot commands.",
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def staffroles(ctx):

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    roles = config.get(
        "admin_roles",
        DEFAULT_ADMIN_ROLES
    )

    embed = discord.Embed(
        title="🛡️ BOT STAFF ROLES",
        description="\n".join([
            f"• {role}"
            for role in roles
        ]),
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))

# =========================================================
# FACTION TICKET SYSTEM
# =========================================================

@bot.command()
async def factionticket(ctx, *, faction_name: str):

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    ticket_channel = bot.get_channel(
        channels.get("faction_tickets")
    )

    if not ticket_channel:

        await ctx.send(
            "Faction ticket system is not configured."
        )

        return

    linked_data = linked_players.get(
        str(ctx.author.id),
        {}
    )

    gamertag = linked_data.get(
        "gamertag",
        "Not Linked"
    )

    embed = discord.Embed(
        title="🎫 NEW FACTION REQUEST",
        description=(
            f"{ctx.author.mention} has submitted a faction request."
        ),
        color=0x9B59B6
    )

    embed.add_field(
        name="🏴 Proposed Faction",
        value=faction_name,
        inline=False
    )

    embed.add_field(
        name="👤 Discord User",
        value=str(ctx.author),
        inline=True
    )

    embed.add_field(
        name="🎮 Linked Gamertag",
        value=gamertag,
        inline=True
    )

    embed.add_field(
        name="👑 Faction Owner",
        value=ctx.author.mention,
        inline=False
    )

    embed.add_field(
        name="📜 Status",
        value="🟡 Pending Staff Review",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Faction Intelligence"
    )

    ticket_message = await ticket_channel.send(
        embed=style_embed(embed)
    )

    staff_channel = bot.get_channel(
        channels.get("faction_staff")
    )

    if staff_channel:

        staff_embed = discord.Embed(
            title="🚨 NEW FACTION TICKET",
            description=(
                f"A new faction application has been submitted by {ctx.author.mention}."
            ),
            color=0xE67E22
        )

        staff_embed.add_field(
            name="🏴 Faction",
            value=faction_name,
            inline=True
        )

        staff_embed.add_field(
            name="🎫 Ticket ID",
            value=str(ticket_message.id),
            inline=True
        )

        staff_embed.add_field(
            name="👑 Owner",
            value=str(ctx.author),
            inline=False
        )

        staff_embed.set_thumbnail(url=BOT_IMAGE)

        staff_embed.set_footer(
            text="Wandering Bot Alpha • Staff Notification"
        )

        await staff_channel.send(
            embed=style_embed(staff_embed)
        )

    confirmation = discord.Embed(
        title="✅ FACTION REQUEST SUBMITTED",
        description=(
            f"Your faction request for `{faction_name}` has been sent to server staff."
        ),
        color=0x2ECC71
    )

    confirmation.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(confirmation)
    )


@bot.command()
async def factionapprove(ctx, message_id: int):

    if not has_staff_permissions(ctx):
        return

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    ticket_channel = bot.get_channel(
        channels.get("faction_tickets")
    )

    if not ticket_channel:
        return

    try:

        message = await ticket_channel.fetch_message(message_id)

        embed = message.embeds[0]

        approved_embed = discord.Embed(
            title="✅ FACTION APPROVED",
            description=embed.description,
            color=0x2ECC71
        )

        for field in embed.fields:

            approved_embed.add_field(
                name=field.name,
                value=field.value,
                inline=field.inline
            )

        approved_embed.set_thumbnail(url=BOT_IMAGE)

        approved_embed.set_footer(
            text="Wandering Bot Alpha • Staff Approved"
        )

        await message.edit(
            embed=style_embed(approved_embed)
        )

        await ctx.send(
            "✅ Faction request approved."
        )

    except Exception as error:

        await ctx.send(
            f"❌ Failed to approve ticket: {error}"
        )


# =========================================================
# CHAT MANAGEMENT SYSTEM
# =========================================================

@bot.command()
async def purge(ctx, amount: int = 10):

    if not has_staff_permissions(ctx):
        return

    if amount < 1:
        amount = 1

    if amount > 500:
        amount = 500

    deleted = await ctx.channel.purge(limit=amount + 1)

    embed = discord.Embed(
        title="🧹 CHAT PURGED",
        description=(
            f"Removed {len(deleted) - 1} messages from {ctx.channel.mention}"
        ),
        color=0xE67E22
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    confirmation = await ctx.send(
        embed=style_embed(embed)
    )

    await asyncio.sleep(5)

    await confirmation.delete()


@bot.command()
async def purgeuser(ctx, member: discord.Member, amount: int = 50):

    if not has_staff_permissions(ctx):
        return

    deleted = []

    async for message in ctx.channel.history(limit=500):

        if message.author == member:

            deleted.append(message)

            if len(deleted) >= amount:
                break

    for message in deleted:

        try:
            await message.delete()
        except:
            pass

    embed = discord.Embed(
        title="🧹 USER MESSAGES PURGED",
        description=(
            f"Removed {len(deleted)} messages from {member.mention}"
        ),
        color=0xE74C3C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    confirmation = await ctx.send(
        embed=style_embed(embed)
    )

    await asyncio.sleep(5)

    await confirmation.delete()


@bot.command()
async def purgebots(ctx, amount: int = 100):

    if not has_staff_permissions(ctx):
        return

    deleted = []

    async for message in ctx.channel.history(limit=1000):

        if message.author.bot:

            deleted.append(message)

            if len(deleted) >= amount:
                break

    for message in deleted:

        try:
            await message.delete()
        except:
            pass

    embed = discord.Embed(
        title="🤖 BOT MESSAGES PURGED",
        description=f"Removed {len(deleted)} bot messages.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    confirmation = await ctx.send(
        embed=style_embed(embed)
    )

    await asyncio.sleep(5)

    await confirmation.delete()

# =========================================================
# RADAR PING SYSTEM
# =========================================================

RADAR_PINGS = {}


@bot.command()
async def setradarchannel(ctx, channel: discord.TextChannel):

    if not has_staff_permissions(ctx):
        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["channels"]["radar"] = channel.id

    save_guild_configs()

    embed = discord.Embed(
        title="📡 RADAR CHANNEL CONFIGURED",
        description=f"Radar alerts will now go to {channel.mention}",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def radarping(ctx, x: str, y: str, *, reason: str = "Survivor Activity"):

    if not has_staff_permissions(ctx):
        return

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    radar_channel = bot.get_channel(
        channels.get("radar")
    )

    if not radar_channel:

        await ctx.send("❌ Radar channel not configured.")
        return

    map_link = f"https://dayz.ginfo.gg/#location={x};{y}"

    embed = discord.Embed(
        title="📡 MANUAL RADAR PING",
        description="Suspicious activity detected.",
        color=0xE74C3C
    )

    embed.add_field(
        name="🎯 Activity",
        value=reason,
        inline=False
    )

    embed.add_field(
        name="📍 Coordinates",
        value=f"[🔵 Open Map](<{map_link}>)",
        inline=False
    )

    embed.add_field(
        name="🛡️ Triggered By",
        value=ctx.author.mention,
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Radar Intelligence"
    )

    await radar_channel.send(
        embed=style_embed(embed)
    )

    await ctx.send("✅ Radar ping sent.")

# =========================================================
# ADMIN SERVER CONTROLS
# =========================================================

@bot.command()
async def restartserver(ctx):

    if not has_staff_permissions(ctx):
        return

    embed = discord.Embed(
        title="🔄 SERVER RESTART REQUESTED",
        description="Live restart request sent to Nitrado server.",
        color=0xE67E22
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

    print("SERVER RESTART REQUESTED")

    guild_id = str(ctx.guild.id)
    config = guild_configs.get(guild_id, {})

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    if not token or not service_id:
        return

    try:

        url = (
            f"https://api.nitrado.net/services/"
            f"{service_id}/gameservers/restart"
        )

        headers = {
            "Authorization": f"Bearer {token}"
        }

        restart_response = requests.post(
            url,
            headers=headers,
            timeout=30
        )

        print(f"RESTART STATUS: {restart_response.status_code}")

    except Exception as error:
        print(error)


@bot.command()
async def togglebasedamage(ctx, state: str):

    if not has_staff_permissions(ctx):
        return

    state = state.lower()

    if state not in ["on", "off"]:

        await ctx.send(
            "Usage: !togglebasedamage on/off"
        )

        return

    embed = discord.Embed(
        title="🛡️ BASE DAMAGE SETTINGS",
        description=f"Base damage turned {state.upper()}.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

    print(f"BASE DAMAGE {state.upper()}")

# =========================================================
# RESTART SCHEDULER COMMANDS
# =========================================================

@bot.command()
async def setrestartinterval(ctx, hours: int):

    if not has_staff_permissions(ctx):
        return

    if hours < 1 or hours > 24:

        await ctx.send(
            "Restart interval must be between 1 and 24 hours."
        )

        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["restart_interval_hours"] = hours

    save_guild_configs()

    embed = discord.Embed(
        title="⏰ RESTART INTERVAL UPDATED",
        description=f"Server will now restart every {hours} hours.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def setrestartstart(ctx, hour: int):

    if not has_staff_permissions(ctx):
        return

    if hour < 0 or hour > 23:

        await ctx.send(
            "Start hour must be between 0 and 23 UTC."
        )

        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["restart_start_hour"] = hour

    save_guild_configs()

    embed = discord.Embed(
        title="🕒 RESTART START HOUR UPDATED",
        description=f"Restart schedule now begins at {hour}:00 UTC.",
        color=0x1ABC9C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def listrestarts(ctx):

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    interval = config.get(
        "restart_interval_hours",
        DEFAULT_RESTART_INTERVAL_HOURS
    )

    start_hour = config.get(
        "restart_start_hour",
        0
    )

    times = []

    current = start_hour

    while current < 24:

        times.append(f"{current:02d}:00 UTC")

        current += interval

    embed = discord.Embed(
        title="📢 ACTIVE RESTART SCHEDULE",
        description="\n".join(times),
        color=0xE67E22
    )

    embed.add_field(
        name="Interval",
        value=f"Every {interval} hours",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))

# =========================================================
# SCHEDULED RESTART LOOP
# =========================================================

DEFAULT_RESTART_INTERVAL_HOURS = 4

last_restart_hour = {}
restart_warning_tracker = {}

@tasks.loop(minutes=1)
async def scheduled_restart_loop():

    global last_restart_hour

    now = datetime.now(UTC)

    current_hour = now.hour
    current_minute = now.minute

    for guild_id, config in list(guild_configs.items()):

        restart_interval = config.get(
            "restart_interval_hours",
            DEFAULT_RESTART_INTERVAL_HOURS
        )

        restart_offset = config.get(
            "restart_start_hour",
            0
        )

        should_restart = (
            current_hour >= restart_offset
            and ((current_hour - restart_offset) % restart_interval == 0)
            and current_minute == 0
        )

        if not should_restart:
            continue

        if last_restart_hour.get(guild_id) == current_hour:
            continue

        last_restart_hour[guild_id] = current_hour

        print(f"SCHEDULED RESTART TRIGGERED {guild_id} @ {current_hour}:00")

        try:

            channels = config.get("channels", {})

            announce_channel = bot.get_channel(
                channels.get("restart_alerts")
            )

            if announce_channel:

                embed = discord.Embed(
                    title="⚠️ SCHEDULED RESTART",
                    description=(
                        f"Automatic restart triggered.\n\n"
                        f"⏰ Interval: Every {restart_interval} hours\n"
                        f"🕒 Current Restart: {current_hour}:00 UTC"
                    ),
                    color=0xE74C3C
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                await announce_channel.send(
                    embed=style_embed(embed)
                )

                token = config.get("nitrado_token")
                service_id = config.get("service_id")

                if token and service_id:

                    try:

                        url = (
                            f"https://api.nitrado.net/services/"
                            f"{service_id}/gameservers/restart"
                        )

                        headers = {
                            "Authorization": f"Bearer {token}"
                        }

                        restart_response = requests.post(
                            url,
                            headers=headers,
                            timeout=30
                        )

                        print(f"AUTO RESTART STATUS: {restart_response.status_code}")

                    except Exception as restart_error:
                        print(restart_error)

        except Exception as error:

            print(error)

# =========================================================
# AI ALERT SYSTEM
# =========================================================

WELCOME_MESSAGES = [
    "Welcome to the apocalypse, survivor. Trust nobody. Especially Dave.",
    "Fresh spawn detected. Someone hide the baked beans.",
    "Welcome in survivor. The wolves can smell fear already.",
    "Another poor soul has entered Chernarus willingly.",
    "Welcome survivor. If you hear footsteps, start panicking.",

    "Welcome to the wasteland, survivor. Try not to die immediately.",
    "Fresh meat has arrived. Someone hide the loot.",
    "Another survivor enters Chernarus with terrible decision making.",
    "Welcome in. Watch out for wolves, snipers, and your own teammates.",
    "Good luck survivor. You're absolutely going to need it."
]

AI_RESPONSES = {
    "angry": "🧠 Maybe log off before you challenge a door to a fist fight.",
    "trash": "💀 DayZ humbles everybody eventually.",
    "lag": "📡 AI Notice: If desync hits, avoid driving unless you enjoy orbiting into space.",
    "hungry": "🥫 Tip: Fishing gear is more valuable than most guns early game.",
    "bear": "🐻 AI Warning: If you hear the bear first, it's probably too late.",
    "raid": "🧠 Tip: Metal doors buy time. Hidden loot buys survival.",
    "loot": "🧠 Tip: Medical buildings and hunting camps are usually worth checking.",
    "base": "🧠 Tip: Small hidden stashes survive longer than giant compounds.",
    "cheater": "🧠 AI Watch: Record clips and timestamps before reporting suspicious activity.",
    "dead": "💀 DayZ teaches lessons the painful way.",
    "fuck": "💸 Calm down survivor, the swear jar is getting rich.",
    "shit": "🧠 Tactical advice: panicking rarely improves aim."
}

AI_KEYWORDS = [
    "raid",
    "explosive",
    "helicrash",
    "admin",
    "cheater",
    "speedhack",
    "base damage"
]

FUNNY_ROTATION = [
    "🧠 Pro tip: if you hear wolves, you are the side quest.",
    "💀 DayZ is 10% aim and 90% bad life choices.",
    "🥫 Beans are temporary. Trauma is forever.",
    "📻 If your friend says 'trust me', do not trust them.",
    "🧤 Helpful advice: carry bandages before ego."
]

async def send_ai_alert(guild_id, config, line):

    channels = config.get("channels", {})

    ai_channel = bot.get_channel(
        channels.get("ai_chat")
    )

    if not ai_channel:
        return

    embed = discord.Embed(
        title="🧠 AI ALERT",
        description=line,
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ai_channel.send(
        embed=style_embed(embed)
    )

# =========================================================
# LIVE SERVER STATUS
# =========================================================

@bot.command()
async def serverstatus(ctx):

    total_guilds = len(guild_configs)

    total_players = sum(len(players) for players in online_players.values())

    embed = discord.Embed(
        title="📡 WANDERING BOT STATUS",
        color=0x3498DB
    )

    embed.add_field(
        name="Connected Servers",
        value=str(total_guilds),
        inline=True
    )

    embed.add_field(
        name="Tracked Players",
        value=str(total_players),
        inline=True
    )

    embed.add_field(
        name="ADM Parser",
        value="🟢 ONLINE",
        inline=False
    )

    embed.add_field(
        name="API Status",
        value="🟢 CONNECTED",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# DISCORD ↔ GAMERTAG LINKING
# =========================================================

@bot.command()
async def linkgamer(ctx, *, gamertag: str):

    user_id = str(ctx.author.id)

    linked_players[user_id] = {
        "discord_name": str(ctx.author),
        "gamertag": gamertag
    }

    save_linked_players()

    embed = discord.Embed(
        title="🔗 GAMERTAG LINKED",
        description=(
            f"Your Discord account is now linked to: `{gamertag}`"
        ),
        color=0x2ECC71
    )

    embed.add_field(
        name="🎮 Linked Survivor",
        value=gamertag,
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Identity System"
    )

    await ctx.send(embed=style_embed(embed))


@bot.tree.command(
    name="linkgamer",
    description="Link your Discord account to your Xbox gamertag"
)
@app_commands.describe(gamertag="Your Xbox gamertag")
async def slash_linkgamer(interaction: discord.Interaction, gamertag: str):
    user_id = str(interaction.user.id)
    linked_players[user_id] = {
        "discord_name": str(interaction.user),
        "gamertag": gamertag
    }
    save_linked_players()
    embed = discord.Embed(
        title="🔗 GAMERTAG LINKED",
        description=f"Linked to: `{gamertag}`",
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.command()
async def mylink(ctx):

    user_id = str(ctx.author.id)

    if user_id not in linked_players:

        await ctx.send(
            "❌ No linked gamertag found. Use `!linkgamer YourName`"
        )

        return

    data = linked_players[user_id]

    embed = discord.Embed(
        title="🎮 LINKED SURVIVOR PROFILE",
        color=0x3498DB
    )

    embed.add_field(
        name="Discord",
        value=str(ctx.author),
        inline=False
    )

    embed.add_field(
        name="Gamertag",
        value=data['gamertag'],
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.has_permissions(administrator=True)
async def unlinkgamer(ctx, member: discord.Member):

    user_id = str(member.id)

    if user_id not in linked_players:

        await ctx.send("No linked gamertag found.")
        return

    del linked_players[user_id]

    save_linked_players()

    await ctx.send(
        f"🗑️ Removed linked gamertag for {member.mention}"
    )

# =========================================================
# PLAYER LOOKUP
# =========================================================

@bot.command()
async def playerstats(ctx, *, player_name: str):

    if player_name not in player_stats:

        await ctx.send(
            "Player not found."
        )

        return

    stats = player_stats[player_name]

    embed = discord.Embed(
        title=f"📊 PLAYER STATS - {player_name}",
        color=0x1ABC9C
    )

    embed.add_field(
        name="Kills",
        value=str(stats.get("kills", 0)),
        inline=True
    )

    embed.add_field(
        name="Deaths",
        value=str(stats.get("deaths", 0)),
        inline=True
    )

    embed.add_field(
        name="Raids",
        value=str(stats.get("raids", 0)),
        inline=True
    )

    embed.add_field(
        name="Builds",
        value=str(stats.get("builds", 0)),
        inline=True
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# PERSISTENT MULTI-GUILD STORAGE
# =========================================================

# Guild setups are permanently stored in:
# guild_configs.json
#
# This means if the bot restarts, redeploys,
# crashes, or updates, every server remains linked
# automatically without requiring /setup again.
#
# Server owners only need to run /setup once.
#
# The only time setup is needed again is if:
# - guild_configs.json is deleted
# - the bot is kicked from a server
# - the hosting storage is wiped manually
#
# =========================================================
# AUTO START TASKS
# =========================================================

async def start_background_tasks():

    try:

        if not adm_loop.is_running():
            adm_loop.start()

        if not online_dashboard_loop.is_running():
            online_dashboard_loop.start()

        if not leaderboard_loop.is_running():
            leaderboard_loop.start()

        if not heatmap_loop.is_running():
            heatmap_loop.start()

        if not scheduled_restart_loop.is_running():
            scheduled_restart_loop.start()

        if not restart_delivery_processor.is_running():
            restart_delivery_processor.start()

    except RuntimeError:
        pass

# =========================================================
# LIVE ONLINE DASHBOARD
# =========================================================

@tasks.loop(minutes=ONLINE_UPDATE_MINUTES)
async def online_dashboard_loop():

    for guild_id, config in list(guild_configs.items()):

        try:

            channels = config.get("channels", {})

            online_channel = bot.get_channel(
                channels.get("online")
            )

            if not online_channel:
                continue

            ensure_guild_runtime(guild_id)

            guild_online = online_players[guild_id]

            if guild_online:

                player_text = "\n".join([
                    f"🟢 {player}"
                    for player in sorted(guild_online)
                ])

            else:

                player_text = "No survivors online."

            embed = discord.Embed(
                title=f"✅🎮 LIVE SURVIVORS ONLINE 🎮✅ ({len(guild_online)})",
                description=player_text,
                color=0x2ECC71
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Auto Refresh Every 15 Minutes"
            )

            embed.timestamp = datetime.now(UTC)

            old_message_id = last_online_message_ids.get(guild_id)
            if old_message_id:
                try:
                    old_message = await online_channel.fetch_message(old_message_id)
                    await old_message.delete()
                except Exception:
                    pass

            sent_message = await online_channel.send(embed=embed)
            last_online_message_ids[guild_id] = sent_message.id

        except Exception as error:
            print(error)

# =========================================================
# LIVE PVP HEATMAP DASHBOARD
# =========================================================

@tasks.loop(minutes=HEATMAP_UPDATE_MINUTES)
async def heatmap_loop():

    for guild_id, config in list(guild_configs.items()):

        try:

            channels = config.get("channels", {})

            heatmap_channel = bot.get_channel(
                channels.get("heatmap")
            )

            if not heatmap_channel:
                continue

            ensure_guild_runtime(guild_id)

            hottest_zones = sorted(
                territory_heat[guild_id].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            lines = []

            for zone, count in hottest_zones:
                lines.append(
                    f"🔥 {zone} — {count} PvP events"
                )

            embed = discord.Embed(
                title="🔥 LIVE CONFLICT HEATMAP",
                description=(
                    "\n".join(lines)
                    if lines else "No PvP activity detected yet."
                ),
                color=0x9B59B6
            )

            embed.add_field(
                name="📡 Status",
                value="Tracking live combat zones across the server.",
                inline=False
            )

            heatmap_path = generate_guild_heatmap_image(guild_id)
            file = discord.File(heatmap_path, filename="heatmap.png")
            embed.set_image(url="attachment://heatmap.png")

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Heatmap Refresh Every 15 Minutes"
            )

            embed.timestamp = datetime.now(UTC)

            old_message_id = last_heatmap_message_ids.get(guild_id)
            if old_message_id:
                try:
                    old_message = await heatmap_channel.fetch_message(old_message_id)
                    await old_message.delete()
                except Exception:
                    pass

            sent_message = await heatmap_channel.send(embed=embed, file=file)
            last_heatmap_message_ids[guild_id] = sent_message.id
            try:
                os.remove(heatmap_path)
            except Exception:
                pass

        except Exception as error:
            print(error)

# =========================================================
# LIVE LEADERBOARD DASHBOARD
# =========================================================

@tasks.loop(minutes=LEADERBOARD_UPDATE_MINUTES)
async def leaderboard_loop():

    for guild_id, config in list(guild_configs.items()):

        try:

            channels = config.get("channels", {})

            leaderboard_channel = bot.get_channel(
                channels.get("leaderboards")
            )

            if not leaderboard_channel:
                continue

            sorted_players = sorted(
                player_stats.items(),
                key=lambda x: x[1].get("kills", 0),
                reverse=True
            )

            lines = []

            for index, (player, stats) in enumerate(
                sorted_players[:10],
                start=1
            ):

                lines.append(
                    f"{index}. {player} — ☠️ {stats.get('kills', 0)} | 💀 {stats.get('deaths', 0)}"
                )

            global_lines = lines[:5]

            guild_lines = []
            guild_only = []
            for player, stats in player_stats.items():
                if str(stats.get("guild_id", "")) == guild_id:
                    guild_only.append((player, stats))
            guild_only.sort(key=lambda x: x[1].get("kills", 0), reverse=True)
            for idx, (player, stats) in enumerate(guild_only[:5], start=1):
                guild_lines.append(
                    f"{idx}. {player} — ☠️ {stats.get('kills', 0)} | 💀 {stats.get('deaths', 0)}"
                )

            embed = discord.Embed(
                title="🏆 LEADERBOARDS (GLOBAL + THIS SERVER) 🏆",
                color=0xF1C40F
            )
            embed.add_field(
                name="🌍 Global Top 5",
                value="\n".join(global_lines) if global_lines else "No stats yet.",
                inline=False
            )
            embed.add_field(
                name="🏠 This Server Top 5",
                value="\n".join(guild_lines) if guild_lines else "No guild-specific stats yet.",
                inline=False
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Leaderboards Refresh Every 15 Minutes"
            )

            embed.timestamp = datetime.now(UTC)

            old_message_id = last_leaderboard_message_ids.get(guild_id)
            if old_message_id:
                try:
                    old_message = await leaderboard_channel.fetch_message(old_message_id)
                    await old_message.delete()
                except Exception:
                    pass

            sent_message = await leaderboard_channel.send(embed=embed)
            last_leaderboard_message_ids[guild_id] = sent_message.id

        except Exception as error:
            print(error)

# READY BLOCK MOVED TO BOTTOM OF FILE

# =========================================================
# ECONOMY SYSTEM FOUNDATION
# =========================================================

SHOP_FILE = "shop.json"
WALLETS_FILE = "wallets.json"
DELIVERY_QUEUE_FILE = "delivery_queue.json"

shop_items = {}
wallets = {}
delivery_queue = []
vehicle_rentals_queue = []


def load_shop():
    global shop_items
    shop_items = load_json(SHOP_FILE)


def save_shop():
    save_json(SHOP_FILE, shop_items)


def load_wallets():
    global wallets
    wallets = load_json(WALLETS_FILE)


def save_wallets():
    save_json(WALLETS_FILE, wallets)


def load_delivery_queue():
    global delivery_queue

    if os.path.exists(DELIVERY_QUEUE_FILE):

        with open(DELIVERY_QUEUE_FILE, "r") as f:
            delivery_queue = json.load(f)


def save_delivery_queue():

    with open(DELIVERY_QUEUE_FILE, "w") as f:
        json.dump(delivery_queue, f, indent=4)


DEFAULT_DAILY_TRANSACTION_LIMIT = 5
VEHICLE_RENTAL_FILE = "vehicle_rentals.json"


# =========================================================
# BASIC SHOP COMMANDS
# =========================================================

@bot.command()
async def wallet(ctx):

    user_id = str(ctx.author.id)

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(ctx.author),
            "balance": 0,
            "daily_transactions": 0
        }

        save_wallets()

    balance = wallets[user_id]["balance"]

    embed = discord.Embed(
        title="💰 SURVIVOR WALLET",
        description=f"{balance} pennies 🪙",
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def shop(ctx):

    if not shop_items:

        await ctx.send("Shop is currently empty.")
        return

    lines = []

    for item_name, data in shop_items.items():

        lines.append(
            f"• {item_name} — {data.get('price', 0)} pennies 🪙"
        )

    embed = discord.Embed(
        title="🛒 BLACK MARKET SHOP",
        description="\n".join(lines[:25]),
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Black Market"
    )

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def buy(ctx, item_name: str, x: str, y: str):

    user_id = str(ctx.author.id)

    if item_name not in shop_items:

        await ctx.send("That item does not exist in the shop.")
        return

    if not shop_items[item_name].get("enabled", True):

        await ctx.send("❌ That item is currently disabled.")
        return

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(ctx.author),
            "balance": 0,
            "daily_transactions": 0
        }

    wallet = wallets[user_id]

    limit = DEFAULT_DAILY_TRANSACTION_LIMIT

    if wallet["daily_transactions"] >= limit:

        await ctx.send("❌ Daily delivery limit reached.")
        return

    price = shop_items[item_name].get("price", 0)

    if wallet["balance"] < price:

        await ctx.send("❌ Not enough pennies.")
        return

    wallet["balance"] -= price
    wallet["daily_transactions"] += 1

    delivery_queue.append({
        "delivery_type": "item",
        "spawn_ready": False,
        "player": str(ctx.author),
        "discord_id": user_id,
        "item": item_name,
        "x": x,
        "y": y,
        "status": "queued",
        "created": str(datetime.now(UTC))
    })

    save_wallets()
    save_delivery_queue()

    map_link = f"https://dayz.ginfo.gg/#location={x};{y}"

    embed = discord.Embed(
        title="📦 DELIVERY QUEUED",
        description=(
            f"Your order has been added to the next restart delivery queue."
        ),
        color=0x3498DB
    )

    embed.add_field(
        name="📦 Item",
        value=item_name,
        inline=True
    )

    embed.add_field(
        name="💰 Cost",
        value=f"{price} pennies 🪙",
        inline=True
    )

    embed.add_field(
        name="📍 Delivery Location",
        value=f"[🔵 Open Map](<{map_link}>)",
        inline=False
    )

    embed.add_field(
        name="⏰ Delivery ETA",
        value="Next server restart",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Black Market Delivery"
    )

    await ctx.send(embed=style_embed(embed))

    # ================= PURCHASE LOG =================

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    purchase_log_channel = bot.get_channel(
        config.get("channels", {}).get("purchase_logs")
    )

    if purchase_log_channel:

        log_embed = discord.Embed(
            title="💳 NEW BLACK MARKET PURCHASE",
            color=0x9B59B6
        )

        log_embed.add_field(
            name="👤 Survivor",
            value=ctx.author.mention,
            inline=True
        )

        log_embed.add_field(
            name="📦 Item",
            value=item_name,
            inline=True
        )

        log_embed.add_field(
            name="💰 Price",
            value=f"{price} pennies 🪙",
            inline=True
        )

        log_embed.add_field(
            name="📍 Delivery Location",
            value=f"[🔵 Open Map](<{map_link}>)",
            inline=False
        )

        log_embed.set_thumbnail(url=BOT_IMAGE)

        log_embed.set_footer(
            text="Wandering Bot Alpha • Purchase Logs"
        )

        await purchase_log_channel.send(
            embed=style_embed(log_embed)
        )


# =========================================================
# VEHICLE RENTAL SYSTEM
# =========================================================

@bot.command()
async def rentvehicle(ctx, vehicle_name: str, rental_hours: int, x: str, y: str):

    user_id = str(ctx.author.id)

    if vehicle_name not in shop_items:

        await ctx.send("❌ Vehicle not available.")
        return

    vehicle_data = shop_items[vehicle_name]

    if vehicle_data.get("category", "").lower() != "vehicles":

        await ctx.send("❌ That item is not configured as a rentable vehicle.")
        return

    rental_price = vehicle_data.get("price", 0) * max(rental_hours, 1)

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(ctx.author),
            "balance": 0,
            "daily_transactions": 0
        }

    if wallets[user_id]["balance"] < rental_price:

        await ctx.send("❌ Not enough pennies.")
        return

    wallets[user_id]["balance"] -= rental_price

    rental_entry = {
        "player": str(ctx.author),
        "discord_id": user_id,
        "vehicle": vehicle_name,
        "x": x,
        "y": y,
        "rental_hours": rental_hours,
        "status": "queued",
        "created": str(datetime.now(UTC))
    }

    vehicle_rentals_queue.append(rental_entry)

    save_wallets()
    save_delivery_queue()

    map_link = f"https://dayz.ginfo.gg/#location={x};{y}"

    embed = discord.Embed(
        title="🚗 VEHICLE RENTAL CONFIRMED",
        description="Vehicle queued for next restart delivery.",
        color=0x3498DB
    )

    embed.add_field(
        name="🚗 Vehicle",
        value=vehicle_name,
        inline=True
    )

    embed.add_field(
        name="⏰ Rental Period",
        value=f"{rental_hours} hours",
        inline=True
    )

    embed.add_field(
        name="💰 Cost",
        value=f"{rental_price} pennies 🪙",
        inline=True
    )

    embed.add_field(
        name="📍 Spawn Location",
        value=f"[🔵 Open Map](<{map_link}>)",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Vehicle Rental System"
    )

    await ctx.send(embed=style_embed(embed))

    # ================= RENTAL LOG =================

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    rental_log_channel = bot.get_channel(
        config.get("channels", {}).get("rental_logs")
    )

    if rental_log_channel:

        rental_embed = discord.Embed(
            title="🚗 NEW VEHICLE RENTAL",
            color=0x3498DB
        )

        rental_embed.add_field(
            name="👤 Survivor",
            value=ctx.author.mention,
            inline=True
        )

        rental_embed.add_field(
            name="🚗 Vehicle",
            value=vehicle_name,
            inline=True
        )

        rental_embed.add_field(
            name="⏰ Rental Time",
            value=f"{rental_hours} hours",
            inline=True
        )

        rental_embed.add_field(
            name="💰 Cost",
            value=f"{rental_price} pennies 🪙",
            inline=True
        )

        rental_embed.add_field(
            name="📍 Spawn Location",
            value=f"[🔵 Open Map](<{map_link}>)",
            inline=False
        )

        rental_embed.set_thumbnail(url=BOT_IMAGE)

        rental_embed.set_footer(
            text="Wandering Bot Alpha • Vehicle Rental Logs"
        )

        await rental_log_channel.send(
            embed=style_embed(rental_embed)
        )


# =========================================================
# RESTART DELIVERY PROCESSOR
# =========================================================

@tasks.loop(minutes=1)
async def restart_delivery_processor():

    now = datetime.now(UTC)

    for guild_id, config in list(guild_configs.items()):

        try:

            restart_interval = config.get(
                "restart_interval_hours",
                DEFAULT_RESTART_INTERVAL_HOURS
            )

            restart_offset = config.get(
                "restart_start_hour",
                0
            )

            if now.minute != 0:
                continue

            if (
                now.hour >= restart_offset
                and ((now.hour - restart_offset) % restart_interval == 0)
            ):

                delivery_file = os.path.join(
                    GUILD_DATA_FOLDER,
                    f"{guild_id}_deliveries.json"
                )

                output = {
                    "items": delivery_queue,
                    "vehicles": vehicle_rentals_queue,
                    "generated": str(now)
                }

                with open(delivery_file, "w") as f:
                    json.dump(output, f, indent=4)

                print(f"DELIVERY FILE GENERATED FOR {guild_id}")

                # =========================================
                # XML DELIVERY GENERATION
                # =========================================

                xml_lines = []

                xml_lines.append('<objects>')

                # ================= ITEMS =================

                for delivery in delivery_queue:

                    item_name = delivery.get("item")
                    x = delivery.get("x")
                    y = delivery.get("y")

                    xml_lines.append(
                        f'<object name="{item_name}" pos="{x} 0 {y}" />'
                    )

                # ================= VEHICLES =================

                for rental in vehicle_rentals_queue:

                    vehicle_name = rental.get("vehicle")
                    x = rental.get("x")
                    y = rental.get("y")

                    xml_lines.append(
                        f'<object name="{vehicle_name}" pos="{x} 0 {y}" />'
                    )

                xml_lines.append('</objects>')

                xml_output_path = os.path.join(
                    GUILD_DATA_FOLDER,
                    f"{guild_id}_deliveries.xml"
                )

                with open(xml_output_path, "w") as xml_file:

                    xml_file.write("\n".join(xml_lines))

                print(f"XML DELIVERY FILE GENERATED FOR {guild_id}")

                upload_success = upload_delivery_xml_to_nitrado(
                    config,
                    xml_output_path
                )

                if upload_success:

                    print(f"DELIVERY XML BRIDGED TO SERVER {guild_id}")

                    delivery_queue.clear()
                    vehicle_rentals_queue.clear()

                    save_delivery_queue()

        except Exception as error:
            print(error)


# =========================================================
# TYPES.XML SHOP MANAGEMENT SYSTEM
# =========================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def addshopitem(
    ctx,
    item_name: str,
    price: int,
    category: str = "General"
):

    shop_items[item_name] = {
        "price": price,
        "category": category,
        "enabled": True
    }

    save_shop()

    embed = discord.Embed(
        title="🛒 ITEM ADDED TO BLACK MARKET",
        color=0x2ECC71
    )

    embed.add_field(
        name="📦 Item",
        value=item_name,
        inline=True
    )

    embed.add_field(
        name="💰 Price",
        value=f"{price} pennies 🪙",
        inline=True
    )

    embed.add_field(
        name="📂 Category",
        value=category,
        inline=True
    )

    embed.add_field(
        name="📡 Delivery",
        value="Delivered next restart",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Economy Management"
    )

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.has_permissions(administrator=True)
async def editshopitem(
    ctx,
    item_name: str,
    price: int = None,
    category: str = None
):

    if item_name not in shop_items:

        await ctx.send("❌ Item not found in shop.")
        return

    if price is not None:
        shop_items[item_name]["price"] = price

    if category is not None:
        shop_items[item_name]["category"] = category

    save_shop()

    embed = discord.Embed(
        title="✏️ SHOP ITEM UPDATED",
        description=f"Updated `{item_name}` successfully.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.has_permissions(administrator=True)
async def toggleshopitem(ctx, item_name: str):

    if item_name not in shop_items:

        await ctx.send("❌ Item not found.")
        return

    current = shop_items[item_name].get("enabled", True)

    shop_items[item_name]["enabled"] = not current

    save_shop()

    state = "ENABLED" if not current else "DISABLED"

    embed = discord.Embed(
        title="📦 SHOP ITEM STATUS UPDATED",
        description=f"`{item_name}` is now {state}.",
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.has_permissions(administrator=True)
async def shopcategories(ctx):

    categories = {}

    for item, data in shop_items.items():

        category = data.get("category", "General")

        if category not in categories:
            categories[category] = []

        categories[category].append(item)

    embed = discord.Embed(
        title="📂 BLACK MARKET CATEGORIES",
        color=0xF1C40F
    )

    for category, items in categories.items():

        embed.add_field(
            name=f"📦 {category}",
            value=f"{len(items)} items",
            inline=False
        )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


# =========================================================
# ADMIN SHOP MANAGEMENT
# =========================================================


@bot.command()
@commands.has_permissions(administrator=True)
async def removeshopitem(ctx, *, item_name: str):

    if item_name not in shop_items:

        await ctx.send("Item not found.")
        return

    del shop_items[item_name]

    save_shop()

    await ctx.send(f"🗑️ Removed {item_name} from the shop.")


@bot.command()
@commands.has_permissions(administrator=True)
async def givepennies(ctx, member: discord.Member, amount: int):

    user_id = str(member.id)

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(member),
            "balance": 0,
            "daily_transactions": 0
        }

    wallets[user_id]["balance"] += amount

    save_wallets()

    await ctx.send(
        f"💰 Added {amount} pennies 🪙 to {member.mention}"
    )


@bot.tree.command(
    name="playerlottery",
    description="Admin only: pick a random currently-online player"
)
async def player_lottery(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    ensure_guild_runtime(guild_id)
    pool = sorted(list(online_players.get(guild_id, set())))
    if not pool:
        await interaction.response.send_message("No online players to pick from.", ephemeral=True)
        return
    import random
    winner = random.choice(pool)
    embed = discord.Embed(
        title="🎰 PLAYER LOTTERY",
        description=f"Winner: **{winner}**",
        color=0xF1C40F
    )
    await interaction.response.send_message(embed=style_embed(embed))


@bot.tree.command(name="online", description="Show currently online survivors")
async def slash_online(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    ensure_guild_runtime(guild_id)
    guild_online = online_players[guild_id]
    player_list = "\n".join(f"🟢 {p}" for p in sorted(guild_online)) if guild_online else "No players online."
    embed = discord.Embed(
        title=f"✅🎮 ONLINE SURVIVORS 🎮✅ ({len(guild_online)})",
        description=player_list,
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="serverstatus", description="Show Wandering Bot status")
async def slash_serverstatus(interaction: discord.Interaction):
    total_guilds = len(guild_configs)
    total_players = sum(len(players) for players in online_players.values())
    embed = discord.Embed(title="📡 WANDERING BOT STATUS", color=0x3498DB)
    embed.add_field(name="Connected Servers", value=str(total_guilds), inline=True)
    embed.add_field(name="Tracked Players", value=str(total_players), inline=True)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="supportbot", description="Request bot setup/help support")
@app_commands.describe(issue="Briefly describe your bot issue")
async def supportbot(interaction: discord.Interaction, issue: str):
    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id, {})
    channel_id = config.get("channels", {}).get("company_announcements")
    ch = bot.get_channel(channel_id) if channel_id else None
    if ch:
        embed = discord.Embed(
            title="🆘 Bot Support Request",
            description=issue[:1000],
            color=0xE67E22
        )
        embed.add_field(name="Server", value=interaction.guild.name, inline=False)
        embed.add_field(name="Requester", value=str(interaction.user), inline=False)
        await ch.send(embed=style_embed(embed))
    await interaction.response.send_message("✅ Support request submitted.", ephemeral=True)

# Full slash mapping wrappers for legacy commands
@bot.tree.command(name="helpme", description="Show command/help information")
async def slash_helpme(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "helpme")
@bot.tree.command(name="swearjar", description="Show swear jar leaderboard")
async def slash_swearjar(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "swearjar")
@bot.tree.command(name="heatmap", description="Show territory heatmap summary")
async def slash_heatmap(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "heatmap")
@bot.tree.command(name="toplongshots", description="Show longshot leaderboard")
async def slash_toplongshots(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "toplongshots")
@bot.tree.command(name="topkills", description="Show top kill leaderboard")
async def slash_topkills(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "topkills")
@bot.tree.command(name="staffroles", description="List staff roles")
async def slash_staffroles(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "staffroles")
@bot.tree.command(name="mylink", description="Show your linked gamertag")
async def slash_mylink(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "mylink")
@bot.tree.command(name="wallet", description="Show your wallet")
async def slash_wallet(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "wallet")
@bot.tree.command(name="shop", description="Show shop")
async def slash_shop(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "shop")

@bot.tree.command(name="setadminrole", description="Set primary admin role")
@app_commands.describe(role_name="Role name")
async def slash_setadminrole(interaction: discord.Interaction, role_name: str): await run_legacy_as_slash(interaction, "setadminrole", role_name=role_name)
@bot.tree.command(name="addstaffrole", description="Add a staff role")
@app_commands.describe(role_name="Role name")
async def slash_addstaffrole(interaction: discord.Interaction, role_name: str): await run_legacy_as_slash(interaction, "addstaffrole", role_name=role_name)
@bot.tree.command(name="factionticket", description="Create faction request")
@app_commands.describe(faction_name="Faction name")
async def slash_factionticket(interaction: discord.Interaction, faction_name: str): await run_legacy_as_slash(interaction, "factionticket", faction_name=faction_name)
@bot.tree.command(name="factionapprove", description="Approve faction request")
@app_commands.describe(message_id="Ticket message ID")
async def slash_factionapprove(interaction: discord.Interaction, message_id: int): await run_legacy_as_slash(interaction, "factionapprove", message_id=message_id)
@bot.tree.command(name="purge", description="Purge recent messages")
@app_commands.describe(amount="Amount")
async def slash_purge(interaction: discord.Interaction, amount: int = 10): await run_legacy_as_slash(interaction, "purge", amount=amount)
@bot.tree.command(name="purgeuser", description="Purge user messages")
@app_commands.describe(member="Member", amount="Amount")
async def slash_purgeuser(interaction: discord.Interaction, member: discord.Member, amount: int = 50): await run_legacy_as_slash(interaction, "purgeuser", member=member, amount=amount)
@bot.tree.command(name="purgebots", description="Purge bot messages")
@app_commands.describe(amount="Amount")
async def slash_purgebots(interaction: discord.Interaction, amount: int = 100): await run_legacy_as_slash(interaction, "purgebots", amount=amount)
@bot.tree.command(name="setradarchannel", description="Set radar channel")
@app_commands.describe(channel="Channel")
async def slash_setradarchannel(interaction: discord.Interaction, channel: discord.TextChannel): await run_legacy_as_slash(interaction, "setradarchannel", channel=channel)
@bot.tree.command(name="radarping", description="Send radar ping")
@app_commands.describe(x="X", y="Y", reason="Reason")
async def slash_radarping(interaction: discord.Interaction, x: str, y: str, reason: str = "Survivor Activity"): await run_legacy_as_slash(interaction, "radarping", x=x, y=y, reason=reason)
@bot.tree.command(name="restartserver", description="Restart server")
async def slash_restartserver(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "restartserver")
@bot.tree.command(name="togglebasedamage", description="Toggle base damage")
@app_commands.describe(state="on or off")
async def slash_togglebasedamage(interaction: discord.Interaction, state: str): await run_legacy_as_slash(interaction, "togglebasedamage", state=state)
@bot.tree.command(name="setrestartinterval", description="Set restart interval")
@app_commands.describe(hours="Hours 1-24")
async def slash_setrestartinterval(interaction: discord.Interaction, hours: int): await run_legacy_as_slash(interaction, "setrestartinterval", hours=hours)
@bot.tree.command(name="setrestartstart", description="Set restart start hour UTC")
@app_commands.describe(hour="Hour 0-23")
async def slash_setrestartstart(interaction: discord.Interaction, hour: int): await run_legacy_as_slash(interaction, "setrestartstart", hour=hour)
@bot.tree.command(name="listrestarts", description="List restart schedule")
async def slash_listrestarts(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "listrestarts")
@bot.tree.command(name="playerstats", description="Lookup player stats")
@app_commands.describe(player_name="Player name")
async def slash_playerstats(interaction: discord.Interaction, player_name: str): await run_legacy_as_slash(interaction, "playerstats", player_name=player_name)
@bot.tree.command(name="buy", description="Buy an item and queue delivery")
@app_commands.describe(item_name="Item", x="Map X", y="Map Y")
async def slash_buy(interaction: discord.Interaction, item_name: str, x: str, y: str): await run_legacy_as_slash(interaction, "buy", item_name=item_name, x=x, y=y)
@bot.tree.command(name="rentvehicle", description="Rent a vehicle")
@app_commands.describe(vehicle_name="Vehicle", rental_hours="Hours", x="Map X", y="Map Y")
async def slash_rentvehicle(interaction: discord.Interaction, vehicle_name: str, rental_hours: int, x: str, y: str): await run_legacy_as_slash(interaction, "rentvehicle", vehicle_name=vehicle_name, rental_hours=rental_hours, x=x, y=y)

# =========================================================
# DAYZ INIT.C DELIVERY LOADER (NITRADO SIDE)
# =========================================================

# ADD THIS TO YOUR DAYZ SERVER init.c FILE
# This loads deliveries.xml on restart.
# Your bot already uploads the XML automatically.
# This is the final bridge.

'''
void SpawnWanderingDeliveries()
{
    string path = "$profile:custom/deliveries.xml";

    FileHandle file = OpenFile(path, FileMode.READ);

    if (!file)
    {
        Print("[WANDERING BOT] deliveries.xml not found");
        return;
    }

    string line;

    while (FGets(file, line) > 0)
    {
        if (line.Contains("<object"))
        {
            string itemName;
            string position;

            int nameStart = line.IndexOf("name=\"") + 6;
            int nameEnd = line.IndexOf("\"", nameStart);

            itemName = line.Substring(nameStart, nameEnd - nameStart);

            int posStart = line.IndexOf("pos=\"") + 5;
            int posEnd = line.IndexOf("\"", posStart);

            position = line.Substring(posStart, posEnd - posStart);

            TStringArray posSplit = new TStringArray;
            position.Split(" ", posSplit);

            if (posSplit.Count() >= 3)
            {
                vector spawnPos = Vector(
                    posSplit.Get(0).ToFloat(),
                    posSplit.Get(1).ToFloat(),
                    posSplit.Get(2).ToFloat()
                );

                EntityAI spawned = EntityAI.Cast(
                    GetGame().CreateObject(itemName, spawnPos)
                );

                if (spawned)
                {
                    Print("[WANDERING BOT] Spawned: " + itemName);
                }
            }
        }
    }

    CloseFile(file);
}

// =====================================================
// CALL THIS INSIDE main() AFTER WEATHER SETUP
// =====================================================

SpawnWanderingDeliveries();
'''

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"SLASH COMMANDS SYNCED: {len(synced)}")
    except Exception as sync_error:
        print(sync_error)

    ensure_folder(GUILD_DATA_FOLDER)

    load_guild_configs()
    load_player_stats()
    load_heatmap()
    load_swear_jar()
    load_linked_players()
    load_shop()
    load_wallets()
    load_delivery_queue()

    await start_background_tasks()

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)
