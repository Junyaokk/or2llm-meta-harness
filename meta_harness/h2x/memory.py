"""
MemoryBuffer — structured rolling history replacing single-string carry_over_insight.
Gives the Decider and Reviewer cross-period visibility into what happened.
Meta-Harness search object ①: memory window size.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class PeriodMemory:
    """One period's outcome, stored in the rolling buffer."""
    period: int
    demand: int
    ordered: int
    sold: int
    reward: float
    or_recommended: int
    pipe_status: str = ""
    trend_dir: str = ""
    or_trust: str = ""

    @property
    def deviation_pct(self) -> float:
        """How much the actual order deviated from OR recommendation."""
        if self.or_recommended > 0:
            return (self.ordered - self.or_recommended) / self.or_recommended * 100
        return 0.0

    @property
    def deviation_str(self) -> str:
        if abs(self.deviation_pct) < 0.5:
            return "=OR"
        sign = "+" if self.deviation_pct > 0 else ""
        return f"{sign}{self.deviation_pct:.0f}%"


class MemoryBuffer:
    """Rolling window of period outcomes. Replaces single-string carry_over_insight."""

    def __init__(self, window: int = 5):
        self.window = window
        self.history: List[PeriodMemory] = []

    def add(self, mem: PeriodMemory):
        self.history.append(mem)

    def get_recent(self, n: int = None) -> List[PeriodMemory]:
        n = n or self.window
        return self.history[-n:]

    def render_for_decider(self) -> str:
        """Compact history table for the Decider — shows what happened, helps learn from mistakes."""
        recent = self.get_recent()
        if not recent:
            return "(No prior periods — this is the first decision.)"

        lines = []
        lines.append(f"PERIOD HISTORY (last {len(recent)}):")
        lines.append(f"{'P':<4} {'Dem':>4} {'Ord':>4} {'OR':>4} {'Sold':>4} {'Rew':>6} {'Dev':>5} {'Pipe':<11} {'Trend':<8} {'Trust':<6}")
        lines.append("-" * 75)

        for m in recent:
            reward_str = f"{m.reward:+.0f}" if m.reward != 0 else "0"
            lines.append(
                f"{m.period:<4} {m.demand:>4} {m.ordered:>4} {m.or_recommended:>4} "
                f"{m.sold:>4} {reward_str:>6} {m.deviation_str:>5} "
                f"{m.pipe_status:<11} {m.trend_dir:<8} {m.or_trust:<6}"
            )

        # Add reward summary
        total_reward = sum(m.reward for m in recent)
        lines.append(f"  Recent total reward: {total_reward:+.0f}")

        return "\n".join(lines)

    def render_for_reviewer(self, draft_order: int, draft_rationale: str) -> str:
        """Full history for the Reviewer — includes the Decider's draft for THIS period."""
        recent = self.get_recent()
        lines = []
        lines.append(f"DECISION HISTORY (last {len(recent)} periods):")
        lines.append(f"{'P':<4} {'Dem':>4} {'Ord':>4} {'OR':>4} {'Sold':>4} {'Rew':>6} {'Dev':>5} {'Pipe':<11}")
        lines.append("-" * 65)

        for m in recent:
            reward_str = f"{m.reward:+.0f}" if m.reward != 0 else "0"
            lines.append(
                f"{m.period:<4} {m.demand:>4} {m.ordered:>4} {m.or_recommended:>4} "
                f"{m.sold:>4} {reward_str:>6} {m.deviation_str:>5} {m.pipe_status:<11}"
            )

        lines.append("")
        lines.append(f"DRAFT ORDER FOR THIS PERIOD: {draft_order}")
        lines.append(f"DECIDER'S RATIONALE: {draft_rationale[:300]}")
        return "\n".join(lines)
