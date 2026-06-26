# Candidate 000 — Baseline
#
# Hypothesis: The current system prompt (faithful to the paper's Appendix B)
# produces competitive but not optimal results. This candidate serves as the
# control group for all subsequent prompt variants.
#
# Search axes touched: NONE (this is the baseline)
#
# Expected behavior:
#   - p01 (stationary): Should follow OR closely, NR ~0.75+
#   - p02 (mean increase): May fail to detect regime shift promptly
#   - p07 (seasonal): May fail to anticipate cyclical patterns
