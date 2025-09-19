import logging


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # The Django request isn't directly available; injected by middleware via threadlocals in a real app.
        # Here we simply avoid KeyErrors by setting empty when missing.
        if not hasattr(record, "request_id"):
            record.request_id = ""
        return True
