# OR2LLM Meta-Harness: AI Agents for Inventory Control

> Reproducing the paper "AI Agents for Inventory Control" — fixed lead-time modes (L=0, L=4) with DeepSeek Chat as the LLM backend, plus a meta-optimization framework for automated prompt engineering.

---

## Paper → Code Mapping

```
Paper Section                        Code Module
─────────────                        ──────────
Section 3: Problem Formulation  →   env.py          (InventoryEnv, state transitions)
Appendix A: OR Baseline         →   or_baseline.py  (Capped Base-stock Policy)
Appendix B: System Prompt       →   agent.py        (SYSTEM_PROMPT_TEMPLATE)
Section 3.1: LLM Agent Design   →   agent.py        (ORToLLMAgent, UserMessageBuilder)
Section 4: Experimental Setup   →   data.py         (InstanceLoader, InventoryBench 480 instances)
Section 4.2: Evaluation Metrics →   data.py         (normalized_reward)
```

---

## System Architecture

```text
╔═══════════════════════════════════════════════════════════════════════╗
║                   OR2LLM Inventory Control Framework                  ║
║          Reproducing "AI Agents for Inventory Control"                ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  ┌─────────────────────────────────────────────────────────────┐     ║
║  │               run.py  Universal Experiment Entry Point       │     ║
║  │  python run.py --index <1-480> --periods <T> [--verbose]    │     ║
║  └─────┬──────────────┬────────────────────┬───────────────────┘     ║
║        │              │                    │                          ║
║        ▼              ▼                    ▼                          ║
║  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐           ║
║  │  Data     │  │  Inventory   │  │  OR→LLM Agent        │           ║
║  │  Loading  │  │  Environment │  │                      │           ║
║  │  data.py  │  │  env.py      │  │  agent.py            │           ║
║  │           │  │              │  │                      │           ║
║  │ Instance  │  │ InventoryEnv │  │ ORToLLMAgent         │           ║
║  │ Loader    │  │              │  │  ├─ ORBaseline       │           ║
║  │           │  │ .step(q)     │  │  │  (or_baseline.py) │           ║
║  │ .load()   │  │ .get_obs()   │  │  ├─ UserMsgBuilder   │           ║
║  │           │  │              │  │  ├─ DeepSeek API     │           ║
║  │ normalized│  │ InTransit    │  │  └─ ResponseParser   │           ║
║  │ _reward() │  │ Order,       │  │                      │           ║
║  │           │  │ PeriodResult │  │                      │           ║
║  └─────┬────┘  └──────┬───────┘  └──────────┬───────────┘           ║
║        │              │                     │                        ║
║        │     ┌────────┴────────┐            │                        ║
║        │     │  Per-Period Loop│◀───────────┘                        ║
║        │     │                │                                      ║
║        │     │ ① obs = env.get_initial_observation()                 ║
║        │     │ ② q = agent.decide(obs, context)                      ║
║        │     │     ├─ or_rec = ORBaseline.compute(history, oh, it)   ║
║        │     │     ├─ msg = UserMessageBuilder.build(obs, or, ins)   ║
║        │     │     ├─ json = DeepSeek(messages=[sys, msg])           ║
║        │     │     └─ parsed = ResponseParser.parse(json, item_id)   ║
║        │     │ ③ result = env.step(q)                                ║
║        │     │     ├─ Place order: InTransitOrder(t, q, L)           ║
║        │     │     ├─ Arrivals: sum(o for o if o.arrives@t)          ║
║        │     │     ├─ Sales: sold = min(d_t, on_hand)                ║
║        │     │     └─ Reward: R = p·sold - h·end_inv                 ║
║        │     │ ④ obs = result["observation"]                         ║
║        │     │ ⑤ if !done, goto ②                                   ║
║        │     └────────────────────────────┘                          ║
║        │                                                             ║
║        ▼                                                             ║
║  ┌──────────────────────────────────────────┐                        ║
║  │  Evaluation Output                        │                       ║
║  │  NR = total_reward / (p × sum(demand))    │                       ║
║  │  → run_result_{index}.json                │                       ║
║  └──────────────────────────────────────────┘                        ║
║                                                                       ║
╠═══════════════════════════════════════════════════════════════════════╣
║  Paper Reference                                                       ║
╠═══════════════════════════════════════════════════════════════════════╣
║  §3  Problem Formulation     → env.py      InventoryEnv, step()      ║
║  §3.1 LLM Agent Design       → agent.py    ORToLLMAgent, decide()    ║
║  App A OR Baseline           → or_baseline.py ORBaseline.compute()   ║
║  App B System Prompt         → agent.py    SYSTEM_PROMPT_TEMPLATE    ║
║  §4   Experimental Setup     → data.py     InstanceLoader, 480 insts ║
║  §4.2 Evaluation             → data.py     normalized_reward()       ║
║  Fig 2 Agent Architecture    → below       Per-period loop A-B-C-D   ║
╚═══════════════════════════════════════════════════════════════════════╝
```

