"""
Candidate 010 — Short window + high sensitivity for seasonal pattern detection.
Hypothesis: A 5-period window on a 10-period seasonal cycle sees alternating
up/down half-cycles. Each half-cycle has a clear directional signal with
sufficient gap_pct to trigger trend detection. The resulting i.i.d. violations
will lower OR trust, guiding the Decider to rely more on pipeline analysis.

Changes from candidate_007:
  - trend_window: 8 → 5 (shorter window catches half-cycles)
  - trend_gap_threshold: 0.10 → 0.08 (more sensitive)
  - trend_evidence_periods: 4 → 3 (lower bar to declare trend)
  - volatility_cv_threshold: 0.3 → 0.25 (still catch variance shifts)
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    # Pipeline — unchanged
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,

    # Demand — short window, high sensitivity
    trend_window=5,
    trend_evidence_periods=3,
    trend_gap_threshold=0.08,
    volatility_cv_threshold=0.25,

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
