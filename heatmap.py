from collections import defaultdict

heatmap = defaultdict(int)

def record_kill(location):
    heatmap[location] += 1

def get_hotspots():
    top = sorted(heatmap.items(), key=lambda x: x[1], reverse=True)[:5]

    if not top:
        return "No PvP data yet."

    return "\n".join([f"{k}: {v}" for k, v in top])