---

## Algorithm Architecture (Paper Figure 2)

```text
                   ┌──────────────────────────────┐
                   │   System Prompt (Appendix B)  │
                   │   p, h, L → q, z*, cap        │
                   └──────────────┬───────────────┘
                                  │ Injected each period
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Per-Period Agent Decision Loop (Fig. 2 in paper)               │
│                                                                 │
│  Input: Observation o_t                                          │
│        ├── on_hand_inventory                                    │
│        ├── in_transit_orders[]                                  │
│        ├── demand_history[]                                     │
│        └── last_period_conclude                                 │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Step A: OR Baseline (Appendix A)                     │      │
│  │   d̄ = mean(history)    s_d = std(history)            │      │
│  │   μ̂ = (1+L)·d̄          σ̂ = √(1+L)·s_d               │      │
│  │   B = μ̂ + z*·σ̂         z* = Φ⁻¹(p/(p+h))            │      │
│  │   cap = μ̂/(1+L) + Φ⁻¹(0.95)·σ̂/√(1+L)               │      │
│  │   q_or = max(0, min(B - IP, cap))                    │      │
│  └──────────────────────┬───────────────────────────────┘      │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Step B: User Message Assembly                        │      │
│  │   Part 1: carry_over_insights (cross-period memory)   │      │
│  │   Part 2: current observation                        │      │
│  │   Part 3: OR recommendation (all statistics)          │      │
│  └──────────────────────┬───────────────────────────────┘      │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Step C: LLM Inference (DeepSeek Chat)                │      │
│  │   Input: system_prompt + user_message                │      │
│  │   Output: JSON {rationale, short_rationale,          │      │
│  │                 carry_over_insight, action}          │      │
│  │   Fallback: parse failure → use q_or                 │      │
│  └──────────────────────┬───────────────────────────────┘      │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Step D: State Transition (env.step)                  │      │
│  │   1. Register order (InTransitOrder)                 │      │
│  │   2. Process arrivals (orders where arrival == t)    │      │
│  │   3. Fulfill demand (sold = min(d_t, on_hand))       │      │
│  │   4. Compute reward (R_t = p·sold - h·ending_inv)    │      │
│  │   5. Produce o_{t+1}                                 │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                 │
│  Output: order_quantity q_t, next_observation o_{t+1}, reward   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Per-File I/O Specification

### `data.py` — Data Loading Layer

| Function/Class | Input | Source | Output | Consumer |
|---------------|-------|--------|--------|----------|
| `InstanceLoader(instance_dir)` | Directory path str | run.py CLI | loader object | run.py |
| `.load()` | train.csv + test.csv | InventoryBench filesystem | `config` dict (9 fields) | run.py → env + agent init |
| `_read_csv(path)` | CSV path (with git-lfs header) | same as above | pandas DataFrame | `.load()` internal |
| `normalized_reward(R, p, Σd)` | total_reward, p, total_demand | env + config | float ∈ [0,1] | terminal output + JSON |
| `build_instance_index(base_dir)` | benchmark root dir | filesystem | list[dict] (480 entries) | run.py --list |
| `run_single_instance(dir, model, periods)` | instance dir + model + truncated periods | external call | dict (result summary) | save_results() |
| `save_results(results, path)` | result dict + output path | caller | JSON file | disk |

### `env.py` — Inventory Environment Layer

| Method | Input | Source | Output | Consumer |
|--------|-------|--------|--------|----------|
| `InventoryEnv.__init__` | demands[], L, p, h, initial_demands[] | InstanceLoader.load() | env object (t=1, on_hand=0) | run.py |
| `get_initial_observation()` | none (reads internal state) | — | `obs` dict (7 fields) | agent.decide() |
| `step(q_t)` | order quantity int | agent.decide() | `{period, reward, done, observation}` | run.py main loop |
| `_build_observation()` | internal state (t, on_hand, in_transit, history) | env self | `obs` dict | step() / get_initial_observation() |
| `critical_fractile` (property) | — | p, h | ρ = p/(p+h) | display only |

**Sub-steps within `step()`:**

| Sub-step | Operation | State Affected |
|----------|-----------|---------------|
| ① Place order | `InTransitOrder(period_placed=t, quantity=q, lead_time=L)` | `in_transit[]` append |
| ② Process arrivals | Iterate `in_transit[]`, sum orders where `arrival_period == t` | `on_hand += arrivals`, remove arrived orders |
| ③ Fulfill demand | `sold = min(demands[t-1], on_hand)` | `on_hand -= sold` |
| ④ Compute reward | `R = p*sold - h*ending_inv` | `total_reward += R`, `PeriodResult` appended |
| ⑤ Record | `demand_history.append(d_t)` | `demand_history[]` grows |

### `or_baseline.py` — OR Baseline Layer

| Method | Input | Source | Output | Consumer |
|--------|-------|--------|--------|----------|
| `ORBaseline.__init__(L, p, h)` | L, p, h | config | `rho`, `z_star=Φ⁻¹(ρ)`, `z_cap=Φ⁻¹(0.95)` | agent internal |
| `.compute(demand_history, on_hand, in_transit_total)` | demand history [], on-hand, in-transit total | obs dict | `ORRecommendation` (12 fields) | agent.decide() → UserMessageBuilder + fallback |

**`compute()` internal chain:**

```text
demand_history[n]  ──▶  d̄ = mean, s_d = std(ddof=1)
                         │
                         ├──▶ μ̂ = (1+L)·d̄
                         ├──▶ σ̂ = √(1+L)·s_d
                         │
                         ├──▶ B = μ̂ + z*·σ̂
                         ├──▶ IP = on_hand + in_transit_total
                         ├──▶ cap = μ̂/(1+L) + z_cap·σ̂/√(1+L)
                         │
                         └──▶ q = max(0, min(B - IP, cap))
