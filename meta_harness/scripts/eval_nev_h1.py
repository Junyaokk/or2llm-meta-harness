"""Evaluate H1 best (candidate_004) on 10 NEV supply chain instances."""
import os, sys, time, json
sys.path.insert(0, "/Users/junyaoyu/Downloads/nio")
from pathlib import Path
from meta_harness.evaluator import Evaluator
from meta_harness.trace_store import TraceStore

NEV_10_INSTANCES = [
    # === L=0 短提前期（国内标准件/通用物料）===
    {"path": "lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_med",
     "label": "p01_标准件_稳态_L0", "description": "标准紧固件，稳态需求"},
    {"path": "lead_time_0/p02_mean_increase/v1_100to200/r1_med",
     "label": "p02_新车上市_跃升_L0", "description": "新车型上市，需求跳涨"},
    {"path": "lead_time_0/p03_mean_decrease/v1_100to50/r1_med",
     "label": "p03_老车退市_下降_L0", "description": "老车型退市，需求萎缩"},
    {"path": "lead_time_0/p04_increasing_trend/v1_linear_100t/r1_med",
     "label": "p04_市场增长_趋势_L0", "description": "NEV市场渗透率持续增长"},
    {"path": "lead_time_0/p05_decreasing_trend/v1_200_minus_3t/r1_med",
     "label": "p05_燃油车替代_下降_L0", "description": "燃油车零件被替代，持续下降"},
    {"path": "lead_time_0/p08_multi_changepoint/v1_up_then_down/r1_med",
     "label": "p08_补贴退坡_变点_L0", "description": "补贴政策调整，需求结构变化"},
    # === L=4 长提前期（进口件/电池材料/芯片）===
    {"path": "lead_time_4/p06_variance_change/v1_normal_to_uniform/r1_med",
     "label": "p06_芯片短缺_波动_L4", "description": "供应链中断，需求波动剧变"},
    {"path": "lead_time_4/p07_seasonal/v1_period10_amp30/r1_med",
     "label": "p07_季度冲刺_季节_L4", "description": "Q4交付冲刺，季节性周期"},
    {"path": "lead_time_4/p09_temp_spike_dip/v1_temp_surge/r1_med",
     "label": "p09_促销抢购_脉冲_L4", "description": "限时促销，临时需求脉冲"},
    {"path": "lead_time_4/p10_autocorrelated/v1_phi_0_7/r1_med",
     "label": "p10_电池排产_自相关_L4", "description": "电池生产计划连续性，自相关需求"},
]

cand_dir = Path(__file__).resolve().parent / "candidates" / "candidate_004"
store = TraceStore(Path(__file__).resolve().parent.parent / "traces" / "trace_store_h1_10nev")

evaluator = Evaluator(
    candidate_dir=cand_dir,
    holdout_configs=NEV_10_INSTANCES,
    n_periods=20,
    model="deepseek-chat",
    api_key=os.getenv("EVAL_API_KEY", ""),
    base_url="https://api.deepseek.com/v1",
)

t0 = time.time()
result = evaluator.evaluate("candidate_004")
elapsed = time.time() - t0

store.save(result)

print(f"\n{'='*60}")
print(f"H1 BEST (candidate_004) on 10 NEV instances — DONE")
print(f"Mean NR: {result.mean_nr:.4f}  ({elapsed:.0f}s)")
for label, nr in sorted(result.per_instance_nr.items()):
    print(f"  {label}: {nr:.4f}")

summary = {"architecture":"H1","candidate":"candidate_004","mean_nr":result.mean_nr,
           "per_instance_nr":result.per_instance_nr,"elapsed_s":elapsed}
json.dump(summary, open(store.store_dir / "summary.json", "w"), indent=2)
