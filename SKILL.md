---
name: youtube-digest
description: "多源视频链接(YouTube/Bilibili/…)转深度知识文章MD，默认中文输出；记忆卡组与复习队列改为按需生成，可选发送飞书。"
version: 5.1.0
author: peizhiwu
license: MIT
metadata:
  hermes:
    tags: [video, youtube, bilibili, transcript, knowledge-article, feishu, digest]
    related_skills: [youtube-content]
---

# Video Digest (multi-source)

## Overview

Pipeline: **视频 URL(任意已注册源) → transcript → 内容分型 → 深度知识文章 + 记忆卡组 → 校验门禁 → 双推远端 → 复习队列 → 可选飞书**.

**v5.1 两处变更**：①蓝图升到 v5.0，又砍掉个人接口、🚧 该承认不知道的边界、讲错风险清单，附录只保留来源频道元信息（内容类型并进元信息行）；②**记忆卡组改为按需生成**——默认每次只加工主文，用户明确要求时才为那个视频补一份卡组。原 v5.0 把正文 17 模块压到 7 个（S1-S7）+ 文末附录 3 项，**卡片包产物取消**（`references/cards-spec.md` 已删除）。理由见 `references/article-blueprint.md` 顶部「v4.0 的由来」：文章内部堆再多重读型模块也不产生长期记忆，产生记忆的是跨天检索——所以砍掉重读模块、把预算移给卡组。**v4.0 之前的老文章不迁移**，validator 自动识别并跳过。

**v3.0 起多源化**：处理逻辑(分型/蓝图/校验)与视频来源**完全解耦**——`references/article-blueprint.md`、`references/content-types.md`、`scripts/validate_output.py` 都不区分源头。新增一个视频源只需在 `scripts/sources/` 加一个文件,见 `scripts/sources/_template.py`。

当前已注册源:**YouTube**、**Bilibili**。源清单由 `scripts/sources/` 目录扫描决定,顶层 `fetch_transcript.py` 自动识别 URL 并路由到对应 adapter,字幕不可用时统一抛出 `captions_unavailable` 错误码,调用方据此进入 ASR fallback(与源头无关,统一走 yt-dlp + faster-whisper)。

The core value is not transcription — it is the article architecture defined in `references/article-blueprint.md`. The article is designed around how readers absorb, retain, and re-tell knowledge: structure-first navigation, chunked chapters, credibility tagging so the reader knows what is fact vs. the host's inference, closed-book self-testing (retrieval practice), and a talking-points arsenal with rebuttal preparation.

**This skill produces ONE file per video by default**（v5.1 起）:

```
主文      默认产出   叙事、因果、论证、可审计的来源强度、转述与攻防
记忆卡组  按需产出   Anki TSV；只有用户明确要求时才为那个视频生成
```

默认交付主文即算完成。**不要主动生成卡组、不要主动入复习队列**——用户说"给这个视频做套卡"之类的明确指令时，再回来跑步骤 5.5 与步骤 6。

> **为什么卡片包被取消。** 按原 cards-spec 第 5 章的内容分配表，卡片包 80% 是主文的
> 「原样复制」或「轻压缩」——它不是第二个产物，是主文的一个导出视图。手写两份的
> 唯一后果是漂移（原规格为此加了「必须逐字一致」的约束，这本身就是设计有问题的信号）。
> 它承担的"反复翻"职责由卡组接管，而卡组是跨天的、可考的、机器生成的。
>
> **为什么卡组是必需的。** 整条 pipeline 终止于「校验通过 + 双推完成」——遗忘曲线
> 在那一刻才刚开始。卡组 + `workspace/review-queue.md` 把产出从**一次性文档**变成
> **一条跨天的时间线**。完整分析见 `workspace/2026-08-20-学习效果诊断与优化方案.md`。

### 漂移控制（重要）

不同 LLM agent 执行本 skill 必须产出**结构一致**的文件。为此：

- `references/article-blueprint.md`（**v5.0**）是**契约**，锁定 7 个正文模块 + 1 项附录的集合、顺序、标题锚点词和每模块最小满足量；
- `references/content-types.md`（**v4.0**）用**机械判定流程**决定唯一一处条件内容（S6 跟踪指标表）是否必选，不靠 agent 自由裁量；
- `references/deck-spec.md`（**v3.0**）锁定卡组的三类卡与双向约束（仅在按需生成卡组时加载）；
- `scripts/credibility.py` 是「来源强度 ⇄ 【实/推/测】」的**唯一映射**——符号不由感觉决定；
- `scripts/validate_output.py` 是**强制门禁**——产出后必须跑通且 exit 0。
  自洽性回归：`python3 scripts/_selftest.py`（用最小合规样例验证 validator 的规则彼此不打架）。

**校验未通过 = 未完成。** 不得交付、不得发送飞书、不得向用户宣称完成。

## When to Use

