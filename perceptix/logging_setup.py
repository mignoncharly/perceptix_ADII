import os
import logging
from rich.logging import RichHandler  # requires: pip install rich

def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_level=True,
        show_path=False,
    )
    handler.setLevel(level)

    # Keep formatter minimal; RichHandler renders time/level nicely
    handler.setFormatter(logging.Formatter("%(message)s"))

    root.addHandler(handler)

    # Optional: quiet noisy libs during demos
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
