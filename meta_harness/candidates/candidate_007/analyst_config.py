"""
Candidate 007 — Seasonal focus: short window, low evidence bar.

Hypothesis: 10-period seasonal cycle → each half-cycle is 5 periods.
With window=5, evidence=4, Analyst confirms trend just as it reverses.
Shorter window (4) + lower evidence (2) catches half-cycles mid-way.

Changes from 005: window=5→4, evidence=4→2, gap=0.15→0.08
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=4,
    trend_evidence_periods=2,
    trend_gap_threshold=0.08,
    volatility_cv_threshold=0.28,
    or_bias_threshold=0.10,
    iid_window=10,
    iid_trend_threshold=0.05,
    z_score_threshold=3.0,
    sustained_deviation_periods=3,
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