- User pastes **any registered video source URL** and asks for 深度文章 / 知识整理 / 拆解 / 学习笔记 / 转述文案
  - 已注册源: `https://youtube.com/...`, `https://youtu.be/...`, `https://www.bilibili.com/video/BV...`, `https://b23.tv/...`,或裸 video_id(`WTz7LaHuqMw` / `BV1V4Te6MEAu`)
  - 收到未注册源的 URL 时,`fetch_transcript.py` 会以 exit 2 失败并列出已注册源。此时要么人工提供一个新 adapter(`scripts/sources/<new>.py`,见 `_template.py`),要么坦白告诉用户该源暂不支持
- User wants the result delivered to Feishu (飞书)

**收到视频链接后不直接开始转录/写作** — 见下方「入口登记（Intake Gate）」，这是所有触发路径共同的第一道关卡。

**Don't use for:** a quick one-paragraph summary (use `youtube-content` directly for YouTube); sources not yet registered as a source adapter; requests to fabricate content when transcript fetch fails; copyrighted transcript reposting without transformation.

**Boundaries:**
- Never invent missing transcript content, timestamps, numbers, guest names, sponsors, charts, or claims.
- If transcript is incomplete, mark the article as "基于可获取字幕整理" and avoid conclusions that depend on missing segments.
- If the user asks for Feishu delivery but env vars are missing, deliver the local file paths and the explicit setup gap; do not report delivery success.
- Default article language is Chinese. Keep source-language terms only where they improve precision.
- Never label a vendor's own claim, a CEO's forecast, or one party's court allegation as 【实】.

## Setup

```bash
# Dependencies
uv pip install youtube-transcript-api requests yt-dlp faster-whisper PyAV
# PEP 668 systems without uv: python3 -m venv ~/.venvs/yt-digest && ~/.venvs/yt-digest/bin/pip install youtube-transcript-api requests yt-dlp faster-whisper PyAV
# ffmpeg is also required for audio normalization (PyAV can decode webm directly,
# so strictly optional but recommended) — install via the platform's own package
# manager and ensure it's on PATH:
#   macOS:   brew install ffmpeg
#   Linux:   sudo apt install ffmpeg
#   Windows: install ffmpeg and add its bin/ directory to PATH
```

**Env vars** — copy `.env.example` to `.env` and fill in real values. `.env` is gitignored; never commit it. Feishu vars are only needed for step 8; HF_HOME only when running ASR fallback; `BILIBILI_SESSDATA` only when attempting B 站 AI 字幕 (optional).

**Local ASR model cache policy — platform-agnostic, no hardcoded paths.** faster-whisper models must be cached outside the skill repo, in a directory the executing machine chooses for itself:

```bash
# Set once per machine, in the shell profile — never hardcode a path in this SKILL.md,
# and never commit a machine-specific path here. Pick any writable location; the goal
# is just "outside the repo" and, on constrained systems, "off the system/OS drive".
export HF_HOME="$HOME/.cache/huggingface"          # macOS/Linux example
# PowerShell equivalent:  $env:HF_HOME = "D:\models\huggingface"   (any writable drive)
export HF_HUB_CACHE="$HF_HOME/hub"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
```

## Transcript Strategy

1. **官方字幕优先** — `fetch_transcript.py` 自动识别 URL 的源,调用对应 adapter 拉取字幕:
   - YouTube → `youtube-transcript-api`,按 `zh,en` 优先级,失败回落自动选轨
   - Bilibili → B 站 `x/player/v2` API。**多数 B 站视频无人工字幕轨**(UP 主未上传),部分有 AI 字幕(CCM)但需要 SESSDATA cookie 才稳定返回,多数情况下本源会抛 `CaptionsUnavailableError` 触发 ASR fallback
   - 新源 → 由新 adapter 决定;同一接口约束下什么源都行
2. **ASR fallback** — 字幕不可用 (`CaptionsUnavailableError` / exit 3) 且**用户明确同意音频处理**时,统一下载 + 本地转写。这一步与源头**完全无关**:
   - yt-dlp 原生支持所有已注册源(YouTube / Bilibili 都是开箱即用)
   - faster-whisper 默认 `large-v3-turbo` 模型,默认语言 `zh`(弱 CPU 机器可用 `--model medium` 降级)
   - cache 目录取决于 `HF_HOME`(见 Setup,不写死路径)
   - CPU-only 机器上 `large-v3-turbo` 跑 30 分钟视频约需 10-15 分钟(M4 Pro 实测 ~2.7x 实时);`medium` 更慢但跨平台一致
   - 文章附录 A1 元信息标注 `文本来源：本地 ASR 转写`(由 ASR 得到时);不得假装 ASR 是官方字幕

**B 站特殊环境变量(可选)**: `BILIBILI_SESSDATA` — 配置后可尝试拉 AI 字幕;不配也不阻塞,直接走 ASR fallback。

