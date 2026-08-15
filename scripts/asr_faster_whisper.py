#!/usr/bin/env python3
"""Transcribe local audio/video with faster-whisper.

Default model: large-v3-turbo. Default language: zh.

Model choice rationale:
    large-v3-turbo offers near-large-v3 accuracy at ~2x the speed (≈809M params,
    int8 ≈1.6GB, ≈1.9GB RSS at runtime). On Apple Silicon M-series it runs CPU-only
    (CTranslate2 has no Metal backend), but the P-cores + Accelerate int8 path is
    fast enough for typical video lengths. Falls back to `medium` on weaker machines
    via --model medium. Set HF_HUB_DISABLE_XET=1 behind a HF mirror to avoid Xet 401s.

Cache directory resolution (platform-agnostic, no hardcoded drive/path):
    1. --cache-dir if explicitly passed
    2. existing HF_HOME env var if already exported (see SKILL.md Setup)
    3. ~/.cache/huggingface as a last-resort cross-platform default

Usage:
    python scripts/asr_faster_whisper.py workspace/audio/video.webm \
      --model large-v3-turbo --language zh --output-prefix workspace/transcripts/video
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def format_ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def resolve_cache_dir(cache_dir_arg: str | None) -> Path:
    """Never hardcode a machine-specific path — see module docstring for the order."""
    if cache_dir_arg:
        return Path(cache_dir_arg)
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"])
    return Path.home() / ".cache" / "huggingface"


def set_hf_cache(cache_dir: Path) -> None:
    os.environ.setdefault("HF_HOME", str(cache_dir))
    os.environ.setdefault("HF_HUB_CACHE", str(cache_dir / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(cache_dir / "transformers"))
    # Mirror + disable Xet backend so first-run downloads work behind a CN mirror
    # without 401/Xet-CDN timeouts. Only setdefault — explicit env wins.
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    (cache_dir / "hub").mkdir(parents=True, exist_ok=True)
    (cache_dir / "transformers").mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="ASR transcription via faster-whisper")
    parser.add_argument("input", help="audio/video file path")
    parser.add_argument("--model", default="large-v3-turbo", help="Whisper model name, default: large-v3-turbo (fallback: medium on weaker CPUs)")
    parser.add_argument("--language", default="zh", help="language code, default: zh")
    parser.add_argument("--device", default="cpu", help="cpu or cuda, default: cpu")
    parser.add_argument("--compute-type", default="int8", help="default: int8 for CPU")
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="HF cache dir; defaults to $HF_HOME if set, else ~/.cache/huggingface",
    )
    parser.add_argument("--output-prefix", default=None, help="output file prefix without suffix")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--vad", action="store_true", default=True, help="enable VAD filter")
    parser.add_argument("--no-vad", dest="vad", action="store_false")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"input file not found: {input_path}")

    cache_dir = resolve_cache_dir(args.cache_dir)
    set_hf_cache(cache_dir)

    from faster_whisper import WhisperModel

    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
        download_root=str(cache_dir),
    )
    out_prefix = Path(args.output_prefix) if args.output_prefix else input_path.with_suffix("")
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    partial_txt_path = out_prefix.with_suffix(".partial.full.txt")
    partial_ts_path = out_prefix.with_suffix(".partial.timestamped.txt")
    partial_txt_path.write_text("", encoding="utf-8")
    partial_ts_path.write_text("", encoding="utf-8")

    segments_iter, info = model.transcribe(
        str(input_path),
        language=args.language,
        beam_size=args.beam_size,
        vad_filter=args.vad,
    )

    segments = []
    with partial_txt_path.open("a", encoding="utf-8") as partial_txt, partial_ts_path.open("a", encoding="utf-8") as partial_ts:
        for seg in segments_iter:
            item = {
                "id": seg.id,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            }
            segments.append(item)
            if item["text"]:
                partial_txt.write(item["text"] + "\n")
                partial_ts.write(f"[{format_ts(item['start'])}-{format_ts(item['end'])}] {item['text']}\n")
                partial_txt.flush()
                partial_ts.flush()
            print(json.dumps({"progress": True, "segment": item["id"], "end": format_ts(item["end"]), "text": item["text"][:80]}, ensure_ascii=False), flush=True)

    full_text = "\n".join(s["text"] for s in segments if s["text"])
    timestamped = "\n".join(
        f"[{format_ts(s['start'])}-{format_ts(s['end'])}] {s['text']}" for s in segments
    )

    payload = {
        "input": str(input_path),
        "model": args.model,
        "language": getattr(info, "language", args.language),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "segment_count": len(segments),
        "segments": segments,
        "full_text": full_text,
        "timestamped_text": timestamped,
    }

    json_path = out_prefix.with_suffix(".asr.json")
    txt_path = out_prefix.with_suffix(".full.txt")
    ts_path = out_prefix.with_suffix(".timestamped.txt")

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(full_text, encoding="utf-8")
    ts_path.write_text(timestamped, encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "model": args.model,
        "language": payload["language"],
        "duration": payload["duration"],
        "segment_count": len(segments),
        "json": str(json_path),
        "text": str(txt_path),
        "timestamped": str(ts_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
