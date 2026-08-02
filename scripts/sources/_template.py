"""新视频源接入模板 — 3 步接入一个新源。

使用:
 1. 复制本文件为新文件 (如 sources/vimeo.py / sources/xigua.py)
 2. 改类常量 SOURCE_NAME / SOURCE_DOMAINS
 3. 实现 4 个方法

新源**不需要**改任何已有文件 — sources/__init__.py 的文件扫描会自动发现并注册。

约定与边界见 sources/__init__.py 顶部 docstring。
"""

from __future__ import annotations

import re

from . import (
    AudioArtifact,
    CaptionsUnavailableError,
    SourceAdapter,
    SourceFetchError,
    SourceNotRecognizedError,
    Transcript,
    TranscriptSegment,
)


class ExampleAdapter(SourceAdapter):
    """示例: 一个虚构的视频站。

    真实接入参考 youtube.py / bilibili.py。
    """

    SOURCE_NAME = "example"                         # 全局唯一
    SOURCE_DOMAINS = ("example.com", "exmpl.tv")    # 用于 URL 识别的域名

    # ── 1. 识别 + 抽 ID ─────────────────────────────────────

    @classmethod
    def parse_video_id(cls, url: str) -> str:
        """从 URL 抽取 video_id。
        - 必须是稳定 ID,跨时间不变,跨 URL 形态不变 (watch/embed/share/短链指向同 ID)
        - 找不到时抛 SourceNotRecognizedError,不要静默返回错值"""
        m = re.search(r"example\.com/watch/([A-Za-z0-9_-]{6,})", url)
        if m:
            return m.group(1)
        m = re.search(r"exmpl\.tv/([A-Za-z0-9_-]{6,})", url)
        if m:
            return m.group(1)
        raise SourceNotRecognizedError(f"无法从 URL 抽取 example 视频 ID: {url!r}")

    # ── 2. yt-dlp 兜底下载 URL ───────────────────────────────

    def get_audio_download_url(self, video_id: str) -> str:
        return f"https://example.com/watch/{video_id}"

    # ── 3. 元数据 (可选但建议实现) ───────────────────────────

    def fetch_metadata(self, video_id: str) -> dict:
        return {
            "title": "",
            "duration": 0,
            "uploader": "",
            "published_at": "",
            "description": "",
        }

    # ── 4. 字幕抓取 ─────────────────────────────────────────

    def fetch_transcript(self, video_id: str, languages: list | None = None) -> Transcript:
        """抓字幕。字幕不可用时必须抛 CaptionsUnavailableError 而不是返回空 Transcript ——
        顶层根据这个异常路由到 ASR fallback。"""
        raise CaptionsUnavailableError(
            f"example 源暂未实现字幕抓取 — {video_id}",
            reason="not_implemented",
        )
        # 真正实现参考 bilibili.py:
        #   segments = [...]
        #   return Transcript(
        #       video_id=video_id,
        #       source=self.SOURCE_NAME,
        #       language="zh",
        #       segment_count=len(segments),
        #       duration=format_duration(...),
        #       full_text=" ".join(s.text for s in segments),
        #       segments=segments,
        #       timestamped_text=...,
        #       source_track="official",   # 或 'auto-generated' / 'ccm'
        #       raw_metadata=self.fetch_metadata(video_id),
        #   )
