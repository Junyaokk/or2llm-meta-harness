"""
H2 Evaluator — evaluates Analyst + Decider candidates against holdout instances.
Follows the same pattern as meta_harness/evaluator.py but uses the two-layer
architecture: Analyst (code) → Decider (LLM).
"""
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from or_to_llm import InventoryEnv, InstanceLoader, normalized_reward
from or_to_llm.or_baseline import ORBaseline
from meta_harness.h2.analyst import Analyst, AnalystConfig, AnalystReport


@dataclass
class H2PeriodTrace:
    """Extended period trace with Analyst report data."""
    period: int
    demand: int
    ordered: int
    sold: int
    reward: float
    or_recommended: int
    decider_rationale: str
    decider_short_rationale: str
    carry_over_insight: str
    analyst_summary: str = ""
    analyst_alerts: List[str] = field(default_factory=list)
    pipe_status: str = ""
    trend_dir: str = ""
    or_trust: str = ""

    # Backwards compatibility with existing trace/report infra
    @property
    def llm_rationale(self) -> str:
        return self.decider_rationale

    @property
    def llm_short_rationale(self) -> str:
        return self.decider_short_rationale


@dataclass
class H2CandidateResult:
    """Aggregated result for one H2 candidate."""
    candidate_id: str
    instance_traces: List = field(default_factory=list)

    @property
    def mean_nr(self) -> float:
        if not self.instance_traces:
            return 0.0
        return float(np.mean([t.normalized_reward for t in self.instance_traces]))

    @property
    def per_instance_nr(self) -> Dict[str, float]:
        return {t.instance_label: t.normalized_reward for t in self.instance_traces}


class H2Evaluator:
    """Evaluates an H2 candidate (Analyst config + Decider prompt)."""

    def __init__(self, candidate_dir: Path, holdout_configs: List[dict],
                 n_periods: int = 20, model: str = "deepseek-chat",
                 api_key: str = "", base_url: str = ""):
        self.candidate_dir = Path(candidate_dir)
        self.holdout_configs = holdout_configs
        self.n_periods = n_periods
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self._load_candidate()

    def _load_candidate(self):
        """Load analyst_config.py and decider_prompt.py from candidate dir."""
        # Load analyst config
        config_file = self.candidate_dir / "analyst_config.py"
        if not config_file.exists():
            raise FileNotFoundError(f"Analyst config not found: {config_file}")
        spec = importlib.util.spec_from_file_location(
            f"{self.candidate_dir.name}_analyst_config", config_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.analyst_config = mod.ANALYST_CONFIG

        # Load decider prompt
        prompt_file = self.candidate_dir / "decider_prompt.py"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Decider prompt not found: {prompt_file}")
        spec = importlib.util.spec_from_file_location(
            f"{self.candidate_dir.name}_decider_prompt", prompt_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.decider_prompt_template = mod.SYSTEM_PROMPT

    def evaluate(self, candidate_id: str) -> H2CandidateResult:
        """Run H2 candidate against all holdout instances."""
        result = H2CandidateResult(candidate_id=candidate_id)

        for cfg in self.holdout_configs:
            inst_dir = Path(__file__).resolve().parent.parent.parent / \
                       "InventoryBench-main" / "benchmark" / \
                       "synthetic_trajectory" / cfg["path"]

            if not inst_dir.exists():
                print(f"  [SKIP] Instance not found: {cfg['path']}")
                continue

            try:
                inst_trace = self._evaluate_one_instance(inst_dir, cfg)
                result.instance_traces.append(inst_trace)
                print(f"  [{cfg['label']}] NR={inst_trace.normalized_reward:.4f}  "
                      f"Reward=${inst_trace.total_reward:.1f}")
            except Exception as e:
                import traceback
                print(f"  [FAIL] {cfg['label']}: {e}")
                traceback.print_exc()

        return result

    def _evaluate_one_instance(self, inst_dir: Path, cfg: dict):
        """Run one instance with Analyst + Decider and collect H2 trace."""
        loader = InstanceLoader(str(inst_dir))
        config = loader.load()

        demands = config["test_demands"][:self.n_periods]
        lead_time = config["lead_time"]
        p = config["p"]
        h = config["h"]

        env = InventoryEnv(
            demands=demands,
            lead_time=lead_time,
            p=p,
            h=h,
            initial_demands=config["initial_demands"],
        )

        # Build Analyst + ORBaseline
        analyst = Analyst(config=self.analyst_config)
        or_baseline = ORBaseline(lead_time, p, h)

        # Build Decider (LLM)
        from meta_harness.h2.decider import Decider
        decider = Decider(
            item_id=config["item_id"],
            system_prompt_template=self.decider_prompt_template,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            anticipated_lead_time=lead_time,
            p=p, h=h,
        )

        period_traces = []
        obs = env.get_initial_observation()
        context = config.get("description", "")

        while not env.done:
            # Step A: OR baseline
            or_rec = or_baseline.compute(
                demand_history=obs["demand_history"],
                on_hand=obs.get("on_hand_inventory", 0),
                in_transit_total=obs.get("in_transit_total", 0),
            )

            # Inject lead_time into obs for analyst
            obs["lead_time"] = lead_time
            obs["p"] = p
            obs["h"] = h
            obs["context"] = context

            # Step B: Analyst
            report = analyst.analyze(obs, or_rec, item_id=config["item_id"],
                                     context=context)

            # Step C: Decider
            report_text = analyst.render_for_decider(
                report, obs, or_rec, config["item_id"],
                carry_over=decider.carry_over_insights)

            response = decider.decide(report_text, or_rec.recommended_order)
            q = response.order_quantity

            # Pre-step demand for trace
            pre_step_demand = env.demands[env.t - 1] if env.t <= len(env.demands) else 0

            result = env.step(q)
            obs = result["observation"]

            period_traces.append(H2PeriodTrace(
                period=env.t - 1,
                demand=pre_step_demand,
                ordered=q,
                sold=0,  # fixed below
                reward=result["reward"],
                or_recommended=or_rec.recommended_order,
                decider_rationale=response.rationale,
                decider_short_rationale=response.short_rationale,
                carry_over_insight=response.carry_over_insight,
                analyst_summary=report.summary,
                analyst_alerts=report.alerts,
                pipe_status=report.pipeline.get("pipe_status", ""),
                trend_dir=report.demand.get("trend_dir", ""),
                or_trust=report.or_audit.get("trust_level", ""),
            ))

        # Fix sold/reward from env
        for i, pr in enumerate(env.period_results):
            if i < len(period_traces):
                period_traces[i].sold = pr.sold
                period_traces[i].reward = pr.daily_reward

        nr = normalized_reward(env.total_reward, p=p, total_demand=sum(demands))

        # Use the existing InstanceTrace dataclass from evaluator for compatibility
        from meta_harness.evaluator import InstanceTrace
        return InstanceTrace(
            instance_label=cfg["label"],
            item_id=config["item_id"],
            lead_time=lead_time,
            p=p, h=h,
            rho=p / (p + h),
            total_demand=sum(demands),
            total_reward=env.total_reward,
            normalized_reward=nr,
            periods=period_traces,
        )
