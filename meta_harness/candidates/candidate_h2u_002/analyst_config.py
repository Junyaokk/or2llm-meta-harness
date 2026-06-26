"""
Candidate H2U-002 — Active Reviewer with Override Calibration.

Hypothesis: A Reviewer that computes the Decider's recent override accuracy
from the memory table and enforces evidence-quality thresholds on adjustment
magnitude will improve NR by catching unjustified overrides on weak signals.

Uses the same Analyst thresholds as H2U-000 baseline. The new mechanism
is entirely in the Reviewer prompt — the Decider prompt and Analyst config
are unchanged from baseline.
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=4,
    trend_evidence_periods=3,
    trend_gap_threshold=0.10,
    volatility_cv_threshold=0.25,
    or_bias_threshold=0.08,
    iid_window=10,
    iid_trend_threshold=0.08,
    z_score_threshold=3.0,
    sustained_deviation_periods=3,
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
