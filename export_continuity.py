"""
export_continuity.py

Standalone MK64 Switch continuity exporter.

Run after your VS/GP dedupe + JSON export scripts. This does not connect to
Discord and does not require Flask or discord.py.

Inputs expected in the current folder:
- vs_data.json
- gp_data.json
- optional compiled_sources.json
- optional discord_stats.sqlite3

Outputs:
- public_mk64_continuity/community_history.json
- public_mk64_continuity/community_history.html
- public_mk64_continuity/players/index.json
- public_mk64_continuity/players/index.html
- public_mk64_continuity/players/<player>.json
- public_mk64_continuity/players/<player>.html
"""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

# -----------------------------
# Config
# -----------------------------

VS_DATA_FILE = "vs_data.json"
GP_DATA_FILE = "gp_data.json"
SOURCES_FILE = "compiled_sources.json"
STATS_DB_FILE = "discord_stats.sqlite3"
EXPORT_DIR = "public_mk64_continuity"

AWREV_MK64_URL = "https://awrev.com/mk64/"
AWREV_MK64_HISTORY_URL = "https://awrev.com/mk64/history.php"
AWREV_MK64_ABOUT_URL = "https://awrev.com/mk64/about-mk64-switch.php"
AWREV_MK64_PLAYERS_URL = "https://awrev.com/mk64/players.php"
DISCORD_INVITE_URL = "https://discord.gg/hebCNMbKme"
YOUTUBE_URL = "https://www.youtube.com/@YoyoYoshi1"

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
    "blazeup": "martin",
    "fx": "fx64",
    "urbanoutlaw": "urban",
}

PLAYER_NOTES: dict[str, dict[str, Any]] = {
    "gumby": {
        "display_name": "Gumby",
        "roles": ["Founder", "administrator", "organizer", "recruiter", "competitor"],
        "summary": "Gumby founded the MK64 Switch Discord in July 2022 and helped build the community through recruitment, onboarding, organization, events, and competition.",
        "links": [AWREV_MK64_HISTORY_URL],
    },
    "spacedcowboy": {
        "display_name": "SpacedCowboy",
        "roles": ["Co-founder", "competitor", "CampKart champion"],
        "summary": "SpacedCowboy co-founded the MK64 Switch Discord and became one of the community's major early competitive figures, including in-person CampKart success.",
        "links": [AWREV_MK64_HISTORY_URL, "https://awrev.com/mk64/campkart2025.php"],
    },
    "yoyoyoshi": {
        "display_name": "YoyoYoshi",
        "roles": ["Co-founder", "administrator", "webmaster", "broadcaster", "community historian"],
        "summary": "YoyoYoshi co-founded the MK64 Switch Discord and maintains the MK64 Switch website, rankings, records, broadcasts, player documentation, and community history.",
        "links": [AWREV_MK64_URL, YOUTUBE_URL],
    },
    "gg": {
        "display_name": "GG",
        "roles": ["Co-founder", "administrator", "competitor"],
        "summary": "GG co-founded the MK64 Switch Discord and has been a major competitor and community figure in the organized Nintendo Switch Online scene.",
        "links": [AWREV_MK64_HISTORY_URL],
    },
    "patalus": {
        "display_name": "Patalus",
        "roles": ["Administrator", "competitor", "tournament champion"],
        "summary": "Patalus joined the admin/mod team in 2023 and became a major tournament and multiplayer competitor in the MK64 Switch community.",
        "links": [AWREV_MK64_HISTORY_URL],
    },
}

