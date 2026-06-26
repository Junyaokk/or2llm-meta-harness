"""Evaluate H2M v2 (candidate_016) on 10 holdout instances."""
import os, sys, time, json
sys.path.insert(0, "/Users/junyaoyu/Downloads/nio")
from pathlib import Path
from meta_harness.h2m.h2m_evaluator import H2MEvaluator
from meta_harness.trace_store import TraceStore

ALL_10_INSTANCES = [
    # Original 5
    {"path": "lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_med", "label": "p01_stationary_L0", "description": "Stationary IID, L=0"},
    {"path": "lead_time_0/p04_increasing_trend/v1_linear_100t/r1_med", "label": "p04_increasing_L0", "description": "Increasing linear trend, L=0"},
    {"path": "lead_time_4/p07_seasonal/v1_period10_amp30/r1_med", "label": "p07_seasonal_L4", "description": "Seasonal period=10, L=4"},
    {"path": "lead_time_0/p08_multi_changepoint/v1_up_then_down/r1_med", "label": "p08_changepoint_L0", "description": "Changepoint up-then-down, L=0"},
    {"path": "lead_time_4/p06_variance_change/v1_normal_to_uniform/r1_med", "label": "p06_variance_L4", "description": "Variance change, L=4"},
    # New 5
    {"path": "lead_time_0/p02_mean_increase/v1_100to200/r1_med", "label": "p02_meanshift_up_L0", "description": "Mean increase 100→200, L=0"},
    {"path": "lead_time_0/p03_mean_decrease/v1_100to50/r1_med", "label": "p03_meanshift_down_L0", "description": "Mean decrease 100→50, L=0"},
    {"path": "lead_time_0/p05_decreasing_trend/v1_200_minus_3t/r1_med", "label": "p05_decreasing_L0", "description": "Decreasing trend, L=0"},
    {"path": "lead_time_4/p09_temp_spike_dip/v1_temp_surge/r1_med", "label": "p09_tempsurge_L4", "description": "Temporary surge, L=4"},
    {"path": "lead_time_4/p10_autocorrelated/v1_phi_0_7/r1_med", "label": "p10_autocorr_L4", "description": "Autocorrelated phi=0.7, L=4"},
]

cand_dir = Path(__file__).resolve().parent / "candidates" / "candidate_016"
store = TraceStore(Path(__file__).resolve().parent.parent / "traces" / "trace_store_h2m_10inst")

evaluator = H2MEvaluator(
    candidate_dir=cand_dir,
    holdout_configs=ALL_10_INSTANCES,
    n_periods=20,
    model="deepseek-chat",
    api_key=os.getenv("EVAL_API_KEY", ""),
    base_url="https://api.deepseek.com/v1",
)

t0 = time.time()
result = evaluator.evaluate("candidate_016")
elapsed = time.time() - t0

store.save(result)

print(f"\n{'='*60}")
print(f"H2M (candidate_016) on 10 instances — DONE")
print(f"Mean NR: {result.mean_nr:.4f}  ({elapsed:.0f}s)")
for label, nr in sorted(result.per_instance_nr.items()):
    print(f"  {label}: {nr:.4f}")

summary = {
    "architecture": "H2M",
    "candidate": "candidate_016",
    "n_instances": 10,
    "mean_nr": result.mean_nr,
    "per_instance_nr": result.per_instance_nr,
    "elapsed_s": elapsed,
}
json.dump(summary, open(store.store_dir / "summary.json", "w"), indent=2)
print(f"Summary: {store.store_dir / 'summary.json'}")
