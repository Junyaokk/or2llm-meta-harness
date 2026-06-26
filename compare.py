#!/usr/bin/env python3
"""
对比实验：Original vs Harness (with ReviewerAgent).
选 5 个 diverse instance，各跑 20 期，对比 NR。
"""
import sys
import time
import json
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from or_to_llm import (
    InventoryEnv, InstanceLoader, ORToLLMAgent,
    normalized_reward, build_instance_index,
)
from or_to_llm.harness import Harness

BENCHMARK_DIR = Path("InventoryBench-main/benchmark/synthetic_trajectory")


def run_original(inst, demands, config, periods, model="deepseek-chat"):
    """Original run — no harness."""
    env = InventoryEnv(
        demands=demands[:periods],
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
        model=model,
    )
    orders, total_reward, history = agent.run_episode(
        env, context=config["description"],
    )
    nr = normalized_reward(
        total_reward, p=config["p"],
        total_demand=sum(demands[:periods]),
    )
    return total_reward, nr, orders, len(history)


def run_harness(inst, demands, config, periods):
    """Harness run — with ReviewerAgent."""
    env = InventoryEnv(
        demands=demands[:periods],
        lead_time=config["lead_time"],
        p=config["p"],
        h=config["h"],
        initial_demands=config["initial_demands"],
    )
    harness = Harness.from_config("config/solo_reviewer.yaml")
    harness.create_agent(
        item_id=config["item_id"],
        L=config["lead_time"],
        p=config["p"],
        h=config["h"],
    )
    result = harness.run_episode(env, context=config["description"])
    nr = normalized_reward(
        result.total_reward, p=config["p"],
        total_demand=sum(demands[:periods]),
    )
    return result.total_reward, nr, [p["qty"] for p in result.periods], result


