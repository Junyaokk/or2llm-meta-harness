"""
Candidate 017 — H2 with H1 best (004) knowledge baked into Analyst config.

Knowledge extracted from H1 candidate_004 optimized prompt:
  1. "5-period avg demand" → trend_window=5
  2. "Gap < 15% → TRUST OR" → trend_gap_threshold=0.15
  3. "Gap > 20% consistently → POTENTIAL SHIFT" → or_bias_threshold=0.12
  4. "4+ periods monotonic → UPTREND/DOWNTREND" → trend_evidence_periods=4
  5. "Wider swings but same center → VARIANCE CHANGE. TRUST OR quantity"
     → volatility_cv_threshold=0.30 (detect but don't over-adjust)
  6. "IP >= B → pipeline is full. Order 0 or small"
     → pipe_overfill_ratio=1.0
  7. "Wait for 4+ periods of confirmation" → sustained_deviation_periods=4
  8. "Bias downward when uncertain" → encoded in Decider prompt
  9. "Cap adjustment at ±50% of OR recommendation" → encoded in Decider prompt
  10. "Trust case: OR ±10%" → encoded in Decider prompt

Key differences from H2 baseline (006):
  - trend_window: 5 (same, but now explicitly from H1 best)
  - trend_gap_threshold: 0.15 (H1 knowledge: <15%=noise)
  - or_bias_threshold: 0.12 (H1 knowledge: >20%=shift, we set detection bar at 12%)
  - volatility_cv_threshold: 0.30 (H1 knowledge: detect variance but don't confuse with mean shift)
  - trend_evidence_periods: 4 (H1 knowledge: "4+ periods monotonic")

Key differences from H2 best (011):
  - 011 was a "compromise blend" of 007+010, not informed by H1
  - 017 explicitly encodes H1's learned thresholds
  - Decider prompt is completely rewritten with H1's 5-step decision tree
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    # Pipeline
    pipe_overfill_ratio=1.0,       # H1: "IP >= B → pipeline full"
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,

    # Demand — calibrated from H1 best (004)
    trend_window=5,                # H1: "Compute 5-period avg demand"
    trend_evidence_periods=4,      # H1: "Monotonic increase over 4+ periods"
    trend_gap_threshold=0.15,      # H1: "Gap < 15% → TRUST OR"
    volatility_cv_threshold=0.30,  # H1: "Wider swings same center → VARIANCE, trust OR"

    # OR audit — calibrated from H1 best (004)
    or_bias_threshold=0.12,         # H1: "Gap > 20% → POTENTIAL SHIFT", set lower for early detection
    iid_window=10,
    iid_trend_threshold=0.10,      # H1: OR "equal-weights all history, assumes i.i.d."

    # Anomaly
    z_score_threshold=3.0,
    sustained_deviation_periods=4,  # H1: "Wait for 4+ periods of confirmation"

    # Active modules
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
