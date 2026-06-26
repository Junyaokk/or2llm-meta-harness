"""
Analyst — deterministic analytics layer. No LLM, zero API cost.
Computes pipeline projection, demand decomposition, OR assumption audit.
Configurable thresholds are the Meta-Harness search space.

Separates "computing" from "judging". The LLM Decider receives the
AnalystReport and makes decisions, never doing arithmetic itself.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import numpy as np
from scipy.stats import linregress


@dataclass
class AnalystConfig:
    """All configurable analyst parameters — Meta-Harness search space ①."""
    # Pipeline projection
    pipe_overfill_ratio: float = 1.0       # IP/B >= this → OVERFILLED
    pipe_adequate_ratio: float = 0.7       # IP/B >= this → ADEQUATE
    overdue_tolerance: int = 1             # waited > L + this → overdue

    # Demand decomposition
    trend_window: int = 5                  # periods for trend detection
    trend_evidence_periods: int = 4        # min periods to declare trend
    trend_gap_threshold: float = 0.15      # 5p-avg vs d_bar gap to flag
    volatility_cv_threshold: float = 0.5   # CV > this → volatile

    # OR assumption audit
    or_bias_threshold: float = 0.12        # |5p_avg - d_bar|/d_bar > this → equal_weights violated
    iid_window: int = 10                   # periods for i.i.d. check
    iid_trend_threshold: float = 0.10      # slope/d_bar > this → i.i.d. violated

    # Anomaly detection
    z_score_threshold: float = 3.0         # |z| > this → spike
    sustained_deviation_periods: int = 4   # periods for sustained deviation

    # Active modules
    enable_pipeline: bool = True
    enable_demand: bool = True
    enable_or_audit: bool = True
    enable_anomaly: bool = True


@dataclass
class AnalystReport:
    """Structured analysis output — the Decider's input."""
    pipeline: Dict = field(default_factory=dict)
    demand: Dict = field(default_factory=dict)
    or_audit: Dict = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)
    summary: str = ""  # one-line executive summary