Feishu delivery requires an app (custom bot webhook cannot send files). Set env vars before use:

```bash
export FEISHU_APP_ID="cli_xxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxx"
export FEISHU_RECEIVE_ID="oc_xxxxxxxx"        # chat_id of target group/user chat
export FEISHU_RECEIVE_ID_TYPE="chat_id"       # open_id | user_id | union_id | email | chat_id
```

Minimal app permissions: `im:message`, `im:message:send_as_bot`, `im:file`. The bot must be added to the target chat. See `references/feishu-setup.md`.

`SKILL_DIR` below = the directory containing this SKILL.md.

## Naming Convention

**article 文件命名格式**：`<YYYY-MM-DD>-<中文标题>[.suffix]`

```
日期      取文章附录 A1「整理日期」的值，不是文件系统 mtime。放最前面是为了
          让 ls 按时间自然排序。
中文标题  直接使用文章 H1 主标题，保留中文、空格、标点与关键英文术语。
          禁止在 article 文件名中加入 source、video_id、英文 slug 或代码化标题。

suffix    主文无 suffix；记忆卡组加 -deck 且扩展名为 .tsv。（-cards 已于 v5.0 停用）
```

**示例**：

```
2026-08-02-AI 巨头资本战争：你以为他们在砸钱买公司，其实是在互相抵押命根子.md
2026-08-02-AI 巨头资本战争：你以为他们在砸钱买公司，其实是在互相抵押命根子-deck.tsv

2026-08-02-一场采访如何变成话语权审判：Hasan、LBC 与“能不能类比纳粹”的争论.md
2026-08-02-一场采访如何变成话语权审判：Hasan、LBC 与“能不能类比纳粹”的争论-deck.tsv
```

> **文件名不再含 video_id，卡组标签怎么办？** `build_deck.py` 按
> 「正文 `video_id:` 声明 → `workspace/todolist.md` 已完成表 → 兜底哈希」的顺序解析，
> 保证 Anki 标签仍是稳定的 ASCII 短串（Anki 用空格分隔 tag，中文标题直接当标签会被拆碎）。

**transcript / ASR 归档命名不跟随 article 规则**：为保证机器去重与溯源，transcript 仍使用 `<date>-<source>-<video_id>.json` 或 `<date>-<source>-<video_id>.asr.json/.full.txt/.timestamped.txt`。article 是给人读的产物，用中文标题；transcript 是机器归档，用 source + video_id。

`validate_output.py` 的卡组自动配对基于文件名 stem（去掉 `.md` 后加 `-deck.tsv`），不依赖具体格式，改名不影响校验。仓库里遗留的 `*-cards.md` 是 v5.0 之前的历史产物，**保留不删、不再新增**，审计脚本会跳过它们。

## Intake Gate — 登记优先于执行

**这是入口机制，先于步骤 1，对每一个新收到的视频链接（任意已注册源）都强制生效。**

多个 agent（本地不同会话、不同机器、有/无 ASR 能力）共享同一个仓库。默认假设是：收到链接的这个 agent 不一定是应该马上处理它的那个 agent。因此：

1. **识别源 + 提取 `video_id`**(由 `scripts/sources/` 里的 adapter 完成,如 YouTube 11 字符 / B 站 BV 号),检查 `workspace/todolist.md`「待处理」表和 `workspace/articles/` 是否已有同一 (源, video_id) 的条目/产出——避免重复登记或重复处理。
2. **登记一行到 `workspace/todolist.md`「待处理」表**：添加日期、video_id、URL、用户随口提到的备注（若有），状态写 `待处理`。不要求先探测是否有字幕、不要求抓取标题——登记本身必须是零重活动作，只是记账。
3. **立即提交并推送这一次登记**，让其他机器上的 agent 能看到最新队列。Remote 别名按 URL 现查，不要硬编码（原因见步骤 7 的说明）：
   ```bash
   GH_REMOTE=$(git remote -v | awk '/github\.com/ && /\(push\)/ {print $1; exit}')
   GITEE_REMOTE=$(git remote -v | awk '/gitee\.com/ && /\(push\)/ {print $1; exit}')
   git add workspace/todolist.md
   git commit -m "todo: 登记待处理视频 <video_id>"
   git push "$GH_REMOTE" main && git push "$GITEE_REMOTE" main
   ```
   这是轻量推送，**不需要**跑 `scripts/audit_workspace.py`——那是产出物（文章+卡组）的门禁，不适用于登记表这种纯记账变更。
4. **向用户提问**：「已登记进待办清单。现在就用当前 agent 执行 digest 吗？」

**只有用户明确回答"是/现在做/立刻处理"之类，才继续进入下面的步骤 1。** 用户如果说"先不用""放着就行""等有 ASR 的机器处理"或没有明确肯定，就停在这里——条目留在待处理表，不做任何转录或写作动作。

