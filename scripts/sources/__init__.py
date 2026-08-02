"""视频源插件骨架 — 统一识别/路由/输出。

加一个新视频源 = 在 sources/ 下新建一个 .py 文件,继承 SourceAdapter 即可。
不需要修改已有任何文件 — 注册表用文件系统扫描自动发现。

核心约定(继承者必读):
 1. SOURCE_NAME / SOURCE_DOMAINS 是路由用的唯一标识,必须类常量
 2. iter_url_patterns() 返回的正则只用来识别 URL,不做抓取
 3. parse_video_id(url) 返回该源内的稳定 video_id (用于 transcript 归档)
 4. fetch_transcript(video_id, languages) 返回 统一 Transcript 对象;
    字幕不可用时抛 CaptionsUnavailableError 由上层路由到 ASR fallback
 5. fetch_metadata(video_id) 返回 源方原始元数据 dict,字段不强制,
    但建议至少给 title/duration/uploader/published_at
 6. get_audio_download_url(video_id) 返回该源的可下载地址 (通常就是 watch URL),
    yt-dlp 会自动识别优先级,源不需要重复实现下载

注册表 API:
 - detect(url) → SourceAdapter 子类 (找不到返回 None)
 - all_sources() → [SourceAdapter 子类 ...]
 - adapter_for(url) → 实例化后的 adapter

边界:
 - 这里只负责 元数据+字幕 拉取,音频下载/ASR/文章/卡片都不在这里
 - 不写死任何机器路径 (HF_HOME / workspace 路径) — 由调用方注入
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ── 异常 ──────────────────────────────────────────────────────────────────

class SourceError(Exception):
    """源相关错误的基类。"""
    pass


class SourceNotRecognizedError(SourceError):
    """URL 不符合任何已注册源。"""
    pass


class CaptionsUnavailableError(SourceError):
    """字幕不可用 — 上层应该走 ASR fallback。

    attribute reason: 简短机读字符串,如 'no_track' / 'subtitles_disabled' / 'login_required'
    """
    def __init__(self, message: str, reason: str = "unknown") -> None:
        super().__init__(message)
        self.reason = reason


class SourceFetchError(SourceError):
    """源 API 调用本身失败 (网络/解析/限流等)。"""
    pass


# ── 数据模型 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VideoRef:
    """一次成功识别后的最小标识。"""
    source: str        # 源名,如 'youtube' / 'bilibili'
    video_id: str      # 源内稳定 ID: YouTube 11字符 / B站 BV 号
    canonical_url: str # 源内规范化观看 URL (用于 yt-dlp 兜底)
    extra: dict = field(default_factory=dict)  # 源特有信息 (如 B站的 aid/cid)


@dataclass
class TranscriptSegment:
    text: str
    start: float          # 秒
    duration: float       # 秒


@dataclass
class Transcript:
    """统一字幕输出 — 与现有 fetch_transcript.py 输出的 JSON 完全同构。"""
    video_id: str               # 源内稳定 ID
    source: str                 # 来源源名
    language: str               # 实际抓到的字幕语言
    segment_count: int
    duration: str               # 已格式化为 'H:MM:SS' / 'M:SS'
    full_text: str              # 拼接的全文
    segments: list = field(default_factory=list)  # [TranscriptSegment]
    timestamped_text: str = ""  # 可选
    source_track: str = ""      # 字幕轨类型标注: 'official' / 'auto-generated' / 'asr'
    raw_metadata: dict = field(default_factory=dict)  # 原始 fetch_metadata 结果

    def to_dict(self) -> dict:
        d = asdict(self)
        # segments 展开为 dict 列表,与既有 transcript JSON 同构
        d["segments"] = [{"text": s.text, "start": s.start, "duration": s.duration}
                         for s in self.segments]
        return d


@dataclass
class AudioArtifact:
    """音频下载结果。"""
    path: str           # 本地文件路径
    format: str         # 'webm' / 'm4a' / 'mp3' / 'wav'
    duration_seconds: float = 0.0
    size_bytes: int = 0


# ── 抽象基类 ─────────────────────────────────────────────────────────────

class SourceAdapter:
    """视频源适配器基类。

    子类必须覆盖全部 4 个抽象方法,可选覆盖 fetch_metadata/iter_url_patterns。

    注册机制: 文件放 sources/ 下,模块内定义一个 SourceAdapter 子类即可被发现。
    类常量 SOURCE_NAME 必须全骨架唯一 (会被注册表校验冲突)。
    """

    SOURCE_NAME: str = ""           # 必须覆盖,如 'youtube' / 'bilibili'
    SOURCE_DOMAINS: tuple = ()      # 必须覆盖,如 ('youtube.com', 'youtu.be')

    # ── 识别 ──

    @classmethod
    def iter_url_patterns(cls) -> Iterable[re.Pattern]:
        """返回 一组编译后的正则,只要任一个 search 命中就判定 URL 属于本源。
        默认实现 = 用 SOURCE_DOMAINS 匹配 hostname,子类可覆盖做更细的判断
        (比如 区分 watch 页 / 短链 / embed 页)。"""
        for d in cls.SOURCE_DOMAINS:
            yield re.compile(rf"(?:^|//|\.)({re.escape(d)})(?:/|$|:)", re.I)

    @classmethod
    def matches(cls, url: str) -> bool:
        return any(p.search(url) for p in cls.iter_url_patterns())

    # ── ID 抽取 ──

    @classmethod
    def parse_video_id(cls, url: str) -> str:
        """从 URL 中抽取该源的稳定 video_id。失败抛 SourceNotRecognizedError。"""
        raise NotImplementedError

    # ── 元数据 ──

    def fetch_metadata(self, video_id: str) -> dict:
        """拉取视频元数据。字段不强制,但建议至少给:
        title / duration / uploader / published_at / description。
        默认实现返回空 dict,子类按需覆盖。"""
        return {}

    # ── 字幕抓取 ──

    def fetch_transcript(self, video_id: str, languages: list | None = None) -> Transcript:
        """拉取字幕。字幕不可用时必须抛 CaptionsUnavailableError 由上层路由到 ASR。
        languages 是优先级列表 ['zh', 'en'],None = 让源自己挑。"""
        raise NotImplementedError

    # ── 音频下载 URL ──

    def get_audio_download_url(self, video_id: str) -> str:
        """返回 yt-dlp 能识别的观看 URL。子类几乎都要覆盖(B站 BV 号需要补全 URL)。"""
        raise NotImplementedError


# ── 注册表 ────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, type[SourceAdapter]] = {}
_DISCOVERED = False


def _discover() -> None:
    """扫描 sources/ 目录下所有模块,导入后找到 SourceAdapter 子类自动注册。"""
    global _DISCOVERED
    if _DISCOVERED:
        return
    pkg_dir = Path(__file__).parent
    for finder, name, ispkg in pkgutil.iter_modules([str(pkg_dir)]):
        if name.startswith("_"):
            continue  # 跳过 _template/_example 等模板/示例
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception as exc:
            logger.warning("sources.%s 导入失败: %s", name, exc)
            continue
        for attr in vars(mod).values():
            if (isinstance(attr, type)
                    and issubclass(attr, SourceAdapter)
                    and attr is not SourceAdapter
                    and attr.SOURCE_NAME):
                if attr.SOURCE_NAME in _REGISTRY:
                    raise SourceError(
                        f"重复的 SOURCE_NAME {attr.SOURCE_NAME!r}: "
                        f"{_REGISTRY[attr.SOURCE_NAME].__module__} 与 {mod.__name__}"
                    )
                _REGISTRY[attr.SOURCE_NAME] = attr
    _DISCOVERED = True


def all_sources() -> list[type[SourceAdapter]]:
    _discover()
    return list(_REGISTRY.values())


def detect(url: str) -> type[SourceAdapter] | None:
    """根据 URL 找到匹配的 adapter 类。无匹配返回 None。"""
    _discover()
    for cls in _REGISTRY.values():
        if cls.matches(url):
            return cls
    return None


def adapter_for(url: str) -> SourceAdapter:
    """识别并实例化。失败抛 SourceNotRecognizedError。"""
    cls = detect(url)
    if cls is None:
        raise SourceNotRecognizedError(
            f"URL 无法识别为已注册的视频源: {url!r}。"
            f"已注册源: {sorted(_REGISTRY)}"
        )
    return cls()


def ref_for(url: str) -> VideoRef:
    """一次性识别 + 提取 ID + 拼接 canonical URL。"""
    adapter = adapter_for(url)
    video_id = adapter.__class__.parse_video_id(url)
    return VideoRef(
        source=adapter.SOURCE_NAME,
        video_id=video_id,
        canonical_url=adapter.get_audio_download_url(video_id),
    )
