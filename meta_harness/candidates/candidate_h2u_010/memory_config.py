"""
Candidate H2U-010 — Adaptive Coverage Bounds Memory Config.

Same 5-period sliding window as H2U-007 baseline. The Adaptive Coverage Bounds
mechanism is entirely in the Decider prompt — the bounds are computed from the
demand history and pipeline data provided in the standard Analyst report.
"""
MEMORY_WINDOW = 5
