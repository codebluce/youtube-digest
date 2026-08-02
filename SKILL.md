---
name: youtube-digest
description: "YouTube链接转深度知识文章MD + 速查卡片包，默认中文输出，可选发送飞书。"
version: 2.0.0
author: peizhiwu
license: MIT
metadata:
  hermes:
    tags: [youtube, transcript, knowledge-article, feishu, digest]
    related_skills: [youtube-content]
---

# YouTube Digest

## Overview

Pipeline: **YouTube URL → transcript → 内容分型 → 深度知识文章 + 速查卡片包 → 校验门禁 → 双推远端 → 可选飞书双发**.

The core value is not transcription — it is the article architecture defined in `references/article-blueprint.md`. The article is designed around how readers absorb, retain, and re-tell knowledge: structure-first navigation, chunked chapters, credibility tagging so the reader knows what is fact vs. the host's inference, closed-book self-testing (retrieval practice), and a talking-points arsenal with rebuttal preparation.

**This skill produces TWO files per video.** The long-form article is read once; the cards pack is what gets re-opened. Delivering only the article is an incomplete run.

### 漂移控制（重要）

不同 LLM agent 执行本 skill 必须产出**结构一致**的文件。为此：

- `references/article-blueprint.md` 是**契约**，锁定了模块集合、顺序、标题锚点词和每模块最小满足量；
- `references/content-types.md` 用**机械判定流程**决定哪些条件模块必选，不靠 agent 自由裁量；
- `references/cards-spec.md` 锁定卡片包的 9 张卡与飞书兼容约束；
- `scripts/validate_output.py` 是**强制门禁**——产出后必须跑通且 exit 0。

**校验未通过 = 未完成。** 不得交付、不得发送飞书、不得向用户宣称完成。

## When to Use

- User pastes a YouTube URL and asks for 深度文章 / 知识整理 / 拆解 / 学习笔记 / 转述文案
- User wants the result delivered to Feishu (飞书)

**收到 YouTube 链接后不直接开始转录/写作** — 见下方「入口登记（Intake Gate）」，这是所有触发路径共同的第一道关卡。

**Don't use for:** a quick one-paragraph summary (use `youtube-content` directly); non-YouTube sources; videos with transcripts disabled; requests to fabricate content when transcript fetch fails; copyrighted transcript reposting without transformation.

**Boundaries:**
- Never invent missing transcript content, timestamps, numbers, guest names, sponsors, charts, or claims.
- If transcript is incomplete, mark the article as "基于可获取字幕整理" and avoid conclusions that depend on missing segments.
- If the user asks for Feishu delivery but env vars are missing, deliver the local file paths and the explicit setup gap; do not report delivery success.
- Default article language is Chinese. Keep source-language terms only where they improve precision.
- Never label a vendor's own claim, a CEO's forecast, or one party's court allegation as 【实】.

## Setup

```bash
# Dependencies
uv pip install youtube-transcript-api requests yt-dlp faster-whisper
# PEP 668 systems without uv: python3 -m venv ~/.venvs/yt-digest && ~/.venvs/yt-digest/bin/pip install youtube-transcript-api requests yt-dlp faster-whisper
# ffmpeg is also required for audio download/normalization — install via the platform's
# own package manager and ensure it's on PATH:
#   macOS:   brew install ffmpeg
#   Linux:   sudo apt install ffmpeg
#   Windows: install ffmpeg and add its bin/ directory to PATH
```

**Env vars** — copy `.env.example` to `.env` and fill in real values. `.env` is gitignored; never commit it. Feishu vars are only needed for step 8; HF_HOME is only needed when running the ASR fallback.

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

1. **YouTube captions first** — `fetch_transcript.py` tries YouTubeTranscriptApi with preferred languages.
2. **ASR fallback** — when captions are disabled/unavailable and the user approves audio processing, download audio with yt-dlp, normalize with ffmpeg, and transcribe locally with faster-whisper.
   - Default local model: `medium`; default language: `zh`; cache directory: whatever `HF_HOME` resolves to on the executing machine (see Setup above — never hardcode a drive letter or path here).
   - CPU-only machine: the `medium` model may take tens of minutes for a 30-minute video, regardless of OS.
   - Mark article metadata as `文本来源：本地 ASR 转写`; do not pretend ASR is official subtitles.

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

**格式**：`<YYYY-MM-DD>-<video_id>-<slug>[.suffix]`

