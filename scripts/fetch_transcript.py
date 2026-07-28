#!/usr/bin/env python3
"""
Fetch a YouTube video transcript and output it as structured JSON.

Usage:
    uv run python3 fetch_transcript.py <url_or_video_id> [--language zh,en] [--timestamps]

Default language preference is Chinese first, then English. If the preferred language fetch fails, the script retries once without language restriction.

Output (JSON):
    {
        "video_id": "...",
        "language": "en",
        "segments": [{"text": "...", "start": 0.0, "duration": 2.5}, ...],
        "full_text": "complete transcript as plain text",
        "timestamped_text": "00:00 first line\n00:05 second line\n..."
    }

Install dependency:  uv pip install youtube-transcript-api
"""

import argparse
import json
import os
import re
import sys


def extract_video_id(url_or_id: str) -> str:
    """Extract the 11-character video ID from various YouTube URL formats."""
    url_or_id = url_or_id.strip()
    patterns = [
        r'(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fetch_transcript(video_id: str, languages: list = None):
    """Fetch transcript segments from YouTube.

    Returns a list of dicts with 'text', 'start', and 'duration' keys.
    Compatible with youtube-transcript-api v1.x.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("Error: youtube-transcript-api not installed. Run: uv pip install youtube-transcript-api",
              file=sys.stderr)
        sys.exit(1)

    api = YouTubeTranscriptApi()
    if languages:
        result = api.fetch(video_id, languages=languages)
    else:
        result = api.fetch(video_id)

    # v1.x returns FetchedTranscriptSnippet objects; normalize to dicts
    return [
        {"text": seg.text, "start": seg.start, "duration": seg.duration}
        for seg in result
    ]


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube transcript as JSON")
    parser.add_argument("url", help="YouTube URL or video ID")
    parser.add_argument("--language", "-l", default="zh,en",
                        help="Comma-separated language codes (e.g. zh,en). Default: zh,en")
    parser.add_argument("--timestamps", "-t", action="store_true",
                        help="Include timestamped text in output")
    parser.add_argument("--text-only", action="store_true",
                        help="Output plain text instead of JSON")
    args = parser.parse_args()

    video_id = extract_video_id(args.url)
    languages = [l.strip() for l in args.language.split(",")] if args.language else None

    try:
        segments = fetch_transcript(video_id, languages)
        resolved_language = ",".join(languages) if languages else "auto"
    except Exception as first_error:
        # Default zh,en may fail when a video only exposes another transcript language.
        # Retry once with YouTubeTranscriptApi's auto selection before reporting failure.
        try:
            segments = fetch_transcript(video_id, None)
            resolved_language = "auto_after_preferred_failed"
        except Exception as e:
            error_msg = str(e)
            first_error_msg = str(first_error)
            if "blocking requests from your ip" in error_msg.lower() or "blocking requests from your ip" in first_error_msg.lower():
                print(json.dumps({"error": "YouTube is blocking this server's IP. Use HTTPS_PROXY or fetch from another machine. See SKILL.md pitfall #1."}, ensure_ascii=False))
                sys.exit(1)
            # ── ASR Fallback (Baidu → local) ──
            fallback_ok = (
                "disabled" in error_msg.lower() or "disabled" in first_error_msg.lower() or
                "no transcript" in error_msg.lower() or "no transcript" in first_error_msg.lower()
            )
            if fallback_ok:
                print(f"YouTube transcript unavailable — falling back to ASR...", file=sys.stderr)
                try:
                    import subprocess as _sp
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    dl_script = os.path.join(script_dir, "download_audio.py")
                    audio_path = f"/tmp/yt_{video_id}.wav"
                    _sp.run([sys.executable, dl_script, args.url, "--output", audio_path],
                            check=True, timeout=300, capture_output=True)

                    # Try Baidu ASR first (fast, accurate Chinese)
                    baidu_env = os.environ.copy()
                    dotenv_path = os.path.join(os.path.dirname(script_dir), ".env")
                    if os.path.exists(dotenv_path):
                        baidu_env.update({k: v for line in open(dotenv_path) if "=" in line
                                         for k, v in [line.strip().split("=", 1)]})
                    baidu_script = os.path.join(script_dir, "transcribe_baidu.py")
                    baidu_result = _sp.run([sys.executable, baidu_script, audio_path],
                                           env=baidu_env, timeout=300,
                                           capture_output=True, text=True)
                    if baidu_result.returncode == 0:
                        baidu_json = json.loads(baidu_result.stdout)
                        if baidu_json.get("full_text"):
                            merged = {
                                "video_id": video_id,
                                "language": languages[0] if languages else "zh",
                                "source": "baidu-asr",
                                "full_text": baidu_json["full_text"],
                                "char_count": baidu_json.get("char_count", 0)
                            }
                            print(json.dumps(merged, ensure_ascii=False, indent=2))
                            try: os.unlink(audio_path)
                            except: pass
                            return

                    # Fallback to local faster-whisper
                    asr_script = os.path.join(script_dir, "transcribe_audio.py")
                    lang = languages[0] if languages else "zh"
                    model = os.environ.get("WHISPER_MODEL", "small")
                    result = _sp.run([sys.executable, asr_script, audio_path,
                                     "--language", lang, "--model", model],
                                    check=True, timeout=600, capture_output=True, text=True)
                    try: os.unlink(audio_path)
                    except: pass
                    print(result.stdout.strip())
                    return
                except Exception as asr_err:
                    print(json.dumps({"error": f"ASR fallback also failed: {asr_err}", "yt_error": error_msg}, ensure_ascii=False))
                    sys.exit(1)
            else:
                print(json.dumps({"error": error_msg, "first_error": first_error_msg}, ensure_ascii=False))
                sys.exit(1)

    full_text = " ".join(seg["text"] for seg in segments)
    timestamped = "\n".join(
        f"{format_timestamp(seg['start'])} {seg['text']}" for seg in segments
    )

    if args.text_only:
        print(timestamped if args.timestamps else full_text)
        return

    result = {
        "video_id": video_id,
        "language": resolved_language,
        "segment_count": len(segments),
        "duration": format_timestamp(segments[-1]["start"] + segments[-1]["duration"]) if segments else "0:00",
        "full_text": full_text,
    }
    if args.timestamps:
        result["timestamped_text"] = timestamped

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
