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
# Optional persistent Railway volume path; the default is local to the bot process.
GP_REJECTED_AUDIT_FILE = os.getenv("GP_REJECTED_AUDIT_FILE", "gp_rejected_audit.json")
GP_REJECTED_AUDIT_LIMIT = 10000

STATS_DB_FILE = "discord_stats.sqlite3"
MANUAL_EVENT_RESULTS_FILE = "mk64_event_results.json"

# Optional Railway volume: set ELO_ANNOUNCEMENT_STATE_FILE to a persistent path,
# e.g. /data/elo_announcement_state.json. The default lives beside bot.py.
ELO_ANNOUNCEMENT_STATE_FILE = os.getenv(
    "ELO_ANNOUNCEMENT_STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "elo_announcement_state.json"),
)
ELO_ANNOUNCEMENT_CHANNEL_ID_RAW = os.getenv("ELO_ANNOUNCEMENT_CHANNEL_ID", "").strip()
ELO_ANNOUNCEMENT_CHANNEL_ID = (
    int(ELO_ANNOUNCEMENT_CHANNEL_ID_RAW)
    if ELO_ANNOUNCEMENT_CHANNEL_ID_RAW else MK64_VS_CHANNEL_ID
)


# CampKart 3 GP concluded on Saturday, September 5, 2026.
# Insert reviewed CampKart GP results before later Discord GP activity.
GP_MANUAL_EVENT_CUTOFF = datetime(2026, 9, 6, tzinfo=timezone.utc)

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
    "1035953951499104306": "gumby",  # Gumby Discord user ID in historical VS reports
    "jesse": "spacedcowboy",
    "jessek": "spacedcowboy",
    "jessek13": "spacedcowboy",
    "spaced": "spacedcowboy",
    "socal": "juggernaut",
    "coolex": "thecoolex",
    "fuzzy": "fuzz",
    "fuzzyfugs": "fuzz",
    "fuzzyfugsdkchallenge": "fuzz",
    "booth": "noakevbo",
    "palatus": "patalus",
    "pat": "patalus",
    "espagetti": "espaghetti",
    "yoyo": "yoyoyoshi",
    "bobby": "yoyoyoshi",
    "blazeup": "martin",
    "fx": "fx64",
    "fx64ranked": "fx64",
    "urbanoutlaw": "urban",
    "wildermk64": "wilder",
}


def normalize_name(name):
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9_]", "", name)
    return ALIASES.get(name, name)


def normalize_vs_match_players(match):
    """Canonicalize stored/new VS identities before Elo and statistics updates."""
    scores = match.get("scores", {})
    normalized = {}
    for player, score in scores.items():
        canonical = normalize_name(str(player))
        if not canonical or canonical in normalized:
            raise ValueError(f"VS identity collision in match {match.get('message_id') or match.get('source_id')}: {player}")
        normalized[canonical] = score
    if len(normalized) != len(scores):
        raise ValueError("VS normalization changed the number of players")
    match["scores"] = normalized
    # Reconstruct placements from canonical scores to avoid stale raw-ID keys.
    match["placements"] = sorted(normalized.items(), key=lambda item: -item[1])
    return match


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
        name = ALIASES.get(user_id) or mention_names.get(user_id)

        if not name:
            return match.group(0)

        return f"@{name}"

    return VS_MENTION_PATTERN.sub(repl, content)


def clean_score_name(name):
    name = str(name or "").strip()
    name = re.sub(r"\s+", " ", name)

    aka_match = re.search(r"\ba\s*/?\s*k\s*/?\s*a\b\s+(.+)$", name, re.IGNORECASE)
    if aka_match:
        name = aka_match.group(1).strip()

    name = re.sub(r"\[[^\]]*\]", "", name)
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.sub(r"^@", "", name)
    name = name.strip(" ,:;|-()")

    # Preserve multi-word player handles such as "Mr Pitt" as mrpitt instead
    # of collapsing them to the final word. normalize_name removes spacing and
    # punctuation afterward.
    return normalize_name(name)


# A qualifying VS scoreboard is ranked by default, regardless of date.
# Explicit noncompetitive labels always take precedence over a "Ranked" word.
VS_NONCOMPETITIVE_PATTERN = re.compile(
    r"\b(?:unranked|casual|exhibition|unrated|friendly|for\s+fun|"
    r"not\s+(?:for\s+)?rank(?:ed|ing)|not\s+posted\s+on\s+kaillera)\b",
    re.IGNORECASE,
)


def is_excluded_vs_result(content):
    return bool(VS_NONCOMPETITIVE_PATTERN.search(content or ""))


