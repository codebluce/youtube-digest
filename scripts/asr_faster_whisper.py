#!/usr/bin/env python3
"""Transcribe local audio/video with faster-whisper.

Default model: medium. Default language: zh. Default cache: D:/models/huggingface.

Usage:
    python scripts/asr_faster_whisper.py workspace/audio/video.webm \
      --model medium --language zh --output-prefix workspace/transcripts/video
"""

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


def set_hf_cache(cache_dir: str) -> None:
    cache = Path(cache_dir)
    os.environ.setdefault("HF_HOME", str(cache))
    os.environ.setdefault("HF_HUB_CACHE", str(cache / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(cache / "transformers"))
    (cache / "hub").mkdir(parents=True, exist_ok=True)
    (cache / "transformers").mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="ASR transcription via faster-whisper")
    parser.add_argument("input", help="audio/video file path")
    parser.add_argument("--model", default="medium", help="Whisper model name, default: medium")
    parser.add_argument("--language", default="zh", help="language code, default: zh")
    parser.add_argument("--device", default="cpu", help="cpu or cuda, default: cpu")
    parser.add_argument("--compute-type", default="int8", help="default: int8 for CPU")
    parser.add_argument("--cache-dir", default="D:/models/huggingface", help="HF cache dir")
    parser.add_argument("--output-prefix", default=None, help="output file prefix without suffix")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--vad", action="store_true", default=True, help="enable VAD filter")
    parser.add_argument("--no-vad", dest="vad", action="store_false")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"input file not found: {input_path}")

    set_hf_cache(args.cache_dir)

    from faster_whisper import WhisperModel

    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
        download_root=args.cache_dir,
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
