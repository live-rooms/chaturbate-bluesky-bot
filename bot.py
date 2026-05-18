#!/usr/bin/env python3
"""
Chaturbate → Bluesky Bot
Fetches live ebony-tagged rooms from Chaturbate and posts to Bluesky.

Schedule: 1 post per allowed UTC hour, 10 evenly-spaced hours per day.
Posting hours (UTC): 0, 2, 5, 7, 10, 12, 15, 17, 20, 22
"""

import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

CHATURBATE_API = (
    "https://chaturbate.com/api/public/affiliates/onlinerooms/"
    "?wm=T2CSW&client_ip=request_ip&tag=ebony&limit=500"
)

REVSHARE_URL = "https://chaturbate.com/in/?tour=JpRf&campaign=T2CSW&track=default&next=/female-cams/"

BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "ebonysexcams.bsky.social")
BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")

STATE_FILE = Path("state.json")
MAX_SEEN = 5000

POSTING_HOURS = [0, 2, 5, 7, 10, 12, 15, 17, 20, 22]


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def current_hour_utc() -> int:
    return datetime.now(timezone.utc).hour


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"seen": [], "daily": {"date": "", "posted_hours": [], "count": 0}}


def save_state(state: dict):
    state["seen"] = state["seen"][-MAX_SEEN:]
    STATE_FILE.write_text(json.dumps(state))


def reset_daily_if_needed(state: dict):
    today = today_utc()
    if state.get("daily", {}).get("date") != today:
        state["daily"] = {"date": today, "posted_hours": [], "count": 0}


def is_posting_hour(hour: int, posted_hours: list[int]) -> bool:
    return hour in POSTING_HOURS and hour not in posted_hours


def fetch_rooms() -> list[dict]:
    resp = httpx.get(CHATURBATE_API, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])


def fetch_image_bytes(url: str) -> bytes | None:
    try:
        resp = httpx.get(url, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"  Image fetch failed: {e}")
        return None


def bsky_login(handle: str, password: str) -> tuple[str, str]:
    resp = httpx.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["accessJwt"], data["did"]


def bsky_upload_image(token: str, image_bytes: bytes, mime: str = "image/jpeg") -> str:
    resp = httpx.post(
        "https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": mime,
        },
        content=image_bytes,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["blob"]


def build_post(room: dict) -> tuple[str, list[dict]]:
    """
    Returns (post_text, facets) where facets make hashtags and the link clickable.
    """
    username = room.get("username", "")
    display_name = room.get("display_name") or username
    subject = room.get("subject", "")
    tags: list[str] = room.get("tags", [])

    lines = []

    if display_name:
        lines.append(f"{display_name} is live on Chaturbate!")
    else:
        lines.append("Live now on Chaturbate!")

    if subject:
        clean_subject = subject.strip()
        if clean_subject:
            lines.append(clean_subject)

    lines.append("")

    link_label = "Join Now - Free"
    lines.append(link_label)

    lines.append("")

    hashtag_strs = []
    for tag in tags:
        clean = re.sub(r"[^a-zA-Z0-9_]", "", tag.replace(" ", "_"))
        if clean:
            hashtag_strs.append(f"#{clean}")

    if not any(h.lower() == "#ebony" for h in hashtag_strs):
        hashtag_strs.insert(0, "#ebony")

    hashtag_line = " ".join(hashtag_strs[:10])
    lines.append(hashtag_line)

    text = "\n".join(lines)

    facets = []
    text_bytes = text.encode("utf-8")

    link_label_bytes = link_label.encode("utf-8")
    link_start = text_bytes.find(link_label_bytes)
    if link_start >= 0:
        facets.append({
            "index": {
                "byteStart": link_start,
                "byteEnd": link_start + len(link_label_bytes),
            },
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": REVSHARE_URL,
            }],
        })

    for htag in hashtag_strs[:10]:
        htag_bytes = htag.encode("utf-8")
        search_from = 0
        while True:
            idx = text_bytes.find(htag_bytes, search_from)
            if idx == -1:
                break
            end_idx = idx + len(htag_bytes)
            if end_idx < len(text_bytes) and re.match(r"[a-zA-Z0-9_]", chr(text_bytes[end_idx])):
                search_from = idx + 1
                continue
            tag_value = htag[1:]
            facets.append({
                "index": {
                    "byteStart": idx,
                    "byteEnd": end_idx,
                },
                "features": [{
                    "$type": "app.bsky.richtext.facet#tag",
                    "tag": tag_value,
                }],
            })
            break

    return text, facets


def bsky_post(token: str, did: str, text: str, facets: list[dict], image_blob=None):
    record: dict = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    if facets:
        record["facets"] = facets

    if image_blob:
        record["embed"] = {
            "$type": "app.bsky.embed.images",
            "images": [{
                "image": image_blob,
                "alt": "Live cam preview",
            }],
        }

    resp = httpx.post(
        "https://bsky.social/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo": did,
            "collection": "app.bsky.feed.post",
            "record": record,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def run():
    if not BLUESKY_APP_PASSWORD:
        raise RuntimeError("BLUESKY_APP_PASSWORD environment variable is not set.")

    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    print(f"[{now_utc.isoformat()}] Current UTC hour: {hour}")
    print(f"  Scheduled posting hours: {POSTING_HOURS}")

    state = load_state()
    reset_daily_if_needed(state)

    posted_hours: list[int] = state["daily"]["posted_hours"]
    daily_count: int = state["daily"]["count"]

    print(f"  Posts today: {daily_count}/10 | Hours already posted: {posted_hours}")

    if not is_posting_hour(hour, posted_hours):
        if hour not in POSTING_HOURS:
            print(f"  Hour {hour} is not a scheduled posting hour. Skipping.")
        else:
            print(f"  Hour {hour} already posted today. Skipping.")
        save_state(state)
        return

    print(f"  Hour {hour} is a scheduled posting slot — proceeding.")

    print("  Fetching Chaturbate rooms...")
    rooms = fetch_rooms()
    print(f"  Found {len(rooms)} rooms with ebony tag.")

    seen = set(state.get("seen", []))
    new_rooms = [r for r in rooms if r.get("username") not in seen]
    print(f"  {len(new_rooms)} new (not yet posted).")

    if not new_rooms:
        print("  No new rooms available. Marking hour as used to avoid retrying.")
        posted_hours.append(hour)
        state["daily"]["posted_hours"] = posted_hours
        save_state(state)
        return

    random.shuffle(new_rooms)
    room = new_rooms[0]
    username = room.get("username", "")

    print(f"  Selected room: {username}")

    print("  Logging into Bluesky...")
    token, did = bsky_login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
    print(f"  Logged in as {BLUESKY_HANDLE}")

    text, facets = build_post(room)

    image_blob = None
    image_url = (
        room.get("image_url_360x270")
        or room.get("image_url_180x135")
        or room.get("thumb")
    )
    if image_url:
        img_bytes = fetch_image_bytes(image_url)
        if img_bytes:
            try:
                image_blob = bsky_upload_image(token, img_bytes)
                print("  Image uploaded.")
            except Exception as e:
                print(f"  Image upload failed: {e}")

    try:
        result = bsky_post(token, did, text, facets, image_blob)
        print(f"  Posted: {result.get('uri')}")
        seen.add(username)
        posted_hours.append(hour)
        state["daily"]["posted_hours"] = posted_hours
        state["daily"]["count"] = daily_count + 1
        state["seen"] = list(seen)
    except Exception as e:
        print(f"  Post failed: {e}")

    save_state(state)
    print(f"\nDone. Total posts today: {state['daily']['count']}/10.")


if __name__ == "__main__":
    run()
