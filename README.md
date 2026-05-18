# Chaturbate → Bluesky Bot

Posts live Chaturbate rooms with the **ebony** tag to Bluesky automatically, once per hour.

Each post includes:
- Room name and subject
- Clickable blue hashtags from the room's tags
- A preview image from the room
- A **"Join Now - Free"** affiliate link

---

## Setup

### 1. Fork / push this repo to GitHub

Upload all files in this folder to a new GitHub repository.

### 2. Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these two secrets:

| Secret name | Value |
|---|---|
| `BLUESKY_HANDLE` | `ebonysexcams.bsky.social` |
| `BLUESKY_APP_PASSWORD` | Your Bluesky app password (e.g. `xxxx-xxxx-xxxx-xxxx`) |

> Create an app password at: **bsky.app → Settings → App Passwords**

### 3. Enable GitHub Actions

Go to your repo → **Actions** tab → click **"I understand my workflows, go ahead and enable them"** if prompted.

### 4. Run manually to test

Go to **Actions → Post to Bluesky → Run workflow** to trigger a test run immediately.

---

## How it works

- Runs **once per hour** via GitHub Actions cron schedule
- Fetches all live rooms tagged `ebony` from the Chaturbate public API
- Skips rooms already posted (tracked via a cache file between runs)
- For each new room: builds a Bluesky post with rich text facets (clickable hashtags + affiliate link), uploads the room thumbnail, and creates the post
- Hashtags appear **blue and clickable** on Bluesky using the AT Protocol `richtext.facet#tag` type

---

## Files

```
bot.py                          Main bot script
requirements.txt                Python dependencies (httpx only)
.github/workflows/post.yml      GitHub Actions schedule
```
