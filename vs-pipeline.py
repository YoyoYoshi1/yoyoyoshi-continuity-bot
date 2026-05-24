import discord
import re
from collections import defaultdict
import statistics

# --- CONFIG ---
TOKEN = "MTUwMTM4ODM0MDc5OTQ3NTg2Mg.G6x-Lj.5aqXwiho3bTT3tKFJ1KZhPaibCR3GiUkLBptWs"
CHANNEL_ID = 997416976051871854
K_FACTOR = 32
MIN_MATCHES = 5
MAX_SCORE = 60  # max realistic VS score

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# --- STORAGE ---
matches = []
ratings = defaultdict(lambda: 1000)

player_stats = defaultdict(lambda: {
    "matches": 0,
    "points": 0
})

# --- ALIASES ---
ALIASES = {
    "jesse": "spacedcowboy",
    "jessek": "spacedcowboy",
    "spaced": "spacedcowboy",

    "socal": "juggernaut",
    "coolex": "thecoolex",
    "fuzzy": "fuzz",

    "booth": "noakevbo",

    "palatus": "patalus",
    "pat": "patalus",

    "espagetti": "espaghetti",

    "yoyo": "yoyoyoshi",
    "bobby": "yoyoyoshi"
}

# --- NORMALIZE ---
def normalize_name(name):
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9_]', '', name)
    return ALIASES.get(name, name)

# --- PARSER ---
pattern = r"^@?([A-Za-z0-9_\-]{2,})\s+(\d+)$"

def parse_message(content):
    lines = content.split("\n")
    scores = {}

    for line in lines:
        line = line.strip()
        match = re.match(pattern, line)

        if match:
            name, score = match.groups()
            score = int(score)

            # skip bad scores but keep parsing
            if score > MAX_SCORE:
                print("⚠️ SKIPPING BAD SCORE:", name, score)
                continue

            clean = normalize_name(name)
            scores[clean] = score

    # need at least 2 valid players
    if len(scores) < 2:
        return None

    placements = sorted(scores.items(), key=lambda x: -x[1])

    return {
        "scores": scores,
        "placements": placements
    }

# --- ELO ---
def expected_score(r1, r2):
    return 1 / (1 + 10 ** ((r2 - r1) / 400))


def update_ratings(match):
    players = [p for p, _ in match["placements"]]

    if len(players) < 2:
        return

    for i, p1 in enumerate(players):
        r1 = ratings[p1]
        total_delta = 0

        for j, p2 in enumerate(players):
            if i == j:
                continue

            r2 = ratings[p2]
            actual = 1 if i < j else 0
            expected = expected_score(r1, r2)

            total_delta += (actual - expected)

        ratings[p1] += K_FACTOR * (total_delta / (len(players) - 1))

# --- WEIGHTED ELO ---
def adjusted_rating(player):
    base = ratings[player]
    games = player_stats[player]["matches"]

    confidence = games / (games + 50)

    return 1000 + (base - 1000) * confidence

# --- MAIN ---
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        print("ERROR: Channel not found")
        await client.close()
        return

    scanned = 0
    parsed = 0
    rejected = 0

    async for msg in channel.history(limit=None, oldest_first=True):
        scanned += 1

        match = parse_message(msg.content)

        if match:
            parsed += 1
            matches.append(match)

            update_ratings(match)

            for player, score in match["scores"].items():
                player_stats[player]["matches"] += 1
                player_stats[player]["points"] += score

        else:
            rejected += 1

    print(f"\nScanned: {scanned}")
    print(f"Parsed matches: {parsed}")
    print(f"Rejected messages: {rejected}")

    print("\n--- Leaderboard (VS Weighted Elo) ---")

    eligible = [
        p for p in ratings
        if player_stats[p]["matches"] >= MIN_MATCHES
    ]

    sorted_players = sorted(
        eligible,
        key=lambda p: -adjusted_rating(p)
    )

    for name in sorted_players:
        adj = adjusted_rating(name)
        raw = ratings[name]

        stats = player_stats[name]
        avg = stats["points"] / stats["matches"] if stats["matches"] else 0

        print(f"{name}: {round(adj)} (raw {round(raw)}) | matches: {stats['matches']} | avg pts: {round(avg,1)}")

    # --- MEDIAN ---
    values = [adjusted_rating(p) for p in sorted_players]
    if values:
        print(f"\nMedian Elo: {round(statistics.median(values))}")

    # --- OPTIONAL: SHOW SOME MATCHES ---
    print("\n--- Sample Matches (last 5) ---")
    for m in matches[-5:]:
        print(m["placements"])

    await client.close()


client.run(TOKEN)