```
日期    取文章 M00「整理日期」的值，不是文件系统 mtime。放最前面是为了
        让 ls 按时间自然排序——video_id 是随机字符串，排序毫无意义。
video_id  保留，用于溯源与去重，但不再是文件名里唯一可读的部分。
slug    纯小写英文 + 连字符，≤5 个单词，描述这篇讲的主题，不是来源标签。
        禁止：中文概念的拼音缩写（如"大摩"写成 damo、"军备"写成 junbei）；
        冗余后缀（如 -digest——本 skill 产出的都是 digest，加了等于没加）。
        人名/公司全名的拼音或英文是允许的（如 sk-hynix、fu-peng），
        问题只在缩写和语义中断，不在"是不是中文来源"。
```

**示例**：

```
2026-07-29-fKoWrF49Qo8-trump-wealth-playbook.md
2026-07-29-fKoWrF49Qo8-trump-wealth-playbook-cards.md
2026-07-29-fKoWrF49Qo8.json                            (transcript)
```

三类产出统一套用此格式：主文、卡片包（加 `-cards` 后缀）、transcript 归档。ASR fallback 产出的 `.asr.json` / `.full.txt` / `.timestamped.txt` 后缀不变，同样加日期前缀。

`validate_output.py` 的卡片自动配对基于文件名 stem（去掉 `.md` 后加 `-cards.md`），不依赖具体格式，改名不影响校验。

## Intake Gate — 登记优先于执行

**这是入口机制，先于步骤 1，对每一个新收到的 YouTube 链接都强制生效。**

多个 agent（本地不同会话、不同机器、有/无 ASR 能力）共享同一个仓库。默认假设是：收到链接的这个 agent 不一定是应该马上处理它的那个 agent。因此：

1. **提取 `video_id`**，检查 `workspace/todolist.md`「待处理」表和 `workspace/articles/` 是否已有同一 `video_id` 的条目/产出——避免重复登记或重复处理。
2. **登记一行到 `workspace/todolist.md`「待处理」表**：添加日期、video_id、URL、用户随口提到的备注（若有），状态写 `待处理`。不要求先探测是否有字幕、不要求抓取标题——登记本身必须是零重活动作，只是记账。
3. **立即提交并推送这一次登记**，让其他机器上的 agent 能看到最新队列。Remote 别名按 URL 现查，不要硬编码（原因见步骤 7 的说明）：
   ```bash
   GH_REMOTE=$(git remote -v | awk '/github\.com/ && /\(push\)/ {print $1; exit}')
   GITEE_REMOTE=$(git remote -v | awk '/gitee\.com/ && /\(push\)/ {print $1; exit}')
   git add workspace/todolist.md
   git commit -m "todo: 登记待处理视频 <video_id>"
   git push "$GH_REMOTE" main && git push "$GITEE_REMOTE" main
   ```
   这是轻量推送，**不需要**跑 `scripts/audit_workspace.py`——那是产出物（文章+卡片包）的门禁，不适用于登记表这种纯记账变更。
4. **向用户提问**：「已登记进待办清单。现在就用当前 agent 执行 digest 吗？」

**只有用户明确回答"是/现在做/立刻处理"之类，才继续进入下面的步骤 1。** 用户如果说"先不用""放着就行""等有 ASR 的机器处理"或没有明确肯定，就停在这里——条目留在待处理表，不做任何转录或写作动作。

**例外**：用户在发链接的同一句话里已经给出明确的立即执行指令（例如"加工这个视频""马上处理这个"），可以视为已经完成了确认，跳过"询问"这一步，但**登记这一步永远不跳过**——照样先写入 todolist，再继续，这样待办表和已处理产出能对得上。

处理完成后（跑完下面的完整流程、校验通过、双推完成），把这一行从「待处理」表移到「已完成」表，补上产出路径，同样提交推送。

---

## Workflow

**八步，顺序执行，不得跳步。** 步骤 6 是硬门禁，步骤 7 双推是默认动作。前提：已通过上方的 Intake Gate。

### 1. Fetch transcript

```bash
uv run python3 SKILL_DIR/scripts/fetch_transcript.py "<URL>" --language zh,en --timestamps \
  --output SKILL_DIR/workspace/transcripts/<date>-<video_id>.json
```

(No uv on the server: use the venv python from Setup.) Done when: JSON with non-empty `full_text`. The script defaults to `zh,en` and retries without language restriction when needed. On failure it prints an error JSON to stdout and exits 1 — it never falls back to ASR by itself.

**If captions are unavailable and the user approves ASR fallback**, run:

```bash
# Download audio; add --proxy socks5://127.0.0.1:1080 when needed
uv run python3 -m yt_dlp -f "bestaudio/best" --output "SKILL_DIR/workspace/audio/%(id)s.%(ext)s" "<URL>"

# Optional but recommended: normalize audio when ffmpeg is available
ffmpeg -y -i SKILL_DIR/workspace/audio/<video_id>.webm -ar 16000 -ac 1 -c:a pcm_s16le SKILL_DIR/workspace/audio/<video_id>.wav

# HF_HOME / HF_HUB_CACHE / TRANSFORMERS_CACHE should already be exported in this
# shell per the Setup section above — do not inline a hardcoded path here.
uv run python3 SKILL_DIR/scripts/asr_faster_whisper.py SKILL_DIR/workspace/audio/<video_id>.wav --model medium --language zh --output-prefix SKILL_DIR/workspace/transcripts/<date>-<video_id>
```

(`<video_id>.wav` under `workspace/audio/` is a gitignored temp file — no date prefix needed there. The `--output-prefix` target under `workspace/transcripts/` is the permanent archive, so it takes the full `<date>-<video_id>` per the Naming Convention above.)

ASR is done when `<date>-<video_id>.asr.json`, `<date>-<video_id>.full.txt`, and `<date>-<video_id>.timestamped.txt` exist (see Naming Convention above for `<date>`). Use the ASR JSON as the transcript archive in step 2. If both captions and ASR fail, stop and report the gap; never fabricate transcript content.

### 2. ARCHIVE the transcript — mandatory, before writing anything

Save the raw transcript JSON to `SKILL_DIR/workspace/transcripts/<date>-<video_id>.json` for official captions, or keep `SKILL_DIR/workspace/transcripts/<date>-<video_id>.asr.json` for ASR fallback. This is mandatory. **Verify the file is non-empty after writing** — a 0-byte archive has happened before and destroys the ability to re-run.

### 3. Determine content type

Load `references/content-types.md` and run its 4-step decision flow **in order, stopping at the first match**. The type determines which conditional modules are mandatory. Do not choose by feel; do not revisit the decision after writing.

Record the result — it goes into the article's M01 line verbatim.

### 4. Write the article

Load `references/article-blueprint.md` and follow the module lock table exactly: fixed module set, fixed order, exact anchor words, per-module DoD minimums.

- **Default output language is Chinese** regardless of the video's language; keep original English terms in parentheses on first appearance when useful.
- If the transcript exceeds ~50K chars, process in ~40K overlapping chunks and merge before writing.
- Save to `SKILL_DIR/workspace/articles/<date>-<video_id>-<slug>.md` when running inside this repo; otherwise `~/youtube-digests/<date>-<video_id>-<slug>.md`.

### 5. Write the cards pack

Load `references/cards-spec.md`. Save to `<same_dir>/<date>-<video_id>-<slug>-cards.md`.

Hard constraints: no pipe tables (Feishu does not render them), no `<details>` (Feishu exposes the answers), ≤3500 CJK chars. The cards pack must be usable **without** the article open.

### 6. Validate — HARD GATE

```bash
uv run python3 SKILL_DIR/scripts/validate_output.py <article.md> --cards <cards.md>
```

Done when: **exit 0**. On exit 1, fix every FAIL and re-run — do not rationalize, do not deliver partially, do not proceed to step 7. WARN items are advisory but should be reviewed.

The script auto-detects content type from the article's M01 line; use `--type` only when debugging.

### 7. Push to both remotes — DEFAULT, not opt-in

**双推是默认动作，不需要用户开口要求。** 推送前先跑一次全仓审计，确保历史产出没有被后续编辑破坏：

```bash
uv run python3 SKILL_DIR/scripts/audit_workspace.py   # 必须 exit 0 才允许推送
```

然后执行：