```

### `agent.py` — Agent Decision Layer

| Method/Class | Input | Source | Output | Consumer |
|-------------|-------|--------|--------|----------|
| `ORToLLMAgent.__init__` | item_id, L, p, h, model, api_key | config + defaults | agent (with system_prompt, client, ORBaseline) | run.py |
| `_build_system_prompt()` | item_id, L, p, h (self) | `__init__` | Formatted System Prompt string | `_call_llm()` |
| `decide(obs, context)` | obs dict + SKU description | env.get_obs() + config | order quantity int | env.step() |
| `_call_llm(user_msg, retries)` | user_message str | UserMessageBuilder | LLM JSON string | ResponseParser |
| `run_episode(env, context)` | env + context | external | (orders[], total_reward, history[]) | run_single_instance() |

**`decide()` internal sub-steps:**

| Sub-step | Method/Class | Input | Output |
|----------|-------------|-------|--------|
| OR recommendation | `ORBaseline.compute()` | demand_history, on_hand, in_transit_total | `ORRecommendation` |
| Message assembly | `UserMessageBuilder.build()` | obs, or_rec, carry_over_insights, item_id, context | 3-part user_message str |
| LLM inference | `_call_llm()` | user_message | LLM JSON str |
| Parse | `ResponseParser.parse()` | JSON str, item_id | `AgentResponse` |
| Fallback | try/except | parse error | downgrade to `AgentResponse(q=or_rec.recommended_order)` |
| Insight update | `carry_over_insights = parsed.carry_over_insight` | LLM insight text | next period injection |

**`UserMessageBuilder.build()` output structure:**

```text
Part 1 (when insights exist): ═══ CARRY-OVER INSIGHTS ═══
                   LLM-discovered new trends/changes from prior period

