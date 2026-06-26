"""
Evaluate H2 baseline (candidate_h2_000) against 5 dev instances.
Compares with H1 best (candidate_004, NR=0.7425).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meta_harness.h2.h2_evaluator import H2Evaluator
from meta_harness.config import HOLDOUT_INSTANCES, N_PERIODS, EVAL_MODEL, EVAL_API_KEY, EVAL_BASE_URL, CANDIDATES_DIR

CANDIDATE_DIR = Path(CANDIDATES_DIR) / "candidate_h2_000"

print("=" * 70)
print("H2 BASELINE EVALUATION — candidate_h2_000")
print(f"  Decider: H1(004) faithful translation")
print(f"  Analyst: conservative defaults")
print(f"  Instances: {len(HOLDOUT_INSTANCES)}")
print(f"  Periods/instance: {N_PERIODS}")
print("=" * 70)

evaluator = H2Evaluator(
    candidate_dir=CANDIDATE_DIR,
    holdout_configs=HOLDOUT_INSTANCES,
    n_periods=N_PERIODS,
    model=EVAL_MODEL,
    api_key=EVAL_API_KEY,
    base_url=EVAL_BASE_URL,
)

result = evaluator.evaluate("candidate_h2_000")

print(f"\n{'=' * 70}")
print(f"RESULTS: {result.candidate_id}")
print(f"{'=' * 70}")
print(f"Mean NR: {result.mean_nr:.4f}")
print()

# Per-instance comparison
H1_BEST_NR = {
    "p01_stationary_L0": 0.8862,
    "p04_increasing_trend_L0": 0.8682,
    "p07_seasonal_L4": 0.5406,
    "p08_changepoint_L0": 0.8701,
    "p06_variance_L4": 0.5472,
}
H1_BEST_MEAN = 0.7425

print(f"{'Instance':<30s} {'H1(004)':>8s} {'H2(000)':>8s} {'Delta':>8s}")
print("-" * 60)
for t in result.instance_traces:
    label = t.instance_label
    h1_nr = H1_BEST_NR.get(label, 0)
    h2_nr = t.normalized_reward
    delta = h2_nr - h1_nr
    d_sign = "+" if delta >= 0 else ""
    print(f"{label:<30s} {h1_nr:>8.4f} {h2_nr:>8.4f} {d_sign}{delta:>7.4f}")

print("-" * 60)
h2_mean = result.mean_nr
delta = h2_mean - H1_BEST_MEAN
d_sign = "+" if delta >= 0 else ""
print(f"{'MEAN':<30s} {H1_BEST_MEAN:>8.4f} {h2_mean:>8.4f} {d_sign}{delta:>7.4f}")

print()
if delta >= 0:
    print(f"✅ H2 architecture hypothesis CONFIRMED: +{delta:.4f} over H1 best")
else:
    print(f"⚠️  H2 baseline below H1 best by {delta:.4f}. Analyzing traces needed.")
