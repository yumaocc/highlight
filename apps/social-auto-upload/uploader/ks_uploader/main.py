# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import inspect
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from patchright.async_api import Locator
from patchright.async_api import Page
from patchright.async_api import Playwright
from patchright.async_api import async_playwright

from conf import DEBUG_MODE, LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from uploader.base_video import BaseVideoUploader
from utils.base_social_media import set_init_script
from utils.files_times import get_absolute_path
from utils.login_qrcode import build_login_qrcode_path
from utils.login_qrcode import decode_qrcode_from_path
from utils.login_qrcode import print_terminal_qrcode
from utils.login_qrcode import remove_qrcode_file
from utils.login_qrcode import save_data_url_image
from utils.log import kuaishou_logger

KUAISHOU_UPLOAD_URL = "https://cp.kuaishou.com/article/publish/video"
KUAISHOU_MANAGE_URL = "https://cp.kuaishou.com/article/manage/video?status=2&from=publish"
KUAISHOU_LOGIN_URL = "https://passport.kuaishou.com/pc/account/login/?sid=kuaishou.web.cp.api&callback=https%3A%2F%2Fcp.kuaishou.com%2Frest%2Finfra%2Fsts%3FfollowUrl%3Dhttps%253A%252F%252Fcp.kuaishou.com%252Farticle%252Fpublish%252Fvideo%26setRootDomain%3Dtrue"
KUAISHOU_UPLOAD_URL_PATTERN = "**/article/publish/video**"
KUAISHOU_MANAGE_URL_PATTERN = "**/article/manage/video?status=2&from=publish**"
KUAISHOU_COOKIE_INVALID_SELECTOR = "div.names div.container div.name:text('机构服务')"
KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
KUAISHOU_PUBLISH_STRATEGY_SCHEDULED = "scheduled"


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


def _print_ks_qrcode(qrcode_content: str, qrcode_path: Path) -> None:
    try:
        print_terminal_qrcode(qrcode_content, qrcode_path, "快手APP", compact=False, border=2)
    except TypeError as exc:
        if "unexpected keyword argument 'compact'" not in str(exc):
            raise
        kuaishou_logger.warning(_msg("😵", "检测到旧版二维码打印函数，小人切回兼容模式继续登录"))
        print_terminal_qrcode(qrcode_content, qrcode_path, "快手APP")


async def _emit_qrcode_callback(qrcode_callback, payload: dict):
    if not qrcode_callback:
        return

    callback_result = qrcode_callback(payload)
    if inspect.isawaitable(callback_result):
        await callback_result


def _build_login_result(
    success: bool,
    status: str,
    message: str,
    account_file: str,
    qrcode: dict | None = None,
    current_url: str = "",
) -> dict:
    return {
        "success": success,
        "status": status,
        "message": message,
        "account_file": str(account_file),
        "qrcode": qrcode,
        "current_url": current_url,
    }


async def _is_ks_cookie_invalid(page: Page, timeout: int = 5000) -> bool:
    try:
        await page.wait_for_selector(KUAISHOU_COOKIE_INVALID_SELECTOR, timeout=timeout)
        return True
    except Exception:
        return False


async def _extract_ks_qrcode_src(page: Page) -> str:
    login_form = page.locator("main#login-form").first
    await login_form.wait_for(state="visible", timeout=30000)

    qrcode_img = login_form.locator('div.qr-login img[alt="qrcode"]').first
    try:
        if not await qrcode_img.count() or not await qrcode_img.is_visible():
            platform_switch = login_form.locator("div.platform-switch").first
            await platform_switch.wait_for(state="visible", timeout=10000)
            await platform_switch.click()
            await asyncio.sleep(1)
    except Exception:
        platform_switch = login_form.locator("div.platform-switch").first
        await platform_switch.wait_for(state="visible", timeout=10000)
        await platform_switch.click()
        await asyncio.sleep(1)

    await qrcode_img.wait_for(state="visible", timeout=15000)

    qrcode_src = await qrcode_img.get_attribute("src")
    if not qrcode_src:
        raise RuntimeError("未获取到快手登录二维码地址")

    return qrcode_src


async def _save_ks_qrcode(page: Page, account_file: str, previous_qrcode_path: Path | None = None, qrcode_callback=None) -> dict:
    qrcode_src = await _extract_ks_qrcode_src(page)
    qrcode_path = save_data_url_image(qrcode_src, build_login_qrcode_path(account_file, suffix="ks_login_qrcode"))

    if previous_qrcode_path and previous_qrcode_path != qrcode_path:
        if remove_qrcode_file(previous_qrcode_path):
            kuaishou_logger.info(_msg("🧹", f"临时二维码文件已清理: {previous_qrcode_path}"))

    kuaishou_logger.info(_msg("🖼️", f"二维码已经准备好啦，已保存到: {qrcode_path}"))
    qrcode_content = decode_qrcode_from_path(qrcode_path)
    if qrcode_content:
        _print_ks_qrcode(qrcode_content, qrcode_path)
    else:
        kuaishou_logger.warning(_msg("😵", f"终端没法完整显示二维码，请打开 {qrcode_path} 扫码"))

    qrcode_info = {
        "image_path": str(qrcode_path),
        "image_data_url": qrcode_src,
    }
    await _emit_qrcode_callback(qrcode_callback, qrcode_info)
    return qrcode_info


