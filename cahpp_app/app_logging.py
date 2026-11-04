"""Journal technique borné, sans données métier ni texte brut des exceptions."""
from __future__ import annotations

import logging
import sys
import threading
import traceback
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import ROOT_DIR

LOG_DIR = ROOT_DIR / "logs"
_log_path: Path | None = None
_setup_error = ""


def configure_logging(directory: Path = LOG_DIR) -> Path | None:
    """Configure uniquement les journaux de l'application (4 fichiers de 1 Mio)."""
    global _log_path, _setup_error
    logger = logging.getLogger("cahpp_app")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _log_path = None
    _setup_error = ""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "commandes-cahpp.log"
        handler = RotatingFileHandler(
            path, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
        )
    except OSError as exc:
        _setup_error = type(exc).__name__
        logger.addHandler(logging.NullHandler())
        return None
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    ))
    logger.addHandler(handler)
    _log_path = path
    return path


def log_failure(logger: logging.Logger, event: str, error: BaseException) -> None:
    """Conserve type, code et pile technique, jamais message, source ou variables."""
    frames = traceback.extract_tb(error.__traceback__)
    stack = " > ".join(
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        for frame in frames
    )
    logger.error(
        "%s type=%s errno=%s sqlite=%s pile=%s",
        event, type(error).__name__, getattr(error, "errno", None),
        getattr(error, "sqlite_errorname", None), stack or "indisponible",
    )


def install_exception_hooks() -> None:
    """Capture les erreurs non gérées du processus et des workers Python."""
    logger = logging.getLogger(__name__)

    def process_error(kind, error, tb):
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, error, tb)
            return
        log_failure(logger, "processus_exception", error.with_traceback(tb))

    def thread_error(args):
        log_failure(logger, "worker_exception", args.exc_value)

    sys.excepthook = process_error
    threading.excepthook = thread_error


def logging_snapshot() -> dict[str, object]:
    recent: list[str] = []
    if _log_path is not None:
        try:
            with _log_path.open(encoding="utf-8", errors="replace") as stream:
                recent = list(deque(stream, maxlen=25))
        except OSError as exc:
            return {"path": str(_log_path), "error": type(exc).__name__, "recent": []}
    return {"path": str(_log_path or ""), "error": _setup_error, "recent": recent}