**例外**：用户在发链接的同一句话里已经给出明确的立即执行指令（例如"加工这个视频""马上处理这个"），可以视为已经完成了确认，跳过"询问"这一步，但**登记这一步永远不跳过**——照样先写入 todolist，再继续，这样待办表和已处理产出能对得上。

处理完成后（跑完下面的完整流程、校验通过、双推完成），把这一行从「待处理」表移到「已完成」表，补上产出路径，同样提交推送。

---

## Review Gate — 每次会话开始时扫一眼（队列非空时才有意义）

`todolist.md` 是**入口队列**（哪些视频还没处理），`review-queue.md` 是**出口队列**
（哪些内容还没复习）。两者共用同一套架构：git 同步的 markdown 队列 + 多机 agent 认领。

> ⚠️ **v5.1 起卡组按需生成，复习队列因此只装"用户要过卡组"的那些视频。**
> 队列为空是正常状态，不是漏做。

**每次会话开始时（在做任何其他事之前）跑一次：**

```bash
uv run python3 SKILL_DIR/scripts/review_due.py
```

- 退出码 1 = 今天没有到期项，静默继续，不要打断用户；
- 退出码 0 = 有到期项，**主动告诉用户**并问要不要现在考。用户说不用就跳过，
  不改队列（下次仍然到期，逾期天数会累积显示）。

**怎么考**：从 `<stem>-deck.tsv` 抽题。上次错题优先。装了 Anki 的话直接让 Anki 排程，
这里只负责提醒。**D+7 的推荐形态**是先听 3 分钟稿（S7）再答 5 张卡——
听是重新激活，答才是检索，比重读 10000 字的依从性高一个数量级。

**考完记账**：

```bash
uv run python3 SKILL_DIR/scripts/review_due.py --done <video_id> [--wrong 3,5]
```

答对进下一档，答错退一档并记下错题号。**错题不是记录，是下一轮的输入。**
记完账和登记一样要提交推送（轻量推送，不跑 audit）。

---

## Workflow

**七步 + 两步按需，顺序执行，不得跳步。** 步骤 5 是硬门禁；步骤 7 双推、步骤 7.5 推 vault 是默认动作；**步骤 5.5 生成卡组与步骤 6 入复习队列只在用户明确要求时才做**。前提：已通过上方的 Intake Gate。

### 1. Fetch transcript

```bash
uv run python3 SKILL_DIR/scripts/fetch_transcript.py "<URL或video_id>" --language zh,en --timestamps \
  --output SKILL_DIR/workspace/transcripts/<date>-<source>-<video_id>.json
```

URL 形态不限:`https://www.youtube.com/watch?v=...`、`https://youtu.be/...`、`https://www.bilibili.com/video/BV...`、`https://b23.tv/...`、或裸 video_id(如 `WTz7LaHuqMw` / `BV1V4Te6MEAu`)。底层根据 URL 自动路由到对应 adapter。

退出码约定:
- `0` 字幕拉取 + 落盘成功(stdout JSON 含 `json` 路径等)
- `2` URL 无法识别为已注册源 → 报告用户该源暂不支持,或参考 `scripts/sources/_template.py` 新写一个 adapter
- `3` 字幕不可用 (`captions_unavailable`) → 进入下方 ASR fallback 分支(经用户确认)
- `4` 源端网络/API 异常 → 报告用户重试或换网络环境
- `5` 落盘文件为空 → 找文件系统/权限问题,见 pitfall #7

**字幕不可用 → ASR fallback**(源无关):

```bash
# 1) 下载音频(yt-dlp 原生支持所有已注册源,加 --proxy socks5://127.0.0.1:1080 走代理)
uv run python3 -m yt_dlp -f "bestaudio/best" --output "SKILL_DIR/workspace/audio/%(id)s.%(ext)s" "<canonical_url>"

# 2) 可选但推荐: ffmpeg 归一化到 16kHz 单声道 WAV(没 ffmpeg 时 PyAV 也能直接读 webm)
ffmpeg -y -i SKILL_DIR/workspace/audio/<video_id>.webm -ar 16000 -ac 1 -c:a pcm_s16le SKILL_DIR/workspace/audio/<video_id>.wav

# 3) faster-whisper 本地转写 (HF_HOME 等 cache 变量由 Setup 段设置,不在此硬编码路径)
uv run python3 SKILL_DIR/scripts/asr_faster_whisper.py SKILL_DIR/workspace/audio/<video_id>.wav \
  --model large-v3-turbo --language zh --output-prefix SKILL_DIR/workspace/transcripts/<date>-<source>-<video_id>
```

(`<video_id>.wav` 在 `workspace/audio/` 是 gitignored 临时文件,无需日期前缀。`--output-prefix` 指向 `workspace/transcripts/` 是正式归档,按 Naming Convention 拼 `<date>-<source>-<video_id>`。)

