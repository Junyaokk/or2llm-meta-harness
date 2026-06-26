import logging

logger = logging.getLogger(__name__)


class FallbackHandler:
    def __init__(self, strategy: str = "or_baseline"):
        self.strategy = strategy
        self.previous_qty: int = 0

    def handle(self, exception: Exception, or_recommended: int, step_name: str) -> int:
        logger.warning(f"[Fallback] Step '{step_name}' failed: {exception}")
        if self.strategy == "or_baseline":
            return or_recommended
        elif self.strategy == "previous":
            return self.previous_qty
        elif self.strategy == "zero":
            return 0
        return or_recommended

    def update(self, qty: int):
        self.previous_qty = qty
