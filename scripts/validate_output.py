#!/usr/bin/env python3
"""校验 youtube-digest 产出是否符合 article-blueprint v2.0 / cards-spec v1.0。

这是**漂移控制的强制门禁**：不同 LLM agent 执行同一 skill 时，文字规范会被各自
解读，机械校验不会。产出后必须通过本脚本且 exit 0 才算完成。

用法:
    python3 validate_output.py <article.md> [--cards <cards.md>] [--type <类型名>]

    --type 省略时，从文章 M01 行（**内容类型**：`xxx`）自动提取。
    --cards 省略时，自动尝试同目录下的 <article_stem>-cards.md。

退出码:
    0  全部 ERROR 项通过（WARN 不阻断）
    1  存在 ERROR 项
    2  参数或文件错误
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

# ── 常量 ────────────────────────────────────────────────────────────────

# 合法的可信度符号（白名单，其余一律视为漂移）
VALID_TAGS = ("【实】", "【推】", "【测】")

# 常见的非法替代写法，用于给出精确的纠正提示
ILLEGAL_TAG_PATTERNS = [
    (r"\[实\]|\[推\]|\[测\]", "半角方括号"),
    (r"【事实】|【推断】|【预测】", "扩写词"),
    (r"【F】|【I】|【P】", "英文缩写"),
    (r"✅\s*事实|❓\s*推断", "emoji 替代"),
]

# 主文模块锚点词 → (模块ID, 是否条件模块)
ARTICLE_ANCHORS: list[tuple[str, str, bool]] = [
    ("M00", "来源频道", False),
    ("M01", "内容类型", False),
    ("M02", "可信度总账", False),
    ("M03", "失效条件", True),
    ("M04", "怎么读这篇", False),
    ("M05", "30 秒速览", False),
    ("M06", "知识地图", False),
    ("M07", "📌 Takeaway", False),
    ("M08", "知识网络", False),
    ("M09", "系统性回顾", False),
    ("M10", "闭卷自测", False),
    ("M11", "多空对照", True),
    ("M12", "立场脚手架", False),
    ("M13", "跟踪清单", True),
    ("M14", "转述弹药库", False),
    ("M15", "延伸思考", False),
    ("M16", "立场与利益相关", True),
]

# 内容类型 → 触发的条件模块（与 content-types.md 第 2 章一致）
TYPE_TRIGGERS: dict[str, set[str]] = {
    "知识科普型": set(),
    "公司行业研究型": {"M03", "M11", "M13", "M16"},
    "宏观策略型": {"M03", "M11", "M13", "M16"},
    "事件复盘型": {"M16"},
}

# 金融属性类型：适用额外硬约束
FINANCIAL_TYPES = {"公司行业研究型", "宏观策略型"}

# 卡片包锚点词 → (卡号, 是否条件卡)
CARD_ANCHORS: list[tuple[str, str, bool]] = [
    ("头部", "一句话定位", False),
    ("卡1", "必记数字", False),
    ("卡2", "概念速查", False),
    ("卡3", "30 秒讲稿", False),
    ("卡4", "场景变体", False),
    ("卡5", "追问攻防", False),
    ("卡6", "讲错风险", False),
    ("卡7", "自测", False),
    ("卡8", "立场", False),
    ("卡9", "跟踪表", True),
]

ARTICLE_MIN_CHARS = 8000
ARTICLE_MAX_CHARS = 16000
CARDS_MAX_CHARS = 3500

# 禁止出现的投资建议措辞（金融属性类型）
INVESTMENT_ADVICE = ["建议买入", "建议卖出", "建议加仓", "建议减仓", "目标价"]


# ── 结果收集 ────────────────────────────────────────────────────────────


class Report:
    """收集校验结果。ERROR 阻断交付，WARN 仅提示。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []
        self.passes: list[str] = []

    def error(self, item: str, detail: str) -> None:
        self.errors.append(f"{item} — {detail}")

    def warn(self, item: str, detail: str) -> None:
        self.warns.append(f"{item} — {detail}")

    def ok(self, item: str) -> None:
        self.passes.append(item)

    def check(self, cond: bool, item: str, detail: str, fatal: bool = True) -> bool:
        """条件为真则记 PASS，否则记 ERROR/WARN。返回条件本身便于串联。"""
        if cond:
            self.ok(item)
        elif fatal:
            self.error(item, detail)
        else:
            self.warn(item, detail)
        return cond


