---
name: meta-harness-inventory
description: Run one iteration of inventory optimization harness evolution. Called by meta_harness proposer.
---

# Meta-Harness Inventory — Proposer Specification

Run ONE iteration of harness evolution. Do all work in the main session — do NOT delegate to subagents.

**You do NOT run benchmarks.** You analyze traces, prototype changes, and implement new candidate systems. The outer loop handles evaluation.

## CRITICAL CONSTRAINTS

- You MUST produce **2 new candidates** every iteration.
- Do NOT write "no improvement possible" or abort early. ALWAYS complete all steps.
- Each candidate must have a **falsifiable hypothesis** targeting a different mechanism.

### Anti-parameter-tuning rules

The most common failure mode: candidates that only change numeric thresholds in `AnalystConfig` (pipe_overfill_ratio, trend_gap_threshold, z_score_threshold, etc.) without changing any logic. These almost always regress or tie.

**Good candidates change a fundamental mechanism:**
- A new decision tree in `SYSTEM_PROMPT` (e.g., different branching logic, new decision heuristics)
- A new Analyst signal or computation (e.g., exponential smoothing, change-point detection, lead time estimation)
- A new architectural pattern (e.g., Reviewer with different review criteria, Decider with multi-round deliberation)
- A new memory strategy (e.g., sliding window insight aggregation, forgetting mechanism, pattern library)
- A new OR override logic (e.g., conditional trust based on signal consistency, ensemble weighting)

**Bad candidates just tune numbers.** If the logic in the prompt is identical to the base except for thresholds (15% → 20%, 4 periods → 5 periods, ±50% → ±40%), rewrite with a genuinely novel mechanism.

**Combining mechanisms is valid.** Take the decision tree from candidate_A and the pipeline logic from candidate_B. Cross-architecture inspiration is encouraged — an H1 insight can be re-expressed in H2 format.

**Diversify axes across iterations:**
- Axis A: Decision tree logic (TRUST vs SHIFT branching, step ordering)
- Axis B: Analyst signal design (new computed features, detection algorithms)
- Axis C: Reviewer strategy (approval criteria, adjustment aggressiveness)
- Axis D: Memory architecture (what to remember, when to forget)
- Axis E: OR relationship (trust calibration, ensemble methods)
- Axis F: Risk management (pipeline handling, uncertainty quantification)

If the last 3 iterations all explored the same axis, pick different ones.

### Anti-overfitting rules

- **No instance-specific hints.** Do NOT mention "p01_stationary", "p07_seasonal", "L=0", "L=4" in any code, prompt, or comment.
- **No hardcoded knowledge** about specific demand patterns. The system must be general-purpose.
- **General patterns are OK.** Rules like "trending demand requires sustained evidence" or "high variance ≠ mean shift" apply broadly.
- **Parameter values can differ** if driven by a new mechanism, not blind tuning.

### Framework immutability — CRITICAL

- **NEVER modify core framework files.** This includes: `h2/analyst.py`, `h2/decider.py`, `h2x/reviewer.py`, `h2x/memory.py`, `h2u/h2u_evaluator.py`, `h2u/h2u_runner.py`, `config.py`, `proposer.py`, `validator.py`, `trace_store.py`, `reporter.py`.
- **New Analyst signals go in candidate files.** If you need a new `enable_*` config field or computation, add a standalone function to the candidate's `analyst_config.py` or `decider_prompt.py`. Do NOT edit `h2/analyst.py` to add new `AnalystConfig` fields.
- **Candidate directories are the ONLY write targets.** Write ONLY to `candidates/candidate_XXX/` and `logs/evolution/pending_eval.json`.

## WORKFLOW

### Step 0: Analyze

1. Read **all** state files:
   - `logs/evolution/evolution_summary.jsonl` — every candidate's NR scores per iteration
   - `traces/trace_store/<candidate_id>/<instance_label>.json` — per-period decision traces with full rationales
   - `traces/trace_store_*/` — check all trace store variants (trace_store_h2, trace_store_h2x, etc.)
   - `config.py` — holdout instances, N_PERIODS, evaluator settings

2. Identify failure patterns:
   - Which instances score lowest? Read their full period-by-period traces.
   - At what periods does the LLM deviate from OR? What was the rationale? Was it justified?
   - Are there systematic errors (always overriding up on noise, missing pipeline signals, etc.)?

3. Formulate **2 hypotheses**, each targeting a different mechanism. Each must be falsifiable: "Adding mechanism X will improve NR on instances with property Y because Z."

