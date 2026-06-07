import json
import os
import statistics
from collections import defaultdict
from datetime import datetime

DATA_FILE = "vs_data.json"
OUTPUT_DIR = "public/mk64/vs/data/quarters"

K_FACTOR = 32
MIN_MATCHES = 5

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
    confidence = games / (games + 50)
    return 1000 + (rating - 1000) * confidence


def normalize_match(match):
    old_placements = match.get("placements", [])
    old_scores = match.get("scores", {})

    scores = defaultdict(int)

    for player, score in old_scores.items():
        scores[canon(player)] += score

    placements = []
    seen = set()

    for player, score in old_placements:
        player = canon(player)

        if player in seen:
            continue

        seen.add(player)
        placements.append((player, scores.get(player, score)))

    placements.sort(key=lambda x: -x[1])

    clean = dict(match)
    clean["scores"] = dict(scores)
    clean["placements"] = placements

    return clean


def replay_elo(matches):
    ratings = defaultdict(lambda: 1000.0)
    stats = defaultdict(lambda: {"matches": 0, "points": 0})

    for match in matches:
        match = normalize_match(match)

        placements = match.get("placements", [])
        scores = match.get("scores", {})
        players = [p for p, _ in placements]

        if len(players) < 2:
            continue

        old_ratings = {p: ratings[p] for p in players}
        deltas = defaultdict(float)

        for i, p1 in enumerate(players):
            total_delta = 0

            for j, p2 in enumerate(players):
                if i == j:
                    continue

                actual = 1 if i < j else 0
                expected = expected_score(old_ratings[p1], old_ratings[p2])
                total_delta += actual - expected

            deltas[p1] = K_FACTOR * (total_delta / (len(players) - 1))

        for player, delta in deltas.items():
            ratings[player] += delta

        for player in players:
            stats[player]["matches"] += 1
            stats[player]["points"] += scores.get(player, 0)

    players_out = []

    for player, s in stats.items():
        games = s["matches"]
        points = s["points"]
        raw = ratings[player]
        weighted = adjusted_rating(raw, games)

        players_out.append({
            "player": player,
            "eligible": games >= MIN_MATCHES,
            "elo": round(weighted),
            "raw_elo": round(raw),
            "matches": games,
            "points": points,
            "avg_points": round(points / games, 2) if games else 0
        })

    players_out.sort(key=lambda p: (-p["elo"], -p["matches"], p["player"]))

    eligible = [p for p in players_out if p["eligible"]]

    leaderboard = [
        {"rank": i + 1, **p}
        for i, p in enumerate(eligible)
    ]

    return leaderboard, players_out


def main():
    print("Running VS quarter-only export...")

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

    print(f"Loaded {len(raw_matches)} raw matches")
    print(f"Using {len(matches)} dated matches")
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
    print("VS quarter-only Elo export complete.")


if __name__ == "__main__":
    main()