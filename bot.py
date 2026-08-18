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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8783779072:AAEpdmWmPFC5_ITH8CHMy_CQ7itxQSNHWSw")

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
        "nocheckcertificate": True,
        # mp4 ကို ဦးစားပေး
        "format_sort": ["res", "ext:mp4:m4a", "codec:h264:aac", "size"],
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    # cookies ကို USE_COOKIES=1 ထားမှသာ သုံးမယ်
    # (cookies ဟောင်း/expired ဖြစ်နေရင် "format is not available" error တက်တတ်)
    use_cookies = os.environ.get("USE_COOKIES", "0").strip() in ("1", "true", "yes")
    if use_cookies and os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
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
        if not isinstance(d, dict) or d.get("status") != "downloading":
            return
        now = time.time()
        if now - last[0] < 2.5:
            return
        last[0] = now

        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes") or 0
        speed = d.get("_speed_str") or "N/A"
        eta = d.get("_eta_str") or "N/A"
        if not isinstance(speed, str):
            speed = "N/A"
        else:
            speed = speed.strip()
        if not isinstance(eta, str):
            eta = "N/A"
        else:
            eta = eta.strip()

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
        "👋 **YT Video Downloader Bot မှ ကြိုဆိုပါတယ်!**\n\n"
        "📥 **အသုံးပြုနည်း -**\n"
        "မည်သည့် YouTube ဗီဒီယို Link ကိုမဆို ပေးပို့လိုက်ပါ — Bot မှ မြန်ဆန်စွာ ဒေါင်းလုဒ်ဆွဲပြီး ပြန်လည် ပေးပို့ပေးပါမည်။\n\n"
        "⚡ **အင်္ဂါရပ်များ -**\n"
        "• ဒေါင်းလုဒ်ပြုလုပ်ရာတွင် အလွန်မြန်ဆန်ခြင်း\n"
        "• HD / SD ရုပ်ထွက် Quality ရရှိနိုင်ခြင်း\n"
        "• ၁၀၀% အခမဲ့ အသုံးပြုနိုင်ခြင်း\n\n"
        "Video / Audio ကြိုက်နှစ်သက်ရာ ရွေးချယ်နိုင်ပါသည်။\n\n"
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
        # Playlist ဖြစ်နေရင် ပထမဆုံး 1 ပုဒ်ကိုပဲ ယူရန် noplaylist ထည့်ပေးပါ
        ydl_opts["noplaylist"] = True

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            await status.edit_text(f"❌ အချက်အလက် မရရှိပါ။\n\n— {CREDIT}")
            return

        # Playlist entry ဖြစ်နေပါက None မဟုတ်တဲ့ ပထမဆုံး video ကို ဆွဲထုတ်ပါ
        if "entries" in info and info["entries"]:
            info = next((e for e in info["entries"] if e is not None), None)

        if not info:
            await status.edit_text(f"❌ အချက်အလက် မရရှိပါ။\n\n— {CREDIT}")
            return

        title = info.get("title") or "Unknown Title"
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
        err_msg = f"{type(e).__name__}: {e}"
        await status.edit_text(f"❌ အမှားဖြစ်သွားပါပြီ။\n`{err_msg}`\n\n— {CREDIT}")



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
                "noplaylist": True,
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
                
                # Playlist entry ဖြစ်နေပါက None မဟုတ်တဲ့ ပထမဆုံး video ကို ဆွဲထုတ်ပါ
                if info and "entries" in info:
                    info = next((e for e in info["entries"] if e is not None), None)

                # NoneType Error မတက်စေရန် Safe Check ပြုလုပ်ခြင်း
                if not info:
                    await safe_edit(status, f"❌ Video အချက်အလက်များ မရရှိပါ။\n\n— {CREDIT}")
                    return

                final_path = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"

            await safe_edit(status, f"📤 Telegram သို့ ပို့နေပါသည်...\n\n— {CREDIT}")
            await status.reply_audio(
                audio=final_path,
                caption=f"✅ {info.get('title', 'Audio')}\n\n— {CREDIT}",
                title=info.get("title", "Audio"),
                performer="YouTube"
            )

            # Cleanup
            try:
                if os.path.exists(final_path):
                    os.remove(final_path)
            except Exception:
                pass

        else:
            # Video download — format selector ကို ပြောင်းလဲအောင် ပြင်ထား
            # (ext=mp4 တင်းကျပ်စွာ မသတ်မှတ်ဘဲ fallback များများ ထည့်)
            format_map = {
                "best": "bestvideo*+bestaudio/best/bestvideo+bestaudio",
                "720": "bestvideo*[height<=720]+bestaudio/best[height<=720]/bestvideo*+bestaudio/best",
                "480": "bestvideo*[height<=480]+bestaudio/best[height<=480]/bestvideo*+bestaudio/best",
            }
            fmt = format_map.get(quality, format_map["best"])

            ydl_opts = get_base_ydl_opts()
            ydl_opts.update({
                "noplaylist": True,
                "format": fmt,
                "outtmpl": out_template,
                "merge_output_format": "mp4",
                "progress_hooks": [make_progress_hook(status, loop, f"{quality.upper()} Downloading")],
            })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                # Playlist entry ဖြစ်နေပါက None မဟုတ်တဲ့ ပထမဆုံး video ကို ဆွဲထုတ်ပါ
                if info and "entries" in info:
                    info = next((e for e in info["entries"] if e is not None), None)

                # NoneType Error မတက်စေရန် Safe Check ပြုလုပ်ခြင်း
                if not info:
                    await safe_edit(status, f"❌ Video အချက်အလက်များ မရရှိပါ။\n\n— {CREDIT}")
                    return

                final_path = ydl.prepare_filename(info)
                # ensure .mp4 extension after merge
                if not final_path.endswith(".mp4"):
                    base = final_path.rsplit(".", 1)[0]
                    if os.path.exists(base + ".mp4"):
                        final_path = base + ".mp4"

            title = info.get("title", "Video")
            duration, width, height = get_video_metadata(final_path)

            # Thumbnail
            thumb_path = os.path.join(OUTPUT_FOLDER, f"{safe_title}_thumb.jpg")
            has_thumb = extract_thumbnail(final_path, thumb_path)

            await safe_edit(status, f"📤 Telegram သို့ ပို့နေပါသည်...\n\n— {CREDIT}")

            await status.reply_video(
                video=final_path,
                caption=f"✅ **{title}**\n\n— {CREDIT}",
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_path if has_thumb else None,
                supports_streaming=True,
            )

            # Cleanup
            try:
                if os.path.exists(final_path):
                    os.remove(final_path)
                if has_thumb and os.path.exists(thumb_path):
                    os.remove(thumb_path)
            except Exception:
                pass

        await status.delete()

    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        await safe_edit(status, f"❌ အမှားဖြစ်သွားပါပြီ။\n`{err_msg}`\n\n— {CREDIT}")


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Bot is starting...")
    app.run()
