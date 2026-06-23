from __future__ import annotations
import asyncio, logging, shutil, uuid
from pathlib import Path
from config import DOWNLOADS_DIR, MAX_QUEUE_SIZE, PRICE_MINI_AUDIT, PRICE_FULL_ROAST, PRICE_EDIT_60, PRICE_EDIT_120, FREE_SAMPLE_SECONDS, MAX_VIDEO_DURATION_SEC, MIN_VIDEO_DURATION_SEC
from db import create_job, update_job, debit_wallet, refund_wallet, set_free_sample_used, get_user
from renderer_ffmpeg import render_video_ffmpeg, audit_video
from utils import ffprobe_duration, rupees_str, escape_md, check_disk_space
from telegram.constants import ParseMode

logger=logging.getLogger("GodModeV3")
video_queue: asyncio.Queue|None=None
active_users:set[int]=set()

SERVICE_PRICE={"mini_audit":PRICE_MINI_AUDIT,"full_roast":PRICE_FULL_ROAST,"edit60":PRICE_EDIT_60,"edit120":PRICE_EDIT_120,"free_sample":0}
SERVICE_MAX={"mini_audit":60.0,"full_roast":120.0,"edit60":60.0,"edit120":120.0,"free_sample":FREE_SAMPLE_SECONDS}

def service_price(kind:str)->int: return SERVICE_PRICE.get(kind,0)
def service_max(kind:str)->float: return SERVICE_MAX.get(kind,MAX_VIDEO_DURATION_SEC)
def is_audit(kind:str)->bool: return kind in ("mini_audit","full_roast")
def is_edit(kind:str)->bool: return kind in ("edit60","edit120","free_sample")

async def download_file(bot, file_id: str, dest: Path):
    f=await bot.get_file(file_id)
    await f.download_to_drive(str(dest))

async def enqueue(bot, user_id:int, kind:str, config:dict) -> tuple[bool,str]:
    global video_queue
    if video_queue is None: return False,"Worker not ready"
    if video_queue.qsize() >= MAX_QUEUE_SIZE: return False,"Queue full"
    if user_id in active_users: return False,"You already have an active job"
    job_id=uuid.uuid4().hex[:12]
    price=service_price(kind)
    create_job(job_id,user_id,kind,price,config)
    active_users.add(user_id)
    await video_queue.put({"job_id":job_id,"user_id":user_id,"kind":kind,"price":price,"config":config,"bot":bot})
    return True,job_id

def format_report(strategy:dict) -> str:
    """Plain-text viral report. No Markdown parse mode to avoid Telegram entity errors."""
    scores = strategy.get("scores", {}) or {}
    hooks = strategy.get("hook_options", []) or []
    mistakes = strategy.get("mistakes", []) or []
    fixes = strategy.get("fixes", []) or []
    ctas = strategy.get("cta_suggestions", []) or []
    hashtags = strategy.get("hashtags", []) or []

    lines = []
    lines.append(f"📊 Viral Score: {strategy.get('viral_score', 70)}/100")
    lines.append(
        f"🎯 Hook: {scores.get('hook', 7)}/10 | "
        f"Pacing: {scores.get('pacing', 7)}/10 | "
        f"Clarity: {scores.get('clarity', 7)}/10 | "
        f"CTA: {scores.get('cta', 6)}/10"
    )
    lines.append("")
    lines.append("❌ Top Mistakes:")
    for x in mistakes[:5]:
        lines.append(f"• {x}")
    lines.append("")
    lines.append("✅ Fixes:")
    for x in fixes[:5]:
        lines.append(f"• {x}")
    lines.append("")
    lines.append("🧲 Hook Ideas:")
    for i, x in enumerate(hooks[:3], 1):
        lines.append(f"{i}. {x}")
    lines.append("")
    if ctas:
        lines.append(f"📌 CTA: {ctas[0]}")
    if strategy.get("post_caption"):
        lines.append("")
        lines.append("📝 Caption:")
        lines.append(str(strategy.get("post_caption", "")))
    if hashtags:
        lines.append("")
        lines.append("🏷 " + " ".join(map(str, hashtags[:15])))
    return "\n".join(lines)[:3900]

