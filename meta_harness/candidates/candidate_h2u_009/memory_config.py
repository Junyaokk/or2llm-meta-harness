"""
Candidate H2U-009 — Trend Quality Vetting Memory Config.

Same 5-period sliding window as H2U-007 baseline. The Trend Quality Vetting
mechanism is in the Analyst (autocorr + momentum computation) and Decider
prompt (quality-gated override logic).
"""
MEMORY_WINDOW = 5
