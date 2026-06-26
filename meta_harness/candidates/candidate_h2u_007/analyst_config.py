"""
Candidate H2U-007 — Insight-Driven Override Modulation.

Hypothesis: When the Decider's carry-over insight from the previous period
was WRONG (demand moved opposite to the predicted direction), reducing
override magnitude toward OR prevents the system from doubling down on
a misread pattern. This self-calibration mechanism embeds "learning from
mistakes" into the Decider's reasoning, distinct from the Reviewer's
post-hoc calibration check.

Builds on H2U-002 analyst config (best performing base).
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
