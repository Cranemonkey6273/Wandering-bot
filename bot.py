# =========================================================
# NITRADO API
# =========================================================

def ping_latest_adm_log(config):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")
    nitrado_user = config.get("nitrado_user")

    if not token or not service_id or not nitrado_user:
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    search_paths = [

        # =================================================
        # METHOD 1 - ORIGINAL V1 METHOD
        # =================================================

        f"/games/{nitrado_user}/noftp/dayzxb/config/",

        # =================================================
        # METHOD 2
        # =================================================

        f"/games/{nitrado_user}/noftp/dayzxb/",

        # =================================================
        # METHOD 3
        # =================================================

        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/",

        # =================================================
        # METHOD 4
        # =================================================

        f"/games/{nitrado_user}/noftp/",

    ]

    try:

        for search_path in search_paths:

            print(f"[SEARCH PATH] {search_path}")

            url = (
                f"https://api.nitrado.net/services/{service_id}/gameservers/file_server/list"
            )

            params = {
                "dir": search_path,
                "search": "*DayZServer*",
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

            entries = data.get(
                "data",
                {}
            ).get(
                "entries",
                []
            )

            matching_logs = [
                entry
                for entry in entries
                if re.match(
                    r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
                    entry.get("name", ""),
                    re.IGNORECASE,
                )
            ]

            if not matching_logs:
                print("NO ADM LOGS FOUND HERE")
                continue

            matching_logs.sort(
                key=lambda x: x.get("modified_at", ""),
                reverse=True
            )

            latest = matching_logs[0]

            print(f"LATEST ADM FOUND: {latest.get('path')}")

            return latest

        print("ALL SEARCH METHODS FAILED")
        return None

    except Exception as error:
        print(error)
        return None