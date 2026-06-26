#!/usr/bin/env python
"""
通用实验脚本 -- 运行 InventoryBench 真实 CSV 数据实例.
用法:
  python run.py --index 1                   # 运行第1个实例 (默认50周期)
  python run.py --index 5 --periods 30      # 运行第5个实例, 30周期
  python run.py --index 1 --periods 10 -v   # 10周期 + 详细输出
  python run.py --list                       # 列出所有可用实例
"""

import argparse
import json
import sys
from pathlib import Path

from or_to_llm import (
    InventoryEnv,
    ORToLLMAgent,
    InstanceLoader,
    normalized_reward,
    build_instance_index,
    TraceLogger,
    DashboardBuilder,
    ReportBuilder,
)

BENCHMARK_DIR = Path(__file__).resolve().parent / "InventoryBench-main" / "benchmark" / "synthetic_trajectory"

# Demo instance shortcuts — maps --index 2,3 to selected NEV battery supply chain scenarios.
# Usage: python run.py --index 2  (or --index 3)
DEMO_MAP = {
    2: {
        "path": "lead_time_4/p04_increasing_trend/v3_exp_1_05/r1_high",
        "label": "NEV Battery: Exponential Demand Growth (S-Curve)",
        "story": "NEV渗透率爆发 → 电池需求指数增长(5%/期) → Agent预判趋势超越OR基线",
    },
    3: {
        "path": "lead_time_4/p08_multi_changepoint/v2_down_then_up/r1_high",
        "label": "NEV Battery: Supply Recovery After Disruption",
        "story": "供应商产能危机 → 需求触底 → 产能恢复反弹 → Agent检测转折信号",
    },
}


def list_instances():
    instances = build_instance_index(str(BENCHMARK_DIR))
    for i, inst in enumerate(instances, 1):
        print(f"{i:4d}. [{inst['lead_time']}] {inst['pattern']}/{inst['variant']}/{inst['instance']}")
    print(f"\nTotal: {len(instances)} instances")
    return instances


