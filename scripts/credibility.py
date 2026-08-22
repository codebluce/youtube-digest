#!/usr/bin/env python3
"""来源强度 ⇄ 可信度符号的**唯一映射**（blueprint v3.0 §2.02 的可执行版本）。

为什么单独成文件：主文用「来源强度」6 值自由词表，卡片包用【实】【推】【测】3 值符号。
v2.0 里这两套词表之间没有定义映射，于是每生成一次卡片包，agent 都要重做一次主观的
6→3 压缩——而"这个数字视频里明确说了"的直觉会稳定地把它推向【实】。
实测后果（2026-08-02 ai-capex-war）：主文 33 个数字全部标注为「UP主口述无源」，
同一篇卡片包卡 1 的 11 个数字**全部**标成【实】，而卡片包自己定义【实】="可对外说死"。

本文件是 validator 与 build_deck 共用的单一真相源。改映射只改这里。
"""

from __future__ import annotations

import re

TAG_REAL = "【实】"
TAG_INFER = "【推】"
TAG_FORECAST = "【测】"
VALID_TAGS = (TAG_REAL, TAG_INFER, TAG_FORECAST)

# ── 映射表 ──────────────────────────────────────────────────────────────
# 自上而下，第一个命中的规则决定符号。顺序有意义：降级规则排在升级规则前面，
# 这样「视频引用第三方，但属厂商自述」会正确落到【推】。

SOURCE_RULES: list[tuple[tuple[str, ...], str]] = [
    # —— 先扣掉一切"单方说法"，无论它披着什么外衣 ——
    (("厂商自述", "公司自述", "官方口径", "自述口径"), TAG_INFER),
    (("CEO", "高管", "创始人表态", "管理层指引"), TAG_INFER),
    (("庭审单方", "单方爆料", "爆料", "传闻", "小道"), TAG_INFER),
    (("卖方研究", "目标价", "分析师预测"), TAG_INFER),
    # —— UP 主自己说的 / 自己算的 ——
    (("UP主口述", "UP 主口述", "主讲人口述", "口述无源", "无源"), TAG_INFER),
    (("推算", "推断", "估算", "换算"), TAG_INFER),
    # —— 明确标注"没有信源"的，无论前面挂谁的名字 ——
    (("未注明", "无具体信源", "未标信源"), TAG_INFER),
    # —— 二手加工：归纳、转述、解读、类比，都不是原始事实 ——
    (("归纳", "转述", "示意", "对比基准", "解读", "评价",
      "类比", "推演", "历史规律", "测算", "个人经历"), TAG_INFER),
    # —— 讲述者自己承认不确定 ——
    (("含糊", "存疑", "自述"), TAG_INFER),
    # —— UP 主/受访者的复述与叙述：仍然是单一来源 ——
    (("受访者", "嘉宾口述", "视频叙述", "视频技术叙述", "技术叙述", "叙述"), TAG_INFER),
    (("行业口径", "业内口径", "口径"), TAG_INFER),
    # —— 可独立验证的才配得上【实】 ——
    (("公开史实", "公开资料", "已公开", "史实", "公开记录", "行业公开",
      "路线图", "已发生"), TAG_REAL),
    (("公司财报", "财报", "官方公告", "公司公告", "监管文件", "招股书"), TAG_REAL),
    (("视频引用第三方", "第三方机构", "引用第三方", "行业数据库", "视频引用"), TAG_REAL),
]

# 覆盖规则：任何指向未来的表述一律【测】，压过上面所有规则。
# 「公司财报里写的 2027 年产能目标」也是【测】——财报保证的是过去，不是目标。
FORECAST_WORDS: tuple[str, ...] = (
    "预计", "预期", "预测", "有望", "展望", "指引",
    "将达", "将超", "拟建", "目标产量", "远期", "规划性质",
)
# 弱信号：提示但不判死。「计划」「规划」常用于描述一个已存在的计划本身。
FORECAST_SOFT: tuple[str, ...] = ("计划", "规划", "未来", "目标")

