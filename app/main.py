from __future__ import annotations

import sys
from pathlib import Path

# `python app/main.py` ile çalıştırıldığında proje kökü sys.path'te olmaz; `app` import'u için ekle.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os

try:
    from app.agent.task_agent import build_compiled_graph  # noqa: F401
    from app.adapters.browser_session_holder import apply_browser_use_event_timeouts
    from app.config.settings import get_settings
    from app.observability.logging import configure_logging
    from app.telegram.bot import run_bot
except ModuleNotFoundError as e:
    missing = getattr(e, "name", None) or str(e)
    print(
        f"\n[GhostMyShit] Eksik Python modulu: {missing}\n"
        "  (Bu mesaj bazen 'pydantic' sanilir; asil eksik modul yukaridaki isimdir.)\n"
        "  Cozum: proje kokunde  .\\Run.ps1   veya   ./Run.sh\n"
        "  Hala olmazsa .venv klasorunu silip tekrar Run.ps1 calistirin.\n"
        "  Manuel:\n"
        f"    \"{sys.executable}\" -m pip install -e \"{_ROOT}\"\n",
        file=sys.stderr,
    )
    raise SystemExit(1) from e


def main() -> None:
    settings = get_settings()
    apply_browser_use_event_timeouts(settings)
    configure_logging(
        os.environ.get("LOG_LEVEL", "INFO"),
        redact_telegram_token=settings.log_redact_telegram_token,
    )
    run_bot(settings)


if __name__ == "__main__":
    main()
