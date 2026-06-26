"""
Candidate H2U-001 — Cyclic Pattern Detection Memory Config.

Same 5-period sliding window as baseline. The alternation score is computed
by the LLM from the trend_dir column in the history table, not from a new
analyst signal.
"""
MEMORY_WINDOW = 5
