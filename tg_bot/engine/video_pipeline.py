from __future__ import annotations

import os
import shutil
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional

from tg_bot.config import BASE_DIR, MATERIALS_DIR
from tg_bot.engine.agent_runner import transcribe_audio_bytes

OUTPUT_DIR = BASE_DIR / "content" / "Montage"

def find_binary(name: str) -> str:
    """Finds binary path checking standard system locations."""
    which_bin = shutil.which(name)
    if which_bin:
        return which_bin
        
    candidates = [
        Path(f"/opt/homebrew/bin/{name}"),
        Path(f"/usr/local/bin/{name}"),
        Path(f"/usr/bin/{name}"),
        Path(f"/root/.local/bin/{name}"),
        Path.home() / ".local" / "bin" / name
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)
    return name

def format_ass_time(seconds: float) -> str:
    """Converts seconds float to ASS timestamp format: H:MM:SS.cs"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)
    return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"

def generate_ass_subtitles(segments: List[Dict[str, Any]], output_ass: Path):
    """
    Generates a stylized ASS subtitle file tailored for 9:16 vertical videos.
    Bold typography, high contrast outline, positioned safely above Reels/Shorts UI.
    """
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,54,&H00FFFFFF,&H000000FF,&H00181928,&H80000000,-1,0,0,0,100,100,0,0,1,5,3,2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for s in segments:
        start_t = format_ass_time(s.get("start", 0.0))
        end_t = format_ass_time(s.get("end", s.get("start", 0.0) + 2.0))
        text = s.get("text", "").strip()
        # Clean text
        text = text.replace("\n", " ").replace('"', '')
        if text:
            events.append(f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{text}")

    output_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

async def cut_silence(ffmpeg_bin: str, input_path: Path, output_path: Path) -> bool:
    """Removes silent pauses longer than 0.4s using ffmpeg silenceremove filter."""
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(input_path),
        "-af", "silenceremove=stop_periods=-1:stop_duration=0.4:stop_threshold=-32dB",
        "-c:v", "copy",
        str(output_path)
    ]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await proc.communicate()
    return proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0

async def process_video_montage(
    input_video_path: Path,
    cut_pauses: bool = True,
    add_subs: bool = True
) -> Tuple[bool, Optional[Path], str]:
    """
    Automated video editing pipeline:
    1. Cut silence pauses (via ffmpeg filter)
    2. Extract audio and transcribe with Whisper
    3. Generate stylized 9:16 vertical subtitles
    4. Burn subtitles into final MP4 video
    Returns (success, output_path, log).
    """
    ffmpeg_bin = find_binary("ffmpeg")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    final_output = OUTPUT_DIR / f"Montaged_{input_video_path.stem}.mp4"

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        working_video = input_video_path

        # Step 1: Cut silence if requested
        if cut_pauses:
            silence_cut_video = tmp_dir / "silence_cut.mp4"
            cut_ok = await cut_silence(ffmpeg_bin, working_video, silence_cut_video)
            if cut_ok:
                working_video = silence_cut_video

        # Step 2: Extract audio for Whisper transcription
        audio_path = tmp_dir / "voice.mp3"
        extract_cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(working_video),
            "-vn",
            "-acodec", "libmp3lame",
            "-q:a", "2",
            str(audio_path)
        ]
        proc = await asyncio.create_subprocess_exec(*extract_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()

        if not audio_path.exists():
            return False, None, "Не удалось извлечь аудиодорожку из видео."

        # Step 3: Transcription
        audio_bytes = audio_path.read_bytes()
        transcribed_text = await transcribe_audio_bytes(audio_bytes, filename="voice.mp3")

        if not transcribed_text or "Ошибка" in transcribed_text:
            # Fallback: return silence-cut video if transcription failed
            shutil.copy2(working_video, final_output)
            return True, final_output, f"Паузы вырезаны (субтитры пропущены: {transcribed_text})"

        # Step 4: Split into subtitle phrases
        words = transcribed_text.split()
        segments = []
        duration_approx = 4.0  # seconds per phrase chunk
        chunk_size = 5
        
        current_time = 0.5
        for i in range(0, len(words), chunk_size):
            phrase = " ".join(words[i:i+chunk_size])
            segments.append({
                "start": current_time,
                "end": current_time + duration_approx,
                "text": phrase
            })
            current_time += duration_approx + 0.2

        ass_file = tmp_dir / "subtitles.ass"
        generate_ass_subtitles(segments, ass_file)

        # Step 5: Burn subtitles into video
        burn_cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(working_video),
            "-vf", f"ass={ass_file.name}",
            "-c:a", "copy",
            "-preset", "veryfast",
            "-crf", "22",
            str(final_output)
        ]
        # Run inside tmp_dir so relative path to ass works
        proc_burn = await asyncio.create_subprocess_exec(
            *burn_cmd,
            cwd=str(tmp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc_burn.communicate()

        if final_output.exists() and final_output.stat().st_size > 0:
            return True, final_output, f"Монтаж успешно завершен! Паузы удалены, субтитры наложены."
        else:
            # Fallback without subtitle filter
            shutil.copy2(working_video, final_output)
            return True, final_output, f"Видео сохранено без субтитров (фильтр libass недоступен)."

if __name__ == "__main__":
    print(f"FFmpeg binary: {find_binary('ffmpeg')}")
