"""
TraceStore -- persists and queries Plan B trace data.

Each candidate's results are stored as:
  trace_store/
    candidate_000/
      scores.json         # Summary: per-instance NR + mean NR
      p01_L0_rho80.json   # Full per-period traces for one instance
      p02_L0_rho80.json
      p07_L4_rho80.json
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .evaluator import CandidateResult, InstanceTrace, PeriodTrace


class TraceStore:
    """Stores and queries evaluation traces for all candidates."""

    def __init__(self, store_dir: Path):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, result: CandidateResult):
        """Save a candidate's full results to the trace store."""
        cand_dir = self.store_dir / result.candidate_id
        cand_dir.mkdir(parents=True, exist_ok=True)

        # Save summary scores
        scores = {
            "candidate_id": result.candidate_id,
            "mean_nr": result.mean_nr,
            "per_instance_nr": result.per_instance_nr,
        }
        with open(cand_dir / "scores.json", "w") as f:
            json.dump(scores, f, indent=2)

        # Save per-instance full traces
        for inst_trace in result.instance_traces:
            trace_data = self._serialize_instance_trace(inst_trace)
            out_path = cand_dir / f"{inst_trace.instance_label}.json"
            with open(out_path, "w") as f:
                json.dump(trace_data, f, indent=2, ensure_ascii=False)

    def load_scores(self, candidate_id: str) -> Optional[dict]:
        """Load summary scores for a candidate."""
        path = self.store_dir / candidate_id / "scores.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def load_instance_trace(self, candidate_id: str,
                            instance_label: str) -> Optional[dict]:
        """Load full per-period trace for one candidate on one instance."""
        path = self.store_dir / candidate_id / f"{instance_label}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def list_candidates(self) -> List[str]:
        """List all evaluated candidate IDs sorted by name."""
        if not self.store_dir.exists():
            return []
        return sorted([
            d.name for d in self.store_dir.iterdir()
            if d.is_dir() and (d / "scores.json").exists()
        ])

    def get_all_scores(self) -> List[dict]:
        """Get scores for all candidates, sorted by mean_nr descending."""
        all_scores = []
        for cid in self.list_candidates():
            s = self.load_scores(cid)
            if s:
                all_scores.append(s)
        all_scores.sort(key=lambda x: x["mean_nr"], reverse=True)
        return all_scores

    def build_proposer_context(self, max_candidates: int = 3,
                               worst_instances: int = 2) -> str:
        """
        Build a text context for the proposer to read.

        Plan B: includes full rationale traces for worst-performing instances.
        This is the "memory-rich" input that distinguishes Meta-Harness from
        prior text optimizers (DSPy, TextGrad) that only pass scalar scores.

        Returns a formatted string the proposer can directly read.
        """
        all_scores = self.get_all_scores()
        if not all_scores:
            return "(No prior candidates evaluated yet.)"

        parts = []
        parts.append("=" * 70)
        parts.append("PRIOR HARNESS CANDIDATES — SCORES + TRACES")
        parts.append("=" * 70)

        # Top-level scoreboard
        parts.append("\n## Scoreboard (mean NR across holdout instances)\n")
        parts.append(f"{'Rank':<5} {'Candidate':<20} {'Mean NR':<10} {'Per-Instance'}")
        parts.append("-" * 70)
        for rank, s in enumerate(all_scores, 1):
            per_inst = ", ".join(
                f"{k}={v:.4f}" for k, v in s["per_instance_nr"].items()
            )
            parts.append(f"{rank:<5} {s['candidate_id']:<20} {s['mean_nr']:<10.4f} {per_inst}")

        # For the top and bottom candidates, include full rationale traces
        candidates_to_detail = []
        if all_scores:
            candidates_to_detail.append(all_scores[0]["candidate_id"])  # best
        if len(all_scores) > 1:
            candidates_to_detail.append(all_scores[-1]["candidate_id"])  # worst
        if len(all_scores) > 2:
            # middle candidate
            mid = all_scores[len(all_scores) // 2]
            if mid["candidate_id"] not in candidates_to_detail:
                candidates_to_detail.append(mid["candidate_id"])

        candidates_to_detail = candidates_to_detail[:max_candidates]

        for cid in candidates_to_detail:
            s = self.load_scores(cid)
            parts.append(f"\n{'=' * 70}")
            parts.append(f"DETAILED TRACE: {cid} (mean NR = {s['mean_nr']:.4f})")
            parts.append(f"{'=' * 70}")

            # Find worst-performing instances for this candidate
            per_inst = s["per_instance_nr"]
            sorted_insts = sorted(per_inst.items(), key=lambda x: x[1])
            worst_inst_labels = [label for label, _ in sorted_insts[:worst_instances]]

            for label in worst_inst_labels:
                trace = self.load_instance_trace(cid, label)
                if not trace:
                    continue

                parts.append(f"\n### Instance: {label} (NR = {trace['normalized_reward']:.4f})")
                parts.append(f"    Item: {trace['item_id']}, L={trace['lead_time']}, "
                           f"rho={trace['rho']:.2f}, Total Demand={trace['total_demand']}")
                parts.append(f"    Total Reward: ${trace['total_reward']:.1f}")
                parts.append("")

                # Print per-period decision trace
                parts.append(f"{'P':<4} {'Demand':<8} {'Order':<8} {'ORRec':<8} "
                           f"{'Sold':<8} {'Reward':<10} {'LLM Rationale (truncated)'}")
                parts.append("-" * 100)

                for p in trace["periods"]:
                    rationale_short = p["llm_rationale"][:120].replace("\n", " ")
                    parts.append(
                        f"{p['period']:<4} {p['demand']:<8} {p['ordered']:<8} "
                        f"{p['or_recommended']:<8} {p['sold']:<8} "
                        f"{p['reward']:<10.1f} {rationale_short}"
                    )

                # Show full rationale for key decision periods
                # (periods where LLM deviated from OR recommendation)
                deviations = [
                    p for p in trace["periods"]
                    if p["ordered"] != p["or_recommended"]
                ]
                if deviations:
                    parts.append(f"\n### Key Deviation Periods for {label}:")
                    for p in deviations[-5:]:  # last 5 deviations
                        parts.append(f"\n--- Period {p['period']} ---")
                        parts.append(f"  Demand: {p['demand']}, OR rec: {p['or_recommended']}, "
                                   f"LLM ordered: {p['ordered']}")
                        parts.append(f"  Full Rationale:")
                        parts.append(f"  {p['llm_rationale'][:500]}")

        return "\n".join(parts)

    @staticmethod
    def _serialize_instance_trace(t: InstanceTrace) -> dict:
        periods_data = []
        for p in t.periods:
            entry = {
                "period": p.period,
                "demand": p.demand,
                "ordered": p.ordered,
                "sold": p.sold,
                "reward": p.reward,
                "or_recommended": p.or_recommended,
                "llm_rationale": p.llm_rationale,
                "llm_short_rationale": p.llm_short_rationale,
                "carry_over_insight": p.carry_over_insight,
            }
            # H2 fields (duck-typing via hasattr)
            if hasattr(p, "analyst_summary"):
                entry["analyst_summary"] = p.analyst_summary
            if hasattr(p, "analyst_alerts"):
                entry["analyst_alerts"] = p.analyst_alerts
            if hasattr(p, "pipe_status"):
                entry["pipe_status"] = p.pipe_status
            if hasattr(p, "trend_dir"):
                entry["trend_dir"] = p.trend_dir
            if hasattr(p, "or_trust"):
                entry["or_trust"] = p.or_trust
            # H2X fields (duck-typing via hasattr)
            if hasattr(p, "draft_order"):
                entry["draft_order"] = p.draft_order
            if hasattr(p, "reviewer_rationale"):
                entry["reviewer_rationale"] = p.reviewer_rationale
            if hasattr(p, "approved"):
                entry["approved"] = p.approved
            if hasattr(p, "risk_flag"):
                entry["risk_flag"] = p.risk_flag
            if hasattr(p, "adjustment_pct"):
                entry["adjustment_pct"] = p.adjustment_pct
            # H2M fields (duck-typing via hasattr)
            if hasattr(p, "concern_level"):
                entry["concern_level"] = p.concern_level
            if hasattr(p, "decider_accepted_critique"):
                entry["decider_accepted_critique"] = p.decider_accepted_critique
            if hasattr(p, "conversation_rounds"):
                entry["conversation_rounds"] = p.conversation_rounds
            if hasattr(p, "revision_rationale"):
                entry["revision_rationale"] = p.revision_rationale
            periods_data.append(entry)

        return {
            "instance_label": t.instance_label,
            "item_id": t.item_id,
            "lead_time": t.lead_time,
            "p": t.p,
            "h": t.h,
            "rho": t.rho,
            "total_demand": t.total_demand,
            "total_reward": t.total_reward,
            "normalized_reward": t.normalized_reward,
            "periods": periods_data,
        }
