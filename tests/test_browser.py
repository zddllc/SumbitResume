import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from selenium.common.exceptions import WebDriverException

from utils.browser import (
    DEFAULT_USER_DATA_DIR,
    BrowserConfigurationError,
    attach_chrome,
    chrome_session,
    main,
    start_chrome,
)


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.chrome_patch = patch("utils.browser.webdriver.Chrome")
        self.chrome = self.chrome_patch.start()
        self.addCleanup(self.chrome_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        display = patch.dict(os.environ, {"DISPLAY": os.environ.get("DISPLAY") or ":99"})
        display.start()
        self.addCleanup(display.stop)
        uid = patch("utils.browser.os.geteuid", return_value=1000, create=True)
        uid.start()
        self.addCleanup(uid.stop)

    def test_start_chrome_uses_persistent_absolute_profile(self):
        profile = self.root / "profile with spaces"
        driver = start_chrome(user_data_dir=profile)
        self.assertIs(driver, self.chrome.return_value)
        self.assertTrue(profile.is_dir())
        options = self.chrome.call_args.kwargs["options"]
        self.assertIn(f"--user-data-dir={profile.resolve()}", options.arguments)
        self.assertNotIn("--headless=new", options.arguments)
        self.assertNotIn("--no-sandbox", options.arguments)
        self.assertNotIn("debuggerAddress", options.experimental_options)
        driver.set_page_load_timeout.assert_called_once_with(120)
        driver.set_script_timeout.assert_called_once_with(60)
        driver.implicitly_wait.assert_called_once_with(0)
        driver.quit.assert_not_called()

    def test_default_profile_is_isolated_from_personal_chrome(self):
        self.assertEqual(
            DEFAULT_USER_DATA_DIR,
            Path(__file__).resolve().parents[1] / ".browser-data" / "linkedin",
        )

    def test_explicit_binaries_headless_and_debugging_port(self):
        chrome = self.root / "chrome.exe"
        chromedriver = self.root / "chromedriver.exe"
        chrome.touch()
        chromedriver.touch()
        start_chrome(
            user_data_dir=self.root / "profile",
            chrome_path=chrome,
            chromedriver_path=chromedriver,
            headless=True,
            debugging_port=9222,
        )
        options = self.chrome.call_args.kwargs["options"]
        service = self.chrome.call_args.kwargs["service"]
        self.assertEqual(options.binary_location, str(chrome.resolve()))
        self.assertEqual(service.path, str(chromedriver.resolve()))
        self.assertIn("--headless=new", options.arguments)
        self.assertIn("--remote-debugging-address=127.0.0.1", options.arguments)
        self.assertIn("--remote-debugging-port=9222", options.arguments)

    def test_attach_only_uses_local_debugging_address(self):
        driver = attach_chrome(9333)
        self.assertIs(driver, self.chrome.return_value)
        options = self.chrome.call_args.kwargs["options"]
        self.assertEqual(
            options.experimental_options, {"debuggerAddress": "127.0.0.1:9333"}
        )
        self.assertEqual(options.arguments, [])

    def test_invalid_ports_fail_before_browser_start(self):
        for port in (0, -1, 65536):
            for operation in (start_chrome, attach_chrome):
                with self.subTest(port=port, operation=operation):
                    with self.assertRaises(ValueError):
                        operation(debugging_port=port)
        self.chrome.assert_not_called()

    def test_missing_executables_fail_explicitly(self):
        with self.assertRaises(FileNotFoundError):
            start_chrome(chrome_path=self.root / "absent.exe")
        with self.assertRaises(FileNotFoundError):
            start_chrome(chromedriver_path=self.root / "absent-driver.exe")
        with self.assertRaises(FileNotFoundError):
            attach_chrome(chromedriver_path=self.root / "absent-driver.exe")
        self.chrome.assert_not_called()

    def test_context_closes_owned_browser(self):
        with chrome_session(user_data_dir=self.root / "profile") as driver:
            self.assertIs(driver, self.chrome.return_value)
        driver.quit.assert_called_once()

    def test_context_closes_browser_after_caller_failure(self):
        with self.assertRaisesRegex(RuntimeError, "caller failed"):
            with chrome_session(user_data_dir=self.root / "profile"):
                raise RuntimeError("caller failed")
        self.chrome.return_value.quit.assert_called_once()

    def test_initialization_error_closes_browser_and_propagates(self):
        self.chrome.return_value.set_script_timeout.side_effect = WebDriverException(
            "Timeout configuration failed"
        )
        with self.assertRaisesRegex(WebDriverException, "Timeout configuration failed"):
            start_chrome(user_data_dir=self.root / "profile")
        self.chrome.return_value.quit.assert_called_once()

    def test_cleanup_error_is_logged_without_hiding_initialization_error(self):
        self.chrome.return_value.set_script_timeout.side_effect = WebDriverException(
            "Timeout configuration failed"
        )
        self.chrome.return_value.quit.side_effect = WebDriverException("Quit failed")
        with self.assertLogs("utils.browser", level="ERROR"):
            with self.assertRaisesRegex(
                WebDriverException, "Timeout configuration failed"
            ):
                start_chrome(user_data_dir=self.root / "profile")

    def test_startup_failure_is_not_swallowed(self):
        self.chrome.side_effect = WebDriverException("Chrome unavailable")
        with self.assertRaisesRegex(WebDriverException, "Chrome unavailable"):
            start_chrome(user_data_dir=self.root / "profile")

    def test_linux_without_a_desktop_fails_with_an_actionable_message(self):
        with (
            patch("utils.browser.sys.platform", "linux"),
            patch("utils.browser.os.geteuid", return_value=1000, create=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            with self.assertRaisesRegex(BrowserConfigurationError, "DISPLAY"):
                start_chrome(user_data_dir=self.root / "profile")
        self.chrome.assert_not_called()

    def test_linux_root_does_not_disable_the_chrome_sandbox(self):
        with (
            patch("utils.browser.sys.platform", "linux"),
            patch("utils.browser.os.geteuid", return_value=0, create=True),
        ):
            with self.assertRaisesRegex(BrowserConfigurationError, "root"):
                start_chrome(user_data_dir=self.root / "profile")
        self.chrome.assert_not_called()

    def test_linux_headless_and_wayland_use_the_expected_options(self):
        with (
            patch("utils.browser.sys.platform", "linux"),
            patch("utils.browser.os.geteuid", return_value=1000, create=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            start_chrome(user_data_dir=self.root / "headless", headless=True)
            self.assertIn("--headless=new", self.chrome.call_args.kwargs["options"].arguments)
            with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
                start_chrome(user_data_dir=self.root / "wayland")
            self.assertIn("--ozone-platform=wayland", self.chrome.call_args.kwargs["options"].arguments)

    @patch("utils.browser.input", return_value="")
    @patch("utils.browser.print")
    def test_cli_waits_and_closes_browser(self, _print, read_input):
        with patch("sys.argv", [
            "utils.browser", "--user-data-dir", str(self.root / "profile"),
            "--debugging-port", "9222",
        ]):
            main()
        read_input.assert_called_once()
        self.chrome.return_value.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
