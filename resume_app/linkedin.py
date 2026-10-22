"""Visible, user-authenticated LinkedIn DOM traversal, without private APIs."""

import logging
import re
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import ValidationError
from selenium import webdriver
from selenium.common.exceptions import (
    InvalidSessionIdException, NoSuchWindowException, StaleElementReferenceException,
    TimeoutException, WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from resume_app.errors import AppError, TaskCancelled
from resume_app.models import JobPost
from utils.browser import BrowserConfigurationError, start_chrome


_LOGGER = logging.getLogger(__name__)
RECOMMENDED_URL = "https://www.linkedin.com/jobs/collections/recommended/"
LIST_SELECTOR = ".scaffold-layout__list, .jobs-search-results-list"
PANEL_SELECTOR = ".scaffold-layout__detail"
DESCRIPTION_SELECTOR = (
    "#job-details, .jobs-description__content, "
    ".jobs-description-content__text, .show-more-less-html__markup"
)
CARD_SELECTOR = (
    ".scaffold-layout__list [data-job-id], "
    ".scaffold-layout__list [data-occludable-job-id], "
    ".scaffold-layout__list a[href*='/jobs/view/'], "
    ".jobs-search-results-list [data-job-id]"
)


def job_id_from_url(url: str) -> str | None:
    parts = urlsplit(urljoin("https://www.linkedin.com", url))
    if parts.hostname not in {"www.linkedin.com", "linkedin.com"}:
        return None
    match = re.search(r"/jobs/view/(?:[^/]*-)?(\d{1,30})/?$", parts.path)
    return match.group(1) if match else None


def check_cancelled(cancel: Event) -> None:
    if cancel.is_set():
        raise TaskCancelled()


@dataclass
class Candidate:
    linkedin_id: str
    post: JobPost | None = None
    error: str | None = None


class LinkedInLoginRequired(AppError):
    pass


def clean_application_url(url: str) -> str:
    JobPost.validate_application_url(url)
    parts = urlsplit(url)
    amazon = parts.hostname == "amazon.jobs" or (parts.hostname or "").endswith(".amazon.jobs")
    query = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and not (amazon and key.lower() in {"cmpid", "ss"})
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class LinkedInBrowser:
    def __init__(
        self, profile_root: Path, chrome_path: str | None = None,
        chromedriver_path: str | None = None,
    ) -> None:
        self.profile_root = profile_root
        self.chrome_path = chrome_path
        self.chromedriver_path = chromedriver_path
        self.driver: webdriver.Chrome | None = None

    def open(self, user_id: str) -> None:
        if self.driver is not None:
            try:
                if self.driver.window_handles:
                    self.driver.get("https://www.linkedin.com/")
                    return
            except WebDriverException:
                _LOGGER.warning("Previously opened browser session is no longer usable")
            self.close()
        try:
            self.driver = start_chrome(
                user_data_dir=self.profile_root / user_id,
                chrome_path=self.chrome_path,
                chromedriver_path=self.chromedriver_path,
            )
        except BrowserConfigurationError as error:
            raise AppError(str(error), 503) from error
        self.driver.get("https://www.linkedin.com/")

    def close(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except WebDriverException:
                _LOGGER.warning("Chrome session was already closed during cleanup")
            finally:
                self.driver = None

    def _require_login(self, driver: webdriver.Chrome) -> None:
        path = urlsplit(driver.current_url).path
        if any(part in path for part in ("/login", "/checkpoint", "/authwall", "/uas/")):
            raise LinkedInLoginRequired("请先在 Chrome 中手动完成 LinkedIn 登录或安全验证，再重试")
        if driver.find_elements(By.CSS_SELECTOR, "input#username, input#password"):
            raise LinkedInLoginRequired("LinkedIn 尚未登录，请在打开的 Chrome 中手动登录")

    def _visible_text(self, scope: webdriver.Chrome | WebElement, selectors: str) -> str:
        for element in scope.find_elements(By.CSS_SELECTOR, selectors):
            if element.is_displayed() and element.text.strip():
                return element.text.strip()
        return ""

    def _panel_job_id(self, driver: webdriver.Chrome) -> str | None:
        for link in driver.find_elements(By.CSS_SELECTOR, f"{PANEL_SELECTOR} h1 a[href*='/jobs/view/']"):
            if link.is_displayed():
                return job_id_from_url(link.get_attribute("href") or "")
        return None

    def _select_job(self, driver: webdriver.Chrome, linkedin_id: str) -> None:
        selector = (
            f'.scaffold-layout__list [data-job-id="{linkedin_id}"], '
            f'.scaffold-layout__list [data-occludable-job-id="{linkedin_id}"], '
            f'.jobs-search-results-list [data-job-id="{linkedin_id}"]'
        )
        row = WebDriverWait(driver, 15).until(
            lambda browser: next(iter(browser.find_elements(By.CSS_SELECTOR, selector)), False)
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'nearest'});", row)
        clickable = (
            f'.scaffold-layout__list [data-job-id="{linkedin_id}"], '
            f'.scaffold-layout__list a[href*="/jobs/view/{linkedin_id}/"], '
            f'.jobs-search-results-list [data-job-id="{linkedin_id}"]'
        )
        def find_card(browser: webdriver.Chrome) -> WebElement | Literal[False]:
            for element in browser.find_elements(By.CSS_SELECTOR, clickable):
                if element.is_displayed() and element.is_enabled():
                    return element
            return False

        card = WebDriverWait(driver, 15).until(find_card)
        card.click()

        def ready(browser):
            self._require_login(browser)
            try:
                return (
                    self._panel_job_id(browser) == linkedin_id
                    and bool(self._visible_text(
                        browser, f"{PANEL_SELECTOR} #job-details"
                    ))
                )
            except StaleElementReferenceException:
                return False

        WebDriverWait(driver, 20).until(ready)

    def _external_application(
        self, driver: webdriver.Chrome, button: WebElement,
    ) -> dict[str, object]:
        original = driver.current_window_handle
        before = set(driver.window_handles)
        opened: str | None = None
        same_window = False
        try:
            button.click()

            def destination(browser):
                nonlocal opened, same_window
                extra = set(browser.window_handles) - before
                if len(extra) > 1:
                    raise AppError("申请入口打开多个窗口，请在浏览器中手动确认后重试")
                if extra:
                    opened = extra.pop()
                    browser.switch_to.window(opened)
                parts = urlsplit(browser.current_url)
                if parts.scheme == "https" and parts.hostname and not (
                    parts.hostname == "linkedin.com" or parts.hostname.endswith(".linkedin.com")
                ):
                    same_window = opened is None
                    return browser.current_url
                return False

            landed = WebDriverWait(driver, 25).until(destination)
            landing = clean_application_url(landed)
            driver.find_element(By.TAG_NAME, "body")
            choices: set[str] = set()
            for anchor in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
                label = (anchor.text or anchor.get_attribute("aria-label") or "").strip()
                if anchor.is_displayed() and re.fullmatch(
                    r"apply(?:\s+now|\s+for\s+this\s+job)?|立即申请|申请此职位",
                    label, re.IGNORECASE,
                ):
                    href = urljoin(driver.current_url, anchor.get_attribute("href") or "")
                    if urlsplit(href).scheme == "https":
                        choices.add(clean_application_url(href))
            application = next(iter(choices)) if len(choices) == 1 else landing
            return {
                "application_kind": "external", "application_url": application,
                "application_landing_url": landing,
                "application_url_source": (
                    "company_apply_link" if len(choices) == 1 else "external_redirect"
                ),
            }
        except TimeoutException as error:
            raise AppError(
                "外站申请入口未能打开；若 LinkedIn 显示跳转或安全确认，请手动完成后重试"
            ) from error
        finally:
            if opened is not None and opened in driver.window_handles:
                driver.switch_to.window(opened)
                driver.close()
            driver.switch_to.window(original)
            if same_window:
                driver.back()
                WebDriverWait(driver, 20).until(
                    lambda browser: browser.find_elements(By.CSS_SELECTOR, LIST_SELECTOR)
                )

    def _read_application(
        self, driver: webdriver.Chrome, panel: WebElement,
    ) -> dict[str, object]:
        for button in panel.find_elements(
            By.CSS_SELECTOR, "button.jobs-apply-button, a.jobs-apply-button"
        ):
            if not button.is_displayed() or not button.is_enabled():
                continue
            label = (button.get_attribute("aria-label") or button.text).lower()
            if any(text in label for text in ("easy apply", "轻松申请", "简易申请")):
                return {"application_kind": "easy_apply"}
            href = button.get_attribute("href")
            if href:
                address = urljoin(driver.current_url, href)
                host = urlsplit(address).hostname or ""
                if host != "linkedin.com" and not host.endswith(".linkedin.com"):
                    return {
                        "application_kind": "external",
                        "application_url": clean_application_url(address),
                        "application_landing_url": clean_application_url(address),
                        "application_url_source": "external_redirect",
                    }
            return self._external_application(driver, button)
        return {
            "application_kind": "unavailable",
            "application_error": "未找到可用申请入口；职位可能已关闭，或页面结构已变化",
        }

    def _read_panel(self, driver: webdriver.Chrome, linkedin_id: str) -> JobPost:
        if self._panel_job_id(driver) != linkedin_id:
            raise AppError("右侧职位尚未切换完成，已拒绝读取上一职位的描述")
        panel = driver.find_element(By.CSS_SELECTOR, PANEL_SELECTOR)
        description = WebDriverWait(driver, 20).until(
            lambda _browser: self._visible_text(panel, DESCRIPTION_SELECTOR)
        )
        for button in panel.find_elements(
            By.CSS_SELECTOR,
            "button.jobs-description__footer-button, button.show-more-less-html__button",
        ):
            label = button.text.strip().lower()
            expandable = button.get_attribute("aria-expanded") == "false" or any(
                text in label for text in ("show more", "see more", "显示更多", "查看更多", "展开")
            )
            if expandable and button.is_displayed() and button.is_enabled():
                button.click()
                before = description
                description = WebDriverWait(driver, 10).until(
                    lambda browser: (
                        text if (text := self._visible_text(panel, DESCRIPTION_SELECTOR)) != before
                        or button.get_attribute("aria-expanded") == "true" else False
                    )
                )
                break
        title = self._visible_text(panel, "h1")
        company = self._visible_text(
            panel, ".job-details-jobs-unified-top-card__company-name, "
            ".jobs-unified-top-card__company-name, .topcard__org-name-link"
        )
        location = self._visible_text(
            panel, ".job-details-jobs-unified-top-card__primary-description-container "
            ".tvm__text--low-emphasis, .jobs-unified-top-card__bullet, .topcard__flavor--bullet"
        )
        application = self._read_application(driver, panel)
        return JobPost.model_validate({
            "linkedin_id": linkedin_id,
            "url": f"https://www.linkedin.com/jobs/view/{linkedin_id}/",
            "title": title, "company": company, "location": location,
            "description": description, **application,
        })

    def _read_job(self, driver: webdriver.Chrome, linkedin_id: str) -> JobPost:
        self._select_job(driver, linkedin_id)
        return self._read_panel(driver, linkedin_id)

    def _card_ids(self, driver: webdriver.Chrome) -> list[str]:
        result: list[str] = []
        for element in driver.find_elements(By.CSS_SELECTOR, CARD_SELECTOR):
            identity = job_id_from_url(element.get_attribute("href") or "")
            if identity is None:
                identity = (
                    element.get_attribute("data-job-id")
                    or element.get_attribute("data-occludable-job-id") or ""
                )
            if re.fullmatch(r"\d{1,30}", identity) and identity not in result:
                result.append(identity)
        return result

    def jobs(self, limit: int, cancel: Event) -> Generator[Candidate, None, None]:
        driver = self.driver
        if driver is None:
            raise AppError("请先点击打开 Chrome，并手动登录 LinkedIn")
        check_cancelled(cancel)
        if not urlsplit(driver.current_url).path.startswith("/jobs/collections/recommended"):
            driver.get(RECOMMENDED_URL)
        self._require_login(driver)
        try:
            WebDriverWait(driver, 20).until(lambda browser: self._card_ids(browser))
        except TimeoutException as error:
            self._require_login(driver)
            raise AppError("未找到推荐职位。可能没有推荐、页面尚未加载或 LinkedIn 页面结构已变化") from error
        listing = driver.current_window_handle
        initial_signature = tuple(self._card_ids(driver))
        visited: set[str] = set()
        page_signatures = {initial_signature}
        stagnant = 0
        try:
            while len(visited) < limit:
                check_cancelled(cancel)
                driver.switch_to.window(listing)
                ids = self._card_ids(driver)
                fresh = [identity for identity in ids if identity not in visited]
                if fresh:
                    stagnant = 0
                for identity in fresh:
                    check_cancelled(cancel)
                    visited.add(identity)
                    try:
                        post = self._read_job(driver, identity)
                        check_cancelled(cancel)
                        yield Candidate(identity, post=post)
                    except (InvalidSessionIdException, NoSuchWindowException) as error:
                        raise AppError("Chrome 已关闭，请重新打开后再遍历") from error
                    except LinkedInLoginRequired:
                        raise
                    except (TimeoutException, ValidationError, AppError, ValueError) as error:
                        _LOGGER.warning("Cannot extract LinkedIn job %s: %s", identity, type(error).__name__)
                        yield Candidate(identity, error=(
                            str(error) if isinstance(error, AppError)
                            else "无法读取完整职位描述或申请链接，页面结构可能已变化"
                        ))
                    if len(visited) >= limit:
                        return
                    if cancel.wait(1.2):
                        raise TaskCancelled()
                driver.switch_to.window(listing)
                containers = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".scaffold-layout__list, .jobs-search-results-list",
                )
                if containers:
                    driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollHeight", containers[0]
                    )
                else:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                if cancel.wait(1.5):
                    raise TaskCancelled()
                if not [identity for identity in self._card_ids(driver) if identity not in visited]:
                    stagnant += 1
                if stagnant >= 3:
                    buttons = driver.find_elements(
                        By.CSS_SELECTOR,
                        ".jobs-search-pagination__button--next, "
                        ".artdeco-pagination__button--next, button[aria-label='View next page']",
                    )
                    button = next(
                        (item for item in buttons if item.is_displayed() and item.is_enabled()),
                        None,
                    )
                    if button is None:
                        return
                    before = self._card_ids(driver)
                    button.click()
                    try:
                        WebDriverWait(driver, 15).until(
                            lambda browser: self._card_ids(browser) != before
                        )
                    except TimeoutException as error:
                        raise AppError("推荐列表翻页后没有更新，请检查 Chrome 页面后重试") from error
                    signature = tuple(self._card_ids(driver))
                    if signature in page_signatures:
                        return
                    page_signatures.add(signature)
                    stagnant = 0
        finally:
            try:
                if listing in driver.window_handles:
                    driver.switch_to.window(listing)
            except WebDriverException:
                _LOGGER.warning("Browser was closed before returning to the recommended list")
