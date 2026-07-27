# youtube-digest 本地工作空间

本目录用于运行 `youtube-knowledge-digest` skill 时存放本地过程文件和产出，避免污染项目根目录。

## 目录

- `transcripts/`：YouTube 字幕 JSON / 原始文本
- `articles/`：按 `references/article-blueprint.md` 生成的深度知识文章 Markdown
- `logs/`：抓取、生成、飞书发送日志
- `tmp/`：临时文件，可清理

## 推荐工作流

1. 用 `scripts/fetch_transcript.py` 获取字幕，输出到 `workspace/transcripts/`
2. 按 `references/article-blueprint.md` 生成文章，输出到 `workspace/articles/`
3. 如需发送飞书，用 `scripts/send_feishu.py`，日志放到 `workspace/logs/`

## 清理规则

- `tmp/` 可随时删除
- `transcripts/` 可在文章生成后按需保留或删除
- `articles/` 是正式产出，建议保留或归档
