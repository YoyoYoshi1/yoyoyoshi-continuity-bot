import json
import os
from datetime import datetime

DATA_DIR = "public/mk64/vs/data"
OUTPUT_DIR = "public/mk64/vs"

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

    var currentPath = window.location.pathname;
    var sidebarLinks = document.querySelectorAll("#sidebar-container a");

    sidebarLinks.forEach(function(link) {
      var href = link.getAttribute("href");

      if (
        href === currentPath ||
        href === currentPath.replace("/mk64/", "") ||
        href === currentPath.replace("/mk64/vs/", "vs/")
      ) {
        link.classList.add("active");
      }
    });
  })
  .catch(function() {
    document.getElementById("sidebar-container").innerHTML =
      '<div class="panel">Sidebar could not be loaded.</div>';
  });
</script>"""

def page(title, description, body):
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

recent_matches = matches[-100:][::-1]

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
<section class="panel">
  <div class="section-heading">How These Rankings Work</div>
  <div class="info-box">
    <strong>Coverage Period</strong><br>
    These results currently cover parsed VS match posts from {coverage_start} through {coverage_end}.
  </div>
  <p>
    The leaderboard uses a multi-player Elo model. Each VS match is treated as a set of head-to-head outcomes:
    finishing above another player counts as a win against that player, and finishing below counts as a loss.
  </p>
  <p>
    The displayed rating is confidence-weighted. That means newer or low-sample players are pulled closer to 1000
    until they have more recorded matches. This helps prevent one or two strong results from overranking someone
    before the data has enough weight.
  </p>
  <p>
    Players must have at least {summary["min_matches"]} parsed matches to appear on the main leaderboard.
    All players still appear on the full player list.
  </p>
</section>
"""

index_body = f"""
<section class="panel">
  <div class="section-heading">MK64 VS Rankings</div>
  <p>
    This section tracks Mario Kart 64 Switch VS results parsed from Discord match posts.
    It turns scattered score posts into a lasting ranking archive, player record, and match log.
  </p>
  <p class="note">
    Total matches: {summary["total_matches"]}. Eligible players: {summary["eligible_players"]}.
    Coverage: {coverage_start} – {coverage_end}.
  </p>
  <p>
    <a href="leaderboard.html">View Leaderboard</a> |
    <a href="players.html">View All Players</a> |
    <a href="matches.html">View Match Log</a>
  </p>
</section>
{explanation}
"""

leaderboard_body = f"""
{explanation}
<section class="panel">
  <div class="section-heading">VS Leaderboard</div>
  <p class="note">
    Weighted Elo leaderboard. Median Elo: {summary["median_elo"]}.
  </p>
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
    <tbody>{leaderboard_rows}</tbody>
  </table>
</section>
"""

players_body = f"""
<section class="panel">
  <div class="section-heading">All VS Players</div>
  <p>
    This table includes every parsed player, including players who have not yet reached the minimum match threshold.
  </p>
  <p class="note">Coverage: {coverage_start} – {coverage_end}. Last updated: {generated}.</p>
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
    <tbody>{players_rows}</tbody>
  </table>
</section>
"""

matches_body = f"""
<section class="panel">
  <div class="section-heading">VS Match Log</div>
  <p>
    This log shows the latest 100 parsed VS matches, with dates and direct Discord source links where available.
  </p>
  <p class="note">Full parsed coverage: {coverage_start} – {coverage_end}. Last updated: {generated}.</p>
  <table>
    <thead>
      <tr>
        <th>Match ID</th>
        <th>Date</th>
        <th>Placements</th>
        <th>Source</th>
      </tr>
    </thead>
    <tbody>{match_rows}</tbody>
  </table>
</section>
"""

write("index.html", page(
    "MK64 Switch VS Rankings",
    "Mario Kart 64 Switch VS rankings, weighted Elo leaderboard, player stats, and Discord match log.",
    index_body
))

write("leaderboard.html", page(
    "MK64 Switch VS Leaderboard",
    "Mario Kart 64 Switch weighted Elo leaderboard for ranked VS play.",
    leaderboard_body
))

write("players.html", page(
    "MK64 Switch VS Players",
    "Mario Kart 64 Switch VS player stats, Elo ratings, matches, and average points.",
    players_body
))

write("matches.html", page(
    "MK64 Switch VS Match Log",
    "Recent Mario Kart 64 Switch VS match log with dates, placements, scores, and Discord source links.",
    matches_body
))

print("VS HTML generation complete.")