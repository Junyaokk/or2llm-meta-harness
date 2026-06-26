"""
candidate_h2x_001 — H2X iteration 1.
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=5,
    trend_evidence_periods=4,
    trend_gap_threshold=0.12,
    volatility_cv_threshold=0.35,
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
