import discord
import requests
import os
from supabase import create_client
from datetime import timedelta

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NITRADO_TOKEN = os.getenv("NITRADO_TOKEN")
SERVICE_ID = os.getenv("SERVICE_ID")

print("SERVICE_ID:", SERVICE_ID)

headers = {
    "Authorization": f"Bearer {NITRADO_TOKEN}"
}

LOG_FILE = "server.ADM"

# ================= INIT =================
client = discord.Client(intents=discord.Intents.default())
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

last_size = 0

# ================= DOWNLOAD LOG =================
def download_log():
    try:
        # STEP 1: LIST ROOT DIRECTORY
        url = f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list?dir=/games/ni12248929_2/ftproot/dayzxb/config"

        response = requests.get(url, headers=headers)
        res = response.json()

        if "data" not in res:
            print("❌ FILE LIST ERROR:", res)
            return False

        files = res["data"]["entries"]

        print("ROOT FILES:")
        for f in files:
            print(f["name"], "-", f["type"])

        return False  # stop here for now (debug only)

    except Exception as e:
        print("❌ ERROR:", e)
        return False

        files = res["data"]["entries"]

        print("FILES:", files)  # 👈 DEBUG (IMPORTANT)

        # STEP 2: FIND ADM FILES
        adm_files = []
adm_files = [
    f for f in files
    if f.get("path", "").endswith(".ADM") and "DayZServer" in f.get("name", "")
]

if not adm_files:
    print("❌ No ADM logs found")
    return False

# Sort by filename (newest timestamp in name)
adm_files.sort(key=lambda x: x["name"], reverse=True)

latest_file = adm_files[0]
latest_path = latest_file["path"]

print("✅ Latest ADM log found:", latest_path))

        # STEP 4: DOWNLOAD FILE
        download_url = f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/download?file={latest_path}"

        res = requests.get(
    f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list?dir=/dayzxb/config",
    headers=headers
).json()

        if "data" not in res:
            print("❌ DOWNLOAD ERROR:", res)
            return False

        file_url = res["data"]["token"]["url"]
        file_data = requests.get(file_url).text

        with open(LOG_FILE, "w") as f:
            f.write(file_data)

        print("✅ Log downloaded:", latest_path)
        return True

    except Exception as e:
        print("❌ LOG DOWNLOAD ERROR:", e)
        return False
# ================= PARSER =================
def parse_log():
    global last_size

    try:
        if not os.path.exists(LOG_FILE):
            return

        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(last_size)
            lines = f.readlines()
            last_size = f.tell()

        for line in lines:
            line = line.strip()
            print("📜", line)

            if "killed" in line:
                print("💀 Kill detected:", line)

            if "unconscious" in line:
                print("🧠 Unconscious event:", line)

            if "hit by" in line:
                print("⚔️ Hit event:", line)

    except Exception as e:
        print("❌ PARSE ERROR:", e)


# ================= LOOP =================
async def tracker_loop():
    await client.wait_until_ready()
    print("🚀 Tracker started")

    while not client.is_closed():
        success = download_log()

        if success:
            parse_log()

        await discord.utils.sleep_until(
            discord.utils.utcnow() + timedelta(seconds=15)
        )


# ================= DISCORD EVENTS =================
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    client.loop.create_task(tracker_loop())


# ================= START =================
client.run(DISCORD_TOKEN)