Part 2:            PERIOD 3 / 50
                   === CURRENT STATUS ===
                   Item: chips(Regular)
                   On-hand inventory: 50
                   In-transit orders (117 total):
                     Period 3: 117 units (lead_time=4, waited 1 periods)
                   === LAST PERIOD CONCLUDE ===
                   Period 2 conclude: ordered=120, arrived=0, ...
                   Recent demand history (last 10 periods): [...]
                   All demand history (12 periods): [...]

Part 3:            ═══ OR ALGORITHM RECOMMENDATIONS ═══
                   Demand mean (d_bar): 100.0
                   Demand std (s_d): 15.0
                   ...
                   OR recommended order: 73
```

**`AgentResponse` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `rationale` | str | LLM full reasoning process |
| `short_rationale_for_human` | str | 1-3 sentence summary (for logging) |
| `carry_over_insight` | str | Cross-period insight (empty = "no new findings") |
| `order_quantity` | int | Final ordering decision |
| `raw_json` | dict | LLM raw JSON (for debugging) |

---

## Paper Formula → Code Mapping

| Paper Symbol | Meaning | Code Variable | Location |
|-------------|---------|---------------|----------|
| L | Fixed lead time | `lead_time` | `InventoryEnv.__init__` |
| p | Unit sales profit | `p` | `InventoryEnv.__init__` |
| h | Unit holding cost | `h` | `InventoryEnv.__init__` |
| ρ = p/(p+h) | Critical fractile | `critical_fractile` / `rho` | `InventoryEnv` property / `ORBaseline.__init__` |
| z* = Φ⁻¹(ρ) | Safety factor | `z_star` | `ORBaseline.__init__` |
| d̄ | Demand sample mean | `d_bar` | `ORBaseline.compute()` |
| s_d | Demand sample std | `s_d` | `ORBaseline.compute()` |
| μ̂ = (1+L)·d̄ | Lead-time demand mean | `mu_hat` | `ORBaseline.compute()` |
| σ̂ = √(1+L)·s_d | Lead-time demand std | `sigma_hat` | `ORBaseline.compute()` |
| B = μ̂ + z*·σ̂ | Base-stock level | `base_stock_level` / `B` | `ORBaseline.compute()` |
| IP = on_hand + pipeline | Inventory position | `inventory_position` / `IP` | `ORBaseline.compute()` |
| cap | Order cap | `order_cap` / `cap` | `ORBaseline.compute()` |
| q_t | Decision order quantity | `recommended_order` / `order_quantity` | `ORRecommendation` / `AgentResponse` |
| R_t = p·sold - h·end_inv | Single-period reward | `daily_reward` | `PeriodResult` |
| NR = ΣR_t / (p·Σd_t) | Normalized reward | `normalized_reward()` | `data.py` |

---

## Meta-Harness: Prompt Optimization Framework

Beyond the core agent, this repo includes a **meta-optimization framework** (`meta_harness/`) that uses Claude Code to automatically search for better system prompts.

### Architecture Evolution

| Architecture | Agents | LLM Calls/Period | Key Innovation |
|-------------|--------|------------------|----------------|
| H1 | 1 | 1× | Single-agent system prompt search |
| H2 | 2 | 1× | Analyst (Python compute) + Decider (LLM judgment) separation |
| H2X | 3 | 2× | Structured Memory Buffer + Reviewer (four-eyes principle) |
| H2M | 2 (dialog) | 2-3× | Conversational multi-agent, Decider has Last Word |

### H1 → H2 → H2X → H2M Causal Chain

- **H1 baseline**: Single prompt handles both computation AND judgment → LLM hallucinates calculations, collapses on L=4 scenarios (NR=29% on variance change)
- **H2**: Separates compute (Python Analyst: pipeline status, trend direction, OR trust) from judgment (LLM Decider) → baseline jumps +9.8% without any optimization
- **H2X**: Replaces single-string `carry_over_insight` with structured table of last 5 periods (demand/order/sold/reward/pipeline/trend) + Reviewer sanity check before execution
- **H2M**: Upgrades one-way review to conversational multi-agent — Decider proposes, Reviewer critiques, Decider revises with final authority (matches enterprise reality)

Key insight: **Architecture determines the baseline (lower bound) and robustness; optimization determines the peak (upper bound).**

---

## Quick Start

### Requirements

```bash
pip install numpy pandas scipy openai plotly
```

### Data Preparation

```bash
# Clone InventoryBench dataset (requires Git LFS)
git clone git@github.com:TianyiPeng/InventoryBench.git InventoryBench-main
cd InventoryBench-main
git sparse-checkout set benchmark/synthetic_trajectory/lead_time_0 benchmark/synthetic_trajectory/lead_time_4
git lfs pull
```

### Running

```bash
# List all 480 instances
python run.py --list