def parse_vs_message(content, message=None):
    # Retain the original ranked-mention extraction, but do not import an
    # explicitly noncompetitive result even when it contains "Ranked".
    if is_excluded_vs_result(content):
        return None
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

        player_name = normalize_name(user_id) if user_id in ALIASES else mention_names.get(
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



# Conservative legacy VS recovery: plain-text scoreboards, 2022 onward.
# Keep the original ranked-mention parser as the first-pass parser.
VS_LEGACY_NAME_ALIASES = {
    "clapdaddyakafuzz": "fuzz", "clapdaddy": "fuzz",
    "cptntryhardchangloveyaben": "chang", "cptntryhard": "chang",
    "captn": "chang", "captain": "chang", "chang": "chang",
    "dipthe4man": "dip", "dip": "dip", "thecountess": "countess",
    "juggernautlasbest": "juggernaut", "juggernut": "juggernaut",
    "fx": "fx64", "fx64": "fx64",
    "gg": "gg", "jesses": "spacedcowboy",
}
VS_LEGACY_ROW = re.compile(
    r"^\s*(?:[-*]\s*)?(?P<name>.+?)\s*(?:\s+-\s*|\s+)(?P<score>\d{1,2})(?=\s|$|[:!]|\\)",
    re.IGNORECASE,
)
VS_LEGACY_SCORE_SUFFIX = re.compile(r"^\s*(?:[:][a-z0-9_~]+[:]\s*)?", re.IGNORECASE)


def vs_legacy_name(raw):
    raw = str(raw or "").strip()
    # Discord emotes that precede a player's name (e.g. :Gumby: 36).
    emoji_only = re.fullmatch(r":([A-Za-z][A-Za-z0-9_~]*):", raw)
    if emoji_only:
        raw = emoji_only.group(1)
    else:
        raw = re.sub(r":(?:[A-Za-z][A-Za-z0-9_~]*):", " ", raw)
    raw = raw.lstrip("@ ").strip()
    raw = re.sub(r"\s+a\s*/?\s*k\s*/?\s*a\s+", " a/k/a ", raw, flags=re.I)
    if re.search(r"\ba/k/a\b", raw, flags=re.I):
        raw = re.split(r"\ba/k/a\b", raw, flags=re.I)[-1].strip()
    normal = normalize_name(raw)
    return VS_LEGACY_NAME_ALIASES.get(normal, normal)


def parse_vs_legacy_message(content, message=None):
    """Parse 3-/4-player, 16-race plain-text VS scoreboards with total 96.

    Requiring exactly 96 points and a full, consecutive set of player rows
    prevents chat messages and GP cup scores from becoming VS matches.
    Two-player and nonstandard scoreboards stay manual-review only.
    """
    if is_excluded_vs_result(content):
        return None
    text = replace_discord_mentions(content, message)
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if rows:
                # Allow blank lines, but not other commentary inside a scoreboard.
                continue
            continue
        # Match a player and their score at the start of the line. Names may
        # include Discord @mentions, slashes, punctuation, and spaces.
        m = re.match(r"^(?:[-*]\s*)?(?P<name>@?[^\n]+?)\s*(?:\s-\s*|\s+|-(?=\d))(?P<score>\d{1,2})(?=\s|$|[!:])", line)
        if not m:
            if rows and len(rows) < 4:
                rows = []
            continue
        name = m.group("name").strip()
        # Never parse game notes, headings, track/cup rows, or standings commentary.
        if re.search(r"\b(?:mush(?:room)?|flow(?:er)?|spec(?:ial)?|star|total|ranked|round|notes?|score|result|winner)\b", name, re.I):
            if rows and len(rows) < 4:
                rows = []
            continue
        name = vs_legacy_name(name)
        if not name or name.startswith("user_") or name in {"deleteduser", "image"} or len(name) > 36:
            rows = []
            continue
        score = int(m.group("score"))
        if score > MAX_SCORE:
            rows = []
            continue
        rows.append((name, score))
        if len(rows) == 4:
            if len({p for p, _ in rows}) == 4 and sum(v for _, v in rows) == 96:
                scores = dict(rows)
                return {"scores": scores, "placements": sorted(scores.items(), key=lambda x: -x[1])}
            rows = []
    if len(rows) == 3 and len({p for p, _ in rows}) == 3 and sum(v for _, v in rows) == 96:
        scores = dict(rows)
        return {"scores": scores, "placements": sorted(scores.items(), key=lambda x: -x[1])}
    return None


def parse_vs_message_with_legacy(content, message=None):
    """Rank qualifying VS scoreboards by default; explicit exclusions win."""
    if is_excluded_vs_result(content):
        return None
    return parse_vs_message(content, message) or parse_vs_legacy_message(content, message)

def expected_score(r1, r2):
    return 1 / (1 + 10 ** ((r2 - r1) / 400))


def update_ratings(match):
    players = [p for p, _ in match["placements"]]

    if len(players) < 2:
        return


    # Compare actual lobby scores pairwise so tied scores are true Elo ties.
    # Sorting order alone must not turn a 33-33 or 24-24 result into a win/loss.
    for p1 in players:
        r1 = ratings[p1]
        total_delta = 0

        for p2 in players:
            if p1 == p2:
                continue

            r2 = ratings[p2]
            s1 = match["scores"][p1]
            s2 = match["scores"][p2]

            if s1 > s2:
                actual = 1.0
            elif s1 < s2:
                actual = 0.0
            else:
                actual = 0.5

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
    # Existing records may predate identity aliases; normalize before rebuilding
    # their Elo and per-player totals, without discarding any match history.
    for match in matches:
        normalize_vs_match_players(match)
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


def rebuild_vs_state_from_matches(save=True):
    """Recalculate stored VS Elo/stats with the current score-aware tie model."""
    global ratings, player_stats

    ratings = defaultdict(lambda: 1000)
    player_stats = defaultdict(lambda: {
        "matches": 0,
        "points": 0
    })

    matches.sort(key=lambda m: (str(m.get("created_at", "")), int(m.get("event_order") or 0)))
    for match in matches:
        normalize_vs_match_players(match)
        update_ratings(match)
        for player, score in match.get("scores", {}).items():
            player_stats[player]["matches"] += 1
            player_stats[player]["points"] += score

    if save:
        save_vs_data()


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

    normalize_vs_match_players(match)
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
# VS Elo announcements (separate from results and ranking calculations)
# -----------------------------

def snapshot_vs_announcement():
    """Serializable snapshot; includes all rated players, not only the top ten."""
    return {
        "ratings": {
            name: {
                "adjusted": round(adjusted_rating(name), 3),
                "raw": round(float(ratings[name]), 3),
                "matches": int(player_stats[name]["matches"]),
            }
            for name in ratings
        },
        "match_count": len(matches),
    }


def load_elo_announcement_state():
    if not os.path.exists(ELO_ANNOUNCEMENT_STATE_FILE):
        return None
    with open(ELO_ANNOUNCEMENT_STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    if not isinstance(state, dict) or not isinstance(state.get("ratings"), dict):
        raise ValueError("Invalid Elo announcement state; refusing to overwrite it.")
    return state


def save_elo_announcement_state(state):
    directory = os.path.dirname(os.path.abspath(ELO_ANNOUNCEMENT_STATE_FILE))
    os.makedirs(directory, exist_ok=True)
    temp_path = ELO_ANNOUNCEMENT_STATE_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, ELO_ANNOUNCEMENT_STATE_FILE)


def build_vs_elo_announcement(current, previous, limit=10):
    """Return (embed, changed); do not invent historic changes on the first post."""
    current_players = current["ratings"]
    old_players = previous["ratings"] if previous else {}
    ranked = get_vs_leaderboard()[:limit]
    if not ranked:
        return None, False

    if previous and current_players == old_players and current["match_count"] == previous.get("match_count"):
        return None, False

    embed = discord.Embed(
        title="MK64 Switch 4P VS — Elo Rankings Update",
        description="Updated standings based on recorded VS results.",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )
    lines = []
    for index, name in enumerate(ranked, 1):
        now = current_players[name]
        delta_text = ""
        if previous and name in old_players:
            delta = now["adjusted"] - float(old_players[name]["adjusted"])
            delta_text = f" ({delta:+.0f})" if abs(delta) >= 0.5 else " (±0)"
        elif previous:
            delta_text = " (new)"
        lines.append(
            f"**{index}. {discord.utils.escape_markdown(name)}** — "
            f"{now['adjusted']:.0f}{delta_text} · {now['matches']} matches"
        )
    embed.add_field(name="Top 10" if limit == 10 else f"Top {limit}", value="\n".join(lines), inline=False)

    if previous:
        added = max(0, current["match_count"] - int(previous.get("match_count", 0)))
        embed.add_field(name="Recorded-match growth", value=f"+{added} since last announcement", inline=False)
        embed.set_footer(text="Elo changes compare adjusted ratings with the previous announcement; recalculations may affect them.")
    else:
        embed.add_field(name="First announcement", value="Baseline established; rating changes will appear on subsequent updates.", inline=False)
    return embed, True


# -----------------------------
# MK64 GP parser config/storage
# -----------------------------

def reject_gp_score_reason(content):
    """Classify obvious non-results for parser audit output."""
    text = html.unescape(content or "")
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "empty_or_attachment_only"

    lower = text.lower()

    if not re.search(r"\d", text):
        return "no_numeric_score"

    if re.search(r"\b(friend code|friend request|available|schedule|scheduling|rules|bracket|challonge|good luck|practice|what time|are you free|rdy|ready)\b", lower):
        return "conversation_or_scheduling"

    if re.search(r"\b(score\?|do we have a score|i need the points|points totaled|totaled up)\b", lower):
        return "score_request_not_result"

    if re.search(r"\b(alot|a lot|not much|ashamed|lol)\b", lower) and not re.search(r"\b\d{1,3}\b", text):
        return "non_numeric_score"

    return "unknown_format"


# Audit only messages that resemble actual GP results; routine conversation is excluded.
# This is intentionally independent of Elo eligibility and does not import a match.
def gp_review_candidate(content, message=None):
    raw = html.unescape(replace_discord_mentions(content or "", message))
    if not raw.strip():
        return False
    if re.search(r"\b(?:casual|unranked|exhibition)\b", raw, re.I):
        return False
    if GP_CUP_PATTERN.search(raw) or GP_TOTAL_PATTERN.search(raw):
        return True
    if re.search(r"(?im)^\s*(?:ranked|:total:|total\s*[:=]|=[ ]*\d{1,3}\s*[-–—]\s*\d{1,3})", raw):
        return True
    # A named match plus multiple numeric cup rows may be a report missing labels.
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    if len(lines) >= 4 and any(gp_result_matchup(x) for x in lines[:3]):
        if sum(bool(GP_BARE_PAIR_PATTERN.fullmatch(x)) for x in lines) >= 3:
            return True
    return False


def gp_review_reason(content, message=None):
    raw = html.unescape(replace_discord_mentions(content or "", message))
    if not raw.strip():
        return "empty_or_attachment_only"
    if re.search(r"\b(?:casual|unranked|exhibition)\b", raw, re.I):
        return "casual_or_unranked"
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    if GP_CUP_PATTERN.search(raw) or GP_TOTAL_PATTERN.search(raw) or any(
        GP_CUP_PATTERN.fullmatch(x) or GP_TOTAL_PATTERN.fullmatch(x) for x in lines
    ):
        matchups = [x for x in lines if gp_result_matchup(x)]
        if not matchups:
            return "missing_or_unrecognized_matchup"
        if len(matchups) != 1:
            return "ambiguous_matchup"
        cups = [tuple(map(int, m.groups())) for x in lines if (m := GP_CUP_PATTERN.fullmatch(x))]
        totals = [tuple(map(int, m.groups())) for x in lines if (m := GP_TOTAL_PATTERN.fullmatch(x))]
        if len(cups) == 4 and len(totals) == 1:
            if tuple(map(sum, zip(*cups))) != totals[0]:
                return "cup_total_mismatch"
        if len(cups) < 4:
            return "missing_or_unrecognized_cup_rows"
        if len(totals) != 1:
            return "missing_or_ambiguous_total"
        return "recognized_structure_failed_validation"
    if re.search(r"\branked\b", raw, re.I):
        return "ranked_result_unrecognized_format"
    return "unrecognized_result_format"


def gp_review_entry(message, segment, channel_name, source_label, segment_index=1):
    """Serializable, evidence-preserving record for human review, never Elo input."""
    raw = html.unescape(replace_discord_mentions(segment or "", message))
    return {
        "message_id": str(message.id),
        "segment_index": segment_index,
        "channel_id": str(message.channel.id),
        "channel_name": channel_name,
        "source": source_label,
        "created_at": message.created_at.isoformat(),
        "jump_url": message.jump_url,
        "author": str(message.author),
        "reason": gp_review_reason(segment, message),
        "content": raw[:6000],
        "content_truncated": len(raw) > 6000,
    }


def write_gp_rejected_audit(entries):
    """Replace the report on a successful full rebuild; never edit GP match data."""
    folder = os.path.dirname(os.path.abspath(GP_REJECTED_AUDIT_FILE))
    os.makedirs(folder, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "truncated": len(entries) > GP_REJECTED_AUDIT_LIMIT,
        "entries": entries[:GP_REJECTED_AUDIT_LIMIT],
    }
    temp_path = GP_REJECTED_AUDIT_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, GP_REJECTED_AUDIT_FILE)
    print(f"GP rejected-result audit: {report['count']} candidate segments → {GP_REJECTED_AUDIT_FILE}")


