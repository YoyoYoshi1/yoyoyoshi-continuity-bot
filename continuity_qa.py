"""
continuity_qa.py

Standalone MK64 Switch continuity QA checker.

Run after your VS/GP export scripts and after export_continuity.py.
This does not connect to Discord and does not require Flask or discord.py.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

VS_DATA_FILE = "vs_data.json"
GP_DATA_FILE = "gp_data.json"
SOURCES_FILE = "compiled_sources.json"
EXPORT_DIR = "public_mk64_continuity"

REQUIRED_MK64_URLS = [
    "https://awrev.com/mk64/",
    "https://awrev.com/mk64/history.php",
    "https://awrev.com/mk64/about-mk64-switch.php",
]

PLAYER_NOTE_NAMES = {
    "gumby",
    "spacedcowboy",
    "yoyoyoshi",
    "gg",
    "patalus",
}

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


def normalize_name(name: str) -> str:
    name = str(name or "").lower().strip()
    name = re.sub(r"[^a-z0-9_]", "", name)
    return ALIASES.get(name, name)


def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_url(url: str) -> str:
    return str(url or "").strip().rstrip("/")


def issue(level: str, message: str) -> dict[str, str]:
    return {"level": level, "message": message}


def load_records() -> dict[str, Any]:
    vs = load_json(VS_DATA_FILE, {})
    gp = load_json(GP_DATA_FILE, {})
    sources = load_json(SOURCES_FILE, [])
    return {
        "vs_matches": vs.get("matches", []),
        "vs_player_stats": vs.get("player_stats", {}),
        "gp_matches": gp.get("matches", []),
        "gp_player_stats": gp.get("player_stats", {}),
        "sources": sources,
    }


def combined_activity(records: dict[str, Any]) -> dict[str, int]:
    activity: dict[str, int] = {}
    for name, stats in records["vs_player_stats"].items():
        clean = normalize_name(name)
        activity[clean] = activity.get(clean, 0) + int(stats.get("matches", 0))
    for name, stats in records["gp_player_stats"].items():
        clean = normalize_name(name)
        activity[clean] = activity.get(clean, 0) + int(stats.get("matches", 0))
    return activity


def run_qa(records: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    if not os.path.exists(VS_DATA_FILE):
        findings.append(issue("error", f"Missing {VS_DATA_FILE}. Run the VS pipeline first."))
    if not os.path.exists(GP_DATA_FILE):
        findings.append(issue("warning", f"Missing {GP_DATA_FILE}. GP continuity will be incomplete."))

    sources = records["sources"]
    source_urls = {normalize_url(src.get("url", "")) for src in sources if isinstance(src, dict)}

    old_mk64 = [u for u in source_urls if "yoyoyoshihub.neocities.org/mk64" in u]
    if old_mk64:
        findings.append(issue("warning", f"Found {len(old_mk64)} MK64 source URL(s) still pointing to Neocities."))

    for url in REQUIRED_MK64_URLS:
        if normalize_url(url) not in source_urls and os.path.exists(SOURCES_FILE):
            findings.append(issue("warning", f"compiled_sources.json does not include required MK64 source: {url}"))

    activity = combined_activity(records)
    high_activity_missing = [
        (name, count)
        for name, count in activity.items()
        if count >= 20 and name not in PLAYER_NOTE_NAMES
    ]
    if high_activity_missing:
        sample = ", ".join(
            f"{name} ({count})"
            for name, count in sorted(high_activity_missing, key=lambda x: -x[1])[:15]
        )
        findings.append(issue("notice", "High-activity players without manual continuity notes: " + sample))

    player_index = os.path.join(EXPORT_DIR, "players", "index.json")
    history_json = os.path.join(EXPORT_DIR, "community_history.json")
    if not os.path.exists(player_index):
        findings.append(issue("notice", "Player index export not found. Run python export_continuity.py."))
    if not os.path.exists(history_json):
        findings.append(issue("notice", "Community history export not found. Run python export_continuity.py."))

    if records["vs_matches"] and not records["vs_player_stats"]:
        findings.append(issue("warning", "VS matches exist but VS player_stats is empty."))
    if records["gp_matches"] and not records["gp_player_stats"]:
        findings.append(issue("warning", "GP matches exist but GP player_stats is empty."))

    founder_missing = [name for name in PLAYER_NOTE_NAMES if name not in activity or activity.get(name, 0) == 0]
    if founder_missing:
        findings.append(issue("notice", "Manual-note players with no recorded match activity in current data: " + ", ".join(sorted(founder_missing))))

    return findings


def print_report(findings: list[dict[str, str]]) -> None:
    print("MK64 Continuity QA")
    print("==================")
    if not findings:
        print("No major continuity issues found.")
        return
    for f in findings:
        print(f"[{f['level'].upper()}] {f['message']}")


def main() -> None:
    records = load_records()
    print_report(run_qa(records))


if __name__ == "__main__":
    main()
