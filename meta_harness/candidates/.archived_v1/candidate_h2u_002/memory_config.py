"""
candidate_h2u_002 — Evidence-weighted insight memory config.

Key innovation: carry_over_insight is now structured with evidence tracking.
The Decider writes insights in a format that enables the Reviewer and next-period
Decider to assess whether the insight is still supported by evidence.

Insight format: "CLAIM: <claim> | EVIDENCE: <N periods supporting> | LAST_SEEN: P<N>"

Rules embedded in Decider prompt:
- New insight gets evidence=1
- If same claim repeated next period, evidence++
- If 3+ periods pass without reinforcement, evidence--
- If evidence drops to 0, insight is expired (not carried forward)
- Contradictory claim replaces old claim (e.g., "mean shifted up" replaces "mean shifted down")
- Maximum insight lifespan: 8 periods regardless of evidence
"""
MEMORY_WINDOW = 5
