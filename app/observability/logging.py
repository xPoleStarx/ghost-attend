import logging
import sys
from typing import Any


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(thread_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
    out: dict[str, Any] = {**kwargs}
    if thread_id is not None:
        out["thread_id"] = thread_id
    return out
