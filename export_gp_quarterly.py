import json
import os
import statistics
from collections import defaultdict
from datetime import datetime

DATA_FILE = "gp_data.json"
OUTPUT_DIR = "public/mk64/gp/data/quarters"

K_FACTOR = 32
MIN_MATCHES = 3

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


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def quarter_key(dt):
    q = ((dt.month - 1) // 3) + 1
    return f"{dt.year}-Q{q}"


def expected_score(r1, r2):
    return 1 / (1 + 10 ** ((r2 - r1) / 400))


def adjusted_rating(rating, games):
    confidence = games / (games + 30)
    return 1000 + (rating - 1000) * confidence


def normalize_match(match):
    scores = {
        canon(player): score
        for player, score in match.get("scores", {}).items()
    }

    clean = dict(match)
    clean["scores"] = scores
    clean["players"] = list(scores.keys())

    return clean


def replay_elo(matches):
    ratings = defaultdict(lambda: 1000.0)
    stats = defaultdict(lambda: {
        "matches": 0,
        "wins": 0,
        "losses": 0,
        "ties": 0,
        "points_for": 0,
        "points_against": 0,
    })

    for match in matches:
        match = normalize_match(match)
        scores = match.get("scores", {})

        if len(scores) != 2:
            continue

        players = list(scores.keys())
        p1, p2 = players[0], players[1]
        s1, s2 = scores[p1], scores[p2]

        old_r1 = ratings[p1]
        old_r2 = ratings[p2]

        expected1 = expected_score(old_r1, old_r2)
        expected2 = expected_score(old_r2, old_r1)

        if s1 > s2:
            actual1, actual2 = 1, 0
            stats[p1]["wins"] += 1
            stats[p2]["losses"] += 1
        elif s2 > s1:
            actual1, actual2 = 0, 1
            stats[p2]["wins"] += 1
            stats[p1]["losses"] += 1
        else:
            actual1, actual2 = 0.5, 0.5
            stats[p1]["ties"] += 1
            stats[p2]["ties"] += 1

        ratings[p1] += K_FACTOR * (actual1 - expected1)
        ratings[p2] += K_FACTOR * (actual2 - expected2)

        stats[p1]["matches"] += 1
        stats[p2]["matches"] += 1
        stats[p1]["points_for"] += s1
        stats[p1]["points_against"] += s2
        stats[p2]["points_for"] += s2
        stats[p2]["points_against"] += s1

    players_out = []

    for player, s in stats.items():
        games = s["matches"]
        raw = ratings[player]
        weighted = adjusted_rating(raw, games)

        players_out.append({
            "player": player,
            "eligible": games >= MIN_MATCHES,
            "elo": round(weighted),
            "raw_elo": round(raw),
            "matches": games,
            "wins": s["wins"],
            "losses": s["losses"],
            "ties": s["ties"],
            "points_for": s["points_for"],
            "points_against": s["points_against"],
        })

    players_out.sort(key=lambda p: (-p["elo"], -p["matches"], p["player"]))

    eligible = [p for p in players_out if p["eligible"]]

    leaderboard = [
        {"rank": i + 1, **p}
        for i, p in enumerate(eligible)
    ]

    return leaderboard, players_out


def main():
    print("Running GP quarter-only export...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_matches = data.get("matches", data)
    matches = []

    for match in raw_matches:
        dt = parse_date(match.get("created_at"))
        if not dt:
            continue

        clean = normalize_match(match)
        clean["_parsed_date"] = dt
        clean["_quarter"] = quarter_key(dt)
        matches.append(clean)

    matches.sort(key=lambda m: m["_parsed_date"])

    quarters = sorted(set(m["_quarter"] for m in matches))

    print(f"Loaded {len(raw_matches)} raw GP matches")
    print(f"Using {len(matches)} dated GP matches")
    print(f"Found {len(quarters)} quarters")

    index = []

    for q in quarters:
        q_matches = [m for m in matches if m["_quarter"] == q]

        leaderboard, players = replay_elo(q_matches)
        ratings = [p["elo"] for p in leaderboard]

        output = {
            "quarter": q,
            "type": "quarter_only",
            "total_matches": len(q_matches),
            "eligible_players": len(leaderboard),
            "median_elo": round(statistics.median(ratings)) if ratings else None,
            "leaderboard": leaderboard,
            "players": players
        }

        filename = f"{q}.json"
        out_path = os.path.join(OUTPUT_DIR, filename)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        index.append({
            "quarter": q,
            "file": filename,
            "type": "quarter_only",
            "total_matches": len(q_matches),
            "eligible_players": len(leaderboard)
        })

        print(f"Wrote {out_path}")

    index_path = os.path.join(OUTPUT_DIR, "index.json")

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print(f"Wrote {index_path}")
    print("GP quarter-only Elo export complete.")


if __name__ == "__main__":
    main()