# Youtube Video Downloader & Uploader Bot

A Telegram bot (built with [Pyrogram](https://docs.pyrogram.org/)) that detects Facebook video links, extracts the video/audio DASH streams, downloads and merges them with FFmpeg, and uploads the final video back to Telegram — with live progress bars for every step.

Credits: `@UseMasterUpdate`

## Features

- Auto-detects `facebook.com`, `fb.watch`, and `fb.com` links in chat
- Parses Facebook's DASH stream data directly from the page (no third-party API)
- Downloads video + audio streams separately with a live progress bar
- Merges streams into a single MP4 using FFmpeg
- Extracts a random thumbnail frame (10%–80% into the video)
- Fixes correct video duration/dimensions before upload
- Uploads with a live progress bar and `supports_streaming=True`
- Automatic cleanup of temp files, even on failure

## Requirements

- Python 3.11+
- FFmpeg + ffprobe (installed automatically in the Docker image)
- A Telegram bot token and API credentials from [my.telegram.org](https://my.telegram.org)

## Environment Variables

| Variable    | Description                                  |
|-------------|-----------------------------------------------|
| `API_ID`    | Telegram API ID from my.telegrae` to `.env` and fill in your values for local tes
#nning Lo
pip install -r requirements.txt
#

## Deployment

This repo includes ready-to-use config files for three platforms. All three build from the included `Dockerfile`, which installs FFmpeg alongside Python — no manual buildpack setup needed.

### Railway

1. Push this repo to GitHub.
2. On [Railway](https://railway.app), click **New Project → Deploy from GitHub repo** and select this repo.
3. Railway will detect `railway.json` and build using the Dockerfile automatically.
4. Add the environment variables (`API_ID`, `API_HASH`, `BOT_TOKEN`) in the **Variables** tab.
5. Deploy — the bot starts via `python bot.py`.

### Render

1. Push this repo to GitHub.
2. On [Render](https://render.com), click **New → Blueprint** and point it at this repo (it will read `render.yaml`).
3. Render creates a **Worker** service using the Dockerfile.
4. Fill in `API_ID`, `API_HASH`, and `BOT_TOKEN` when prompted (they're marked `sync: false` so Render asks for them securely).
5. Deploy.

### Koyeb

1. Push this repo to GitHub.
2. On [Koyeb](https://www.koyeb.com), click **Create App → GitHub**, select this repo. Koyeb will detect the `Dockerfile` automatically (the included `koyeb.yaml` documents the same config if you deploy via the Koyeb CLI).
3. Set service type to **Worker** (no public port needed).
4. Add `API_ID`, `API_HASH`, and `BOT_TOKEN` as secrets/environment variables.
5. Deploy.

## Project Structure

```
.
├── bot.py             # Main bot logic
├── Dockerfile          # Container build (Python + FFmpeg)
├── requirements.txt    # Python dependencies
├── Procfile            # Fallback start command for buildpack-based platforms
├── railway.json        # Railway deployment config
├── render.yaml          # Render deployment config
├── koyeb.yaml           # Koyeb deployment config
├── .env.example         # Sample environment variables
├── .gitignore
└── README.md
```

## Notes

- The bot stores nothing permanently — downloaded/merged files and thumbnails are deleted right after upload (or on failure).
- Facebook regularly changes its internal page structure. If extraction starts failing, the DASH-parsing logic in `bot.py` (`_extract_fb_links_sync`) may need updating to match Facebook's current HTML.