def main():
    instances = build_instance_index(str(BENCHMARK_DIR))

    # 5 diverse cases across patterns and lead times
    case_specs = [
        {"label": "Stationary L=0 (high rho)",     "pattern": "p01_stationary_iid",       "lead_time": "lead_time_0", "variant_hint": "v1_normal_100_25", "rho_dir": "r1_high"},
        {"label": "Stationary L=4 (low rho)",       "pattern": "p01_stationary_iid",       "lead_time": "lead_time_4", "variant_hint": "v1_normal_100_25", "rho_dir": "r1_low"},
        {"label": "Mean increase L=0 (med rho)",    "pattern": "p02_mean_increase",        "lead_time": "lead_time_0", "variant_hint": "v1_100to200", "rho_dir": "r1_med"},
        {"label": "Variance change L=4 (high rho)", "pattern": "p06_variance_change",      "lead_time": "lead_time_4", "variant_hint": "v1", "rho_dir": "r1_high"},
        {"label": "Seasonal L=0 (low rho)",         "pattern": "p07_seasonal",             "lead_time": "lead_time_0", "variant_hint": "v1", "rho_dir": "r1_low"},
    ]

    PERIODS = 20
    selected = []

    print("=" * 80)
    print(f"Harness vs Original — 5 cases, {PERIODS} periods each")
    print("=" * 80)

    for spec in case_specs:
        found = None
        for i, inst in enumerate(instances):
            if (spec["lead_time"] == inst["lead_time"] and
                spec["pattern"] in inst["pattern"] and
                spec["variant_hint"] in inst["variant"] and
                spec["rho_dir"] in inst["instance"]):
                found = (i + 1, inst)
                break
        if found is None:
            # Broader fallback: any instance matching lead_time
            for i, inst in enumerate(instances):
                if spec["lead_time"] == inst["lead_time"]:
                    found = (i + 1, inst)
                    print(f"  Fallback2: idx={i+1}, {inst['pattern']}/{inst['variant']}/{inst['instance']}")
                    break
        if found is None:
            print(f"  SKIP: no instance found for {spec['label']}")
            continue
        selected.append(found)

    results = []
    # Filter out None entries
    valid_pairs = [(s, spec) for s, spec in zip(selected, case_specs) if s is not None]
    if len(valid_pairs) < len(case_specs):
        print(f"\n  (skipped {len(case_specs) - len(valid_pairs)} cases due to missing instances)\n")

    for (idx, inst), spec in valid_pairs:
        print(f"\n{'─' * 60}")
        print(f"[{idx}] {spec['label']}")
        print(f"    Path: {inst['pattern']}/{inst['variant']}/{inst['instance']}")
        print(f"    L={inst['lead_time']}")

        loader = InstanceLoader(inst["path"])
        config = loader.load()
        demands = config["test_demands"]

        print(f"    p={config['p']}, h={config['h']}, ρ={config['p']/(config['p']+config['h']):.2f}")

        # Original
        print(f"  Original ...", end=" ", flush=True)
        t0 = time.time()
        try:
            orig_r, orig_nr, orig_orders, orig_decisions = run_original(
                inst, demands, config, PERIODS,
            )
            orig_t = time.time() - t0
            print(f"NR={orig_nr:.4f} reward={orig_r:.1f} ({orig_t:.1f}s)")
        except Exception as e:
            print(f"FAILED: {e}")
            continue

        # Harness (with Reviewer)
        print(f"  Harness  ...", end=" ", flush=True)
        t0 = time.time()
        try:
            h_r, h_nr, h_orders, h_result = run_harness(
                inst, demands, config, PERIODS,
            )
            h_t = time.time() - t0
            overrides = h_result.reviewer_overrides
            print(f"NR={h_nr:.4f} reward={h_r:.1f} overrides={overrides} ({h_t:.1f}s)")
        except Exception as e:
            print(f"FAILED: {e}")
            import traceback
            traceback.print_exc()
            continue

        delta = h_nr - orig_nr
        status = "▲" if delta > 0 else ("▬" if delta == 0 else "▼")
        results.append({
            "idx": idx, "label": spec["label"],
            "pattern": inst["pattern"], "variant": inst["variant"],
            "lead_time": inst["lead_time"],
            "p": config["p"], "h": config["h"],
            "original_nr": round(orig_nr, 4),
            "harness_nr": round(h_nr, 4),
            "delta": round(delta, 4),
            "reviewer_overrides": h_result.reviewer_overrides,
        })
        print(f"  Delta: {status} {delta:+.4f}")

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"{'Case':<40} {'Orig NR':>8} {'Harn NR':>8} {'Delta':>8} {'Ovr':>4}")
    print(f"{'─' * 72}")
    for r in results:
        sign = "+" if r["delta"] > 0 else ""
        print(f"{r['label']:<40} {r['original_nr']:>8.4f} {r['harness_nr']:>8.4f} {sign}{r['delta']:>7.4f} {r['reviewer_overrides']:>4}")

    avg_delta = 0.0
    avg_orig = 0.0
    avg_harn = 0.0
    total_overrides = 0

    if results:
        avg_delta = sum(r["delta"] for r in results) / len(results)
        avg_orig = sum(r["original_nr"] for r in results) / len(results)
        avg_harn = sum(r["harness_nr"] for r in results) / len(results)
        total_overrides = sum(r["reviewer_overrides"] for r in results)
        print(f"{'─' * 72}")
        print(f"{'AVERAGE':<40} {avg_orig:>8.4f} {avg_harn:>8.4f} {'+' if avg_delta > 0 else ''}{avg_delta:>7.4f} {total_overrides:>4}")

        print(f"\nReviewer overrides total: {total_overrides}")
        if avg_delta > 0:
            print(f"NR improvement: +{avg_delta:.4f} ({avg_delta/avg_orig*100:+.1f}%)")

    # Save results
    out = {
        "config": {"periods": PERIODS, "cases": len(results)},
        "results": results,
        "summary": {
            "avg_original_nr": round(avg_orig, 4) if results else 0,
            "avg_harness_nr": round(avg_harn, 4) if results else 0,
            "avg_delta": round(avg_delta, 4) if results else 0,
            "total_reviewer_overrides": total_overrides,
        },
    }
    with open("outputs/comparisons/harness_comparison.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved to harness_comparison.json")


if __name__ == "__main__":
    main()
