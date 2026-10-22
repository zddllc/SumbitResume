"""Persistent Chrome startup and local remote-debugging attachment."""

import argparse
import logging
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


DEFAULT_USER_DATA_DIR = Path(__file__).resolve().parents[1] / ".browser-data" / "linkedin"
_LOGGER = logging.getLogger(__name__)


class BrowserConfigurationError(ValueError):
    pass


def _validate_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("debugging_port must be between 1 and 65535")


def _driver_service(chromedriver_path: str | Path | None) -> Service:
    if chromedriver_path is None:
        return Service()
    path = Path(chromedriver_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"ChromeDriver not found: {path}")
    return Service(executable_path=str(path))


def _connect(options: Options, service: Service) -> webdriver.Chrome:
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.set_page_load_timeout(120)
        driver.set_script_timeout(60)
        driver.implicitly_wait(0)
    except WebDriverException:
        try:
            driver.quit()
        except WebDriverException:
            _LOGGER.exception("Failed to close Chrome after initialization failed")
        raise
    return driver


def start_chrome(
    *,
    user_data_dir: str | Path = DEFAULT_USER_DATA_DIR,
    chrome_path: str | Path | None = None,
    chromedriver_path: str | Path | None = None,
    headless: bool = False,
    debugging_port: int | None = None,
) -> webdriver.Chrome:
    """Start Chrome with an isolated, reusable profile; the caller owns quit()."""
    if debugging_port is not None:
        _validate_port(debugging_port)
    if sys.platform == "linux":
        if os.geteuid() == 0:
            raise BrowserConfigurationError("请用普通桌面用户启动 Chrome，不要以 root 或禁用沙箱的方式运行")
        if not headless and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise BrowserConfigurationError(
                "Linux 图形会话不可用：请在 113 的桌面用户会话启动后端，并配置 DISPLAY/XAUTHORITY"
            )
    service = _driver_service(chromedriver_path)
    options = Options()
    if chrome_path is not None:
        binary = Path(chrome_path).expanduser().resolve()
        if not binary.is_file():
            raise FileNotFoundError(f"Chrome executable not found: {binary}")
        options.binary_location = str(binary)
    profile = Path(user_data_dir).expanduser().resolve()
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        profile.chmod(0o700)
    options.add_argument(f"--user-data-dir={profile}")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-gpu")
    if headless:
        options.add_argument("--headless=new")
    elif sys.platform == "linux" and os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        options.add_argument("--ozone-platform=wayland")
    if debugging_port is not None:
        options.add_argument("--remote-debugging-address=127.0.0.1")
        options.add_argument(f"--remote-debugging-port={debugging_port}")
    return _connect(options, service)


def attach_chrome(
    debugging_port: int = 9222,
    *,
    chromedriver_path: str | Path | None = None,
) -> webdriver.Chrome:
    """Attach Selenium to an existing local Chrome remote-debugging session."""
    _validate_port(debugging_port)
    options = Options()
    options.add_experimental_option(
        "debuggerAddress", f"127.0.0.1:{debugging_port}"
    )
    return _connect(options, _driver_service(chromedriver_path))


@contextmanager
def chrome_session(
    *,
    user_data_dir: str | Path = DEFAULT_USER_DATA_DIR,
    chrome_path: str | Path | None = None,
    chromedriver_path: str | Path | None = None,
    headless: bool = False,
    debugging_port: int | None = None,
) -> Generator[webdriver.Chrome, None, None]:
    """Start an owned browser and close it even if the caller raises."""
    driver = start_chrome(
        user_data_dir=user_data_dir,
        chrome_path=chrome_path,
        chromedriver_path=chromedriver_path,
        headless=headless,
        debugging_port=debugging_port,
    )
    try:
        yield driver
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start persistent Chrome for automation")
    parser.add_argument("--user-data-dir", type=Path, default=DEFAULT_USER_DATA_DIR)
    parser.add_argument("--chrome-path", type=Path)
    parser.add_argument("--chromedriver-path", type=Path)
    parser.add_argument("--debugging-port", type=int)
    args = parser.parse_args()
    with chrome_session(
        user_data_dir=args.user_data_dir,
        chrome_path=args.chrome_path,
        chromedriver_path=args.chromedriver_path,
        debugging_port=args.debugging_port,
    ):
        print("Chrome is ready. Log in manually if needed.")
        input("Press Enter to close Chrome and exit: ")


if __name__ == "__main__":
    main()
