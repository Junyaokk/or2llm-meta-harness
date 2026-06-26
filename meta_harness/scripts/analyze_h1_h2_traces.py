"""Extract failure patterns from H1 and H2 traces for causal chain narrative."""
import json
from pathlib import Path
from collections import defaultdict

H1_DIR = Path(__file__).resolve().parent.parent / "traces" / "trace_store_h1_10nev" / "candidate_004"
H2_DIR = Path(__file__).resolve().parent.parent / "traces" / "trace_store_h2_10nev" / "candidate_011"

def analyze_trace(filepath):
    """Extract key metrics from a single trace file."""
    data = json.load(open(filepath))
    periods = data.get("periods", [])

    negative_rewards = []
    large_deviation_periods = []
    or_deviations = []
    overfill_orders = []
    rewards = []

    for p in periods:
        demand = p.get("demand", 0)
        order = p.get("ordered", 0)
        reward = p.get("reward", 0)
        pipe_status = p.get("pipe_status", "ADEQUATE")
        or_rec = p.get("or_recommended", 0)
        period = p.get("period", "?")

        if demand > 0:
            rewards.append(reward)

            if reward < 0:
                negative_rewards.append({
                    "period": period, "demand": demand, "order": order,
                    "reward": reward, "pipe": pipe_status, "or_rec": or_rec
                })

            deviation = abs(order - demand)
            if deviation > 0.5 * demand:
                large_deviation_periods.append({
                    "period": period, "demand": demand, "order": order,
                    "dev_pct": deviation / demand * 100, "reward": reward, "pipe": pipe_status
                })

            if or_rec > 0:
                or_deviations.append(abs(order - or_rec) / or_rec * 100)

            if pipe_status == "OVERFILLED" and order > 20:
                overfill_orders.append({
                    "period": period, "order": order, "demand": demand, "reward": reward
                })

    return {
        "total_reward": sum(rewards),
        "n_negative_rewards": len(negative_rewards),
        "negative_rewards": negative_rewards,
        "n_large_deviations": len(large_deviation_periods),
        "large_deviations": large_deviation_periods,
        "avg_or_deviation_pct": sum(or_deviations) / max(len(or_deviations), 1),
        "max_or_deviation_pct": max(or_deviations) if or_deviations else 0,
        "n_overfill_orders": len(overfill_orders),
        "overfill_orders": overfill_orders,
        "rewards": rewards,
    }

print("=" * 90)
print("H1 (candidate_004) vs H2 (candidate_011) — PER-INSTANCE FAILURE ANALYSIS")
print("=" * 90)

h1_summary = json.load(open(Path(__file__).resolve().parent.parent / "traces" / "trace_store_h1_10nev" / "summary.json"))
h2_summary = json.load(open(Path(__file__).resolve().parent.parent / "traces" / "trace_store_h2_10nev" / "summary.json"))

instance_files_h1 = sorted([f for f in H1_DIR.glob("*.json") if f.name != "scores.json"])
instance_files_h2 = sorted([f for f in H2_DIR.glob("*.json") if f.name != "scores.json"])

h1_analyses = {}
h2_analyses = {}

for f in instance_files_h1:
    h1_analyses[f.stem] = analyze_trace(f)
for f in instance_files_h2:
    h2_analyses[f.stem] = analyze_trace(f)

# === PER-INSTANCE COMPARISON ===
print(f"\n{'Instance':<30s} {'H1 NR':>8s} {'H2 NR':>8s} {'Δ NR':>8s} {'H1 NegR':>8s} {'H2 NegR':>8s} {'H1 OR偏差%':>10s} {'H2 OR偏差%':>10s} {'H1大偏':>6s} {'H2大偏':>6s}")
print("-" * 110)

l0_labels = []
l4_labels = []

