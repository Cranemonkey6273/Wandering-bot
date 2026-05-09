import re
import requests
from datetime import datetime


# =========================
# FILL THESE IN
# =========================

NITRADO_TOKEN = "PASTE_TOKEN_HERE"

SERVICE_ID = "12768216"        # Goes in API URL
NITRADO_USER = "ni12248929_1"  # Goes after /games/
PLATFORM = "dayzxb"            # Goes after /noftp/  example: dayzxb or dayzps


# =========================
# DO NOT TOUCH BELOW
# =========================

def extract_timestamp(filename):
    """
    Reads timestamp from filename like:
    DayZServer_X1_x64_2026-05-09_22-30-15.ADM
    """

    match = re.search(
        r"_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.ADM$",
        filename,
        re.IGNORECASE
    )

    if not match:
        return datetime.fromtimestamp(0)

    date_part = match.group(1)
    time_part = match.group(2).replace("-", ":")

    return datetime.fromisoformat(f"{date_part}T{time_part}")


def ping_latest_adm_log():
    url = f"https://api.nitrado.net/services/{SERVICE_ID}/gameservers/file_server/list"

    headers = {
        "Authorization": f"Bearer {NITRADO_TOKEN}",
        "Accept": "application/json"
    }

    params = {
        "dir": f"/games/{NITRADO_USER}/noftp/{PLATFORM}/config/",
        "search": "*DayZServer*"
    }

    print("[PING] Calling Nitrado API")
    print("[PING] URL:", url)
    print("[PING] DIR:", params["dir"])
    print("[PING] SEARCH:", params["search"])
    print("")

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

        print("[PING] HTTP Status:", response.status_code)

        if response.status_code == 401:
            print("[ERROR] 401 Unauthorized - token is wrong or expired")
            return None
        if response.status_code != 200:
            print("[ERROR] Bad HTTP status from Nitrado")
            print(response.text)
            return None

        data = response.json()

        if data.get("status") != "success":
            print("[ERROR] Nitrado returned non-success response")
            print(data)
            return None

        entries = data.get("data", {}).get("entries", [])

        if not entries:
            print("[LOG] API returned no files")
            return None

        matching_logs = [
            entry for entry in entries
            if re.match(
                r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
                entry.get("name", ""),
                re.IGNORECASE
            )
        ]

        if not matching_logs:
            print("[LOG] No matching ADM logs found")
            print("")
            print("[DEBUG] Files returned by API:")

            for entry in entries:
                print(" -", entry.get("name"))

            return None

        matching_logs.sort(
            key=lambda entry: extract_timestamp(entry.get("name", "")),
            reverse=True
        )

        latest_log = matching_logs[0]

        print("")
        print("========== LATEST ADM LOG ==========")
        print("Name:", latest_log.get("name"))
        print("Path:", latest_log.get("path"))
        print("API modified_at:", latest_log.get("modified_at"))
        print("Size:", latest_log.get("size"))
        print("====================================")
        print("")

        return latest_log
    except requests.Timeout:
        print("[ERROR] Request timed out")
        return None

    except Exception as error:
        print("[ERROR] Something failed")
        print(error)
        return None


if __name__ == "__main__":
    latest_log = ping_latest_adm_log()

    if latest_log:
        print("FINAL RESULT:")
        print("filename:", latest_log.get("name"))
        print("modified_at:", latest_log.get("modified_at"))
    else:
        print("FINAL RESULT:")
        print("None")
