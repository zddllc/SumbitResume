"""Run on a logged-in Linux desktop; uses a synthetic page, not LinkedIn."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.browser import chrome_session

with tempfile.TemporaryDirectory(prefix="resume-chrome-smoke-") as profile:
    with chrome_session(user_data_dir=profile) as browser:
        browser.get("data:text/html,<title>Resume%20Chrome%20Smoke</title><h1>Ready</h1>")
        if browser.title != "Resume Chrome Smoke":
            raise RuntimeError("Chrome did not respond with the expected synthetic page")
        print("Graphical Chrome smoke check passed; no LinkedIn login or application touched.")