# ── 工具函数 ────────────────────────────────────────────────────────────


def cn_chars(text: str) -> int:
    """统计中文字符数（不含标点与英文）。"""
    return len(re.findall(r"[一-鿿]", text))


def strip_code_blocks(text: str) -> str:
    """移除围栏代码块，避免示例内容干扰正文检查。"""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def extract_section(text: str, anchor: str) -> str | None:
    """提取标题行含 anchor 的模块正文。

    两个必须处理的边界：
    1. 必须锚定到标题行（## / ### / ####），否则会误匹配「怎么读这篇」导航块中
       提及的同名模块——那里只是索引，不含模块内容。
    2. 只在同级或更高级标题处截断，否则 `## 转述弹药库` 会被其下的
       `### 17.1 三档主稿` 提前切断，丢掉全部子模块内容。
    """
    match = re.search(rf"^(#{{2,4}})\s*[^\n]*{anchor}[^\n]*\n", text, re.M)
    if not match:
        return None
    level = len(match.group(1))
    start = match.end()
    tail = re.search(rf"^#{{1,{level}}}\s", text[start:], re.M)
    return text[start : start + tail.start()] if tail else text[start:]


def detect_type(text: str) -> str | None:
    """从 M01 行提取内容类型名，容忍空格与斜杠写法。"""
    match = re.search(r"内容类型\*{0,2}[：:]\s*`?([^`\n—]+)`?", text)
    if not match:
        return None
    raw = match.group(1)
    # 归一化："公司 / 行业研究型" → "公司行业研究型"
    normalized = re.sub(r"[\s/、]", "", raw)
    for known in TYPE_TRIGGERS:
        if known in normalized or normalized in known:
            return known
    return None


# ── 主文校验 ────────────────────────────────────────────────────────────