def progress_bar(percent: int) -> str:
    filled = max(0, min(10, int(percent / 10)))
    return "█" * filled + "░" * (10 - filled)

def estimate_left(kind: str, percent: int) -> str:
    total = 2 if is_audit(kind) else 6
    left = max(0, int(round(total * (100 - percent) / 100)))
    return "Almost done" if left <= 0 else f"~{left} min left"

def progress_text(kind: str, percent: int, status: str, extra: str = "") -> str:
    title = "📊 Auditing your reel" if is_audit(kind) else "🎬 Editing your reel"
    text = (
        f"{title}...\n\n"
        f"Progress: {progress_bar(percent)} {percent}%\n\n"
        f"Status:\n{status}\n\n"
        f"ETA: {estimate_left(kind, percent)}"
    )
    if extra:
        text += f"\n{extra}"
    return text

async def update_progress(msg, kind: str, percent: int, status: str, extra: str = ""):
    try:
        await msg.edit_text(progress_text(kind, percent, status, extra))
    except Exception:
        pass

async def worker_loop():
    assert video_queue is not None
    while True:
        job=await video_queue.get()
        user_id=job["user_id"]; job_id=job["job_id"]; bot=job["bot"]; kind=job["kind"]; price=job["price"]; config=job["config"]
        charged=0; workdir=DOWNLOADS_DIR/job_id
        try:
            update_job(job_id,"PROCESSING")
            workdir.mkdir(parents=True,exist_ok=True)
            progress_msg = await bot.send_message(user_id, progress_text(kind, 0, "📋 Starting now"))
            if not check_disk_space(DOWNLOADS_DIR, 1000): raise RuntimeError("Server storage is low. Try later.")
            await update_progress(progress_msg, kind, 10, "📥 Downloading your video")
            input_path=workdir/"input.mp4"; output_path=workdir/"output.mp4"
            await download_file(bot, config["video_file_id"], input_path)
            await update_progress(progress_msg, kind, 20, "🔍 Checking file, duration and limits")
            dur=ffprobe_duration(str(input_path))
            if dur < MIN_VIDEO_DURATION_SEC: raise ValueError(f"Video too short. Minimum {MIN_VIDEO_DURATION_SEC:.0f}s.")
            maxdur=service_max(kind)
            if dur > maxdur: raise ValueError(f"This pack supports max {maxdur:.0f}s video.")
            if kind == "free_sample":
                u=get_user(user_id)
                if u["free_sample_used"]: raise ValueError("Free sample already used.")
                set_free_sample_used(user_id)
            elif price>0:
                ok,_=debit_wallet(user_id,price,f"job:{kind}:{job_id}",job_id)
                if not ok: raise ValueError(f"Insufficient balance. Need {rupees_str(price)}.")
                charged=price
            await bot.send_message(user_id,"🧠 Analyzing hook, pacing and content…")
            if is_audit(kind):
                result=await asyncio.get_running_loop().run_in_executor(None, audit_video, str(input_path), {**config,"kind":kind}, workdir)
                await bot.send_message(user_id, format_report(result["strategy"]))
            else:
                await bot.send_message(user_id,"🎬 Rendering your viral reel…")
                result=await asyncio.get_running_loop().run_in_executor(None, render_video_ffmpeg, str(input_path), str(output_path), {**config,"kind":kind}, workdir)
                await bot.send_message(user_id,"📤 Uploading final video…")
                with open(output_path,"rb") as vf:
                    await bot.send_video(user_id, vf, caption=f"✅ Done\nDuration: {result['duration']:.1f}s\nCost: {rupees_str(charged) if charged else 'FREE SAMPLE'}", supports_streaming=True)
                await bot.send_message(user_id, format_report(result["strategy"]))
            update_job(job_id,"COMPLETED")
        except Exception as e:
            logger.exception("job failed %s", job_id)
            if charged: refund_wallet(user_id,charged,f"refund:{job_id}",job_id)
            update_job(job_id,"FAILED",str(e)[:300])
            await bot.send_message(user_id, f"❌ Job failed\n\n{str(e)[:250]}\n\nYou have not been charged." + (" Refund issued." if charged else ""))
        finally:
            active_users.discard(user_id)
            shutil.rmtree(workdir, ignore_errors=True)
            video_queue.task_done()
