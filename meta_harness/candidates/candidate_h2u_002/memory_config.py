"""
Candidate H2U-002 — Active Reviewer Memory Config.

Same 5-period sliding window as baseline. The Reviewer computes override
calibration from the demand, ordered, and or_recommended columns in the
history table — no new analyst signals needed.
"""
MEMORY_WINDOW = 5
