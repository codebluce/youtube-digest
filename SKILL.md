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
# ffmpeg is also required for audio download/normalization: install to PATH or use D:/tools/ffmpeg/bin on this Windows workstation
```

Local ASR model cache policy: store faster-whisper models outside the skill repo, default `D:/models/huggingface` on this Windows workstation. Set `HF_HOME`, `HF_HUB_CACHE`, and `TRANSFORMERS_CACHE` before ASR so models do not occupy C drive.

## Transcript Strategy

1. **YouTube captions first** — `fetch_transcript.py` tries YouTubeTranscriptApi with preferred languages.
2. **ASR fallback** — when captions are disabled/unavailable and the user approves audio processing, download audio with yt-dlp, normalize with ffmpeg, and transcribe locally with faster-whisper.
   - Default local model: `medium`; default language: `zh`; default cache: `D:/models/huggingface`.
   - CPU-only Windows workstation: medium model may take tens of minutes for a 30 min video.
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

## Workflow

**八步，顺序执行，不得跳步。** 步骤 6 是硬门禁，步骤 7 双推是默认动作。

### 1. Fetch transcript

```bash
uv run python3 SKILL_DIR/scripts/fetch_transcript.py "<URL>" --language zh,en --timestamps
```

(No uv on the server: use the venv python from Setup.) Done when: JSON with non-empty `full_text`. The script defaults to `zh,en` and retries without language restriction when needed.

**If captions are unavailable and the user approves ASR fallback**, run:

```bash
# Download audio; add --proxy socks5://127.0.0.1:1080 when needed
uv run python3 -m yt_dlp -f "bestaudio/best" --output "SKILL_DIR/workspace/audio/%(id)s.%(ext)s" "<URL>"

# Optional but recommended: normalize audio when ffmpeg is available
ffmpeg -y -i SKILL_DIR/workspace/audio/<video_id>.webm -ar 16000 -ac 1 -c:a pcm_s16le SKILL_DIR/workspace/audio/<video_id>.wav

