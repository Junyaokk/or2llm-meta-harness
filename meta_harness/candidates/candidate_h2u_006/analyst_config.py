"""
Candidate H2U-006 — Hysteresis-based Trust Calibration.

Hypothesis: A continuous OR-trust score with asymmetric update dynamics
(slow decay when non-stationarity evidence accumulates, slow recovery
when evidence fades) will improve NR by preventing the system from
oscillating between full-trust and full-distrust of OR. On seasonal data,
trust stays moderate (never fully abandons OR), preventing extreme
cycle-chasing. On genuine trends, trust decays steadily and stays low,
allowing sustained overrides.

Uses same AnalystConfig as baseline H2U-000. The trust score is computed
by the Decider from the period history table.
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
