import json
import os
from datetime import datetime

DATA_DIR = "public/mk64/gp/data"
OUTPUT_DIR = "public/mk64/gp"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_json(filename):
    with open(os.path.join(DATA_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)


leaderboard = load_json("leaderboard.json")
players = load_json("players.json")
matches = load_json("matches.json")
summary = load_json("summary.json")

generated = datetime.now().strftime("%B %d, %Y")


def fmt_date(value):
    if not value:
        return "Unknown"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except Exception:
        return "Unknown"


match_dates = [m.get("created_at") for m in matches if m.get("created_at")]
coverage_start = fmt_date(min(match_dates)) if match_dates else "Unknown"
coverage_end = fmt_date(max(match_dates)) if match_dates else "Unknown"

CSS = """
:root {
  --bg: #ffffff;
  --panel: #e6e6e6;
  --text: #000000;
  --muted: #333333;
  --link: #0000ee;
  --link-hover: #cc0000;
  --max: 1160px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: Verdana, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  font-size: 13px;
}

a { color: var(--link); text-decoration: underline; }
a:hover, a:focus { color: var(--link-hover); }

.wrap {
  width: min(var(--max), calc(100% - 20px));
  margin: 0 auto;
  padding: 14px 0 30px;
}

.grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 14px;
  align-items: start;
}

.panel {
  background: var(--panel);
  border: 3px ridge #cccccc;
  padding: 14px;
  margin-bottom: 14px;
}

.section-heading {
  margin-bottom: 10px;
  padding: 5px 8px;
  border: 2px outset #cccccc;
  background: linear-gradient(#8fa3cc, #5f739d);
  color: #ffffff;
  font-size: 13px;
  font-weight: bold;
}

.section-heading::before { content: "» "; }

table {
  width: 100%;
  border-collapse: collapse;
  background: #ffffff;
  font-size: 12px;
}

th, td {
  border: 1px solid #999999;
  padding: 6px;
  text-align: left;
  vertical-align: top;
}

th { background: #dbe3f3; }
tr:nth-child(even) { background: #f5f5f5; }

.note {
  color: var(--muted);
  font-size: 12px;
}

.info-box {
  background: #ffffff;
  border: 2px outset #cccccc;
  padding: 10px;
  margin-bottom: 10px;
}

select {
  font-family: Verdana, Arial, sans-serif;
  font-size: 13px;
  padding: 4px;
}

@media (max-width: 980px) {
  .grid { grid-template-columns: 1fr; }
}
"""

SCRIPT = """
<script>
function loadHTML(id, file) {
  fetch("../" + file)
    .then(function(response) {
      if (!response.ok) throw new Error();
      return response.text();
    })
    .then(function(html) {
      document.getElementById(id).innerHTML = html;
    })
    .catch(function() {
      document.getElementById(id).innerHTML =
        '<div class="panel">' + file + ' could not be loaded.</div>';
    });
}

loadHTML("header-container", "header.html");
loadHTML("footer-container", "footer.html");

fetch("../sidebar.html")
  .then(function(response) {
    if (!response.ok) throw new Error();
    return response.text();
  })
  .then(function(html) {
    document.getElementById("sidebar-container").innerHTML = html;
  })
  .catch(function() {
    document.getElementById("sidebar-container").innerHTML =
      '<div class="panel">Sidebar could not be loaded.</div>';
  });
</script>"""


def page(title, description, body, extra_script=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <style>{CSS}</style>
</head>
<body>
<div class="wrap">

<div id="header-container"><div class="panel">Loading header...</div></div>

<div class="grid">
  <aside class="sidebar" id="sidebar-container">
    <div class="panel">Loading sidebar...</div>
  </aside>

  <main class="content">
    {body}
    <section class="panel">
      <div class="section-heading">Page Info</div>
      <p class="note">Last updated: {generated}</p>
    </section>
  </main>
</div>

<div id="footer-container"><div class="panel">Loading footer...</div></div>

</div>
{SCRIPT}
{extra_script}
</body>
</html>
"""


def write(filename, html):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {path}")


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

nav_links = """
<p>
  <a href="leaderboard.html">View Leaderboard</a> |
  <a href="players.html">View All Players</a> |
  <a href="matches.html">View Match Log</a> |
  <a href="quarters.html">View Quarterly GP Seasons</a>
</p>
"""

explanation = f"""
<section class="panel">
  <div class="section-heading">How These Rankings Work</div>
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
<section class="panel">
  <div class="section-heading">MK64 GP Rankings</div>
  <p>
    This section tracks Mario Kart 64 Switch Grand Prix results parsed from Discord and legacy GP Elo records.
    It turns scattered match history into a lasting ranking archive, player record, match log, and seasonal Elo chronology.
  </p>
  <p class="note">
    Total matches: {summary["total_matches"]}. Eligible players: {summary["eligible_players"]}.
    Coverage: {coverage_start} – {coverage_end}.
  </p>
  {nav_links}
</section>
{explanation}
"""

leaderboard_body = f"""
{explanation}
<section class="panel">
  <div class="section-heading">GP Leaderboard</div>
  <p class="note">
    Weighted Elo leaderboard. Median Elo: {summary["median_elo"]}.
  </p>
  {nav_links}
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
    <tbody>{leaderboard_rows}</tbody>
  </table>
</section>
"""

players_body = f"""
<section class="panel">
  <div class="section-heading">All GP Players</div>
  <p>
    This table includes every parsed GP player, including players who have not yet reached the minimum match threshold.
  </p>
  <p class="note">Coverage: {coverage_start} – {coverage_end}. Last updated: {generated}.</p>
  {nav_links}
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
    <tbody>{players_rows}</tbody>
  </table>
</section>
"""

matches_body = f"""
<section class="panel">
  <div class="section-heading">GP Match Log</div>
  <p>
    This log shows all parsed GP matches, with dates and direct Discord source links where available.
  </p>
  <p class="note">Full parsed coverage: {coverage_start} – {coverage_end}. Last updated: {generated}.</p>
  {nav_links}
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
    <tbody>{match_rows}</tbody>
  </table>
</section>
"""

quarters_body = f"""
<section class="panel">
  <div class="section-heading">Quarterly GP Seasons</div>
  <p>
    Browse quarter-only seasonal GP Elo rankings. Each quarter recalculates Elo using only matches played during that quarter.
  </p>
  <p class="note">Coverage: {coverage_start} – {coverage_end}. Last updated: {generated}.</p>
  {nav_links}
  <div class="info-box">
    <label for="quarter-select"><strong>Select Quarter:</strong></label>
    <select id="quarter-select">
      <option value="">Loading quarters...</option>
    </select>
  </div>
</section>

<section class="panel">
  <div class="section-heading" id="quarter-heading">Quarter Season</div>
  <div id="quarter-summary" class="note">Choose a quarter to view seasonal rankings.</div>
  <br>
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
    fetch("data/quarters/" + entry.file)
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

  fetch("data/quarters/index.json")
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

write("index.html", page(
    "MK64 Switch GP Rankings",
    "Mario Kart 64 Switch Grand Prix rankings, weighted Elo leaderboard, player stats, match log, and quarterly GP seasons.",
    index_body
))

write("leaderboard.html", page(
    "MK64 Switch GP Leaderboard",
    "Mario Kart 64 Switch weighted Elo leaderboard for Grand Prix play.",
    leaderboard_body
))

write("players.html", page(
    "MK64 Switch GP Players",
    "Mario Kart 64 Switch GP player stats, Elo ratings, records, and point totals.",
    players_body
))

write("matches.html", page(
    "MK64 Switch GP Match Log",
    "Mario Kart 64 Switch GP match log with dates, scores, Elo changes, and Discord source links.",
    matches_body
))

write("quarters.html", page(
    "MK64 Switch Quarterly GP Seasons",
    "Mario Kart 64 Switch quarter-only GP Elo seasons and historical seasonal rankings.",
    quarters_body,
    QUARTERS_SCRIPT
))

print("GP HTML generation complete.")