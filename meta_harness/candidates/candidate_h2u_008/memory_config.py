"""
Candidate H2U-008 — Stockout Risk Floor Reviewer Memory Config.

Same 5-period sliding window as H2U-002 baseline. The Stockout Risk Floor
mechanism is entirely in the Reviewer prompt — it uses the analyst report
(pipeline, demand, arrival timeline) to assess whether the draft order
risks a stockout within the lead time window.
"""
MEMORY_WINDOW = 5
