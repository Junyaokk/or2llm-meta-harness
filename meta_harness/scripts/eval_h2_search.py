"""Evaluate H2 search candidates (005–009) on 10 NEV instances."""
import os, sys, time, json
sys.path.insert(0, "/Users/junyaoyu/Downloads/nio")
from pathlib import Path
from meta_harness.h2.h2_evaluator import H2Evaluator
from meta_harness.trace_store import TraceStore

NEV_10_INSTANCES = [
    {"path": "lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_med", "label": "p01_标准件_稳态_L0"},
    {"path": "lead_time_0/p02_mean_increase/v1_100to200/r1_med", "label": "p02_新车上市_跃升_L0"},
    {"path": "lead_time_0/p03_mean_decrease/v1_100to50/r1_med", "label": "p03_老车退市_下降_L0"},
    {"path": "lead_time_0/p04_increasing_trend/v1_linear_100t/r1_med", "label": "p04_市场增长_趋势_L0"},
    {"path": "lead_time_0/p05_decreasing_trend/v1_200_minus_3t/r1_med", "label": "p05_燃油车替代_下降_L0"},
    {"path": "lead_time_0/p08_multi_changepoint/v1_up_then_down/r1_med", "label": "p08_补贴退坡_变点_L0"},
    {"path": "lead_time_4/p06_variance_change/v1_normal_to_uniform/r1_med", "label": "p06_芯片短缺_波动_L4"},
    {"path": "lead_time_4/p07_seasonal/v1_period10_amp30/r1_med", "label": "p07_季度冲刺_季节_L4"},
    {"path": "lead_time_4/p09_temp_spike_dip/v1_temp_surge/r1_med", "label": "p09_促销抢购_脉冲_L4"},
    {"path": "lead_time_4/p10_autocorrelated/v1_phi_0_7/r1_med", "label": "p10_电池排产_自相关_L4"},
]

def eval_candidate(cand_name):
    cand_dir = Path(__file__).resolve().parent / "candidates" / cand_name
    store = TraceStore(Path(__file__).resolve().parent.parent / "traces" / f"trace_store_{cand_name}_10nev")

    evaluator = H2Evaluator(
        candidate_dir=cand_dir,
        holdout_configs=NEV_10_INSTANCES,
        n_periods=20,
        model="deepseek-chat",
        api_key=os.getenv("EVAL_API_KEY", ""),
        base_url="https://api.deepseek.com/v1",
    )

    t0 = time.time()
    result = evaluator.evaluate(cand_name)
    elapsed = time.time() - t0

    store.save(result)

    summary = {
        "architecture": "H2",
        "candidate": cand_name,
        "mean_nr": result.mean_nr,
        "per_instance_nr": result.per_instance_nr,
        "elapsed_s": elapsed,
    }
    json.dump(summary, open(store.store_dir / "summary.json", "w"), indent=2)

    print(f"\n{'='*60}")
    print(f"{cand_name} — DONE  Mean NR: {result.mean_nr:.4f}  ({elapsed:.0f}s)")
    for label, nr in sorted(result.per_instance_nr.items()):
        print(f"  {label}: {nr:.4f}")

    return result.mean_nr

if __name__ == "__main__":
    cand = sys.argv[1] if len(sys.argv) > 1 else "candidate_005"
    nr = eval_candidate(cand)
    print(f"\nFINAL: {cand} Mean NR = {nr:.4f}")