ASR is done when `<date>-<source>-<video_id>.asr.json`, `<date>-<source>-<video_id>.full.txt`, and `<date>-<source>-<video_id>.timestamped.txt` exist (see Naming Convention above for `<date>`). Use the ASR JSON as the transcript archive in step 2. If both captions and ASR fail, stop and report the gap; never fabricate transcript content.

### 2. ARCHIVE the transcript — mandatory, before writing anything

Save the raw transcript JSON to `SKILL_DIR/workspace/transcripts/<date>-<source>-<video_id>.json` for official captions, or keep `SKILL_DIR/workspace/transcripts/<date>-<source>-<video_id>.asr.json` for ASR fallback. This is mandatory. **Verify the file is non-empty after writing** — a 0-byte archive has happened before and destroys the ability to re-run.

**If ASR fallback was used, clean up `workspace/audio/` now that the transcript is safely archived:**

```bash
rm -f SKILL_DIR/workspace/audio/<video_id>.webm SKILL_DIR/workspace/audio/<video_id>.wav
```

Order matters — only delete **after** confirming the `.asr.json`/`.full.txt`/`.timestamped.txt` archive is non-empty, never before. The audio was always meant to be disposable (see Naming Convention: `workspace/audio/` is gitignored and never committed), but leaving it on disk after the transcript exists just wastes space for no benefit — a 30-minute video's audio is tens of MB, versus a few hundred KB of archived text. Skip this step when the transcript came from official captions directly (no audio was ever downloaded in that path).

### 3. Determine content type

Load `references/content-types.md` and run its 4-step decision flow **in order, stopping at the first match**. v5.0 起分型只决定一件事：S6 的跟踪指标表是否必选。Do not choose by feel; do not revisit the decision after writing.

Record the result — 它写进附录 A1 元信息行的「内容类型」一项，不再单独成节。

### 4. Write the article

Load `references/article-blueprint.md`（**v5.0**）and follow the module lock table exactly: fixed module set, fixed order, exact anchor words, **exact heading level and position**, per-module DoD minimums.

容易漏的几条，逐条对照：

```
□ 导读 2-3 句紧跟主标题，不带标题行     v5.1 起前置；不得给结论，否则读前预判被剧透
□ 附录 A1 元信息行写「蓝图版本：v5.0」  不写会被当成老文章直接跳过校验（等于白做）
□ 元信息行含「内容类型」                 v5.0 起它不再单独成节，写在这一行里
□ S1 读前预判 3 题，只问不答            正文第一个模块，在 30 秒速览之前
□ 每章至少 1 组章前设问不给答案          答案在正文里回收，标「↑ 回答了章前第N问」
□ 数字的可信度符号按映射表查表           不是重新判断
□ 附录 A1 仍然是带「###」标题的模块，不是一段散文
□ 没有把砍掉的模块写回来                 见 blueprint 第 4 章禁止清单
```

- **Default output language is Chinese** regardless of the video's language; keep original English terms in parentheses on first appearance when useful.
- If the transcript exceeds ~50K chars, process in ~40K overlapping chunks and merge before writing.
- Save to `SKILL_DIR/workspace/articles/<date>-<中文标题>.md` when running inside this repo; otherwise `~/youtube-digests/<date>-<中文标题>.md`.

### 5. Validate — HARD GATE

```bash
uv run python3 SKILL_DIR/scripts/validate_output.py <article.md>
```

Done when: **exit 0**. On exit 1, fix every FAIL and re-run — do not rationalize, do not deliver partially, do not proceed to step 6. WARN items are advisory but should be reviewed.

The script auto-detects content type 与 blueprint version from 附录 A1 的元信息行；use `--type` only when debugging. **卡组不存在时不报错**——v5.1 起卡组是按需产物，只有 `<stem>-deck.tsv` 存在（或显式传 `--deck`）时才校验它。声明版本低于 v5.0（或没有版本行但命中 ≥3 个废止模块）的老文章会被自动跳过并 exit 0。

末尾的**学习效力评分**不阻断交付，但它是唯一在度量「学的怎么样」而不是「格式对不对」
的东西。生成型占比长期停在 10% 附近，说明模块写全了但没起作用；这一路的减法就是冲这个数字去的。

### 5.5 Build the memory deck（按需，不默认执行）

**只有用户明确要求为某个视频做卡组时才跑这一步。**

```bash
uv run python3 SKILL_DIR/scripts/build_deck.py <article.md>
uv run python3 SKILL_DIR/scripts/validate_output.py <article.md>   # 有卡组后重跑一次
```

出的是**草稿**，必须人工过一遍再交付（清单见 `references/deck-spec.md` 第 4 章）：删掉查表即可答的、合并语义重复的、把陈述句改成问句、检查数字卡正反成对。**数字卡尤其要按"讲出去会被追问"的重要度重挑**，别照单全收脚本按文档顺序截断的结果。

