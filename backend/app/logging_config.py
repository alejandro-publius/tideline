"""Structured logging setup.

Emits one line per event as `key=value` pairs, so logs stay greppable in a
terminal and parse cleanly when shipped to a log aggregator. Any fields passed
via `logger.info(..., extra={...})` are appended as additional pairs.
"""

import logging
import sys

# LogRecord attributes present on every record; anything else in a record's
# __dict__ was passed via `extra=` and should be rendered as a key=value pair.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"time={self.formatTime(record, '%Y-%m-%dT%H:%M:%S')} "
            f"level={record.levelname} "
            f"logger={record.name} "
            f'msg="{record.getMessage()}"'
        )
        extras = " ".join(
            f"{key}={value}" for key, value in record.__dict__.items() if key not in _RESERVED
        )
        line = f"{base} {extras}" if extras else base
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(level: str = "INFO") -> None:
    """Attach a structured handler to the `tideline` logger tree once."""
    logger = logging.getLogger("tideline")
    logger.setLevel(level.upper())
    if any(getattr(h, "_tideline", False) for h in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    handler._tideline = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.propagate = False
