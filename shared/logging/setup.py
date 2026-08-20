import logging

from .formatter import JSONFormatter


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """Replace the root logger's handlers with a single structured JSON handler.

    Safe to call multiple times (e.g. across tests) - it always resets the
    root handler list rather than appending.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter(service_name))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
