"""
Diagnose: what Analyst signals does the Decider receive for p04 (increasing trend)?
Print key periods to understand if trend is being detected and used.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from or_to_llm import InventoryEnv, InstanceLoader
from or_to_llm.or_baseline import ORBaseline
from meta_harness.h2.analyst import Analyst, AnalystConfig

# Use our H2 baseline config
from meta_harness.candidates.candidate_h2_000.analyst_config import ANALYST_CONFIG

# Find p04 instance
inst_dir = Path(__file__).resolve().parent.parent / "InventoryBench-main" / "benchmark" / \
           "synthetic_trajectory" / "lead_time_0" / "p04_increasing_trend" / \
           "v1_linear_100t" / "r1_med"

loader = InstanceLoader(str(inst_dir))
config = loader.load()
demands = config["test_demands"][:20]
lead_time = config["lead_time"]
p = config["p"]
h = config["h"]

env = InventoryEnv(
    demands=demands, lead_time=lead_time, p=p, h=h,
    initial_demands=config["initial_demands"],
)

analyst = Analyst(config=ANALYST_CONFIG)
or_baseline = ORBaseline(lead_time, p, h)

obs = env.get_initial_observation()
context = config.get("description", "")

# Collect a few key period snapshots
for period_idx in range(1, 21):
    or_rec = or_baseline.compute(
        demand_history=obs["demand_history"],
        on_hand=obs.get("on_hand_inventory", 0),
        in_transit_total=obs.get("in_transit_total", 0),
    )

    obs["lead_time"] = lead_time
    obs["p"] = p
    obs["h"] = h
    obs["context"] = context

    report = analyst.analyze(obs, or_rec, item_id=config["item_id"], context=context)

    # Print key periods (early and late)
    if period_idx in [1, 2, 5, 8, 10, 12, 15, 18, 20]:
        d = report.demand
        p_info = report.pipeline
        a = report.or_audit
        print(f"\n--- Period {period_idx} ---")
        print(f"Demand: {env.demands[env.t-1] if env.t <= len(env.demands) else '?'}")
        print(f"  d_bar={d.get('d_bar')} | 5p_avg={d.get('recent_5p_avg')} | gap={d.get('gap_pct'):+.1f}%")
        print(f"  trend={d.get('trend_dir')} | slope={d.get('slope_per_period'):+.3f}/p | evidence={d.get('evidence_periods')}p | R²={d.get('r_squared'):.3f}")
        print(f"  volatile={d.get('is_volatile')} (CV={d.get('cv'):.3f})")
        print(f"  pipe={p_info.get('pipe_status')} | IP={p_info.get('IP'):.0f} | B={p_info.get('B'):.0f} | room={p_info.get('room_to_order')}")
        print(f"  OR trust={a.get('trust_level')} | OR rec={or_rec.recommended_order}")
        print(f"  Recent demands: {obs['demand_history'][-5:]}")
        print(f"  Summary: {report.summary}")

    # Take a step with OR recommendation to continue
    q = or_rec.recommended_order
    result = env.step(q)
    obs = result["observation"]