for label in sorted(h1_analyses.keys()):
    h1a = h1_analyses[label]
    h2a = h2_analyses.get(label)

    if any(label.startswith(p) for p in ["p06","p07","p09","p10"]):
        l4_labels.append(label)
    else:
        l0_labels.append(label)

    h1_nr = h1_summary["per_instance_nr"].get(label, 0)
    h2_nr = h2_summary["per_instance_nr"].get(label, 0) if h2a else 0
    delta = h2_nr - h1_nr

    h2_neg = str(h2a['n_negative_rewards']) if h2a else 'N/A'
    h2_or_dev = h2a['avg_or_deviation_pct'] if h2a else 0
    h2_large = str(h2a['n_large_deviations']) if h2a else 'N/A'

    print(f"{label:<30s} {h1_nr:8.4f} {h2_nr:8.4f} {delta:+8.4f} {h1a['n_negative_rewards']:8d} {h2_neg:>8s} {h1a['avg_or_deviation_pct']:10.1f} {h2_or_dev:10.1f} {h1a['n_large_deviations']:6d} {h2_large:>6s}")

# === NEGATIVE REWARD PERIODS ===
print("\n" + "=" * 90)
print("NEGATIVE REWARD PERIODS — H1 vs H2")
print("=" * 90)

for label in sorted(h1_analyses.keys()):
    h1a = h1_analyses[label]
    h2a = h2_analyses.get(label)
    if h1a["n_negative_rewards"] > 0 or (h2a and h2a["n_negative_rewards"] > 0):
        print(f"\n--- {label} ---")
        if h1a["n_negative_rewards"] > 0:
            for nr in h1a["negative_rewards"]:
                print(f"  H1 P{str(nr['period']):>2s}: demand={nr['demand']:3d}, order={nr['order']:3d}, OR={str(nr['or_rec']):>4s}, pipe={nr['pipe']:12s}, reward={nr['reward']:+.0f}")
        if h2a and h2a["n_negative_rewards"] > 0:
            for nr in h2a["negative_rewards"]:
                print(f"  H2 P{str(nr['period']):>2s}: demand={nr['demand']:3d}, order={nr['order']:3d}, OR={str(nr['or_rec']):>4s}, pipe={nr['pipe']:12s}, reward={nr['reward']:+.0f}")

# === L=4 DEEP DIVE ===
print("\n" + "=" * 90)
print("L=4 PERIOD-BY-PERIOD COMPARISON (order / demand / OR / reward)")
print("=" * 90)

for label in sorted(l4_labels):
    if label not in h1_analyses or label not in h2_analyses:
        continue

    h1_data = json.load(open(H1_DIR / f"{label}.json"))
    h2_data = json.load(open(H2_DIR / f"{label}.json"))

    print(f"\n--- {label} ---")
    print(f"{'P':>3s} {'Demand':>6s} {'H1_Ord':>7s} {'H2_Ord':>7s} {'OR_Rec':>7s} {'H1_Rew':>8s} {'H2_Rew':>8s} {'Pipe':>12s}")
    print("-" * 70)

    for h1p, h2p in zip(h1_data["periods"], h2_data["periods"]):
        d = h1p["demand"]
        h1o = h1p["ordered"]
        h2o = h2p["ordered"]
        h1r = h1p["reward"]
        h2r = h2p["reward"]
        ore = h1p["or_recommended"]
        pipe = h2p.get("pipe_status", "?")

        # Flag bad decisions
        flag = ""
        if h1r < 0 and h2r >= 0:
            flag = " ← H1 fails, H2 ok"
        elif h2r < 0 and h1r >= 0:
            flag = " ← H2 fails, H1 ok"
        elif h1r < 0 and h2r < 0:
            flag = " ← BOTH fail"

        print(f"{h1p['period']:3d} {d:6.0f} {h1o:7.0f} {h2o:7.0f} {ore:7.0f} {h1r:8.0f} {h2r:8.0f} {pipe:>12s}{flag}")

# === H2 ANALYST INSIGHT QUALITY ===
print("\n" + "=" * 90)
print("H2 ANALYST INSIGHT TRACE (carry_over_insight + analyst_summary)")
print("=" * 90)

