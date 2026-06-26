"""
Candidate H2U-007 — Insight-Driven Override Modulation Memory Config.

Same 5-period sliding window as H2U-002 baseline. The Insight Calibration
mechanism is entirely in the Decider prompt — it uses the carry-over insight
field and the current period's demand to determine whether the last insight
was correct, then modulates override magnitude accordingly.
"""
MEMORY_WINDOW = 5
