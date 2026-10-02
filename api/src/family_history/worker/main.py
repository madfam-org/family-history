"""Worker process setup: settings, logging, metrics, signals."""

from __future__ import annotations

import logging
import signal
import sys
import threading
from types import FrameType

from family_history.config import get_settings
from family_history.db.engine import create_database
from family_history.logging_setup import configure_logging
from family_history.metrics import start_metrics_server
from family_history.worker.runner import Worker

logger = logging.getLogger("family_history.worker")


def serve() -> int:
    settings = get_settings()
    configure_logging()
    if settings.database_url is None:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    database = create_database(
        settings.database_url.get_secret_value(), pool_size=2, max_overflow=1
    )
    metrics = start_metrics_server(settings.metrics_port) if settings.metrics_port else None
    stop = threading.Event()

    def on_signal(signum: int, _frame: FrameType | None) -> None:
        logger.info("worker stopping", extra={"signal": signum})
        stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        Worker(database).run_forever(stop)
    finally:
        if metrics is not None:
            metrics.stop()
        database.dispose()
    return 0