# 卡片包里自相矛盾的写法：符号说【实】，紧跟的限定词却说明它不是。
SELF_CONTRADICTING = re.compile(
    r"【实】\s*(?:视频)?(?:口述|转述|据称|称|自述|推算|推断|估算|无源|预计|预期)"
)


# 「公开」类兜底：写法千变万化（公开市场数据 / 公司年报 / 官方披露报告 / 厂商公开
# 许可证条款 / 公开长文…），逐个枚举追不上。规则改为：只要声称公开可查，且没有被
# 上面的降级规则拦下，就给【实】。降级规则先跑，所以「UP主转述的公开报道」仍是【推】。
PUBLIC_HINTS = ("公开", "官方披露", "公司披露", "年报", "许可证条款", "判决", "裁定")


# 「预期」既可以是对未来的判断（"预期产量"），也可以是经济学名词（"收入预期"、
# "通胀预期"）。后者是被研究的变量本身，不是前瞻表述，命中即豁免。
FORECAST_EXEMPT = (
    "收入预期", "通胀预期", "预期管理", "预期差", "理性预期",
    "预期收益率", "市场预期值", "预期寿命",
)


def map_source_to_tag(source: str, meaning: str = "") -> tuple[str, str]:
    """来源强度 + 含义 → (可信度符号, 命中的理由)。

    meaning 参与判定，因为时态藏在含义里而不在来源里：
    「谷歌 TPU 2026 **预计**产量 / UP主口述无源」的来源是口述，但它首先是个预测。
    """
    text = f"{source} {meaning}"
    scan = text
    for term in FORECAST_EXEMPT:
        scan = scan.replace(term, "")
    for word in FORECAST_WORDS:
        if word in scan:
            return TAG_FORECAST, f"含前瞻表述「{word}」"
    for keys, tag in SOURCE_RULES:
        for key in keys:
            if key in source:
                return tag, f"来源强度含「{key}」"
    for hint in PUBLIC_HINTS:
        if hint in source:
            return TAG_REAL, f"来源强度含「{hint}」（声称公开可查，且未被任何降级规则拦下）"
    # 兜底：来源写法不在词表里 —— 按蓝图「拿不准一律降级」原则给【推】
    return TAG_INFER, "来源强度未匹配已知词表，按降级原则处理"


def soft_forecast_hit(text: str) -> str | None:
    """返回命中的弱前瞻词，用于 WARN 级提示。"""
    for word in FORECAST_SOFT:
        if word in text:
            return word
    return None


# ── 数字归一化 ──────────────────────────────────────────────────────────
# 主文写「130 亿美元」，卡片写「130亿美元」；主文「超过 1 万亿美元」，卡片「1万亿美元+」。
# 跨文件比对必须先抹平这些差异，否则一致性检查会全线漏报。

_STRIP = ("+", "＋", "约", "超过", "近", "逾", "达", "以上", "左右", "多", "余")


def norm_num(raw: str) -> str:
    s = re.sub(r"\s+", "", raw.strip())
    for token in _STRIP:
        s = s.replace(token, "")
    return s


def num_match(a: str, b: str) -> bool:
    """两个归一化后的数字串是否指同一个数。"""
    na, nb = norm_num(a), norm_num(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # 允许单位省略：「300万颗」vs「300万」
    return (na in nb or nb in na) and min(len(na), len(nb)) >= 3


# ── 谨慎度序 ────────────────────────────────────────────────────────────
# 【实】最松（可对外说死），【测】最紧（只能作观点）。
# 蓝图原则「拿不准一律降级」意味着：卡片比映射更保守是允许的，更松不允许。

CAUTION: dict[str, int] = {TAG_REAL: 2, TAG_INFER: 1, TAG_FORECAST: 0}


def looser_than(card_tag: str, mapped_tag: str) -> bool:
    """卡片标记是否比映射结果更松（=违规）。"""
    return CAUTION.get(card_tag, 2) > CAUTION.get(mapped_tag, 2)


def is_legend_line(line: str) -> bool:
    """符号说明行会同时出现两个以上标记，不是论断，不参与可信度检查。"""
    return sum(1 for t in VALID_TAGS if t in line) >= 2
