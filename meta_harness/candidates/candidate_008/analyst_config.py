"""
Candidate 008 — Long window stability: wider view, higher evidence bar.

Hypothesis: For autocorrelated demand (p10) and gradual trends (p04),
a longer window (7) provides better signal-to-noise. Low CV threshold (0.22)
helps distinguish true variance regime changes from sampling noise.

Changes from 005: window=5→7, gap=0.15→0.12, cv=0.30→0.22
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=7,
    trend_evidence_periods=4,
    trend_gap_threshold=0.12,
    volatility_cv_threshold=0.22,
    or_bias_threshold=0.10,
    iid_window=10,
    iid_trend_threshold=0.10,
    z_score_threshold=3.0,
    sustained_deviation_periods=4,
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
