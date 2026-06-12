import os
import json
import asyncio
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

RULES_FILE = "stream_rules.json"
POLL_SECONDS = 180
LIVE_STREAMS_FILE = "public/live_streams.json"

_last_announced = {}
_twitch_access_token = None


def load_stream_rules():
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_streamers(rules):
    streamers = set()

    for server in rules.get("servers", []):
        for game_rule in server.get("game_rules", []):
            for streamer in game_rule.get("allowed_streamers", []):
                streamers.add(streamer.lower().strip())

    return sorted(streamers)


def get_twitch_access_token():
    global _twitch_access_token

    if _twitch_access_token:
        return _twitch_access_token

    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        raise RuntimeError("Missing TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET in .env")

    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials"
        },
        timeout=10
    )

    response.raise_for_status()
    data = response.json()

    _twitch_access_token = data["access_token"]
    return _twitch_access_token


def get_live_streams(streamers):
    if not streamers:
        return []

    token = get_twitch_access_token()

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    params = []
    for streamer in streamers:
        params.append(("user_login", streamer))

    response = requests.get(
        "https://api.twitch.tv/helix/streams",
        headers=headers,
        params=params,
        timeout=10
    )

    response.raise_for_status()
    return response.json().get("data", [])

def write_live_streams_json(live_streams, rules):
    public_streams = []
    now = datetime.now(timezone.utc).isoformat()

    for stream in live_streams:
        for server in rules.get("servers", []):
            for game_rule in server.get("game_rules", []):
                if not stream_matches_rule(stream, game_rule):
                    continue

                public_streams.append({
                    "server": server.get("server"),
                    "user_login": stream.get("user_login"),
                    "user_name": stream.get("user_name"),
                    "game_name": stream.get("game_name"),
                    "title": stream.get("title"),
                    "started_at": stream.get("started_at"),
                    "viewer_count": stream.get("viewer_count"),
                    "url": f"https://twitch.tv/{stream.get('user_login')}",
                    "updated_at": now
                })

    os.makedirs(os.path.dirname(LIVE_STREAMS_FILE), exist_ok=True)

    with open(LIVE_STREAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(public_streams, f, indent=2)


def game_matches(game_name, match_type, expected_game):
    game_name = (game_name or "").lower().strip()
    expected_game = (expected_game or "").lower().strip()

    if match_type == "any":
        return True

    if match_type == "exact":
        return game_name == expected_game

    if match_type == "startswith":
        return game_name.startswith(expected_game)

    if match_type == "contains":
        return expected_game in game_name

    return False


def stream_matches_rule(stream, game_rule):
    streamer = stream.get("user_login", "").lower().strip()
    game_name = stream.get("game_name", "")

    allowed_streamers = [
        s.lower().strip()
        for s in game_rule.get("allowed_streamers", [])
    ]

    if streamer not in allowed_streamers:
        return False

    return game_matches(
        game_name=game_name,
        match_type=game_rule.get("match_type", "exact"),
        expected_game=game_rule.get("game", "")
    )


def should_announce(server_key, stream, dedupe_minutes):
    stream_id = stream.get("id")
    streamer = stream.get("user_login", "").lower().strip()

    dedupe_key = f"{server_key}:{streamer}:{stream_id}"
    now = datetime.now(timezone.utc)

    previous = _last_announced.get(dedupe_key)

    if previous:
        elapsed_minutes = (now - previous).total_seconds() / 60
        if elapsed_minutes < dedupe_minutes:
            return False

    _last_announced[dedupe_key] = now
    return True


def make_stream_message(server, stream):
    streamer = stream.get("user_name") or stream.get("user_login")
    game = stream.get("game_name") or "something"
    title = stream.get("title") or ""
    url = f"<https://twitch.tv/{stream.get('user_login')}>"

    server_key = server.get("server", "")

    if server_key == "mk64":
        intro = f"🟢 **{streamer}** is live in MK64!"
    else:
        intro = f"🟢 **{streamer}** is now live!"

    message = f"{intro}\n\n**{game}**"

    if title:
        message += f"\n\n{title}"

    message += f"\n\n{url}"

    return message


async def send_stream_announcement(client, server, stream):
    channel_id = int(server["announcement_channel_id"])
    channel = client.get_channel(channel_id)

    if channel is None:
        print(f"Could not find channel ID {channel_id}")
        return

    message = make_stream_message(server, stream)
    await channel.send(message)


async def stream_poll_loop(client):
    await client.wait_until_ready()

    print("Stream tracker started.")

    while not client.is_closed():
        try:
            rules = load_stream_rules()
            streamers = get_all_streamers(rules)
            live_streams = get_live_streams(streamers)

            write_live_streams_json(live_streams, rules)

            for stream in live_streams:
                for server in rules.get("servers", []):
                    for game_rule in server.get("game_rules", []):
                        if not stream_matches_rule(stream, game_rule):
                            continue

                        dedupe_minutes = int(server.get("dedupe_minutes", 180))

                        if not should_announce(
                            server_key=server.get("server", "unknown"),
                            stream=stream,
                            dedupe_minutes=dedupe_minutes
                        ):
                            continue

                        await send_stream_announcement(client, server, stream)

        except Exception as e:
            print("Stream tracker error:", e)

        await asyncio.sleep(POLL_SECONDS)


def start_stream_tracker(client):
    client.loop.create_task(stream_poll_loop(client))