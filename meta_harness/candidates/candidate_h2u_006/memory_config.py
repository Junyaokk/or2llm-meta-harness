"""
Candidate H2U-006 — Hysteresis Trust Memory Config.

7-period sliding window provides enough history for the trust score
calibration (needs to see override profitability over 5+ periods).
"""
MEMORY_WINDOW = 7
