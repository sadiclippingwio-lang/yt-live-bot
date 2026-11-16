import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

YT_API_KEY = os.environ["YOUTUBE_API_KEY"]
# One or more channel IDs (each starts with "UC"), separated by commas
YT_CHANNEL_IDS = [c.strip() for c in os.environ["YOUTUBE_CHANNEL_ID"].split(",") if c.strip()]
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
PING = os.environ.get("PING_ROLE_ID", "").strip()  # role ID, or the word "everyone"

API = "https://www.googleapis.com/youtube/v3"
SEEN_FILE = Path("announced.json")
HEADERS = {"User-Agent": "yt-live-discord-bot (github actions)"}


def get_json(url, params):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def load_seen():
    try:
        return json.loads(SEEN_FILE.read_text())
    except Exception:
        return []


def get_live_videos(channel_id):
    playlist = "UU" + channel_id[2:]
    items = get_json(
        f"{API}/playlistItems",
        {"part": "contentDetails", "playlistId": playlist, "maxResults": 5, "key": YT_API_KEY},
    ).get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    if not ids:
        return []
    vids = get_json(f"{API}/videos", {"part": "snippet", "id": ",".join(ids), "key": YT_API_KEY})
    return [v for v in vids.get("items", []) if v["snippet"].get("liveBroadcastContent") == "live"]


def post_to_discord(video):
    snip = video["snippet"]
    url = f"https://www.youtube.com/watch?v={video['id']}"
    thumbs = snip.get("thumbnails", {})
    thumb = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("default") or {}).get("url")

    ping = ""
    if PING:
        ping = "@everyone " if PING.lower() == "everyone" else f"<@&{PING}> "

    embed = {
        "title": snip["title"],
        "url": url,
        "description": f"**{snip['channelTitle']}** is now live on YouTube!",
        "color": 0xFF0000,
    }
    if thumb:
        embed["image"] = {"url": thumb}

    payload = {
        "content": f"{ping}🔴 {snip['channelTitle']} is LIVE!\n{url}",
        "embeds": [embed],
        "allowed_mentions": {"parse": ["roles", "everyone"]},
    }
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode(),
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=20).read()


def main():
    seen = load_seen()
    changed = False
    errors = 0

    for channel_id in YT_CHANNEL_IDS:
        try:
            live = get_live_videos(channel_id)
        except Exception as e:
            print(f"Error checking {channel_id}: {e}", file=sys.stderr)
            errors += 1
            continue

        if not live:
            print(f"{channel_id}: not live.")
            continue

        for v in live:
            if v["id"] in seen:
                print(f"{channel_id}: already announced {v['id']}.")
                continue
            try:
                post_to_discord(v)
            except Exception as e:
                print(f"Error posting {v['id']}: {e}", file=sys.stderr)
                errors += 1
                continue
            seen.append(v["id"])
            changed = True
            print(f"Announced {v['id']}")

    if changed:
        SEEN_FILE.write_text(json.dumps(seen[-200:]))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
