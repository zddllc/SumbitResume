"""Deployment configuration shared by Windows and graphical Linux sessions."""

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


def base_path(value: str) -> str:
    if value in ("", "/"):
        return ""
    if (
        not value.startswith("/") or "//" in value or "\\" in value
        or any(part in {".", ".."} for part in value.split("/"))
        or any(character in value for character in ("?", "#", "%"))
        or any(character.isspace() for character in value)
    ):
        raise ValueError("APP_BASE_PATH must be an absolute URL prefix such as /resume")
    return value.rstrip("/")


def _boolean(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    if value.lower() not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value.lower() == "true"


def _path(name: str, default: Path) -> Path:
    value = Path(os.environ.get(name, str(default))).expanduser()
    return (value if value.is_absolute() else ROOT / value).resolve()


def load_config() -> dict:
    configured_env = os.environ.get("RESUME_ENV_FILE")
    env_file = Path(configured_env).expanduser() if configured_env else ROOT / ".env"
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    if configured_env and not env_file.is_file():
        raise FileNotFoundError("RESUME_ENV_FILE does not exist")
    load_dotenv(env_file, override=False)
    prefix = base_path(os.environ.get("APP_BASE_PATH", "/resume"))
    hosts = [
        value.strip() for value in os.environ.get(
            "TRUSTED_HOSTS", "localhost,127.0.0.1,[::1]"
        ).split(",") if value.strip()
    ]
    if not hosts or "*" in hosts:
        raise ValueError("TRUSTED_HOSTS must contain explicit hostnames, not *")
    port = int(os.environ.get("BIND_PORT", "8000"))
    threads = int(os.environ.get("SERVER_THREADS", "4"))
    if not 1 <= port <= 65535 or not 1 <= threads <= 32:
        raise ValueError("BIND_PORT or SERVER_THREADS is out of range")
    return {
        "MONGO_URI": os.environ.get("MONGO_URI", "mongodb://10.0.0.44:27017"),
        "MONGO_DB": os.environ.get("MONGO_DB", "resume"),
        "APP_BASE_PATH": prefix,
        "INSTANCE_DIR": _path("INSTANCE_DIR", ROOT / ".instance"),
        "BROWSER_PROFILE_ROOT": _path("BROWSER_PROFILE_ROOT", ROOT / ".browser-data"),
        "CHROME_PATH": os.environ.get("CHROME_PATH") or None,
        "CHROMEDRIVER_PATH": os.environ.get("CHROMEDRIVER_PATH") or None,
        "PDF_FONT_PATH": os.environ.get("PDF_FONT_PATH") or None,
        "SESSION_COOKIE_NAME": os.environ.get("SESSION_COOKIE_NAME", "resume_session"),
        "SESSION_COOKIE_SECURE": _boolean("COOKIE_SECURE", False),
        "TRUST_PROXY": _boolean("TRUST_PROXY", False),
        "TRUSTED_HOSTS": hosts,
        "BIND_HOST": os.environ.get("BIND_HOST", "127.0.0.1"),
        "BIND_PORT": port, "SERVER_THREADS": threads,
    }
