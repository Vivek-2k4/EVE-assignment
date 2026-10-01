import json
import logging


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Pass structured fields via extra={"ctx": {...}}."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "ctx", {}) or {})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