```bash
git add workspace/transcripts/<date>-<video_id>.json \
        workspace/articles/<date>-<video_id>-<slug>.md \
        workspace/articles/<date>-<video_id>-<slug>-cards.md
# ASR fallback 的归档文件（存在才加）：
#   workspace/transcripts/<date>-<video_id>.asr.json
#   workspace/transcripts/<date>-<video_id>.full.txt
#   workspace/transcripts/<date>-<video_id>.timestamped.txt
git commit -m "docs: <video_id> 深度文章 + 卡片包 + 字幕原稿"
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

三件套一起推，缺一不可：**字幕原稿 JSON/ASR JSON、主文、卡片包**。

Done when: 两个 remote 都返回成功。验证方式（不要只看 `git push` 的输出，本地 remote-tracking 引用可能是陈旧的）：

```bash
git ls-remote "$GH_REMOTE" main && git ls-remote "$GITEE_REMOTE" main   # 两者应与本地 HEAD 一致
```

只有在用户**明确说不要推**时才跳过。若某个 remote 推送失败（如凭据缺失），如实报告是哪个失败、失败原因，不得笼统说"已推送"。

### 8. Deliver

**If the user asked for Feishu** — send both, cards as message body, article as attachment:

```bash
uv run python3 SKILL_DIR/scripts/send_feishu.py <article.md> --text-file <cards.md>
```

Done when: exit 0 and a message_id is printed. On exit 2 (missing config), report the env var setup and deliver local paths instead — do not fake success.

**Move the `workspace/todolist.md` entry from「待处理」to「已完成」**, filling in the article path, then commit+push that change with the rest (or as a follow-up lightweight push per the Intake Gate pattern).

**Always report back to the user**: article path, cards path, content type + triggered conditional modules, validation result (`63 PASS / 0 FAIL` style), push status per remote (`✅`/`❌` each), Feishu status if attempted, and the 30-second overview pasted inline.

## Common Pitfalls

1. **Datacenter IP blocked by YouTube.** Cloud servers (阿里云/腾讯云/AWS) are frequently blocked: error mentions "blocking requests from your IP". Fixes: set `HTTPS_PROXY` to a residential proxy; or fetch the transcript on an unblocked machine and copy the JSON over. Never substitute a fabricated transcript.
2. **Number conflicts inside the transcript** (e.g. 265亿 vs 290亿). Keep both, annotate their context — do not silently pick one. These pairs are prime material for the cards pack's 讲错风险清单.
3. **Subtitle dumping.** The article must *restructure* (timeline / causality / comparison), not paste paragraphs of raw transcript. If a chapter reads like verbatim subtitles, rewrite it.
4. **Credibility qualifiers eroding in summaries.** The most common real-world drift: the body text says "按 XX 公司的说法…4 倍", but the 速览 / 概念卡片 / 要点清单 drop the qualifier and state it as fact. Those compressed positions are exactly what readers quote. Tag every one of them.
5. **Feishu 99991663/99991672 errors** = wrong receive_id_type or bot not in chat. Verify `FEISHU_RECEIVE_ID_TYPE` matches the ID prefix (`oc_`=chat_id, `ou_`=open_id) and the bot has been added to the group.
6. **Premature completion.** Sending the raw transcript, a flat summary, or the article alone does not count. The deliverable is: article + cards pack + validation exit 0.
7. **Empty transcript archive.** Writing the JSON is not the same as verifying it. Check the byte size.
8. **Hardcoded remote alias names.** `origin`/`gitee`/`github` are per-machine local git config, not repository facts — this has been fixed back and forth incorrectly across parallel sessions on different machines more than once. Always resolve by URL (`git remote -v | grep github.com` / `gitee.com`) per the Naming-free snippet in step 7, never assume a specific alias string.
9. **Skipping the Intake Gate.** Jumping straight to transcript fetch when a YouTube URL arrives, without first logging it in `workspace/todolist.md` and confirming execution — this defeats the multi-agent handoff the todolist exists for. Registration happens even when the user's message already implies "do it now."

## Verification Checklist

机器可校验的部分由 `validate_output.py` 覆盖（步骤 6）。以下是**脚本查不到、必须人工确认**的项：

- [ ] 主标题观点化，不是视频原标题的复述
- [ ] 知识地图的节点是**能说出口的判断句**，不是名词短语（脚本只能查结构，判不了句式）
- [ ] 知识地图的主干流程与 M14 三分钟版讲的顺序一致——两者是同一副骨架的图形态与口语态
- [ ] 每章正文是重构叙事（时间线/因果/对比），不是字幕搬运
- [ ] 章前设问是读者视角的真问题，不是章标题的同义重复
- [ ] 自测题确实需要串联 ≥2 章才能回答（脚本只能数题目数量，判不了跨章）
- [ ] 数字锚点的「来源强度」标注准确——厂商自述没被写成第三方数据
- [ ] 字幕内的数字冲突已并列保留并标注语境
- [ ] 多空对照两栏证据强度大致相当；若视频本身一边倒，已在 M16 指出
- [ ] 卡片包能脱离主文独立使用，不是"详见第X章"式空壳
- [ ] 转录稿已归档且**非空**

脚本已自动覆盖（**可机检项**）：模块与锚点词存在性 / 条件模块触发与多判 / M01 附加清单与分型一致 / 可信度符号白名单 / 总账加总 / 速览与 Takeaway 标记率 / 来源强度列存在 / 自测题数与折叠存在 / 知识网络与弹药库子模块存在性 / 证伪信号计数 / 篇幅区间 / 金融免责措辞 / 卡片包飞书兼容性。**注意：脚本大多只查"锚点词存在"，不判断内容质量**——上面 checklist 中"判断句 vs 名词短语""跨章 vs 单章""重构 vs 搬运"这类语义项仍需人工确认，validator 通过不等于这些项达标。
