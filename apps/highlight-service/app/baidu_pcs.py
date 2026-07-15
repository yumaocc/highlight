from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from .config import get_settings
from .episode_selector import (
    DownloadedEpisode,
    RemoteFile,
    VIDEO_SUFFIXES,
    download_result,
    episode_number,
    episode_result,
    normalize_remote_path,
    remote_join,
    safe_filename,
    safe_remote_segment,
    select_first_episodes,
)


BAIDU_PCS_COMMAND_LOCK = Lock()


class BaiduPCSError(RuntimeError):
    pass


class BaiduPCSClient:
    """Thin wrapper around BaiduPCS-Go for share transfer, listing, and download."""

    def __init__(self, binary_path: str | None = None, timeout_seconds: int | None = None) -> None:
        settings = get_settings()
        self.binary_path = binary_path or settings.baidu_pcs_go_path
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.baidu_pcs_timeout_seconds
        if not self.binary_path:
            raise BaiduPCSError("BAIDU_PCS_GO_PATH is not configured")
        if not Path(self.binary_path).exists():
            raise BaiduPCSError(f"BaiduPCS-Go executable not found: {self.binary_path}")

    def mkdirs(self, remote_dir: str) -> None:
        current = ""
        for part in normalize_remote_path(remote_dir).strip("/").split("/"):
            if not part:
                continue
            current = f"{current}/{part}"
            output = self._run(["mkdir", current], check=False)
            if output.returncode != 0 and not _is_already_exists(output.text):
                raise BaiduPCSError(_command_error("mkdir", output.text))

    def cd(self, remote_dir: str) -> None:
        self._run_checked(["cd", normalize_remote_path(remote_dir)])

    def transfer_share(self, share_url: str, extract_code: str = "", target_dir: str = "/") -> dict[str, Any]:
        if not share_url:
            raise BaiduPCSError("Baidu share URL is required")
        target = normalize_remote_path(target_dir)
        args = ["transfer", "--collect", share_url]
        if extract_code:
            args.append(extract_code)
        with BAIDU_PCS_COMMAND_LOCK:
            self.mkdirs(target)
            self.cd(target)
            output = self._run(args, check=False)
            if output.returncode != 0 or _looks_like_baidu_error(output.text):
                if _is_duplicate_file(output.text):
                    return {"target_dir": target, "output": output.text, "skipped": True, "reason": "duplicate_file"}
                if _looks_like_saas_parse_failure(output.text):
                    fallback = transfer_saas_share(share_url, extract_code, target)
                    return {
                        "target_dir": target,
                        "output": fallback["message"],
                        "skipped": fallback["skipped"],
                        "reason": fallback.get("reason", "saas_fallback"),
                        "fallback": fallback,
                    }
                raise BaiduPCSError(_command_error(args[0] if args else "BaiduPCS-Go", output.text))
        return {"target_dir": target, "output": output.text, "skipped": False}

    def list_dir(self, remote_dir: str) -> list[RemoteFile]:
        target = normalize_remote_path(remote_dir)
        output = self._run_checked(["ls", target])
        return parse_ls_output(output.text, target)

    def list_video_files(self, remote_dir: str, *, recursive: bool = True, max_depth: int = 4) -> list[RemoteFile]:
        results: list[RemoteFile] = []
        visited: set[str] = set()

        def visit(path: str, depth: int) -> None:
            normalized = normalize_remote_path(path)
            if normalized in visited:
                return
            visited.add(normalized)
            for item in self.list_dir(normalized):
                if item.is_dir:
                    if recursive and depth < max_depth:
                        visit(item.path, depth + 1)
                    continue
                if Path(item.name).suffix.lower() in VIDEO_SUFFIXES:
                    results.append(item)

        visit(remote_dir, 0)
        return results

    def download_file(self, remote_file: RemoteFile, destination_dir: Path, *, overwrite: bool = False) -> DownloadedEpisode:
        if remote_file.is_dir:
            raise BaiduPCSError(f"cannot download directory: {remote_file.path}")
        destination_dir.mkdir(parents=True, exist_ok=True)
        args = ["download", "--saveto", str(destination_dir)]
        if overwrite:
            args.append("--ow")
        args.append(remote_file.path)
        self._run_checked(args, timeout=max(self.timeout_seconds, 3600))
        target = _find_downloaded_path(destination_dir, remote_file.name)
        if not target:
            raise BaiduPCSError(f"download finished but file was not found: {remote_file.name}")
        stat = target.stat()
        return DownloadedEpisode(
            name=remote_file.name,
            remote_path=remote_file.path,
            local_path=str(target),
            size_bytes=stat.st_size,
            episode_number=episode_number(remote_file.name),
        )

    def _run_checked(self, args: list[str], *, timeout: int | None = None) -> _CommandResult:
        result = self._run(args, timeout=timeout)
        if result.returncode != 0:
            raise BaiduPCSError(_command_error(args[0] if args else "BaiduPCS-Go", result.text))
        if _looks_like_baidu_error(result.text):
            raise BaiduPCSError(result.text.strip())
        return result

    def _run(self, args: list[str], *, check: bool = True, timeout: int | None = None) -> _CommandResult:
        env = os.environ.copy()
        process = subprocess.run(
            [self.binary_path, *args],
            capture_output=True,
            text=True,
            timeout=timeout or self.timeout_seconds,
            env=env,
            check=False,
        )
        text = "\n".join(part for part in (process.stdout, process.stderr) if part).strip()
        result = _CommandResult(returncode=process.returncode, text=text)
        if check and process.returncode != 0:
            raise BaiduPCSError(_command_error(args[0] if args else "BaiduPCS-Go", text))
        return result


