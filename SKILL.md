---
name: youtube-digest
description: "YouTube链接转深度知识文章MD，默认中文输出，可选发送飞书。"
version: 1.2.0
author: peizhiwu
license: MIT
metadata:
  hermes:
    tags: [youtube, transcript, knowledge-article, feishu, digest]
    related_skills: [youtube-content]
---

# YouTube Digest

## Overview

Pipeline: **YouTube URL → transcript → 中文深度知识文章 (.md) → 可选飞书发送**.

The core value is not transcription — it is the article architecture defined in `references/article-blueprint.md`. The article is designed around how readers absorb, retain, and re-tell knowledge: structure-first navigation, chunked chapters each closed with takeaways (retrieval practice), a final systematic review (spaced repetition), and a "talking-points arsenal" so the reader can re-tell the content to others (Feynman principle).

## When to Use

- User pastes a YouTube URL and asks for 深度文章 / 知识整理 / 拆解 / 学习笔记 / 转述文案
- User wants the result delivered to Feishu (飞书)

**Don't use for:** a quick one-paragraph summary (use `youtube-content` directly); non-YouTube sources; videos with transcripts disabled; requests to fabricate content when transcript fetch fails; copyrighted transcript reposting without transformation.

**Boundaries:**
- Never invent missing transcript content, timestamps, numbers, guest names, sponsors, charts, or claims.
- If transcript is incomplete, mark the article as "基于可获取字幕整理" and avoid conclusions that depend on missing segments.
- If the user asks for Feishu delivery but env vars are missing, deliver the local Markdown path and explicit setup gap; do not report delivery success.
- Default article language is Chinese. Keep source-language terms only where they improve precision.

## Setup

```bash
# Dependencies
uv pip install youtube-transcript-api requests
# PEP 668 systems without uv: python3 -m venv ~/.venvs/yt-digest && ~/.venvs/yt-digest/bin/pip install youtube-transcript-api requests
```

Feishu delivery requires an app (custom bot webhook cannot send files). Set env vars before use:

```bash
export FEISHU_APP_ID="cli_xxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxx"
export FEISHU_RECEIVE_ID="oc_xxxxxxxx"        # chat_id of target group/user chat
export FEISHU_RECEIVE_ID_TYPE="chat_id"       # open_id | user_id | union_id | email | chat_id
```

Minimal app permissions: `im:message`, `im:message:send_as_bot`, `im:file`. The bot must be added to the target chat. See `references/feishu-setup.md` for the full app creation walkthrough.

`SKILL_DIR` below = the directory containing this SKILL.md.

## Workflow

1. **Fetch transcript.**
   ```bash
   uv run python3 SKILL_DIR/scripts/fetch_transcript.py "<URL>" --language zh,en --timestamps
   ```
   (No uv on the server: run with the venv python from Setup.) Done when: JSON with non-empty `full_text`. The fetch script defaults to `zh,en` and will retry without language restriction when needed. If still empty, tell the user transcripts are disabled and stop.

2. **Write the article.** Load `references/article-blueprint.md` and follow its module spec exactly. **Default output language is Chinese regardless of the video's language**; keep original English terms in parentheses on first appearance when useful. If the transcript exceeds ~50K chars, process in ~40K overlapping chunks and merge before writing. Done when: every blueprint module is present and every number in the article traces to the transcript (never invent figures).

3. **Save the file** to `SKILL_DIR/workspace/articles/<video_id>-<slug>.md` when this repo is local; otherwise use `~/youtube-digests/<video_id>-<slug>.md`. Keep transcripts under `SKILL_DIR/workspace/transcripts/` when available.

4. **Send to Feishu if requested.**
   ```bash
   uv run python3 SKILL_DIR/scripts/send_feishu.py SKILL_DIR/workspace/articles/<file>.md --text "<一句话定位 + 文章字数>"
   ```
   Done when: script exits 0 and prints the message_id. If it exits 2 (missing config), report the env var setup to the user and deliver the local file path instead — do not fake success. If the user did not ask for Feishu, skip this step.

5. **Report back** to the user: article path, Feishu delivery status if attempted, and the article's 30-second overview pasted inline.

## Common Pitfalls

1. **Datacenter IP blocked by YouTube.** Cloud servers (阿里云/腾讯云/AWS) are frequently blocked: error mentions "blocking requests from your IP". Fixes: set `HTTPS_PROXY` to a residential/landing proxy; or fetch the transcript from an unblocked machine and `scp` it over; cookies alone rarely suffice. Never substitute a fabricated transcript.
2. **Number conflicts inside the transcript** (e.g. 265亿 vs 290亿). Keep both, annotate their context — do not silently pick one.
3. **Subtitle dumping.** The article must *restructure* (timeline / causality / comparison), not paste paragraphs of raw transcript. If a chapter reads like verbatim subtitles, rewrite it.
4. **Feishu 99991663/99991672 errors** = wrong receive_id_type or bot not in chat. Verify `FEISHU_RECEIVE_ID_TYPE` matches the ID prefix (`oc_`=chat_id, `ou_`=open_id) and the bot has been added to the group.
5. **Premature completion.** Sending the raw transcript or a flat summary to Feishu does not count. The deliverable is the full blueprint article.

## Verification Checklist

- [ ] Transcript JSON non-empty and language matches expectation
- [ ] Article contains ALL blueprint modules (速览 / 知识地图 / 主体章节+Takeaway / 概念卡片 / 系统回顾 / 转述弹药库 / 延伸思考)
- [ ] 转述弹药库 contains exactly the required three narrative versions: 30s / 3min / 10min
- [ ] Output language is Chinese by default; original terms are retained only as needed
- [ ] No invented numbers; conflicts annotated
- [ ] File saved under `workspace/articles/` when running inside this local skill repo, otherwise under `~/youtube-digests/`
- [ ] Feishu script exit 0 with message_id (or honest failure report + local path)
