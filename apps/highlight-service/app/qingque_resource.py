from __future__ import annotations

import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx


DEFAULT_QINGQUE_DOC_ID = "eZQBGcZW8Gc2gdfFbwROXAN_v"
DEFAULT_QINGQUE_IDENTITY_ID = "2BVjpP7d2gd"
DEFAULT_QINGQUE_SHEETS = (
    "1438618429",
    "694740665",
    "45441510",
    "1984407342",
)
QINGQUE_BASE_URL = "https://docs.qingque.cn"
BAIDU_LINK_RE = re.compile(r"https?://pan\.baidu\.com/[^\s，,；;）)]+", re.IGNORECASE)
EXTRACT_CODE_RE = re.compile(r"(?:提取码|提取碼|密码|密碼|pwd)\s*[:：=]?\s*([A-Za-z0-9]{4})", re.IGNORECASE)


@dataclass(frozen=True)
class QingqueResourceMatch:
    drama_name: str
    baidu_url: str
    extract_code: str
    raw_link_text: str
    sheet_id: str
    sheet_name: str
    row: int
    score: float
    match_type: str


class QingqueResourceError(RuntimeError):
    pass


class QingqueResourceClient:
    def __init__(
        self,
        *,
        doc_id: str = DEFAULT_QINGQUE_DOC_ID,
        identity_id: str = DEFAULT_QINGQUE_IDENTITY_ID,
        sheet_ids: tuple[str, ...] = DEFAULT_QINGQUE_SHEETS,
        ttl_seconds: int = 1800,
        timeout_seconds: int = 60,
    ) -> None:
        self.doc_id = doc_id
        self.identity_id = identity_id
        self.sheet_ids = sheet_ids
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._cache_expires_at = 0.0
        self._cache: list[QingqueResourceMatch] = []

    def search(self, name: str, *, limit: int = 10, refresh: bool = False) -> list[QingqueResourceMatch]:
        query = normalize_search_text(name)
        if not query:
            raise QingqueResourceError("name is required")
        resources = self.resources(refresh=refresh)
        scored = [with_match_score(item, query) for item in resources]
        matches = [item for item in scored if item.score >= 0.58 or query in normalize_search_text(item.drama_name)]
        matches.sort(key=lambda item: (-item.score, item.sheet_name, item.row))
        return matches[:limit]

    def resources(self, *, refresh: bool = False) -> list[QingqueResourceMatch]:
        now = time.monotonic()
        if not refresh and self._cache and now < self._cache_expires_at:
            return list(self._cache)
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            home = fetch_home(client, self.doc_id, self.identity_id)
            revision = home.get("snapshotVersion") or home.get("docLatestRevision")
            if not revision:
                raise QingqueResourceError("Qingque home response does not include snapshot revision")
            sheet_names = sheet_name_map(home)
            resources: list[QingqueResourceMatch] = []
            for sheet_id in self.sheet_ids:
                snapshot = fetch_sheet_snapshot(client, self.doc_id, self.identity_id, str(revision), sheet_id)
                rows = parse_snapshot_rows(snapshot)
                resources.extend(extract_resources_from_rows(rows, sheet_id=sheet_id, sheet_name=sheet_names.get(sheet_id, sheet_id)))
        self._cache = resources
        self._cache_expires_at = now + self.ttl_seconds
        return list(resources)


def fetch_home(client: httpx.Client, doc_id: str, identity_id: str) -> dict[str, Any]:
    response = client.get(f"{QINGQUE_BASE_URL}/excel/api/home/{doc_id}", params={"identityId": identity_id})
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result")
    if not isinstance(result, dict):
        raise QingqueResourceError("Qingque home response is invalid")
    return result


