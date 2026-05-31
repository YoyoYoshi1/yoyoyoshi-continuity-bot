print("BOT FILE TEST — NEW VERSION LOADED")

import os
import re
import json
import random
import requests
import discord
import statistics
import sqlite3

from bs4 import BeautifulSoup
from discord import app_commands
from dotenv import load_dotenv
from urllib.parse import urljoin
from collections import defaultdict
from datetime import datetime, timezone

from streams import start_stream_tracker


# -----------------------------
# Environment / startup config
# -----------------------------

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_RAW = os.getenv("DISCORD_GUILD_ID")
MK64_VS_CHANNEL_ID_RAW = os.getenv("MK64_VS_CHANNEL_ID", "997416976051871854")

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env")

if not GUILD_ID_RAW:
    raise RuntimeError("Missing DISCORD_GUILD_ID in .env")

GUILD_ID = int(GUILD_ID_RAW)
MK64_VS_CHANNEL_ID = int(MK64_VS_CHANNEL_ID_RAW)
MY_GUILD = discord.Object(id=GUILD_ID)


# -----------------------------
# MK64 VS parser config/storage
# -----------------------------

K_FACTOR = 32
MIN_MATCHES = 5
MAX_SCORE = 60
DATA_FILE = "vs_data.json"
STATS_DB_FILE = "discord_stats.sqlite3"

matches = []
ratings = defaultdict(lambda: 1000)
player_stats = defaultdict(lambda: {
    "matches": 0,
    "points": 0
})
last_message_id = None
processed_message_ids = set()

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
            server="mk64",
            site="YoyoYoshi Hub",
            content_type="hub",
            game="Mario Kart 64",
            title="MK64 Switch Multiplayer Hub",
            url="https://yoyoyoshihub.neocities.org/mk64/",
            tags=["mk64", "mario kart 64", "switch", "rankings", "tournaments", "records"],
            aliases=["mk64", "mario kart 64", "mk64 switch", "mk64 hub"],
            description="Central MK64 Switch hub for tournament history, rankings, media, records, events, and community resources.",
            source_type="static",
            author="YoyoYoshi",
            era="modern"
        )
    ] + scrape_links(
        root_url="https://yoyoyoshihub.neocities.org/mk64/",
        server="mk64",
        site="YoyoYoshi Hub",
        base_tags=["mk64", "mario kart 64", "switch", "hub"],
        aliases=["mk64", "mario kart 64"],
        description_prefix="MK64 Hub page",
        game="Mario Kart 64"
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

async def import_vs_history():
    global last_message_id

    channel = client.get_channel(MK64_VS_CHANNEL_ID)

    if channel is None:
        print("ERROR: MK64 VS channel not found")
        return

    scanned = 0
    parsed = 0
    rejected = 0

    after_msg = None

    if last_message_id:
        try:
            after_msg = await channel.fetch_message(int(last_message_id))
            print(f"Resuming VS import after message ID: {last_message_id}")
        except discord.NotFound:
            print("Last VS message not found. Falling back to full scan.")
        except discord.HTTPException:
            print("Could not fetch last VS message. Falling back to full scan.")

    print("Scanning MK64 VS channel history...")

    async for msg in channel.history(
        limit=None,
        oldest_first=True,
        after=after_msg
    ):
        if msg.author == client.user:
            continue

        scanned += 1
        match = parse_vs_message(msg.content, msg)

        if match:
            if record_vs_match(match, message=msg, save=False):
                parsed += 1
            else:
                mark_vs_processed(msg.id, save=False)
        else:
            rejected += 1
            mark_vs_processed(msg.id, save=False)

    save_vs_data()

    print("MK64 VS history scan complete.")
    print(f"Scanned: {scanned}")
    print(f"Parsed matches: {parsed}")
    print(f"Rejected messages: {rejected}")
    print(f"Saved matches: {len(matches)}")
    print(f"Last processed message ID: {last_message_id}")


# -----------------------------
# Events
# -----------------------------

@client.event
async def on_ready():
    global stream_tracker_started, vs_history_imported

    init_stats_db()

    print(f"Loaded {len(SOURCES)} sources.")
    print("Saved compiled_sources.json.")
    print(f"Logged in as {client.user}")

    print("MK64_VS_CHANNEL_ID =", MK64_VS_CHANNEL_ID)

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

    if not stream_tracker_started:
        start_stream_tracker(client)
        stream_tracker_started = True


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    record_message_stat(message)

    if message.channel.id != MK64_VS_CHANNEL_ID:
        return

    content = message.content.strip()

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

    if content == "!serverstats":
        await message.channel.send(format_server_stats(message.guild))
        return

    if content == "!userstats":
        await message.channel.send(format_user_stats(message.guild))
        return

    if content == "!monthlystats":
        await message.channel.send(format_monthly_stats(message.guild))
        return

    match = parse_vs_message(content, message)

    if match:
        recorded = record_vs_match(match, message=message)

        if recorded:
            await message.add_reaction("✅")
    else:
        mark_vs_processed(message.id)


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
        "• `/backfill_stats` — admin-only Discord message stats backfill\n"
        "• `/serverstats` — Discord message totals by channel\n"
        "• `/userstats` — Discord message totals by user\n"
        "• `/monthlystats` — Discord message totals by month"
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

    await interaction.response.defer(ephemeral=True)

    scanned, inserted, skipped = await backfill_message_stats(interaction.guild)

    msg = (
        f"Backfill complete.\n"
        f"Scanned messages: {scanned}\n"
        f"New rows inserted: {inserted}"
    )

    if skipped:
        msg += "\nSkipped channels: " + ", ".join(skipped[:20])

    await interaction.followup.send(msg, ephemeral=True)


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

client.run(TOKEN)