"""YouTube 源适配器。

URL 形态支持:
 - youtube.com/watch?v=<11字符>
 - youtu.be/<11字符>
 - youtube.com/shorts/<11字符>
 - youtube.com/embed/<11字符>
 - youtube.com/live/<11字符>
 - 直接的 11 字符 ID

字幕用 youtube-transcript-api,优先 zh,en,失败回落到自动选轨。
"""

from __future__ import annotations

import re

from . import (
    CaptionsUnavailableError,
    SourceAdapter,
    SourceFetchError,
    SourceNotRecognizedError,
    Transcript,
    TranscriptSegment,
)


def _format_ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class YouTubeAdapter(SourceAdapter):
    SOURCE_NAME = "youtube"
    SOURCE_DOMAINS = ("youtube.com", "youtu.be", "m.youtube.com")

    _ID_REGEX = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})")
    _ID_BARE = re.compile(r"^([a-zA-Z0-9_-]{11})$")

    @classmethod
    def iter_url_patterns(cls):
        """除了域名匹配,还要识别**裸 11 字符 ID**(用户可能直接粘贴)。"""
        yield from super().iter_url_patterns()
        yield cls._ID_BARE

    @classmethod
    def parse_video_id(cls, url: str) -> str:
        url = url.strip()
        m = cls._ID_REGEX.search(url)
        if m:
            return m.group(1)
        m = cls._ID_BARE.match(url)
        if m:
            return m.group(1)
        raise SourceNotRecognizedError(f"无法从 URL 抽取 YouTube video_id: {url!r}")

    def get_audio_download_url(self, video_id: str) -> str:
        return f"https://www.youtube.com/watch?v={video_id}"

    # ── 字幕 ──

    def fetch_transcript(self, video_id: str, languages: list | None = None) -> Transcript:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError as e:
            raise SourceFetchError(
                "youtube-transcript-api 未安装。pip install youtube-transcript-api"
            ) from e

        api = YouTubeTranscriptApi()
        last_err: Exception | None = None

        # 第一次: 按语言优先级
        if languages:
            try:
                result = api.fetch(video_id, languages=languages)
                return self._to_transcript(video_id, result, resolved=",".join(languages))
            except Exception as e:
                last_err = e

        # 第二次: 不限语言自动选轨
        try:
            result = api.fetch(video_id)
            return self._to_transcript(
                video_id, result,
                resolved="auto_after_preferred_failed" if languages else "auto",
            )
        except Exception as e:
            last_err = e

        # 两次都失败 — 判定原因
        msg = str(last_err).lower()
        if "blocking requests from your ip" in msg:
            raise SourceFetchError(
                "YouTube 屏蔽了本机 IP (数据中心 IP 常见)。"
                "用 HTTPS_PROXY 走住宅代理重试,见 SKILL.md pitfall #1"
            ) from last_err
        raise CaptionsUnavailableError(
            f"YouTube 字幕不可用 ({video_id}): {last_err}",
            reason="subtitles_disabled_or_no_track",
        ) from last_err

    def _to_transcript(self, video_id: str, fetched, resolved: str) -> Transcript:
        segments = [
            TranscriptSegment(text=s.text, start=s.start, duration=s.duration)
            for s in fetched
        ]
        full_text = " ".join(s.text for s in segments)
        timestamped = "\n".join(
            f"{_format_ts(s.start)} {s.text}" for s in segments
        )
        duration_str = (
            _format_ts(segments[-1].start + segments[-1].duration)
            if segments else "0:00"
        )
        return Transcript(
            video_id=video_id,
            source=self.SOURCE_NAME,
            language=resolved,
            segment_count=len(segments),
            duration=duration_str,
            full_text=full_text,
            segments=segments,
            timestamped_text=timestamped,
            source_track="official",
        )
