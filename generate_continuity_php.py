"""
generate_continuity_php.py

Generate awRev MK64 continuity/history PHP pages from continuity JSON exports.

Run after:
- python export_continuity.py

Inputs:
- public_mk64_continuity/community_history.json

Outputs by default:
- generated_mk64_php/history/index.php
- generated_mk64_php/history/community-history.php

Copy/upload generated files into:
- /mk64/history/

This script is intentionally standalone and does not require Discord, Flask, or discord.py.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

INPUT_FILE = Path("public_mk64_continuity/community_history.json")
OUTPUT_DIR = Path("generated_mk64_php/history")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def php_header(title: str, description: str = "") -> str:
    title_e = e(title)
    desc_e = e(description or title)
    return f"""<?php
$page_title = '{title_e}';
$page_description = '{desc_e}';
?>
<?php if (file_exists(__DIR__ . '/../header.php')) include __DIR__ . '/../header.php'; ?>
<main class=\"content\">
"""


def php_footer() -> str:
    return """
</main>
<?php if (file_exists(__DIR__ . '/../footer.php')) include __DIR__ . '/../footer.php'; ?>
"""


def year_from_date(date_text: str) -> str:
    if not date_text or len(date_text) < 4:
        return "Unknown"
    return date_text[:4]


def render_core_links(core_links: dict[str, str]) -> str:
    if not core_links:
        return "<li>TBD</li>"
    labels = {
        "website": "MK64 Switch Website",
        "about": "About MK64 Switch",
        "history": "Community History",
        "players": "Players",
        "discord": "Discord",
    }
    items = []
    for key, url in core_links.items():
        label = labels.get(key, key.title())
        items.append(f'<li><a href="{e(url)}">{e(label)}</a></li>')
    return "\n".join(items)


def render_timeline(history: dict[str, Any]) -> str:
    milestones = sorted(history.get("milestones", []), key=lambda m: str(m.get("date", "")))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in milestones:
        grouped[year_from_date(str(m.get("date", "")))].append(m)

    sections = []
    for year in sorted(grouped.keys()):
        items = []
        for m in grouped[year]:
            tags = ", ".join(m.get("tags", []))
            items.append(
                f"""<li>
<strong>{e(m.get('date', 'unknown'))} — {e(m.get('title', 'Untitled'))}</strong><br>
{e(m.get('summary', ''))}<br>
<em>{e(tags)}</em>
</li>"""
            )
        sections.append(f"<h3>{e(year)}</h3>\n<ol>{''.join(items)}</ol>")
    return "\n".join(sections)


def render_stats(history: dict[str, Any]) -> str:
    stats = history.get("stats", {})
    rows = [
        ("VS matches", stats.get("vs_matches", 0)),
        ("GP matches", stats.get("gp_matches", 0)),
        ("Tracked VS players", stats.get("tracked_vs_players", 0)),
        ("Tracked GP players", stats.get("tracked_gp_players", 0)),
        ("Indexed Discord messages", stats.get("indexed_discord_messages", 0)),
    ]
    return "".join(f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>" for label, value in rows)


def render_history_page(history: dict[str, Any]) -> str:
    return f"""{php_header('MK64 Switch Community History Draft', 'Digital historiography draft for the MK64 Switch competitive community.')}
<section class=\"panel\">
  <div class=\"section-heading\">MK64 Switch Community History Draft</div>
  <p><em>{e(history.get('source_note', 'Generated from MK64 continuity exports. Review before publication.'))}</em></p>
  <p>This page converts MK64 Switch bot records, manual milestones, and continuity metadata into a reviewable community-history draft.</p>
</section>

<section class=\"panel\">
  <div class=\"section-heading\">Current Bot Record Coverage</div>
  <table class=\"data-table\">
    <tbody>{render_stats(history)}</tbody>
  </table>
</section>

<section class=\"panel\">
  <div class=\"section-heading\">Timeline</div>
  {render_timeline(history)}
</section>

<section class=\"panel\">
  <div class=\"section-heading\">Core Links</div>
  <ul>{render_core_links(history.get('core_links', {}))}</ul>
</section>
{php_footer()}"""


def render_index(history: dict[str, Any]) -> str:
    milestones = history.get("milestones", [])
    stats = history.get("stats", {})
    return f"""{php_header('MK64 Switch Continuity', 'MK64 Switch continuity, community history, and institutional-memory exports.')}
<section class=\"panel\">
  <div class=\"section-heading\">MK64 Switch Continuity</div>
  <p>This section collects generated continuity pages for the Mario Kart 64 Nintendo Switch Online competitive community.</p>
  <p>Current export: {e(len(milestones))} milestones, {e(stats.get('vs_matches', 0))} VS matches, {e(stats.get('gp_matches', 0))} GP matches, and {e(stats.get('indexed_discord_messages', 0))} indexed Discord messages.</p>
</section>

<section class=\"panel\">
  <div class=\"section-heading\">Pages</div>
  <ul>
    <li><a href=\"community-history.php\">Community History Draft</a></li>
    <li><a href=\"../players/\">Player Profiles</a></li>
  </ul>
</section>
{php_footer()}"""


def generate(input_file: Path, output_dir: Path) -> None:
    history = load_json(input_file, {})
    if not history:
        raise FileNotFoundError(f"Missing {input_file}. Run python export_continuity.py first.")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.php").write_text(render_index(history), encoding="utf-8")
    (output_dir / "community-history.php").write_text(render_history_page(history), encoding="utf-8")

    print("Continuity PHP generation complete.")
    print(f"Input: {input_file}")
    print(f"Output: {output_dir}")
    print("Pages generated: index.php, community-history.php")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MK64 continuity/history PHP pages from continuity exports.")
    parser.add_argument("--input", default=str(INPUT_FILE), help="community_history.json path")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Output directory for generated PHP")
    args = parser.parse_args()
    generate(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
