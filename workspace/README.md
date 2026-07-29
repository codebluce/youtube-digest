# youtube-digest 本地工作空间

本目录用于运行 `youtube-digest` skill 时存放本地过程文件和产出，避免污染项目根目录。

## 目录

- `audio/`：无字幕视频的本地音频文件
- `transcripts/`：YouTube 字幕 JSON / ASR 转写 JSON / 原始文本
- `articles/`：按 `references/article-blueprint.md` 生成的深度知识文章 Markdown
- `logs/`：抓取、ASR、生成、飞书发送日志
- `tmp/`：临时文件，可清理

## 推荐工作流

1. 优先用 `scripts/fetch_transcript.py` 获取字幕，输出到 `workspace/transcripts/`
2. 如果无字幕且用户确认，下载音频到 `workspace/audio/`，用 `scripts/asr_faster_whisper.py` 本地转写到 `workspace/transcripts/`
3. 按 `references/article-blueprint.md` 生成文章，输出到 `workspace/articles/`
4. 如需发送飞书，用 `scripts/send_feishu.py`，日志放到 `workspace/logs/`

## 清理规则

- `tmp/` 可随时删除
- `transcripts/` 可在文章生成后按需保留或删除
- `articles/` 是正式产出，建议保留或归档
