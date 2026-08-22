#!/usr/bin/env python3
"""扫描 workspace/review-queue.md，列出今天到期的复习项。

用法:
    python3 review_due.py [--date YYYY-MM-DD] [--all]
    python3 review_due.py --done <video_id> [--wrong 3,5] [--date YYYY-MM-DD]

退出码:
    0  有到期项（或 --done 执行成功）
    1  今天没有到期项
    2  队列文件缺失 / 参数错误
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import signal
import sys
from pathlib import Path

# 被 `| head` 截断时安静退出，不吐 BrokenPipeError
with __import__("contextlib").suppress(AttributeError, ValueError):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

QUEUE = Path(__file__).resolve().parents[1] / "workspace" / "review-queue.md"

# 间隔序列：答对进下一档，答错退一档（最低回到 D+1）
INTERVALS = [1, 3, 7, 16, 35]


def parse_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    section = re.search(r"## 待复习\n(.*?)(?=\n>|\n---|\n## )", text, re.S)
    if not section:
        return rows
    for line in section.group(1).strip().split("\n"):
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[0] in ("video_id", ""):
            continue
        rows.append({
            "vid": cells[0], "article": cells[1], "first": cells[2],
            "due": cells[3], "count": cells[4], "wrong": cells[5],
            "status": cells[6], "raw": line,
        })
    return rows


def cmd_due(rows: list[dict], today: dt.date, show_all: bool) -> int:
    due = []
    for r in rows:
        try:
            d = dt.date.fromisoformat(r["due"])
        except ValueError:
            continue
        if show_all or d <= today:
            due.append((d, r))
    if not due:
        print(f"{today}：没有到期的复习项。")
        return 1
    due.sort(key=lambda x: x[0])
    print(f"{today} 到期 {len(due)} 项：\n")
    for d, r in due:
        overdue = (today - d).days
        flag = f"逾期 {overdue} 天" if overdue > 0 else "今天到期"
        deck = Path(r["article"]).stem + "-deck.tsv"
        nth = int(r["count"] or 0) + 1
        print(f"  · {r['vid']}  第 {nth} 次复习  （{flag}）")
        print(f"    卡组：{deck}")
        if r["wrong"] not in ("—", "-", ""):
            print(f"    ⚠️ 上次错题优先出：{r['wrong']}")
        print()
    print("复习完成后：python3 review_due.py --done <video_id> [--wrong 3,5]")
    return 0


def cmd_done(text: str, rows: list[dict], vid: str, wrong: str, today: dt.date) -> int:
    target = next((r for r in rows if r["vid"] == vid), None)
    if not target:
        print(f"错误: 队列中没有 {vid}", file=sys.stderr)
        return 2
    count = int(target["count"] or 0)
    # 答错退一档，答对进一档
    idx = max(0, count - 1) if wrong else count
    if idx >= len(INTERVALS):
        print(f"{vid} 已走完 D+{INTERVALS[-1]}，请手动移入「已归档」表。")
        return 0
    nxt = today + dt.timedelta(days=INTERVALS[idx])
    new_cells = [vid, target["article"], target["first"], nxt.isoformat(),
                 str(idx + 1), wrong or "—", "待复习"]
    new_line = "| " + " | ".join(new_cells) + " |"
    QUEUE.write_text(text.replace(target["raw"], new_line), encoding="utf-8")
    print(f"{vid} → 下次复习 {nxt}（第 {idx + 1} 次）" + (f"，错题 {wrong} 已记录" if wrong else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="复习队列到期扫描")
    ap.add_argument("--date", default=None, help="模拟日期 YYYY-MM-DD")
    ap.add_argument("--all", action="store_true", help="列出全部，不只到期项")
    ap.add_argument("--done", default=None, metavar="VIDEO_ID", help="标记某条已复习")
    ap.add_argument("--wrong", default="", help="本次答错的题号，如 3,5（留空=全对）")
    args = ap.parse_args()

    if not QUEUE.is_file():
        print(f"错误: 找不到 {QUEUE}", file=sys.stderr)
        return 2
    text = QUEUE.read_text(encoding="utf-8")
    rows = parse_rows(text)
    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()

    if args.done:
        return cmd_done(text, rows, args.done, args.wrong, today)
    return cmd_due(rows, today, args.all)


if __name__ == "__main__":
    sys.exit(main())