# Run a single instance (default 50 periods)
python run.py --index 1

# Specify period count + verbose output
python run.py --index 1 --periods 30 -v

# Full trace (Steps A/B/C/D detailed log)
python run.py --index 1 --periods 20 --trace --trace-file trace.log

# Generate interactive Plotly dashboard
python run.py --index 1 --periods 30 --plot

# Trace + Dashboard + Report combined
python run.py --index 1 --periods 30 --trace --plot --report
```

### Output Files

| Flag | Output File | Purpose |
|------|------------|---------|
| `--trace --trace-file FILE` | `.log` text | Full Step A/B/C/D decision trace |
| `--plot` | `dashboard_<N>.html` | Interactive Plotly charts + formulas (MathJax) |
| `--report` | `report_<N>.md` | Markdown report: LaTeX equations + per-period decision table + reasoning timeline + OR parameter evolution |
| default | `run_result_<N>.json` | Structured JSON result data |

### Dashboard Charts

`--plot` generates a self-contained Plotly HTML dashboard with 4 charts:

| # | Chart | Interaction | Presentation Value |
|---|-------|-------------|-------------------|
| 1 | **Decision Comparison** | hover for values | LLM vs OR order quantity, Δ bars show override direction |
| 2 | **Inventory Waterfall** | hover for values | On-hand + arrivals vs demand, red X marks stockout points |
| 3 | **Cumulative Reward Curve** | hover for values | Cumulative + per-period reward, stockout ⚠ markers |
| 4 | **Reasoning Insight Timeline** | hover for LLM reasoning | Blue dots = LLM rationale, gold stars = cross-period insight generation |

Dashboard header shows 6 KPIs: Total Reward / Normalized / Periods / LLM Overrides OR / Stockouts / Insights

### Programmatic Usage

```python
from or_to_llm import InstanceLoader, InventoryEnv, ORToLLMAgent, normalized_reward

loader = InstanceLoader("InventoryBench-main/benchmark/synthetic_trajectory/lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_low")
config = loader.load()

