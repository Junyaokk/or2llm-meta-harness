"""
Candidate H2U-005 — EWMA Gap Persistence Memory Config.

Uses 8-period sliding window to provide enough history for the EWMA gap
reversal check (needs 2*lead_time + 2 = 10 periods ideally, but 8 is
sufficient for typical lead times while keeping context manageable).
"""
MEMORY_WINDOW = 8
