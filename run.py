"""Single-instance Windows/Linux API server; Chrome uses the same desktop session."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout
from waitress import serve

from resume_app import create_app
from resume_app.config import load_config


@contextmanager
def single_instance(path: Path) -> Generator[None, None, None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(path)
    try:
        lock.acquire(timeout=0)
    except Timeout as error:
        raise RuntimeError("本工作台已有后端在运行，请不要重复启动") from error
    try:
        yield
    finally:
        lock.release()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    with single_instance(Path(config["INSTANCE_DIR"]) / "app.lock"):
        app = create_app(config)
        try:
            serve(
                app, host=app.config["BIND_HOST"], port=app.config["BIND_PORT"],
                threads=app.config["SERVER_THREADS"], clear_untrusted_proxy_headers=False,
            )
        finally:
            app.extensions["resume_runner"].close()
            client = app.extensions.get("resume_mongo_client")
            if client is not None:
                client.close()
