# youtube-digest 本地工作空间

本目录用于运行 `youtube-digest` skill 时存放本地过程文件和产出，避免污染项目根目录。

## 目录

- `audio/`：无字幕视频的本地音频文件
- `transcripts/`：字幕 JSON / ASR 转写 JSON / 原始文本
- `articles/`：主文、卡片包、记忆卡组三件产出
- `logs/`：抓取、ASR、生成、飞书发送日志
- `tmp/`：临时文件，可清理

## 本目录下的队列与索引

```
todolist.md        入口队列 —— 哪些视频还没处理
review-queue.md    出口队列 —— 哪些内容还没复习（D+1/3/7/16/35）
```

`todolist.md` 与 `review-queue.md` 是同一套架构的两面：git 同步的 markdown 队列 +
多机 agent 认领，只是方向相反。前者管「还没开始」，后者管「还没记住」。

## 推荐工作流

1. `scripts/fetch_transcript.py` 取字幕 → `workspace/transcripts/`
2. 无字幕且用户确认 → 下载音频到 `workspace/audio/`，`scripts/asr_faster_whisper.py` 本地转写
3. 按 `references/article-blueprint.md`（**v4.0**）生成主文 → `workspace/articles/`
4. `scripts/build_deck.py` 生成记忆卡组草稿，**人工过一遍**再交付
5. `scripts/validate_output.py` —— exit 0 才算完成
6. 把这一条加进 `review-queue.md`（首读日=今天，下次复习=D+1）
7. 双推 + `scripts/push_to_vault.py`（卡组会一并进 vault）

产物是**两个**：主文 `.md` + 卡组 `-deck.tsv`。卡片包已于 v5.0 取消，
目录里遗留的 `*-cards.md` 是历史产物，保留不删、不再新增。

## 每次会话开始

```bash
python3 scripts/review_due.py     # 退出码 0 = 有到期复习项
```

## 自洽性回归

```bash
python3 scripts/_selftest.py     # 用最小合规样例验证 validator 的规则彼此不打架
```

改过 blueprint 或 validator 之后跑一次。它同时是一份「v4.0 的文章长什么样」的骨架示例。

## 清理规则

- `tmp/` 可随时删除
- `transcripts/` 可在文章生成后按需保留或删除
- `articles/` 是正式产出，建议保留或归档
- `review-queue.md` 必须入库（跨机器共享）
