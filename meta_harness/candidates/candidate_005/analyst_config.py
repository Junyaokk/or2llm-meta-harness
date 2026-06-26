"""
Candidate 005 — H2 Baseline: H1 best (004) knowledge → H2 architecture.

Analyst thresholds directly calibrated from H1(004) optimized prompt:
  - "5-period avg" → trend_window=5
  - "Gap < 15% → TRUST OR" → trend_gap_threshold=0.15
  - "4+ periods monotonic" → trend_evidence_periods=4
  - "Wider swings same center → VARIANCE" → volatility_cv_threshold=0.30
  - "Gap > 20% → POTENTIAL SHIFT" → or_bias_threshold=0.12

Decider prompt: H1(004) 5-step decision tree, translated to H2 format.
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=5,
    trend_evidence_periods=4,
    trend_gap_threshold=0.15,
    volatility_cv_threshold=0.30,
    or_bias_threshold=0.12,
    iid_window=10,
    iid_trend_threshold=0.10,
    z_score_threshold=3.0,
    sustained_deviation_periods=4,
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
