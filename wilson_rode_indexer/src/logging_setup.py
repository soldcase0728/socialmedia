"""Structured logging with a hard guarantee that document text never prints.

Two handlers are installed:

``console``
    Everything the operator sees.  A :class:`ContentGuard` filter rejects any
    record that is not explicitly marked as safe, so an accidental
    ``log.info(page_text)`` somewhere in the codebase cannot leak confidential
    content to the terminal.

``file``
    A rotating log inside the derived-index folder.  It records operations,
    counts and errors -- also without document text.

The rule enforced here is structural rather than advisory: to log something
that *could* contain document text, a caller must pass ``extra={"safe": True}``
and take responsibility for the content.  Nothing in this package does.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from pathlib import Path
from typing import Optional

LOGGER_NAME = "wri"

#: Records longer than this are treated as suspicious on the console.  Real
#: progress lines are short; extracted document text is not.
MAX_CONSOLE_MESSAGE_CHARS = 500

#: Patterns that strongly suggest substantive document content rather than a
#: status message.  Matching records are replaced with a placeholder.
_CONTENT_MARKERS = (
    re.compile(r"^\s*(?:From|To|Cc|Bcc|Subject|Sent)\s*:\s+\S", re.IGNORECASE | re.MULTILINE),
    re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}"),
)


class ContentGuard(logging.Filter):
    """Filter that prevents document text from reaching a handler.

    A record passes unchanged when it is short and contains no content
    markers, or when the caller set ``record.safe = True``.  Otherwise the
    message is replaced by a neutral placeholder that still records that
    something was suppressed, so the audit trail stays honest.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D102
        if getattr(record, "safe", False):
            return True
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            record.msg = "<unformattable log record suppressed>"
            record.args = ()
            return True

        suspicious = len(message) > MAX_CONSOLE_MESSAGE_CHARS or any(
            marker.search(message) for marker in _CONTENT_MARKERS
        )
        if suspicious:
            record.msg = (
                "<suppressed: message resembled document content "
                f"({len(message)} chars) from {record.module}:{record.lineno}>"
            )
            record.args = ()
        return True


class _PlainFormatter(logging.Formatter):
    """Console formatter: terse, timestamped, no tracebacks by default."""

    def __init__(self) -> None:
        super().__init__(fmt="%(asctime)s  %(levelname)-7s %(message)s",
                         datefmt="%H:%M:%S")


class _FileFormatter(logging.Formatter):
    """File formatter: full context for the audit trail."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(lineno)d | "
                "%(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )


def setup_logging(
    log_dir: Optional[Path] = None,
    *,
    level: str = "INFO",
    console_level: str = "INFO",
    filename: str = "wilson_rode_indexer.log",
    max_bytes: int = 50 * 1024 * 1024,
    backup_count: int = 10,
) -> logging.Logger:
    """Configure and return the package logger.

    Parameters
    ----------
    log_dir:
        Directory for the rotating log file.  When ``None`` only the console
        handler is installed (used by unit tests).
    level:
        Level for the file handler.
    console_level:
        Level for the console handler.
    filename, max_bytes, backup_count:
        Rotating-file-handler settings.

    Returns
    -------
    logging.Logger
        The configured ``wri`` logger.  Safe to call repeatedly; existing
        handlers are replaced.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    guard = ContentGuard()

    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console.setFormatter(_PlainFormatter())
    console.addFilter(guard)
    logger.addHandler(console)

    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        file_handler.setFormatter(_FileFormatter())
        file_handler.addFilter(guard)
        logger.addHandler(file_handler)

    return logger


def get_logger(suffix: Optional[str] = None) -> logging.Logger:
    """Return a child of the package logger, e.g. ``wri.inventory``."""
    return logging.getLogger(LOGGER_NAME if not suffix else f"{LOGGER_NAME}.{suffix}")