def download_first_episodes_from_baidupcs_share(
    share_url: str,
    extract_code: str,
    destination_dir: Path,
    *,
    remote_root: str | None = None,
    remote_name: str = "",
    limit: int = 5,
    recursive: bool = True,
    max_depth: int = 4,
    overwrite: bool = False,
    drama_name: str = "",
    client: BaiduPCSClient | None = None,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be greater than 0")
    settings = get_settings()
    pcs = client or BaiduPCSClient()
    root = normalize_remote_path(remote_root or settings.baidu_pcs_remote_root)
    folder_name = safe_remote_segment(remote_name or drama_name)
    target_dir = remote_join(root, folder_name)
    transfer = pcs.transfer_share(share_url, extract_code, target_dir)
    files = pcs.list_video_files(target_dir, recursive=recursive, max_depth=max_depth)
    selected = select_first_episodes(files, limit=limit, drama_name=drama_name or remote_name)
    downloaded = [
        pcs.download_file(remote_file, destination_dir, overwrite=overwrite)
        for remote_file in selected
    ]
    return {
        "share_url": share_url,
        "extract_code": extract_code,
        "remote_root": root,
        "remote_dir": target_dir,
        "resolved_remote_dir": target_dir,
        "destination_dir": str(destination_dir),
        "transfer": transfer,
        "found": len(files),
        "selected": [episode_result(item) for item in selected],
        "downloaded": [download_result(item) for item in downloaded],
    }


def parse_ls_output(output: str, parent_path: str) -> list[RemoteFile]:
    files: list[RemoteFile] = []
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not _is_table_item_line(line):
            continue
        item = parse_ls_item_line(line, parent_path)
        if item:
            files.append(item)
    return files


def parse_ls_item_line(line: str, parent_path: str) -> RemoteFile | None:
    match = re.match(r"^\s*\d+\s+(.+?)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.+?)\s*$", line)
    if not match:
        return None
    size_text = match.group(1).strip()
    name = match.group(4).strip()
    if not name:
        return None
    is_dir = name.endswith("/")
    clean_name = name.rstrip("/") if is_dir else name
    return RemoteFile(
        name=clean_name,
        path=remote_join(parent_path, clean_name),
        size=parse_size(size_text),
        is_dir=is_dir,
        raw={"line": line},
    )


def parse_size(value: str) -> int:
    text = str(value or "").strip()
    if not text or text == "-":
        return 0
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)([KMGT]?B)$", text, flags=re.IGNORECASE)
    if not match:
        return 0
    number = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}.get(unit, 1)
    return int(number * multiplier)


