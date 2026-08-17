# ============================================================
# YouTube Video Downloader Bot (Pyrogram)
# Style inspired by @UseMasterUpdate Facebook bot
# ============================================================

import os
import re
import time
import random
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
import yt_dlp

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
API_ID    = int(os.environ.get("API_ID", 31606811))
API_HASH  = os.environ.get("API_HASH", "36e6d64e83ee00422c8ba535a60eaa99")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8783779072:AAHz1ACcEgyYg0ZB41aH_MgWxVIKQJcZgiA")

# Cookies File Path
COOKIES_FILE = "cookies.txt"

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("API_ID, API_HASH and BOT_TOKEN are required")

OUTPUT_FOLDER = "downloads"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

CREDIT = "@KMM_MOD1"   # ပြောင်းချင်ရင် ပြောင်းပါ

app = Client(
    "yt_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ──────────────────────────────────────────────
# Helper function for ydl options
# ──────────────────────────────────────────────
def get_base_ydl_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    }
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts

# ──────────────────────────────────────────────
# Utilities (Facebook bot style)
# ──────────────────────────────────────────────
def human_size(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} TB"

def progress_bar(current: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width
    filled = int(width * current / total)
    return f"[{'█' * filled}{'░' * (width - filled)}] {current / total * 100:.1f}%"

_last_edit: dict[int, float] = {}

async def safe_edit(msg: Message, text: str, min_interval: float = 2.5) -> None:
    now = time.time()
    if now - _last_edit.get(msg.id, 0) < min_interval:
        return
    _last_edit[msg.id] = now
    try:
        await msg.edit_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass

# ──────────────────────────────────────────────
# YouTube URL detector
# ──────────────────────────────────────────────
YT_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+",
    re.IGNORECASE,
)

def extract_yt_url(text: str) -> str | None:
    m = YT_PATTERN.search(text)
    return m.group(0) if m else None

# ──────────────────────────────────────────────
# yt-dlp Progress Hook
# ──────────────────────────────────────────────
def make_progress_hook(status_msg: Message, loop: asyncio.AbstractEventLoop, label: str):
    last = [0.0]

    def hook(d):
        if d["status"] != "downloading":
            return
        now = time.time()
        if now - last[0] < 2.5:
            return
        last[0] = now

        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes", 0)
        speed = d.get("_speed_str", "N/A").strip()
        eta = d.get("_eta_str", "N/A").strip()

        bar = progress_bar(downloaded, total) if total else "██████████"
        text = (
            f"📥 **{label}**\n"
            f"{bar}\n"
            f"`{human_size(downloaded)}" + (f" / {human_size(total)}" if total else "") + "`\n"
            f"Speed: `{speed}` | ETA: `{eta}`\n\n"
            f"— {CREDIT}"
        )
        asyncio.run_coroutine_threadsafe(safe_edit(status_msg, text, min_interval=0), loop)

    return hook

# ──────────────────────────────────────────────
# FFmpeg helpers
# ──────────────────────────────────────────────
def extract_thumbnail(video_path: str, thumb_path: str) -> bool:
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30
        )
        duration = float(probe.stdout.strip() or "10")
        seek = random.uniform(duration * 0.10, duration * 0.80)

        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-ss", str(seek), "-i", video_path,
             "-vframes", "1", "-vf", "scale=320:-1", "-y", thumb_path],
            timeout=30, check=True
        )
        return os.path.exists(thumb_path)
    except Exception:
        return False

def get_video_metadata(video_path: str) -> tuple[int, int, int]:
    try:
        dur = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30
        )
        duration = int(float(dur.stdout.strip() or "0"))
    except Exception:
        duration = 0

    try:
        dim = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=30
        )
        w, h = dim.stdout.strip().split(",")
        width, height = int(w), int(h)
    except Exception:
        width, height = 1280, 720

    return duration, width, height

# ──────────────────────────────────────────────
# Main Handlers
# ──────────────────────────────────────────────
@app.on_message(filters.command("start"))
async def start_handler(_, message: Message):
    await message.reply_text(
        "🎬 **YouTube Downloader Bot**\n\n"
        "YouTube လင့်ခ်ပို့ပါ။\n"
        "Video / Audio ရွေးနိုင်ပါတယ်။\n\n"
        f"— {CREDIT}"
    )

