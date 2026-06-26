import hashlib
import re
import time
from typing import Optional


class ResponseCache:
    def __init__(self, max_size: int = 1000, similarity_threshold: float = 0.92, enabled: bool = True):
        self.enabled = enabled
        self.max_size = max_size
        self.threshold = similarity_threshold
        self._store: dict[str, tuple[str, float]] = {}
        self.hits = 0
        self.misses = 0

    def _compute_key(self, user_message: str, system_prompt: str) -> str:
        normalized = re.sub(r"PERIOD \d+ / \d+", "PERIOD N / M", user_message)
        normalized = re.sub(r"Period \d+ conclude", "Period N conclude", normalized)
        normalized = re.sub(r"demand history \(last \d+ periods\): \[[\d, ]+\]", "demand history (last N periods): [...]", normalized)
        payload = system_prompt + "\n" + normalized
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, user_message: str, system_prompt: str) -> Optional[str]:
        if not self.enabled:
            return None
        key = self._compute_key(user_message, system_prompt)
        if key in self._store:
            self.hits += 1
            return self._store[key][0]
        # fuzzy match on recent demands stripped
        for cached_key, (resp, _) in list(self._store.items()):
            if self._similarity(key, cached_key) > self.threshold:
                self.hits += 1
                return resp
        self.misses += 1
        return None

    def set(self, user_message: str, system_prompt: str, response: str):
        if not self.enabled:
            return
        key = self._compute_key(user_message, system_prompt)
        if len(self._store) >= self.max_size:
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]
        self._store[key] = (response, time.time())

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def _similarity(self, key1: str, key2: str) -> float:
        if key1 == key2:
            return 1.0
        common = sum(1 for a, b in zip(key1, key2) if a == b)
        return common / max(len(key1), len(key2))
