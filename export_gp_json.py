import json
import os
import statistics
from collections import defaultdict

SOURCE_FILE = "gp_data.json"
OUTPUT_DIR = "public/mk64/gp/data"

MIN_MATCHES = 3
K_FACTOR = 32

ALIASES = {
    "jesse": "spacedcowboy",
    "jessek": "spacedcowboy",
    "spaced": "spacedcowboy",
    "socal": "juggernaut",
    "coolex": "thecoolex",
    "fuzzy": "fuzz",
    "fuzzyfugs": "fuzz",
    "booth": "noakevbo",
    "palatus": "patalus",
    "pat": "patalus",
    "espagetti": "espaghetti",
    "yoyo": "yoyoyoshi",
    "bobby": "yoyoyoshi",
    "blazeup": "Martin",
    "fx": "fx64",
    "urbanoutlaw": "urban",
}


def canon(name):
    n = str(name).strip()
    return ALIASES.get(n.lower(), n)


def expected_score(r1, r2):
    return 1 / (1 + 10 ** ((r2 - r1) / 400))


def adjusted_rating(rating, games):
    confidence = games / (games + 30)
    return 1000 + (rating - 1000) * confidence


with open(SOURCE_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

matches = data.get("matches", [])

ratings = defaultdict(lambda: 1000.0)
stats = defaultdict(lambda: {
    "matches": 0,
    "wins": 0,
    "losses": 0,
    "ties": 0,
    "points_for": 0,
    "points_against": 0
})
exported_matches = []

os.makedirs(OUTPUT_DIR, exist_ok=True)

for i, match in enumerate(matches, 1):
    scores = {
        canon(player): score
        for player, score in match.get("scores", {}).items()
    }

    if len(scores) != 2:
        continue

    players = list(scores.keys())
    p1, p2 = players[0], players[1]
    s1, s2 = scores[p1], scores[p2]

    old_r1, old_r2 = ratings[p1], ratings[p2]
    expected1 = expected_score(old_r1, old_r2)
    expected2 = expected_score(old_r2, old_r1)

    if s1 > s2:
        actual1, actual2 = 1, 0
        winner = p1
    elif s2 > s1:
        actual1, actual2 = 0, 1
        winner = p2
    else:
        actual1, actual2 = 0.5, 0.5
        winner = None

    delta1 = K_FACTOR * (actual1 - expected1)
    delta2 = K_FACTOR * (actual2 - expected2)

    ratings[p1] += delta1
    ratings[p2] += delta2

    stats[p1]["matches"] += 1
    stats[p2]["matches"] += 1
    stats[p1]["points_for"] += s1
    stats[p1]["points_against"] += s2
    stats[p2]["points_for"] += s2
    stats[p2]["points_against"] += s1

    if winner == p1:
        stats[p1]["wins"] += 1
        stats[p2]["losses"] += 1
    elif winner == p2:
        stats[p2]["wins"] += 1
        stats[p1]["losses"] += 1
    else:
        stats[p1]["ties"] += 1
        stats[p2]["ties"] += 1

    exported_matches.append({
        "match_id": i,
        "message_id": match.get("message_id"),
        "created_at": match.get("created_at"),
        "jump_url": match.get("jump_url"),
        "author": match.get("author"),
        "players": [
            {
                "player": p1,
                "score": s1,
                "old_elo": round(old_r1, 1),
                "new_elo": round(ratings[p1], 1),
                "delta": round(delta1, 1)
            },
            {
                "player": p2,
                "score": s2,
                "old_elo": round(old_r2, 1),
                "new_elo": round(ratings[p2], 1),
                "delta": round(delta2, 1)
            }
        ],
        "winner": winner
    })

players = []

for player in ratings:
    games = stats[player]["matches"]
    raw = ratings[player]

    players.append({
        "player": player,
        "eligible": games >= MIN_MATCHES,
        "elo": round(adjusted_rating(raw, games)),
        "raw_elo": round(raw),
        "matches": games,
        "wins": stats[player]["wins"],
        "losses": stats[player]["losses"],
        "ties": stats[player]["ties"],
        "points_for": stats[player]["points_for"],
        "points_against": stats[player]["points_against"],
    })

players.sort(key=lambda p: (-p["elo"], -p["matches"], p["player"]))

leaderboard = [p for p in players if p["eligible"]]

for i, player in enumerate(leaderboard):
    player["rank"] = i + 1

eligible_elos = [p["elo"] for p in leaderboard]

summary = {
    "total_matches": len(exported_matches),
    "total_players": len(players),
    "eligible_players": len(leaderboard),
    "min_matches": MIN_MATCHES,
    "median_elo": round(statistics.median(eligible_elos)) if eligible_elos else None
}

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

print("GP JSON export complete.")