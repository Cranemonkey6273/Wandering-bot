from ftplib import FTP
import re
from config import FTP_HOST, FTP_USER, FTP_PASS, FTP_LOG_PATH

last_position = 0
current_file = None


---------- FIND LATEST ADM FILE ----------
def get_latest_adm(ftp):
    files = ftp.nlst(FTP_LOG_PATH)
    adm_files = [f for f in files if f.endswith(".ADM")]

    if not adm_files:
        return None

    # newest file (sorted by name timestamp)
    return sorted(adm_files)[-1]


---------- FETCH NEW LINES ----------
def fetch_new_lines():
    global last_position, current_file

    ftp = FTP(FTP_HOST)
    ftp.login(FTP_USER, FTP_PASS)

    latest = get_latest_adm(ftp)

    # detect file change (server restart)
    if latest != current_file:
        print(f"🔄 Switched to new ADM file: {latest}")
        current_file = latest
        last_position = 0

    if not current_file:
        ftp.quit()
        return []

    size = ftp.size(current_file)

    # first run → skip old logs
    if last_position == 0:
        last_position = size
        ftp.quit()
        return []

    # file reset
    if size < last_position:
        last_position = 0
        ftp.quit()
        return []

    chunks = []

    def collect(data):
        chunks.append(data)

    ftp.retrbinary(f"RETR {current_file}", collect)
    ftp.quit()

    text = b"".join(chunks).decode(errors="ignore")

    new_text = text[last_position:]
    last_position = size

    return new_text.splitlines()


---------- PARSER ----------
def parse_event(line):
    line_lower = line.lower()

    # get player names
    players = re.findall(r'Player "(.?)"', line)

    # ---------- KILL ----------
    if "killed" in line_lower:
        if len(players) >= 2:
            killer = players[0]
            victim = players[1]
            return f"💀 {killer} killed {victim}"

        return f"💀 {line}"

    # ---------- DAMAGE ----------
    if "hit" in line_lower:
        return f"⚔️ {line}"

    # ---------- BUILD ----------
    if "built" in line_lower:
        if players:
            return f"🏗 {players[0]} built structure"

    # ---------- ITEM PLACED ----------
    if "placed" in line_lower:
        if players:
            item_match = re.search(r'placed (.?)<', line)
            item = item_match.group(1) if item_match else "item"
            return f"📦 {players[0]} placed {item}"

    return None
