import time
from heatmap import record_kill
from economy import add_money

LOG_FILE = "server.log"

def process_logs():
    print("Tracking logs...")

    try:
        with open(LOG_FILE, "r") as f:
            f.seek(0, 2)

            while True:
                line = f.readline()
                if not line:
                    time.sleep(1)
                    continue

                if "killed" in line:
                    parts = line.split()

                    killer = parts[0]
                    location = parts[-1]

                    record_kill(location)
                    add_money(killer, 200)

    except FileNotFoundError:
        print("No log file found yet (this is normal for now)")