class Analyst:
    """Deterministic pre-decision analytics. Configurable, searchable, no LLM."""

    def __init__(self, config: AnalystConfig = None):
        self.cfg = config or AnalystConfig()

    def analyze(self, obs: dict, or_rec, item_id: str = "",
                context: str = "") -> AnalystReport:
        """Run all active analysis modules and return structured report."""
        report = AnalystReport()

        if self.cfg.enable_pipeline:
            report.pipeline = self._analyze_pipeline(obs, or_rec)

        if self.cfg.enable_demand:
            report.demand = self._analyze_demand(obs, or_rec)

        if self.cfg.enable_or_audit:
            report.or_audit = self._audit_or(obs, or_rec, report)

        if self.cfg.enable_anomaly:
            report.alerts = self._detect_anomalies(obs, report)

        report.summary = self._build_summary(report)
        return report

    # ------------------------------------------------------------------
    # Pipeline Projection
    # ------------------------------------------------------------------

    def _analyze_pipeline(self, obs: dict, or_rec) -> Dict:
        on_hand = obs.get("on_hand_inventory", 0)
        in_transit = obs.get("in_transit_orders", [])
        in_transit_total = obs.get("in_transit_total", 0)
        L = obs.get("lead_time", 0)
        B = or_rec.base_stock_level
        IP = on_hand + in_transit_total

        # Build arrival timeline
        timeline = []
        overdue_orders = []
        for o in in_transit:
            waited = o.get("waited_periods", 0)
            arrival_in = L - waited  # periods until arrival (negative = overdue)
            status = "arriving_now" if arrival_in == 0 else (
                "overdue" if arrival_in < -self.cfg.overdue_tolerance else "in_transit"
            )
            entry = {
                "period_placed": o["period_placed"],
                "quantity": o["quantity"],
                "waited": waited,
                "arrives_in_periods": max(0, arrival_in),
                "status": status,
            }
            timeline.append(entry)
            if status == "overdue":
                overdue_orders.append(entry)

        # Pipeline health
        ip_b_ratio = IP / B if B > 0 else float("inf")
        if ip_b_ratio >= self.cfg.pipe_overfill_ratio:
            pipe_status = "OVERFILLED"
        elif ip_b_ratio >= self.cfg.pipe_adequate_ratio:
            pipe_status = "ADEQUATE"
        else:
            pipe_status = "UNDERFILLED"

        room = max(0, int(B - IP))

        return {
            "IP": IP,
            "B": B,
            "ip_b_ratio": round(ip_b_ratio, 3),
            "pipe_status": pipe_status,
            "on_hand": on_hand,
            "in_transit_total": in_transit_total,
            "in_transit_batches": len(in_transit),
            "arrival_timeline": timeline,
            "overdue_count": len(overdue_orders),
            "overdue_orders": overdue_orders,
            "room_to_order": room,
            "cap": or_rec.order_cap,
        }

    # ------------------------------------------------------------------
    # Demand Decomposition
    # ------------------------------------------------------------------

    def _analyze_demand(self, obs: dict, or_rec) -> Dict:
        history = obs.get("demand_history", [])
        if len(history) < 3:
            return {"trend_dir": "flat", "slope": 0.0, "confidence": 0.0,
                    "d_bar": or_rec.demand_mean, "recent_5p_avg": or_rec.demand_mean,
                    "gap_pct": 0.0, "evidence_periods": 0}

        arr = np.array(history, dtype=np.float64)
        d_bar = or_rec.demand_mean
        w = min(self.cfg.trend_window, len(arr))
        recent = arr[-w:]
        recent_avg = float(recent.mean())

        gap_pct = (recent_avg - d_bar) / d_bar if d_bar > 0 else 0.0

        # Linear regression on trend window
        x = np.arange(w)
        slope, intercept, r_value, p_value, std_err = linregress(x, recent)
        slope_per_period = float(slope)

        # Determine trend direction (two detection pathways)
        trend_dir = "flat"
        evidence = 0
        diffs = np.diff(recent)
        r_squared = r_value ** 2

        # Pathway A: gap-based detection — recent avg differs meaningfully from d_bar
        gap_detected = abs(gap_pct) > self.cfg.trend_gap_threshold

        # Pathway B: regression-based detection — strong linear fit even if gap is small
        # (captures gradual trends like +2/period that gap threshold misses)
        regression_detected = (
            r_squared > 0.7 and
            abs(slope_per_period) > 0.5 and
            np.sum(diffs > 0) >= self.cfg.trend_evidence_periods - 1
            if slope_per_period > 0
            else np.sum(diffs < 0) >= self.cfg.trend_evidence_periods - 1
            if slope_per_period < 0
            else False
        )

        if gap_detected or regression_detected:
            if slope_per_period > 0 and np.sum(diffs > 0) >= self.cfg.trend_evidence_periods - 1:
                trend_dir = "up"
                evidence = int(np.sum(diffs > 0)) + 1
            elif slope_per_period < 0 and np.sum(diffs < 0) >= self.cfg.trend_evidence_periods - 1:
                trend_dir = "down"
                evidence = int(np.sum(diffs < 0)) + 1

        # Volatility check
        cv = float(np.std(recent, ddof=1) / recent_avg) if recent_avg > 0 else 0.0
        is_volatile = cv > self.cfg.volatility_cv_threshold

        if is_volatile and trend_dir == "flat":
            trend_dir = "volatile"

        # Seasonal hint from product description
        seasonal_hint = "none"
        ctx = obs.get("context", "")
        if ctx:
            ctx_lower = ctx.lower()
            seasonal_keywords = {
                "ice cream": "summer_peak", "icecream": "summer_peak",
                "cold drink": "summer_peak", "soda": "summer_peak",
                "heater": "winter_peak", "coat": "winter_peak",
                "umbrella": "rainy_peak",
                "chip": "none", "snack": "none",
                "holiday": "holiday_peak", "christmas": "winter_peak",
            }
            for kw, hint in seasonal_keywords.items():
                if kw in ctx_lower:
                    seasonal_hint = hint
                    break

        return {
            "d_bar": round(d_bar, 1),
            "recent_5p_avg": round(recent_avg, 1),
            "gap_pct": round(gap_pct * 100, 1),
            "trend_dir": trend_dir,
            "slope_per_period": round(slope_per_period, 3),
            "r_squared": round(r_value ** 2, 3),
            "confidence": round(abs(r_value), 3),
            "evidence_periods": evidence,
            "is_volatile": is_volatile,
            "cv": round(cv, 3),
            "seasonal_hint": seasonal_hint,
        }

    # ------------------------------------------------------------------
    # OR Assumption Audit
    # ------------------------------------------------------------------

    def _audit_or(self, obs: dict, or_rec, report: AnalystReport) -> Dict:
        concerns = []
        violations = {"iid": False, "equal_weights": False, "lead_time_match": True}

        # i.i.d. check: if trend is detected, i.i.d. is violated
        demand = report.demand
        if demand.get("trend_dir") in ("up", "down"):
            if demand.get("evidence_periods", 0) >= self.cfg.trend_evidence_periods:
                violations["iid"] = True
                concerns.append(f"i.i.d. violated: {demand['trend_dir']}-trend detected "
                              f"({demand['evidence_periods']} periods evidence)")

        # Equal weights check: if 5p avg differs significantly from d_bar
        if abs(demand.get("gap_pct", 0)) / 100 > self.cfg.or_bias_threshold:
            violations["equal_weights"] = True
            direction = "overestimates" if demand["gap_pct"] < 0 else "underestimates"
            concerns.append(f"equal-weights causes OR to {direction} demand "
                          f"(|gap|={abs(demand['gap_pct']):.1f}% > {self.cfg.or_bias_threshold*100:.0f}%)")

        # Lead time match: check overdue
        if report.pipeline.get("overdue_count", 0) > 0:
            violations["lead_time_match"] = False
            concerns.append(f"actual L > promised L: {report.pipeline['overdue_count']} overdue")

        # Trust level
        if len(concerns) == 0:
            trust = "high"
            bias = 0
        elif len(concerns) == 1 and not violations["lead_time_match"]:
            trust = "medium"
            gap = demand.get("gap_pct", 0) / 100
            bias = int(or_rec.recommended_order * max(-0.3, min(0.3, gap)))
        else:
            trust = "low"
            gap = demand.get("gap_pct", 0) / 100
            bias = int(or_rec.recommended_order * max(-0.5, min(0.5, gap)))

        return {
            "trust_level": trust,
            "concerns": concerns,
            "violations": violations,
            "suggested_bias": bias,
            "suggested_bias_pct": round(bias / max(or_rec.recommended_order, 1) * 100, 1),
        }

    # ------------------------------------------------------------------
    # Anomaly Detection
    # ------------------------------------------------------------------

    def _detect_anomalies(self, obs: dict, report: AnalystReport) -> List[str]:
        alerts = []
        history = obs.get("demand_history", [])
        if len(history) < 5:
            return alerts

        arr = np.array(history, dtype=np.float64)
        mean = float(arr.mean())
        std = float(arr.std(ddof=1)) if len(arr) > 1 else 1.0

        # Latest period spike
        latest = arr[-1]
        z = (latest - mean) / std if std > 0 else 0.0
        if abs(z) > self.cfg.z_score_threshold:
            direction = "high" if z > 0 else "low"
            alerts.append(f"SPIKE: last demand {int(latest)} is {abs(z):.1f}σ {direction}")

        # Sustained deviation
        w = self.cfg.sustained_deviation_periods
        recent = arr[-w:]
        recent_mean = float(recent.mean())
        recent_z = (recent_mean - mean) / (std / np.sqrt(w)) if std > 0 else 0
        if abs(recent_z) > 2.0:
            direction = "above" if recent_z > 0 else "below"
            alerts.append(f"SUSTAINED: last {w} periods avg {recent_mean:.0f} is {direction} "
                        f"historical mean {mean:.0f} (z={recent_z:.1f})")

        # Pipeline alerts
        pipe = report.pipeline
        if pipe.get("overdue_count", 0) > 0:
            alerts.append(f"PIPELINE: {pipe['overdue_count']} order(s) overdue")
        if pipe.get("pipe_status") == "OVERFILLED":
            alerts.append("PIPELINE: IP exceeds B — ordering more creates holding cost")
        elif pipe.get("pipe_status") == "UNDERFILLED" and pipe.get("on_hand", 0) == 0:
            alerts.append("PIPELINE: critically low — risk of stockout")

        return alerts

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(self, report: AnalystReport) -> str:
        pipe = report.pipeline.get("pipe_status", "?")
        trend = report.demand.get("trend_dir", "?")
        trust = report.or_audit.get("trust_level", "?")
        alerts_n = len(report.alerts)
        return (f"Pipeline:{pipe} | Trend:{trend} | OR-Trust:{trust} | "
                f"Alerts:{alerts_n}")

    # ------------------------------------------------------------------
    # Render report as Decider-readable text
    # ------------------------------------------------------------------

    def render_for_decider(self, report: AnalystReport, obs: dict,
                           or_rec, item_id: str, carry_over: str = "") -> str:
        """Convert AnalystReport into LLM-readable text for the Decider."""
        parts = []

        # Carry-over from previous periods
        if carry_over and carry_over.strip():
            parts.append("=" * 60)
            parts.append("CARRY-OVER INSIGHTS:")
            parts.append(carry_over)
            parts.append("=" * 60)
            parts.append("")

        # Current state
        parts.append(f"Period {obs['period']}/{obs['total_periods']} | SKU: {item_id} | L={obs.get('lead_time', '?')}")
        parts.append(f"On-hand: {obs.get('on_hand_inventory', 0)} | p={obs.get('p', '?')} | h={obs.get('h', '?')}")
        parts.append("")

        # Pipeline section
        p = report.pipeline
        parts.append("─── PIPELINE ANALYSIS (computed, not estimated) ───")
        parts.append(f"Status: {p.get('pipe_status')} | IP={p.get('IP', '?'):.0f} | B={p.get('B', '?'):.0f} | Ratio={p.get('ip_b_ratio', '?'):.2f}")
        parts.append(f"On-hand: {p.get('on_hand', 0)} | In-transit: {p.get('in_transit_total', 0)} ({p.get('in_transit_batches', 0)} batches)")
        parts.append(f"Room to order: {p.get('room_to_order', 0)} | Cap: {p.get('cap', '?'):.0f}")
        if p.get("overdue_count", 0) > 0:
            parts.append(f"OVERDUE: {p['overdue_count']} order(s)")
        for entry in p.get("arrival_timeline", []):
            parts.append(f"  P{entry['period_placed']}: {entry['quantity']}u {entry['status']} ({entry['arrives_in_periods']}p)")
        parts.append("")

        # Demand section
        d = report.demand
        parts.append("─── DEMAND ANALYSIS (computed, not estimated) ───")
        parts.append(f"d_bar={d.get('d_bar', '?')} | 5p-avg={d.get('recent_5p_avg', '?')} | Gap={d.get('gap_pct', '?'):+.1f}%")
        parts.append(f"Trend: {d.get('trend_dir')} | Slope: {d.get('slope_per_period', 0):+.3f}/p | Evidence: {d.get('evidence_periods', 0)}p | R²={d.get('r_squared', 0):.3f}")
        parts.append(f"Volatile: {d.get('is_volatile')} (CV={d.get('cv', 0):.3f}) | Seasonal: {d.get('seasonal_hint', 'none')}")
        # Show recent demand values for pattern recognition (read only, don't recompute)
        demand_history = obs.get("demand_history", [])
        all_n = len(demand_history)
        recent_n = min(10, all_n)
        recent_demands = demand_history[-recent_n:]
        parts.append(f"Recent demand history (last {recent_n}p): {recent_demands}")
        parts.append(f"All demand history ({all_n}p): {demand_history}")
        parts.append("")

        # OR audit section
        a = report.or_audit
        parts.append("─── OR ASSUMPTION AUDIT ───")
        parts.append(f"Trust level: {a.get('trust_level')}")
        parts.append(f"Violations: i.i.d.={a.get('violations', {}).get('iid', False)}, equal-w={a.get('violations', {}).get('equal_weights', False)}, L-match={a.get('violations', {}).get('lead_time_match', True)}")
        if a.get("concerns"):
            for c in a["concerns"]:
                parts.append(f"  ⚠ {c}")
        parts.append(f"Suggested bias: {a.get('suggested_bias', 0):+d} ({a.get('suggested_bias_pct', 0):+.1f}%)")
        parts.append("")

        # Product context
        ctx = obs.get("context", "")
        if ctx:
            parts.append(f"Product: {ctx}")
            parts.append("")

        # Last period conclude message
        last_conclude = obs.get("last_period_conclude", "")
        if last_conclude:
            parts.append("─── LAST PERIOD SUMMARY ───")
            parts.append(last_conclude)
            parts.append("")

        # OR recommendation (full stats, matching H1 format)
        parts.append("─── OR RECOMMENDATION ───")
        parts.append(f"  d_bar={or_rec.demand_mean:.1f} | s_d={or_rec.demand_std:.1f}")
        parts.append(f"  mu_hat={or_rec.mu_hat:.1f} | sigma_hat={or_rec.sigma_hat:.1f}")
        parts.append(f"  rho={or_rec.critical_fractile:.4f} | z*={or_rec.z_star:.4f}")
        parts.append(f"  B={or_rec.base_stock_level:.1f} | IP={or_rec.inventory_position:.1f} | cap={or_rec.order_cap:.1f}")
        parts.append(f"  q_or = {or_rec.recommended_order}")
        parts.append("  Note: OR uses promised lead time and historical demand only. It cannot see lost shipments or regime shifts.")
        parts.append("")

        # Alerts
        if report.alerts:
            parts.append("─── ALERTS ───")
            for alert in report.alerts:
                parts.append(f"  ⚠ {alert}")
            parts.append("")


        # Summary
        parts.append(f"Summary: {report.summary}")

        return "\n".join(parts)

    def _compute_suggestion(self, report: AnalystReport, or_rec):
        """Pre-compute a suggested order for the Decider to judge (accept/modify/reject)."""
        d = report.demand
        p = report.pipeline
        a = report.or_audit

        gap_pct = d.get("gap_pct", 0)  # percentage, e.g. +30.0 means 30%
        trend_dir = d.get("trend_dir", "flat")
        evidence = d.get("evidence_periods", 0)
        is_volatile = d.get("is_volatile", False)
        pipe_status = p.get("pipe_status", "ADEQUATE")
        room = p.get("room_to_order", 0)
        cap = int(p.get("cap", or_rec.order_cap))
        trust = a.get("trust_level", "medium")
        ip_val = p.get("IP", 0)
        b_val = p.get("B", 0)

        or_q = int(or_rec.recommended_order)
        gap_abs = abs(gap_pct)

        # Default: follow OR
        suggested = or_q
        reason = "Follow OR"

        # Pipeline hard constraint: OVERFILLED → 0 or minimal
        if pipe_status == "OVERFILLED" and ip_val >= b_val:
            # Only override if extremely strong evidence
            if gap_abs > 30 and evidence >= 4:
                suggested = max(0, min(int(cap * 0.2), room))
                reason = f"OVERFILLED but extreme surge (gap={gap_pct:+.1f}%, evidence={evidence}p) → small order"
            else:
                suggested = 0
                reason = f"OVERFILLED (IP={ip_val:.0f} >= B={b_val:.0f}) → order 0"
            return suggested, reason

        # Trust OR: gap small (< 15%) and trust is high/medium
        if gap_abs < 15 and trust in ("high", "medium") and trend_dir in ("flat", "volatile"):
            # Small ±10% adjustment for product knowledge
            suggested = max(0, min(int(or_q * 1.1), cap, room)) if room > 0 else 0
            reason = f"TRUST OR (gap={gap_pct:+.1f}% < 15%, trust={trust}) → OR ±10%"
            return suggested, reason

        # Potential shift: gap > 20% or trend is clear
        if gap_abs > 20 or (trend_dir in ("up", "down") and evidence >= 4):
            # Variance only (high volatility but flat trend) → trust OR
            if is_volatile and trend_dir == "flat":
                suggested = max(0, min(int(or_q * 1.1), cap, room)) if room > 0 else 0
                reason = f"VARIANCE ONLY (CV high, trend flat) → trust OR"
                return suggested, reason

            # Mean shift with trend direction
            if trend_dir in ("up", "down") and evidence >= 4:
                # Compute adjustment: gap_pct is percentage, convert to fraction
                direction = 1 if trend_dir == "up" else -1
                adjustment_raw = (gap_pct / 100.0) * or_q  # e.g. 30% → 0.30 * OR
                adjustment = direction * adjustment_raw

                # Cap at ±50% of OR
                adjustment = max(-or_q * 0.5, min(or_q * 0.5, adjustment))

                suggested = int(or_q + adjustment)

                # Apply pipeline constraints
                if pipe_status == "UNDERFILLED" and trend_dir == "up":
                    suggested = max(suggested, int(or_q * 1.1))  # at least +10% if underfilled
                suggested = min(suggested, cap, room) if room > 0 else 0
                suggested = max(0, suggested)

                reason = f"MEAN SHIFT (trend={trend_dir}, gap={gap_pct:+.1f}%, evidence={evidence}p) → adjust {adjustment:+.0f} → {suggested}"
                return suggested, reason

            # Gap > 20% but trend unclear → cautious
            if gap_abs > 20:
                suggested = int(or_q * (1 + gap_pct / 200.0))  # half adjustment for unclear
                suggested = max(0, min(suggested, cap, room)) if room > 0 else 0
                reason = f"CAUTION (gap={gap_pct:+.1f}% but trend unclear) → slight adjust"
                return suggested, reason

        # Caution zone (15-20% gap)
        if 15 <= gap_abs <= 20:
            suggested = max(0, min(int(or_q * 1.05), cap, room)) if room > 0 else 0
            reason = f"CAUTION ZONE (gap={gap_pct:+.1f}%) → OR +5%"
            return suggested, reason

        # Default: follow OR with pipeline constraint
        suggested = max(0, min(or_q, cap, room)) if room > 0 else 0
        reason = "Follow OR (no signal to override)"
        return suggested, reason
