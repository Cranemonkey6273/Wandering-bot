import os
import re
import asyncio
import requests
import discord
from supabase import create_client

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

NITRADO_TOKEN = os.getenv("NITRADO_TOKEN")
SERVICE_ID = os.getenv("SERVICE_ID")

FTP_LOG_PATH = os.getenv("FTP_LOG_PATH")

headers = {
    "Authorization": f"Bearer {NITRADO_TOKEN}"
}

LOG_FILE = "server.ADM"

# ================= DISCORD =================

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ================= SUPABASE =================

supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= TRACKING =================

last_size = 0

# ================= DOWNLOAD LOG =================

def download_latest_log():

    try:

        res = requests.get(
            f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list",
            headers=headers,
            params={"dir": FTP_LOG_PATH}
        ).json()

        if "data" not in res:
            print("❌ FILE LIST ERROR:", res)
            return False

        files = res["data"]["entries"]

        adm_files = [
            f for f in files
            if f["name"].endswith(".ADM")
        ]

        if not adm_files:
            print("❌ No ADM logs found")
            return False

        # ✅ FIXED SORTING
        adm_files.sort(
            key=lambda x: x["modified_at"],
            reverse=True
        )

        latest = adm_files[0]

        log_path = latest["path"]

        print(f"✅ Latest ADM log found: {log_path}")

        download = requests.get(
            f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/download",
            headers=headers,
            params={"file": log_path}
        ).json()

        if "data" not in download:
            print("❌ DOWNLOAD ERROR:", download)
            return False

        download_url = download["data"]["token"]["url"]

        file_data = requests.get(download_url)

        with open(LOG_FILE, "wb") as f:
            f.write(file_data.content)

        print(f"✅ Log downloaded: {log_path}")

        return True

    except Exception as e:
        print("❌ DOWNLOAD EXCEPTION:", e)
        return False

# ================= PARSE LOG =================

async def parse_new_lines():

    global last_size

    channel = client.get_channel(CHANNEL_ID)

    if not channel:
        print("❌ Discord channel not found")
        return

    try:

        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:

            f.seek(last_size)

            new_lines = f.readlines()

            last_size = f.tell()

        for line in new_lines:

            line = line.strip()

            if not line:
                continue

            print("NEW:", line)

            # ================= PLAYER NAME =================

            player_match = re.search(r'Player "(.?)"', line)

            player = player_match.group(1) if player_match else "Unknown"

            # ================= COORDS =================

            pos_match = re.search(
                r'pos=<([\d.]+), ([\d.]+), ([\d.]+)>',
                line
            )

            location = "Unknown"

            if pos_match:

                x = pos_match.group(1)
                y = pos_match.group(2)

                location = f"X:{x} Y:{y}"

            # ================= KILLS =================

            if " killed " in line:

                players = re.findall(r'Player "(.?)"', line)

                if len(players) >= 2:

                    killer = players[0]
                    victim = players[1]

                    embed = discord.Embed(
                        title="💀 PLAYER KILL",
                        color=0xff0000
                    )

                    embed.add_field(
                        name="🔫 Killer",
                        value=killer,
                        inline=False
                    )

                    embed.add_field(
                        name="☠️ Victim",
                        value=victim,
                        inline=False
                    )

                    embed.add_field(
                        name="📍 Location",
                        value=location,
                        inline=False
                    )

                    embed.set_footer(
                        text="Wandering Bot Live Feed"
                    )

                    await channel.send(embed=embed)

            # ================= SUICIDES =================

            elif " committed suicide" in line:

                embed = discord.Embed(
                    title="☠️ SUICIDE",
                    color=0x555555
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                embed.add_field(
                    name="📍 Location",
                    value=location,
                    inline=False
                )

                embed.set_footer(
                    text="Wandering Bot Live Feed"
                )

                await channel.send(embed=embed)

            # ================= BUILDING =================

            elif "Built " in line:

                build_match = re.search(
                    r'Built (.?) on',
                    line
                )

                build = (
                    build_match.group(1)
                    if build_match
                    else "Structure"
                )

                embed = discord.Embed(
                    title="🛠️ BUILDING",
                    color=0xffaa00
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                embed.add_field(
                    name="🧱 Structure",
                    value=build,
                    inline=False
                )

                embed.add_field(
                    name="📍 Location",
                    value=location,
                    inline=False
                )

                embed.set_footer(
                    text="Wandering Bot Live Feed"
                )

                await channel.send(embed=embed)

            # ================= ITEM PLACEMENT =================

            elif " placed " in line:

                item_match = re.search(
                    r'placed (.?)<',
                    line
                )

                item = (
                    item_match.group(1)
                    if item_match
                    else "Item"
                )

                embed = discord.Embed(
                    title="📦 ITEM PLACED",
                    color=0x00aaff
                )

                embed.add_field(
                    name="👤 Player",
                    value=player,
                    inline=False
                )

                embed.add_field(
                    name="📦 Item",
                    value=item,
                    inline=False
                )

                embed.add_field(
                    name="📍 Location",
                    value=location,
                    inline=False
                )

                embed.set_footer(
                    text="Wandering Bot Live Feed"
                )

                await channel.send(embed=embed)

    except Exception as e:
        print("❌ PARSE ERROR:", e)

# ================= LOOP =================

async def tracker_loop():

    await client.wait_until_ready()

    print("🚀 Tracker started")

    while not client.is_closed():

        success = download_latest_log()

        if success:
            await parse_new_lines()

        await asyncio.sleep(10)

# ================= EVENTS =================

@client.event
async def on_ready():

    print(f"✅ Logged in as {client.user}")

    client.loop.create_task(tracker_loop())

# ================= START =================

client.run(DISCORD_TOKEN)