COMMUNITY_MILESTONES: list[dict[str, Any]] = [
    {
        "date": "2022-07-15",
        "title": "MK64 Switch Discord founded",
        "summary": "Gumby launched the MK64 Switch Discord with SpacedCowboy, YoyoYoshi, and GG to organize Mario Kart 64 Nintendo Switch Online multiplayer matches.",
        "tags": ["founding", "discord", "community"],
    },
    {
        "date": "2022-09-05",
        "title": "First 2P Grand Prix tournament begins",
        "summary": "The first 2P Grand Prix Double Elimination Tournament helped establish organized competitive play in the early MK64 Switch community.",
        "tags": ["gp", "tournament", "early history"],
    },
    {
        "date": "2023-04-22",
        "title": "2P GP Elo rankings introduced",
        "summary": "The community introduced Elo rankings for 2P Grand Prix competition, turning match results into long-term competitive records.",
        "tags": ["gp", "elo", "rankings"],
    },
    {
        "date": "2023-07-29",
        "title": "Patalus joins admin/mod team",
        "summary": "Patalus joined the Discord admin/mod team as the community continued expanding through tournaments, rankings, and organized multiplayer events.",
        "tags": ["administration", "community"],
    },
    {
        "date": "2024-09-06",
        "title": "CampKart 1 begins",
        "summary": "CampKart 1 became the first major in-person championship benchmark for the MK64 Switch community.",
        "tags": ["campkart", "in-person", "tournament"],
    },
    {
        "date": "2025-08-30",
        "title": "CampKart 2 begins",
        "summary": "CampKart 2 continued the community's in-person tradition with Grand Prix and 4P VS championship events.",
        "tags": ["campkart", "in-person", "tournament"],
    },
    {
        "date": "2026-04-25",
        "title": "MK64 Switch Hub launches",
        "summary": "YoyoYoshi launched the MK64 Switch Multiplayer Hub as a centralized website for tournament history, rankings, media, records, events, and resources.",
        "tags": ["website", "history", "rankings"],
    },
    {
        "date": "2026-06-12",
        "title": "MK64 Switch website moves to awRev",
        "summary": "The MK64 Switch website moved to awRev.com/mk64 as a stronger permanent home for rankings, player pages, match history, tournament coverage, media, and community documentation.",
        "tags": ["awrev", "migration", "institution"],
    },
]

# -----------------------------
# Helpers
# -----------------------------

def normalize_name(name: str) -> str:
    name = str(name or "").lower().strip()
    name = re.sub(r"[^a-z0-9_]", "", name)
    return ALIASES.get(name, name)


def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def short_date(value: str | None) -> str:
    dt = parse_dt(value)
    return dt.date().isoformat() if dt else "unknown"


def date_range(items: list[dict[str, Any]]) -> tuple[str, str]:
    dates = []
    for item in items:
        dt = parse_dt(item.get("created_at"))
        if dt:
            dates.append(dt)
    if not dates:
        return "unknown", "unknown"
    return min(dates).date().isoformat(), max(dates).date().isoformat()


def normalize_source_url(url: str) -> str:
    return str(url or "").strip().rstrip("/")

# -----------------------------
# Loading bot records
# -----------------------------

def load_records() -> dict[str, Any]:
    vs_data = load_json(VS_DATA_FILE, {})
    gp_data = load_json(GP_DATA_FILE, {})
    sources = load_json(SOURCES_FILE, [])

    return {
        "vs_matches": vs_data.get("matches", []),
        "vs_ratings": vs_data.get("ratings", {}),
        "vs_player_stats": vs_data.get("player_stats", {}),
        "gp_matches": gp_data.get("matches", []),
        "gp_ratings": gp_data.get("ratings", {}),
        "gp_player_stats": gp_data.get("player_stats", {}),
        "sources": sources,
    }


def combined_player_names(records: dict[str, Any]) -> list[str]:
    names = set(PLAYER_NOTES.keys())
    names.update(normalize_name(n) for n in records["vs_player_stats"].keys())
    names.update(normalize_name(n) for n in records["gp_player_stats"].keys())
    for match in records["vs_matches"]:
        names.update(normalize_name(n) for n in match.get("scores", {}).keys())
    for match in records["gp_matches"]:
        names.update(normalize_name(n) for n in match.get("players", []))
    return sorted(n for n in names if n)


def get_player_matches(records: dict[str, Any], player: str):
    clean = normalize_name(player)
    vs = [m for m in records["vs_matches"] if clean in {normalize_name(p) for p in m.get("scores", {}).keys()}]
    gp = [m for m in records["gp_matches"] if clean in {normalize_name(p) for p in m.get("players", [])}]
    return vs, gp


