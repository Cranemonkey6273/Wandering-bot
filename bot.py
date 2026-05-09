import re
from datetime import datetime


def extract_timestamp(name):
    match = re.search(
        r"_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.ADM$",
        name,
        re.IGNORECASE
    )

    if not match:
        return datetime.fromtimestamp(0)

    date_part = match.group(1)
    time_part = match.group(2).replace("-", ":")

    return datetime.fromisoformat(f"{date_part}T{time_part}")


def print_latest_adm_modified_at(api_response, server_id):
    """
    api_response = response.json() from Nitrado API
    This uses API data only. No DB.
    """

    entries = (
        api_response
        .get("data", {})
        .get("entries", [])
    )

    matching_logs = [
        entry for entry in entries
        if re.match(
            r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
            entry.get("name", ""),
            re.IGNORECASE
        )
    ]

    if not matching_logs:
        print(f"[LOG] No matching ADM logs found for {server_id}")
        return None

    matching_logs.sort(
        key=lambda entry: extract_timestamp(entry.get("name", "")),
        reverse=True
    )

    latest_log = matching_logs[0]

    print(f"[API] Latest ADM log for {server_id}: {latest_log.get('name')}")
    print(f"[API] modified_at from Nitrado API: {latest_log.get('modified_at')}")

    return latest_log.get("modified_at")