### Step 1: Prototype — MANDATORY

Do NOT skip this step. Candidates that skip prototyping almost always have bugs or produce no improvement.

For each hypothesis:
1. Write a test script in `/tmp/` that exercises the core logic in isolation.
2. Pull real trace data from `traces/trace_store/*/<instance>.json` to test against.
3. Try 2-3 variants. Compare. Pick the best before implementing.
4. Delete test scripts when done.

### Step 2: Implement

For each of the 3 candidates:

1. **Determine architecture and base.** Choose the architecture (H1/H2/H2X) that best fits the hypothesis. Find the top-performing candidate in that architecture as your copy base.

2. **Create candidate directory.** New directory: `candidates/candidate_<next_id>/`. Use the next available 3-digit ID.

3. **Copy base files, then modify.** Copy the base candidate's files, then make targeted changes for the new mechanism.

4. **Self-critique (mandatory):** After implementing, re-read the files and ask:
   - Does this introduce a genuinely NEW mechanism, or just tune parameters?
   - Is the hypothesis falsifiable — could evaluation disprove it?
   - Would this work on a completely different set of instances?

5. **Validate:** Run the import check for the architecture.

### Step 3: Write pending_eval.json

Write to the path specified in the task prompt:

```json
{
  "iteration": <N>,
  "architecture": "H1|H2|H2X|H2U",
  "candidates": [
    {
      "name": "candidate_<id>",
      "architecture": "H1|H2|H2X|H2U",
      "hypothesis": "<falsifiable claim about what will improve>",
      "axis": "exploitation|exploration",
      "base_candidate": "<which candidate this builds on>",
      "components": ["tag1", "tag2"]
    }
  ]
}
```

Output: `CANDIDATES: candidate_<id1>, candidate_<id2>, candidate_<id3>`

## ARCHITECTURE FILE FORMATS

### H1 Architecture — Pure LLM Prompt

Single file: `candidates/<candidate_id>/system_prompt.py`

```python
"""
<candidate_id> — <one-line description>.
"""
SYSTEM_PROMPT = """<full system prompt for LLM decider>"""
```

The prompt must output valid JSON with keys: `rationale`, `short_rationale_for_human`, `carry_over_insight`, `action` (mapping item_id to integer order quantity).

Template variables available: `{item_id}`, `{anticipated_lead_time}`, `{p}`, `{h}`, `{critical_fractile}`, `{z_star}`, `{or_recommended}`, `{or_cap}`. All others must be computed by the LLM from observation context.

### H2 Architecture — Analyst + Decider

Two files:

**`candidates/<candidate_id>/analyst_config.py`:**
```python
"""
<candidate_id> — <one-line description>.
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=5,
    trend_evidence_periods=4,
    trend_gap_threshold=0.15,
    volatility_cv_threshold=0.5,
    or_bias_threshold=0.12,
    iid_window=10,
    iid_trend_threshold=0.10,
    z_score_threshold=3.0,
    sustained_deviation_periods=4,
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
```

Note: When changing Analyst behavior, prefer adding a NEW module (new enable_* + computation) over tuning existing thresholds. Threshold-only changes are parameter variants.

**`candidates/<candidate_id>/decider_prompt.py`:**
```python
"""
<candidate_id> — <one-line description>.
"""
SYSTEM_PROMPT = """<full decider prompt>"""
```

The Decider receives Analyst signals (pipeline, demand, OR audit, alerts) as FACT. It exercises judgment via a decision tree. Output format: same JSON schema as H1.

### H2X Architecture — Memory + Decider + Reviewer

Four files:

**`candidates/<candidate_id>/analyst_config.py`** — Same format as H2.

**`candidates/<candidate_id>/decider_prompt.py`** — Same format as H2, but may reference memory window content.

**`candidates/<candidate_id>/reviewer_prompt.py`:**
```python
"""
<candidate_id> — <one-line description>.
"""
SYSTEM_PROMPT = """<full reviewer prompt>"""
```

The Reviewer sees the Decider's draft order + rationale plus the same analysis context. It outputs JSON with: `approved` (bool), `final_order` (int), `adjustment_reason` (str), `risk_flag` ("safe"|"caution"|"override").

**`candidates/<candidate_id>/memory_config.py`:**
```python
"""
<candidate_id> — <one-line description>.
"""
MEMORY_WINDOW = 5  # periods of history to retain in memory buffer
```

### H2U Architecture — Unified Analyst + Memory + Decider + Reviewer