def build_profile(records: dict[str, Any], player: str) -> dict[str, Any]:
    clean = normalize_name(player)
    note = PLAYER_NOTES.get(clean, {})
    vs, gp = get_player_matches(records, clean)
    first_seen, last_seen = date_range(vs + gp)

    vs_stats = records["vs_player_stats"].get(clean, {})
    gp_stats = records["gp_player_stats"].get(clean, {})

    profile = {
        "player_id": clean,
        "display_name": note.get("display_name", clean),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_note": "Generated from MK64 bot records, Discord-derived match data, manual community notes, and awRev continuity metadata. Review before publication.",
        "roles": note.get("roles", []),
        "summary": note.get("summary", "No manual biography note has been added yet."),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "links": note.get("links", []),
        "vs": {
            "matches": int(vs_stats.get("matches", 0)),
            "points": int(vs_stats.get("points", 0)),
            "elo_raw": round(float(records["vs_ratings"][clean])) if clean in records["vs_ratings"] else None,
            "recent_matches": [
                {
                    "date": short_date(m.get("created_at")),
                    "scores": m.get("scores", {}),
                    "jump_url": m.get("jump_url", ""),
                }
                for m in sorted(vs, key=lambda x: x.get("created_at", ""), reverse=True)[:10]
            ],
        },
        "gp": {
            "matches": int(gp_stats.get("matches", 0)),
            "record": f"{gp_stats.get('wins', 0)}-{gp_stats.get('losses', 0)}-{gp_stats.get('ties', 0)}",
            "elo_raw": round(float(records["gp_ratings"][clean])) if clean in records["gp_ratings"] else None,
            "recent_matches": [
                {
                    "date": short_date(m.get("created_at")),
                    "players": m.get("players", []),
                    "winner": m.get("winner"),
                    "scores": m.get("scores", {}),
                    "jump_url": m.get("jump_url", ""),
                }
                for m in sorted(gp, key=lambda x: x.get("created_at", ""), reverse=True)[:10]
            ],
        },
    }
    profile["total_recorded_matches"] = profile["vs"]["matches"] + profile["gp"]["matches"]
    return profile

# -----------------------------
# HTML rendering
# -----------------------------

def link_list(links: list[str]) -> str:
    if not links:
        return "<li>TBD</li>"
    return "".join(f'<li><a href="{html.escape(link)}">{html.escape(link)}</a></li>' for link in links)


def render_player_html(profile: dict[str, Any]) -> str:
    title = html.escape(profile["display_name"])
    roles = ", ".join(html.escape(r) for r in profile.get("roles", [])) or "TBD"
    summary = html.escape(profile.get("summary", ""))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title} - MK64 Continuity Profile</title>
</head>
<body>
<h1>{title}</h1>
<p><strong>Roles:</strong> {roles}</p>
<p><strong>First seen in bot records:</strong> {html.escape(profile['first_seen'])}</p>
<p><strong>Latest bot record:</strong> {html.escape(profile['last_seen'])}</p>
<p>{summary}</p>

<h2>Competition Summary</h2>
<ul>
  <li>VS matches: {profile['vs']['matches']}</li>
  <li>VS Elo: {profile['vs']['elo_raw'] or 'TBD'}</li>
  <li>GP matches: {profile['gp']['matches']}</li>
  <li>GP record: {html.escape(profile['gp']['record'])}</li>
  <li>GP Elo: {profile['gp']['elo_raw'] or 'TBD'}</li>
</ul>

<h2>Related Links</h2>
<ul>{link_list(profile.get('links', []))}</ul>

<p><em>{html.escape(profile['source_note'])}</em></p>
</body>
</html>
"""


def render_player_index_html(index: dict[str, Any]) -> str:
    rows = []
    for player in sorted(index["players"], key=lambda p: p["display_name"].lower()):
        pid = html.escape(player["player_id"])
        name = html.escape(player["display_name"])
        rows.append(
            f'<tr><td><a href="{pid}.html">{name}</a></td>'
            f'<td>{html.escape(player["first_seen"])}</td>'
            f'<td>{html.escape(player["last_seen"])}</td>'
            f'<td>{player["vs_matches"]}</td>'
            f'<td>{player["gp_matches"]}</td>'
            f'<td>{player["total_recorded_matches"]}</td></tr>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>MK64 Continuity Player Index</title></head>
<body>
<h1>MK64 Continuity Player Index</h1>
<p>Generated from MK64 bot records and manual continuity notes. Review before publication.</p>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Player</th><th>First Seen</th><th>Latest Record</th><th>VS Matches</th><th>GP Matches</th><th>Total</th></tr>
{''.join(rows)}
</table>
</body>
</html>
"""


