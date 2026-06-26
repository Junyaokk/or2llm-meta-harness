"""
Candidate 009 — Balanced compromise: middle ground across all dimensions.

Hypothesis: Neither extreme dominates. Modest relaxations on all thresholds
maintain H1(004) quality on L=0 while improving L=4 detection speed.

Changes from 005: window=5→6, evidence=4→3, gap=0.15→0.10, cv=0.30→0.28, bias=0.12→0.09
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=6,
    trend_evidence_periods=3,
    trend_gap_threshold=0.10,
    volatility_cv_threshold=0.28,
    or_bias_threshold=0.09,
    iid_window=10,
    iid_trend_threshold=0.08,
    z_score_threshold=3.0,
    sustained_deviation_periods=4,
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
