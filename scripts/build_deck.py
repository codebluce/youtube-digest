#!/usr/bin/env python3
"""从主文生成记忆卡组 <stem>-deck.tsv（Anki 可直接导入）。

为什么要有第二个产物
─────────────────────────────────────────────────────────────────────────
主文是「读」的产物。蓝图自己写明：Takeaway 只是"再读一遍并点头"（recognition），
不产生长期记忆；真正的检索练习只有 S5 闭卷自测承担，而它只占全文一成上下。

卡组把这个比例反过来：它不新增任何内容——数字锚点表、闭卷自测、我错了的信号
里的材料本来就在——只是把它们重排成**跨天可考**的形态。
这是全案里唯一一个把「一次性阅读」变成「跨天检索」的改动，且零内容成本。

v3.0（随 blueprint v5.0）：讲错风险与 🚧 边界随主文一起砍除，「纠错」「边界」
两类卡下线。现存三类：综合（S5 闭卷自测）、证伪（S6 我错了的信号）、
数字与数字反向（S4 数字锚点表）。

三条设计要求（否则退化成卡片包的又一个副本）
  ① 原子化   一卡一事实，不能是段落切片
  ② 双向     数字类正反两问，单向卡会产生只认前半句的假记忆
  ③ 可信度进标签  ::实/::推/::测 写进 Anki tag，复习时可信度分层跟着一起被复习

本脚本产出的是**草稿**。agent 必须逐条过一遍：删掉查表即可答的、合并重复的、
把陈述句改成问句。机械生成能到 80%，最后 20% 是判断力。

用法:
    python3 build_deck.py <article.md> [-o <out.tsv>] [--stdout]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credibility import VALID_TAGS, map_source_to_tag  # noqa: E402

TAG_CHAR = {"【实】": "实", "【推】": "推", "【测】": "测"}


def extract_section(text: str, anchor: str) -> str | None:
    m = re.search(rf"^(#{{2,4}})\s*[^\n]*{anchor}[^\n]*\n", text, re.M)
    if not m:
        return None
    level = len(m.group(1))
    start = m.end()
    tail = re.search(rf"^#{{1,{level}}}\s", text[start:], re.M)
    return text[start : start + tail.start()] if tail else text[start:]


def _todolist_map() -> dict[str, str]:
    """从 workspace/todolist.md 的「已完成」表读出 主文文件名 → video_id。"""
    path = Path(__file__).resolve().parents[1] / "workspace" / "todolist.md"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", cells[1]):
            stem = Path(cells[3]).stem
            if stem:
                out[stem] = cells[1]
    return out


def video_id(stem: str, article: str = "") -> str:
    """取 video_id 作为 Anki 标签前缀。

    v2.1 起文件名是纯中文标题（`<日期>-<中文标题>.md`），不再含 video_id。
    查找顺序：正文里的 `video_id: XXX` 声明 → todolist「已完成」表 → 旧式文件名 → 兜底。

    **兜底必须是 ASCII 且不含空格**：Anki 用空格分隔 tag，中文标题直接当标签会
    被拆成好几个碎片标签，复习时按标签筛选就全乱了。
    """
    m = re.search(r"video[_\s-]?id\s*[:：]\s*([A-Za-z0-9_-]{6,20})", article)
    if m:
        return m.group(1)
    mapped = _todolist_map().get(stem)
    if mapped:
        return mapped
    for part in stem.split("-"):
        # 必须是纯 ASCII：中文标题里的汉字 c.isalpha() 也为真，不加这一条，
        # v2.1 起的中文文件名会被整段当成 video_id，而 Anki 用空格分隔 tag，
        # 中文标题直接当标签会被拆成一串碎片标签。
        if not part.isascii():
            continue
        if len(part) >= 10 and any(c.isdigit() for c in part) and any(c.isalpha() for c in part):
            if not re.fullmatch(r"\d{4}|\d{2}", part):
                return part
    date = re.match(r"(\d{4}-\d{2}-\d{2})", stem)
    digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:6]
    return f"{date.group(1) if date else 'undated'}-{digest}"


def clean(s: str) -> str:
    s = re.sub(r"\*\*|`|<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ── 各来源的抽卡逻辑 ────────────────────────────────────────────────────


def cards_from_numbers(article: str, vid: str) -> list[tuple[str, str, str]]:
    """S4 数字锚点表 → 双向数字卡（符号由来源强度经 credibility.py 映射得出）。"""
    out: list[tuple[str, str, str]] = []
    pattern = r"^\|\s*数字\s*\|\s*含义\s*\|\s*来源强度\s*\|\s*\n\|[-\s|:]+\|\s*\n((?:\|.*\n)+)"
    for block in re.finditer(pattern, article, re.M):
        for line in block.group(1).strip().split("\n"):
            cells = [clean(c) for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or not cells[0] or cells[0].startswith("⚠️"):
                continue
            if cells[2].startswith("⚠️") or len(cells[2]) > 24:
                continue
            num, meaning, src = cells[0], cells[1], cells[2]
            tag, _ = map_source_to_tag(src, meaning)
            tc = TAG_CHAR[tag]
            hedge = "" if tc == "实" else "（口径：%s，对外引用加「视频称」）" % src
            out.append((f"{meaning}——数值是多少？", f"{num}　{tag}{hedge}", f"{vid}::数字::{tc}"))
            out.append((f"「{num}」在本篇指的是什么？", f"{meaning}　{tag}", f"{vid}::数字反向::{tc}"))
    return out


def cards_from_quiz(article: str, vid: str) -> list[tuple[str, str, str]]:
    """闭卷自测 → 综合卡（跨章题，卡组里价值最高的一类）。"""
    out: list[tuple[str, str, str]] = []
    block = extract_section(article, "闭卷自测")
    if not block:
        return out
    # 两种题号写法都要吃：「1. 题面」与「**Q1.** 题面」
    pattern = (r"^(?:\*\*Q\d+\.\*\*|\d+\.)\s*(.+?)\n+"
               r"<details>.*?</summary>\s*(.*?)\s*</details>")
    for q, a in re.findall(pattern, block, re.S | re.M):
        q, a = clean(q), clean(a)
        a = re.sub(r"□\s*我答错了.*$", "", a, flags=re.S).strip()
        a = re.sub(r"[｜|]?\s*答不上\s*→.*$", "", a, flags=re.S).strip()
        if not q or not a:
            continue
        tc = "推"
        for t in VALID_TAGS:
            if t in a:
                tc = TAG_CHAR[t]
                break
        out.append((q, a, f"{vid}::综合::{tc}"))
    return out


def cards_from_falsification(article: str, vid: str) -> list[tuple[str, str, str]]:
    """S6「我错了的信号」→ 证伪卡。

    v2.0 新增，补上概念卡下线后的额度。为什么这类卡比概念定义卡值钱：概念定义
    在被追问时几乎从不出问题（要么记得要么查得到），真正会当场哑火的是"你凭什么
    认为自己是对的、什么情况下你会改主意"。它考的是判断的边界，不是词条。
    """
    out: list[tuple[str, str, str]] = []
    block = extract_section(article, "立场与证伪")
    if not block:
        return out
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    stance = ""
    for ln in lines:
        # 立场标题：**立场A：xxx** / ### 立场一 xxx / 立场：xxx
        m = re.match(r"^(?:#{2,4}\s*)?\*{0,2}立场\s*[A-Za-z一二三1-9]?\s*[：:·、]?\s*(.+?)\*{0,2}$", ln)
        if m and len(clean(m.group(1))) > 1:
            stance = clean(m.group(1))
            continue
        m2 = re.match(r"^[-*|\s]*\*{0,2}我错了的信号\*{0,2}\s*[：:▸|]\s*(.+)$", ln)
        if m2:
            signal = clean(m2.group(1)).strip("| ")
            if not signal or signal.startswith("▸"):
                continue
            head = stance or "本文的这个立场"
            out.append((f"「{head}」这个判断，看到什么就该推翻？",
                        f"{signal}　【测】（这是可观测事件，不是感觉）",
                        f"{vid}::证伪::测"))
    return out


# ── 组装 ────────────────────────────────────────────────────────────────


def build(article_path: Path, cap: int = 32):
    article = article_path.read_text(encoding="utf-8")
    vid = video_id(article_path.stem, article)

    rows = (
        cards_from_quiz(article, vid)
        + cards_from_falsification(article, vid)
        + cards_from_numbers(article, vid)
    )

    seen: set[str] = set()
    deduped: list[tuple[str, str, str]] = []
    for front, back, tag in rows:
        key = re.sub(r"\W", "", front)
        if key in seen or not back:
            continue
        seen.add(key)
        deduped.append((front, back, tag))

    # 优先级：能考「机制」与「边界」的排在能考「事实」的前面。
    order = {"综合": 0, "证伪": 1, "数字": 2, "数字反向": 2}

    def rank(row: tuple[str, str, str]) -> int:
        kind = row[2].split("::")[1] if "::" in row[2] else ""
        return order.get(kind, 9)

    deduped.sort(key=rank)
    if cap and len(deduped) > cap:
        kept, dropped = deduped[:cap], deduped[cap:]
        # 数字卡必须正反成对：截断点可能正好落在一对中间，留下一张孤儿卡。
        # 孤儿卡是最坏的一种卡——读者只认前半句，听到数字认不出它属于谁。
        # 从尾部往回退，直到正反数量相等（validator 也会拦这一项）。
        def kind(row):
            return row[2].split("::")[1] if "::" in row[2] else ""
        while kept and kind(kept[-1]) in ("数字", "数字反向"):
            fwd = sum(1 for r in kept if kind(r) == "数字")
            bwd = sum(1 for r in kept if kind(r) == "数字反向")
            if fwd == bwd:
                break
            dropped.insert(0, kept.pop())
        return kept, dropped
    return deduped, []


def main() -> int:
    ap = argparse.ArgumentParser(description="生成记忆卡组（Anki TSV）")
    ap.add_argument("article")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--cap", type=int, default=32, help="卡片数上限（0 = 不限）")
    args = ap.parse_args()

    article_path = Path(args.article)
    if not article_path.is_file():
        print(f"错误: 主文不存在 — {article_path}", file=sys.stderr)
        return 2
    rows, dropped = build(article_path, args.cap)
    header = [
        "# youtube-digest 记忆卡组（草稿）",
        "# 导入 Anki：文件 → 导入 → 字段分隔符 Tab → 允许 HTML 关闭 → 第三列映射为 Tags",
        "# ⚠️ 这是机械生成的草稿，交付前必须人工过一遍：",
        "#    删掉查表即可答的、合并语义重复的、把陈述句改成问句。",
        f"# 共 {len(rows)} 张"
        + (f"（按优先级截断；另有 {len(dropped)} 张候选未收录，--cap 0 可查看全部）" if dropped else ""),
    ]
    body = "\n".join("\t".join(r) for r in rows)
    text = "\n".join(header) + "\n" + body + "\n"

    if args.stdout:
        sys.stdout.write(text)
    else:
        out = Path(args.out) if args.out else article_path.with_name(f"{article_path.stem}-deck.tsv")
        out.write_text(text, encoding="utf-8")
        print(f"已写出 {out.name}：{len(rows)} 张"
              + (f"，另有 {len(dropped)} 张候选被截断（不是静默丢弃：用 --cap 0 全量导出）" if dropped else ""))
        if len(rows) < 20:
            print("⚠️ 不足 20 张，需要人工补卡（validator 会拦）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