def main():
    parser = argparse.ArgumentParser(description="OR->LLM Inventory Control -- Universal Runner")
    parser.add_argument("--index", type=int, default=None,
                        help="Instance index (1-based, from --list)")
    parser.add_argument("--periods", type=int, default=50,
                        help="Number of test periods to run (default: 50)")
    parser.add_argument("--list", action="store_true",
                        help="List all available instances and exit")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose per-period output")
    parser.add_argument("--trace", action="store_true",
                        help="Full Step A/B/C/D trace output (aligns with architecture diagram)")
    parser.add_argument("--trace-file", type=str, default=None,
                        help="Save trace output to file (use with --trace)")
    parser.add_argument("--plot", action="store_true",
                        help="Generate interactive Plotly HTML dashboard")
    parser.add_argument("--plot-file", type=str, default=None,
                        help="Dashboard output path (default: dashboard_<index>.html)")
    parser.add_argument("--report", action="store_true",
                        help="Generate well-structured Markdown report")
    parser.add_argument("--report-file", type=str, default=None,
                        help="Report output path (default: report_<index>.md)")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results to JSON file")
    parser.add_argument("--model", type=str, default="deepseek-chat",
                        help="LLM model name (default: deepseek-chat)")
    args = parser.parse_args()

    if not BENCHMARK_DIR.exists():
        print(f"ERROR: Benchmark data not found at {BENCHMARK_DIR}")
        print("Clone: git clone git@github.com:TianyiPeng/InventoryBench.git InventoryBench-main")
        sys.exit(1)

    instances = build_instance_index(str(BENCHMARK_DIR))

    if args.list:
        print("=== DEMO SHORTCUTS (NEV Battery Supply Chain) ===")
        for idx in sorted(DEMO_MAP):
            d = DEMO_MAP[idx]
            print(f"  {idx:4d}. {d['label']}")
            print(f"         {d['story']}")
        print(f"\n=== ALL INSTANCES ({len(instances)} total) ===")
        for i, inst in enumerate(instances, 1):
            print(f"{i:4d}. [{inst['lead_time']}] {inst['pattern']}/{inst['variant']}/{inst['instance']}")
        print(f"\nTotal: {len(instances)} instances + {len(DEMO_MAP)} demo shortcuts")
        return

    if args.index is None:
        parser.print_help()
        print("\nUse --list to see available instances, then --index N to run one.")
        sys.exit(1)

    # Check demo shortcut map first
    if args.index in DEMO_MAP:
        demo = DEMO_MAP[args.index]
        demo_path = str(BENCHMARK_DIR / demo["path"])
        inst = {
            "path": demo_path,
            "lead_time": demo["path"].split("/")[0],
            "pattern": demo["path"].split("/")[1],
            "variant": demo["path"].split("/")[2],
            "instance": demo["path"].split("/")[3],
            "_demo_label": demo["label"],
            "_demo_story": demo["story"],
        }
        print("=" * 60)
        print(f"Demo #{args.index}: {demo['label']}")
        print(f"  Story: {demo['story']}")
        print(f"  Instance: {inst['pattern']}/{inst['variant']}/{inst['instance']}")
        print(f"  Lead time: {inst['lead_time']}")
        print(f"  Periods: {args.periods}")
        print(f"  Model: {args.model}")
        print("=" * 60)
    else:
        idx = args.index - 1
        if idx < 0 or idx >= len(instances):
            print(f"Invalid index: {args.index}. Valid range: 1-{len(instances)}")
            sys.exit(1)

        inst = instances[idx]

        print("=" * 60)
        print(f"Instance #{args.index}: {inst['pattern']}/{inst['variant']}/{inst['instance']}")
        print(f"  Lead time dir: {inst['lead_time']}")
        print(f"  Periods: {args.periods}")
        print(f"  Model: {args.model}")
        print("=" * 60)

    # Load config
    loader = InstanceLoader(inst["path"])
    config = loader.load()

    demands = config["test_demands"][:args.periods]

    print(f"  Item: {config['item_id']}")
    print(f"  L={config['lead_time']}, p={config['p']}, h={config['h']}, rho={config['p']/(config['p']+config['h']):.2f}")
    print(f"  First 5 demands: {demands[:5]}")
    print("=" * 60)

    env = InventoryEnv(
        demands=demands,
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
        model=args.model,
    )

    trace = TraceLogger(args.trace_file) if args.trace else None

    obs = env.get_initial_observation()
    period_log = []
    decision_records = []

    while not env.done:
        # === Steps A+B+C: Agent decision (returns full DecisionRecord) ===
        carry_before = agent.carry_over_insights  # capture before decide() updates it
        record = agent.decide(obs, context=config["description"])
        q = record.order_quantity
        decision_records.append(record)

        # Step A/B/C trace
        if trace:
            trace.log_step_a(env.t, obs, record.or_recommendation)
            trace.log_step_b(env.t, record.user_message, carry_before)
            trace.log_step_c(env.t, record.llm_raw_output, record.agent_response)

        # Capture pre-step values for Step D trace
        pre_step_demand = env.demands[env.t - 1] if env.t <= len(env.demands) else 0
        pre_step_arrivals = sum(
            o.quantity for o in env.in_transit if o.arrival_period == env.t
        )

        # === Step D: State transition ===
        result = env.step(q)
        obs = result["observation"]

        pr = env.period_results[-1]
        entry = {
            "period": pr.period,
            "demand": pr.demand,
            "ordered": q,
            "arrived": pr.arrived,
            "on_hand_before": pr.starting_inventory,
            "sold": pr.sold,
            "on_hand_after": pr.ending_inventory,
            "reward": round(result["reward"], 2),
        }
        period_log.append(entry)

        # Step D trace
        if trace:
            trace.log_step_d(
                period=pr.period,
                q_t=q,
                lead_time=config["lead_time"],
                arrivals=pr.arrived,
                starting_inv=pr.starting_inventory,
                demand=pr.demand,
                sold=pr.sold,
                ending_inv=pr.ending_inventory,
                p=config["p"],
                h=config["h"],
                reward=result["reward"],
            )

        status = f"P{entry['period']:2d} | demand={entry['demand']:3d} order={entry['ordered']:3d} arrive={entry['arrived']:3d} sold={entry['sold']:3d} end_inv={entry['on_hand_after']:3d} reward={entry['reward']:7.1f}"
        if args.verbose:
            rec = agent.or_baseline.compute(
                obs["demand_history"],
                obs["on_hand_inventory"],
                obs.get("in_transit_total", 0),
            )
            status += f"\n      OR rec: {rec.recommended_order}"
            last_resp = agent.decision_history[-1]
            status += f"\n      LLM: {last_resp.short_rationale_for_human[:120]}"
        print(status)

    if trace:
        trace.close()

    nr = normalized_reward(env.total_reward, p=config["p"], total_demand=sum(demands))

    # Generate interactive dashboard
    if args.plot:
        plot_path = args.plot_file or f"outputs/dashboards/dashboard_{args.index}.html"
        dashboard = DashboardBuilder(plot_path)
        dashboard.build(
            period_log=period_log,
            decision_history=decision_records,
            config=config,
            total_reward=env.total_reward,
            normalized_reward=nr,
            instance_info=inst,
            system_prompt=agent.system_prompt,
        )
        print(f"Dashboard saved to {plot_path}")

    # Generate Markdown report
    if args.report:
        report_path = args.report_file or f"outputs/reports/report_{args.index}.md"
        report = ReportBuilder(report_path)
        report.build(
            period_log=period_log,
            decision_history=decision_records,
            config=config,
            total_reward=env.total_reward,
            normalized_reward=nr,
            instance_info=inst,
        )
        print(f"Report saved to {report_path}")

    print("-" * 60)
    print(f"  Total reward: ${env.total_reward:.2f}  |  Normalized: {nr:.4f}")
    print(f"  Insights: {sum(1 for h in agent.decision_history if h.carry_over_insight)} / {len(agent.decision_history)}")
    print("=" * 60)

    out = {
        "index": args.index,
        "instance": inst,
        "item_id": config["item_id"],
        "lead_time": config["lead_time"],
        "p": config["p"],
        "h": config["h"],
        "periods": args.periods,
        "total_reward": env.total_reward,
        "normalized_reward": nr,
        "periods_detail": period_log,
    }

    output_path = args.output or f"outputs/results/run_result_{args.index}.json"
    with open(output_path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
