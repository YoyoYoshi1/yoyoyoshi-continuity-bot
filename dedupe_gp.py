# dedupe_gp.py

import json
import shutil
from datetime import datetime

INPUT_FILE = "gp_data.json"

backup_file = f"gp_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
shutil.copyfile(INPUT_FILE, backup_file)
print(f"Backup created: {backup_file}")

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

matches = data.get("matches", []) if isinstance(data, dict) else data

print(f"Original GP matches: {len(matches)}")

seen = set()
deduped = []

for match in reversed(matches):
    if not isinstance(match, dict):
        continue

    msg_id = match.get("message_id") or match.get("id")

    if not msg_id:
        key = json.dumps(match, sort_keys=True)
    else:
        key = str(msg_id)

    if key not in seen:
        seen.add(key)
        deduped.append(match)

deduped.reverse()

print(f"Deduped GP matches: {len(deduped)}")
print(f"Removed duplicates: {len(matches) - len(deduped)}")

if isinstance(data, dict):
    data["matches"] = deduped
    output = data
else:
    output = deduped

with open(INPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("gp_data.json rewritten successfully.")