def fetch_sheet_snapshot(client: httpx.Client, doc_id: str, identity_id: str, revision: str, sheet_id: str) -> Any:
    response = client.post(
        f"{QINGQUE_BASE_URL}/excel/api/latest/snapshot/{doc_id}",
        params={
            "snapshotRevision": revision,
            "top": "false",
            "sheetId": sheet_id,
            "identityId": identity_id,
        },
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json()


def sheet_name_map(home: dict[str, Any]) -> dict[str, str]:
    ids = home.get("sheetIds") or []
    names = home.get("sheetNames") or []
    if not isinstance(ids, list) or not isinstance(names, list):
        return {}
    return {str(sheet_id): str(names[index]) for index, sheet_id in enumerate(ids) if index < len(names)}


def parse_snapshot_rows(snapshot: Any) -> dict[int, dict[int, Any]]:
    try:
        sheet_data = snapshot[1][1]["2"]
        coordinates = sheet_data["2"]
        cells = sheet_data["3"]
        values = sheet_data["4"]
    except (IndexError, KeyError, TypeError) as exc:
        raise QingqueResourceError("Qingque snapshot structure is not supported") from exc

    if not isinstance(coordinates, list) or not isinstance(cells, list) or not isinstance(values, list):
        raise QingqueResourceError("Qingque snapshot contains invalid table data")

    rows: dict[int, dict[int, Any]] = {}
    for coordinate in coordinates:
        if not isinstance(coordinate, dict):
            continue
        row_index = coordinate.get("1")
        column_index = coordinate.get("2")
        cell_index = coordinate.get("3")
        if not all(isinstance(value, int) for value in (row_index, column_index, cell_index)):
            continue
        if cell_index < 0 or cell_index >= len(cells):
            continue
        value = cell_display_value(cells[cell_index], values)
        if value in ("", None):
            continue
        rows.setdefault(row_index, {})[column_index] = value
    return rows


def cell_display_value(cell: Any, values: list[Any]) -> Any:
    if not isinstance(cell, dict):
        return ""
    value_index = cell.get("1")
    if not isinstance(value_index, int):
        value_index = cell.get("2")
    if not isinstance(value_index, int) or value_index < 0 or value_index >= len(values):
        return ""
    value = values[value_index]
    if not isinstance(value, dict):
        return ""
    if "2" in value:
        return value["2"]
    if "3" in value:
        return value["3"]
    return ""


def extract_resources_from_rows(rows: dict[int, dict[int, Any]], *, sheet_id: str, sheet_name: str) -> list[QingqueResourceMatch]:
    resources: list[QingqueResourceMatch] = []
    for header_row, row in sorted(rows.items()):
        headers = {normalize_header(value): column for column, value in row.items()}
        name_column = first_existing(headers, ("任务名称", "短剧名称", "剧名", "片名"))
        link_column = first_existing(headers, ("网盘链接", "百度云链接", "百度网盘链接", "素材网盘链接"))
        if name_column is None or link_column is None:
            continue
        for row_index in sorted(key for key in rows if key > header_row):
            data_row = rows[row_index]
            if looks_like_header_row(data_row):
                break
            drama_name = str(data_row.get(name_column) or "").strip()
            raw_link_text = str(data_row.get(link_column) or "").strip()
            if not drama_name or "pan.baidu.com" not in raw_link_text:
                continue
            baidu_url = extract_baidu_url(raw_link_text)
            if not baidu_url:
                continue
            resources.append(
                QingqueResourceMatch(
                    drama_name=drama_name,
                    baidu_url=baidu_url,
                    extract_code=extract_code(raw_link_text, baidu_url),
                    raw_link_text=raw_link_text,
                    sheet_id=sheet_id,
                    sheet_name=sheet_name,
                    row=row_index + 1,
                    score=1.0,
                    match_type="indexed",
                )
            )
        break
    return resources


def normalize_header(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def first_existing(headers: dict[str, int], candidates: tuple[str, ...]) -> int | None:
    for candidate in candidates:
        if candidate in headers:
            return headers[candidate]
    return None


def looks_like_header_row(row: dict[int, Any]) -> bool:
    values = {normalize_header(value) for value in row.values()}
    return "任务名称" in values and "网盘链接" in values


def extract_baidu_url(text: str) -> str:
    match = BAIDU_LINK_RE.search(text)
    return match.group(0).rstrip(".。") if match else ""


def extract_code(text: str, baidu_url: str = "") -> str:
    parsed = urlparse(baidu_url)
    pwd = parse_qs(parsed.query).get("pwd")
    if pwd and pwd[0]:
        return pwd[0][:4]
    match = EXTRACT_CODE_RE.search(text)
    return match.group(1) if match else ""


def normalize_search_text(value: str) -> str:
    return re.sub(r"[\s《》<>【】\\[\\]（）()·._-]+", "", str(value or "")).lower()


def with_match_score(item: QingqueResourceMatch, query: str) -> QingqueResourceMatch:
    target = normalize_search_text(item.drama_name)
    if not target:
        score = 0.0
        match_type = "none"
    elif query == target:
        score = 1.0
        match_type = "exact"
    elif query in target:
        score = min(0.98, 0.78 + len(query) / max(len(target), 1) * 0.2)
        match_type = "contains"
    elif target in query:
        score = min(0.95, 0.74 + len(target) / max(len(query), 1) * 0.2)
        match_type = "contains"
    else:
        score = SequenceMatcher(None, query, target).ratio()
        match_type = "fuzzy"
    return QingqueResourceMatch(
        drama_name=item.drama_name,
        baidu_url=item.baidu_url,
        extract_code=item.extract_code,
        raw_link_text=item.raw_link_text,
        sheet_id=item.sheet_id,
        sheet_name=item.sheet_name,
        row=item.row,
        score=round(score, 4),
        match_type=match_type,
    )


qingque_resource_client = QingqueResourceClient()
