#!/usr/bin/env python3
"""全仓一致性审计 —— 在 validate_output.py 单篇校验之上，检查 workspace 级别的配对完整性。

检查项：
  1. 每篇正式文章 articles/<date>-<vid>-<slug>.md 都有对应的 <stem>-cards.md
  2. 每篇文章的 video_id 在 transcripts/ 下有非空归档（.json 或 .asr.json）
  3. transcript 归档 JSON 可解析且 full_text 非空
  4. 逐篇跑 validate_output.py，任一篇 FAIL 则整体 FAIL
  5. .env 未被 git 追踪（防 S1 类事故复发）

用法:
    python3 audit_workspace.py [--skip-validator]

退出码: 0 全部通过；1 存在问题；2 环境错误
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ARTICLES = SKILL_DIR / "workspace" / "articles"
TRANSCRIPTS = SKILL_DIR / "workspace" / "transcripts"
VALIDATOR = SKILL_DIR / "scripts" / "validate_output.py"

# 文件名格式：
#   旧版: <YYYY-MM-DD>-<youtube_video_id>-<slug>.md
#   多源: <YYYY-MM-DD>-<source>-<source_video_id>-<slug>.md
LEGACY_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([A-Za-z0-9_-]{11})-(.+)\.md$")
MULTISOURCE_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z][a-z0-9]*)-([A-Za-z0-9_]+)-(.+)\.md$")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="审计 youtube-digest workspace 一致性")
    ap.add_argument("--skip-validator", action="store_true",
                    help="只做配对/归档检查，不逐篇调用 validate_output.py")
    args = ap.parse_args()

    problems = 0

    # ── 检查 5 最先做：.env 不得被 git 追踪 ──
    print("检查 .env 是否被 git 追踪 …")
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env"],
            cwd=SKILL_DIR, capture_output=True, text=True,
        )
        if tracked.returncode == 0:
            fail(".env 被 git 追踪 —— 立即 git rm --cached .env 并轮换泄露的密钥")
            problems += 1
        else:
            ok(".env 未被 git 追踪")
    except FileNotFoundError:
        print("  WARN  git 不可用，跳过 .env 追踪检查")

    if not ARTICLES.is_dir():
        print(f"错误: 文章目录不存在 — {ARTICLES}", file=sys.stderr)
        return 2

    articles = sorted(
        p for p in ARTICLES.glob("*.md")
        if not p.name.endswith("-cards.md") and (LEGACY_NAME_RE.match(p.name) or MULTISOURCE_NAME_RE.match(p.name))
    )
    if not articles:
        print("未发现任何正式文章（articles/ 下无 <date>-<vid>-<slug>.md）")
        return 0

    print(f"\n发现 {len(articles)} 篇正式文章，逐篇检查 …\n")

    for art in articles:
        legacy = LEGACY_NAME_RE.match(art.name)
        multi = MULTISOURCE_NAME_RE.match(art.name)
        if multi:
            date, source, vid = multi.group(1), multi.group(2), multi.group(3)
            transcript_prefixes = [f"{date}-{source}-{vid}", f"{date}-{vid}"]
        else:
            date, vid = legacy.group(1), legacy.group(2)
            transcript_prefixes = [f"{date}-{vid}"]
        print(f"■ {art.name}")

        # 1. 卡片包配对
        cards = art.with_name(f"{art.stem}-cards.md")
        if cards.is_file() and cards.stat().st_size > 0:
            ok(f"卡片包配对 ({cards.name})")
        else:
            fail(f"缺卡片包或为空 — 期望 {cards.name}")
            problems += 1

        # 2+3. transcript 归档存在、非空、可解析
        candidates = []
        for prefix in transcript_prefixes:
            candidates.extend([TRANSCRIPTS / f"{prefix}.json", TRANSCRIPTS / f"{prefix}.asr.json"])
        archive = next((p for p in candidates if p.is_file()), None)
        if archive is None:
            expected_names = " 或 ".join(p.name for p in candidates)
            fail(f"transcript 归档缺失 — 期望 {expected_names}")
            problems += 1
        elif archive.stat().st_size == 0:
            fail(f"transcript 归档为 0 字节 — {archive.name}")
            problems += 1
        else:
            try:
                data = json.loads(archive.read_text(encoding="utf-8"))
                if data.get("full_text", "").strip():
                    ok(f"transcript 归档有效 ({archive.name}, {archive.stat().st_size} bytes)")
                else:
                    fail(f"transcript 归档 full_text 为空 — {archive.name}")
                    problems += 1
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                fail(f"transcript 归档 JSON 不可解析 — {archive.name}: {exc}")
                problems += 1

        # 4. 单篇 validator（显式 UTF-8，Windows 默认 GBK 会解码失败）
        if not args.skip_validator:
            r = subprocess.run(
                [sys.executable, str(VALIDATOR), str(art)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            tail = (r.stdout + r.stderr).strip().splitlines()
            verdict = next((ln for ln in reversed(tail) if ln.startswith("结论")), tail[-1] if tail else "")
            if r.returncode == 0:
                ok(f"validator 通过 ({verdict.strip()})")
            else:
                fail(f"validator 未通过 ({verdict.strip()}) — 单独跑 validate_output.py 查看明细")
                problems += 1
        print()

    print("=" * 60)
    if problems:
        print(f"审计未通过：{problems} 个问题。修复后重跑，不得推送不合规产出。")
        return 1
    print("审计通过：全部文章双产物齐备、transcript 归档有效、单篇校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
