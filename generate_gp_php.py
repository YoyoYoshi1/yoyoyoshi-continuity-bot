import json
import os
from datetime import datetime

DATA_DIR = "public/mk64/gp/data"
OUTPUT_DIR = "public/mk64/gp"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_json(filename):
    with open(os.path.join(DATA_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)


def write(filename, content):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote {path}")


def fmt_date(value):
    if not value:
        return "Unknown"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except Exception:
        return "Unknown"


def php_escape(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


leaderboard = load_json("leaderboard.json")
players = load_json("players.json")
matches = load_json("matches.json")
summary = load_json("summary.json")

generated = datetime.now().strftime("%B %d, %Y")

match_dates = [m.get("created_at") for m in matches if m.get("created_at")]
coverage_start = fmt_date(min(match_dates)) if match_dates else "Unknown"
coverage_end = fmt_date(max(match_dates)) if match_dates else "Unknown"


GP_JSON_LD = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    "name": "Mario Kart 64 Switch Grand Prix Elo Rankings",
    "description": (
        "Competitive Mario Kart 64 Nintendo Switch Online Grand Prix rankings, "
        "weighted Elo ratings, player records, match results, and quarterly seasonal history."
    ),
    "creator": {
        "@type": "Person",
        "name": "YoyoYoshi"
    },
    "about": [
        "Mario Kart 64",
        "Nintendo Switch Online",
        "competitive gaming",
        "Grand Prix rankings",
        "Elo ratings",
        "MK64 Switch community",
        "Mario Kart 64 Switch Online"
    ],
    "temporalCoverage": f"{coverage_start} – {coverage_end}",
    "keywords": (
        "Mario Kart 64 Switch, MK64 Switch, competitive MK64, "
        "Nintendo Switch Online league, GP Elo rankings, Grand Prix rankings, "
        "MK64 Switch GP leaderboard"
    )
}


def page(current_page, title, description, crumb_title, crumb_url, body, extra_script="", json_ld=None):
    json_ld_html = ""
    if json_ld:
        json_ld_html = f"""
<script type="application/ld+json">
{json.dumps(json_ld, indent=2)}
</script>
"""

    return f"""<?php
$currentPage = '{php_escape(current_page)}';

$pageTitle = '{php_escape(title)}';
$metaDescription = '{php_escape(description)}';

$crumbTitle = '{php_escape(crumb_title)}';
$crumbUrl = '{php_escape(crumb_url)}';
$contentAriaLabel = '{php_escape(crumb_title)}';

require_once __DIR__ . '/../includes/header.php';
?>

{json_ld_html}
{body}

<section class="content-box">
  <div class="news-board-title">Page Info</div>
  <p class="note">Last updated: {generated}</p>
</section>

{extra_script}

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
"""


nav_links = """
<p>
  <a href="/mk64/gp/">GP Rankings Home</a> |
  <a href="/mk64/gp/leaderboard.php">Leaderboard</a> |
  <a href="/mk64/gp/players.php">All Players</a> |
  <a href="/mk64/gp/matches.php">Match Log</a> |
  <a href="/mk64/gp/quarters.php">Quarterly GP Seasons</a>
</p>
"""


leaderboard_rows = "\n".join(
    f"""
    <tr>
      <td>{p["rank"]}</td>
      <td>{p["player"]}</td>
      <td>{p["elo"]}</td>
      <td>{p["raw_elo"]}</td>
      <td>{p["matches"]}</td>
      <td>{p["wins"]}-{p["losses"]}-{p["ties"]}</td>
    </tr>
    """
    for p in leaderboard
)

players_rows = "\n".join(
    f"""
    <tr>
      <td>{p["player"]}</td>
      <td>{"Yes" if p["eligible"] else "No"}</td>
      <td>{p["elo"]}</td>
      <td>{p["raw_elo"]}</td>
      <td>{p["matches"]}</td>
      <td>{p["wins"]}-{p["losses"]}-{p["ties"]}</td>
      <td>{p["points_for"]}</td>
      <td>{p["points_against"]}</td>
    </tr>
    """
    for p in players
)

recent_matches = matches[::-1]

match_rows = "\n".join(
    f"""
    <tr>
      <td>{m["match_id"]}</td>
      <td>{fmt_date(m.get("created_at"))}</td>
      <td>{"<br>".join([x["player"] + " — " + str(x["score"]) + " (" + str(x.get("delta", "—")) + ")" for x in m["players"]])}</td>
      <td>{m.get("winner") or "Tie"}</td>
      <td>{'<a href="' + m.get("jump_url", "#") + '" target="_blank" rel="noreferrer">Discord</a>' if m.get("jump_url") else "—"}</td>
    </tr>
    """
    for m in recent_matches
)


explanation = f"""
<section class="content-box">
  <div class="news-board-title">How These Rankings Work</div>

  <div class="info-box">
    <strong>Coverage Period</strong><br>
    These results currently cover parsed GP match records from {coverage_start} through {coverage_end}.
  </div>

  <p>
    The leaderboard uses a 1v1 Elo model for Grand Prix matches. Wins, losses, and ties update each player's rating.
  </p>

  <p>
    The displayed rating is confidence-weighted. Newer or low-sample players are pulled closer to 1000
    until they have more recorded matches.
  </p>

  <p>
    Players must have at least {summary["min_matches"]} parsed matches to appear on the main leaderboard.
    All players still appear on the full player list.
  </p>
</section>
"""


index_body = f"""
<article class="content-box">
  <div class="news-board-title">MK64 Switch GP Rankings</div>
  <div class="intro-box-body">
    <p>
      <strong>This section tracks Mario Kart 64 Switch Grand Prix results parsed from Discord and legacy GP Elo records.</strong>
    </p>

    <p>
      It turns scattered match history into a lasting ranking archive, player record, match log, and seasonal Elo chronology.
    </p>

    <p>
      These pages help preserve the competitive Grand Prix history of the MK64 Switch community and make the ratings easier to find, verify, and archive outside Discord.
    </p>

    <p class="note">
      Total matches: {summary["total_matches"]}. Eligible players: {summary["eligible_players"]}.
      Coverage: {coverage_start} – {coverage_end}.
    </p>

    {nav_links}
  </div>
</article>

{explanation}
"""


leaderboard_body = f"""
{explanation}

<section class="content-box">
  <div class="news-board-title">GP Leaderboard</div>

  <p>
    This leaderboard ranks eligible Mario Kart 64 Switch Grand Prix players using confidence-weighted Elo ratings.
  </p>

  <p class="note">
    Weighted Elo leaderboard. Median Elo: {summary["median_elo"]}.
  </p>

  {nav_links}

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Player</th>
          <th>Weighted Elo</th>
          <th>Raw Elo</th>
          <th>Matches</th>
          <th>Record</th>
        </tr>
      </thead>
      <tbody>
        {leaderboard_rows}
      </tbody>
    </table>
  </div>
</section>
"""


players_body = f"""
<section class="content-box">
  <div class="news-board-title">All GP Players</div>

  <p>
    This table includes every parsed GP player, including players who have not yet reached the minimum match threshold.
  </p>

  <p>
    Player records help preserve match volume, wins, losses, ties, points for, points against, and Elo ratings across the MK64 Switch Grand Prix scene.
  </p>

  <p class="note">
    Coverage: {coverage_start} – {coverage_end}. Last updated: {generated}.
  </p>

  {nav_links}

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Player</th>
          <th>Eligible</th>
          <th>Weighted Elo</th>
          <th>Raw Elo</th>
          <th>Matches</th>
          <th>Record</th>
          <th>Points For</th>
          <th>Points Against</th>
        </tr>
      </thead>
      <tbody>
        {players_rows}
      </tbody>
    </table>
  </div>
</section>
"""


matches_body = f"""
<section class="content-box">
  <div class="news-board-title">GP Match Log</div>

  <p>
    This log shows all parsed Grand Prix matches, with dates, scores, Elo changes, winners, and direct Discord source links where available.
  </p>

  <p>
    The match log provides the source record behind the GP Elo rankings and helps make the MK64 Switch Grand Prix history publicly auditable.
  </p>

  <p class="note">
    Full parsed coverage: {coverage_start} – {coverage_end}. Last updated: {generated}.
  </p>

  {nav_links}

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Match ID</th>
          <th>Date</th>
          <th>Players / Elo Change</th>
          <th>Winner</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {match_rows}
      </tbody>
    </table>
  </div>
</section>
"""


quarters_body = f"""
<section class="content-box">
  <div class="news-board-title">Quarterly GP Seasons</div>

  <p>
    Browse quarter-only seasonal GP Elo rankings. Each quarter recalculates Elo using only matches played during that quarter.
  </p>

  <p>
    Quarterly snapshots help preserve seasonal form, historical standings, and competitive development across the MK64 Switch Grand Prix community.
  </p>

  <p class="note">
    Coverage: {coverage_start} – {coverage_end}. Last updated: {generated}.
  </p>

  {nav_links}

  <div class="info-box">
    <label for="quarter-select"><strong>Select Quarter:</strong></label>
    <select id="quarter-select">
      <option value="">Loading quarters...</option>
    </select>
  </div>
</section>

<section class="content-box">
  <div class="news-board-title" id="quarter-heading">Quarter Season</div>
  <div id="quarter-summary" class="note">Choose a quarter to view seasonal rankings.</div>
  <br>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Player</th>
          <th>Weighted Elo</th>
          <th>Raw Elo</th>
          <th>Matches</th>
          <th>Record</th>
        </tr>
      </thead>
      <tbody id="quarter-table">
        <tr><td colspan="6">Loading quarterly data...</td></tr>
      </tbody>
    </table>
  </div>
</section>
"""


QUARTERS_SCRIPT = """
<script>
(function() {
  var select = document.getElementById("quarter-select");
  var table = document.getElementById("quarter-table");
  var heading = document.getElementById("quarter-heading");
  var summary = document.getElementById("quarter-summary");

  function setError(message) {
    select.innerHTML = '<option value="">Unavailable</option>';
    table.innerHTML = '<tr><td colspan="6">' + message + '</td></tr>';
    summary.innerHTML = message;
  }

  function renderQuarter(entry) {
    fetch("/mk64/gp/data/quarters/" + entry.file)
      .then(function(response) {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(function(data) {
        heading.innerHTML = "Quarter Season: " + data.quarter;
        summary.innerHTML =
          "Matches in this quarter: " + data.total_matches +
          ". Eligible players: " + data.eligible_players +
          ". Median Elo: " + (data.median_elo === null ? "N/A" : data.median_elo) + ".";

        if (!data.leaderboard || !data.leaderboard.length) {
          table.innerHTML = '<tr><td colspan="6">No eligible players for this quarter.</td></tr>';
          return;
        }

        table.innerHTML = data.leaderboard.map(function(p) {
          return '<tr>' +
            '<td>' + p.rank + '</td>' +
            '<td>' + p.player + '</td>' +
            '<td>' + p.elo + '</td>' +
            '<td>' + p.raw_elo + '</td>' +
            '<td>' + p.matches + '</td>' +
            '<td>' + p.wins + '-' + p.losses + '-' + p.ties + '</td>' +
          '</tr>';
        }).join("");
      })
      .catch(function() {
        table.innerHTML = '<tr><td colspan="6">This quarter file could not be loaded.</td></tr>';
      });
  }

  fetch("/mk64/gp/data/quarters/index.json")
    .then(function(response) {
      if (!response.ok) throw new Error();
      return response.json();
    })
    .then(function(index) {
      if (!index.length) {
        setError("No quarterly GP seasons are available yet.");
        return;
      }

      select.innerHTML = index.map(function(q, i) {
        return '<option value="' + i + '">' + q.quarter + '</option>';
      }).join("");

      select.value = index.length - 1;
      renderQuarter(index[index.length - 1]);

      select.addEventListener("change", function() {
        renderQuarter(index[Number(select.value)]);
      });
    })
    .catch(function() {
      setError("Quarterly index could not be loaded. Run export_gp_quarterly.py first.");
    });
})();
</script>
"""


write("index.php", page(
    "gp",
    "MK64 Switch GP Rankings",
    "Mario Kart 64 Switch Grand Prix rankings, weighted Elo leaderboard, player stats, match log, and quarterly GP seasons.",
    "GP Rankings",
    "/mk64/gp/",
    index_body,
    json_ld=GP_JSON_LD
))

write("leaderboard.php", page(
    "gp-leaderboard",
    "MK64 Switch GP Leaderboard",
    "Mario Kart 64 Switch weighted Elo leaderboard for Grand Prix play.",
    "GP Leaderboard",
    "/mk64/gp/leaderboard.php",
    leaderboard_body,
    json_ld=GP_JSON_LD
))

write("players.php", page(
    "gp-players",
    "MK64 Switch GP Players",
    "Mario Kart 64 Switch GP player stats, Elo ratings, records, and point totals.",
    "GP Players",
    "/mk64/gp/players.php",
    players_body,
    json_ld=GP_JSON_LD
))

write("matches.php", page(
    "gp-matches",
    "MK64 Switch GP Match Log",
    "Mario Kart 64 Switch GP match log with dates, scores, Elo changes, and Discord source links.",
    "GP Match Log",
    "/mk64/gp/matches.php",
    matches_body,
    json_ld=GP_JSON_LD
))

write("quarters.php", page(
    "gp-quarters",
    "MK64 Switch Quarterly GP Seasons",
    "Mario Kart 64 Switch quarter-only GP Elo seasons and historical seasonal rankings.",
    "GP Quarterly Seasons",
    "/mk64/gp/quarters.php",
    quarters_body,
    QUARTERS_SCRIPT,
    GP_JSON_LD
))

print("GP PHP generation complete.")