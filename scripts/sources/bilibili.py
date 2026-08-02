"""Bilibili 源适配器。

URL 形态支持:
 - bilibili.com/video/BV<10字符>
 - bilibili.com/video/av<数字>
 - b23.tv/<短链>
 - 直接的 BV 号

关键事实:
 1. 多数 UP 主视频**没有人工字幕轨**(`subtitles: []`)。B站 AI 字幕(CCM)
    部分视频有,但需要 SESSDATA cookie 才稳定返回。
 2. 因此本源的 fetch_transcript 大概率会抛 CaptionsUnavailableError,
    顶层转 ASR fallback (yt-dlp + faster-whisper) 是常态路径。

Cookie 配置 (可选):
  export BILIBILI_SESSDATA="<你的 SESSDATA>"
  不配置时仍尝试拉字幕,但命中率低。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

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


def _http_get(url: str, headers: dict | None = None, timeout: int = 15) -> dict:
    """最小 HTTP GET JSON 封装,避免额外依赖。"""
    hdrs = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json",
        **(headers or {}),
    }
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SourceFetchError(f"HTTP {e.code} {url}") from e
    except urllib.error.URLError as e:
        raise SourceFetchError(f"网络错误 {url}: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise SourceFetchError(f"非 JSON 响应 {url}") from e


class BilibiliAdapter(SourceAdapter):
    SOURCE_NAME = "bilibili"
    SOURCE_DOMAINS = ("bilibili.com", "b23.tv")

    _BV_REGEX = re.compile(r"(?:bilibili\.com/video/)?(BV[0-9A-Za-z]{10})")
    _BV_BARE = re.compile(r"^(BV[0-9A-Za-z]{10})$")
    _AV_REGEX = re.compile(r"(?:bilibili\.com/video/)?av(\d+)", re.I)
    _B23_REGEX = re.compile(r"b23\.tv/([0-9A-Za-z]+)")

    @classmethod
    def iter_url_patterns(cls):
        yield from super().iter_url_patterns()
        yield cls._BV_BARE

    @classmethod
    def parse_video_id(cls, url: str) -> str:
        url = url.strip()
        # 裸 BV 优先 — 避免和正则其它分支混淆
        m = cls._BV_BARE.match(url)
        if m:
            return m.group(1)
        m = cls._BV_REGEX.search(url)
        if m:
            return m.group(1)
        m = cls._AV_REGEX.search(url)
        if m:
            # av 号要转 BV — 调 API
            return cls._av_to_bv(m.group(1))
        m = cls._B23_REGEX.search(url)
        if m:
            return cls._resolve_b23(m.group(1))
        raise SourceNotRecognizedError(f"无法从 URL 抽取 B 站 BV 号: {url!r}")

    @classmethod
    def _av_to_bv(cls, aid: str) -> str:
        d = _http_get(f"https://api.bilibili.com/x/web-interface/view?aid={aid}")
        if d.get("code") != 0:
            raise SourceNotRecognizedError(f"av{aid} 解析失败: {d}")
        return d["data"]["bvid"]

    @classmethod
    def _resolve_b23(cls, short: str) -> str:
        """b23.tv 是 302 跳转,跟随一次拿到目标 URL 再抽 BV。"""
        url = f"https://b23.tv/{short}"
        try:
            req = urllib.request.Request(url, method="HEAD", headers={
                "User-Agent": "Mozilla/5.0",
            })
            opener = urllib.request.build_opener(NoRedirect())
            try:
                opener.open(req, timeout=10)
            except urllib.error.HTTPError as e:
                # 302 会被 NoRedirect 转成 HTTPError,Location 在 headers 里
                if e.code in (301, 302, 303, 307, 308):
                    target = e.headers.get("Location", "")
                    m = cls._BV_REGEX.search(target)
                    if m:
                        return m.group(1)
                    m = cls._AV_REGEX.search(target)
                    if m:
                        return cls._av_to_bv(m.group(1))
                    raise SourceNotRecognizedError(
                        f"b23.tv/{short} 跳转到非视频页: {target!r}"
                    ) from e
                raise
        except Exception as e:
            raise SourceFetchError(f"b23.tv/{short} 短链解析失败: {e}") from e
        raise SourceNotRecognizedError(f"b23.tv/{short} 未能识别跳转目标")

    def get_audio_download_url(self, video_id: str) -> str:
        return f"https://www.bilibili.com/video/{video_id}/"

    # ── 元数据 ──

    def fetch_metadata(self, video_id: str) -> dict:
        d = _http_get(f"https://api.bilibili.com/x/web-interface/view?bvid={video_id}")
        if d.get("code") != 0:
            raise SourceFetchError(f"B站 view API 失败: {d}")
        data = d["data"]
        return {
            "title": data.get("title", ""),
            "duration": data.get("duration", 0),
            "uploader": data.get("owner", {}).get("name", ""),
            "published_at": data.get("pubdate", 0),
            "description": data.get("desc", ""),
            "aid": data.get("aid", 0),
            "cid": data.get("cid", 0),
            "view_count": data.get("stat", {}).get("view", 0),
            "danmaku_count": data.get("stat", {}).get("danmaku", 0),
            "coin": data.get("stat", {}).get("coin", 0),
            "favorite": data.get("stat", {}).get("favorite", 0),
            "share": data.get("stat", {}).get("share", 0),
        }

    # ── 字幕 ──

    def fetch_transcript(self, video_id: str, languages: list | None = None) -> Transcript:
        meta = self.fetch_metadata(video_id)
        cid = meta.get("cid", 0)
        if not cid:
            raise SourceFetchError(f"未拿到 {video_id} 的 cid,无法拉字幕轨列表")

        headers = {"Referer": f"https://www.bilibili.com/video/{video_id}/"}
        sessdata = os.environ.get("BILIBILI_SESSDATA", "").strip()
        if sessdata:
            headers["Cookie"] = f"SESSDATA={sessdata}"

        player_url = (
            f"https://api.bilibili.com/x/player/v2?bvid={video_id}&cid={cid}"
        )
        player = _http_get(player_url, headers=headers)
        if player.get("code") != 0:
            raise SourceFetchError(f"B站 player API 失败: {player}")

        subtitle = player.get("data", {}).get("subtitle", {}) or {}
        tracks = subtitle.get("subtitles", []) or []

        if not tracks:
            if not sessdata:
                raise CaptionsUnavailableError(
                    f"{video_id} 无人工字幕轨,且未配置 BILIBILI_SESSDATA。"
                    "如需尝试 AI 字幕,请配置后重试;否则走 ASR fallback",
                    reason="no_track_no_cookie",
                )
            raise CaptionsUnavailableError(
                f"{video_id} 无可用字幕轨 (即使已配置 SESSDATA)",
                reason="no_track_with_cookie",
            )

        # 按 languages 优先级挑轨,默认第一个
        chosen = None
        if languages:
            for want in languages:
                for t in tracks:
                    if (t.get("lan") or "").startswith(want):
                        chosen = t
                        break
                if chosen:
                    break
        if chosen is None:
            chosen = tracks[0]

        sub_url = chosen.get("subtitle_url") or chosen.get("base_url") or ""
        if not sub_url:
            raise CaptionsUnavailableError(
                f"{video_id} 字幕轨没有 subtitle_url", reason="empty_track_url"
            )
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url

        data = _http_get(sub_url, headers=headers, timeout=30)
        body = data.get("body") or []
        if not body:
            raise CaptionsUnavailableError(
                f"{video_id} 字幕轨 body 为空", reason="empty_body"
            )

        segments = []
        for seg in body:
            content = (seg.get("content") or "").strip()
            if not content:
                continue
            start = float(seg.get("from", 0.0))
            end = float(seg.get("to", start))
            segments.append(TranscriptSegment(
                text=content, start=start, duration=max(0.0, end - start),
            ))

        if not segments:
            raise CaptionsUnavailableError(
                f"{video_id} 字幕轨 body 无有效内容", reason="no_valid_segment"
            )

        full_text = " ".join(s.text for s in segments)
        timestamped = "\n".join(f"{_format_ts(s.start)} {s.text}" for s in segments)
        duration_str = (
            _format_ts(segments[-1].start + segments[-1].duration)
            if segments else "0:00"
        )
        return Transcript(
            video_id=video_id,
            source=self.SOURCE_NAME,
            language=chosen.get("lan", "auto"),
            segment_count=len(segments),
            duration=duration_str,
            full_text=full_text,
            segments=segments,
            timestamped_text=timestamped,
            source_track=chosen.get("type", "official"),  # 'ai' 时会标 'ai'
            raw_metadata=meta,
        )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """阻止 urllib 自动跟随 302,这样我们能拿到 Location 头手动解析 BV。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
