"""
Candidate 012 — H2X Baseline: Memory + Decider + Reviewer.
Memory window = 5 periods. Decider sees history table + analyst report.
Reviewer sanity-checks draft before execution.

Best H2 analyst config carried forward from candidate_011.
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=6,
    trend_evidence_periods=3,
    trend_gap_threshold=0.09,
    volatility_cv_threshold=0.28,
    or_bias_threshold=0.08,
    iid_window=10,
    iid_trend_threshold=0.05,
    z_score_threshold=3.0,
    sustained_deviation_periods=4,
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
