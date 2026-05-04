import re
import re

def track_logs():
    print("TRACKER STARTED")

    with open("server.ADM", "r") as f:
        f.seek(0, 2)

        while True:
            line = f.readline()
            if not line:
                continue

            if "committed suicide" in line:
                print("DEATH EVENT:", line)


def parse_line(line):
    death_pattern = r'Player "(.+?)".pos=<([\d.]+), ([\d.]+), ([\d.]+)>.died'
    match = re.search(death_pattern, line)

    if match:
        player = match.group(1)
        x = float(match.group(2))
        y = float(match.group(3))
        z = float(match.group(4))

        return {
            "type": "death",
            "player": player,
            "coords": (x, y, z)
        }

    return None

def parse_line(line):
    death_pattern = r'Player "(.+?)".pos=<([\d.]+), ([\d.]+), ([\d.]+)>.died'

    match = re.search(death_pattern, line)

    if match:
        player = match.group(1)
        x = float(match.group(2))
        y = float(match.group(3))
        z = float(match.group(4))

        return {
            "type": "death",
            "player": player,
            "coords": (x, y, z)
        }

    return None
