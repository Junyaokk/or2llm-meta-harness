"""
Candidate 011 — Balanced blend of candidate_007 (variance) and candidate_010 (seasonal).
Hypothesis: A middle-ground config captures both seasonal half-cycles and variance
regime shifts without excessive false positives on stationary data.

Changes from candidate_007:
  - trend_window: 8 → 6 (compromise: long enough for stability, short enough for cycles)
  - trend_evidence_periods: 4 → 3 (faster trend declaration)
  - trend_gap_threshold: 0.10 → 0.09 (slightly more sensitive)
  - volatility_cv_threshold: 0.3 → 0.28 (slightly more sensitive to variance shifts)
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    # Pipeline — unchanged
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,

    # Demand — balanced sensitivity
    trend_window=6,
    trend_evidence_periods=3,
    trend_gap_threshold=0.09,
    volatility_cv_threshold=0.28,

    # OR audit — lower bar for detecting bias
    or_bias_threshold=0.08,
    iid_window=10,
    iid_trend_threshold=0.05,

    # Anomaly — unchanged
    z_score_threshold=3.0,
    sustained_deviation_periods=4,

    # Active modules — all on
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
