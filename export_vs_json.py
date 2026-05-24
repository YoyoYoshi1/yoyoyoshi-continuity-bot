import json
import os
import statistics

# --- CONFIG ---
SOURCE_FILE = "vs_data.json"
OUTPUT_DIR = "public/mk64/vs/data"

MIN_MATCHES = 5

# --- LOAD ---
with open(SOURCE_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

matches = data.get("matches", [])
ratings = data.get("ratings", {})
player_stats = data.get("player_stats", {})

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- HELPERS ---
def adjusted_rating(player):
    base = ratings.get(player, 1000)
    games = player_stats.get(player, {}).get("matches", 0)
    confidence = games / (games + 50)
    return 1000 + (base - 1000) * confidence

def avg_points(player):
    stats = player_stats.get(player, {})
    matches_played = stats.get("matches", 0)
    points = stats.get("points", 0)

    if matches_played == 0:
        return 0

    return points / matches_played

# --- PLAYERS ---
players = []

for player in ratings:
    stats = player_stats.get(player, {})
    matches_played = stats.get("matches", 0)

    players.append({
        "player": player,
        "eligible": matches_played >= MIN_MATCHES,
        "elo": round(adjusted_rating(player)),
        "raw_elo": round(ratings[player]),
        "matches": matches_played,
        "points": stats.get("points", 0),
        "avg_points": round(avg_points(player), 2)
    })

players = sorted(players, key=lambda p: (-p["elo"], -p["matches"], p["player"]))

# --- LEADERBOARD ---
leaderboard = [p for p in players if p["eligible"]]

for i, player in enumerate(leaderboard):
    player["rank"] = i + 1

# --- MATCH LOG ---
exported_matches = []

for i, match in enumerate(matches, 1):
    placements = match.get("placements", [])
    scores = match.get("scores", {})

    exported_matches.append({
        "match_id": i,
        "message_id": match.get("message_id"),
        "created_at": match.get("created_at"),
        "jump_url": match.get("jump_url"),
        "author": match.get("author"),
        "placements": [
            {
                "place": place + 1,
                "player": player,
                "score": score
            }
            for place, (player, score) in enumerate(placements)
        ],
        "scores": scores
    })

# --- SUMMARY ---
eligible_elos = [p["elo"] for p in leaderboard]

summary = {
    "total_matches": len(matches),
    "total_players": len(players),
    "eligible_players": len(leaderboard),
    "min_matches": MIN_MATCHES,
    "median_elo": round(statistics.median(eligible_elos)) if eligible_elos else None
}

# --- WRITE ---
outputs = {
    "leaderboard.json": leaderboard,
    "players.json": players,
    "matches.json": exported_matches,
    "summary.json": summary
}

for filename, payload in outputs.items():
    path = os.path.join(OUTPUT_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote {path}")

print("VS JSON export complete.")