import statistics
import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    def __init__(self):
        self._data: dict[str, list[Any]] = defaultdict(list)
        self._episode_start: float = 0.0

    def record(self, name: str, value: Any):
        self._data[name].append(value)

    def start_episode(self):
        self._episode_start = time.time()

    def summary(self) -> dict:
        llm_durations = self._data.get("llm_duration_ms", [])
        deviations = self._data.get("deviation_from_or", [])
        tokens = self._data.get("tokens_used", [])
        overrides = self._data.get("review_overrides", [0])

        n_periods = len(self._data.get("period", []))
        return {
            "total_periods": n_periods,
            "wall_time_sec": round(time.time() - self._episode_start, 1),
            "llm_calls": len(llm_durations),
            "avg_llm_latency_ms": round(statistics.mean(llm_durations), 1) if llm_durations else 0,
            "p99_llm_latency_ms": round(_percentile(llm_durations, 99), 1) if llm_durations else 0,
            "total_tokens": sum(tokens),
            "avg_or_deviation": round(statistics.mean(deviations), 1) if deviations else 0,
            "max_or_deviation": max(deviations) if deviations else 0,
            "review_overrides": sum(overrides),
            "parse_errors": sum(self._data.get("parse_errors", [0])),
            "llm_retries": sum(self._data.get("llm_retries", [0])),
        }


def _percentile(data: list, p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = k - f
    if f + 1 < len(s):
        return s[f] + c * (s[f + 1] - s[f])
    return float(s[f])
