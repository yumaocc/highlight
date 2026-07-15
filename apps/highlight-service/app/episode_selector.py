from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
NON_STORY_KEYWORDS = (
    "花絮",
    "预告",
    "預告",
    "片花",
    "彩蛋",
    "番外",
    "试看",
    "試看",
    "解说",
    "解說",
    "混剪",
    "宣传",
    "宣傳",
    "物料",
    "素材说明",
    "说明",
    "封面",
    "海报",
    "海報",
    "字幕",
    "主题曲",
    "主題曲",
    "ost",
    "trailer",
    "preview",
    "teaser",
)
GENERIC_PATH_SEGMENTS = {"短剧资源", "百度网盘", "百度云", "baidu", "我的资源"}


@dataclass(frozen=True)
class RemoteFile:
    name: str
    path: str
    size: int = 0
    is_dir: bool = False
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class DownloadedEpisode:
    name: str
    remote_path: str
    local_path: str
    size_bytes: int
    episode_number: int | None = None


def select_first_episodes(files: list[RemoteFile], *, limit: int = 5, drama_name: str = "") -> list[RemoteFile]:
    candidates = story_episode_candidates(files, drama_name=drama_name)
    numbered = [item for item in candidates if episode_number(item.name) is not None]
    unnumbered = [item for item in candidates if episode_number(item.name) is None]
    numbered.sort(key=lambda item: (episode_number(item.name) or 999999, natural_key(item.name)))
    unnumbered.sort(key=lambda item: natural_key(item.name))
    return (numbered + unnumbered)[:limit]


def story_episode_candidates(files: list[RemoteFile], *, drama_name: str = "") -> list[RemoteFile]:
    story_files = [item for item in files if is_story_video(item)]
    matched = filter_by_drama_name(story_files, drama_name)
    if matched:
        return matched
    return story_files


def filter_by_drama_name(files: list[RemoteFile], drama_name: str) -> list[RemoteFile]:
    normalized_drama = normalize_title(drama_name)
    if not normalized_drama:
        return []
    matched = [
        item
        for item in files
        if normalized_drama in normalize_title(item.name) or path_segment_matches(item.path, normalized_drama)
    ]
    if matched:
        return matched

    drama_parts = [part for part in re.split(r"[/\s._\-《》【】()（）]+", drama_name) if len(normalize_title(part)) >= 2]
    normalized_parts = [normalize_title(part) for part in drama_parts]
    if not normalized_parts:
        return []
    return [
        item
        for item in files
        if any(part in normalize_title(item.name) or path_segment_matches(item.path, part) for part in normalized_parts)
    ]


def is_story_video(item: RemoteFile) -> bool:
    text = normalize_title(f"{item.path} {item.name}")
    if any(keyword in text for keyword in NON_STORY_KEYWORDS):
        return False
    return episode_number(item.name) is not None or episode_number(item.path) is not None


def episode_number(filename: str) -> int | None:
    stem = Path(filename).stem
    patterns = [
        r"第\s*0*(\d{1,4})\s*[集话話]",
        r"(?:EP|E)\s*0*(\d{1,4})(?!\d)",
        r"S\d{1,3}\s*E\s*0*(\d{1,4})(?!\d)",
        r"(?:^|[^\d])0*(\d{1,3})(?=[^\d]*$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem, flags=re.IGNORECASE)
        if not match:
            continue
        number = int(match.group(1))
        if number > 0:
            return number
    return None


def normalize_title(value: str) -> str:
    return re.sub(r"[\s《》<>【】\[\]（）()·._/\\-]+", "", str(value or "")).lower()


def path_segment_matches(path: str, normalized_name: str) -> bool:
    generic_segments = {normalize_title(item) for item in GENERIC_PATH_SEGMENTS}
    for segment in str(path or "").split("/"):
        normalized_segment = normalize_title(segment)
        if not normalized_segment or normalized_segment in generic_segments:
            continue
        if normalized_name in normalized_segment:
            return True
    return False


def normalize_remote_path(path: str) -> str:
    clean = "/" + str(path or "").strip().strip("/")
    return clean if clean != "/" else "/"


def remote_join(parent: str, name: str) -> str:
    return f"{normalize_remote_path(parent).rstrip('/')}/{name}".replace("//", "/")


def safe_filename(name: str) -> str:
    clean = Path(name).name.strip()
    clean = re.sub(r"[/:\\\0]", "_", clean)
    return clean or "downloaded-video.mp4"


def safe_remote_segment(name: str) -> str:
    clean = str(name or "").strip()
    clean = re.sub(r"[/\\:\0]+", "_", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip(" .") or "未命名短剧"


def natural_key(value: str) -> list[Any]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def episode_result(item: RemoteFile) -> dict[str, Any]:
    return {
        "name": item.name,
        "remote_path": item.path,
        "size": item.size,
        "episode_number": episode_number(item.name),
    }


def download_result(item: DownloadedEpisode) -> dict[str, Any]:
    return {
        "name": item.name,
        "remote_path": item.remote_path,
        "local_path": item.local_path,
        "size_bytes": item.size_bytes,
        "episode_number": item.episode_number,
    }
