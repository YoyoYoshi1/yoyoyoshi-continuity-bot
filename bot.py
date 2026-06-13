print("BOT FILE TEST — NEW VERSION LOADED")

import os
import re
import json
import random
import requests
import discord
import statistics
import sqlite3
import html

from bs4 import BeautifulSoup
from discord import app_commands
from dotenv import load_dotenv
from urllib.parse import urljoin
from collections import defaultdict
from datetime import datetime, timezone
import threading

from flask import Flask, jsonify, send_file

from streams import start_stream_tracker

# -----------------------------
# Web server
# -----------------------------

app = Flask(__name__)

LIVE_STREAMS_FILE = "live_streams.json"


@app.route("/")
def home():
    return "YoyoYoshi Bot is running."


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "updated_at": datetime.now(timezone.utc).isoformat()
    })


@app.route("/live_streams.json")
def live_streams():
    if os.path.exists(LIVE_STREAMS_FILE):
        return send_file(
            LIVE_STREAMS_FILE,
            mimetype="application/json"
        )

    return jsonify({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "streams": []
    })


def run_web_server():
    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )

# -----------------------------
# Environment / startup config
# -----------------------------

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_RAW = os.getenv("DISCORD_GUILD_ID")

MK64_VS_CHANNEL_ID_RAW = os.getenv(
    "MK64_VS_CHANNEL_ID",
    "997416976051871854"
)

NSO_4P_TOURNEY_CHANNEL_ID_RAW = os.getenv(
    "NSO_4P_TOURNEY_CHANNEL_ID",
    "1122249513487310928"
)

GP_CHANNEL_ID_RAWS = {
    "GRAND_PRIX_SCORES_CHANNEL_ID": os.getenv(
        "GRAND_PRIX_SCORES_CHANNEL_ID",
        "1012093550449655878"
    ),
    "ELO_GP_MATCH_RESULTS_CHANNEL_ID": os.getenv(
        "ELO_GP_MATCH_RESULTS_CHANNEL_ID",
        "1099432653993820322"
    ),
    "TUK_2_DISCUSSION_CHANNEL_ID": os.getenv(
        "TUK_2_DISCUSSION_CHANNEL_ID",
        "1290023289946636339"
    ),
    "GP_LEAGUE_CHANNEL_ID": os.getenv(
        "GP_LEAGUE_CHANNEL_ID",
        "1040839082248503358"
    ),
    "TUP_TOURNAMENT_CHANNEL_ID": os.getenv(
        "TUP_TOURNAMENT_CHANNEL_ID",
        "1121631676230029332"
    ),
    "TUK_TOURNAMENT_CHANNEL_ID": os.getenv(
        "TUK_TOURNAMENT_CHANNEL_ID",
        "1076081113946128385"
    ),
}

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env")

if not GUILD_ID_RAW:
    raise RuntimeError("Missing DISCORD_GUILD_ID in .env")

GUILD_ID = int(GUILD_ID_RAW)

MK64_VS_CHANNEL_ID = int(MK64_VS_CHANNEL_ID_RAW)
NSO_4P_TOURNEY_CHANNEL_ID = int(NSO_4P_TOURNEY_CHANNEL_ID_RAW)

VS_RESULT_CHANNEL_IDS = {
    MK64_VS_CHANNEL_ID,
    NSO_4P_TOURNEY_CHANNEL_ID,
}

GP_RESULT_CHANNEL_IDS = {
    int(value)
    for value in GP_CHANNEL_ID_RAWS.values()
    if value
}

# Import this channel first; it is treated as the best historical GP source.
ELO_GP_MATCH_RESULTS_CHANNEL_ID = int(
    GP_CHANNEL_ID_RAWS["ELO_GP_MATCH_RESULTS_CHANNEL_ID"]
)

GP_SUPPLEMENTAL_CHANNEL_IDS = [
    channel_id
    for channel_id in GP_RESULT_CHANNEL_IDS
    if channel_id != ELO_GP_MATCH_RESULTS_CHANNEL_ID
]

MY_GUILD = discord.Object(id=GUILD_ID)


# -----------------------------
# MK64 VS parser config/storage
# -----------------------------

K_FACTOR = 32
MIN_MATCHES = 5
MAX_SCORE = 60
DATA_FILE = "vs_data.json"
GP_DATA_FILE = "gp_data.json"
STATS_DB_FILE = "discord_stats.sqlite3"

GP_K_FACTOR = 32
GP_MIN_MATCHES = 3
GP_MAX_SCORE = 160

CONTINUITY_EXPORT_DIR = "public_mk64_continuity"

PLAYER_NOTES = {
    "gumby": {"display_name": "Gumby", "roles": ["Founder", "administrator", "organizer", "recruiter"], "summary": "Co-founded the MK64 Switch Discord in July 2022 and helped build the community through recruitment, organization, events, and competition.", "links": ["https://awrev.com/mk64/history.php"]},
    "spacedcowboy": {"display_name": "SpacedCowboy", "roles": ["Co-founder", "competitor", "CampKart champion"], "summary": "Co-founded the MK64 Switch Discord and became one of the community's major early competitive figures.", "links": ["https://awrev.com/mk64/campkart2025.php"]},
    "yoyoyoshi": {"display_name": "YoyoYoshi", "roles": ["Co-founder", "administrator", "webmaster", "broadcaster", "community historian"], "summary": "Co-founded the MK64 Switch Discord and maintains the MK64 Switch website, rankings, records, broadcasts, and community documentation.", "links": ["https://awrev.com/mk64/", "https://www.youtube.com/@YoyoYoshi1"]},
    "gg": {"display_name": "GG", "roles": ["Co-founder", "administrator", "competitor"], "summary": "Co-founded the MK64 Switch Discord and has been a major competitor and community figure.", "links": ["https://awrev.com/mk64/history.php"]},
    "patalus": {"display_name": "Patalus", "roles": ["Administrator", "competitor", "tournament champion"], "summary": "Joined the admin/mod team in 2023 and became a major tournament and multiplayer competitor.", "links": ["https://awrev.com/mk64/history.php"]}
}

COMMUNITY_MILESTONES = [
    {"date": "2022-07-15", "title": "MK64 Switch Discord founded", "summary": "Gumby launched the MK64 Switch Discord with SpacedCowboy, YoyoYoshi, and GG to organize Mario Kart 64 Nintendo Switch Online multiplayer matches.", "tags": ["founding", "discord", "community"]},
    {"date": "2023-04-22", "title": "2P GP Elo rankings introduced", "summary": "The community introduced Elo rankings for 2P Grand Prix competition, helping turn match results into long-term competitive records.", "tags": ["gp", "elo", "rankings"]},
    {"date": "2024-09-06", "title": "CampKart 1 begins", "summary": "CampKart 1 became the first major in-person championship benchmark for the MK64 Switch community.", "tags": ["campkart", "in-person", "tournament"]},
    {"date": "2026-04-25", "title": "MK64 Switch Hub launches", "summary": "YoyoYoshi launched the MK64 Switch Multiplayer Hub as a centralized website for tournament history, rankings, media, records, events, and resources.", "tags": ["website", "history", "rankings"]},
    {"date": "2026-06-12", "title": "MK64 Switch website moves to awRev", "summary": "The MK64 Switch website moved to awRev.com/mk64 as a stronger permanent home for rankings, player pages, match history, tournament coverage, media, and community documentation.", "tags": ["awrev", "migration", "institution"]}
]

matches = []
ratings = defaultdict(lambda: 1000)
player_stats = defaultdict(lambda: {
    "matches": 0,
    "points": 0
})
last_message_id = None
processed_message_ids = set()

gp_matches = []
gp_ratings = defaultdict(lambda: 1000)
gp_player_stats = defaultdict(lambda: {
    "matches": 0,
    "wins": 0,
    "losses": 0,
    "ties": 0,
    "points_for": 0,
    "points_against": 0
})
processed_gp_message_ids = set()
gp_match_keys = set()

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


def normalize_name(name):
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9_]", "", name)
    return ALIASES.get(name, name)


VS_MENTION_PATTERN = re.compile(r"<@!?(\d+)>")
INLINE_SCORE_PATTERN = re.compile(
    r"@([^@\n\r]+?)\s+(\d{1,2})(?=\s|$)",
    re.IGNORECASE
)
LINE_SCORE_PATTERN = re.compile(
    r"^@?([A-Za-z0-9_\-]{2,32})\s+(\d{1,2})$",
    re.IGNORECASE
)


def display_name_for_mention(user):
    if hasattr(user, "display_name") and user.display_name:
        return user.display_name
    if hasattr(user, "global_name") and user.global_name:
        return user.global_name
    return getattr(user, "name", str(user))


def replace_discord_mentions(content, message=None):
    if message is None:
        return content

    mention_names = {
        str(user.id): display_name_for_mention(user)
        for user in getattr(message, "mentions", [])
    }

    def repl(match):
        user_id = match.group(1)
        name = mention_names.get(user_id)

        if not name:
            return match.group(0)

        return f"@{name}"

    return VS_MENTION_PATTERN.sub(repl, content)


def clean_score_name(name):
    name = name.strip()
    name = re.sub(r"\s+", " ", name)

    aka_match = re.search(r"\ba\s*/?\s*k\s*/?\s*a\b\s+(.+)$", name, re.IGNORECASE)
    if aka_match:
        name = aka_match.group(1).strip()

    name = re.sub(r"\[[^\]]*\]", "", name)
    name = re.sub(r"\([^)]*\)", "", name)
    name = name.strip(" ,:;|-")

    parts = name.split()
    if len(parts) > 1:
        name = parts[-1]

    return normalize_name(name)