def check_article(text: str, ctype: str, rep: Report) -> None:
    body = strip_code_blocks(text)
    expected = TYPE_TRIGGERS[ctype]

    # 1. 模块存在性（必选 + 条件触发）
    for mid, anchor, conditional in ARTICLE_ANCHORS:
        present = anchor in text
        if conditional and mid not in expected:
            rep.check(
                not present,
                f"[{mid}] {anchor} 不应出现",
                f"{ctype} 未触发该条件模块，产出了即为漂移",
                fatal=False,
            )
            continue
        rep.check(present, f"[{mid}] {anchor}", f"缺失必选模块，锚点词「{anchor}」未出现")

    # 2. 可信度符号白名单
    for pattern, desc in ILLEGAL_TAG_PATTERNS:
        hits = re.findall(pattern, text)
        rep.check(
            not hits,
            f"[符号] 无非法可信度标记（{desc}）",
            f"发现 {len(hits)} 处 {desc} 写法，只允许 {' '.join(VALID_TAGS)}",
        )

    # 3. 可信度总账一致性
    ledger = re.search(
        r"(\d+)\s*条核心论断.*?【实】\s*(\d+).*?【推】\s*(\d+).*?【测】\s*(\d+)", text, re.DOTALL
    )
    if ledger:
        total, real, infer, pred = (int(g) for g in ledger.groups())
        rep.check(
            total == real + infer + pred,
            "[M02] 总账加总一致",
            f"总数 {total} ≠ {real}+{infer}+{pred}={real + infer + pred}",
        )
    else:
        rep.check(False, "[M02] 总账格式", "未找到「N 条核心论断 — 【实】a / 【推】b / 【测】c」")

    # 4. 30 秒速览每条带标记
    tldr_block = extract_section(text, r"30\s*秒速览")
    if tldr_block:
        items = re.findall(r"^\d+\.\s*(.+)$", tldr_block, re.M)
        tagged = [i for i in items if any(t in i for t in VALID_TAGS)]
        rep.check(3 <= len(items) <= 5, "[M05] 速览 3-5 条", f"实际 {len(items)} 条")
        rep.check(
            len(items) == len(tagged),
            "[M05] 速览每条带可信度标记",
            f"{len(items) - len(tagged)} 条缺标记",
        )
    else:
        rep.check(False, "[M05] 速览可解析", "未能定位 30 秒速览段落")

    # 5. Takeaway 数量与标记
    takeaway_blocks = re.findall(r"📌 Takeaway(.*?)(?=\n##\s|\n---)", text, re.DOTALL)
    rep.check(
        3 <= len(takeaway_blocks) <= 10,
        "[M07] 主体章节 3-10 章",
        f"检测到 {len(takeaway_blocks)} 个 Takeaway 区块",
    )
    untagged = 0
    for block in takeaway_blocks:
        for line in re.findall(r"^[-*]\s*(.+)$", block, re.M):
            if not any(t in line for t in VALID_TAGS):
                untagged += 1
    rep.check(untagged == 0, "[M07] Takeaway 全部带标记", f"{untagged} 条缺可信度标记")

    # 6. 数字锚点表含来源强度列
    rep.check("来源强度" in text, "[M07] 数字锚点表含「来源强度」列", "未找到来源强度列")

    # 7. 闭卷自测
    details = re.findall(r"<details", text)
    rep.check(5 <= len(details) <= 8, "[M10] 自测 5-8 题", f"实际 {len(details)} 个折叠块")
    quiz_block = extract_section(text, "闭卷自测")
    if quiz_block:
        has_credibility_q = any(t in quiz_block for t in VALID_TAGS)
        rep.check(has_credibility_q, "[M10] ≥1 题考可信度分层", "自测中未出现可信度符号")
        rep.check("回看" in quiz_block, "[M10] 答案含回看指路", "未找到「回看」指引")

    # 8. 知识网络
    net_block = extract_section(text, "知识网络")
    if net_block:
        rep.check("迁移锚点" in net_block, "[M08] 含迁移锚点列", "知识网络缺少迁移锚点列")
        rep.check("```" in net_block, "[M08] 含 ASCII 关系图", "知识网络下方缺少关系图")

    # 9. 转述弹药库五个子模块
    block = extract_section(text, "转述弹药库")
    if block:
        for label, needle in [
            ("30 秒版", "30 秒版"),
            ("3 分钟版", "3 分钟版"),
            ("10 分钟版", "10 分钟版"),
            ("场景变体", "场景变体"),
            ("追问攻防", "追问攻防"),
            ("讲错风险", "讲错风险"),
            ("金句", "金句"),
        ]:
            rep.check(needle in block, f"[M14] 含{label}", f"转述弹药库缺少「{needle}」")
        rep.check("🚧" in block, "[M14] 攻防含「该承认不知道的边界」", "未找到 🚧 边界区块")

    # 10. 立场脚手架
    stance_block = extract_section(text, "立场脚手架")
    if stance_block:
        signals = stance_block.count("我错了的信号")
        rep.check(signals >= 2, "[M12] ≥2 个立场且各带证伪信号", f"仅 {signals} 处「我错了的信号」")

    # 11. 条件模块内部规格
    if "M11" in expected:
        bb_block = extract_section(text, "多空对照")
        if bb_block:
            rep.check("证伪信号" in bb_block, "[M11] 多空对照含证伪信号", "缺少证伪信号行")
    if "M13" in expected:
        track_block = extract_section(text, "跟踪清单")
        if track_block:
            rows = re.findall(r"^\|", track_block, re.M)
            # 表格行数 = 表头 + 分隔行 + 数据行，故数据行需 ≥5 → 总行数 ≥7
            rep.check(len(rows) >= 7, "[M13] 跟踪清单 ≥5 指标", f"表格仅 {max(0, len(rows) - 2)} 行数据")
    if "M16" in expected:
        bias_block = extract_section(text, "立场与利益相关")
        if bias_block:
            rep.check("利益披露" in bias_block, "[M16] 含利益披露", "缺少利益披露项")

    # 12. 篇幅
    chars = cn_chars(text)
    rep.check(
        ARTICLE_MIN_CHARS <= chars <= ARTICLE_MAX_CHARS,
        f"[篇幅] 主文 {ARTICLE_MIN_CHARS}-{ARTICLE_MAX_CHARS} 字",
        f"实际 {chars} 字",
        fatal=False,
    )

    # 13. 金融属性额外约束
    if ctype in FINANCIAL_TYPES:
        found = [w for w in INVESTMENT_ADVICE if w in body]
        rep.check(not found, "[金融] 无投资建议措辞", f"出现禁用词：{', '.join(found)}")
        rep.check("非投资建议" in text, "[金融] 含免责声明", "文末缺少「非投资建议」")
        rep.check("信息截止" in text, "[金融] 元信息含信息截止日", "未标注信息截止日")


