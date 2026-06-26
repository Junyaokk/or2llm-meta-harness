"""
H2 Baseline Analyst Config — conservative defaults aligned with H1(004) thresholds.

Design rationale:
  - trend_gap_threshold=0.15: matches 004's "Gap < 15% → TRUST OR" (STEP 1)
  - trend_evidence_periods=4: matches 004's "Wait for 4+ periods of confirmation"
  - volatility_cv_threshold=0.50: conservative, only flag clearly volatile patterns
  - or_bias_threshold=0.12: matches 004's implicit "d_bar vs 5p-avg >20%" warning threshold
  - pipe_overfill_ratio=1.0: OVERFILLED = IP >= B (004's definition)
  - pipe_adequate_ratio=0.7: ADEQUATE = IP >= 0.7*B (reasonable buffer)
  - overdue_tolerance=1: in fixed L mode, overdue is impossible; tolerance prevents false triggers
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    # Pipeline projection
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,

    # Demand decomposition (aligned with 004's evidence thresholds)
    trend_window=5,
    trend_evidence_periods=4,
    trend_gap_threshold=0.15,
    volatility_cv_threshold=0.50,

    # OR assumption audit
    or_bias_threshold=0.12,
    iid_window=10,
    iid_trend_threshold=0.10,

    # Anomaly detection
    z_score_threshold=3.0,
    sustained_deviation_periods=4,

    # All modules active
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
