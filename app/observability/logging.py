import logging
import re
import sys
from typing import Any

_TELEGRAM_BOT_URL_TOKEN = re.compile(r"/bot\d+:[A-Za-z0-9_-]+/")


class TelegramTokenRedactFilter(logging.Filter):
    """Log mesajlarında Telegram Bot API URL içindeki token'ı maskele."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "/bot" in record.msg:
            record.msg = _TELEGRAM_BOT_URL_TOKEN.sub("/bot***REDACTED***/", record.msg)
        if record.args:
            record.args = tuple(
                _TELEGRAM_BOT_URL_TOKEN.sub("/bot***REDACTED***/", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def _apply_third_party_log_levels() -> None:
    """httpx INFO satırları tam URL (bot token) basar; gürültü ve sızıntıyı azalt."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _ensure_redact_filter_on_root_handlers() -> None:
    root = logging.getLogger()
    for h in root.handlers:
        if not any(isinstance(f, TelegramTokenRedactFilter) for f in h.filters):
            h.addFilter(TelegramTokenRedactFilter())


def configure_logging(
    level: str = "INFO",
    *,
    redact_telegram_token: bool = True,
) -> None:
    _apply_third_party_log_levels()

    root = logging.getLogger()
    if root.handlers:
        if redact_telegram_token:
            _ensure_redact_filter_on_root_handlers()
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    if redact_telegram_token:
        handler.addFilter(TelegramTokenRedactFilter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(thread_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
    out: dict[str, Any] = {**kwargs}
    if thread_id is not None:
        out["thread_id"] = thread_id
    return out
