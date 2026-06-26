"""
candidate_h2u_003 — Analyst config matching H2U baseline.
Pattern-aware trust calibration lives in Decider prompt.
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
