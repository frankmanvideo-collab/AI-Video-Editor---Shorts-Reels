from __future__ import annotations
import json, logging, math, os, random, shlex, subprocess
from pathlib import Path
from config import ASSETS_DIR, FONT_PATH
from utils import ffprobe_duration, has_audio_stream, run_cmd, video_dimensions
from ai_director import transcribe_audio, ai_strategy

logger=logging.getLogger("GodModeV3")

def ass_time(t: float) -> str:
    t=max(0,float(t)); h=int(t//3600); m=int((t%3600)//60); s=t%60
    return f"{h}:{m:02d}:{s:05.2f}"

def ass_escape(s: str) -> str:
    return str(s).replace("\\","\\\\").replace("{","\\{").replace("}","\\}").replace("\n","\\N")

def pick_asset(sub: str) -> str|None:
    d=ASSETS_DIR/sub
    if not d.exists(): return None
    files=[p for p in d.iterdir() if p.suffix.lower() in (".mp3",".wav",".m4a")]
    return str(random.choice(files)) if files else None

def write_ass(path: Path, words: list[dict], duration: float, hook: str|None, cta: str|None, placement: str, punchwords: set[str]) -> None:
    y_align = 2 if placement == "bottom" else (5 if placement == "center" else 8)
    header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Liberation Sans,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,5,2,{y_align},60,60,170,1
Style: Punch,Liberation Sans,98,&H0000FFCC,&H0000FFCC,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,6,2,{y_align},60,60,170,1
Style: Hook,Liberation Sans,92,&H0000D7FF,&H0000D7FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,7,3,8,60,60,90,1
Style: CTA,Liberation Sans,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,5,2,2,60,60,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[header]
    if hook:
        lines.append(f"Dialogue: 5,{ass_time(0)},{ass_time(min(3,duration))},Hook,,0,0,0,,{ass_escape(hook.upper())}\n")
    i=0
    while i < len(words):
        group=words[i:i+3]; i+=3
        if not group: continue
        st=float(group[0].get("start",0)); en=float(group[-1].get("end", st+0.6))
        if st>=duration: continue
        en=min(duration, max(st+0.25,en))
        text=" ".join(str(w.get("word","")).strip() for w in group).strip()
        if not text: continue
        style="Punch" if any(str(w.get("word","")).upper().strip(".,!?;:'\"") in punchwords for w in group) else "Caption"
        lines.append(f"Dialogue: 3,{ass_time(st)},{ass_time(en)},{style},,0,0,0,,{ass_escape(text.upper())}\n")
    if cta and duration>4:
        lines.append(f"Dialogue: 6,{ass_time(max(0,duration-3))},{ass_time(duration)},CTA,,0,0,0,,{ass_escape(cta)}\n")
    path.write_text("".join(lines), encoding="utf-8")

def extract_audio(input_path: str, audio_path: str) -> None:
    run_cmd(["ffmpeg","-y","-i",input_path,"-vn","-ac","1","-ar","16000","-b:a","64k",audio_path],timeout=180)

def ffmpeg_filter_escape(path: str) -> str:
    # subtitles filter needs escaped colon/backslash/single quotes
    return path.replace("\\","/").replace(":","\\:").replace("'","\\'")

def render_video_ffmpeg(input_path: str, output_path: str, config: dict, workdir: Path) -> dict:
    duration=ffprobe_duration(input_path)
    has_audio=has_audio_stream(input_path)
    audio_path=str(workdir/"audio.mp3")
    transcript={"text":"","words":[]}
    if has_audio:
        extract_audio(input_path,audio_path)
        audio_dur=min(duration, ffprobe_duration(audio_path))
        transcript=transcribe_audio(audio_path,audio_dur)
    manual=(config.get("manual_caption_text") or "").strip()
    if manual and not transcript.get("words"):
        from ai_director import _fake_word_timestamps
        transcript={"text":manual,"words":_fake_word_timestamps(manual,duration)}
    strategy=ai_strategy(transcript.get("text",""), config, mode=config.get("kind","edit"))
    selected_hook=config.get("selected_hook")
    if selected_hook in (None,"auto"):
        selected_hook=strategy["hook_options"][strategy.get("best_hook_index",0)]
    elif selected_hook == "skip":
        selected_hook=None
    cta=config.get("cta")
    if cta == "skip": cta=None
    if cta in (None,"auto"):
        cta=(strategy.get("cta_suggestions") or [None])[0]
    ass_path=workdir/"captions.ass"
    write_ass(ass_path, transcript.get("words") or [], duration, selected_hook, cta, config.get("placement","bottom"), {str(x).upper() for x in strategy.get("punchwords",[])})
    bgm=pick_asset("backgrounds")
    final_dur=max(0.1, duration/1.1)
    sub_filter=f"subtitles='{ffmpeg_filter_escape(str(ass_path))}'"
    # Keep aspect, cap width to 1080, cap height to 1920, burn ASS captions, speed-up.
    vf=f"scale='if(gt(iw,1080),1080,iw)':-2,{sub_filter},setpts=PTS/1.1"
    cmd=["ffmpeg","-y","-i",input_path]
    if bgm: cmd += ["-stream_loop","-1","-i",bgm]
    if has_audio and bgm:
        fc=f"[0:v]{vf}[v];[0:a]loudnorm,atempo=1.1[a0];[1:a]volume=0.08,atrim=0:{final_dur}[bgm];[a0][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]"
        cmd += ["-filter_complex",fc,"-map","[v]","-map","[a]"]
    elif has_audio:
        fc=f"[0:v]{vf}[v];[0:a]loudnorm,atempo=1.1[a]"
        cmd += ["-filter_complex",fc,"-map","[v]","-map","[a]"]
    elif bgm:
        fc=f"[0:v]{vf}[v];[1:a]volume=0.12,atrim=0:{final_dur}[a]"
        cmd += ["-filter_complex",fc,"-map","[v]","-map","[a]"]
    else:
        cmd += ["-vf",vf,"-an"]
    cmd += ["-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-movflags","+faststart",output_path]
    run_cmd(cmd, timeout=max(300,int(duration*15)))
    return {"duration": ffprobe_duration(output_path), "strategy": strategy, "transcript_text": transcript.get("text","")}

def audit_video(input_path: str, config: dict, workdir: Path) -> dict:
    duration=ffprobe_duration(input_path)
    transcript={"text":"","words":[]}
    if has_audio_stream(input_path):
        audio_path=str(workdir/"audit_audio.mp3")
        extract_audio(input_path,audio_path)
        transcript=transcribe_audio(audio_path, min(duration, ffprobe_duration(audio_path)))
    elif config.get("manual_caption_text"):
        transcript={"text":config.get("manual_caption_text"),"words":[]}
    strategy=ai_strategy(transcript.get("text",""), config, mode="audit")
    return {"duration":duration,"strategy":strategy,"transcript_text":transcript.get("text","")}
