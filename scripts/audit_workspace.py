#!/usr/bin/env python3
"""全仓一致性审计 —— 在 validate_output.py 单篇校验之上，检查 workspace 级别的配对完整性。

检查项：
  1. 若某篇生成了 <stem>-deck.tsv，则它必须非空（v5.1 起卡组是按需产物，缺席不算问题）
  2. 每篇文章通过 workspace/todolist.md 已完成表关联 video_id，并在 transcripts/ 下有非空归档（.json 或 .asr.json）
  3. transcript 归档 JSON 可解析且 full_text 非空
  4. 逐篇跑 validate_output.py，任一篇 FAIL 则整体 FAIL
  5. .env 未被 git 追踪（防密钥泄露事故复发）

v5.1：卡片包已取消，卡组改为按需生成。仓库里遗留的 `*-cards.md` 是历史产物，
跳过不检查、也不当作文章。

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
TODOLIST = SKILL_DIR / "workspace" / "todolist.md"
VALIDATOR = SKILL_DIR / "scripts" / "validate_output.py"

# article 文件名格式：<YYYY-MM-DD>-<中文标题>.md。
# 允许标题中出现英文/数字/标点；禁止 source/video_id/英文 slug 不是靠正则识别，
# 而是在命名规范与 review 中约束。这里仅要求日期前缀 + .md。
ARTICLE_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")

# 已完成表行：| 完成日期 | video_id | 标题 | 主文 | 处理者备注 |
DONE_ROW_RE = re.compile(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*([^|]+?)\s*\|\s*[^|]+\|\s*([^|]+?)\s*\|")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def load_done_article_map() -> dict[str, str]:
    """从 todolist 已完成表读取 article 路径 -> video_id 映射。"""
    if not TODOLIST.is_file():
        return {}
    mapping: dict[str, str] = {}
    for line in TODOLIST.read_text(encoding="utf-8").splitlines():
        m = DONE_ROW_RE.match(line)
        if not m:
            continue
        video_id = m.group(1).strip()
        article = m.group(2).strip()
        if article and article != "—":
            mapping[article.replace("\\", "/")] = video_id
    return mapping


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

    done_map = load_done_article_map()
    articles = sorted(
        p for p in ARTICLES.glob("*.md")
        if not p.name.endswith("-cards.md") and ARTICLE_NAME_RE.match(p.name)
    )
    if not articles:
        print("未发现任何正式文章（articles/ 下无 <date>-<中文标题>.md）")
        return 0

    print(f"\n发现 {len(articles)} 篇正式文章，逐篇检查 …\n")

    for art in articles:
        m = ARTICLE_NAME_RE.match(art.name)
        date = m.group(1)
        rel_article = art.relative_to(SKILL_DIR).as_posix()
        vid = done_map.get(rel_article)
        print(f"■ {art.name}")

        # 1. 卡组配对（只对 v4.0 及以后的文章要求；老文章豁免）
        deck = art.with_name(f"{art.stem}-deck.tsv")
        if not deck.is_file():
            # v5.1 起卡组按需生成，没有不算问题
            ok("本篇未生成卡组（按需产物）")
        elif deck.stat().st_size > 0:
            ok(f"卡组存在且非空 ({deck.name})")
        else:
            fail(f"卡组为 0 字节 — {deck.name}")
            problems += 1

        # 2+3. transcript 归档存在、非空、可解析
        archive = None
        if not vid:
            fail(f"todolist 已完成表未登记该主文路径 — {rel_article}")
            problems += 1
        else:
            candidates = sorted(TRANSCRIPTS.glob(f"{date}-*{vid}*.json"))
            archive = next((p for p in candidates if p.name.endswith(".json") and p.is_file()), None)
            if archive is None:
                fail(f"transcript 归档缺失 — 未找到 {date}-*{vid}*.json")
                problems += 1

        if archive is not None:
            if archive.stat().st_size == 0:
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
            verdict = next((ln for ln in reversed(tail) if ln.startswith(("结论", "跳过"))), tail[-1] if tail else "")
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
    print("审计通过：transcript 归档有效、单篇校验通过（卡组按需，缺席不算问题）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
