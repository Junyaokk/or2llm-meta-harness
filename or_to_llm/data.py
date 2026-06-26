"""
数据加载与评估 -- CSV 数据加载器、归一化奖励、批量运行.
对应论文评估框架.
"""

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .env import InventoryEnv
from .agent import ORToLLMAgent


class InstanceLoader:
    """从 InventoryBench CSV 文件加载单个实例"""

    def __init__(self, instance_dir: str):
        self.dir = Path(instance_dir)
        self.train_path = self.dir / "train.csv"
        self.test_path = self.dir / "test.csv"

        if not self.train_path.exists():
            raise FileNotFoundError(f"train.csv not found: {self.train_path}")
        if not self.test_path.exists():
            raise FileNotFoundError(f"test.csv not found: {self.test_path}")

    def load(self) -> dict:
        train_df = self._read_csv(self.train_path)
        test_df = self._read_csv(self.test_path)

        item_cols = [c for c in test_df.columns if c.startswith("demand_")]
        if len(item_cols) != 1:
            raise ValueError(f"Expected 1 demand column, got {len(item_cols)}: {item_cols}")
        demand_col = item_cols[0]
        item_id = demand_col[len("demand_"):]

        initial_demands = [int(x) for x in train_df[f"demand_{item_id}"].tolist()]
        test_demands = [int(x) for x in test_df[f"demand_{item_id}"].tolist()]

        desc_col = f"description_{item_id}"
        description = str(test_df[desc_col].iloc[0]) if desc_col in test_df.columns else ""

        lead_time = int(test_df[f"lead_time_{item_id}"].iloc[0])
        p = float(test_df[f"profit_{item_id}"].iloc[0])
        h = float(test_df[f"holding_cost_{item_id}"].iloc[0])

        if lead_time not in (0, 4):
            raise ValueError(f"Unsupported lead_time={lead_time}. Only L=0 and L=4 are supported.")

        return {
            "item_id": item_id,
            "description": description,
            "lead_time": lead_time,
            "p": p,
            "h": h,
            "initial_demands": initial_demands,
            "test_demands": test_demands,
        }

    @staticmethod
    def _read_csv(path: Path) -> pd.DataFrame:
        with open(path, "r") as f:
            lines = f.readlines()
        data_lines = [l for l in lines if not l.startswith("version https://")]
        return pd.read_csv(io.StringIO("".join(data_lines)))


def normalized_reward(total_reward: float, p: float, total_demand: float) -> float:
    denominator = p * total_demand
    if denominator <= 0:
        return 0.0
    return max(total_reward / denominator, 0.0)


def run_single_instance(instance_dir: str, model: str = "deepseek-chat", periods: int = None) -> dict:
    loader = InstanceLoader(instance_dir)
    config = loader.load()

    demands = config["test_demands"]
    if periods is not None and periods < len(demands):
        demands = demands[:periods]

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
        model=model,
    )

    orders, total_reward, history = agent.run_episode(
        env, context=config["description"]
    )

    nr = normalized_reward(
        total_reward, p=config["p"],
        total_demand=sum(demands),
    )

    print(f"Instance: {config['item_id']} | L={config['lead_time']} | rho={env.critical_fractile:.2f}")
    print(f"  Total reward: ${total_reward:.2f} | Normalized: {nr:.4f}")

    return {
        "instance_path": instance_dir,
        "item_id": config["item_id"],
        "lead_time": config["lead_time"],
        "p": config["p"],
        "h": config["h"],
        "critical_fractile": env.critical_fractile,
        "total_reward": total_reward,
        "normalized_reward": nr,
        "total_demand": sum(demands),
        "orders": orders,
        "decision_summaries": [h.short_rationale_for_human for h in history],
    }


def save_results(results: dict, output_path: str):
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to {output_path}")


def validate_with_benchmark_data(base_dir: str, limit: int = 6):
    """从 InventoryBench CSV 数据做端到端验证 (前 limit 个实例)."""
    print("=" * 70)
    print(f"End-to-End Validation with Benchmark Data (first {limit} instances)")
    print("=" * 70)

    base = Path(base_dir)
    results = []

    for lead_time_dir in ["lead_time_0", "lead_time_4"]:
        lt_path = base / lead_time_dir
        if not lt_path.exists():
            print(f"  Skipping {lead_time_dir}: directory not found")
            continue

        for pattern_dir in sorted(lt_path.iterdir()):
            if not pattern_dir.is_dir():
                continue
            for variant_dir in sorted(pattern_dir.iterdir()):
                if not variant_dir.is_dir():
                    continue
                for inst_dir in sorted(variant_dir.iterdir()):
                    if not inst_dir.is_dir() or len(results) >= limit:
                        break
                    try:
                        result = run_single_instance(str(inst_dir))
                        results.append(result)
                    except Exception as e:
                        print(f"  ERROR on {inst_dir.name}: {e}")
                    if len(results) >= limit:
                        break
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    print(f"\nRan {len(results)} benchmark instances")
    if results:
        nrs = [r["normalized_reward"] for r in results]
        print(f"Mean normalized reward: {np.mean(nrs):.4f}")
    return results


def build_instance_index(base_dir: str) -> list:
    """构建所有可用实例的索引列表，按排序顺序 (1-indexed)."""
    base = Path(base_dir)
    instances = []
    for lead_time_dir in sorted(base.iterdir()):
        if not lead_time_dir.is_dir():
            continue
        if lead_time_dir.name == "lead_time_stochastic":
            continue
        for pattern_dir in sorted(lead_time_dir.iterdir()):
            if not pattern_dir.is_dir():
                continue
            for variant_dir in sorted(pattern_dir.iterdir()):
                if not variant_dir.is_dir():
                    continue
                for inst_dir in sorted(variant_dir.iterdir()):
                    if not inst_dir.is_dir():
                        continue
                    if (inst_dir / "train.csv").exists() and (inst_dir / "test.csv").exists():
                        instances.append({
                            "path": str(inst_dir),
                            "lead_time": lead_time_dir.name,
                            "pattern": pattern_dir.name,
                            "variant": variant_dir.name,
                            "instance": inst_dir.name,
                        })
    return instances
