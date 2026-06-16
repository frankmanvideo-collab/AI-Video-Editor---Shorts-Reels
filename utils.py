from __future__ import annotations
import json, logging, re, shutil, subprocess, time
from pathlib import Path
from typing import Any
from telegram.constants import ParseMode

logger = logging.getLogger("GodModeV3")

def rupees_str(paisa: int) -> str:
    return f"₹{paisa/100:.2f}"

def escape_md(text: str) -> str:
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", str(text))

def safe_json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback

def run_cmd(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    logger.info("Running command: %s", " ".join(cmd[:8]) + (" ..." if len(cmd) > 8 else ""))
    return subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)

def ffprobe_json(path: str) -> dict:
    r = run_cmd(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path], timeout=60)
    return json.loads(r.stdout)

def ffprobe_duration(path: str) -> float:
    data = ffprobe_json(path)
    return float(data.get("format", {}).get("duration") or 0)

def has_audio_stream(path: str) -> bool:
    try:
        data = ffprobe_json(path)
        return any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    except Exception:
        return False

def video_dimensions(path: str) -> tuple[int, int]:
    data = ffprobe_json(path)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            return int(s.get("width") or 0), int(s.get("height") or 0)
    return 0, 0

def cleanup_old_files(directory: Path, max_age_seconds: int = 3600) -> None:
    now = time.time()
    if not directory.exists(): return
    for p in directory.iterdir():
        try:
            if p.name == ".gitkeep": continue
            age = now - p.stat().st_mtime
            if age > max_age_seconds:
                if p.is_dir(): shutil.rmtree(p, ignore_errors=True)
                else: p.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("cleanup failed for %s: %s", p, e)

def check_disk_space(path: Path, min_free_mb: int = 1500) -> bool:
    usage = shutil.disk_usage(path)
    return usage.free / (1024*1024) >= min_free_mb
