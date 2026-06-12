import json
import os
from datetime import datetime

DATA_DIR = "public/mk64/vs/data"
OUTPUT_DIR = "public/mk64/vs"

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


leaderboard = load_json("leaderboard.json")
players = load_json("players.json")
matches = load_json("matches.json")
summary = load_json("summary.json")

generated = datetime.now().strftime("%B %d, %Y")

match_dates = [m.get("created_at") for m in matches if m.get("created_at")]
coverage_start = fmt_date(min(match_dates)) if match_dates else "Unknown"
coverage_end = fmt_date(max(match_dates)) if match_dates else "Unknown"


VS_JSON_LD = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    "name": "Mario Kart 64 Switch VS Elo Rankings",
    "description": (
        "Competitive Mario Kart 64 Nintendo Switch Online VS rankings, "
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
        "Elo ratings",
        "VS league rankings",
        "MK64 Switch community",
        "Mario Kart 64 Switch Online"
    ],
    "temporalCoverage": f"{coverage_start} – {coverage_end}",
    "keywords": (
        "Mario Kart 64 Switch, MK64 Switch, competitive MK64, "
        "Nintendo Switch Online league, Elo rankings, VS rankings, "
        "MK64 Switch VS leaderboard"
    )
}


def php_escape(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


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
  <a href="/mk64/vs/">VS Rankings Home</a> |
  <a href="/mk64/vs/leaderboard.php">Leaderboard</a> |
  <a href="/mk64/vs/players.php">All Players</a> |
  <a href="/mk64/vs/matches.php">Match Log</a> |
  <a href="/mk64/vs/quarters.php">Quarterly History</a>
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
      <td>{p["avg_points"]}</td>
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
      <td>{p["points"]}</td>
      <td>{p["avg_points"]}</td>
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
      <td>{"<br>".join([str(x["place"]) + ". " + x["player"] + " — " + str(x["score"]) for x in m["placements"]])}</td>
      <td>{'<a href="' + m.get("jump_url", "#") + '" target="_blank" rel="noreferrer">Discord</a>' if m.get("jump_url") else "—"}</td>
    </tr>
    """
    for m in recent_matches
)


explanation = f"""
<section class="content-box">
  <div class="news-board-title">How These Competitive Rankings Work</div>

  <div class="info-box">
    <strong>Coverage Period</strong><br>
    These results currently cover parsed Mario Kart 64 Nintendo Switch Online VS match posts from {coverage_start} through {coverage_end}.
  </div>

  <p>
    These rankings document competitive Mario Kart 64 Switch VS play. The leaderboard uses a multi-player Elo model.
    Each VS match is treated as a set of head-to-head outcomes: finishing above another player counts as a win
    against that player, and finishing below counts as a loss.
  </p>

  <p>
    The displayed rating is confidence-weighted. Newer or low-sample players are pulled closer to 1000
    until they have more recorded matches.
  </p>

  <p>
    Players must have at least {summary["min_matches"]} parsed matches to appear on the main competitive leaderboard.
    All players still appear on the full player list.
  </p>
</section>
"""


index_body = f"""
<article class="content-box">
  <div class="news-board-title">Competitive MK64 Switch VS Rankings</div>
  <div class="intro-box-body">
    <p>
      <strong>This section documents the competitive Mario Kart 64 Nintendo Switch Online VS scene.</strong>
    </p>

    <p>
      It converts Discord-based league results into public weighted Elo rankings, player records,
      match logs, and historical seasonal snapshots.
    </p>

    <p>
      The MK64 Switch community features organized leagues, Elo rankings, tournaments, streams,
      and historical records. These rankings help preserve and document that competitive history.
    </p>

    <p>
      The goal is to make the community's competitive structure easier to find, understand, verify,
      archive, and recognize through public web pages rather than Discord posts alone.
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
  <div class="news-board-title">Competitive VS Elo Leaderboard</div>

  <p>
    This leaderboard ranks eligible Mario Kart 64 Switch VS players using confidence-weighted Elo ratings.
    It is intended to show competitive standings for organized MK64 Switch Online play.
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
          <th>Avg Pts</th>
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
  <div class="news-board-title">All Competitive VS Players</div>

  <p>
    This table includes every parsed Mario Kart 64 Switch VS player, including players who have not yet reached
    the minimum match threshold for the main competitive Elo leaderboard.
  </p>

  <p>
    Player records help preserve participation history, total points, average points, match volume, and Elo ratings
    across the MK64 Switch competitive scene.
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
          <th>Total Pts</th>
          <th>Avg Pts</th>
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
  <div class="news-board-title">Competitive VS Match Log</div>

  <p>
    This log preserves parsed Mario Kart 64 Switch VS matches, including dates, placements, scores,
    and direct Discord source links where available.
  </p>

  <p>
    The match log provides the source record behind the competitive Elo rankings and helps make the
    MK64 Switch Online league history publicly auditable.
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
          <th>Placements</th>
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
  <div class="news-board-title">Quarterly Competitive Elo History</div>

  <p>
    Browse quarter-only seasonal Elo rankings for competitive Mario Kart 64 Switch VS play.
    Each quarter recalculates Elo using only matches played during that quarter.
  </p>

  <p>
    Quarterly snapshots help preserve historical form, seasonal standings, and competitive development
    across the MK64 Switch Online community.
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
  <div class="news-board-title" id="quarter-heading">Quarter Snapshot</div>
  <div id="quarter-summary" class="note">Choose a quarter to view historical rankings.</div>
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
          <th>Avg Pts</th>
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
  var quarterIndex = [];

  function setError(message) {
    select.innerHTML = '<option value="">Unavailable</option>';
    table.innerHTML = '<tr><td colspan="6">' + message + '</td></tr>';
    summary.innerHTML = message;
  }

  function renderQuarter(entry) {
    fetch("/mk64/vs/data/quarters/" + entry.file)
      .then(function(response) {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(function(data) {
        heading.innerHTML = "Quarter Snapshot: " + data.quarter;
        summary.innerHTML =
          "Competitive matches in this quarter: " + data.total_matches +
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
            '<td>' + p.avg_points + '</td>' +
          '</tr>';
        }).join("");
      })
      .catch(function() {
        table.innerHTML = '<tr><td colspan="6">This quarter file could not be loaded.</td></tr>';
      });
  }

  fetch("/mk64/vs/data/quarters/index.json")
    .then(function(response) {
      if (!response.ok) throw new Error();
      return response.json();
    })
    .then(function(index) {
      quarterIndex = index;

      if (!quarterIndex.length) {
        setError("No quarterly snapshots are available yet.");
        return;
      }

      select.innerHTML = quarterIndex.map(function(q, i) {
        return '<option value="' + i + '">' + q.quarter + '</option>';
      }).join("");

      select.value = quarterIndex.length - 1;
      renderQuarter(quarterIndex[quarterIndex.length - 1]);

      select.addEventListener("change", function() {
        renderQuarter(quarterIndex[Number(select.value)]);
      });
    })
    .catch(function() {
      setError("Quarterly index could not be loaded. Run export_vs_quarterly.py first.");
    });
})();
</script>
"""


write("index.php", page(
    "vs",
    "Competitive MK64 Switch VS Elo Rankings",
    "Competitive Mario Kart 64 Nintendo Switch Online VS Elo rankings, player records, match logs, and seasonal history.",
    "VS Elo Rankings",
    "/mk64/vs/",
    index_body,
    json_ld=VS_JSON_LD
))

write("leaderboard.php", page(
    "vs-leaderboard",
    "Competitive MK64 Switch VS Leaderboard",
    "Competitive Mario Kart 64 Nintendo Switch Online weighted Elo leaderboard for ranked VS play.",
    "VS Leaderboard",
    "/mk64/vs/leaderboard.php",
    leaderboard_body,
    json_ld=VS_JSON_LD
))

write("players.php", page(
    "vs-players",
    "MK64 Switch Competitive VS Players",
    "Mario Kart 64 Switch Online competitive VS player stats, Elo ratings, matches, total points, and average points.",
    "VS Players",
    "/mk64/vs/players.php",
    players_body,
    json_ld=VS_JSON_LD
))

write("matches.php", page(
    "vs-matches",
    "MK64 Switch Competitive VS Match Log",
    "Mario Kart 64 Switch Online competitive VS match log with dates, placements, scores, and Discord source links.",
    "VS Match Log",
    "/mk64/vs/matches.php",
    matches_body,
    json_ld=VS_JSON_LD
))

write("quarters.php", page(
    "vs-quarters",
    "MK64 Switch Quarterly Competitive VS Seasons",
    "Mario Kart 64 Switch Online quarter-only VS Elo seasons, seasonal standings, and historical rankings.",
    "VS Quarterly History",
    "/mk64/vs/quarters.php",
    quarters_body,
    QUARTERS_SCRIPT,
    VS_JSON_LD
))

print("VS PHP generation complete.")