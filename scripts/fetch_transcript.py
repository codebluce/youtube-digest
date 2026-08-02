#!/usr/bin/env python3
"""多源视频 transcript 抓取入口。

支持任意已注册的视频源(YouTube/Bilibili/未来扩展),自动识别 URL 路由到对应 adapter。
字幕不可用时输出明确错误码 `captions_unavailable`,由调用方决定走 ASR fallback
(见 SKILL.md 步骤 1 末尾的 ASR 命令模板 — 与源头无关,统一走 yt-dlp + faster-whisper)。

用法:
    python3 fetch_transcript.py <URL或video_id> [--language zh,en] [--timestamps]
                                [--output FILE] [--metadata-only]

成功(stdout 最后行,JSON):
    {"ok": true, "source": "youtube", "video_id": "...", "json": "...", "timestamped": "..."}

字幕不可用(exit 3,stderr JSON):
    {"error": "...", "captions_unavailable": true,
     "audio_fallback": {"url": "...", "video_id": "...", "source": "..."}}

URL 不可识别(exit 2):
    {"error": "URL 无法识别", "registered_sources": [...]}

输出文件命名(归档到 workspace/transcripts/,与 SKILL.md 命名约定一致):
    <output 显式指定>  优先
    否则自动:  <date>-<source>-<video_id>.json
               <date>-<source>-<video_id>.timestamped.txt  (仅 --timestamps)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# 让本脚本能找到 sources/ 包 (跨平台)
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from sources import (  # noqa: E402
    CaptionsUnavailableError,
    SourceFetchError,
    SourceNotRecognizedError,
    adapter_for,
    all_sources,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="多源视频 transcript 抓取 (YouTube/Bilibili/...)",
        epilog="新源支持只需在 scripts/sources/ 加一个文件,本入口自动识别。",
    )
    parser.add_argument("url", help="视频 URL 或源内稳定 video_id")
    parser.add_argument("--language", "-l", default="zh,en",
                        help="字幕语言优先级,逗号分隔 (默认 zh,en)")
    parser.add_argument("--timestamps", "-t", action="store_true",
                        help="额外输出 timestamped_text 文件")
    parser.add_argument("--output", "-o", default=None,
                        help="输出 JSON 路径 (默认 workspace/transcripts/<date>-<source>-<id>.json)")
    parser.add_argument("--metadata-only", action="store_true",
                        help="只拉元数据不拉字幕 (调试用)")
    args = parser.parse_args()

    languages = [l.strip() for l in args.language.split(",")] if args.language else None

    # ── 1. 识别源与 video_id ──
    try:
        adapter = adapter_for(args.url)
    except SourceNotRecognizedError as e:
        print(json.dumps({
            "error": str(e),
            "registered_sources": sorted(s.SOURCE_NAME for s in all_sources()),
        }, ensure_ascii=False), file=sys.stderr)
        return 2

    try:
        video_id = adapter.__class__.parse_video_id(args.url)
    except SourceNotRecognizedError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2

    # ── 2. 拉元数据 (尽力而为,失败不阻塞) ──
    metadata: dict = {}
    try:
        metadata = adapter.fetch_metadata(video_id) or {}
    except Exception as e:
        print(f"[warn] 元数据拉取失败 ({adapter.SOURCE_NAME}): {e}", file=sys.stderr)

    if args.metadata_only:
        print(json.dumps({
            "ok": True,
            "source": adapter.SOURCE_NAME,
            "video_id": video_id,
            "metadata": metadata,
        }, ensure_ascii=False, indent=2))
        return 0

    # ── 3. 拉字幕 ──
    try:
        transcript = adapter.fetch_transcript(video_id, languages=languages)
    except CaptionsUnavailableError as e:
        # 路由到 ASR fallback — 给调用方足够的信息去跑 yt-dlp + whisper
        print(json.dumps({
            "error": str(e),
            "reason": e.reason,
            "captions_unavailable": True,
            "audio_fallback": {
                "source": adapter.SOURCE_NAME,
                "video_id": video_id,
                "url": adapter.get_audio_download_url(video_id),
                "hint": (
                    "走 ASR fallback: yt-dlp 下载音频 + faster-whisper 转写。"
                    "见 SKILL.md 步骤 1 末尾 ASR 命令模板"
                ),
            },
            "metadata": metadata,
        }, ensure_ascii=False), file=sys.stderr)
        return 3
    except SourceFetchError as e:
        print(json.dumps({
            "error": str(e),
            "source": adapter.SOURCE_NAME,
            "video_id": video_id,
        }, ensure_ascii=False), file=sys.stderr)
        return 4

    # ── 4. 落盘 ──
    if args.output:
        out_json = Path(args.output)
    else:
        today = date.today().isoformat()
        out_json = Path("workspace/transcripts") / f"{today}-{adapter.SOURCE_NAME}-{video_id}.json"

    out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = transcript.to_dict()
    payload["raw_metadata"] = metadata

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    out_json.write_text(json_text, encoding="utf-8")

    # 步骤 2 的硬要求: 写完必须验证非空
    if out_json.stat().st_size == 0:
        print(json.dumps({
            "error": f"落盘文件为空 {out_json} — 见 SKILL.md pitfall #7"
        }, ensure_ascii=False), file=sys.stderr)
        return 5

    out_ts = None
    if args.timestamps and transcript.timestamped_text:
        out_ts = out_json.with_suffix(".timestamped.txt")
        out_ts.write_text(transcript.timestamped_text, encoding="utf-8")

    # ── 5. 输出摘要 (机器可读) ──
    print(json.dumps({
        "ok": True,
        "source": transcript.source,
        "video_id": transcript.video_id,
        "language": transcript.language,
        "source_track": transcript.source_track,
        "segment_count": transcript.segment_count,
        "duration": transcript.duration,
        "json": str(out_json),
        "timestamped": str(out_ts) if out_ts else None,
        "metadata_excerpt": {
            "title": metadata.get("title"),
            "uploader": metadata.get("uploader"),
            "duration": metadata.get("duration"),
        },
    }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