@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def url_handler(_, message: Message):
    url = extract_yt_url(message.text or "")
    if not url:
        return

    status = await message.reply_text(f"⏳ ဗီဒီယိုအချက်အလက် ရယူနေပါသည်...\n\n— {CREDIT}")

    try:
        ydl_opts = get_base_ydl_opts()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title", "Unknown")
        duration = info.get("duration") or 0

        h, rem = divmod(duration, 3600)
        m, s = divmod(rem, 60)
        duration_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

        buttons = [
            [
                InlineKeyboardButton("🎥 Best", callback_data=f"yt|best|{url}"),
                InlineKeyboardButton("🎥 720p", callback_data=f"yt|720|{url}"),
            ],
            [
                InlineKeyboardButton("🎥 480p (မြန်)", callback_data=f"yt|480|{url}"),
                InlineKeyboardButton("🎵 Audio MP3", callback_data=f"yt|audio|{url}"),
            ]
        ]

        await status.edit_text(
            f"📹 **{title}**\n\n"
            f"⏱ Duration: `{duration_str}`\n\n"
            f"အောက်ပါမှ ရွေးချယ်ပါ 👇\n\n— {CREDIT}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        await status.edit_text(f"❌ အမှားဖြစ်သွားပါပြီ။\n`{e}`\n\n— {CREDIT}")

@app.on_callback_query(filters.regex(r"^yt\|"))
async def callback_handler(_, query: CallbackQuery):
    await query.answer()
    try:
        _, quality, url = query.data.split("|", 2)
    except Exception:
        await query.message.edit_text("❌ Data မမှန်ကန်ပါ။")
        return

    status = query.message
    await safe_edit(status, f"⏳ ဒေါင်းလုဒ် စတင်နေပါသည်...\n\n— {CREDIT}")

    loop = asyncio.get_running_loop()
    safe_title = re.sub(r'[^\w\s\-_\.]', '', str(time.time()))[:20]
    out_template = os.path.join(OUTPUT_FOLDER, f"{safe_title}.%(ext)s")

    try:
        if quality == "audio":
            ydl_opts = get_base_ydl_opts()
            ydl_opts.update({
                "format": "bestaudio/best",
                "outtmpl": out_template,
                "progress_hooks": [make_progress_hook(status, loop, "Audio Downloading")],
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                final_path = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"

            await safe_edit(status, f"📤 Telegram သို့ ပို့နေပါသည်...\n\n— {CREDIT}")
            await status.reply_audio(
                audio=final_path,
                caption=f"✅ {info.get('title', 'Audio')}\n\n— {CREDIT}",
                title=info.get("title"),
                performer="YouTube"
            )

        else:
            duration = 0
            try:
                ydl_opts_pre = get_base_ydl_opts()
                with yt_dlp.YoutubeDL(ydl_opts_pre) as ydl:
                    info_pre = ydl.extract_info(url, download=False)
                    duration = info_pre.get("duration") or 0
            except Exception:
                pass

            if quality == "480" or duration > 3600:
                fmt = "best[height<=480][ext=mp4]/best[height<=480]/best[ext=mp4]/best"
                label = "480p Video"
            elif quality == "720":
                fmt = "best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best"
                label = "720p Video"
            else:
                fmt = "best[height<=1080][ext=mp4]/best[height<=1080]/best[ext=mp4]/best"
                label = "Best Video"

            ydl_opts = get_base_ydl_opts()
            ydl_opts.update({
                "format": fmt,
                "outtmpl": out_template,
                "progress_hooks": [make_progress_hook(status, loop, f"{label} Downloading")],
                "concurrent_fragment_downloads": 5,
                "http_chunk_size": 10485760,
            })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                final_path = ydl.prepare_filename(info)

            # Thumbnail
            thumb_path = final_path + ".jpg"
            has_thumb = extract_thumbnail(final_path, thumb_path)

            duration, width, height = get_video_metadata(final_path)

            await safe_edit(status, f"📤 Telegram သို့ ပို့နေပါသည်...\n\n— {CREDIT}")

            await status.reply_video(
                video=final_path,
                caption=f"✅ {info.get('title', 'Video')}\n\n— {CREDIT}",
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_path if has_thumb else None,
                supports_streaming=True,
            )

            if has_thumb and os.path.exists(thumb_path):
                os.remove(thumb_path)

        # Cleanup
        if os.path.exists(final_path):
            os.remove(final_path)

        await safe_edit(status, f"✅ ပြီးဆုံးပါပြီ။\n\n— {CREDIT}")

    except Exception as e:
        await safe_edit(status, f"❌ အမှားဖြစ်သွားပါပြီ။\n`{e}`\n\n— {CREDIT}")

@app.on_message(filters.command("help"))
async def help_handler(_, message: Message):
    await message.reply_text(
        "📖 **အသုံးပြုနည်း**\n\n"
        "1️⃣ YouTube လင့်ခ်ပို့ပါ\n"
        "2️⃣ အရည်အသွေး ရွေးပါ (480p က အမြန်ဆုံး)\n"
        "3️⃣ Progress bar နဲ့ ဒေါင်းလုဒ်လုပ်ပေးပါမယ်\n\n"
        f"— {CREDIT}"
    )

if __name__ == "__main__":
    print("YouTube Bot is running...")
    app.run()
