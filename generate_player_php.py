"""
generate_player_php.py

Generate awRev MK64 player PHP pages from continuity JSON exports.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

INPUT_DIR = Path("public_mk64_continuity/players")
OUTPUT_DIR = Path("generated_mk64_php/players")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def php_header(title: str, description: str = "", current_page: str = "players") -> str:
    title_e = e(title)
    desc_e = e(description or title)
    current_e = e(current_page)

    return f"""<?php
$pageTitle = '{title_e}';
$pageDescription = '{desc_e}';
$currentPage = '{current_e}';

require_once __DIR__ . '/../includes/header.php';
?>

<div class="layout">
<?php require_once __DIR__ . '/../includes/sidebar.php'; ?>

<main class="column main-content">
"""


def php_footer() -> str:
    return """
</main>
</div>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
"""


def render_link_list(links: list[str]) -> str:
    if not links:
        return "<li>TBD</li>"

    items = []
    for link in links:
        link_e = e(link)
        items.append(f'<li><a href="{link_e}">{link_e}</a></li>')

    return "\n".join(items)


def render_recent_vs(profile: dict[str, Any]) -> str:
    matches = profile.get("vs", {}).get("recent_matches", [])

    if not matches:
        return "<p>No recent VS matches in continuity export.</p>"

    rows = []

    for m in matches:
        scores = m.get("scores", {})
        score_text = ", ".join(f"{e(p)} {e(s)}" for p, s in scores.items())
        url = m.get("jump_url", "")
        source = f' <a href="{e(url)}">source</a>' if url else ""

        rows.append(
            f"<tr><td>{e(m.get('date', 'unknown'))}</td><td>{score_text}{source}</td></tr>"
        )

    return f"""<table class="data-table">
<thead><tr><th>Date</th><th>Scores</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>"""


def render_recent_gp(profile: dict[str, Any]) -> str:
    matches = profile.get("gp", {}).get("recent_matches", [])

    if not matches:
        return "<p>No recent GP matches in continuity export.</p>"

    rows = []

    for m in matches:
        scores = m.get("scores", {})
        score_text = ", ".join(f"{e(p)} {e(s)}" for p, s in scores.items())
        winner = e(m.get("winner") or "TBD")
        url = m.get("jump_url", "")
        source = f' <a href="{e(url)}">source</a>' if url else ""

        rows.append(
            f"<tr><td>{e(m.get('date', 'unknown'))}</td><td>{winner}</td><td>{score_text}{source}</td></tr>"
        )

    return f"""<table class="data-table">
<thead><tr><th>Date</th><th>Winner</th><th>Scores</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>"""


def render_player_page(profile: dict[str, Any]) -> str:
    name = profile.get("display_name", profile.get("player_id", "Player"))
    roles = profile.get("roles", [])
    role_text = ", ".join(e(r) for r in roles) if roles else "TBD"

    title = f"{name} - MK64 Switch Player Profile"
    description = (
        f"MK64 Switch continuity profile for {name}, including VS, GP, "
        f"match history, roles, and community notes."
    )

    vs = profile.get("vs", {})
    gp = profile.get("gp", {})

    return f"""{php_header(title, description, "players")}
<section class="panel">
  <div class="section-heading">{e(name)}</div>
  <p><strong>Roles:</strong> {role_text}</p>
  <p><strong>First seen in bot records:</strong> {e(profile.get('first_seen', 'unknown'))}</p>
  <p><strong>Latest bot record:</strong> {e(profile.get('last_seen', 'unknown'))}</p>
  <p>{e(profile.get('summary', 'No manual biography note has been added yet.'))}</p>
</section>

<section class="panel">
  <div class="section-heading">Competition Summary</div>
  <ul>
    <li>VS matches: {e(vs.get('matches', 0))}</li>
    <li>VS Elo: {e(vs.get('elo_raw') or 'TBD')}</li>
    <li>GP matches: {e(gp.get('matches', 0))}</li>
    <li>GP record: {e(gp.get('record', '0-0-0'))}</li>
    <li>GP Elo: {e(gp.get('elo_raw') or 'TBD')}</li>
    <li>Total recorded matches: {e(profile.get('total_recorded_matches', 0))}</li>
  </ul>
</section>

<section class="panel">
  <div class="section-heading">Recent VS Matches</div>
  {render_recent_vs(profile)}
</section>

<section class="panel">
  <div class="section-heading">Recent GP Matches</div>
  {render_recent_gp(profile)}
</section>

<section class="panel">
  <div class="section-heading">Related Links</div>
  <ul>{render_link_list(profile.get('links', []))}</ul>
</section>

<section class="panel">
  <div class="section-heading">Source Note</div>
  <p><em>{e(profile.get('source_note', 'Generated from MK64 continuity exports. Review before publication.'))}</em></p>
</section>
{php_footer()}"""


def render_index(index: dict[str, Any]) -> str:
    players = index.get("players", [])
    rows = []

    sorted_players = sorted(
        players,
        key=lambda x: (
            -int(x.get("total_recorded_matches", 0)),
            str(x.get("display_name", "")).lower()
        )
    )

    for p in sorted_players:
        pid = e(p.get("player_id", ""))
        name = e(p.get("display_name", pid))

        rows.append(
            f'<tr><td><a href="{pid}.php">{name}</a></td>'
            f'<td>{e(p.get("first_seen", "unknown"))}</td>'
            f'<td>{e(p.get("last_seen", "unknown"))}</td>'
            f'<td>{e(p.get("vs_matches", 0))}</td>'
            f'<td>{e(p.get("gp_matches", 0))}</td>'
            f'<td>{e(p.get("total_recorded_matches", 0))}</td></tr>'
        )

    return f"""{php_header(
        'MK64 Switch Player Profiles',
        'MK64 Switch player profiles generated from VS, GP, and continuity records.',
        'players'
    )}
<section class="panel">
  <div class="section-heading">MK64 Switch Player Profiles</div>
  <p>Draft player profile pages generated from MK64 bot records, match data, and continuity notes. Review before publication.</p>
  <p>Generated profiles: {e(index.get('count', len(players)))}</p>
</section>

<section class="panel">
  <div class="section-heading">Player Index</div>
  <table class="data-table">
    <thead>
      <tr>
        <th>Player</th>
        <th>First Seen</th>
        <th>Latest Record</th>
        <th>VS Matches</th>
        <th>GP Matches</th>
        <th>Total</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
{php_footer()}"""


def generate(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    index = load_json(input_dir / "index.json", {})

    if not index:
        raise FileNotFoundError(
            f"Missing {input_dir / 'index.json'}. Run python export_continuity.py first."
        )

    (output_dir / "index.php").write_text(render_index(index), encoding="utf-8")

    count = 0

    for player in index.get("players", []):
        pid = str(player.get("player_id", "")).strip()

        if not pid:
            continue

        profile = load_json(input_dir / f"{pid}.json", {})

        if not profile:
            continue

        (output_dir / f"{pid}.php").write_text(
            render_player_page(profile),
            encoding="utf-8"
        )

        count += 1

    print("Player PHP generation complete.")
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Player pages generated: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate MK64 player PHP pages from continuity exports."
    )

    parser.add_argument(
        "--input",
        default=str(INPUT_DIR),
        help="Continuity players export directory"
    )

    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR),
        help="Output directory for generated PHP"
    )

    args = parser.parse_args()

    generate(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()