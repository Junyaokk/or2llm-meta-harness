"""
Candidate H2U-005 — EWMA Gap Persistence Regime Classifier.

Hypothesis: Replacing simple trend detection with an EWMA-based gap persistence
check that classifies regimes as TRENDING (one-sided persistent gap), CYCLIC
(reversing gap), or NEUTRAL (small gap) will improve NR on seasonal and
variance-change instances. On seasonal data, the EWMA gap oscillates around
zero (flipping sign), triggering CYCLIC regime and capping overrides. On
genuine trends, the gap is persistently one-sided, allowing full overrides.

Uses same AnalystConfig as baseline H2U-000. The EWMA computation and regime
classification are performed by the Decider from the period history table —
no new AnalystConfig fields are needed.
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