def _is_table_item_line(line: str) -> bool:
    return bool(re.match(r"^\s*\d+\s+", line)) and not re.search(r"文件总数|目录总数", line)


def _find_downloaded_path(destination_dir: Path, remote_name: str) -> Path | None:
    expected = destination_dir / safe_filename(remote_name)
    if expected.exists():
        return expected
    matches = list(destination_dir.rglob(safe_filename(remote_name)))
    if matches:
        matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return matches[0]
    return None


def _is_already_exists(output: str) -> bool:
    text = output.lower()
    return "已存在" in output or "exist" in text


def _is_duplicate_file(output: str) -> bool:
    text = str(output or "").lower()
    return "文件重复" in output or ("重复" in output and "文件" in output) or "duplicate" in text


def _looks_like_baidu_error(output: str) -> bool:
    text = output.strip()
    if not text:
        return False
    return "遇到错误" in text or "错误代码" in text or "失败" in text and "成功" not in text


def _command_error(command: str, output: str) -> str:
    detail = output.strip() or "no output"
    return f"BaiduPCS-Go {command} failed: {detail}"


class _CommandResult:
    def __init__(self, returncode: int, text: str) -> None:
        self.returncode = returncode
        self.text = text


def transfer_saas_share(share_url: str, extract_code: str, target_dir: str) -> dict[str, Any]:
    """Transfer Baidu enterprise/SaaS shares that BaiduPCS-Go cannot parse."""
    cookies = _load_baidupcs_cookies()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Encoding": "identity",
    }
    try:
        with httpx.Client(timeout=30, follow_redirects=True, cookies=cookies, headers=headers) as client:
            page = client.get(share_url)
            page.raise_for_status()
            page_data = _extract_yun_data(page.text)
            if page_data.get("shareType") != "saas":
                raise BaiduPCSError("分享页不是企业 SaaS 链接，不能使用企业分享兜底")

            share_info = page_data.get("saasShareInfo") or {}
            share_id = share_info.get("shareid")
            share_uk = share_info.get("share_uk")
            surl = page_data.get("surl")
            if not all((share_id, share_uk, surl)):
                raise BaiduPCSError("企业分享页缺少 shareid/share_uk/surl")

            verify = client.post(
                "https://pan.baidu.com/share/verify",
                params={
                    "surl": surl,
                    "clienttype": 0,
                    "app_id": 250528,
                    "web": 1,
                    "channel": "chunlei",
                    "t": int(time.time() * 1000),
                },
                data={"pwd": extract_code, "vcode": "", "vcode_str": ""},
                headers={"Referer": str(page.url)},
            )
            verify.raise_for_status()
            verify_data = verify.json()
            if int(verify_data.get("errno") or 0) != 0:
                raise BaiduPCSError(verify_data.get("show_msg") or "企业分享提取码验证失败")
            sekey = unquote(str(verify_data.get("randsk") or ""))
            if not sekey:
                raise BaiduPCSError("企业分享验证成功，但没有返回 sekey")

            listing = client.get(
                "https://pan.baidu.com/share/list",
                params={
                    "root": 1,
                    "uk": share_uk,
                    "shareid": share_id,
                    "shorturl": surl,
                    "page": 1,
                    "num": 100,
                    "web": 1,
                    "app_id": 250528,
                    "channel": "chunlei",
                    "clienttype": 0,
                },
                headers={"Referer": f"https://pan.baidu.com/e/{page_data.get('shorturl') or '1' + str(surl)}"},
            )
            listing.raise_for_status()
            list_data = listing.json()
            if int(list_data.get("errno") or 0) != 0:
                raise BaiduPCSError(list_data.get("show_msg") or "企业分享文件列表读取失败")
            files = list_data.get("list") or []
            fs_ids = [int(item["fs_id"]) for item in files if item.get("fs_id")]
            if not fs_ids:
                raise BaiduPCSError("企业分享中没有可转存文件")

            disk_page = client.get("https://pan.baidu.com/disk/main")
            disk_page.raise_for_status()
            bdstoken = _extract_bdstoken(disk_page.text)
            response = client.post(
                "https://pan.baidu.com/share/transfer",
                params={
                    "shareid": share_id,
                    "from": share_uk,
                    "bdstoken": bdstoken,
                    "sekey": sekey,
                    "ondup": "fail",
                    "async": 1,
                    "app_id": 250528,
                    "channel": "chunlei",
                    "clienttype": 0,
                    "web": 1,
                },
                data={"fsidlist": json.dumps(fs_ids), "path": normalize_remote_path(target_dir)},
                headers={
                    "Referer": f"https://pan.baidu.com/e/{page_data.get('shorturl') or '1' + str(surl)}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            response.raise_for_status()
            result = response.json()
    except BaiduPCSError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise BaiduPCSError(f"企业分享转存请求失败: {exc}") from exc

    errno = int(result.get("errno") or 0)
    if errno == 0:
        return {
            "ok": True,
            "skipped": False,
            "reason": "saas_fallback",
            "message": "企业分享已通过 HTTP 兼容接口转存到网盘",
            "item_count": len(fs_ids),
        }
    if errno in {4, 12} or _has_duplicate_transfer_info(result):
        return {
            "ok": True,
            "skipped": True,
            "reason": "duplicate_file",
            "message": "企业分享目标文件已存在，跳过重复转存",
            "item_count": len(fs_ids),
        }
    raise BaiduPCSError(result.get("show_msg") or f"企业分享转存失败，错误码 {errno}")


def _load_baidupcs_cookies() -> dict[str, str]:
    config_root = Path(os.environ.get("BAIDUPCS_GO_CONFIG_DIR") or Path.home() / ".config" / "BaiduPCS-Go")
    config_path = config_root / "pcs_config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaiduPCSError(f"无法读取 BaiduPCS-Go 登录配置: {config_path}") from exc
    active_uid = config.get("baidu_active_uid")
    users = config.get("baidu_user_list") or []
    user = next((item for item in users if item.get("uid") == active_uid), users[0] if users else None)
    if not user:
        raise BaiduPCSError("BaiduPCS-Go 没有可用的登录账号")
    cookies: dict[str, str] = {}
    for part in str(user.get("cookies") or "").split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        if not name or not value or '"' in value or name == "BDCLND":
            continue
        cookies[name] = value
    if not cookies.get("BDUSS") or not cookies.get("STOKEN"):
        raise BaiduPCSError("BaiduPCS-Go Cookie 缺少 BDUSS 或 STOKEN")
    return cookies


def _extract_yun_data(html: str) -> dict[str, Any]:
    match = re.search(r"window\.yunData\s*=\s*(\{.*?\});\s*(?:\n|</script>)", html, flags=re.DOTALL)
    if not match:
        raise BaiduPCSError("企业分享页没有找到 window.yunData")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise BaiduPCSError("企业分享页 window.yunData 解析失败") from exc


def _extract_bdstoken(html: str) -> str:
    match = re.search(r"['\"]bdstoken['\"]\s*[:=]\s*['\"]([^'\"]+)", html)
    if not match:
        raise BaiduPCSError("百度网盘登录页没有返回 bdstoken")
    return match.group(1)


def _has_duplicate_transfer_info(result: dict[str, Any]) -> bool:
    return any(int(item.get("errno") or 0) == -30 for item in result.get("info") or [])


def _looks_like_saas_parse_failure(output: str) -> bool:
    return "分享链接转存到网盘失败" in output and "STOKEN" in output