Done when: `<stem>-deck.tsv` 存在且 ≥20 张，且 validator 仍 exit 0。

### 6. Enqueue for review（跟随卡组，按需）

**只有生成了卡组才做这一步**——没有卡可考，入队等于制造一条永远无法执行的提醒。

把这一条加进 `workspace/review-queue.md`「待复习」表：

```
| <video_id> | <主文文件名> | <今天> | <明天> | 0 | — | 待复习 |
```

首读日 = 今天，下次复习 = D+1。间隔序列 `D+1 → D+3 → D+7 → D+16 → D+35`。
这一步不做，前面所有工作在 7 天后能留下的大约就是 30 秒速览那 5 条。

### 7. Push to both remotes — DEFAULT, not opt-in

**双推是默认动作，不需要用户开口要求。** 推送前先跑一次全仓审计，确保历史产出没有被后续编辑破坏：

```bash
uv run python3 SKILL_DIR/scripts/audit_workspace.py   # 必须 exit 0 才允许推送
```

然后执行：

```bash
git add workspace/transcripts/<date>-<source>-<video_id>.json \
        workspace/articles/<date>-<中文标题>.md
# ASR fallback 的归档文件（存在才加）：
#   workspace/transcripts/<date>-<source>-<video_id>.asr.json
#   workspace/transcripts/<date>-<source>-<video_id>.full.txt
#   workspace/transcripts/<date>-<source>-<video_id>.timestamped.txt
# 只有本次确实生成了卡组时才加这一行：
# git add "workspace/articles/<date>-<中文标题>-deck.tsv" workspace/review-queue.md
git commit -m "docs: <video_id> 深度文章 + 字幕原稿"
```

> ⚠️ **Remote 别名不可硬编码。** `origin` / `gitee` / `github` 这些名字是每台机器本地的 git 配置，不是仓库内容——不同机器的 clone 完全可能给同一个远程仓库起不同的别名。这个坑已经在不同并行会话之间来回踩过好几次：一次写死成 `origin`(GitHub)+`gitee`，下一次"修复"改成 `origin`(Gitee)+`github`，两次都只对某一台机器成立，对另一台都会直接推送失败。**正确做法是每次都按 URL 现查，不要假设任何具体名字：**
>
> ```bash
> GH_REMOTE=$(git remote -v | awk '/github\.com/ && /\(push\)/ {print $1; exit}')
> GITEE_REMOTE=$(git remote -v | awk '/gitee\.com/ && /\(push\)/ {print $1; exit}')
> echo "GitHub remote 别名 = ${GH_REMOTE:-<未配置>} ｜ Gitee remote 别名 = ${GITEE_REMOTE:-<未配置>}"
> ```
>
> 如果两者有一个是空的，说明这台机器缺对应的 remote，需要先 `git remote add` 补上（URL 见仓库现有的另一个 remote，或问用户），不要跳过某个 remote 就继续。

用上面解析出的别名推送：

```bash
git push "$GH_REMOTE" main && git push "$GITEE_REMOTE" main
```

两件套一起推，缺一不可：**字幕原稿 JSON/ASR JSON、主文**。若本次按需生成了卡组，再加上 `-deck.tsv` 与 `review-queue.md`。

Done when: 两个 remote 都返回成功。验证方式（不要只看 `git push` 的输出，本地 remote-tracking 引用可能是陈旧的）：

```bash
git ls-remote "$GH_REMOTE" main && git ls-remote "$GITEE_REMOTE" main   # 两者应与本地 HEAD 一致
```

只有在用户**明确说不要推**时才跳过。若某个 remote 推送失败（如凭据缺失），如实报告是哪个失败、失败原因，不得笼统说"已推送"。

### 7.5 Push to Obsidian vault — DEFAULT, not opt-in

**推送到 Obsidian vault 是默认动作，不需要用户开口要求。** 主文 + 卡组会被拷到 vault 仓库的「深度分析」文件夹，然后双推到 vault 自己的 GitHub / Gitee 两个 remote。

**vault 克隆位置**：`~/Documents/Obsidian01`（本机规范位置；如这台机器克隆在别处，用环境变量 `VAULT_DIR` 覆盖）。首次使用前先克隆并配好双 remote：

```bash
cd ~/Documents
git clone --depth 20 --single-branch --branch main \
    git@github.com:codebluce/Obsidian-Vault.git Obsidian01
cd Obsidian01
git remote rename origin github
git remote add gitee git@gitee.com:ppwupp/obsidian-vault.git
git fetch gitee
```

之后每次产出一篇 digest（已通过步骤 5 校验、步骤 7 双推完成）：

```bash
uv run python3 SKILL_DIR/scripts/push_to_vault.py \
    workspace/articles/<date>-<中文标题>.md
```