async def _is_ks_qrcode_expired(page: Page) -> bool:
    expired_box = page.locator("div.qrcode-status.qrcode-status-timeout").first
    try:
        if not await expired_box.count():
            return False
        return await expired_box.is_visible()
    except Exception:
        return False


async def _is_ks_login_page_gone(page: Page) -> bool:
    try:
        login_form = page.locator("main#login-form").first
        if not await login_form.count():
            return True
        return not await login_form.is_visible()
    except Exception:
        return True


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        if LOCAL_CHROME_PATH:
            browser = await playwright.chromium.launch(headless=True, executable_path=LOCAL_CHROME_PATH)
        else:
            browser = await playwright.chromium.launch(headless=True, channel="chrome")
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto(KUAISHOU_UPLOAD_URL)
            if await _is_ks_cookie_invalid(page):
                kuaishou_logger.info(_msg("🥹", "cookie 已失效，得重新登录一下"))
                return False

            kuaishou_logger.success(_msg("🥳", "cookie 有效"))
            return True
        except Exception as exc:
            kuaishou_logger.warning(_msg("😵", f"cookie 校验时出错，按失效处理: {exc}"))
            return False
        finally:
            await browser.close()


async def ks_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless: bool = LOCAL_CHROME_HEADLESS):
    account_file = get_absolute_path(account_file, "ks_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            result = _build_login_result(False, "cookie_invalid", "cookie文件不存在或已失效", account_file)
            return result if return_detail else False
        kuaishou_logger.info(_msg("🥹", "cookie 失效了，准备重新登录快手创作者平台"))
        result = await get_ks_cookie(account_file, qrcode_callback=qrcode_callback, headless=headless)
        return result if return_detail else result["success"]

    result = _build_login_result(True, "cookie_valid", "cookie有效", account_file)
    return result if return_detail else True


async def get_ks_cookie(
    account_file,
    qrcode_callback=None,
    headless: bool = LOCAL_CHROME_HEADLESS,
    poll_interval: int = 3,
    max_checks: int = 100,
):
    if headless:
        kuaishou_logger.info(_msg("🖼️", "快手登录将以无头模式运行，小人会输出终端二维码并保存本地二维码图片"))

    async with async_playwright() as playwright:
        if LOCAL_CHROME_PATH:
            browser = await playwright.chromium.launch(headless=headless, executable_path=LOCAL_CHROME_PATH)
        else:
            browser = await playwright.chromium.launch(headless=headless, channel="chrome")
        context = await browser.new_context()
        context = await set_init_script(context)
        qrcode_path = None
        qrcode_info = None
        result = _build_login_result(False, "failed", "快手登录失败", account_file)
        try:
            page = await context.new_page()
            await page.goto(KUAISHOU_LOGIN_URL)
            kuaishou_logger.info(_msg("🧍", "请在浏览器里扫码登录快手，小人正在耐心等待"))

            qrcode_info = await _save_ks_qrcode(page, account_file, qrcode_callback=qrcode_callback)
            qrcode_path = Path(qrcode_info["image_path"])

            for _ in range(max_checks):
                if page.url.startswith(KUAISHOU_UPLOAD_URL) or await _is_ks_login_page_gone(page):
                    await context.storage_state(path=account_file)
                    if await cookie_auth(account_file):
                        kuaishou_logger.success(_msg("🥳", "快手扫码登录成功，小人开心收工"))
                        result = _build_login_result(True, "success", "快手扫码登录成功", account_file, qrcode_info, page.url)
                    else:
                        kuaishou_logger.error(_msg("😢", "快手扫码完成了，但 cookie 校验失败"))
                        result = _build_login_result(
                            False,
                            "cookie_invalid",
                            "快手扫码流程结束，但 cookie 校验失败",
                            account_file,
                            qrcode_info,
                            page.url,
                        )
                    return result

                if qrcode_info and await _is_ks_qrcode_expired(page):
                    kuaishou_logger.warning(_msg("😵", "二维码失效了，小人马上去刷新"))
                    refresh_button = page.locator("p.qrcode-refresh").first
                    if await refresh_button.count():
                        await refresh_button.click()
                        await asyncio.sleep(1)
                    qrcode_info = await _save_ks_qrcode(
                        page,
                        account_file,
                        qrcode_path,
                        qrcode_callback=qrcode_callback,
                    )
                    qrcode_path = Path(qrcode_info["image_path"])

                await asyncio.sleep(poll_interval)

            result = _build_login_result(
                False,
                "timeout",
                "等待快手扫码登录超时",
                account_file,
                qrcode_info,
                page.url,
            )
        except Exception as exc:
            result = _build_login_result(False, "failed", str(exc), account_file, current_url=page.url if "page" in locals() else "")
        finally:
            if remove_qrcode_file(qrcode_path):
                kuaishou_logger.info(_msg("🧹", f"临时二维码文件已清理: {qrcode_path}"))
            if not result["success"]:
                kuaishou_logger.error(_msg("😢", f"登录失败: {result['message']}"))
            await context.close()
            await browser.close()

    return result


class KSBaseUploader(BaseVideoUploader):
    def __init__(
        self,
        publish_date: datetime | int,
        account_file,
        publish_strategy: str | None = None,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        self.publish_date = publish_date
        self.account_file = str(account_file)
        self.publish_strategy = publish_strategy
        self.debug = debug
        self.headless = headless
        self.local_executable_path = LOCAL_CHROME_PATH
        self.date_format = "%Y-%m-%d %H:%M"

    async def validate_base_args(self):
        if not os.path.exists(self.account_file):
            raise RuntimeError(f"cookie文件不存在，请先完成快手登录: {self.account_file}")
        if not await cookie_auth(self.account_file):
            raise RuntimeError(f"cookie文件已失效，请先完成快手登录: {self.account_file}")

        if self.publish_strategy is None:
            self.publish_strategy = (
                KUAISHOU_PUBLISH_STRATEGY_SCHEDULED
                if self.publish_date != 0
                else KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE
            )

        if self.publish_strategy not in {
            KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE,
            KUAISHOU_PUBLISH_STRATEGY_SCHEDULED,
        }:
            raise ValueError(f"不支持的发布策略: {self.publish_strategy}")

        if self.publish_strategy == KUAISHOU_PUBLISH_STRATEGY_SCHEDULED:
            self.publish_date = self.validate_publish_date(self.publish_date)
        else:
            self.publish_date = 0

    async def set_schedule_time(self, page: Page, publish_date: datetime):
        kuaishou_logger.info(_msg("🕒", "小人准备设置定时发布时间"))
        publish_date_str = publish_date.strftime("%Y-%m-%d %H:%M:%S")

        # 1. 切换到"定时发布"radio (用文本匹配更稳)
        await page.locator('label.ant-radio-wrapper').filter(has_text="定时发布").click()
        await asyncio.sleep(2)

        # 2. 点击 picker 打开下拉面板
        await page.locator('input[placeholder="选择日期时间"]').click()
        await asyncio.sleep(1)

        # 3. 用 React 兼容的方式直接设置 input 的 value
        #    (ant-design DatePicker 是 controlled component, 必须用 native setter + bubbling event)
        js_code = """
        (newValue) => {
            const input = document.querySelector('input[placeholder="选择日期时间"]');
            if (!input) return false;
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeSetter.call(input, newValue);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        """
        ok = await page.evaluate(js_code, publish_date_str)
        if not ok:
            kuaishou_logger.error("❌ 找不到时间选择器输入框")
            return

        await asyncio.sleep(1)
        # 4. 按 Enter 确认
        await page.keyboard.press("Enter")
        await asyncio.sleep(2)
        kuaishou_logger.info(f"✅ 定时发布时间已设置为 {publish_date_str}")

    async def close_guide_overlay(self, page: Page) -> bool:
        joyride_tooltip = page.locator('div[id^="react-joyride-step"] div[role="alertdialog"]')

        # 判断是否显示
        if await joyride_tooltip.count() > 0 and await joyride_tooltip.first.is_visible():
            print("检测到 Joyride 引导遮罩，正在关闭...")

            # 点击关闭按钮（X），使用多个可靠特征
            close_button = page.locator('div[role="alertdialog"]').locator(
                '[aria-label="Skip"], [data-action="skip"], button[title="Skip"]'
            )

            try:
                await close_button.click(force=True, timeout=5000)
            except Exception as exc:
                kuaishou_logger.warning(_msg("😵", f"Joyride 关闭按钮点击失败，准备兜底清理遮罩: {exc}"))

            # 等待遮罩消失；如果平台动画或按钮状态异常，直接移除遮罩，避免挡住后续点击。
            try:
                await joyride_tooltip.wait_for(state="hidden", timeout=5000)
            except Exception as exc:
                kuaishou_logger.warning(_msg("😵", f"Joyride 遮罩未自动消失，准备兜底清理: {exc}"))
                await page.evaluate(
                    """() => {
                        document.querySelectorAll('[id^="react-joyride-step"], .react-joyride__overlay').forEach((node) => node.remove());
                        document.body.style.overflow = '';
                    }"""
                )
                await page.wait_for_timeout(500)

            print("✅ 已关闭 Joyride 遮罩")
        else:
            print("未检测到 Joyride 遮罩，继续执行")


class KSVideo(KSBaseUploader):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime | int,
        account_file,
        publish_strategy: str | None = None,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
        thumbnail_path=None,
        desc: str | None = None,
        promotion_task_title: str = "",
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
        )
        self.title = title
        self.file_path = file_path
        self.tags = tags or []
        self.thumbnail_path = thumbnail_path
        self.desc = desc or ""
        self.promotion_task_title = (promotion_task_title or "").strip()

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("快手视频上传时，title 是必须的")
        self.file_path = str(self.validate_video_file(self.file_path))
        if self.thumbnail_path:
            self.thumbnail_path = str(self.validate_image_file(self.thumbnail_path))

    async def handle_upload_error(self, page: Page):
        kuaishou_logger.warning(_msg("😵", "视频上传摔了一跤，小人马上重新上传"))
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def set_thumbnail(self, page: Page):
        if not self.thumbnail_path:
            return

        kuaishou_logger.info(_msg("🖼️", "小人准备设置封面"))

        cover_label = page.locator("span").filter(has_text="封面设置")
        await cover_label.wait_for(state="visible", timeout=30000)
        await cover_label.locator("xpath=../following-sibling::div[1]").locator('div').nth(0).click()

        modal = page.locator('div[role="document"].ant-modal')
        await modal.wait_for(state="visible", timeout=30000)

        upload_cover_tab = modal.get_by_text("上传封面", exact=True)
        await upload_cover_tab.wait_for(state="visible", timeout=10000)
        await upload_cover_tab.click()

        file_input = modal.locator('input[type="file"]')
        await file_input.wait_for(state="attached", timeout=30000)
        await file_input.set_input_files(self.thumbnail_path)
        await asyncio.sleep(1)

        confirm_button = modal.get_by_role("button", name="确认", exact=True)
        await confirm_button.wait_for(state="visible", timeout=10000)
        await confirm_button.click()

        await modal.wait_for(state="hidden", timeout=30000)
        kuaishou_logger.success(_msg("🥳", "封面已经设置完成"))

    @staticmethod
    def _normalize_dropdown_text(text: str) -> str:
        return " ".join((text or "").split())

    @staticmethod
    def _promotion_task_title_candidates(text: str) -> list[str]:
        normalized = KSVideo._normalize_dropdown_text(text).strip("《》「」\"' ")
        if not normalized:
            return []

        candidates = [normalized]
        suffixes = [
            "剧情精剪",
            "精彩剪辑",
            "高光切片",
            "引流版本",
            "引流版",
            "推广版本",
            "推广版",
            "宣传版本",
            "宣传版",
            "短剧剪辑",
            "剪辑版本",
            "剪辑版",
            "精剪版本",
            "精剪版",
            "精剪",
            "切片",
        ]
        for suffix in suffixes:
            pattern = rf"[\s_\-·|｜]*{re.escape(suffix)}$"
            stripped = re.sub(pattern, "", normalized).strip("《》「」\"' ")
            if stripped and stripped != normalized:
                candidates.append(stripped)

        first_part = re.split(r"[\s_\-·|｜]+", normalized, maxsplit=1)[0].strip("《》「」\"' ")
        if first_part and first_part != normalized:
            candidates.append(first_part)

        unique_candidates: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in unique_candidates:
                unique_candidates.append(candidate)
        return unique_candidates

    async def _get_author_service_selects(self, page: Page) -> list[dict[str, Any]]:
        result = await page.evaluate(
            """() => {
                const visible = (node) => {
                    if (!node || !(node instanceof HTMLElement)) return false;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none';
                };
                const textOf = (node) => (node?.innerText || node?.textContent || '').trim();
                const label = [...document.querySelectorAll('*')]
                    .filter((node) => textOf(node) === '作者服务' && visible(node))
                    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
                const allSelects = [...document.querySelectorAll('.ant-select')].map((node, index) => {
                    const rect = node.getBoundingClientRect();
                    return {
                        index,
                        text: textOf(node),
                        className: node.className || '',
                        disabled: String(node.className || '').includes('ant-select-disabled')
                            || node.getAttribute('aria-disabled') === 'true',
                        rect: {
                            top: rect.top,
                            left: rect.left,
                            width: rect.width,
                            height: rect.height,
                        },
                        visible: visible(node),
                        afterLabel: label ? Boolean(label.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING) : false,
                    };
                });
                if (!label) {
                    return allSelects.filter((item) => item.visible);
                }
                const labelRect = label.getBoundingClientRect();
                const nearby = allSelects.filter((item) => {
                    return item.visible
                        && item.rect.top >= labelRect.top - 40
                        && item.rect.top <= labelRect.top + 260
                        && item.rect.left >= labelRect.left - 40;
                });
                if (nearby.length >= 2) return nearby;
                return allSelects.filter((item) => item.visible && item.afterLabel).slice(0, 4);
            }"""
        )
        return result or []

    async def _promotion_task_diagnostics(self, page: Page) -> str:
        try:
            selects = await self._get_author_service_selects(page)
        except Exception as exc:
            selects = [{"error": str(exc)}]

        try:
            dropdowns = await page.evaluate(
                """() => [...document.querySelectorAll('.ant-select-dropdown')].map((node) => {
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return {
                        text: (node.innerText || node.textContent || '').trim().slice(0, 500),
                        className: node.className || '',
                        visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
                    };
                })"""
            )
        except Exception as exc:
            dropdowns = [{"error": str(exc)}]

        select_summary = "; ".join(
            f"#{item.get('index')} text={item.get('text', '')!r} class={item.get('className', '')!r} disabled={item.get('disabled')}"
            for item in selects[:6]
        )
        dropdown_summary = "; ".join(
            f"visible={item.get('visible')} text={item.get('text', '')!r} class={item.get('className', '')!r}"
            for item in dropdowns[:4]
        )
        return f"作者服务下拉框: {select_summary or '未找到'}；页面下拉层: {dropdown_summary or '未找到'}"

    async def _author_service_select_locator(self, page: Page, ordinal: int, label: str) -> Locator:
        selects = await self._get_author_service_selects(page)
        if len(selects) <= ordinal:
            diagnostics = await self._promotion_task_diagnostics(page)
            raise RuntimeError(f"未找到快手作者服务的{label}下拉框。{diagnostics}")
        return page.locator(".ant-select").nth(int(selects[ordinal]["index"]))

    async def _visible_ant_dropdown(self, page: Page, timeout: int = 10000) -> Locator:
        dropdown = page.locator(".ant-select-dropdown:visible").last
        await dropdown.wait_for(state="visible", timeout=timeout)
        return dropdown

    async def _open_ant_select(self, page: Page, select: Locator, label: str) -> Locator:
        await select.scroll_into_view_if_needed(timeout=5000)
        selector = select.locator(".ant-select-selector").first
        input_box = select.locator("input").first

        last_error: Exception | None = None
        click_targets = [selector, input_box, select]
        for target in click_targets:
            for force in (False, True):
                try:
                    await target.click(timeout=5000, force=force)
                    return await self._visible_ant_dropdown(page, timeout=5000)
                except Exception as exc:
                    last_error = exc
                    await page.wait_for_timeout(300)

        try:
            await select.evaluate(
                """(root) => {
                    const target = root.querySelector('.ant-select-selector') || root;
                    const input = root.querySelector('input');
                    input?.focus?.();
                    for (const type of ['mousedown', 'mouseup', 'click']) {
                        target.dispatchEvent(new MouseEvent(type, {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            button: 0,
                        }));
                    }
                    return true;
                }"""
            )
            return await self._visible_ant_dropdown(page, timeout=5000)
        except Exception as exc:
            last_error = exc

        diagnostics = await self._promotion_task_diagnostics(page)
        raise RuntimeError(f"无法打开快手{label}下拉框: {last_error}. {diagnostics}")

    async def _try_open_ant_select(self, page: Page, select: Locator, label: str, timeout: int = 2000) -> Locator | None:
        try:
            return await self._open_ant_select(page, select, label)
        except Exception as exc:
            kuaishou_logger.warning(_msg("😵", f"打开快手{label}下拉框未立即成功，准备使用搜索输入兜底: {exc}"))
            try:
                input_box = select.locator("input").first
                await input_box.click(timeout=3000, force=True)
                await page.keyboard.press("ArrowDown")
                dropdown = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden), .ant-select-dropdown:visible").last
                await dropdown.wait_for(state="visible", timeout=timeout)
                return dropdown
            except Exception:
                return None

    async def _click_locator_safely(self, page: Page, locator: Locator, label: str) -> bool:
        try:
            await locator.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        for force in (False, True):
            try:
                await locator.click(timeout=3000, force=force)
                await page.wait_for_timeout(500)
                return True
            except Exception:
                pass

        try:
            box = await locator.bounding_box(timeout=3000)
            if box and box["width"] > 0 and box["height"] > 0:
                await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                await page.wait_for_timeout(500)
                return True
        except Exception as exc:
            kuaishou_logger.warning(_msg("😵", f"{label}坐标点击失败: {exc}"))

        return False

    async def _click_dropdown_option_from_page_dom(self, page: Page, text: str, label: str, exact: bool = True) -> bool:
        target_text = self._normalize_dropdown_text(text)
        dom_match = await page.evaluate(
            """(payload) => {
                const target = payload.target;
                const exact = payload.exact;
                const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                const visible = (node) => {
                    if (!node || !(node instanceof HTMLElement)) return false;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none';
                };
                const matchedText = (value) => {
                    const optionText = normalize(value);
                    if (!optionText) return false;
                    return exact ? optionText === target || optionText.includes(target) : optionText.includes(target);
                };
                const clickableOf = (node) => node.closest?.(
                    '.ant-select-item-option:not(.ant-select-item-option-disabled), .ant-select-item:not(.ant-select-item-option-disabled), [role="option"]'
                ) || node;
                const dropdowns = [...document.querySelectorAll('.ant-select-dropdown')];
                for (const dropdown of dropdowns) {
                    if (!visible(dropdown) || dropdown.className.includes('ant-select-dropdown-hidden')) continue;
                    const specificOptions = [
                        ...dropdown.querySelectorAll(
                            '.ant-select-item-option:not(.ant-select-item-option-disabled), [role="option"], .ant-select-item:not(.ant-select-item-option-disabled)'
                        )
                    ];
                    const broadOptions = [
                        ...dropdown.querySelectorAll('[title], [aria-label], li, div, span')
                    ]
                        .filter((node) => node !== dropdown && !specificOptions.includes(node))
                        .sort((a, b) => {
                            const aRect = a.getBoundingClientRect();
                            const bRect = b.getBoundingClientRect();
                            const aText = normalize(a.innerText || a.textContent || '');
                            const bText = normalize(b.innerText || b.textContent || '');
                            return (aRect.width * aRect.height) - (bRect.width * bRect.height)
                                || aText.length - bText.length;
                        });

                    for (const option of [...specificOptions, ...broadOptions]) {
                        const optionText = option.getAttribute('title')
                            || option.getAttribute('label')
                            || option.getAttribute('aria-label')
                            || option.innerText
                            || option.textContent
                            || '';
                        if (!matchedText(optionText)) continue;
                        const clickable = clickableOf(option);
                        if (!visible(clickable)) continue;
                        clickable.scrollIntoView?.({ block: 'nearest' });
                        const rect = clickable.getBoundingClientRect();
                        const point = {
                            x: rect.left + rect.width / 2,
                            y: rect.top + rect.height / 2,
                        };
                        const hit = document.elementFromPoint(point.x, point.y);
                        if (!hit || (!clickable.contains(hit) && !hit.closest?.('.ant-select-dropdown'))) continue;
                        return {
                            text: normalize(optionText),
                            className: clickable.className || '',
                            dropdownClassName: dropdown.className || '',
                            visible: visible(clickable),
                            rect: {
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height,
                            },
                            clickPoint: point,
                        };
                    }
                }
                return null;
            }""",
            {"target": target_text, "exact": exact},
        )
        if dom_match:
            kuaishou_logger.info(
                _msg(
                    "🧩",
                    f"{label}使用页面 DOM 事件点击选项: {dom_match.get('text')} "
                    f"class={dom_match.get('className')} dropdown={dom_match.get('dropdownClassName')}",
                )
            )
            click_point = dom_match.get("clickPoint") or {}
            x = click_point.get("x")
            y = click_point.get("y")
            if x is not None and y is not None:
                await page.mouse.click(float(x), float(y))
            else:
                raise RuntimeError(f"{label}找到了选项但没有可点击坐标: {dom_match}")
            await page.wait_for_timeout(1000)
            return True
        return False

    async def _click_dropdown_option(self, page: Page, dropdown: Locator, text: str, label: str, exact: bool = True) -> bool:
        options = dropdown.locator(".ant-select-item-option:not(.ant-select-item-option-disabled)")
        count = await options.count()
        target_text = self._normalize_dropdown_text(text)
        partial_match = None

        for index in range(count):
            option = options.nth(index)
            option_text = self._normalize_dropdown_text(await option.inner_text(timeout=3000))
            if exact and option_text == target_text:
                return await self._click_locator_safely(page, option, label)
            if not exact and target_text in option_text:
                return await self._click_locator_safely(page, option, label)
            if target_text in option_text and partial_match is None:
                partial_match = option

        if exact and partial_match is not None:
            return await self._click_locator_safely(page, partial_match, label)

        dom_match = await dropdown.evaluate(
            """(root, payload) => {
                const target = payload.target;
                const exact = payload.exact;
                const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                const visible = (node) => {
                    if (!node || !(node instanceof HTMLElement)) return false;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && style.pointerEvents !== 'none';
                };
                const candidates = [
                    ...root.querySelectorAll('[role="option"], .ant-select-item, .ant-select-item-option, li, div, span')
                ].filter(visible);

                for (const node of candidates) {
                    const nodeText = normalize(node.innerText || node.textContent || '');
                    if (!nodeText) continue;
                    const matched = exact ? nodeText === target || nodeText.includes(target) : nodeText.includes(target);
                    if (!matched) continue;
                    const clickable = node.closest('.ant-select-item-option, .ant-select-item, [role="option"]') || node;
                    if (!visible(clickable)) continue;
                    const rect = clickable.getBoundingClientRect();
                    return {
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2,
                        text: nodeText,
                        className: clickable.className || '',
                    };
                }
                return null;
            }""",
            {"target": target_text, "exact": exact},
        )
        if dom_match:
            kuaishou_logger.info(
                _msg(
                    "🧩",
                    f"{label}使用 DOM 坐标点击选项: {dom_match.get('text')} class={dom_match.get('className')}",
                )
            )
            await page.mouse.click(float(dom_match["x"]), float(dom_match["y"]))
            await page.wait_for_timeout(700)
            return True

        if await self._click_dropdown_option_from_page_dom(page, text, label, exact=exact):
            return True

        visible_text = await self._visible_dropdown_text(dropdown)
        kuaishou_logger.warning(_msg("😵", f"未在{label}下拉框找到选项: {text}. 当前弹层文本: {visible_text}"))
        return False

    async def _visible_dropdown_text(self, dropdown: Locator) -> str:
        try:
            return (await dropdown.inner_text(timeout=3000)).strip()
        except Exception:
            return ""

    async def _fill_ant_select_search(self, page: Page, select: Locator, text: str) -> None:
        await select.scroll_into_view_if_needed(timeout=5000)
        search_input = select.locator("input").first
        await search_input.click(timeout=5000, force=True)
        try:
            await search_input.fill(text, timeout=3000)
        except Exception:
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(text)
        await page.wait_for_timeout(1200)

    async def _select_promotion_task_option(self, page: Page, task_select: Locator, task_title: str) -> bool:
        candidates = self._promotion_task_title_candidates(task_title)
        if not candidates:
            return False

        kuaishou_logger.info(_msg("🧩", f"快手变现任务匹配候选: {' / '.join(candidates)}"))

        task_dropdown = await self._try_open_ant_select(page, task_select, "变现任务")
        if task_dropdown:
            for candidate in candidates:
                if await self._click_dropdown_option(page, task_dropdown, candidate, "变现任务"):
                    return True
                if await self._click_dropdown_option_from_page_dom(page, candidate, "变现任务"):
                    return True

        for candidate in candidates:
            await self._fill_ant_select_search(page, task_select, candidate)
            try:
                task_dropdown = await self._visible_ant_dropdown(page, timeout=8000)
            except Exception:
                task_dropdown = await self._try_open_ant_select(page, task_select, "变现任务")

            if await self._click_dropdown_option_from_page_dom(page, candidate, "变现任务"):
                return True

            if not task_dropdown:
                continue

            if await self._click_dropdown_option(page, task_dropdown, candidate, "变现任务"):
                return True
            if await self._click_dropdown_option(page, task_dropdown, candidate, "变现任务", exact=False):
                return True

        return False

    async def set_promotion_task(self, page: Page):
        task_title = self.promotion_task_title
        if not task_title:
            return

        kuaishou_logger.info(_msg("🧩", f"小人准备关联快手变现任务: {task_title}"))
        author_service_label = page.get_by_text("作者服务", exact=True)
        await author_service_label.wait_for(state="visible", timeout=30000)

        service_select = await self._author_service_select_locator(page, 0, "作者服务类型")
        service_dropdown = await self._try_open_ant_select(page, service_select, "作者服务类型")
        service_option_clicked = False
        if service_dropdown:
            service_option_clicked = await self._click_dropdown_option(page, service_dropdown, "关联变现任务", "作者服务类型")
        if not service_option_clicked:
            service_option_clicked = await self._click_dropdown_option_from_page_dom(
                page,
                "关联变现任务",
                "作者服务类型",
            )
        if not service_option_clicked:
            visible_text = await self._visible_dropdown_text(service_dropdown) if service_dropdown else ""
            raise RuntimeError(f"未找到快手作者服务选项: 关联变现任务. 当前可见选项: {visible_text}")

        await page.wait_for_function(
            """() => {
                const visible = (node) => {
                    if (!node || !(node instanceof HTMLElement)) return false;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none';
                };
                const textOf = (node) => (node?.innerText || node?.textContent || '').trim();
                const authorNode = [...document.querySelectorAll('*')]
                    .filter((node) => textOf(node) === '作者服务' && visible(node))[0];
                if (!authorNode) return false;
                const authorRect = authorNode.getBoundingClientRect();
                const selects = [...document.querySelectorAll('.ant-select')].filter((select) => {
                    const rect = select.getBoundingClientRect();
                    return visible(select)
                        && rect.top >= authorRect.top - 40
                        && rect.top <= authorRect.top + 260
                        && rect.left >= authorRect.left - 40;
                });
                return selects[1] && !selects[1].className.includes('ant-select-disabled');
            }""",
            timeout=10000,
        )

        task_select = await self._author_service_select_locator(page, 1, "变现任务")
        option_clicked = await self._select_promotion_task_option(page, task_select, task_title)
        if not option_clicked:
            diagnostics = await self._promotion_task_diagnostics(page)
            candidates = " / ".join(self._promotion_task_title_candidates(task_title))
            raise RuntimeError(f"未找到快手变现任务: {task_title}. 已尝试候选: {candidates}. {diagnostics}")

        kuaishou_logger.success(_msg("🥳", f"快手变现任务已关联: {task_title}"))

    async def try_set_promotion_task(self, page: Page):
        if not self.promotion_task_title:
            return
        try:
            await self.set_promotion_task(page)
        except Exception as exc:
            raise RuntimeError(f"快手变现任务关联失败，已停止发布: {exc}") from exc

    async def upload(self, playwright: Playwright) -> None:
        kuaishou_logger.info(_msg("🧍", "小人先检查 cookie、视频文件、封面和发布时间"))
        await self.validate_upload_args()
        kuaishou_logger.info(_msg("🥳", "上传前检查通过"))

        if self.local_executable_path:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                executable_path=self.local_executable_path,
            )
        else:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                channel="chrome",
            )
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)

        upload_success = False
        try:
            page = await context.new_page()
            await page.goto(KUAISHOU_UPLOAD_URL)
            kuaishou_logger.info(_msg("🏃", f"小人开始搬运视频: {self.title}.mp4"))
            kuaishou_logger.info(_msg("🧭", "小人正在赶往快手上传主页"))
            await page.wait_for_url(KUAISHOU_UPLOAD_URL_PATTERN)

            upload_button = page.locator("button[class^='_upload-btn']")
            await upload_button.wait_for(state="visible", timeout=10000)

            async with page.expect_file_chooser() as fc_info:
                await upload_button.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(self.file_path)

            await asyncio.sleep(2)

            know_button = page.locator('button[type="button"] span:text("我知道了")').first
            try:
                if await know_button.count() and await know_button.is_visible():
                    await know_button.click()
            except Exception:
                pass

            await self.close_guide_overlay(page)

            kuaishou_logger.info(_msg("✍️", "小人开始填描述和话题"))
            await page.get_by_text("描述").locator("xpath=following-sibling::div").click()
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(self.desc or self.title)
            await page.keyboard.press("Enter")

            for index, tag in enumerate(self.tags[:3], start=1):
                kuaishou_logger.info(_msg("🏷️", f"小人正在添加第 {index} 个话题: #{tag}"))
                await page.keyboard.type(f"#{tag} ")
                await asyncio.sleep(2)

            max_retries = 60
            retry_count = 0
            while retry_count < max_retries:
                try:
                    number = await page.locator("text=上传中").count()
                    if number == 0:
                        kuaishou_logger.success(_msg("🥳", "视频已经传完啦"))
                        break

                    if retry_count % 5 == 0:
                        kuaishou_logger.info(_msg("🏃", "小人正在努力上传视频"))

                    if await page.locator("text=上传失败").count():
                        await self.handle_upload_error(page)

                    await asyncio.sleep(2)
                except Exception as exc:
                    kuaishou_logger.warning(_msg("😵", f"检查上传状态时出错，小人继续重试: {exc}"))
                    await asyncio.sleep(2)
                retry_count += 1

            if retry_count == max_retries:
                kuaishou_logger.warning(_msg("😵", "超过最大重试次数，视频上传可能未完成"))

            await self.set_thumbnail(page)
            await self.set_promotion_task(page)

            if self.publish_strategy == KUAISHOU_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
                await self.set_schedule_time(page, self.publish_date)

            while True:
                try:
                    publish_button = page.get_by_text("发布", exact=True)
                    if await publish_button.count() > 0:
                        await publish_button.click()

                    await asyncio.sleep(1)
                    confirm_button = page.get_by_text("确认发布")
                    if await confirm_button.count() > 0:
                        await confirm_button.click()

                    await page.wait_for_url(KUAISHOU_MANAGE_URL_PATTERN, timeout=5000)
                    kuaishou_logger.success(_msg("🥳", "视频发布成功，小人开心收工"))
                    break
                except Exception as exc:
                    kuaishou_logger.info(_msg("🏃", f"小人正在冲刺发布视频: {exc}"))
                    if self.debug:
                        await page.screenshot(full_page=True)
                    await asyncio.sleep(1)

            upload_success = True
        finally:
            if upload_success:
                await context.storage_state(path=self.account_file)
                kuaishou_logger.success(_msg("🥳", "cookie 更新完毕"))
                await asyncio.sleep(2)
            await context.close()
            await browser.close()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


