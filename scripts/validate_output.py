#!/usr/bin/env python3
"""校验 youtube-digest 产出是否符合 article-blueprint v4.0 / deck-spec v2.0。

这是**漂移控制的强制门禁**：不同 LLM agent 执行同一 skill 时，文字规范会被各自
解读，机械校验不会。产出后必须通过本脚本且 exit 0 才算完成。

v4.0 = 减法 + 跨天记忆
─────────────────────────────────────────────────────────────────────────
结构：导读（无标题，紧跟主标题）+ 正文 7 模块（S1-S7）+ 文末附录 1 项（A1 元信息）。
v5.0 又砍掉三块：个人接口、🚧 该承认不知道的边界、讲错风险清单；附录只留来源频道。
产物：主文（卡片包已取消）。记忆卡组自 v5.1 起改为**按需**产物——默认不生成，
只有 <stem>-deck.tsv 存在或显式传 --deck 时才校验它。

从 v3.0 继承的 P0 检查（都是 bug 修复，不是新功能）：
  · 可信度映射一致性   数字的「来源强度」→【实/推/测】必须按唯一映射转换
  · 前瞻不得标实       含「预计/预期/有望…」的条目一律【测】
  · 自相矛盾写法       禁止「【实】视频口述」这类符号与限定词打架的写法
  · 模块层级与顺序     锚点必须落在正确的标题层级上，且顺序与蓝图一致
                      （只做 `anchor in text` 子串匹配时，模块被嵌进上一个模块
                       里当 ### 用，照样满分通过）

版本判定：主文元信息行写 `蓝图版本：v4.0` 即按 v4.0 校验。缺该行且命中 ≥3 个
已废止模块名 → 判为 v2.x 老文章，跳过校验并 exit 0（老产出已冻结，重校无意义）。

用法:
    python3 validate_output.py <article.md> [--deck <deck.tsv>] [--type <类型名>] [-v]

退出码:
    0  全部 ERROR 项通过（WARN 不阻断），或文章为 v2.x 老产出
    1  存在 ERROR 项
    2  参数或文件错误
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credibility import (  # noqa: E402
    SELF_CONTRADICTING,
    TAG_REAL,
    VALID_TAGS,
    is_legend_line,
    looser_than,
    map_source_to_tag,
    num_match,
    soft_forecast_hit,
)

# ── 常量 ────────────────────────────────────────────────────────────────

ILLEGAL_TAG_PATTERNS = [
    (r"\[实\]|\[推\]|\[测\]", "半角方括号"),
    (r"【事实】|【推断】|【预测】", "扩写词"),
    (r"【F】|【I】|【P】", "英文缩写"),
    (r"✅\s*事实|❓\s*推断", "emoji 替代"),
]

# (模块ID, 锚点词, 是否条件模块, 允许的标题层级)
# 层级 None = 不是标题（S4 的锚点是正文里的 📌 Takeaway 标记）
# 顺序即 blueprint v4.0 的顺序：正文 S1-S7，A1-A3 后置到文末附录。
ARTICLE_ANCHORS: list[tuple[str, str, bool, tuple[int, ...] | None]] = [
    ("S1", "读前预判", False, (2,)),
    ("S2", "30 秒速览", False, (2,)),
    ("S3", "全片脉络", False, (2,)),
    ("S4", "📌 Takeaway", False, None),
    ("S5", "闭卷自测", False, (2,)),
    ("S6", "立场与证伪", False, (2,)),
    ("S7", "转述与攻防", False, (2,)),
    # —— 文末附录：只剩元信息一节 ——
    ("A1", "来源频道", False, (2, 3)),
]

# v4.0 废止的模块名：出现即为「把砍掉的模块写回来」
RETIRED_ANCHORS = [
    ("怎么读这篇", "阅读路径导航已于 v2.1 废弃"),
    ("知识地图", "v4.0 由 S3 全片脉络取代，分章四要素已砍"),
    ("知识网络", "概念表与关系图已于 v4.0 砍除，迁移锚点下放到各章类比"),
    ("系统性回顾", "重读型模块，v4.0 砍除"),
    ("转述弹药库", "v4.0 更名并瘦身为 S7 转述与攻防"),
    ("多空对照", "v4.0 并入 S6 立场与证伪"),
    ("立场脚手架", "v4.0 并入 S6 立场与证伪"),
    ("跟踪清单", "v4.0 并入 S6，锚点词改为「跟踪指标」"),
    ("失效条件", "v4.0 并入 S6 的「我错了的信号」"),
    ("延伸思考", "v4.0 并入 S7 的 🚧 边界"),
    ("场景变体", "v4.0 砍除"),
    ("可信度总账", "数字加总已废，只保留 A1 的三符号说明"),
    ("10 分钟版", "等于把文章再写一遍，v4.0 砍除"),
    ("个人接口", "v5.0 砍除——留白无法验证是否被使用，实际多为装饰"),
    ("讲错风险", "v5.0 砍除"),
    ("该承认不知道", "v5.0 砍除（🚧 边界）"),
    ("立场与利益相关", "v5.0 砍除，附录只保留来源频道元信息"),
]
LEGACY_THRESHOLD = 3   # 命中这么多废止锚点且无版本行 → 判为老文章

CONTENT_TYPES = ("知识科普型", "公司行业研究型", "宏观策略型", "事件复盘型")
FINANCIAL_TYPES = {"公司行业研究型", "宏观策略型"}   # 触发 S6 跟踪指标表
# v5.0 起这是唯一的条件内容：附录 A3「立场与利益相关」已砍除。

ARTICLE_MIN_CHARS = 6000
ARTICLE_MAX_CHARS = 12000
DECK_MIN_ROWS = 20

INVESTMENT_ADVICE = ["建议买入", "建议卖出", "建议加仓", "建议减仓", "目标价"]


# ── 结果收集 ────────────────────────────────────────────────────────────


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []
        self.passes: list[str] = []
        self.metrics: list[tuple[str, str, str, bool]] = []

    def error(self, item: str, detail: str) -> None:
        self.errors.append(f"{item} — {detail}")

    def warn(self, item: str, detail: str) -> None:
        self.warns.append(f"{item} — {detail}")

    def ok(self, item: str) -> None:
        self.passes.append(item)

    def check(self, cond: bool, item: str, detail: str, fatal: bool = True) -> bool:
        if cond:
            self.ok(item)
        elif fatal:
            self.error(item, detail)
        else:
            self.warn(item, detail)
        return cond

    def metric(self, name: str, value: str, target: str, good: bool) -> None:
        self.metrics.append((name, value, target, good))


# ── 工具函数 ────────────────────────────────────────────────────────────


def cn_chars(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def strip_code_blocks(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def extract_section(text: str, anchor: str) -> str | None:
    """提取标题行含 anchor 的模块正文（锚定到标题行，只在同级或更高级处截断）。"""
    match = re.search(rf"^(#{{2,4}})\s*[^\n]*{re.escape(anchor)}[^\n]*\n", text, re.M)
    if not match:
        return None
    level = len(match.group(1))
    start = match.end()
    tail = re.search(rf"^#{{1,{level}}}\s", text[start:], re.M)
    return text[start : start + tail.start()] if tail else text[start:]


def detect_type(text: str) -> str | None:
    match = re.search(r"内容类型\*{0,2}[：:]\s*`?([^`\n—]+)`?", text)
    if not match:
        return None
    normalized = re.sub(r"[\s/、]", "", match.group(1))
    for known in CONTENT_TYPES:
        if known in normalized or normalized in known:
            return known
    return None


def declared_version(text: str) -> str | None:
    m = re.search(r"蓝图版本\*{0,2}\s*[：:]\s*`?v?([0-9]+\.[0-9]+)", text)
    return f"v{m.group(1)}" if m else None


def version_lt(a: str, b: str) -> bool:
    pa = tuple(int(x) for x in a.lstrip("v").split("."))
    pb = tuple(int(x) for x in b.lstrip("v").split("."))
    return pa < pb


def retired_hits(text: str) -> list[tuple[str, str]]:
    return [(a, why) for a, why in RETIRED_ANCHORS if a in text]


# ── P0 检查（自 v3.0 继承，改为主文内部自洽）──────────────────────────


def parse_anchor_tables(text: str) -> list[tuple[str, str, str]]:
    """解析主文所有「数字 ｜ 含义 ｜ 来源强度」表，返回 (数字, 含义, 来源强度)。"""
    rows: list[tuple[str, str, str]] = []
    pattern = r"^\|\s*数字\s*\|\s*含义\s*\|\s*来源强度\s*\|\s*\n\|[-\s|:]+\|\s*\n((?:\|.*\n)+)"
    for block in re.finditer(pattern, text, re.M):
        for line in block.group(1).strip().split("\n"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or not cells[0]:
                continue
            # 表内常有跨列的 ⚠️ 语境说明行，它不是数字行
            if cells[0].startswith("⚠️") or cells[2].startswith("⚠️") or len(cells[2]) > 24:
                continue
            rows.append((cells[0], cells[1], cells[2]))
    return rows


def check_tag_consistency(article: str, rep: Report) -> None:
    """主文内部一致性 —— v2.x 完全没有的那道闸。

    一个数字在数字锚点表里被标注为什么来源强度，它在速览 / Takeaway / 讲错风险
    等压缩位置出现时，就必须挂映射后的那个符号或更保守的符号。
    实测 2026-08-02 ai-capex-war：主文 33 个数字全是「UP主口述无源」（应为【推】），
    而下游压缩位置大量标【实】——压缩位置恰恰是读者会拿去引用的那些句子。

    （v3.0 的这道检查跨主文与卡片包两个文件；卡片包取消后，同样的漂移改在主文
    内部发生，检查逻辑不变，只是比对范围收进了一个文件。）
    """
    anchors = parse_anchor_tables(article)
    if not anchors:
        rep.check(False, "[P0] 主文可解析出数字锚点表",
                  "未找到「数字 ｜ 含义 ｜ 来源强度」表", fatal=False)
        return

    # 只扫压缩位置：速览 / Takeaway 行 / S7 讲错风险，不扫锚点表本身
    scan: list[str] = []
    for anchor in ("30 秒速览", "转述与攻防", "立场与证伪"):
        blk = extract_section(article, anchor)
        if blk:
            scan.extend(blk.split("\n"))
    for blk in re.findall(r"📌 Takeaway(.*?)(?=\n##\s|\n---)", article, re.DOTALL):
        scan.extend(blk.split("\n"))

    mismatched: list[str] = []
    for line in scan:
        st = line.strip()
        if not st or st.startswith("|") or is_legend_line(st):
            continue
        tag = next((t for t in VALID_TAGS if t in st), None)
        if not tag:
            continue
        for number, meaning, src in anchors:
            if len(number) < 2 or not any(c.isdigit() for c in number):
                continue
            if not num_match(number, st) and number not in st:
                continue
            expected, reason = map_source_to_tag(src, f"{meaning} {st}")
            if looser_than(tag, expected):
                mismatched.append(
                    f"{number}：锚点表口径「{src}」应为 {expected}（{reason}），"
                    f"此处标 {tag} —— {st[:40]}")
            break

    rep.check(not mismatched, "[P0] 压缩位置的符号与来源强度一致",
              f"{len(mismatched)} 处标记被放松 ——\n         "
              + "\n         ".join(mismatched[:10]))


def check_forecast_not_fact(text: str, label: str, rep: Report) -> None:
    """任何指向未来的条目都不得标【实】。"""
    bad: list[str] = []
    soft: list[str] = []
    for line in text.split("\n"):
        if TAG_REAL not in line or is_legend_line(line):
            continue
        tag, reason = map_source_to_tag("", line)
        if tag != TAG_REAL and "前瞻" in reason:
            bad.append(f"{line.strip()[:52]} ← {reason}")
        elif (hit := soft_forecast_hit(line)):
            soft.append(f"{line.strip()[:52]} ← 含「{hit}」")
    rep.check(not bad, f"[P0/{label}] 前瞻表述未标【实】",
              f"{len(bad)} 处 ——\n         " + "\n         ".join(bad[:8]))
    if soft:
        rep.warn(f"[P0/{label}] 弱前瞻词与【实】共现",
                 f"{len(soft)} 处需人工确认 ——\n         " + "\n         ".join(soft[:5]))


def check_self_contradicting(text: str, label: str, rep: Report) -> None:
    scannable = "\n".join(ln for ln in text.split("\n") if not is_legend_line(ln))
    hits = SELF_CONTRADICTING.findall(scannable)
    rep.check(not hits, f"[P0/{label}] 无自相矛盾的可信度写法",
              f"{len(hits)} 处形如「【实】视频口述」——限定词已经说明它不是【实】")


def check_module_level_and_order(text: str, ctype: str, rep: Report) -> None:
    """锚点必须落在正确的标题层级上，且出现顺序与蓝图一致。

    只做 `anchor in text` 是不够的：模块被嵌进上一个模块里当 ### 用时，
    子串匹配照样通过，而模块实际上已经不存在了。
    """
    seen: list[tuple[str, int]] = []
    for sid, anchor, conditional, levels in ARTICLE_ANCHORS:
        if levels is None:  # S4：锚点是正文标记，不是标题
            pos = text.find(anchor)
            if pos >= 0:
                seen.append((sid, pos))
            continue
        m = re.search(rf"^(#{{2,4}})\s*[^\n]*{re.escape(anchor)}[^\n]*$", text, re.M)
        if not m:
            continue
        level = len(m.group(1))
        rep.check(level in levels, f"[{sid}] {anchor} 标题层级正确",
                  f"实际 {'#' * level} 级，蓝图要求 {' 或 '.join('#' * L for L in levels)} 级"
                  f"（层级不对通常意味着模块被嵌进了上一个模块里）")
        seen.append((sid, m.start()))

    order_ids = [sid for sid, _ in seen]
    sorted_ids = [sid for sid, _ in sorted(seen, key=lambda x: x[1])]
    rep.check(order_ids == sorted_ids, "[结构] 模块顺序与蓝图一致",
              f"实际顺序 {' → '.join(sorted_ids)}，蓝图顺序 {' → '.join(order_ids)}")


def check_lead(text: str, rep: Report) -> None:
    """导读必须紧跟主标题，而不是压在文末附录里。

    附录是读完之后才会翻的地方，把"这篇讲什么、为什么值得读"放在那里，等于
    在读者最需要它的时刻不给它。v5.1 起导读前置，且**不带标题**——它是主标题的
    延长线，不是一个模块。
    """
    m = re.search(r"^#\s+\S.*$", text, re.M)
    if not m:
        rep.check(False, "[S0] 可定位主标题", "文件应以 `# 观点化主标题` 开头")
        return
    start = m.end()
    nxt = re.search(r"^##\s", text[start:], re.M)
    lead = strip_code_blocks(text[start : start + nxt.start()] if nxt else text[start:]).strip()
    chars = cn_chars(lead)
    rep.check(40 <= chars <= 260, "[S0] 导读紧跟主标题（40-260 字）",
              f"主标题与第一个 ## 之间实际 {chars} 字"
              f"{'——导读可能还留在文末附录里' if chars == 0 else ''}")
    rep.check(not any(t in lead for t in VALID_TAGS), "[S0] 导读不给结论",
              "导读里出现了可信度标记。结论是 S2 速览的职责；写在导读里还会让 "
              "S1 读前预判失效——读者在猜之前就拿到答案了")


# ── 主文校验 ────────────────────────────────────────────────────────────


def check_article(text: str, ctype: str, rep: Report) -> None:
    body = strip_code_blocks(text)

    # 0. 导读前置
    check_lead(text, rep)

    # 1. 模块存在性
    for sid, anchor, _conditional, _levels in ARTICLE_ANCHORS:
        rep.check(anchor in text, f"[{sid}] {anchor}", f"缺失模块，锚点词「{anchor}」未出现")

    # 1b. 废止模块不得复活
    revived = retired_hits(text)
    rep.check(not revived, "[结构] 无 v4.0 废止模块",
              "出现已砍除的模块：" + "；".join(f"{a}（{why}）" for a, why in revived[:6]))

    # 1c. 层级与顺序
    check_module_level_and_order(text, ctype, rep)

    # 2. 可信度符号白名单 + P0 三项
    for pattern, desc in ILLEGAL_TAG_PATTERNS:
        hits = re.findall(pattern, text)
        rep.check(not hits, f"[符号] 无非法可信度标记（{desc}）",
                  f"发现 {len(hits)} 处 {desc} 写法，只允许 {' '.join(VALID_TAGS)}")
    check_forecast_not_fact(text, "主文", rep)
    check_self_contradicting(text, "主文", rep)
    check_tag_consistency(text, rep)

    # 3. S1 读前预判：3 题、只问不答
    pre = extract_section(text, "读前预判")
    if pre:
        qs = re.findall(r"^(?:\d+\.|[-*])\s*(.+\？|.+\?)\s*$", pre, re.M)
        rep.check(len(qs) >= 3, "[S1] 读前预判 ≥3 题", f"实际 {len(qs)} 题")
        rep.check("我的猜测" in pre, "[S1] 每题留「我的猜测」空行", "缺少留白，读者无处写猜测")
        leaked = [t for t in VALID_TAGS if t in pre]
        rep.check(not leaked, "[S1] 读前预判不给答案",
                  "出现了可信度标记，说明这里已经在给结论——那是 S2 速览的职责")
    else:
        rep.check(False, "[S1] 读前预判可解析", "未能定位读前预判段落")

    # 4. S2 速览：3-5 条，每条带标记
    tldr = extract_section(text, "30 秒速览")
    if tldr:
        # `---` / `***` 是水平线，不是列表项。`[-*]\s*(.+)` 会把它们吃进来，
        # 于是每个模块末尾的分隔线都变成一条"缺标记的速览"。先滤掉。
        tldr_lines = "\n".join(
            ln for ln in tldr.split("\n") if not re.fullmatch(r"\s*([-*_])\1{2,}\s*", ln))
        items = re.findall(r"^(?:\d+\.|[-*])\s+(.+)$", tldr_lines, re.M)
        tagged = [i for i in items if any(t in i for t in VALID_TAGS)]
        rep.check(3 <= len(items) <= 5, "[S2] 速览 3-5 条", f"实际 {len(items)} 条")
        rep.check(len(items) == len(tagged), "[S2] 速览每条带可信度标记",
                  f"{len(items) - len(tagged)} 条缺标记")
    else:
        rep.check(False, "[S2] 速览可解析", "未能定位 30 秒速览段落")

    # 5. S3 全片脉络
    flow = extract_section(text, "全片脉络")
    if flow:
        rep.check("主线" in flow, "[S3] 含一句话主线", "全片脉络缺少主线段")
        rep.check("主干流程" in flow, "[S3] 含主干流程", "缺少章与章之间的推进骨架")
        rep.check("```" in flow, "[S3] 用等宽块承载", "必须用代码块，不得用 Markdown 表格")
        rep.check("★" in flow, "[S3] 标注主干章节", "未用 ★ 区分主干与支线章节")
        rep.check("问│" not in flow and "答│" not in flow, "[S3] 未复活分章四要素",
                  "v4.0 已砍除「问/答/据/结」四要素，与章前设问和 Takeaway 三重重复")
    else:
        rep.check(False, "[S3] 全片脉络可解析", "未能定位全片脉络段落")

    # 6. S4 主体章节
    blocks = re.findall(r"📌 Takeaway(.*?)(?=\n##\s|\n---)", text, re.DOTALL)
    n_chap = len(blocks)
    rep.check(3 <= n_chap <= 8, "[S4] 主体章节 3-8 章", f"检测到 {n_chap} 个 Takeaway 区块")
    untagged = sum(
        1 for block in blocks
        for line in re.findall(r"^[-*]\s*(.+)$", block, re.M)
        if not any(t in line for t in VALID_TAGS))
    rep.check(untagged == 0, "[S4] Takeaway 全部带标记", f"{untagged} 条缺可信度标记")
    rep.check("来源强度" in text, "[S4] 数字锚点表含「来源强度」列", "未找到来源强度列")
    windows = len(re.findall(r"↑\s*回答了章前第", text))
    rep.check(windows >= n_chap, "[S4] 每章至少一组延迟一答",
              f"只找到 {windows} 处「↑ 回答了章前第N问」，{n_chap} 章各需至少 1 处")

    # 7. S5 闭卷自测
    details = re.findall(r"<details", text)
    rep.check(5 <= len(details) <= 8, "[S5] 自测 5-8 题", f"实际 {len(details)} 个折叠块")
    quiz = extract_section(text, "闭卷自测")
    if quiz:
        rep.check(any(t in quiz for t in VALID_TAGS), "[S5] ≥1 题考可信度分层",
                  "自测中未出现可信度符号")
        rep.check("回看" in quiz, "[S5] 答案含回看指路", "未找到「回看」指引")

    # 8. S6 立场与证伪
    stance = extract_section(text, "立场与证伪")
    if stance:
        signals = stance.count("我错了的信号")
        rep.check(signals >= 2, "[S6] ≥2 个立场且各带证伪信号",
                  f"仅 {signals} 处「我错了的信号」")
        rep.check("最强反驳" in stance, "[S6] 立场含最强反驳", "缺少最强反驳行")

        has_track = "跟踪指标" in stance
        if ctype in FINANCIAL_TYPES:
            if rep.check(has_track, "[S6] 含跟踪指标表", f"{ctype} 必须产出跟踪指标表"):
                rows = re.findall(r"^\|", stance, re.M)
                rep.check(len(rows) >= 7, "[S6] 跟踪指标 ≥5 项",
                          f"表格仅 {max(0, len(rows) - 2)} 行数据（表头+分隔行不计）")
                rep.check("在哪看" in stance, "[S6] 跟踪表含「在哪看」列", "缺少具体信源列")
        else:
            rep.check(not has_track, "[S6] 非财经类型不产出跟踪指标表",
                      f"{ctype} 未触发该条件内容，产出了即为漂移", fatal=False)
    else:
        rep.check(False, "[S6] 立场与证伪可解析", "未能定位立场与证伪段落")

    # 9. S7 转述与攻防
    arsenal = extract_section(text, "转述与攻防")
    if arsenal:
        for needle in ("30 秒稿", "3 分钟稿", "追问攻防"):
            rep.check(needle in arsenal, f"[S7] 含{needle}", f"转述与攻防缺少「{needle}」")
        n_qa = len(re.findall(r"^\s*[-*]?\s*Q[：:]", arsenal, re.M))
        rep.check(n_qa >= 3, "[S7] 追问攻防 ≥3 组", f"仅 {n_qa} 组 Q&A")
    else:
        rep.check(False, "[S7] 转述与攻防可解析", "未能定位转述与攻防段落")

    # 10. 附录 A1 元信息（v5.0 起附录只剩这一节）
    for field in ("来源频道", "整理日期", "信息截止", "文本来源", "内容类型"):
        rep.check(field in text, f"[A1] 元信息含「{field}」", f"附录元信息行缺少 {field}")
    rep.check(all(t in text for t in VALID_TAGS), "[A1] 含三符号说明",
              "附录未给出【实】【推】【测】的含义说明")

    # 11. 篇幅（WARN，不阻断）
    chars = cn_chars(text)
    rep.check(ARTICLE_MIN_CHARS <= chars <= ARTICLE_MAX_CHARS,
              f"[篇幅] 主文 {ARTICLE_MIN_CHARS}-{ARTICLE_MAX_CHARS} 字",
              f"实际 {chars} 字", fatal=False)

    # 12. 金融属性额外约束
    if ctype in FINANCIAL_TYPES:
        found = [w for w in INVESTMENT_ADVICE if w in body]
        rep.check(not found, "[金融] 无投资建议措辞", f"出现禁用词：{', '.join(found)}")
        rep.check("非投资建议" in text, "[金融] 含免责声明", "文末缺少「非投资建议」")


# ── 记忆卡组校验 ────────────────────────────────────────────────────────

RETIRED_DECK_KINDS = ("辨析", "速查", "概念", "关系", "纠错", "边界")


def check_deck(path: Path, rep: Report, required: bool) -> int:
    if not path.is_file():
        if required:
            rep.error("[卡组] deck 存在", f"未找到 {path.name}（显式传了 --deck，却不存在）")
        else:
            # v5.1 起卡组是**按需**产物：默认只加工主文，用户要了才做。
            # 没有卡组不算未完成，也不该在这里制造一条假 FAIL。
            rep.ok("[卡组] 本次未生成（按需产物，跳过卡组校验）")
        return 0
    rows = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    data = [r for r in rows if not r.startswith("#")]
    rep.check(len(data) >= DECK_MIN_ROWS, f"[卡组] ≥{DECK_MIN_ROWS} 张", f"实际 {len(data)} 张")
    bad_cols = [r for r in data if len(r.split("\t")) != 3]
    rep.check(not bad_cols, "[卡组] 每行三列（正面/背面/标签）",
              f"{len(bad_cols)} 行列数不对（Anki 导入会错位）")
    tagged = [r for r in data if any(f"::{t}" in r for t in ("实", "推", "测"))]
    rep.check(len(tagged) == len(data), "[卡组] 每张卡带可信度标签",
              f"{len(data) - len(tagged)} 张缺 ::实/::推/::测 标签"
              "（复习时可信度分层也要跟着被复习，否则只在初读时看过一眼）")
    fronts = [r.split("\t")[0] for r in data]
    rep.check(len(fronts) == len(set(fronts)), "[卡组] 正面无重复",
              f"{len(fronts) - len(set(fronts))} 张重复")
    no_q = [f for f in fronts if not any(c in f for c in "？?")]
    rep.check(len(no_q) <= len(fronts) * 0.2, "[卡组] 正面以提问式为主",
              f"{len(no_q)}/{len(fronts)} 张正面不是问句——陈述句切片是识别，不是检索",
              fatal=False)
    fwd = sum(1 for r in data if "::数字::" in r)
    bwd = sum(1 for r in data if "::数字反向::" in r)
    rep.check(fwd == bwd, "[卡组] 数字卡正反成对",
              f"正向 {fwd} 张 / 反向 {bwd} 张——只出正向会产生只认前半句的假记忆")
    retired = sorted({k for k in RETIRED_DECK_KINDS if f"::{k}::" in "\n".join(data)})
    rep.check(not retired, "[卡组] 无已下线卡类",
              f"出现 {', '.join(retired)} 类卡，但它们的来源（卡片包 / 知识网络）已不存在")
    return len(data)


# ── 学习效力评分 ────────────────────────────────────────────────────────


def score_learning(article: str, deck_rows: int, rep: Report) -> None:
    """结构合规之外，度量学习效果本身。全部 WARN 级，不阻断交付。"""
    total = cn_chars(article) or 1

    def sec_chars(anchor: str) -> int:
        blk = extract_section(article, anchor)
        return cn_chars(blk) if blk else 0

    gen = sec_chars("读前预判") + sec_chars("闭卷自测") + sec_chars("立场与证伪")
    gen_ratio = gen / total

    n_quiz = len(re.findall(r"<details", article))
    n_chap = len(re.findall(r"📌 Takeaway", article)) or 1
    density = n_quiz / n_chap

    # 可信度漏损 = 压缩位置里标得比映射更松的条目数；0 = 没有一处被放松
    probe = Report()
    check_tag_consistency(article, probe)
    leak_n = 0
    for e in probe.errors:
        m = re.search(r"(\d+) 处标记被放松", e)
        if m:
            leak_n = int(m.group(1))

    windows = len(re.findall(r"↑\s*回答了章前第", article))

    rep.metric("生成型内容占比", f"{gen_ratio:.1%}", "≥20%", gen_ratio >= 0.20)
    rep.metric("检索题密度（题/章）", f"{density:.2f}", "≥1.0", density >= 1.0)
    rep.metric("可信度漏损（放松个数）", str(leak_n), "=0", leak_n == 0)
    if deck_rows:
        rep.metric("原子记忆卡数", str(deck_rows), f"≥{DECK_MIN_ROWS}", deck_rows >= DECK_MIN_ROWS)
    else:
        rep.metric("原子记忆卡数", "—", "按需生成", True)
    rep.metric("延迟提取窗口", str(windows), f"≥{n_chap}", windows >= n_chap)


# ── 入口 ────────────────────────────────────────────────────────────────


def render(rep: Report, verbose: bool) -> None:
    if verbose:
        for item in rep.passes:
            print(f"  PASS  {item}")
    for item in rep.warns:
        print(f"  WARN  {item}")
    for item in rep.errors:
        print(f"  FAIL  {item}")
    print(f"\n合计: {len(rep.passes)} PASS / {len(rep.warns)} WARN / {len(rep.errors)} FAIL")

    if rep.metrics:
        print("\n学习效力评分（不阻断交付，用于跟踪趋势）")
        print("  " + "─" * 58)
        for name, value, target, good in rep.metrics:
            print(f"  {'✓' if good else '·'} {name:<18} {value:>8}   目标 {target}")
        print("  " + "─" * 58)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 youtube-digest 产出（蓝图 v4.0）")
    parser.add_argument("article", help="主文 .md 路径")
    parser.add_argument("--deck", default=None, help="卡组 .tsv 路径（默认同目录 -deck.tsv）")
    parser.add_argument("--type", dest="ctype", default=None, help="内容类型名（默认从文章提取）")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示 PASS 明细")
    args = parser.parse_args()

    article_path = Path(args.article)
    if not article_path.is_file():
        print(f"错误: 主文不存在 — {article_path}", file=sys.stderr)
        return 2
    try:
        article_text = article_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"错误: 无法读取主文 — {exc}", file=sys.stderr)
        return 2

    # legacy 短路：v4.0 之前的产出已冻结，用 v4 规则重校没有意义。
    # 两条路都算 legacy —— 显式声明了低版本，或没有版本行但命中足够多的废止模块。
    version = declared_version(article_text)
    hits = retired_hits(article_text)
    old_declared = version is not None and version_lt(version, "v4.0")
    if old_declared or (version is None and len(hits) >= LEGACY_THRESHOLD):
        why = (f"声明了蓝图版本 {version}" if old_declared
               else f"无版本行且命中废止模块 {len(hits)} 个: "
                    f"{', '.join(a for a, _ in hits[:4])}…")
        print(f"跳过: {article_path.name}")
        print(f"  该文章为 v4.0 之前的产出（{why}）。")
        print("  老产出不按 v4.0 规则重校；如需迁移，按新蓝图重写并把元信息行改成"
              "「蓝图版本：v4.0」后再跑本脚本。")
        return 0

    ctype = args.ctype or detect_type(article_text)
    if ctype not in CONTENT_TYPES:
        print(f"错误: 无法识别内容类型（得到 {ctype!r}）。合法值: {', '.join(CONTENT_TYPES)}。"
              "请检查附录 A2 或用 --type 指定。", file=sys.stderr)
        return 2

    rep = Report()
    print(f"内容类型: {ctype}　蓝图版本: {version or 'v4.0（未声明，按新版校验）'}")
    conditional = "S6 跟踪指标表" if ctype in FINANCIAL_TYPES else "无"
    print(f"条件内容: {conditional}\n")

    check_article(article_text, ctype, rep)
    deck_path = Path(args.deck) if args.deck else article_path.with_name(
        f"{article_path.stem}-deck.tsv")
    deck_rows = check_deck(deck_path, rep, required=bool(args.deck))
    score_learning(article_text, deck_rows, rep)

    render(rep, args.verbose)

    if rep.errors:
        print("\n结论: 未通过。修复全部 FAIL 项后重跑，不得跳过校验交付。")
        return 1
    print("\n结论: 通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
