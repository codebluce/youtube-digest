#!/usr/bin/env python3
"""
Fetch a YouTube video transcript and output it as structured JSON.

Usage:
    uv run python3 fetch_transcript.py <url_or_video_id> [--language zh,en] [--timestamps] [--output PATH]

Default language preference is Chinese first, then English. If the preferred
language fetch fails, the script retries once without language restriction.

This script ONLY fetches YouTube captions. It never downloads audio and never
falls back to ASR — when captions are unavailable it prints an error JSON to
stdout and exits 1, leaving the ASR decision to the agent (see SKILL.md step 1).

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
import re
import sys
from pathlib import Path


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


def fail(payload: dict) -> None:
    """Print an error JSON to stdout and exit 1 (agent parses stdout)."""
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube transcript as JSON")
    parser.add_argument("url", help="YouTube URL or 11-char video ID")
    parser.add_argument("--language", "-l", default="zh,en",
                        help="Comma-separated language codes (e.g. zh,en). Default: zh,en")
    parser.add_argument("--timestamps", "-t", action="store_true",
                        help="Include timestamped text in output")
    parser.add_argument("--text-only", action="store_true",
                        help="Output plain text instead of JSON")
    parser.add_argument("--output", "-o", default=None,
                        help="Write the JSON archive to this path instead of stdout "
                             "(parent directories are created; the file is verified "
                             "non-empty after writing)")
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
            combined = (error_msg + " " + first_error_msg).lower()
            if "blocking requests from your ip" in combined:
                fail({"error": "YouTube is blocking this server's IP. Use HTTPS_PROXY or fetch from another machine. See SKILL.md pitfall #1.",
                      "captions_unavailable": False})
            captions_gone = ("disabled" in combined) or ("no transcript" in combined)
            fail({"error": error_msg,
                  "first_error": first_error_msg,
                  "captions_unavailable": captions_gone,
                  "hint": "captions_unavailable=true means the ASR fallback path (SKILL.md step 1) is applicable — ask the user before running it."})

    full_text = " ".join(seg["text"] for seg in segments)
    timestamped = "\n".join(
        f"{format_timestamp(seg['start'])} {seg['text']}" for seg in segments
    )

    if not full_text.strip():
        fail({"error": "transcript fetched but full_text is empty",
              "video_id": video_id,
              "captions_unavailable": True})

    if args.text_only:
        out = timestamped if args.timestamps else full_text
        if args.output:
            _write_verified(Path(args.output), out)
        else:
            print(out)
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

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        _write_verified(Path(args.output), payload)
        # Also echo to stdout so the agent sees the content without re-reading.
        print(payload)
    else:
        print(payload)


def _write_verified(path: Path, content: str) -> None:
    """Write file and verify it landed non-empty (SKILL.md pitfall #7)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    size = path.stat().st_size
    if size == 0:
        print(f"Error: wrote 0-byte file — {path}", file=sys.stderr)
        sys.exit(1)
    print(f"[fetch_transcript] archived {size} bytes -> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