class KSNote(KSBaseUploader):
    def __init__(
        self,
        image_paths,
        note,
        tags,
        publish_date: datetime | int,
        account_file,
        title: str | None = None,
        publish_strategy: str | None = None,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
        )
        self.image_paths = image_paths
        self.note = note or ""
        self.title = title or (self.note[:20] if self.note else "")
        self.tags = tags or []

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("快手图文上传时，title 是必须的")
        if not self.image_paths:
            raise ValueError("快手图文上传时，图片是必须的")

        if isinstance(self.image_paths, (str, Path)):
            self.image_paths = [self.image_paths]

        normalized_image_paths = []
        for image_path in self.image_paths:
            normalized_image_paths.append(str(self.validate_image_file(image_path)))
        self.image_paths = normalized_image_paths

    async def upload_note_content(self, page: Page) -> None:
        kuaishou_logger.info(_msg("🏃", f"小人开始搬运图文，共 {len(self.image_paths)} 张图片"))
        kuaishou_logger.info(_msg("🔀", "小人正在切换到图文发布"))
        await page.locator('div[role="tablist"] div[role="tab"]:has-text("图文")').click()
        await page.wait_for_timeout(1000)

        kuaishou_logger.info(_msg("📤", "小人正在上传图片"))
        upload_button = page.locator("button[class^='_upload-btn']").filter(has_text="上传图片")
        await upload_button.wait_for(state="visible", timeout=10000)

        async with page.expect_file_chooser() as fc_info:
            await upload_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.image_paths)

        know_button = page.locator('button[type="button"] span:text("我知道了")').first
        try:
            if await know_button.count() and await know_button.is_visible():
                await know_button.click()
        except Exception:
            pass

        await self.close_guide_overlay(page)

        kuaishou_logger.info(_msg("✍️", "小人开始填写图文内容和话题"))
        await page.get_by_text("描述").locator("xpath=following-sibling::div").click()
        await page.keyboard.press("Backspace")
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")
        await page.keyboard.type(self.note)
        await page.keyboard.press("Enter")

        for index, tag in enumerate(self.tags[:3], start=1):
            kuaishou_logger.info(_msg("🏷️", f"小人正在添加第 {index} 个话题: #{tag}"))
            await page.keyboard.type(f"#{tag} ")
            await asyncio.sleep(2)

        max_retries = 60
        retry_count = 0
        while retry_count < max_retries:
            try:
                number = await page.locator("text=上传中").count()
                if number == 0:
                    kuaishou_logger.success(_msg("🥳", "图文素材已经传完啦"))
                    break

                if retry_count % 5 == 0:
                    kuaishou_logger.info(_msg("🏃", "小人正在努力上传图文素材"))

                if await page.locator("text=上传失败").count():
                    kuaishou_logger.warning(_msg("😵", "图文素材上传摔了一跤，小人马上重新上传"))
                    await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.image_paths)

                await asyncio.sleep(2)
            except Exception as exc:
                kuaishou_logger.warning(_msg("😵", f"检查图文上传状态时出错，小人继续重试: {exc}"))
                await asyncio.sleep(2)
            retry_count += 1

        if retry_count == max_retries:
            kuaishou_logger.warning(_msg("😵", "超过最大重试次数，图文上传可能未完成"))

        if self.publish_strategy == KUAISHOU_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        while True:
            try:
                publish_button = page.get_by_text("发布", exact=True)
                if await publish_button.count() > 0:
                    await publish_button.click()

                await asyncio.sleep(1)
                confirm_button = page.get_by_text("确认发布")
                if await confirm_button.count() > 0:
                    await confirm_button.click()

                await page.wait_for_url(KUAISHOU_MANAGE_URL_PATTERN, timeout=5000)
                kuaishou_logger.success(_msg("🥳", "图文发布成功，小人开心收工"))
                break
            except Exception as exc:
                kuaishou_logger.info(_msg("🏃", f"小人正在冲刺发布图文: {exc}"))
                if self.debug:
                    await page.screenshot(full_page=True)
                await asyncio.sleep(1)

    async def upload(self, playwright: Playwright) -> None:
        kuaishou_logger.info(_msg("🧍", "小人先检查 cookie、图片和发布时间"))
        await self.validate_upload_args()
        kuaishou_logger.info(_msg("🥳", "图文上传前检查通过"))

        if self.local_executable_path:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                executable_path=self.local_executable_path,
            )
        else:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                channel="chrome",
            )
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)

        upload_success = False
        try:
            page = await context.new_page()
            await page.goto(KUAISHOU_UPLOAD_URL)
            kuaishou_logger.info(_msg("🧭", "小人正在赶往快手图文发布页"))
            await page.wait_for_url(KUAISHOU_UPLOAD_URL_PATTERN)

            await self.upload_note_content(page)
            upload_success = True
        finally:
            if upload_success:
                await context.storage_state(path=self.account_file)
                kuaishou_logger.success(_msg("🥳", "cookie 更新完毕"))
                await asyncio.sleep(2)
            await context.close()
            await browser.close()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
