from dataclasses import dataclass, field
from typing import List


@dataclass
class Insight:
    content: str
    created_at: int
    last_seen: int
    confidence: float
    evidence_count: int
    type: str = "general"

    def is_expired(self, current_period: int, ttl: int = 5) -> bool:
        return (current_period - self.last_seen > ttl) and self.evidence_count < 3


class InsightManager:
    def __init__(self, max_active: int = 5):
        self.active: List[Insight] = []
        self.archived: List[Insight] = []
        self.max_active = max_active

    def ingest(self, raw_insight: str, current_period: int):
        if not raw_insight or not raw_insight.strip():
            return
        content = raw_insight.strip()
        for existing in self.active:
            if _is_similar(content, existing.content):
                existing.last_seen = current_period
                existing.evidence_count += 1
                existing.confidence = min(1.0, existing.confidence + 0.15)
                return
        self.active.append(Insight(
            content=content, created_at=current_period,
            last_seen=current_period, confidence=0.5,
            evidence_count=1, type=_classify(content),
        ))
        if len(self.active) > self.max_active:
            self.active.sort(key=lambda i: i.confidence)
            self.archived.append(self.active.pop(0))

    def expire_old(self, current_period: int, ttl: int = 5):
        expired = [i for i in self.active if i.is_expired(current_period, ttl)]
        self.active = [i for i in self.active if i not in expired]
        self.archived.extend(expired)

    def to_prompt_string(self) -> str:
        if not self.active:
            return ""
        lines = []
        for i in sorted(self.active, key=lambda i: i.confidence, reverse=True):
            lines.append(f"[confidence={i.confidence:.0%}, type={i.type}] {i.content}")
        return "\n".join(lines)

    def to_state(self) -> dict:
        return {
            "active": [
                {"content": i.content, "created_at": i.created_at,
                 "last_seen": i.last_seen, "confidence": i.confidence,
                 "evidence_count": i.evidence_count, "type": i.type}
                for i in self.active
            ],
        }

    @classmethod
    def from_state(cls, data: dict) -> "InsightManager":
        mgr = cls()
        for item in data.get("active", []):
            mgr.active.append(Insight(**item))
        return mgr


def _is_similar(a: str, b: str) -> bool:
    if a == b:
        return True
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) > 0.6


def _classify(content: str) -> str:
    c = content.lower()
    if any(w in c for w in ["demand", "trend", "spike", "drop", "shift", "increase", "decrease"]):
        return "demand_shift"
    if any(w in c for w in ["lead time", "shipment", "delay", "lost"]):
        return "lead_time"
    if any(w in c for w in ["seasonal", "weekend", "holiday", "month", "periodic"]):
        return "seasonality"
    return "general"