# ── 卡片包校验 ──────────────────────────────────────────────────────────


def check_cards(text: str, ctype: str, rep: Report) -> None:
    expected = TYPE_TRIGGERS[ctype]

    for cid, anchor, conditional in CARD_ANCHORS:
        present = anchor in text
        if conditional and "M13" not in expected:
            rep.check(
                not present,
                f"[卡片/{cid}] {anchor} 不应出现",
                f"{ctype} 未触发跟踪类模块",
                fatal=False,
            )
            continue
        rep.check(present, f"[卡片/{cid}] {anchor}", f"缺失卡片，锚点词「{anchor}」未出现")

    pipe_rows = re.findall(r"^\|", text, re.M)
    rep.check(not pipe_rows, "[卡片] 无竖线表格（飞书兼容）", f"发现 {len(pipe_rows)} 行竖线表格")

    rep.check("<details" not in text, "[卡片] 无 details 折叠", "飞书正文不渲染折叠，答案会暴露")
    rep.check("答 案 区" in text or "答案区" in text, "[卡片] 自测含答案区分隔", "未找到答案区分隔线")

    chars = cn_chars(text)
    rep.check(chars <= CARDS_MAX_CHARS, f"[卡片] ≤{CARDS_MAX_CHARS} 字", f"实际 {chars} 字")

    stance_signals = text.count("我错了的信号")
    rep.check(stance_signals >= 2, "[卡片/卡8] 立场保留证伪信号", f"仅 {stance_signals} 处")


# ── 入口 ────────────────────────────────────────────────────────────────


def render(rep: Report, verbose: bool) -> None:
    if verbose:
        for item in rep.passes:
            print(f"  PASS  {item}")
    for item in rep.warns:
        print(f"  WARN  {item}")
    for item in rep.errors:
        print(f"  FAIL  {item}")
    print(
        f"\n合计: {len(rep.passes)} PASS / {len(rep.warns)} WARN / {len(rep.errors)} FAIL"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 youtube-digest 产出合规性")
    parser.add_argument("article", help="主文 .md 路径")
    parser.add_argument("--cards", default=None, help="卡片包 .md 路径（默认同目录 -cards.md）")
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

    ctype = args.ctype or detect_type(article_text)
    if ctype not in TYPE_TRIGGERS:
        print(
            f"错误: 无法识别内容类型（得到 {ctype!r}）。"
            f"合法值: {', '.join(TYPE_TRIGGERS)}。"
            "请检查文章 M01 行或用 --type 指定。",
            file=sys.stderr,
        )
        return 2

    cards_path = Path(args.cards) if args.cards else article_path.with_name(
        f"{article_path.stem}-cards.md"
    )

    rep = Report()
    print(f"内容类型: {ctype}")
    print(f"条件模块: {', '.join(sorted(TYPE_TRIGGERS[ctype])) or '无'}\n")

    check_article(article_text, ctype, rep)

    if cards_path.is_file():
        check_cards(cards_path.read_text(encoding="utf-8"), ctype, rep)
    else:
        rep.error("[卡片] 卡片包存在", f"未找到 {cards_path.name}，双产物缺一即未完成")

    render(rep, args.verbose)

    if rep.errors:
        print("\n结论: 未通过。修复全部 FAIL 项后重跑，不得跳过校验交付。")
        return 1
    print("\n结论: 通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
