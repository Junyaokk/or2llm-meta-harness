"""
Candidate H2U-001 — Cyclic Pattern Detection via Alternation Score.

Hypothesis: Adding a cyclic/alternation regime classifier to the Decider's
decision tree will improve NR on seasonal instances by preventing the system
from chasing cycle phases as if they were genuine trends.

Uses the same Analyst thresholds as H2U-000 baseline. The new mechanism
is entirely in the Decider and Reviewer prompts.
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