def normalize_gp_score_text(content, message=None):
    text = replace_discord_mentions(content or "", message)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_gp_score_segment(segment):
    text = segment or ""

    # Remove leading labels so they do not become part of the first player name.
    text = re.sub(r"^\s*Round\s+\d+\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*Extra\s+mode\s*[:\-]\s*", "", text, flags=re.IGNORECASE)

    # Remove non-score parenthetical notes, but preserve scores written as (120).
    text = re.sub(r"\((?!\d{1,3}\))[^)]*\)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# GP reports must contain an identifiable matchup and an unambiguous final result.
# Never infer player names from arbitrary words preceding numbers in conversation.
GP_MATCHUP_PATTERN = re.compile(
    r"^\s*(?P<first>@?[^\n]+?)\s+"
    r"(?:vs\.?|versus|defeats?|defeated|beats?|barely\s+beats?|and|va|-)\s+"
    r"(?P<second>@?[^\n]+?)\s*(?:tie|tied)?\s*$",
    re.IGNORECASE,
)
# Old reports use Mush/Flow/Spec, bare text, colon emojis, or custom Discord emojis.
GP_CUP_PATTERN = re.compile(
    r"^\s*\*?\s*(?:(?:<a?:)?(?:mushroomcup|flowercup|starcup|specialcup|mushroom|flower|special|star|mush|flow|spec)(?::\d+>)?|:(?:mushroomcup|flowercup|starcup|specialcup|mushroom|flower|special|star|mush|flow|spec):)\s*:?\s*"
    r"(\d{1,3})\s*[-–—]\s*(\d{1,3})(?:\s*\[[^\]\n]*\])?\s*$",
    re.IGNORECASE,
)
GP_TOTAL_PATTERN = re.compile(
    r"^\s*(?::total:|<a?:total:\d+>|total\s*[:=]?|=)\s*(\d{1,3})\s*[-–—]\s*(\d{1,3})\s*$",
    re.IGNORECASE,
)
GP_BARE_PAIR_PATTERN = re.compile(r"^\s*(\d{1,3})\s*[-–—]\s*(\d{1,3})\s*$")
GP_SIMPLE_PAIR_PATTERN = re.compile(
    r"^\s*@?(?P<first>[A-Za-z][\w.-]{1,31})\)?\s*"
    r"(?P<score1>\d{1,3})(?:/\d{1,2})?\s+"
    r"@?(?P<second>[A-Za-z][\w.-]{1,31})\)?\s*"
    r"(?P<score2>\d{1,3})(?:/\d{1,2})?\s*"
    r"(?:\([^\n]{0,65}\))?\s*$",
    re.IGNORECASE,
)
GP_NOTES_PATTERN = re.compile(r"^(?:game\s*notes?|notes?)\s*:", re.I)
GP_ROUND_LABEL_PATTERN = re.compile(r"^\s*(?:Round\s+\d+(?:/\d+)?|Extra\s+mode)\s*[:\-]?\s*$", re.I)
GP_RESULT_PREFIX_PATTERN = re.compile(r"^\s*(?:ranked(?:\s+.*)?|for ranking)\s*$", re.I)


def gp_result_matchup(line):
    """Return exactly two plausible competitors from one result header."""
    text = re.sub(r"^\s*ranked\b\s*", "", line.strip(), flags=re.I)
    match = GP_MATCHUP_PATTERN.fullmatch(text)
    if not match:
        return None
    first, second = (match.group(k).strip() for k in ("first", "second"))
    # 'DK challenge' is a format descriptor, not part of the competitor name.
    second = re.sub(r"^(?:DK\s+challenge|DK)\s+(?=@)", "", second, flags=re.I)
    first = re.sub(r"\s+DK\s+challenge$", "", first, flags=re.I)
    # Don't promote commentary, results annotations, or lengthy prose to names.
    for name in (first, second):
        if len(name) > 60 or re.search(r"[.!?]\s+[a-z]{3,}", name, re.I):
            return None
        if re.search(r"\b(?:game notes|total|mushroom|flower|special|ranked|casual)\b", name, re.I):
            return None
    p1, p2 = gp_report_player(first), gp_report_player(second)
    if not p1 or not p2 or p1 == p2 or len(p1) > 32 or len(p2) > 32:
        return None
    return p1, p2

def gp_report_player(name):
    name = re.sub(r"<a?:[A-Za-z0-9_~]+:\d+>|:[A-Za-z0-9_~]+:", " ", name).strip()
    name = re.sub(r"\s*<:[^>]+>", "", name).strip()
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    return clean_score_name(name)


def parse_score_lines(content, message=None, max_score=160):
    """Parse unambiguous two-player GP results; never infer totals or players from prose."""
    raw = html.unescape(replace_discord_mentions(content or "", message))
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    if not lines or re.search(r"\b(?:casual|unranked|exhibition)\b", raw, re.I):
        return {}

    # Scores after a notes block may describe unrelated races; ignore those.
    cutoff = next((i for i, line in enumerate(lines) if GP_NOTES_PATTERN.match(line)), len(lines))
    result_lines = lines[:cutoff]
    cups, totals, bare = [], [], []
    first_result_line = len(result_lines)
    for i, line in enumerate(result_lines):
        c = GP_CUP_PATTERN.fullmatch(line)
        t = GP_TOTAL_PATTERN.fullmatch(line)
        b = GP_BARE_PAIR_PATTERN.fullmatch(line)
        if c:
            cups.append(tuple(map(int, c.groups())))
            first_result_line = min(first_result_line, i)
        elif t:
            totals.append(tuple(map(int, t.groups())))
            first_result_line = min(first_result_line, i)
        elif b:
            bare.append(tuple(map(int, b.groups())))
            first_result_line = min(first_result_line, i)

    matchup_candidates = [x for x in (gp_result_matchup(line) for line in result_lines[:first_result_line]) if x]
    if len(matchup_candidates) != 1:
        # Preserve the exact historical two-player one-line result format.
        if len(result_lines) == 1:
            m = GP_SIMPLE_PAIR_PATTERN.fullmatch(result_lines[0])
            if m:
                p1, p2 = gp_report_player(m.group('first')), gp_report_player(m.group('second'))
                a, b = int(m.group('score1')), int(m.group('score2'))
                if p1 and p2 and p1 != p2 and max(a, b) <= max_score:
                    return {p1: a, p2: b}
        return {}

    p1, p2 = matchup_candidates[0]
    if not cups and len(bare) == 5 and not totals:
        cups, totals = bare[:4], bare[4:]
    elif not cups and len(bare) == 4 and len(totals) == 1:
        cups = bare
    elif len(cups) == 4 and len(bare) == 1 and not totals:
        totals = bare

    # No incomplete, mixed or additional score sets may be silently guessed.
    if len(cups) != 4 or len(totals) != 1:
        return {}
    if len(bare) > (5 if not GP_CUP_PATTERN.search(raw) else 1):
        return {}
    if tuple(map(sum, zip(*cups))) != totals[0]:
        return {}
    a, b = totals[0]
    if max(a, b) > max_score:
        return {}
    return {p1: a, p2: b}


def split_gp_score_segments(content, message=None):
    """Split numbered rounds and genuine consecutive match reports, not commentary."""
    raw = html.unescape(replace_discord_mentions(content or "", message))
    if not raw.strip():
        return []
    lines = raw.splitlines(keepends=True)
    segments = []
    current = []
    has_result = False
    has_matchup = False
    for line in lines:
        stripped = line.strip()
        is_round = bool(GP_ROUND_LABEL_PATTERN.fullmatch(stripped))
        is_matchup = gp_result_matchup(stripped) is not None
        # Start a new result after a completed total, or at an explicit new round.
        if current and ((is_round and has_result) or (is_matchup and has_result and has_matchup)):
            segments.append(''.join(current).strip())
            current = []
            has_result = False
            has_matchup = False
        current.append(line)
        has_matchup |= is_matchup
        has_result |= bool(GP_TOTAL_PATTERN.fullmatch(stripped))
    if current:
        segments.append(''.join(current).strip())
    return [segment for segment in segments if segment]


def make_gp_score_match(scores, source_type="gp_score_report", submatch_index=None):
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

    match = {
        "source_type": source_type,
        "scores": scores,
        "players": [p1, p2],
        "winner": winner,
    }

    if submatch_index is not None:
        match["submatch_index"] = submatch_index

    return match


def parse_gp_score_report_messages(content, message=None):
    """Handle separate rounds; carry a matchup only within a clearly numbered series."""
    matches_found = []
    segments = split_gp_score_segments(content, message)
    series_matchup = None
    for idx, segment in enumerate(segments, 1):
        lines = [line.strip() for line in segment.splitlines() if line.strip()]
        found_headers = [pair for pair in (gp_result_matchup(line) for line in lines) if pair]
        if len(found_headers) == 1:
            series_matchup = found_headers[0]
        elif len(found_headers) > 1:
            series_matchup = None

        scores = parse_score_lines(segment, message, GP_MAX_SCORE)
        # A later round may omit the players when the first round introduced
        # them. Only inherit within an explicitly numbered, continuous series.
        if not scores and series_matchup and not found_headers and idx > 1 and re.search(
            r"(?im)^\s*round\s+\d+(?:/\d+)?\s*[:\-]?\s*$", segment
        ):
            first, second = series_matchup
            scores = parse_score_lines(f"@{first} vs @{second}\n" + segment, message, GP_MAX_SCORE)
        match = make_gp_score_match(
            scores,
            source_type="gp_score_report",
            submatch_index=idx if len(segments) > 1 else None,
        )
        if match:
            matches_found.append(match)
    return matches_found


def clean_gp_elo_name(name):
    name = name.strip()
    name = name.replace("\\", "")
    name = re.sub(r"#\d{1,5}$", "", name)
    name = name.strip(" .,:;|-_")
    return clean_score_name(name)


def parse_gp_elo_player_value(value):
    r"""
    Parse old GP Elo bot field values such as:
    \\Cheech\#4947 (1259.1, +7.0)
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


def parse_gp_messages(content, message=None):
    """Return all GP matches found in a Discord message."""
    ledger_match = parse_gp_elo_ledger_message(message)

    if ledger_match:
        return [ledger_match]

    return parse_gp_score_report_messages(content, message)


def parse_gp_message(content, message=None):
    """Backward-compatible helper for live single-match parsing."""
    parsed = parse_gp_messages(content, message)
    return parsed[0] if parsed else None


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
    Dedupe GP matches without collapsing legitimate same-day rematches.

    Prefer a stable reviewed source_id for manual event records, then Discord
    message ID + submatch index for parsed Discord history.
    """
    source_id = match.get("source_id")
    if source_id:
        return ("source_id", str(source_id))

    message_id = match.get("message_id")
    submatch_index = match.get("submatch_index")

    if message_id:
        return (str(message_id), str(submatch_index or 1))

    players = tuple(sorted(match.get("players", [])))
    scores = tuple(sorted((str(p), str(s)) for p, s in match.get("scores", {}).items()))
    created_at = match.get("created_at", "")
    source_type = match.get("source_type", "unknown")

    return (source_type, created_at, players, scores)


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
    for match in gp_matches:
        normalize_gp_match_players(match)
    processed_gp_message_ids = set(data.get("processed_message_ids", []))

    for player, rating in data.get("ratings", {}).items():
        gp_ratings[player] = rating

    for player, stats in data.get("player_stats", {}).items():
        gp_player_stats[player] = stats

    rebuild_gp_match_keys()


def normalize_gp_match_players(match):
    """Apply canonical aliases to all GP match fields without changing results."""
    scores = match.get("scores", {})
    canonical_scores = {}
    for player, score in scores.items():
        canonical = normalize_name(str(player))
        if not canonical or canonical in canonical_scores:
            raise ValueError(f"GP identity collision in match {match.get('message_id') or match.get('source_id')}: {player}")
        canonical_scores[canonical] = score
    match["scores"] = canonical_scores
    if "players" in match:
        match["players"] = [normalize_name(str(player)) for player in match["players"]]
    if "winner" in match and match["winner"] is not None:
        match["winner"] = normalize_name(str(match["winner"]))
    return match


def record_gp_match(match, message=None, save=True, allow_duplicate_key=False):
    actual_message_id = None

    if message is not None:
        actual_message_id = str(message.id)

        # Do not reject solely because this Discord message was already marked
        # processed. A single message can contain multiple GP results, and each
        # submatch is deduped below by message_id + submatch_index.
        match = attach_metadata(match, message)

    normalize_gp_match_players(match)
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

    # Real GP score reports use actual points. Old Elo ledger entries and
    # manually preserved outcome-only tournament records do not, so avoid
    # mixing synthetic 1-0 values into points totals.
    if match.get("source_type") not in {"gp_elo_ledger", "manual_gp_outcome"}:
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
        scores = match.get("scores", {})

        for p1 in players:
            r1 = q_ratings[p1]
            total_delta = 0

            for p2 in players:
                if p1 == p2:
                    continue

                r2 = q_ratings[p2]
                s1 = scores[p1]
                s2 = scores[p2]

                if s1 > s2:
                    actual = 1.0
                elif s1 < s2:
                    actual = 0.0
                else:
                    actual = 0.5

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

            if match.get("source_type") != "manual_gp_outcome":
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


DEPRECATED_MK64_SOURCE_PREFIXES = (
    "https://yoyoyoshihub.neocities.org/mk64/",
)


def filter_deprecated_sources(sources):
    """Drop superseded MK64 Hub routes now served from awRev."""
    filtered = []
    for source in sources:
        url = normalize_url(source.get("url", ""))
        if any(
            url == prefix.rstrip("/") or url.startswith(prefix)
            for prefix in DEPRECATED_MK64_SOURCE_PREFIXES
        ):
            continue
        filtered.append(source)
    return filtered


def build_sources():
    all_sources = []
    all_sources.extend(load_manual_sources())
    all_sources.extend(load_awrev_root())
    all_sources.extend(load_awrev_guides())
    all_sources.extend(load_yoyoyoshi_hub())
    all_sources.extend(load_mk64_hub())
    all_sources.extend(load_gamefaqs_root())
    all_sources.extend(load_video_root())

    all_sources = filter_deprecated_sources(all_sources)
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
commands_synced = False


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
    existing_match_ids = {str(m.get("message_id")) for m in matches if m.get("message_id")}

    print(f"Scanning VS history in #{channel.name}...")

    async for msg in channel.history(
        limit=None,
        oldest_first=True
    ):
        if msg.author == client.user:
            continue

        scanned += 1

        # Older rejected messages must be reconsidered after parser upgrades.
        # Existing imported matches remain protected from duplicate import.
        if str(msg.id) in existing_match_ids:
            continue

        match = parse_vs_message_with_legacy(msg.content, msg)

        if match:
            # Existing rejected IDs were marked processed by older bot versions.
            # Unmark only the current message after successfully parsing it.
            processed_message_ids.discard(str(msg.id))
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


def possible_gp_ledger_overlap(match, message, window_seconds=600):
    """Flag, but do not merge, a GP score possibly represented in the old Elo ledger.

    Ledger embeds use their own Discord IDs, so message-ID deduplication alone
    cannot detect cross-posts. Within ten minutes, the same two players and
    winner are a review candidate, NOT proof of duplication.
    """
    if message is None or match.get("source_type") != "gp_score_report":
        return None
    match_players = set(match.get("players", ()))
    winner = match.get("winner")
    if len(match_players) != 2 or winner is None:
        return None
    for prior in gp_matches:
        if prior.get("source_type") != "gp_elo_ledger":
            continue
        if set(prior.get("players", ())) != match_players or prior.get("winner") != winner:
            continue
        try:
            stamp = datetime.fromisoformat(prior["created_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            msg_dt = message.created_at
            if msg_dt.tzinfo is None:
                msg_dt = msg_dt.replace(tzinfo=timezone.utc)
            if abs((stamp - msg_dt).total_seconds()) <= window_seconds:
                return prior
        except (TypeError, ValueError, KeyError):
            continue
    return None


async def import_gp_history_for_channel(
    channel_id,
    source_label="supplemental",
    before=None,
    after=None,
    review_entries=None,
):
    channel = client.get_channel(channel_id)

    if channel is None:
        print(f"SKIPPING GP channel not found: {channel_id}")
        return

    if review_entries is None:
        review_entries = []

    scanned = 0
    parsed = 0
    rejected = 0
    duplicates = 0

    earliest_message = None
    latest_message = None
    latest_parsed = None
    latest_recorded = None
    latest_rejected = None

    print(f"Scanning GP history in #{channel.name} ({source_label})...")

    try:
        history_kwargs = {"limit": None, "oldest_first": True}
        if before is not None:
            history_kwargs["before"] = before
        if after is not None:
            history_kwargs["after"] = after

        async for msg in channel.history(**history_kwargs):
            if msg.author == client.user:
                continue

            scanned += 1

            if earliest_message is None:
                earliest_message = msg.created_at

            latest_message = msg.created_at

            if str(msg.id) in processed_gp_message_ids:
                continue

            parsed_matches = parse_gp_messages(msg.content, msg)

            # Preserve the rejection of each candidate segment even where a
            # different segment in the same Discord message was imported.
            # Historical Elo ledger embeds are handled separately and aren't
            # mistaken for free-text score reports.
            if parse_gp_elo_ledger_message(msg) is None:
                parsed_indices = {
                    int(match.get("submatch_index") or 1) for match in parsed_matches
                    if match.get("source_type") == "gp_score_report"
                }
                for segment_idx, segment in enumerate(split_gp_score_segments(msg.content, msg), 1):
                    if segment_idx not in parsed_indices and gp_review_candidate(segment, msg):
                        review_entries.append(gp_review_entry(
                            msg, segment, channel.name, source_label, segment_idx
                        ))

            if parsed_matches:
                latest_parsed = msg.created_at
                message_recorded = 0

                for match in parsed_matches:
                    # The historic Elo ledger contains outcome-only cross-posts
                    # with DIFFERENT Discord IDs. Flag close candidate overlaps
                    # for review instead of silently double-counting them.
                    overlap = possible_gp_ledger_overlap(match, msg)
                    if overlap is not None:
                        segment_idx = int(match.get("submatch_index") or 1)
                        segments = split_gp_score_segments(msg.content, msg)
                        segment = segments[segment_idx - 1] if segment_idx <= len(segments) else msg.content
                        entry = gp_review_entry(msg, segment, channel.name, source_label, segment_idx)
                        entry["reason"] = "possible_ledger_duplicate"
                        entry["possible_ledger_message_id"] = str(overlap.get("message_id", ""))
                        entry["possible_ledger_jump_url"] = overlap.get("jump_url", "")
                        review_entries.append(entry)
                        duplicates += 1
                        continue
                    recorded = record_gp_match(match, message=msg, save=False)

                    if recorded:
                        parsed += 1
                        message_recorded += 1
                        latest_recorded = msg.created_at
                    else:
                        duplicates += 1

                if message_recorded == 0:
                    # The message contained parseable results, but all were duplicates.
                    pass
            else:
                rejected += 1
                latest_rejected = msg.created_at
                # Candidate reports are preserved in the JSON audit, not Elo.

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
    print(f"Earliest scanned message: {earliest_message}")
    print(f"Latest scanned message: {latest_message}")
    print(f"Latest parseable GP message: {latest_parsed}")
    print(f"Latest recorded GP match: {latest_recorded}")
    print(f"Latest rejected GP message: {latest_rejected}")

    if scanned:
        parse_rate = (parsed / scanned) * 100
        print(f"GP parse rate for #{channel.name}: {parse_rate:.2f}%")


async def import_gp_history():
    # Rebuild GP from Discord history every startup so source priority remains deterministic.
    reset_gp_state_for_rebuild()
    gp_review_entries = []

    await import_gp_history_for_channel(
        ELO_GP_MATCH_RESULTS_CHANNEL_ID,
        source_label="primary",
        review_entries=gp_review_entries,
    )

    # Preserve the established historical source-priority model. CampKart 3 is
    # inserted at its actual place in the post-legacy chronology so later GP
    # activity is rated after it.
    for channel_id in GP_SUPPLEMENTAL_CHANNEL_IDS:
        await import_gp_history_for_channel(
            channel_id,
            source_label="supplemental-pre-campkart3",
            before=GP_MANUAL_EVENT_CUTOFF,
            review_entries=gp_review_entries,
        )

    import_manual_gp_results(save=False)

    for channel_id in GP_SUPPLEMENTAL_CHANNEL_IDS:
        await import_gp_history_for_channel(
            channel_id,
            source_label="supplemental-post-campkart3",
            after=GP_MANUAL_EVENT_CUTOFF,
            review_entries=gp_review_entries,
        )

    save_gp_data()
    # Do not publish an incomplete audit if a channel failed; those channels
    # still produce their normal diagnostics above.
    write_gp_rejected_audit(gp_review_entries)


def load_manual_event_results():
    """Load reviewed non-Discord tournament results used by the Elo systems."""
    if not os.path.exists(MANUAL_EVENT_RESULTS_FILE):
        print(f"{MANUAL_EVENT_RESULTS_FILE} not found. Skipping manual event results.")
        return {"vs": [], "gp": []}

    with open(MANUAL_EVENT_RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "vs": data.get("vs", []),
        "gp": data.get("gp", []),
    }


def manual_source_ids(records):
    return {
        str(match.get("source_id"))
        for match in records
        if match.get("source_id")
    }


def make_manual_vs_match(entry):
    scores = {
        normalize_name(name): int(score)
        for name, score in entry.get("scores", {}).items()
    }

    if len(scores) not in (3, 4):
        raise ValueError(f"Manual VS result must have 3 or 4 players: {entry.get('source_id')}")

    placements = sorted(scores.items(), key=lambda x: -x[1])

    return {
        "source_type": "manual_event_vs",
        "source_id": entry["source_id"],
        "event": entry.get("event", ""),
        "round": entry.get("round", ""),
        "event_order": entry.get("event_order"),
        "created_at": entry.get("created_at", ""),
        "date_precision": entry.get("date_precision", ""),
        "source_url": entry.get("source_url", ""),
        "scores": scores,
        "placements": placements,
    }


def make_manual_gp_match(entry):
    winner = normalize_name(entry["winner"])
    loser = normalize_name(entry["loser"])

    if not winner or not loser or winner == loser:
        raise ValueError(f"Invalid manual GP result: {entry.get('source_id')}")

    return {
        "source_type": "manual_gp_outcome",
        "source_id": entry["source_id"],
        "event": entry.get("event", ""),
        "round": entry.get("round", ""),
        "event_order": entry.get("event_order"),
        "created_at": entry.get("created_at", ""),
        "date_precision": entry.get("date_precision", ""),
        "source_url": entry.get("source_url", ""),
        # GP Elo uses win/loss outcome, not margin. These synthetic values are
        # deliberately excluded from points-for/against statistics.
        "scores": {winner: 1, loser: 0},
        "players": [winner, loser],
        "winner": winner,
    }


def import_manual_vs_results(save=True):
    data = load_manual_event_results()
    existing_vs_ids = manual_source_ids(matches)
    vs_added = 0

    for entry in sorted(data["vs"], key=lambda x: x.get("event_order", 0)):
        source_id = str(entry.get("source_id", ""))
        if not source_id or source_id in existing_vs_ids:
            continue

        match = make_manual_vs_match(entry)
        record_vs_match(match, save=False)
        existing_vs_ids.add(source_id)
        vs_added += 1

    if save and vs_added:
        save_vs_data()

    print(f"Imported manual VS event results: {vs_added}")
    return vs_added


def import_manual_gp_results(save=True):
    data = load_manual_event_results()
    gp_added = 0

    for entry in sorted(data["gp"], key=lambda x: x.get("event_order", 0)):
        match = make_manual_gp_match(entry)
        if record_gp_match(match, save=False):
            gp_added += 1

    if save and gp_added:
        save_gp_data()

    print(f"Imported manual GP event results: {gp_added}")
    return gp_added


# -----------------------------
# Events
# -----------------------------

@client.event
async def on_ready():
    global stream_tracker_started, vs_history_imported, gp_history_imported, commands_synced

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

    # Keep slash commands guild-scoped for fast updates and remove stale global
    # copies left by older versions of the bot. A global + guild command with the
    # same name can appear twice in Discord's command picker.
    if not commands_synced:
        tree.copy_global_to(guild=MY_GUILD)

        # Delete previously registered global commands (including the old
        # search-style /mk64) from Discord. The guild copies remain intact.
        tree.clear_commands(guild=None)
        removed_globals = await tree.sync()
        print(f"Global slash commands after cleanup: {len(removed_globals)}")

        synced = await tree.sync(guild=MY_GUILD)
        commands_synced = True

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

        # Keep an untouched backup before the first historical VS recovery scan.
        # Existing manual/event data and GP records remain unchanged.
        vs_backup_file = os.path.join(
            os.path.dirname(os.path.abspath(DATA_FILE)),
            "vs_data.pre_legacy_recovery.json",
        )
        if os.path.isfile(DATA_FILE) and not os.path.exists(vs_backup_file):
            import shutil
            shutil.copy2(DATA_FILE, vs_backup_file)
            print(f"Saved VS pre-recovery backup: {vs_backup_file}")

        await import_vs_history()
        import_manual_vs_results(save=False)

        # Recalculate the full stored VS history with score-aware tie handling.
        rebuild_vs_state_from_matches(save=True)

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

        match = parse_vs_message_with_legacy(content, message)

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

        parsed_matches = parse_gp_messages(content, message)

        if parsed_matches:
            recorded_any = False

            for match in parsed_matches:
                recorded = record_gp_match(match, message=message)
                recorded_any = recorded_any or recorded

            if recorded_any:
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

@tree.command(name="commands", description="Show available bot commands.")
@app_commands.guild_only()
async def commands(interaction: discord.Interaction):
    # Read commands from the live guild command tree rather than maintaining a
    # separate list. on_ready copies global definitions into the guild tree.
    registered = tree.get_commands(guild=MY_GUILD)
    public_commands = []
    for command in registered:
        # A default permission restriction (e.g., administrator=True) or an
        # explicitly admin-only description keeps the command off the member list.
        # The latter also covers existing commands with runtime admin checks.
        permissions = getattr(command, "default_permissions", None)
        description = (getattr(command, "description", "") or "").strip()
        if permissions is not None or description.lower().startswith("admin-only:"):
            continue
        public_commands.append(command)

    public_commands.sort(key=lambda command: command.name)
    if not public_commands:
        await interaction.response.send_message(
            "No public slash commands are currently registered.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Bot Commands",
        description="",
        color=discord.Color.blue(),
    )
    # Discord allows 25 embed fields; a single description fits the current
    # command set, with a safe fallback if more commands are added later.
    lines = [
        f"**/{command.name}** — {command.description or 'No description available.'}"
        for command in public_commands
    ]
    chunks = []
    current = ""
    for line in lines:
        if current and len(current) + len(line) + 1 > 3900:
            chunks.append(current)
            current = ""
        current += ("\n" if current else "") + line
    if current:
        chunks.append(current)

    embed.description = chunks[0]
    await interaction.response.send_message(embed=embed)
    for chunk in chunks[1:]:
        await interaction.followup.send(embed=discord.Embed(
            description=chunk, color=discord.Color.blue()
        ))


@tree.command(name="announceelo", description="Admin-only: publish updated 4P VS Elo rankings to Discord.")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def announceelo(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can announce rankings.", ephemeral=True)
        return
    if not vs_history_imported:
        await interaction.response.send_message("VS history is still initializing. Try again after import finishes.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    # Explicit channel setting is optional. Default is the configured VS channel.
    channel = interaction.guild.get_channel(ELO_ANNOUNCEMENT_CHANNEL_ID)
    if channel is None:
        try:
            channel = await client.fetch_channel(ELO_ANNOUNCEMENT_CHANNEL_ID)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            await interaction.followup.send("Announcement channel is unavailable; check ELO_ANNOUNCEMENT_CHANNEL_ID.", ephemeral=True)
            return
    if getattr(channel, "guild", None) is None or channel.guild.id != interaction.guild_id:
        await interaction.followup.send("Announcement channel must belong to this server.", ephemeral=True)
        return
    try:
        previous = load_elo_announcement_state()
        current = snapshot_vs_announcement()
        embed, changed = build_vs_elo_announcement(current, previous)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        await interaction.followup.send(f"Cannot prepare announcement: {exc}", ephemeral=True)
        return
    if not changed:
        await interaction.followup.send("No new Elo changes since the last announcement; nothing posted.", ephemeral=True)
        return
    if embed is None:
        await interaction.followup.send("No eligible VS players to announce.", ephemeral=True)
        return
    try:
        post = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"Could not publish announcement: {exc}", ephemeral=True)
        return

    # Save only after a confirmed send, so failed posts are retried safely.
    current["published_at"] = datetime.now(timezone.utc).isoformat()
    current["discord_message_id"] = str(post.id)
    try:
        save_elo_announcement_state(current)
    except OSError as exc:
        await interaction.followup.send(
            f"Announcement posted, but its state could not be saved ({exc}). "
            "Fix persistent storage before posting again to avoid duplicates.",
            ephemeral=True,
        )
        return
    await interaction.followup.send(f"Published the VS Elo update in {channel.mention}.", ephemeral=True)


@tree.command(name="vsleaderboard", description="Show VS standings.")
@app_commands.describe(limit="Number of players to show, from 1 to 20")
async def vsleaderboard(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(format_vs_leaderboard(limit))


@tree.command(name="vsrank", description="Show a player's VS rating and match totals.")
@app_commands.describe(player="Player name or alias")
async def vsrank(interaction: discord.Interaction, player: str):
    await interaction.response.send_message(format_vs_rank(player))


@tree.command(name="vsstats", description="Show VS match and player totals.")
async def vsstats(interaction: discord.Interaction):
    await interaction.response.send_message(format_vs_stats())


@tree.command(name="vsquarter", description="Show VS standings for a quarter.")
@app_commands.describe(
    quarter="Quarter in YYYY-Q# format, like 2026-Q2. Leave blank for current quarter.",
    limit="Number of players to show, from 1 to 20"
)
async def vsquarter(interaction: discord.Interaction, quarter: str = "", limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(
        format_quarterly_vs_leaderboard(quarter or None, limit)
    )


@tree.command(name="gpleaderboard", description="Show GP standings.")
@app_commands.describe(limit="Number of players to show, from 1 to 20")
async def gpleaderboard(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(format_gp_leaderboard(limit))


@tree.command(name="gprank", description="Show a player's GP rating and record.")
@app_commands.describe(player="Player name or alias")
async def gprank(interaction: discord.Interaction, player: str):
    await interaction.response.send_message(format_gp_rank(player))


@tree.command(name="gpstats", description="Show GP match and player totals.")
async def gpstats(interaction: discord.Interaction):
    await interaction.response.send_message(format_gp_stats())


@tree.command(name="gpquarter", description="Show GP standings for a quarter.")
@app_commands.describe(
    quarter="Quarter in YYYY-Q# format, like 2026-Q2. Leave blank for current quarter.",
    limit="Number of players to show, from 1 to 20"
)
async def gpquarter(interaction: discord.Interaction, quarter: str = "", limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(
        format_quarterly_gp_leaderboard(quarter or None, limit)
    )


@tree.command(name="playerpage", description="Show a player profile from match records.")
@app_commands.describe(player="Player name or alias")
async def playerpage(interaction: discord.Interaction, player: str):
    await interaction.response.send_message(format_player_continuity_profile(player))


@tree.command(name="communityhistory", description="Show community milestones and match totals.")
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


@tree.command(name="serverstats", description="Show message counts by channel.")
@app_commands.describe(limit="Number of channels to show, from 1 to 20")
async def serverstats(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(format_server_stats(interaction.guild, limit))


@tree.command(name="userstats", description="Show the most active members by message count.")
@app_commands.describe(limit="Number of users to show, from 1 to 20")
async def userstats(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(limit, 20))
    await interaction.response.send_message(format_user_stats(interaction.guild, limit))


@tree.command(name="monthlystats", description="Show monthly message counts.")
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