env = InventoryEnv(
    demands=config["test_demands"][:50],
    lead_time=config["lead_time"],
    p=config["p"],
    h=config["h"],
    initial_demands=config["initial_demands"],
)

agent = ORToLLMAgent(
    item_id=config["item_id"],
    anticipated_lead_time=config["lead_time"],
    p=config["p"],
    h=config["h"],
)

orders, total_reward, history = agent.run_episode(env, context=config["description"])
nr = normalized_reward(total_reward, p=config["p"], total_demand=sum(config["test_demands"][:50]))
print(f"Normalized Reward: {nr:.4f}")
```

### Running Meta-Harness

```bash
# Run H1 optimization (outer loop with Claude Code proposer)
python -m meta_harness.runner
```

---

## Project File Structure

```
core/
├── run.py                          # Universal CLI experiment script
├── compare.py                      # Comparison experiment (Original vs Harness)
├── README.md                       # This document
├── or_to_llm/                      # Core agent package
│   ├── __init__.py                 # Aggregate exports
│   ├── env.py                      # Inventory environment (InventoryEnv, InTransitOrder, PeriodResult)
│   ├── or_baseline.py              # OR baseline strategy (ORBaseline, ORRecommendation)
│   ├── agent.py                    # LLM agent (ORToLLMAgent, System Prompt, ResponseParser)
│   ├── data.py                     # Data loading & evaluation (InstanceLoader, normalized_reward)
│   ├── reviewer.py                 # ReviewerAgent for auditing LLM decisions
│   ├── trace.py                    # TraceLogger for Step A/B/C/D tracing
│   ├── visualize.py                # Plotly DashboardBuilder
│   ├── report.py                   # Markdown ReportBuilder
│   └── harness/                    # Sub-package: Harness pipeline (factory, runner, services)
├── meta_harness/                   # Meta-optimization framework
│   ├── runner.py                   # Outer-loop orchestrator (MetaHarnessRunner)
│   ├── evaluator.py                # Candidate evaluator against holdout instances
│   ├── proposer.py                 # Claude Code subprocess proposer
│   ├── validator.py                # H1/H2/H2X candidate validator
│   ├── trace_store.py              # Trace persistence + query
│   ├── reporter.py                 # HTML report generator
│   ├── narrative.py                # H1→H2→H2X→H2M causal chain narrative
│   ├── config.py                   # Centralized configuration
│   ├── claude_wrapper.py           # Claude CLI programmatic wrapper
│   ├── h2/                         # H2 architecture (Analyst + Decider)
│   ├── h2x/                        # H2X architecture (+ Memory + Reviewer)
│   ├── h2m/                        # H2M architecture (+ Conversation)
│   ├── h2u/                        # H2U architecture
│   ├── candidates/                 # Prompt candidates (000-017, h2_*, h2x_*, h2u_*)
│   └── scripts/                    # Evaluation and diagnostics scripts
└── InventoryBench-main/            # Dataset (git clone separately, not in repo)
    └── benchmark/synthetic_trajectory/
        ├── lead_time_0/            # L=0: 240 instances
        └── lead_time_4/            # L=4: 240 instances
```

---

## FAQ

**Q: Why only L=0 and L=4?**
The paper's main experiments use these two fixed lead times. Stochastic lead time (`lead_time_stochastic`) is not yet adapted.

**Q: How are the 480 instances structured?**
10 demand patterns × 4 variants × 3 critical fractiles (ρ) × 2 random seeds × 2 lead times = 480.

**Q: What happens when LLM inference fails?**
On parse failure, the agent automatically falls back to the OR baseline recommendation. Network errors retry 3 times with 5/10/15 second intervals.

**Q: How do I switch models?**
`python run.py --index 1 --model deepseek-chat`. Any OpenAI-compatible API works. Set `EVAL_API_KEY` and `EVAL_BASE_URL` environment variables.
