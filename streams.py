import os
import json
import asyncio
import requests

from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

RULES_FILE = "stream_rules.json"
POLL_SECONDS = 180
LIVE_STREAMS_FILE = "live_streams.json"

_last_announced = {}
_twitch_access_token = None
_twitch_access_token_expires_at = None


def load_stream_rules():
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_streamers(rules):
    streamers = set()

    for server in rules.get("servers", []):
        for game_rule in server.get("game_rules", []):
            for streamer in game_rule.get("allowed_streamers", []):
                clean = (streamer or "").lower().strip()
                if clean:
                    streamers.add(clean)

    return sorted(streamers)


def clear_twitch_access_token():
    global _twitch_access_token, _twitch_access_token_expires_at
    _twitch_access_token = None
    _twitch_access_token_expires_at = None


def get_twitch_access_token(force_refresh=False):
    global _twitch_access_token, _twitch_access_token_expires_at

    now = datetime.now(timezone.utc)

    if force_refresh:
        clear_twitch_access_token()

    if (
        _twitch_access_token
        and _twitch_access_token_expires_at
        and now < _twitch_access_token_expires_at
    ):
        return _twitch_access_token

    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        raise RuntimeError(
            "Missing TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET in environment."
        )

    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=10,
    )

    response.raise_for_status()
    data = response.json()

    _twitch_access_token = data["access_token"]

    # Refresh slightly before Twitch's reported expiration time.
    expires_in = int(data.get("expires_in", 3600))
    refresh_buffer_seconds = min(300, max(30, expires_in // 10))
    _twitch_access_token_expires_at = (
        now + timedelta(seconds=max(60, expires_in - refresh_buffer_seconds))
    )

    print(
        "Twitch access token refreshed. "
        f"Refresh scheduled before {_twitch_access_token_expires_at.isoformat()}."
    )

    return _twitch_access_token


def _request_live_streams(streamers, force_refresh=False):
    token = get_twitch_access_token(force_refresh=force_refresh)

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    params = [
        ("user_login", streamer)
        for streamer in streamers
    ]

    return requests.get(
        "https://api.twitch.tv/helix/streams",
        headers=headers,
        params=params,
        timeout=10,
    )


def get_live_streams(streamers):
    if not streamers:
        return []

    response = _request_live_streams(streamers)

    if response.status_code == 401:
        print("Twitch returned 401. Refreshing access token and retrying once.")
        response = _request_live_streams(streamers, force_refresh=True)

    response.raise_for_status()

    data = response.json()
    live_streams = data.get("data", [])

    print(
        f"Twitch poll complete: checked {len(streamers)} streamer(s), "
        f"found {len(live_streams)} live."
    )

    for stream in live_streams:
        print(
            "TWITCH LIVE:",
            {
                "user_login": stream.get("user_login"),
                "user_name": stream.get("user_name"),
                "game_name": stream.get("game_name"),
                "title": stream.get("title"),
                "stream_id": stream.get("id"),
                "started_at": stream.get("started_at"),
            }
        )

    return live_streams


def game_matches(game_name, match_type, expected_game):
    game_name = (game_name or "").casefold().strip()
    expected_game = (expected_game or "").casefold().strip()
    match_type = (match_type or "exact").casefold().strip()

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
    streamer = (stream.get("user_login") or "").casefold().strip()
    game_name = stream.get("game_name") or ""

    allowed_streamers = [
        (s or "").casefold().strip()
        for s in game_rule.get("allowed_streamers", [])
        if (s or "").strip()
    ]

    if streamer not in allowed_streamers:
        return False

    return game_matches(
        game_name=game_name,
        match_type=game_rule.get("match_type", "exact"),
        expected_game=game_rule.get("game", ""),
    )


def write_live_streams_json(live_streams, rules):
    public_streams = []
    now = datetime.now(timezone.utc).isoformat()
    seen = set()

    for stream in live_streams:
        for server in rules.get("servers", []):
            for game_rule in server.get("game_rules", []):
                if not stream_matches_rule(stream, game_rule):
                    continue

                dedupe_key = (
                    server.get("server"),
                    stream.get("user_login"),
                    stream.get("id"),
                )

                if dedupe_key in seen:
                    continue

                seen.add(dedupe_key)

                public_streams.append({
                    "server": server.get("server"),
                    "live": True,
                    "streamer": stream.get("user_name") or stream.get("user_login"),
                    "user_login": stream.get("user_login"),
                    "url": f"https://twitch.tv/{stream.get('user_login')}",
                    "title": stream.get("title"),
                    "game": stream.get("game_name"),
                    "viewer_count": stream.get("viewer_count"),
                    "started_at": stream.get("started_at"),
                    "checked_at": now,
                })

    with open(LIVE_STREAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "updated_at": now,
                "streams": public_streams,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def announcement_key(server_key, stream):
    stream_id = stream.get("id") or stream.get("started_at") or "unknown"
    streamer = (stream.get("user_login") or "").casefold().strip()
    return f"{server_key}:{streamer}:{stream_id}"


def should_announce(server_key, stream, dedupe_minutes):
    key = announcement_key(server_key, stream)
    now = datetime.now(timezone.utc)
    previous = _last_announced.get(key)

    if not previous:
        return True

    elapsed_minutes = (now - previous).total_seconds() / 60
    return elapsed_minutes >= dedupe_minutes


def mark_announced(server_key, stream):
    key = announcement_key(server_key, stream)
    _last_announced[key] = datetime.now(timezone.utc)


def prune_announcement_cache(max_age_hours=24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    stale_keys = [
        key
        for key, announced_at in _last_announced.items()
        if announced_at < cutoff
    ]

    for key in stale_keys:
        _last_announced.pop(key, None)


def make_stream_message(server, stream):
    streamer = stream.get("user_name") or stream.get("user_login") or "A streamer"
    game = stream.get("game_name") or "something"
    title = stream.get("title") or ""
    user_login = stream.get("user_login") or ""
    url = f"<https://twitch.tv/{user_login}>"

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
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception as e:
            raise RuntimeError(
                f"Could not resolve announcement channel ID {channel_id}: {e}"
            ) from e

    message = make_stream_message(server, stream)
    await channel.send(message)


async def fetch_live_streams_async(streamers):
    return await asyncio.to_thread(get_live_streams, streamers)


async def stream_poll_loop(client):
    await client.wait_until_ready()

    print("Stream tracker started.")

    while not client.is_closed():
        try:
            rules = load_stream_rules()
            streamers = get_all_streamers(rules)
            live_streams = await fetch_live_streams_async(streamers)

            write_live_streams_json(live_streams, rules)
            prune_announcement_cache()

            for stream in live_streams:
                streamer = stream.get("user_login")
                game_name = stream.get("game_name")
                stream_id = stream.get("id")

                for server in rules.get("servers", []):
                    server_key = server.get("server", "unknown")
                    matched_server = False

                    for game_rule in server.get("game_rules", []):
                        matched = stream_matches_rule(stream, game_rule)

                        print(
                            "STREAM ROUTE CHECK:",
                            {
                                "server": server_key,
                                "streamer": streamer,
                                "game": game_name,
                                "rule_match_type": game_rule.get("match_type"),
                                "rule_game": game_rule.get("game"),
                                "matched": matched,
                            }
                        )

                        if matched:
                            matched_server = True
                            break

                    if not matched_server:
                        continue

                    dedupe_minutes = int(server.get("dedupe_minutes", 180))

                    if not should_announce(
                        server_key=server_key,
                        stream=stream,
                        dedupe_minutes=dedupe_minutes,
                    ):
                        print(
                            "STREAM ANNOUNCEMENT SKIPPED (dedupe):",
                            {
                                "server": server_key,
                                "streamer": streamer,
                                "stream_id": stream_id,
                            }
                        )
                        continue

                    try:
                        await send_stream_announcement(client, server, stream)
                    except Exception as e:
                        print(
                            "STREAM ANNOUNCEMENT ERROR:",
                            {
                                "server": server_key,
                                "streamer": streamer,
                                "stream_id": stream_id,
                                "error": repr(e),
                            }
                        )
                        continue

                    mark_announced(server_key, stream)

                    print(
                        "STREAM ANNOUNCEMENT SENT:",
                        {
                            "server": server_key,
                            "streamer": streamer,
                            "game": game_name,
                            "stream_id": stream_id,
                        }
                    )

        except FileNotFoundError:
            print(f"Stream tracker error: rules file not found: {RULES_FILE}")

        except requests.HTTPError as e:
            response = e.response
            status = response.status_code if response is not None else "unknown"
            body = response.text[:500] if response is not None else ""
            print(
                f"Stream tracker HTTP error: status={status}, "
                f"response={body!r}"
            )

        except Exception as e:
            print("Stream tracker error:", repr(e))

        await asyncio.sleep(POLL_SECONDS)


def start_stream_tracker(client):
    client.loop.create_task(stream_poll_loop(client))