def render_history_html(history: dict[str, Any]) -> str:
    items = []
    for m in history["milestones"]:
        tags = ", ".join(m.get("tags", []))
        items.append(
            f'<li><strong>{html.escape(m["date"])} - {html.escape(m["title"])}</strong>'
            f'<br>{html.escape(m["summary"])}'
            f'<br><em>{html.escape(tags)}</em></li>'
        )
    stats = history["stats"]
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>MK64 Switch Community History Draft</title></head>
<body>
<h1>MK64 Switch Community History Draft</h1>
<p><em>{html.escape(history['source_note'])}</em></p>
<p>Bot records currently include {stats['vs_matches']} VS matches, {stats['gp_matches']} GP matches, {stats['tracked_vs_players']} VS players, {stats['tracked_gp_players']} GP players, and {stats.get('indexed_discord_messages', 0)} indexed Discord messages.</p>
<ol>{''.join(items)}</ol>
</body>
</html>
"""

# -----------------------------
# Export
# -----------------------------

def indexed_discord_message_count() -> int:
    if not os.path.exists(STATS_DB_FILE):
        return 0
    try:
        with sqlite3.connect(STATS_DB_FILE) as conn:
            row = conn.execute("SELECT COUNT(*) FROM message_stats").fetchone()
            return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def write_profiles(records: dict[str, Any], export_dir: str = EXPORT_DIR) -> tuple[int, str]:
    player_dir = os.path.join(export_dir, "players")
    os.makedirs(player_dir, exist_ok=True)

    profiles = []
    for name in combined_player_names(records):
        profile = build_profile(records, name)
        if not profile["roles"] and profile["total_recorded_matches"] == 0:
            continue
        profiles.append(profile)
        with open(os.path.join(player_dir, f"{profile['player_id']}.json"), "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        with open(os.path.join(player_dir, f"{profile['player_id']}.html"), "w", encoding="utf-8") as f:
            f.write(render_player_html(profile))

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(profiles),
        "source_note": "Draft player index generated from MK64 bot records and manual continuity notes. Review before publication.",
        "players": [
            {
                "player_id": p["player_id"],
                "display_name": p["display_name"],
                "first_seen": p["first_seen"],
                "last_seen": p["last_seen"],
                "vs_matches": p["vs"]["matches"],
                "gp_matches": p["gp"]["matches"],
                "total_recorded_matches": p["total_recorded_matches"],
            }
            for p in profiles
        ],
    }

    with open(os.path.join(player_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    with open(os.path.join(player_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_player_index_html(index))

    return len(profiles), player_dir


def write_history(records: dict[str, Any], export_dir: str = EXPORT_DIR) -> str:
    os.makedirs(export_dir, exist_ok=True)
    history = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_note": "Draft digital historiography generated from manual milestones and bot records. Review before publication.",
        "milestones": COMMUNITY_MILESTONES,
        "stats": {
            "vs_matches": len(records["vs_matches"]),
            "gp_matches": len(records["gp_matches"]),
            "tracked_vs_players": len(records["vs_player_stats"]),
            "tracked_gp_players": len(records["gp_player_stats"]),
            "indexed_discord_messages": indexed_discord_message_count(),
        },
        "core_links": {
            "website": AWREV_MK64_URL,
            "about": AWREV_MK64_ABOUT_URL,
            "history": AWREV_MK64_HISTORY_URL,
            "players": AWREV_MK64_PLAYERS_URL,
            "discord": DISCORD_INVITE_URL,
        },
    }

    json_path = os.path.join(export_dir, "community_history.json")
    html_path = os.path.join(export_dir, "community_history.html")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_history_html(history))
    return html_path


def main() -> None:
    records = load_records()
    player_count, player_dir = write_profiles(records)
    history_path = write_history(records)
    print("Continuity export complete.")
    print(f"Player profiles exported: {player_count}")
    print(f"Player directory: {player_dir}")
    print(f"Community history: {history_path}")


if __name__ == "__main__":
    main()