脚本做的事：定位 vault（`$VAULT_DIR` 或 `~/Documents/Obsidian01`）→ 建「深度分析」目录（如缺）→ 拷入主文 + 卡组（保留原文件名）→ commit → 按 URL 现查 github/gitee remote 别名 → 分别 push → 用 `git ls-remote` 验证两端 HEAD 与本地一致。

Done when: 脚本 exit 0，最后一行 JSON 打印 `pushed.github.head == pushed.gitee.head`。**Remote 别名规则与步骤 7 相同**——绝不假设 `origin` 在哪边。推送失败（如 vault 克隆缺失、remote 未配、push 被拒）时脚本 exit 非零，如实报告是哪个环节、哪一端失败，不得笼统说"已推送"。

用户明确说不要推 vault 时才跳过本步。

### 8. Deliver

**If the user asked for Feishu** — send the article as an attachment, with the 30 秒速览 as the preceding text message:

```bash
uv run python3 SKILL_DIR/scripts/send_feishu.py <article.md> --text "<把 S2 的 3-5 条粘这里>"
```

`--text` 省略也可以，那样只发附件。

Done when: exit 0 and a message_id is printed. On exit 2 (missing config), report the env var setup and deliver local paths instead — do not fake success.

**Move the `workspace/todolist.md` entry from「待处理」to「已完成」**, filling in the article path, then commit+push that change with the rest (or as a follow-up lightweight push per the Intake Gate pattern).

**Always report back to the user**: article path, deck path + 卡数, content type + triggered conditional content, validation result (`72 PASS / 0 FAIL` style) 与学习效力评分六项, push status per remote (`✅`/`❌` each), Feishu status if attempted, and the 30-second overview pasted inline.

## Common Pitfalls

1. **Datacenter IP blocked (YouTube/B 站共通).** Cloud servers (阿里云/腾讯云/AWS) are frequently blocked by YouTube specifically; B 站风控对数据中心 IP 也明显更严格. Error signature: "blocking requests from your IP" / B 站 `code: -412` / 大量 412/412-like HTTPS. Fixes: set `HTTPS_PROXY` to a residential proxy; or fetch the transcript on an unblocked machine and copy the JSON over. Never substitute a fabricated transcript.
2. **Number conflicts inside the transcript** (e.g. 265亿 vs 290亿). Keep both, annotate their context — do not silently pick one. These pairs are prime material for S5 的自测题与 S7 的追问攻防.
3. **Subtitle dumping.** The article must *restructure* (timeline / causality / comparison), not paste paragraphs of raw transcript. If a chapter reads like verbatim subtitles, rewrite it.
4. **Credibility qualifiers eroding in summaries.** The most common real-world drift: the body text says "按 XX 公司的说法…4 倍", but the 速览 / 概念卡片 / 要点清单 drop the qualifier and state it as fact. Those compressed positions are exactly what readers quote. Tag every one of them.
5. **Feishu 99991663/99991672 errors** = wrong receive_id_type or bot not in chat. Verify `FEISHU_RECEIVE_ID_TYPE` matches the ID prefix (`oc_`=chat_id, `ou_`=open_id) and the bot has been added to the group.
6. **Premature completion.** Sending the raw transcript or a flat summary does not count. The deliverable is: article (7 模块，蓝图 v4.0) + deck.tsv + 入队 + validation exit 0.
7. **Empty transcript archive.** Writing the JSON is not the same as verifying it. Check the byte size.
8. **Hardcoded remote alias names.** `origin`/`gitee`/`github` are per-machine local git config, not repository facts — this has been fixed back and forth incorrectly across parallel sessions on different machines more than once. Always resolve by URL (`git remote -v | grep github.com` / `gitee.com`) per the Naming-free snippet in step 7, never assume a specific alias string.
9. **Skipping the Intake Gate.** Jumping straight to transcript fetch when a video URL (any source) arrives, without first logging it in `workspace/todolist.md` and confirming execution — this defeats the multi-agent handoff the todolist exists for. Registration happens even when the user's message already implies "do it now."
10. **Credibility drift into 压缩位置。** 全仓最严重的一处，独立于第 4 条：主文数字锚点表标注为「UP主口述无源」，而速览 / Takeaway / 转述稿里同一个数字标【实】。实测 8 篇里 7 篇存在，合计 35 个数字。根因是锚点表用 6 值「来源强度」词表、压缩位置用 3 值符号，两套之间没有映射。修法见 `scripts/credibility.py`；validator 现在逐个数字比对。方向上这最要命：**压缩位置正是读者会拿去引用的那些句子，系统里最不准确的那个位置不能是最会被记住的那个。**
11. **把「锚点词存在」当成「结构正确」。** validator 早期只做 `anchor in text` 子串匹配。实测后果：把元信息搬进附录那次重构只完成了一半——8 篇里 5 篇的元信息没真正进附录（有的还留在正文开头，有的只剩纯文本没有标题），**但全部拿到 73 PASS / 0 FAIL「通过」**。现在层级与顺序都会被校验。更一般的教训：**通过校验 ≠ 结构正确 ≠ 内容有效**。
12. **忘了写「蓝图版本：v5.0」。** 不写，且文章又碰巧提到几个废止模块名，validator 会把它当成老文章**直接跳过并 exit 0**——看起来"通过"了，其实一条检查都没跑。新文章必须在附录 A1 元信息行写明版本。
13. **把砍掉的模块写回来。** 最容易复发的是文末自创一段「全文总结」或「要点回顾」——那正是 v4.0 砍掉的重复暴露，validator 会按废止模块拦截。缺的不是总结，是跨天复习。
13. **未经要求就生成卡组。** v5.1 起卡组是按需产物：默认只加工主文，用户没开口就不要跑 build_deck、不要动复习队列。反过来，用户一旦要求做卡组，入队那一行也要一起补上——有卡不入队，等于把 pipeline 停在遗忘曲线的起点。
14. **Leftover audio in `workspace/audio/`.** ASR fallback downloads/normalizes audio there; step 2 includes a cleanup command run right after the transcript archive is verified non-empty. If a run gets interrupted before that cleanup, stray `.webm`/`.wav` files can accumulate silently (gitignored, so they never show up in `git status` — check the directory directly).