Four files — the most complete architecture combining H2's Analyst with H2X's Memory/Reviewer:

**`candidates/<candidate_id>/analyst_config.py`** — Same format as H2. H2-optimized thresholds (lower trend detection, faster OR bias detection).

**`candidates/<candidate_id>/decider_prompt.py`:**
```python
SYSTEM_PROMPT = """<decider prompt with Analyst signal trust + 4-step decision process + memory table awareness>"""
```
The Decider receives Analyst signals as FACT (pipeline/trend/OR trust are computed deterministically) plus a structured memory table. Key template variables: `{item_id}`, `{anticipated_lead_time}`, `{p}`, `{h}`, `{critical_fractile}`, `{z_star}`.

**`candidates/<candidate_id>/reviewer_prompt.py`:**
```python
SYSTEM_PROMPT = """<reviewer prompt with Analyst signal cross-check>"""
```
The Reviewer receives explicit Analyst signals (pipe_status, trend_dir, trust_level) for cross-checking the Decider's draft. Can detect contradictions like "large order on OVERFILLED pipeline."

**`candidates/<candidate_id>/memory_config.py`:**
```python
MEMORY_WINDOW = 5  # periods of structured history
```

H2U is the evolutionary target — optimize all 4 files jointly. When modifying one file, consider consistency with the others (e.g., changing Analyst thresholds should align with Decider's trust logic).

## EVALUATION METRIC

**Normalized Reward (NR):** `NR = total_reward / (p * total_demand)`

- total_reward = sum over periods of (Profit × units_sold - HoldingCost × ending_inventory)
- p = unit profit (selling price - cost)
- total_demand = sum of demand across all periods
- Higher NR is better. NR is a unitless efficiency score.
- Baseline OR (no LLM) typically scores 0.70-0.75 on stationary instances, lower on non-stationary.

## DIRECTORY STRUCTURE

- `candidates/` — All candidate implementations (read to analyze, write to create new)
- `traces/trace_store/<candidate_id>/` — Per-instance JSON traces with period-by-period decisions
- `traces/trace_store_h2/` — H2 evaluation traces
- `traces/trace_store_h2x/` — H2X evaluation traces
- `traces/trace_store_h2_chain/` — H2 chain evaluation traces
- `traces/trace_store_h2x_chain/` — H2X chain evaluation traces
- `traces/trace_store_h2u/` — H2U evaluation traces
- `logs/evolution/evolution_summary.jsonl` — All evaluated candidates with NR scores
- `logs/evolution/claude_sessions/` — Claude Code session logs per iteration
- `config.py` — Holdout instances, N_PERIODS, evaluator LLM config
- `h2/analyst.py` — AnalystConfig dataclass + AnalystReport + compute logic
- `runner.py` — H1 runner
- `h2/h2_runner.py` — H2 runner

## TRACE FILE FORMAT

Each trace file at `traces/trace_store/<candidate_id>/<instance_label>.json`:

```json
{
  "instance_label": "...",
  "item_id": "...",
  "lead_time": 0 or 4,
  "p": <profit>,
  "h": <holding_cost>,
  "rho": 0.80,
  "total_demand": <sum>,
  "total_reward": <sum>,
  "normalized_reward": <NR>,
  "periods": [
    {
      "period": 0..19,
      "demand": <int>,
      "ordered": <int>,
      "sold": <int>,
      "reward": <float>,
      "or_recommended": <int>,
      "llm_rationale": "<full rationale>",
      "llm_short_rationale": "<summary>",
      "carry_over_insight": "<insight>"
    }
  ]
}
```

Key period fields for analysis:
- `ordered` vs `or_recommended`: when does LLM deviate from OR? Is it justified?
- `llm_rationale`: the LLM's own reasoning — look for systematic errors (e.g., misreading pipeline, overreacting to noise)
- `reward`: immediate reward this period — trace cumulative patterns
- `carry_over_insight`: what the LLM chose to remember — does this memory help or hurt?

## EVOLUTION SUMMARY FORMAT

One JSON object per line in `logs/evolution/evolution_summary.jsonl`:

```json
{"iteration": 1, "candidate_id": "candidate_012", "architecture": "H2X", "mean_nr": 0.7523, "axis": "exploration", "hypothesis": "Exponential smoothing for demand estimation improves trend detection latency"}
```

Fields: `iteration`, `candidate_id`, `architecture`, `mean_nr`, `axis` (exploitation/exploration), `hypothesis`.