HF_HOME=D:/models/huggingface HF_HUB_CACHE=D:/models/huggingface/hub TRANSFORMERS_CACHE=D:/models/huggingface/transformers   uv run python3 SKILL_DIR/scripts/asr_faster_whisper.py SKILL_DIR/workspace/audio/<video_id>.wav --model medium --language zh --output-prefix SKILL_DIR/workspace/transcripts/<video_id>
```

ASR is done when `<video_id>.asr.json`, `<video_id>.full.txt`, and `<video_id>.timestamped.txt` exist. Use the ASR JSON as the transcript archive in step 2. If both captions and ASR fail, stop and report the gap; never fabricate transcript content.

### 2. ARCHIVE the transcript — mandatory, before writing anything

Save the raw transcript JSON to `SKILL_DIR/workspace/transcripts/<video_id>.json` for official captions, or keep `SKILL_DIR/workspace/transcripts/<video_id>.asr.json` for ASR fallback. This is mandatory. **Verify the file is non-empty after writing** — a 0-byte archive has happened before and destroys the ability to re-run.

### 3. Determine content type

Load `references/content-types.md` and run its 4-step decision flow **in order, stopping at the first match**. The type determines which conditional modules are mandatory. Do not choose by feel; do not revisit the decision after writing.

Record the result — it goes into the article's M01 line verbatim.

### 4. Write the article

Load `references/article-blueprint.md` and follow the module lock table exactly: fixed module set, fixed order, exact anchor words, per-module DoD minimums.

- **Default output language is Chinese** regardless of the video's language; keep original English terms in parentheses on first appearance when useful.
- If the transcript exceeds ~50K chars, process in ~40K overlapping chunks and merge before writing.
- Save to `SKILL_DIR/workspace/articles/<video_id>-<slug>.md` when running inside this repo; otherwise `~/youtube-digests/<video_id>-<slug>.md`.

### 5. Write the cards pack

Load `references/cards-spec.md`. Save to `<same_dir>/<video_id>-<slug>-cards.md`.

Hard constraints: no pipe tables (Feishu does not render them), no `<details>` (Feishu exposes the answers), ≤3500 CJK chars. The cards pack must be usable **without** the article open.

### 6. Validate — HARD GATE

```bash
uv run python3 SKILL_DIR/scripts/validate_output.py <article.md> --cards <cards.md>
```

Done when: **exit 0**. On exit 1, fix every FAIL and re-run — do not rationalize, do not deliver partially, do not proceed to step 7. WARN items are advisory but should be reviewed.

The script auto-detects content type from the article's M01 line; use `--type` only when debugging.

### 7. Push to both remotes — DEFAULT, not opt-in

**双推是默认动作，不需要用户开口要求。** 每次产出后自动执行：

```bash
git add workspace/transcripts/<video_id>.json         workspace/transcripts/<video_id>.asr.json         workspace/articles/<video_id>-<slug>.md         workspace/articles/<video_id>-<slug>-cards.md
git commit -m "docs: <video_id> 深度文章 + 卡片包 + 字幕原稿"
git push origin main && git push github main
```

三件套一起推，缺一不可：**字幕原稿 JSON/ASR JSON、主文、卡片包**。

Done when: 两个 remote 都返回成功。验证方式（不要只看 `git push` 的输出，本地 remote-tracking 引用可能是陈旧的）：

```bash
git ls-remote origin main && git ls-remote github main   # 两者应与本地 HEAD 一致
```

只有在用户**明确说不要推**时才跳过。若某个 remote 推送失败（如凭据缺失），如实报告是哪个失败、失败原因，不得笼统说"已推送"。

### 8. Deliver

**If the user asked for Feishu** — send both, cards as message body, article as attachment:

```bash
uv run python3 SKILL_DIR/scripts/send_feishu.py <article.md> --text-file <cards.md>
```

Done when: exit 0 and a message_id is printed. On exit 2 (missing config), report the env var setup and deliver local paths instead — do not fake success.

**Always report back to the user**: article path, cards path, content type + triggered conditional modules, validation result (`63 PASS / 0 FAIL` style), push status per remote (`✅`/`❌` each), Feishu status if attempted, and the 30-second overview pasted inline.

## Common Pitfalls

1. **Datacenter IP blocked by YouTube.** Cloud servers (阿里云/腾讯云/AWS) are frequently blocked: error mentions "blocking requests from your IP". Fixes: set `HTTPS_PROXY` to a residential proxy; or fetch the transcript on an unblocked machine and copy the JSON over. Never substitute a fabricated transcript.
2. **Number conflicts inside the transcript** (e.g. 265亿 vs 290亿). Keep both, annotate their context — do not silently pick one. These pairs are prime material for the cards pack's 讲错风险清单.
3. **Subtitle dumping.** The article must *restructure* (timeline / causality / comparison), not paste paragraphs of raw transcript. If a chapter reads like verbatim subtitles, rewrite it.
4. **Credibility qualifiers eroding in summaries.** The most common real-world drift: the body text says "按 XX 公司的说法…4 倍", but the 速览 / 概念卡片 / 要点清单 drop the qualifier and state it as fact. Those compressed positions are exactly what readers quote. Tag every one of them.
5. **Feishu 99991663/99991672 errors** = wrong receive_id_type or bot not in chat. Verify `FEISHU_RECEIVE_ID_TYPE` matches the ID prefix (`oc_`=chat_id, `ou_`=open_id) and the bot has been added to the group.
6. **Premature completion.** Sending the raw transcript, a flat summary, or the article alone does not count. The deliverable is: article + cards pack + validation exit 0.
7. **Empty transcript archive.** Writing the JSON is not the same as verifying it. Check the byte size.

## Verification Checklist

机器可校验的部分由 `validate_output.py` 覆盖（步骤 6）。以下是**脚本查不到、必须人工确认**的项：

- [ ] 主标题观点化，不是视频原标题的复述
- [ ] 每章正文是重构叙事（时间线/因果/对比），不是字幕搬运
- [ ] 章前设问是读者视角的真问题，不是章标题的同义重复
- [ ] 自测题确实需要串联 ≥2 章才能回答（脚本只能数题目数量，判不了跨章）
- [ ] 数字锚点的「来源强度」标注准确——厂商自述没被写成第三方数据
- [ ] 字幕内的数字冲突已并列保留并标注语境
- [ ] 多空对照两栏证据强度大致相当；若视频本身一边倒，已在 M16 指出
- [ ] 卡片包能脱离主文独立使用，不是"详见第X章"式空壳
- [ ] 转录稿已归档且**非空**

脚本已自动覆盖：模块完整性 / 锚点词 / 可信度符号白名单 / 总账加总 / 速览与 Takeaway 标记率 / 来源强度列 / 自测题数与折叠 / 知识网络关系图 / 弹药库五子模块 / 立场证伪信号 / 条件模块触发正确性 / 篇幅 / 金融免责 / 卡片包飞书兼容性。