## Verification Checklist

机器可校验的部分由 `validate_output.py` 覆盖（步骤 5）。以下是**脚本查不到、必须人工确认**的项：

- [ ] 主标题观点化，不是视频原标题的复述
- [ ] S3 主干流程的节点是**能说出口的判断句**，不是名词短语（脚本只能查结构，判不了句式）
- [ ] S3 主干流程与 S7 三分钟稿讲的顺序一致——两者是同一副骨架的图形态与口语态
- [ ] 每章正文是重构叙事（时间线/因果/对比），不是字幕搬运
- [ ] 章前设问是读者视角的真问题，不是章标题的同义重复
- [ ] 自测题确实需要串联 ≥2 章才能回答（脚本只能数题目数量，判不了跨章）
- [ ] 数字锚点的「来源强度」标注准确——厂商自述没被写成第三方数据
- [ ] 字幕内的数字冲突已并列保留并标注语境
- [ ] S6 两个立场证据强度大致相当；若视频本身一边倒，弱侧已注明是反向推演
- [ ] 每个复杂概念都配了类比并挂到读者已有知识上（概念表已砍，类比是唯一的迁移载体）
- [ ] 转录稿已归档且**非空**
- [ ] 读前预判的 3 题是**读者会答错的具体判断**，不是怎么答都不算错的开放题
- [ ] 读前预判**没有泄漏答案**（给了答案 = 这个模块作废）
- [ ] 每章至少 1 组章前设问确实没给答案，且答案在正文里被标注回收
- [ ] （仅当生成了卡组）卡组里没有「查一下就能答」的题；数字卡正反成对；背面 ≤3 行
- [ ] 导读在主标题正下方，且只说"讲什么/值不值得读"，没有提前给出核心判断
- [ ] 附录里 A1 是带标题的模块，不是一段散文
- [ ] （仅当生成了卡组）已加进 `workspace/review-queue.md`

脚本已自动覆盖（**可机检项**）：导读前置与字数、导读不含可信度标记、7 模块 + 1 附录锚点存在性 / 标题层级与模块顺序 / **废止模块未复活** / 条件内容触发与多判 / 可信度符号白名单 / **来源强度→符号一致性（压缩位置逐个数字比对）** / **前瞻表述不得标【实】** / **自相矛盾写法** / 速览条数与标记率 / Takeaway 标记率 / 来源强度列存在 / **每章延迟一答窗口** / 自测题数与折叠 / 「我错了的信号」与最强反驳计数 / 跟踪表列与行数 / S7 三子模块与追问攻防组数 / 篇幅区间 / 金融免责措辞 / **卡组行数、列数、标签、正反成对、无已下线卡类**。

**注意：脚本大多只查"结构存在"，不判断内容质量**——上面 checklist 中"判断句 vs 名词短语""跨章 vs 单章""重构 vs 搬运""前测题是否真会答错"这类语义项仍需人工确认，validator 通过不等于这些项达标。

**学习效力评分**（validator 末尾输出，WARN 级不阻断）是另一类东西：它不查合规，查效果。

```
生成型内容占比      目标 ≥20%     v2.1 实测稳定在 10-11%
检索题密度          目标 ≥1.0     v2.1 实测 0.75-1.00
可信度漏损          目标 =1.00    v2.1 实测 8 篇里 7 篇漂移
原子记忆卡数        目标 ≥20
自我参照钩子        目标 ≥3
延迟提取窗口        目标 ≥章数
跨篇概念连接        越高越好
```

这七个数写进 git，「我们的报告效果如何」才第一次成为一个**可追踪的时间序列**，
而不是一个只能凭感觉回答的问题。
