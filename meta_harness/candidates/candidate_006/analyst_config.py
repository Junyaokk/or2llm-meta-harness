"""
Candidate 006 — Faster detection: lower thresholds for L=4 complex scenarios.

Hypothesis: H1(004)'s thresholds (gap=15%, evidence=4) are tuned for L=0.
In L=4, demand patterns shift faster and evidence takes longer to accumulate.
Lower thresholds detect shifts earlier, preventing the Decider from following
OR too long when OR becomes unreliable.

Changes from 005: window=5→4, evidence=4→3, gap=0.15→0.10, cv=0.30→0.25, bias=0.12→0.08
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