def parse_vs_message(content, message=None):
    text = content.replace("\n", " ")

    if "ranked" not in text.lower():
        return None

    mention_pattern = re.compile(
        r"<@!?(?P<id>\d+)>\s*(?P<score>\d{1,2})"
    )

    mention_names = {}

    if message:
        for user in message.mentions:
            mention_names[str(user.id)] = normalize_name(user.display_name)

    scores = {}

    for match in mention_pattern.finditer(text):
        user_id = match.group("id")
        score = int(match.group("score"))

        if score > MAX_SCORE:
            return None

        player_name = mention_names.get(
            user_id,
            f"user_{user_id}"
        )

        if player_name in scores:
            return None

        scores[player_name] = score

    if len(scores) not in (3, 4):
        return None

    placements = sorted(
        scores.items(),
        key=lambda x: -x[1]
    )

    return {
        "scores": scores,
        "placements": placements
    }


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
            total_delta += actual - expected

        ratings[p1] += K_FACTOR * (total_delta / (len(players) - 1))


def adjusted_rating(player):
    base = ratings[player]
    games = player_stats[player]["matches"]
    confidence = games / (games + 50)
    return 1000 + (base - 1000) * confidence


def attach_metadata(match, message):
    match["message_id"] = message.id
    match["created_at"] = message.created_at.isoformat()
    match["jump_url"] = message.jump_url
    match["author"] = str(message.author)
    return match