for label in sorted(l4_labels)[:2]:
    h2_data = json.load(open(H2_DIR / f"{label}.json"))
    print(f"\n--- {label} ---")
    print(f"{'P':>3s} {'Analyst Summary':>50s} | {'Carry-Over Insight'}")
    print("-" * 130)
    for p in h2_data["periods"]:
        summary = p.get("analyst_summary", "")[:48]
        carry = p.get("carry_over_insight", "")[:70]
        print(f"{p['period']:3d} {summary:>50s} | {carry}")

# === AGGREGATE STATS ===
print("\n" + "=" * 90)
print("AGGREGATE STATISTICS")
print("=" * 90)

h1_l0_nr = sum(h1_summary["per_instance_nr"].get(l, 0) for l in l0_labels) / len(l0_labels)
h2_l0_nr = sum(h2_summary["per_instance_nr"].get(l, 0) for l in l0_labels) / len(l0_labels)
h1_l4_nr = sum(h1_summary["per_instance_nr"].get(l, 0) for l in l4_labels) / len(l4_labels)
h2_l4_nr = sum(h2_summary["per_instance_nr"].get(l, 0) for l in l4_labels) / len(l4_labels)

print(f"\nL=0 (short lead time, {len(l0_labels)} instances): {', '.join(l0_labels)}")
print(f"  H1 avg NR: {h1_l0_nr:.4f}")
print(f"  H2 avg NR: {h2_l0_nr:.4f}")
print(f"  H2 - H1:   {h2_l0_nr - h1_l0_nr:+.4f}")

print(f"\nL=4 (long lead time, {len(l4_labels)} instances): {', '.join(l4_labels)}")
print(f"  H1 avg NR: {h1_l4_nr:.4f}")
print(f"  H2 avg NR: {h2_l4_nr:.4f}")
print(f"  H2 - H1:   {h2_l4_nr - h1_l4_nr:+.4f}")

# Count total failures
h1_total_neg = sum(a["n_negative_rewards"] for a in h1_analyses.values())
h2_total_neg = sum(a["n_negative_rewards"] for a in h2_analyses.values())
h1_total_large = sum(a["n_large_deviations"] for a in h1_analyses.values())
h2_total_large = sum(a["n_large_deviations"] for a in h2_analyses.values())
h1_total_overfill = sum(a["n_overfill_orders"] for a in h1_analyses.values())
h2_total_overfill = sum(a["n_overfill_orders"] for a in h2_analyses.values())

print(f"\nTotal negative-reward periods:     H1={h1_total_neg}, H2={h2_total_neg}")
print(f"Total large-deviation periods:     H1={h1_total_large}, H2={h2_total_large}")
print(f"Total overfill+order periods:      H1={h1_total_overfill}, H2={h2_total_overfill}")

# === WIN/LOSS MATRIX ===
print("\n" + "=" * 90)
print("HEAD-TO-HEAD: H1 vs H2 (per instance)")
print("=" * 90)

h1_wins = 0
h2_wins = 0
ties = 0
for label in sorted(h1_analyses.keys()):
    h1_nr = h1_summary["per_instance_nr"].get(label, 0)
    h2_nr = h2_summary["per_instance_nr"].get(label, 0)
    if h1_nr > h2_nr + 0.001:
        h1_wins += 1
        print(f"  {label:<35s}: H1 wins  ({h1_nr:.4f} > {h2_nr:.4f}, Δ={h1_nr-h2_nr:+.4f})")
    elif h2_nr > h1_nr + 0.001:
        h2_wins += 1
        print(f"  {label:<35s}: H2 wins  ({h2_nr:.4f} > {h1_nr:.4f}, Δ={h2_nr-h1_nr:+.4f})")
    else:
        ties += 1
        print(f"  {label:<35s}: TIE      ({h1_nr:.4f} vs {h2_nr:.4f})")

print(f"\nH1 wins: {h1_wins}, H2 wins: {h2_wins}, Ties: {ties}")