def save_vs_data():
    data = {
        "matches": matches,
        "ratings": dict(ratings),
        "player_stats": dict(player_stats),
        "last_message_id": last_message_id,
        "processed_message_ids": sorted(processed_message_ids)
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_vs_data():
    global matches, last_message_id, processed_message_ids

    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    matches = data.get("matches", [])
    last_message_id = data.get("last_message_id")
    processed_message_ids = set(data.get("processed_message_ids", []))

    for match in matches:
        msg_id = match.get("message_id")
        if msg_id:
            processed_message_ids.add(str(msg_id))

    for player, rating in data.get("ratings", {}).items():
        ratings[player] = rating

    for player, stats in data.get("player_stats", {}).items():
        player_stats[player] = stats


def record_vs_match(match, message=None, message_id=None, save=True):
    global last_message_id

    actual_message_id = None

    if message is not None:
        actual_message_id = str(message.id)

        if actual_message_id in processed_message_ids:
            return False

        match = attach_metadata(match, message)
        last_message_id = message.id
    elif message_id is not None:
        actual_message_id = str(message_id)

        if actual_message_id in processed_message_ids:
            return False

        match["message_id"] = message_id
        last_message_id = message_id

    matches.append(match)
    update_ratings(match)

    for player, score in match["scores"].items():
        player_stats[player]["matches"] += 1
        player_stats[player]["points"] += score

    if actual_message_id:
        processed_message_ids.add(actual_message_id)

    if save:
        save_vs_data()

    return True


def mark_vs_processed(message_id, save=True):
    global last_message_id

    last_message_id = message_id
    processed_message_ids.add(str(message_id))

    if save:
        save_vs_data()


def get_vs_leaderboard():
    eligible = [
        p for p in ratings
        if player_stats[p]["matches"] >= MIN_MATCHES
    ]

    return sorted(
        eligible,
        key=lambda p: -adjusted_rating(p)
    )


def format_vs_leaderboard(limit=10):
    sorted_players = get_vs_leaderboard()[:limit]

    if not sorted_players:
        return "No eligible players yet."

    lines = ["**MK64 VS Leaderboard**"]

    for i, name in enumerate(sorted_players, 1):
        adj = adjusted_rating(name)
        raw = ratings[name]
        stats = player_stats[name]
        avg = stats["points"] / stats["matches"] if stats["matches"] else 0

        lines.append(
            f"{i}. **{name}**: {round(adj)} "
            f"(raw {round(raw)}) | matches: {stats['matches']} | avg pts: {avg:.1f}"
        )

    values = [adjusted_rating(p) for p in sorted_players]

    if values:
        lines.append(f"\nMedian Elo: {round(statistics.median(values))}")

    return "\n".join(lines)


def format_vs_rank(name):
    clean = normalize_name(name)

    if clean not in ratings:
        return f"No data found for `{clean}`."

    stats = player_stats[clean]
    avg = stats["points"] / stats["matches"] if stats["matches"] else 0

    return (
        f"**{clean}**\n"
        f"Elo: {round(adjusted_rating(clean))} "
        f"(raw {round(ratings[clean])})\n"
        f"Matches: {stats['matches']}\n"
        f"Average points: {avg:.1f}"
    )


def format_vs_stats():
    return (
        f"Stored matches: {len(matches)}\n"
        f"Tracked players: {len(player_stats)}\n"
        f"Last processed message ID: {last_message_id}"
    )


# -----------------------------
# MK64 GP parser config/storage
# -----------------------------

def parse_score_lines(content, message=None, max_score=160):
    text = replace_discord_mentions(content, message)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    scores = {}

    for line in lines:
        line = re.sub(r"^P[1-4]\s*:\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"^(gp|grand prix|tournament|round|match)\s*[:#-]?\s*", "", line, flags=re.IGNORECASE)

        match = re.match(r"^@?(.+?)\s+(\d{1,3})$", line)

        if not match:
            continue

        raw_name = match.group(1)
        score = int(match.group(2))

        if score > max_score:
            return None

        clean = clean_score_name(raw_name)

        if not clean:
            continue

        if clean in scores:
            return None

        scores[clean] = score

    return scores


def clean_gp_elo_name(name):
    name = name.strip()
    name = name.replace("\\", "")
    name = re.sub(r"#\d{1,5}$", "", name)
    name = name.strip(" .,:;|-_")
    return clean_score_name(name)


def parse_gp_elo_player_value(value):
    """
    Parse old GP Elo bot field values such as:
    \Cheech\#4947 (1259.1, +7.0)
    justice90.#0 (1201.5, -7.0)
    """
    if not value:
        return None

    text = value.strip()
    text = re.sub(r"\s+", " ", text)

    match = re.search(
        r"(?P<name>.+?)\s*\((?P<rating>\d+(?:\.\d+)?),\s*(?P<delta>[+-]\d+(?:\.\d+)?)\)",
        text
    )

    if not match:
        return None

    player = clean_gp_elo_name(match.group("name"))

    if not player:
        return None

    return {
        "player": player,
        "rating_after": float(match.group("rating")),
        "delta": float(match.group("delta"))
    }


def parse_gp_elo_ledger_message(message):
    """
    Parse old GP Elo bot embed messages. These are not score reports;
    they are authoritative Elo ledger entries with Win/Loss fields.
    """
    if message is None:
        return None

    for embed in getattr(message, "embeds", []):
        title = (embed.title or "").lower().strip()
        description = embed.description or ""

        fields = list(getattr(embed, "fields", []))

        # Most old GP bot entries use title "gp" and fields named Win/Loss.
        win_field = None
        loss_field = None

        for field in fields:
            field_name = (field.name or "").lower()

            if "win" in field_name:
                win_field = field
            elif "loss" in field_name or "lose" in field_name:
                loss_field = field

        # Fallback for unusual embeds: scan description for Win/Loss blocks.
        if not win_field or not loss_field:
            continue

        winner_info = parse_gp_elo_player_value(win_field.value)
        loser_info = parse_gp_elo_player_value(loss_field.value)

        if not winner_info or not loser_info:
            continue

        winner = winner_info["player"]
        loser = loser_info["player"]

        if winner == loser:
            continue

        return {
            "source_type": "gp_elo_ledger",
            "scores": {winner: 1, loser: 0},
            "players": [winner, loser],
            "winner": winner,
            "winner_rating_after": winner_info["rating_after"],
            "loser_rating_after": loser_info["rating_after"],
            "winner_delta": winner_info["delta"],
            "loser_delta": loser_info["delta"]
        }

    return None


def parse_gp_message(content, message=None):
    ledger_match = parse_gp_elo_ledger_message(message)

    if ledger_match:
        return ledger_match

    scores = parse_score_lines(content, message, GP_MAX_SCORE)

    if not scores or len(scores) != 2:
        return None

    players = list(scores.keys())
    p1, p2 = players[0], players[1]
    s1, s2 = scores[p1], scores[p2]

    if s1 > s2:
        winner = p1
    elif s2 > s1:
        winner = p2
    else:
        winner = None

    return {
        "source_type": "gp_score_report",
        "scores": scores,
        "players": [p1, p2],
        "winner": winner
    }


def update_gp_ratings(match):
    if match.get("source_type") == "gp_elo_ledger":
        winner = match.get("winner")
        players = match.get("players", [])
        loser = next((p for p in players if p != winner), None)

        if winner and loser:
            gp_ratings[winner] = float(match["winner_rating_after"])
            gp_ratings[loser] = float(match["loser_rating_after"])

        return

    p1, p2 = match["players"]
    s1 = match["scores"][p1]
    s2 = match["scores"][p2]

    r1 = gp_ratings[p1]
    r2 = gp_ratings[p2]

    expected1 = expected_score(r1, r2)
    expected2 = expected_score(r2, r1)

    if s1 > s2:
        actual1, actual2 = 1, 0
    elif s2 > s1:
        actual1, actual2 = 0, 1
    else:
        actual1, actual2 = 0.5, 0.5

    gp_ratings[p1] += GP_K_FACTOR * (actual1 - expected1)
    gp_ratings[p2] += GP_K_FACTOR * (actual2 - expected2)


def gp_match_key(match):
    """
    Dedupe by date + players.

    The primary #elo-gp-match-results channel contains Elo ledger entries,
    while supplemental channels may contain original score reports. Date + players
    keeps those from double-counting the same match when both sources exist.
    """
    players = tuple(sorted(match.get("players", [])))
    created_at = match.get("created_at", "")
    match_date = created_at[:10] if created_at else "unknown-date"

    return (match_date, players)


def rebuild_gp_match_keys():
    global gp_match_keys
    gp_match_keys = set()

    for match in gp_matches:
        gp_match_keys.add(gp_match_key(match))


def reset_gp_state_for_rebuild():
    """
    GP is rebuilt from Discord history so source priority can be enforced.
    VS is left alone because its existing parser/data flow is already stable.
    """
    global gp_matches, gp_ratings, gp_player_stats, processed_gp_message_ids, gp_match_keys

    gp_matches = []
    gp_ratings = defaultdict(lambda: 1000)
    gp_player_stats = defaultdict(lambda: {
        "matches": 0,
        "wins": 0,
        "losses": 0,
        "ties": 0,
        "points_for": 0,
        "points_against": 0,
    })
    processed_gp_message_ids = set()
    gp_match_keys = set()


def save_gp_data():
    data = {
        "matches": gp_matches,
        "ratings": dict(gp_ratings),
        "player_stats": dict(gp_player_stats),
        "processed_message_ids": sorted(processed_gp_message_ids),
        "match_keys": [str(key) for key in sorted(gp_match_keys, key=str)]
    }

    with open(GP_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_gp_data():
    global gp_matches, processed_gp_message_ids

    if not os.path.exists(GP_DATA_FILE):
        return

    with open(GP_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    gp_matches = data.get("matches", [])
    processed_gp_message_ids = set(data.get("processed_message_ids", []))

    for player, rating in data.get("ratings", {}).items():
        gp_ratings[player] = rating

    for player, stats in data.get("player_stats", {}).items():
        gp_player_stats[player] = stats

    rebuild_gp_match_keys()


def record_gp_match(match, message=None, save=True, allow_duplicate_key=False):
    actual_message_id = None

    if message is not None:
        actual_message_id = str(message.id)

        if actual_message_id in processed_gp_message_ids:
            return False

        match = attach_metadata(match, message)

    key = gp_match_key(match)

    if not allow_duplicate_key and key in gp_match_keys:
        if actual_message_id:
            processed_gp_message_ids.add(actual_message_id)
        return False

    gp_matches.append(match)
    gp_match_keys.add(key)
    update_gp_ratings(match)

    p1, p2 = match["players"]
    s1 = match["scores"][p1]
    s2 = match["scores"][p2]

    gp_player_stats[p1]["matches"] += 1
    gp_player_stats[p2]["matches"] += 1

    # Real GP score reports use actual points. Old Elo ledger entries do not,
    # so avoid mixing fake 1-0 values into points totals.
    if match.get("source_type") != "gp_elo_ledger":
        gp_player_stats[p1]["points_for"] += s1
        gp_player_stats[p1]["points_against"] += s2
        gp_player_stats[p2]["points_for"] += s2
        gp_player_stats[p2]["points_against"] += s1

    if s1 > s2:
        gp_player_stats[p1]["wins"] += 1
        gp_player_stats[p2]["losses"] += 1
    elif s2 > s1:
        gp_player_stats[p2]["wins"] += 1
        gp_player_stats[p1]["losses"] += 1
    else:
        gp_player_stats[p1]["ties"] += 1
        gp_player_stats[p2]["ties"] += 1

    if actual_message_id:
        processed_gp_message_ids.add(actual_message_id)

    if save:
        save_gp_data()

    return True


def adjusted_gp_rating(player):
    base = gp_ratings[player]
    games = gp_player_stats[player]["matches"]
    confidence = games / (games + 30)
    return 1000 + (base - 1000) * confidence


def format_gp_leaderboard(limit=10):
    eligible = [
        p for p in gp_ratings
        if gp_player_stats[p]["matches"] >= GP_MIN_MATCHES
    ]

    sorted_players = sorted(
        eligible,
        key=lambda p: -adjusted_gp_rating(p)
    )[:limit]

    if not sorted_players:
        return "No eligible GP players yet."

    lines = ["**MK64 GP Leaderboard**"]

    for i, name in enumerate(sorted_players, 1):
        stats = gp_player_stats[name]
        lines.append(
            f"{i}. **{name}**: {round(adjusted_gp_rating(name))} "
            f"(raw {round(gp_ratings[name])}) | "
            f"{stats['wins']}-{stats['losses']}-{stats['ties']} | "
            f"matches: {stats['matches']}"
        )

    return "\n".join(lines)


def format_gp_rank(name):
    clean = normalize_name(name)

    if clean not in gp_ratings:
        return f"No GP data found for `{clean}`."

    stats = gp_player_stats[clean]

    return (
        f"**{clean} GP Rank**\n"
        f"Elo: {round(adjusted_gp_rating(clean))} "
        f"(raw {round(gp_ratings[clean])})\n"
        f"Record: {stats['wins']}-{stats['losses']}-{stats['ties']}\n"
        f"Matches: {stats['matches']}\n"
        f"Score-report points for: {stats['points_for']}\n"
        f"Score-report points against: {stats['points_against']}"
    )


def format_gp_stats():
    return (
        f"Stored GP matches: {len(gp_matches)}\n"
        f"Tracked GP players: {len(gp_player_stats)}"
    )


# -----------------------------
# Quarterly / seasonal leaderboards
# -----------------------------

def current_quarter_label():
    now = datetime.now(timezone.utc)
    quarter = ((now.month - 1) // 3) + 1
    return f"{now.year}-Q{quarter}"


def parse_quarter_label(label):
    label = (label or current_quarter_label()).strip().upper().replace(" ", "")

    match = re.match(r"^(\d{4})-?Q([1-4])$", label)

    if not match:
        raise ValueError("Use quarter format like 2026-Q2.")

    year = int(match.group(1))
    quarter = int(match.group(2))
    return year, quarter, f"{year}-Q{quarter}"


def match_in_quarter(match, year, quarter):
    created = match.get("created_at")

    if not created:
        return False

    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return False

    match_quarter = ((dt.month - 1) // 3) + 1
    return dt.year == year and match_quarter == quarter


def format_quarterly_vs_leaderboard(quarter_label=None, limit=10):
    try:
        year, quarter, normalized = parse_quarter_label(quarter_label)
    except ValueError as e:
        return str(e)

    q_ratings = defaultdict(lambda: 1000)
    q_stats = defaultdict(lambda: {"matches": 0, "points": 0})
    q_matches = [m for m in matches if match_in_quarter(m, year, quarter)]

    for match in q_matches:
        players = [p for p, _ in match.get("placements", [])]

        for i, p1 in enumerate(players):
            r1 = q_ratings[p1]
            total_delta = 0

            for j, p2 in enumerate(players):
                if i == j:
                    continue

                r2 = q_ratings[p2]
                actual = 1 if i < j else 0
                expected = expected_score(r1, r2)
                total_delta += actual - expected

            if len(players) > 1:
                q_ratings[p1] += K_FACTOR * (total_delta / (len(players) - 1))

        for player, score in match.get("scores", {}).items():
            q_stats[player]["matches"] += 1
            q_stats[player]["points"] += score

    eligible = [p for p in q_ratings if q_stats[p]["matches"] >= MIN_MATCHES]
    sorted_players = sorted(eligible, key=lambda p: -q_ratings[p])[:limit]

    if not sorted_players:
        return f"No eligible VS players for {normalized}."

    lines = [f"**MK64 VS Quarterly Leaderboard — {normalized}**"]

    for i, name in enumerate(sorted_players, 1):
        stats = q_stats[name]
        avg = stats["points"] / stats["matches"] if stats["matches"] else 0
        lines.append(
            f"{i}. **{name}**: {round(q_ratings[name])} | "
            f"matches: {stats['matches']} | avg pts: {avg:.1f}"
        )

    return "\n".join(lines)


def format_quarterly_gp_leaderboard(quarter_label=None, limit=10):
    try:
        year, quarter, normalized = parse_quarter_label(quarter_label)
    except ValueError as e:
        return str(e)

    q_ratings = defaultdict(lambda: 1000)
    q_stats = defaultdict(lambda: {
        "matches": 0,
        "wins": 0,
        "losses": 0,
        "ties": 0,
        "points_for": 0,
        "points_against": 0
    })
    q_matches = [m for m in gp_matches if match_in_quarter(m, year, quarter)]

    for match in q_matches:
        p1, p2 = match["players"]
        s1 = match["scores"][p1]
        s2 = match["scores"][p2]

        if s1 > s2:
            q_stats[p1]["wins"] += 1
            q_stats[p2]["losses"] += 1
        elif s2 > s1:
            q_stats[p2]["wins"] += 1
            q_stats[p1]["losses"] += 1
        else:
            q_stats[p1]["ties"] += 1
            q_stats[p2]["ties"] += 1

        if match.get("source_type") == "gp_elo_ledger":
            winner = match.get("winner")
            loser = p2 if p1 == winner else p1
            q_ratings[winner] = float(match["winner_rating_after"])
            q_ratings[loser] = float(match["loser_rating_after"])
        else:
            r1 = q_ratings[p1]
            r2 = q_ratings[p2]
            expected1 = expected_score(r1, r2)
            expected2 = expected_score(r2, r1)

            if s1 > s2:
                actual1, actual2 = 1, 0
            elif s2 > s1:
                actual1, actual2 = 0, 1
            else:
                actual1, actual2 = 0.5, 0.5

            q_ratings[p1] += GP_K_FACTOR * (actual1 - expected1)
            q_ratings[p2] += GP_K_FACTOR * (actual2 - expected2)

            q_stats[p1]["points_for"] += s1
            q_stats[p1]["points_against"] += s2
            q_stats[p2]["points_for"] += s2
            q_stats[p2]["points_against"] += s1

        q_stats[p1]["matches"] += 1
        q_stats[p2]["matches"] += 1

    eligible = [p for p in q_ratings if q_stats[p]["matches"] >= GP_MIN_MATCHES]
    sorted_players = sorted(eligible, key=lambda p: -q_ratings[p])[:limit]

    if not sorted_players:
        return f"No eligible GP players for {normalized}."

    lines = [f"**MK64 GP Quarterly Leaderboard — {normalized}**"]

    for i, name in enumerate(sorted_players, 1):
        stats = q_stats[name]
        lines.append(
            f"{i}. **{name}**: {round(q_ratings[name])} | "
            f"{stats['wins']}-{stats['losses']}-{stats['ties']} | "
            f"matches: {stats['matches']}"
        )

    return "\n".join(lines)


# -----------------------------
# Discord message stats storage
# -----------------------------

def init_stats_db():
    with sqlite3.connect(STATS_DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message_stats (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS backfill_state (
                guild_id INTEGER PRIMARY KEY,
                completed_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_message_stats_guild
            ON message_stats(guild_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_message_stats_channel
            ON message_stats(guild_id, channel_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_message_stats_author
            ON message_stats(guild_id, author_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_message_stats_created
            ON message_stats(guild_id, created_at)
        """)

        conn.commit()


def stats_backfill_complete(guild_id):
    with sqlite3.connect(STATS_DB_FILE) as conn:
        row = conn.execute(
            "SELECT completed_at FROM backfill_state WHERE guild_id = ?",
            (guild_id,)
        ).fetchone()

    return row is not None


def mark_stats_backfill_complete(guild_id):
    with sqlite3.connect(STATS_DB_FILE) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO backfill_state (guild_id, completed_at) VALUES (?, ?)",
            (guild_id, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()


def record_message_stat(message):
    if not message.guild:
        return

    with sqlite3.connect(STATS_DB_FILE) as conn:
        conn.execute("""
            INSERT OR IGNORE INTO message_stats
            (message_id, guild_id, channel_id, author_id, author_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            message.id,
            message.guild.id,
            message.channel.id,
            message.author.id,
            str(message.author),
            message.created_at.isoformat()
        ))
        conn.commit()


async def backfill_message_stats(guild):
    scanned = 0
    inserted = 0
    skipped_channels = []

    with sqlite3.connect(STATS_DB_FILE) as conn:
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)

            if not perms.read_messages or not perms.read_message_history:
                skipped_channels.append(channel.name)
                continue

            print(f"Backfilling channel: #{channel.name}")

            batch = []

            try:
                async for msg in channel.history(limit=None, oldest_first=True):
                    scanned += 1

                    batch.append((
                        msg.id,
                        guild.id,
                        channel.id,
                        msg.author.id,
                        str(msg.author),
                        msg.created_at.isoformat()
                    ))

                    if len(batch) >= 500:
                        before = conn.total_changes

                        conn.executemany("""
                            INSERT OR IGNORE INTO message_stats
                            (message_id, guild_id, channel_id, author_id, author_name, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, batch)

                        inserted += conn.total_changes - before
                        batch = []

                    if scanned % 10000 == 0:
                        print(
                            f"Progress: scanned={scanned:,} inserted={inserted:,}"
                        )

                if batch:
                    before = conn.total_changes

                    conn.executemany("""
                        INSERT OR IGNORE INTO message_stats
                        (message_id, guild_id, channel_id, author_id, author_name, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, batch)

                    inserted += conn.total_changes - before

                conn.commit()

            except discord.Forbidden:
                skipped_channels.append(channel.name)

            except discord.HTTPException as e:
                skipped_channels.append(f"{channel.name} ({e})")

    mark_stats_backfill_complete(guild.id)

    return scanned, inserted, skipped_channels


def get_total_message_count(guild_id):
    with sqlite3.connect(STATS_DB_FILE) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM message_stats WHERE guild_id = ?",
            (guild_id,)
        ).fetchone()[0]


def get_top_channels(guild_id, limit=10):
    with sqlite3.connect(STATS_DB_FILE) as conn:
        return conn.execute("""
            SELECT channel_id, COUNT(*) AS c
            FROM message_stats
            WHERE guild_id = ?
            GROUP BY channel_id
            ORDER BY c DESC
            LIMIT ?
        """, (guild_id, limit)).fetchall()


def get_top_users(guild_id, limit=10):
    with sqlite3.connect(STATS_DB_FILE) as conn:
        return conn.execute("""
            SELECT author_id, author_name, COUNT(*) AS c
            FROM message_stats
            WHERE guild_id = ?
            GROUP BY author_id, author_name
            ORDER BY c DESC
            LIMIT ?
        """, (guild_id, limit)).fetchall()


def get_monthly_counts(guild_id, limit=12):
    with sqlite3.connect(STATS_DB_FILE) as conn:
        return conn.execute("""
            SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS c
            FROM message_stats
            WHERE guild_id = ?
            GROUP BY month
            ORDER BY month DESC
            LIMIT ?
        """, (guild_id, limit)).fetchall()


def format_server_stats(guild, channel_limit=10):
    total = get_total_message_count(guild.id)
    top_channels = get_top_channels(guild.id, channel_limit)

    lines = [
        "**Server message stats**",
        f"Total messages indexed: **{total:,}**"
    ]

    if top_channels:
        lines.append("\n**Top channels:**")

        for channel_id, count in top_channels:
            channel = guild.get_channel(channel_id)
            name = channel.mention if channel else f"`{channel_id}`"
            lines.append(f"- {name}: {count:,}")

    return "\n".join(lines)


def format_user_stats(guild, limit=10):
    top_users = get_top_users(guild.id, limit)

    if not top_users:
        return "No user message stats indexed yet."

    lines = ["**Top message counts by user:**"]

    for i, (author_id, author_name, count) in enumerate(top_users, 1):
        member = guild.get_member(author_id)
        name = member.mention if member else author_name
        lines.append(f"{i}. {name}: {count:,}")

    return "\n".join(lines)


def format_monthly_stats(guild, limit=12):
    monthly = get_monthly_counts(guild.id, limit)

    if not monthly:
        return "No monthly message stats indexed yet."

    lines = ["**Monthly message counts:**"]

    for month, count in monthly:
        lines.append(f"- {month}: {count:,}")

    return "\n".join(lines)


# -----------------------------
# Source normalization
# -----------------------------

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:80] or "source"


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def normalize_source(src):
    title = src.get("title", "").strip()
    url = normalize_url(src.get("url", ""))
    server = src.get("server", "general").strip().lower()

    return {
        "id": src.get("id") or slugify(f"{server}_{title or url}"),
        "server": server,
        "site": src.get("site", server),
        "type": src.get("type", src.get("content_type", "page")),
        "game": src.get("game", ""),
        "title": title,
        "url": url,
        "aliases": src.get("aliases", []),
        "tags": src.get("tags", []),
        "description": src.get("description", "").strip(),
        "author": src.get("author", ""),
        "era": src.get("era", ""),
        "source_type": src.get("source_type", "manual")
    }


def make_source(
    server,
    title,
    url,
    tags=None,
    description="",
    site=None,
    source_type="dynamic",
    content_type="page",
    game="",
    aliases=None,
    author="",
    era=""
):
    return normalize_source({
        "id": slugify(f"{server}_{title or url}"),
        "server": server,
        "site": site or server,
        "type": content_type,
        "game": game,
        "title": title,
        "url": url,
        "aliases": aliases or [],
        "tags": tags or [],
        "description": description,
        "author": author,
        "era": era,
        "source_type": source_type
    })


def dedupe_sources(sources):
    seen_urls = set()
    deduped = []

    for src in sources:
        src = normalize_source(src)
        url_key = normalize_url(src["url"]).lower()

        if not url_key or url_key in seen_urls:
            continue

        seen_urls.add(url_key)
        deduped.append(src)

    return deduped


def searchable_text(src):
    parts = [
        src.get("id", ""),
        src.get("title", ""),
        src.get("url", ""),
        src.get("server", ""),
        src.get("site", ""),
        src.get("type", ""),
        src.get("game", ""),
        src.get("description", ""),
        src.get("author", ""),
        src.get("era", ""),
        " ".join(src.get("tags", [])),
        " ".join(src.get("aliases", []))
    ]
    return " ".join(parts).lower()


# -----------------------------
# Dynamic scraping
# -----------------------------

def scrape_links(
    root_url,
    server,
    base_tags,
    description_prefix,
    limit=30,
    site=None,
    content_type="page",
    game="",
    aliases=None
):
    sources = []

    try:
        response = requests.get(root_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for link in soup.find_all("a"):
            href = link.get("href", "").strip()
            title = link.text.strip()

            if not href or not title:
                continue

            if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
                continue

            url = normalize_url(urljoin(root_url, href))

            sources.append(make_source(
                server=server,
                site=site,
                title=title,
                url=url,
                tags=base_tags,
                aliases=aliases or [],
                description=f"{description_prefix}: {title}",
                source_type="dynamic",
                content_type=content_type,
                game=game
            ))

            if len(sources) >= limit:
                break

    except Exception as e:
        print(f"Loading error for {root_url}:", e)

    return sources


# -----------------------------
# Source loaders
# -----------------------------

def load_manual_sources():
    try:
        with open("sources.json", "r", encoding="utf-8") as f:
            return [normalize_source(src) for src in json.load(f)]
    except FileNotFoundError:
        print("sources.json not found. Continuing with dynamic sources only.")
        return []


def load_awrev_root():
    return [
        make_source(
            server="awrev",
            site="awRev",
            content_type="hub",
            title="awRev",
            url="https://awrev.com/",
            tags=["advance wars", "awrev", "battalion wars", "guides", "maps", "community"],
            aliases=["awrev", "advance wars revolution", "aw revolution"],
            description="Main awRev hub for Advance Wars, Battalion Wars, guides, maps, archives, and community resources.",
            source_type="static",
            era="2000s-modern"
        )
    ] + scrape_links(
        root_url="https://awrev.com/",
        server="awrev",
        site="awRev",
        base_tags=["advance wars", "awrev", "community"],
        aliases=["awrev"],
        description_prefix="awRev page"
    )


def load_awrev_guides():
    return scrape_links(
        root_url="https://awrev.com/guides/",
        server="awrev",
        site="awRev",
        base_tags=["advance wars", "awrev", "guide", "guides", "strategy"],
        aliases=["aw guide", "aw guides", "advance wars guide", "advance wars guides"],
        description_prefix="awRev guide",
        content_type="guide"
    )


def load_yoyoyoshi_hub():
    return [
        make_source(
            server="hub",
            site="YoyoYoshi Hub",
            content_type="hub",
            title="YoyoYoshi Hub",
            url="https://yoyoyoshihub.neocities.org/",
            tags=["yoyoyoshi", "hub", "continuity", "archive", "history"],
            aliases=["yoyoyoshi", "yy hub", "main hub"],
            description="Main YoyoYoshi Hub for project continuity, history, routing, and ecosystem resources.",
            source_type="static",
            author="YoyoYoshi",
            era="modern"
        )
    ] + scrape_links(
        root_url="https://yoyoyoshihub.neocities.org/",
        server="hub",
        site="YoyoYoshi Hub",
        base_tags=["yoyoyoshi", "hub", "continuity"],
        aliases=["yoyoyoshi hub"],
        description_prefix="YoyoYoshi Hub page"
    )


def load_mk64_hub():
    return [
        make_source(
            server="mk64", site="awRev", content_type="hub", game="Mario Kart 64",
            title="MK64 Switch Website", url="https://awrev.com/mk64/",
            tags=["mk64", "mario kart 64", "switch", "nintendo switch online", "rankings", "tournaments", "records", "gp league", "vs elo", "community history", "competitive community"],
            aliases=["mk64", "mario kart 64", "mk64 switch", "mk64 website", "mk64 hub", "mk64 switch hub", "mk64 switch website", "mario kart 64 switch", "mario kart 64 nso"],
            description="Main MK64 Switch website on awRev for Nintendo Switch Online community history, rankings, player pages, match history, league coverage, tournaments, videos, and community resources.",
            source_type="static", author="YoyoYoshi", era="2022-modern"
        ),
        make_source(
            server="mk64", site="awRev", content_type="history", game="Mario Kart 64",
            title="MK64 Switch Community History", url="https://awrev.com/mk64/history.php",
            tags=["mk64", "history", "community history", "nso", "league", "tournaments"],
            aliases=["mk64 history", "community history", "mk64 switch history"],
            description="Chronology of the MK64 Switch competitive community from Discord founding through leagues, tournaments, CampKart, rankings, and awRev migration.",
            source_type="static", author="YoyoYoshi", era="2022-modern"
        ),
        make_source(
            server="mk64", site="awRev", content_type="about", game="Mario Kart 64",
            title="About MK64 Switch", url="https://awrev.com/mk64/about-mk64-switch.php",
            tags=["mk64", "about", "nintendo switch online", "competitive scene", "time trials", "nso"],
            aliases=["about mk64 switch", "what is mk64 switch", "mk64 nso community"],
            description="Explains the MK64 Switch Nintendo Switch Online competitive scene and how it relates to broader Mario Kart 64 competition.",
            source_type="static", author="YoyoYoshi", era="2022-modern"
        )
    ] + scrape_links(
        root_url="https://awrev.com/mk64/", server="mk64", site="awRev",
        base_tags=["mk64", "mario kart 64", "switch", "nso", "awrev"],
        aliases=["mk64", "mario kart 64", "mk64 switch"],
        description_prefix="MK64 Switch website page", game="Mario Kart 64"
    )


def load_gamefaqs_root():
    return [
        make_source(
            server="gamefaqs",
            site="GameFAQs",
            content_type="profile",
            title="YoyoYoshi GameFAQs FAQ Contributions",
            url="https://gamefaqs.gamespot.com/community/YoyoYoshi/contributions/faqs",
            tags=["gamefaqs", "faq", "faqs", "guide", "guides", "walkthrough", "walkthroughs", "yoyoyoshi"],
            aliases=["gamefaqs", "faq", "faqs", "guide", "guides", "walkthrough", "walkthroughs", "yoyoyoshi faqs", "faq contributions"],
            description="YoyoYoshi's GameFAQs FAQ contribution page for legacy guides and walkthroughs.",
            source_type="static",
            author="YoyoYoshi",
            era="legacy-modern"
        )
    ]


def load_video_root():
    return [
        make_source(
            server="video",
            site="YouTube",
            content_type="channel",
            title="YoyoYoshi YouTube Channel",
            url="https://www.youtube.com/@YoyoYoshi1",
            tags=["youtube", "video", "videos", "yoyoyoshi", "walkthroughs", "playlist", "playlists"],
            aliases=["youtube", "video", "videos", "yoyoyoshi videos", "yoyoyoshi youtube", "playlist", "playlists"],
            description="YoyoYoshi's YouTube channel for videos, walkthroughs, playlists, and community continuity.",
            source_type="static",
            author="YoyoYoshi",
            era="modern"
        ),
        make_source(
            server="video",
            site="YouTube",
            content_type="playlist_index",
            title="YoyoYoshi YouTube Playlists",
            url="https://www.youtube.com/@YoyoYoshi1/playlists",
            tags=["youtube", "video", "videos", "playlist", "playlists", "advance wars", "mk64", "walkthroughs"],
            aliases=["playlist", "playlists", "youtube playlist", "youtube playlists", "video playlist", "video playlists"],
            description="YoyoYoshi YouTube playlist hub for organized video series and long-form continuity.",
            source_type="static",
            author="YoyoYoshi",
            era="modern"
        )
    ]


def build_sources():
    all_sources = []
    all_sources.extend(load_manual_sources())
    all_sources.extend(load_awrev_root())
    all_sources.extend(load_awrev_guides())
    all_sources.extend(load_yoyoyoshi_hub())
    all_sources.extend(load_mk64_hub())
    all_sources.extend(load_gamefaqs_root())
    all_sources.extend(load_video_root())

    all_sources = dedupe_sources(all_sources)

    with open("compiled_sources.json", "w", encoding="utf-8") as f:
        json.dump(all_sources, f, indent=2, ensure_ascii=False)

    return all_sources


SOURCES = build_sources()


# -----------------------------
# Discord client
# -----------------------------

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

stream_tracker_started = False
vs_history_imported = False
gp_history_imported = False


# -----------------------------
# Search logic
# -----------------------------

def expand_query_words(query_words):
    expanded_words = set(query_words)

    for word in query_words:
        if word.endswith("s") and len(word) > 3:
            expanded_words.add(word[:-1])
        else:
            expanded_words.add(word + "s")

    return expanded_words


def search_sources(query: str, server: str | None = None, limit: int = 3):
    query_clean = query.lower().strip()
    query_words = query_clean.split()
    expanded_words = expand_query_words(query_words)

    scored_results = []

    for item in SOURCES:
        if server and item["server"] != server:
            continue

        haystack = searchable_text(item)
        score = 0

        title_lower = item.get("title", "").lower()
        aliases_lower = [a.lower() for a in item.get("aliases", [])]
        tags_lower = [t.lower() for t in item.get("tags", [])]

        if query_clean == title_lower:
            score += 15

        if query_clean in aliases_lower:
            score += 14

        if query_clean in tags_lower:
            score += 12

        if query_clean in haystack:
            score += 6

        for word in expanded_words:
            if word in haystack:
                score += 2

        for tag in tags_lower:
            if query_clean == tag:
                score += 8
            elif query_clean in tag:
                score += 4

        for alias in aliases_lower:
            if query_clean == alias:
                score += 10
            elif query_clean in alias:
                score += 5

        if score > 0:
            scored_results.append((score, item))

    scored_results.sort(key=lambda x: x[0], reverse=True)
    return [item for score, item in scored_results[:limit]]


def fallback_server_sources(server: str, limit: int = 3):
    matches = [s for s in SOURCES if s.get("server") == server]
    return matches[:limit]


def make_embed(item):
    embed = discord.Embed(
        title=item["title"],
        url=item["url"],
        description=item["description"] or "Continuity route found."
    )

    embed.add_field(
        name="Source",
        value=f'{item.get("site", "Unknown")} • {item.get("type", "page")}',
        inline=False
    )

    if item.get("game"):
        embed.add_field(name="Game", value=item["game"], inline=True)

    if item.get("author"):
        embed.add_field(name="Author", value=item["author"], inline=True)

    tags = item.get("tags", [])
    if tags:
        embed.add_field(name="Tags", value=", ".join(tags[:12]), inline=False)

    return embed


# -----------------------------
# MK64 history import
# -----------------------------

async def import_vs_history_for_channel(channel_id):
    global last_message_id

    channel = client.get_channel(channel_id)

    if channel is None:
        print(f"ERROR: VS channel not found: {channel_id}")
        return

    scanned = 0
    parsed = 0
    rejected = 0

    print(f"Scanning VS history in #{channel.name}...")

    async for msg in channel.history(
        limit=None,
        oldest_first=True
    ):
        if msg.author == client.user:
            continue

        scanned += 1

        if str(msg.id) in processed_message_ids:
            continue

        match = parse_vs_message(msg.content, msg)

        if match:
            if record_vs_match(match, message=msg, save=False):
                parsed += 1
        else:
            rejected += 1
            mark_vs_processed(msg.id, save=False)

    save_vs_data()

    print(f"VS history scan complete for #{channel.name}.")
    print(f"Scanned: {scanned}")
    print(f"Parsed matches: {parsed}")
    print(f"Rejected messages: {rejected}")
    print(f"Saved matches: {len(matches)}")

async def import_vs_history():
    for channel_id in VS_RESULT_CHANNEL_IDS:
        await import_vs_history_for_channel(channel_id)


async def import_gp_history_for_channel(channel_id, source_label="supplemental"):
    channel = client.get_channel(channel_id)

    if channel is None:
        print(f"SKIPPING GP channel not found: {channel_id}")
        return

    scanned = 0
    parsed = 0
    rejected = 0
    duplicates = 0

    print(f"Scanning GP history in #{channel.name} ({source_label})...")

    try:
        async for msg in channel.history(limit=None, oldest_first=True):
            if msg.author == client.user:
                continue

            scanned += 1

            if str(msg.id) in processed_gp_message_ids:
                continue

            match = parse_gp_message(msg.content, msg)

            if match:
                recorded = record_gp_match(match, message=msg, save=False)

                if recorded:
                    parsed += 1
                else:
                    duplicates += 1
            else:
                rejected += 1

    except discord.Forbidden:
        print(f"SKIPPING GP channel #{channel.name}: missing access.")
        return

    except discord.HTTPException as e:
        print(f"SKIPPING GP channel #{channel.name}: HTTP error {e}")
        return

    save_gp_data()

    print(f"GP history scan complete for #{channel.name}.")
    print(f"Scanned: {scanned}")
    print(f"Parsed GP matches: {parsed}")
    print(f"Duplicate GP matches skipped: {duplicates}")
    print(f"Rejected messages: {rejected}")
    print(f"Saved GP matches: {len(gp_matches)}")


async def import_gp_history():
    # Rebuild GP from Discord history every startup so source priority is deterministic.
    reset_gp_state_for_rebuild()

    await import_gp_history_for_channel(
        ELO_GP_MATCH_RESULTS_CHANNEL_ID,
        source_label="primary"
    )

    for channel_id in GP_SUPPLEMENTAL_CHANNEL_IDS:
        await import_gp_history_for_channel(
            channel_id,
            source_label="supplemental"
        )




# -----------------------------
# Events
# -----------------------------

@client.event
async def on_ready():
    global stream_tracker_started, vs_history_imported, gp_history_imported

    init_stats_db()

    print(f"Loaded {len(SOURCES)} sources.")
    print("Saved compiled_sources.json.")
    print(f"Logged in as {client.user}")

    print("VS_RESULT_CHANNEL_IDS =", VS_RESULT_CHANNEL_IDS)
    print("GP_PRIMARY_CHANNEL_ID =", ELO_GP_MATCH_RESULTS_CHANNEL_ID)
    print("GP_SUPPLEMENTAL_CHANNEL_IDS =", GP_SUPPLEMENTAL_CHANNEL_IDS)

    for guild in client.guilds:
        print("GUILD:", guild.name, guild.id)

        for channel in guild.text_channels:
            print("CHANNEL:", channel.name, channel.id)

    tree.copy_global_to(guild=MY_GUILD)
    synced = await tree.sync(guild=MY_GUILD)

    print(f"Synced {len(synced)} guild commands:")
    for cmd in synced:
        print(f"- /{cmd.name}")

    if not vs_history_imported:
        load_vs_data()
        print(f"Loaded {len(matches)} MK64 VS matches.")

        try:
            channel = await client.fetch_channel(MK64_VS_CHANNEL_ID)
            print("FETCHED VS CHANNEL:", channel, channel.id)
        except Exception as e:
            print("FETCH CHANNEL ERROR:", repr(e))

        await import_vs_history()

        vs_history_imported = True

    if not gp_history_imported:
        load_gp_data()
        print(f"Loaded {len(gp_matches)} MK64 GP matches.")

        await import_gp_history()

        gp_history_imported = True

    if not stream_tracker_started:
        start_stream_tracker(client)
        stream_tracker_started = True


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    record_message_stat(message)

    content = message.content.strip()

    if content == "!serverstats":
        await message.channel.send(format_server_stats(message.guild))
        return

    if content == "!userstats":
        await message.channel.send(format_user_stats(message.guild))
        return

    if content == "!monthlystats":
        await message.channel.send(format_monthly_stats(message.guild))
        return

    if message.channel.id in VS_RESULT_CHANNEL_IDS:
        if content == "!leaderboard":
            mark_vs_processed(message.id)
            await message.channel.send(format_vs_leaderboard(10))
            return

        if content.startswith("!rank"):
            mark_vs_processed(message.id)

            parts = content.split(maxsplit=1)

            if len(parts) < 2:
                await message.channel.send("Usage: `!rank playername`")
                return

            await message.channel.send(format_vs_rank(parts[1]))
            return

        if content == "!stats":
            mark_vs_processed(message.id)
            await message.channel.send(format_vs_stats())
            return

        match = parse_vs_message(content, message)

        if match:
            recorded = record_vs_match(match, message=message)

            if recorded:
                await message.add_reaction("✅")
        else:
            mark_vs_processed(message.id)

        return

    if message.channel.id in GP_RESULT_CHANNEL_IDS:
        if content == "!gpleaderboard":
            await message.channel.send(format_gp_leaderboard(10))
            return

        if content.startswith("!gprank"):
            parts = content.split(maxsplit=1)

            if len(parts) < 2:
                await message.channel.send("Usage: `!gprank playername`")
                return

            await message.channel.send(format_gp_rank(parts[1]))
            return

        if content == "!gpstats":
            await message.channel.send(format_gp_stats())
            return

        match = parse_gp_message(content, message)

        if match:
            recorded = record_gp_match(match, message=message)

            if recorded:
                await message.add_reaction("🏁")

        return



# -----------------------------
# Continuity pages / digital historiography helpers
# -----------------------------

def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def short_date(value):
    dt = parse_iso_datetime(value)
    return dt.date().isoformat() if dt else "unknown"


def combined_player_names():
    return sorted(set(player_stats.keys()) | set(gp_player_stats.keys()) | set(PLAYER_NOTES.keys()))


def get_player_matches(player):
    clean = normalize_name(player)
    vs = [m for m in matches if clean in m.get("scores", {})]
    gp = [m for m in gp_matches if clean in m.get("players", [])]
    return vs, gp


def player_date_range(vs, gp):
    dates = []
    for match in vs + gp:
        dt = parse_iso_datetime(match.get("created_at"))
        if dt:
            dates.append(dt)
    if not dates:
        return "unknown", "unknown"
    return min(dates).date().isoformat(), max(dates).date().isoformat()


def build_player_continuity_profile(player):
    clean = normalize_name(player)
    note = PLAYER_NOTES.get(clean, {})
    vs, gp = get_player_matches(clean)
    first_seen, last_seen = player_date_range(vs, gp)
    vs_stat = player_stats.get(clean, {})
    gp_stat = gp_player_stats.get(clean, {})
    return {
        "player_id": clean,
        "display_name": note.get("display_name", clean),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_note": "Generated from MK64 Discord match data, bot records, manual community notes, and awRev continuity metadata. Review before publication.",
        "roles": note.get("roles", []),
        "summary": note.get("summary", "No manual biography note has been added yet."),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "links": note.get("links", []),
        "vs": {
            "matches": vs_stat.get("matches", 0),
            "points": vs_stat.get("points", 0),
            "elo_adjusted": round(adjusted_rating(clean)) if clean in ratings else None,
            "elo_raw": round(ratings[clean]) if clean in ratings else None,
            "recent_matches": [
                {"date": short_date(m.get("created_at")), "scores": m.get("scores", {}), "jump_url": m.get("jump_url", "")}
                for m in sorted(vs, key=lambda x: x.get("created_at", ""), reverse=True)[:10]
            ]
        },
        "gp": {
            "matches": gp_stat.get("matches", 0),
            "record": f"{gp_stat.get('wins', 0)}-{gp_stat.get('losses', 0)}-{gp_stat.get('ties', 0)}",
            "elo_adjusted": round(adjusted_gp_rating(clean)) if clean in gp_ratings else None,
            "elo_raw": round(gp_ratings[clean]) if clean in gp_ratings else None,
            "recent_matches": [
                {"date": short_date(m.get("created_at")), "players": m.get("players", []), "winner": m.get("winner"), "scores": m.get("scores", {}), "jump_url": m.get("jump_url", "")}
                for m in sorted(gp, key=lambda x: x.get("created_at", ""), reverse=True)[:10]
            ]
        }
    }


def format_player_continuity_profile(player):
    profile = build_player_continuity_profile(player)
    lines = [
        f"**{profile['display_name']} - MK64 Continuity Profile**",
        f"First seen in records: {profile['first_seen']}",
        f"Latest record: {profile['last_seen']}"
    ]
    if profile["roles"]:
        lines.append("Roles: " + ", ".join(profile["roles"]))
    if profile["summary"]:
        lines.append("\n" + profile["summary"])
    lines.append(
        f"\nVS: {profile['vs']['matches']} matches"
        + (f" | Elo {profile['vs']['elo_adjusted']}" if profile['vs']['elo_adjusted'] else "")
    )
    lines.append(
        f"GP: {profile['gp']['matches']} matches | {profile['gp']['record']}"
        + (f" | Elo {profile['gp']['elo_adjusted']}" if profile['gp']['elo_adjusted'] else "")
    )
    if profile["links"]:
        lines.append("\nLinks:\n" + "\n".join(profile["links"][:5]))
    lines.append("\nGenerated from bot records and manual notes. Review before using as a public bio.")
    return "\n".join(lines)[:1900]


def render_player_profile_html(profile):
    title = html.escape(profile["display_name"])
    roles = ", ".join(html.escape(r) for r in profile.get("roles", [])) or "TBD"
    summary = html.escape(profile.get("summary", ""))
    links = "".join(f'<li><a href="{html.escape(link)}">{html.escape(link)}</a></li>' for link in profile.get("links", [])) or "<li>TBD</li>"
    return f'''<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{title} - MK64 Continuity Profile</title></head>
<body>
<h1>{title}</h1>
<p><strong>Roles:</strong> {roles}</p>
<p><strong>First seen:</strong> {html.escape(profile['first_seen'])}</p>
<p><strong>Latest record:</strong> {html.escape(profile['last_seen'])}</p>
<p>{summary}</p>
<h2>Competition Summary</h2>
<ul>
<li>VS matches: {profile['vs']['matches']}</li>
<li>VS Elo: {profile['vs']['elo_adjusted'] or 'TBD'}</li>
<li>GP matches: {profile['gp']['matches']}</li>
<li>GP record: {html.escape(profile['gp']['record'])}</li>
<li>GP Elo: {profile['gp']['elo_adjusted'] or 'TBD'}</li>
</ul>
<h2>Links</h2><ul>{links}</ul>
<p><em>{html.escape(profile['source_note'])}</em></p>
</body></html>'''


def render_player_index_html(index):
    rows = []
    for player in sorted(index["players"], key=lambda p: p["display_name"].lower()):
        pid = html.escape(player["player_id"])
        name = html.escape(player["display_name"])
        rows.append(f'<tr><td><a href="{pid}.html">{name}</a></td><td>{html.escape(player["first_seen"])}</td><td>{html.escape(player["last_seen"])}</td><td>{player["vs_matches"]}</td><td>{player["gp_matches"]}</td></tr>')
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>MK64 Continuity Player Index</title></head>
<body><h1>MK64 Continuity Player Index</h1>
<p>Generated from MK64 bot records and manual continuity notes. Review before publication.</p>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Player</th><th>First Seen</th><th>Latest Record</th><th>VS Matches</th><th>GP Matches</th></tr>
{''.join(rows)}
</table></body></html>'''


def write_player_profile_files(export_dir=CONTINUITY_EXPORT_DIR):
    player_dir = os.path.join(export_dir, "players")
    os.makedirs(player_dir, exist_ok=True)
    profiles = []
    for name in combined_player_names():
        profile = build_player_continuity_profile(name)
        if not profile["roles"] and profile["vs"]["matches"] == 0 and profile["gp"]["matches"] == 0:
            continue
        profiles.append(profile)
        with open(os.path.join(player_dir, f"{profile['player_id']}.json"), "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        with open(os.path.join(player_dir, f"{profile['player_id']}.html"), "w", encoding="utf-8") as f:
            f.write(render_player_profile_html(profile))
    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(profiles),
        "players": [{"player_id": p["player_id"], "display_name": p["display_name"], "first_seen": p["first_seen"], "last_seen": p["last_seen"], "vs_matches": p["vs"]["matches"], "gp_matches": p["gp"]["matches"]} for p in profiles]
    }
    with open(os.path.join(player_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    with open(os.path.join(player_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_player_index_html(index))
    return len(profiles), player_dir


def render_community_history_html(history):
    items = []
    for m in history["milestones"]:
        items.append(f'<li><strong>{html.escape(m["date"])} - {html.escape(m["title"])}</strong><br>{html.escape(m["summary"])}</li>')
    stats = history["stats"]
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>MK64 Switch Community History Draft</title></head>
<body><h1>MK64 Switch Community History Draft</h1>
<p><em>{html.escape(history['source_note'])}</em></p>
<p>Bot records currently include {stats['vs_matches']} VS matches, {stats['gp_matches']} GP matches, {stats['tracked_vs_players']} VS players, and {stats['tracked_gp_players']} GP players.</p>
<ol>{''.join(items)}</ol>
</body></html>'''


def export_community_history(export_dir=CONTINUITY_EXPORT_DIR):
    os.makedirs(export_dir, exist_ok=True)
    history = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_note": "Draft digital historiography generated from manual milestones and bot records. Review before publication.",
        "milestones": COMMUNITY_MILESTONES,
        "stats": {"vs_matches": len(matches), "gp_matches": len(gp_matches), "tracked_vs_players": len(player_stats), "tracked_gp_players": len(gp_player_stats)}
    }
    with open(os.path.join(export_dir, "community_history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    path = os.path.join(export_dir, "community_history.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_community_history_html(history))
    return path


def run_continuity_qa():
    issues = []
    old_mk64 = [src for src in SOURCES if "yoyoyoshihub.neocities.org/mk64" in src.get("url", "")]
    if old_mk64:
        issues.append(f"Found {len(old_mk64)} MK64 source(s) still pointing to Neocities instead of awRev.")
    for required in ["https://awrev.com/mk64/", "https://awrev.com/mk64/history.php", "https://awrev.com/mk64/about-mk64-switch.php"]:
        if not any(normalize_url(src.get("url", "")) == normalize_url(required) for src in SOURCES):
            issues.append(f"Missing required MK64 source: {required}")
    high_activity = []
    for name in combined_player_names():
        clean = normalize_name(name)
        total = player_stats.get(clean, {}).get("matches", 0) + gp_player_stats.get(clean, {}).get("matches", 0)
        if total >= 20 and clean not in PLAYER_NOTES:
            high_activity.append((clean, total))
    if high_activity:
        sample = ", ".join(f"{name} ({count})" for name, count in sorted(high_activity, key=lambda x: -x[1])[:10])
        issues.append("High-activity players without manual continuity notes: " + sample)
    return "**Continuity QA:** No major issues found." if not issues else "**Continuity QA findings:**\n" + "\n".join(f"- {issue}" for issue in issues)

# -----------------------------
# Slash commands
# -----------------------------

@tree.command(name="guide", description="Search the full YoyoYoshi continuity ecosystem.")
@app_commands.describe(
    query="What are you looking for?",
    limit="Number of results to show, from 1 to 5"
)
async def guide(interaction: discord.Interaction, query: str, limit: int = 3):
    limit = max(1, min(limit, 5))
    results = search_sources(query, limit=limit)

    if not results:
        await interaction.response.send_message(
            f"I couldn't find anything for **{query}** yet. "
            f"Try `/sitemap` to see available route categories."
        )
        return

    await interaction.response.send_message(
        content=f"Here’s what I found for **{query}**:",
        embeds=[make_embed(r) for r in results]
    )


@tree.command(name="awrev", description="Search awRev resources.")
@app_commands.describe(query="Advance Wars / awRev topic")
async def awrev(interaction: discord.Interaction, query: str):
    results = search_sources(query, "awrev")

    if not results:
        await interaction.response.send_message(
            f"Lash searched the lab, but found nothing for **{query}** yet."
        )
        return

    await interaction.response.send_message(
        content="Lash found something useful:",
        embeds=[make_embed(r) for r in results]
    )


@tree.command(name="mk64", description="Search MK64 Switch resources.")
@app_commands.describe(query="MK64 topic")
async def mk64(interaction: discord.Interaction, query: str):
    results = search_sources(query, "mk64")

    if not results:
        await interaction.response.send_message(
            f"Yoshi couldn't find a route for **{query}** yet. Maybe it needs a new shortcut."
        )
        return

    await interaction.response.send_message(
        content="Yoshi found a route:",
        embeds=[make_embed(r) for r in results]
    )


@tree.command(name="hub", description="Search YoyoYoshi Hub resources.")
@app_commands.describe(query="Hub topic")
async def hub(interaction: discord.Interaction, query: str):
    results = search_sources(query, "hub")

    if not results:
        await interaction.response.send_message(
            f"I couldn't find a Hub page for **{query}** yet."
        )
        return

    await interaction.response.send_message(
        content="YoyoYoshi Hub route found:",
        embeds=[make_embed(r) for r in results]
    )


@tree.command(name="gamefaqs", description="Search YoyoYoshi GameFAQs guide links.")
@app_commands.describe(query="GameFAQs topic")
async def gamefaqs(interaction: discord.Interaction, query: str):
    results = search_sources(query, "gamefaqs")

    if not results and query.lower().strip() in [
        "faq", "faqs", "guide", "guides", "walkthrough", "walkthroughs"
    ]:
        results = fallback_server_sources("gamefaqs")

    if not results:
        await interaction.response.send_message(
            f"I couldn't find a GameFAQs route for **{query}** yet."
        )
        return

    await interaction.response.send_message(
        content="GameFAQs continuity route found:",
        embeds=[make_embed(r) for r in results]
    )


@tree.command(name="video", description="Search YoyoYoshi video and playlist links.")
@app_commands.describe(query="Video or playlist topic")
async def video(interaction: discord.Interaction, query: str):
    results = search_sources(query, "video")

    if not results and query.lower().strip() in [
        "playlist", "playlists", "video", "videos", "youtube"
    ]:
        results = fallback_server_sources("video")

    if not results:
        await interaction.response.send_message(
            f"I couldn't find a video route for **{query}** yet."
        )
        return

    await interaction.response.send_message(
        content="Video route found:",
        embeds=[make_embed(r) for r in results]
    )


@tree.command(name="randomguide", description="Find a random guide or continuity route.")
@app_commands.describe(server="Optional server filter: awrev, mk64, hub, gamefaqs, or video")
async def randomguide(interaction: discord.Interaction, server: str = ""):
    server_clean = server.lower().strip()

    guide_sources = [
        s for s in SOURCES
        if s.get("type") in [
            "guide",
            "walkthrough",
            "hub",
            "playlist_index",
            "event",
            "profile",
            "channel"
        ]
    ]

    if server_clean:
        guide_sources = [
            s for s in guide_sources
            if s.get("server") == server_clean
        ]

    if not guide_sources:
        if server_clean:
            await interaction.response.send_message(
                f"No random guide routes found for **{server_clean}**."
            )
        else:
            await interaction.response.send_message("No guide routes are loaded yet.")
        return

    item = random.choice(guide_sources)

    content = (
        f"Random **{server_clean}** continuity route found:"
        if server_clean
        else "Random continuity route found:"
    )

    await interaction.response.send_message(
        content=content,
        embed=make_embed(item)
    )


@tree.command(name="sitemap", description="Show available continuity route categories.")
async def sitemap(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Available continuity routes:**\n\n"
        "• `/guide` — search everything\n"
        "• `/awrev` — Advance Wars / Battalion Wars / awRev\n"
        "• `/mk64` — MK64 Switch resources\n"
        "• `/hub` — YoyoYoshi Hub pages\n"
        "• `/gamefaqs` — GameFAQs guides\n"
        "• `/video` — YouTube videos/playlists\n"
        "• `/randomguide` — random route\n"
        "• `/sourcecount` — loaded source count\n"
        "• `/debugsources` — source titles by server\n"
        "• `/vsleaderboard` — MK64 VS leaderboard\n"
        "• `/vsrank` — MK64 VS player rank\n"
        "• `/vsstats` — MK64 VS parser stats\n"
        "• `/vsquarter` — MK64 VS quarterly leaderboard\n"
        "• `/gpleaderboard` — MK64 GP leaderboard\n"
        "• `/gprank` — MK64 GP player rank\n"
        "• `/gpstats` — MK64 GP parser stats\n"
        "• `/gpquarter` — MK64 GP quarterly leaderboard\n"
        "• `/backfill_stats` — admin-only Discord message stats backfill\n"
        "• `/serverstats` — Discord message totals by channel\n"
        "• `/userstats` — Discord message totals by user\n"
        "• `/monthlystats` — Discord message totals by month\n"
        "• `/playerpage` — draft MK64 continuity profile\n"
        "• `/communityhistory` — draft MK64 history milestones\n"
        "• `/continuityqa` — admin-only continuity QA\n"
        "• `/exportcontinuity` — admin-only draft player/history export"
    )


@tree.command(name="sourcecount", description="Show loaded continuity source count.")
async def sourcecount(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Loaded **{len(SOURCES)}** compiled continuity sources."
    )


@tree.command(name="debugsources", description="Show source titles by server.")
@app_commands.describe(server="Server name, like gamefaqs, video, mk64, awrev, hub")
async def debugsources(interaction: discord.Interaction, server: str):
    server_clean = server.lower().strip()
    matches_found = [s for s in SOURCES if s.get("server") == server_clean]

    if not matches_found:
        await interaction.response.send_message(
            f"No sources found for server **{server}**."
        )
        return

    titles = "\n".join([f"- {s['title']}" for s in matches_found[:20]])

    await interaction.response.send_message(
        f"Found **{len(matches_found)}** sources for **{server_clean}**:\n{titles}"
    )


@tree.command(name="vsleaderboard", description="Show the MK64 VS leaderboard.")
@app_commands.describe(limit="Number of players to show, from 1 to 20")
async def vsleaderboard(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(format_vs_leaderboard(limit))


@tree.command(name="vsrank", description="Show an MK64 VS player's rating.")
@app_commands.describe(player="Player name or alias")
async def vsrank(interaction: discord.Interaction, player: str):
    await interaction.response.send_message(format_vs_rank(player))


@tree.command(name="vsstats", description="Show MK64 VS parser stats.")
async def vsstats(interaction: discord.Interaction):
    await interaction.response.send_message(format_vs_stats())


@tree.command(name="vsquarter", description="Show the MK64 VS quarterly leaderboard.")
@app_commands.describe(
    quarter="Quarter in YYYY-Q# format, like 2026-Q2. Leave blank for current quarter.",
    limit="Number of players to show, from 1 to 20"
)
async def vsquarter(interaction: discord.Interaction, quarter: str = "", limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(
        format_quarterly_vs_leaderboard(quarter or None, limit)
    )


@tree.command(name="gpleaderboard", description="Show the MK64 GP leaderboard.")
@app_commands.describe(limit="Number of players to show, from 1 to 20")
async def gpleaderboard(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(format_gp_leaderboard(limit))


@tree.command(name="gprank", description="Show an MK64 GP player's rating.")
@app_commands.describe(player="Player name or alias")
async def gprank(interaction: discord.Interaction, player: str):
    await interaction.response.send_message(format_gp_rank(player))


@tree.command(name="gpstats", description="Show MK64 GP parser stats.")
async def gpstats(interaction: discord.Interaction):
    await interaction.response.send_message(format_gp_stats())


@tree.command(name="gpquarter", description="Show the MK64 GP quarterly leaderboard.")
@app_commands.describe(
    quarter="Quarter in YYYY-Q# format, like 2026-Q2. Leave blank for current quarter.",
    limit="Number of players to show, from 1 to 20"
)
async def gpquarter(interaction: discord.Interaction, quarter: str = "", limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(
        format_quarterly_gp_leaderboard(quarter or None, limit)
    )


@tree.command(name="playerpage", description="Draft an MK64 continuity profile from bot records.")
@app_commands.describe(player="Player name or alias")
async def playerpage(interaction: discord.Interaction, player: str):
    await interaction.response.send_message(format_player_continuity_profile(player))


@tree.command(name="communityhistory", description="Show MK64 community history milestones and bot record totals.")
async def communityhistory(interaction: discord.Interaction):
    lines = ["**MK64 Switch Community History — Draft Milestones**"]
    for milestone in COMMUNITY_MILESTONES:
        lines.append(f"- **{milestone['date']} — {milestone['title']}**: {milestone['summary']}")
    lines.append(f"\nBot records: {len(matches)} VS matches, {len(gp_matches)} GP matches, {len(player_stats)} VS players, {len(gp_player_stats)} GP players.")
    await interaction.response.send_message("\n".join(lines)[:1900])


@tree.command(name="continuityqa", description="Admin-only: check continuity links, missing player notes, and migration issues.")
async def continuityqa(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can run this command.", ephemeral=True)
        return
    await interaction.response.send_message(run_continuity_qa(), ephemeral=True)


@tree.command(name="exportcontinuity", description="Admin-only: export draft MK64 player pages and community history files.")
async def exportcontinuity(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can run this command.", ephemeral=True)
        return
    player_count, player_dir = write_player_profile_files()
    history_path = export_community_history()
    await interaction.response.send_message(f"Exported {player_count} draft player continuity profiles to `{player_dir}` and community history to `{history_path}`. Review before publication.", ephemeral=True)


@tree.command(name="backfill_stats", description="Admin-only: backfill Discord message stats once.")
async def backfill_stats(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "Only admins can run this command.",
            ephemeral=True
        )
        return

    if stats_backfill_complete(interaction.guild.id):
        await interaction.response.send_message(
            "Stats backfill already completed for this server.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Starting stats backfill... this may take a while.",
        ephemeral=True
    )

    scanned, inserted, skipped = await backfill_message_stats(interaction.guild)

    msg = (
        f"Backfill complete.\n"
        f"Scanned messages: {scanned}\n"
        f"New rows inserted: {inserted}"
    )

    if skipped:
        msg += "\nSkipped channels: " + ", ".join(skipped[:20])

    print(msg)

    try:
        await interaction.channel.send(msg)
    except Exception as e:
        print("Could not send completion message:", e)


@tree.command(name="serverstats", description="Show Discord message stats by channel.")
@app_commands.describe(limit="Number of channels to show, from 1 to 20")
async def serverstats(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(format_server_stats(interaction.guild, limit))


@tree.command(name="userstats", description="Show Discord message stats by user.")
@app_commands.describe(limit="Number of users to show, from 1 to 20")
async def userstats(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(format_user_stats(interaction.guild, limit))


@tree.command(name="monthlystats", description="Show Discord message stats by month.")
@app_commands.describe(limit="Number of months to show, from 1 to 24")
async def monthlystats(interaction: discord.Interaction, limit: int = 12):
    limit = max(1, min(limit, 24))
    await interaction.response.send_message(format_monthly_stats(interaction.guild, limit))


# -----------------------------
# Run bot
# -----------------------------

threading.Thread(
    target=run_web_server,
    daemon=True
).start()

client.run(TOKEN)
