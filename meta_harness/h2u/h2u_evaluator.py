"""
H2U Evaluator — evaluates Analyst + Memory + Decider + Reviewer candidates.

Loop: ORBaseline -> Analyst -> MemoryBuffer -> Decider -> Reviewer -> env.step

Key differences from H2X:
  - Decider receives memory table prepended to analyst report (not merged via render_for_decider)
  - Reviewer receives explicit Analyst signals (pipe_status, trend_dir, trust_level) for cross-checking
  - AnalystConfig defaults to H2-optimized thresholds (candidate_006)
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
from meta_harness.h2.analyst import Analyst, AnalystConfig
from meta_harness.h2.decider import Decider
from meta_harness.h2x.memory import MemoryBuffer, PeriodMemory
from meta_harness.h2x.reviewer import Reviewer, ReviewerDecision


@dataclass
class H2UPerodTrace:
    """Extended period trace for H2U (Analyst signals + reviewer data)."""
    period: int
    demand: int
    ordered: int
    draft_order: int
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
    reviewer_rationale: str = ""
    approved: bool = True
    risk_flag: str = "safe"
    adjustment_pct: float = 0.0

    @property
    def llm_rationale(self) -> str:
        return self.decider_rationale

    @property
    def llm_short_rationale(self) -> str:
        return self.decider_short_rationale


@dataclass
class H2UCandidateResult:
    """Aggregated result for one H2U candidate."""
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


class H2UEvaluator:
    """Evaluates H2U candidate (Analyst + Memory + Decider + Reviewer)."""

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
        """Load all 4 candidate files."""
        # Invalidate cached analyst module so proposer edits to h2/analyst.py take effect
        for key in list(sys.modules.keys()):
            if "h2.analyst" in key or "meta_harness.h2.analyst" in key:
                del sys.modules[key]

        # Analyst config
        config_file = self.candidate_dir / "analyst_config.py"
        if not config_file.exists():
            raise FileNotFoundError(f"Analyst config not found: {config_file}")
        spec = importlib.util.spec_from_file_location(
            f"{self.candidate_dir.name}_analyst_config", config_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.analyst_config = mod.ANALYST_CONFIG

        # Decider prompt
        prompt_file = self.candidate_dir / "decider_prompt.py"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Decider prompt not found: {prompt_file}")
        spec = importlib.util.spec_from_file_location(
            f"{self.candidate_dir.name}_decider_prompt", prompt_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.decider_prompt_template = mod.SYSTEM_PROMPT

        # Reviewer prompt
        rev_file = self.candidate_dir / "reviewer_prompt.py"
        self.reviewer_prompt_template = ""
        if rev_file.exists():
            spec = importlib.util.spec_from_file_location(
                f"{self.candidate_dir.name}_reviewer_prompt", rev_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.reviewer_prompt_template = mod.SYSTEM_PROMPT

        # Memory config
        mem_file = self.candidate_dir / "memory_config.py"
        self.memory_window = 5
        if mem_file.exists():
            spec = importlib.util.spec_from_file_location(
                f"{self.candidate_dir.name}_memory_config", mem_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.memory_window = getattr(mod, "MEMORY_WINDOW", 5)

    def evaluate(self, candidate_id: str) -> H2UCandidateResult:
        result = H2UCandidateResult(candidate_id=candidate_id)

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
        loader = InstanceLoader(str(inst_dir))
        config = loader.load()

        demands = config["test_demands"][:self.n_periods]
        lead_time = config["lead_time"]
        p = config["p"]
        h = config["h"]

        env = InventoryEnv(
            demands=demands, lead_time=lead_time, p=p, h=h,
            initial_demands=config["initial_demands"],
        )

        analyst = Analyst(config=self.analyst_config)
        or_baseline = ORBaseline(lead_time, p, h)

        decider = Decider(
            item_id=config["item_id"],
            system_prompt_template=self.decider_prompt_template,
            model=self.model, api_key=self.api_key, base_url=self.base_url,
            anticipated_lead_time=lead_time, p=p, h=h,
        )

        reviewer = Reviewer(
            item_id=config["item_id"],
            system_prompt_template=self.reviewer_prompt_template,
            model=self.model, api_key=self.api_key, base_url=self.base_url,
            anticipated_lead_time=lead_time, p=p, h=h,
            or_cap=9999,
        )

        memory = MemoryBuffer(window=self.memory_window)
        period_traces = []
        obs = env.get_initial_observation()
        context = config.get("description", "")

        while not env.done:
            or_rec = or_baseline.compute(
                demand_history=obs["demand_history"],
                on_hand=obs.get("on_hand_inventory", 0),
                in_transit_total=obs.get("in_transit_total", 0),
            )
            reviewer.or_cap = or_rec.order_cap

            obs["lead_time"] = lead_time
            obs["p"] = p
            obs["h"] = h
            obs["context"] = context

            report = analyst.analyze(obs, or_rec, item_id=config["item_id"],
                                     context=context)

            # Step 1: Memory table
            memory_table = memory.render_for_decider()

            # Step 2: Decider — receives analyst report + memory table separately
            analyst_text = analyst.render_for_decider(
                report, obs, or_rec, config["item_id"], carry_over="")

            # Prepend memory table before analyst report
            decider_user_message = memory_table + "\n\n" + analyst_text

            response = decider.decide(decider_user_message, or_rec.recommended_order)
            draft_order = response.order_quantity

            # Step 3: Reviewer — with analyst signals for cross-checking
            analyst_signals = {
                "pipe_status": report.pipeline.get("pipe_status", ""),
                "ip": report.pipeline.get("ip", 0),
                "B": report.pipeline.get("B", 0),
                "trend_dir": report.demand.get("trend_dir", ""),
                "gap_pct": report.demand.get("gap_pct", 0),
                "trust_level": report.or_audit.get("trust_level", ""),
            }
            review_memory_table = memory.render_for_reviewer(draft_order, response.rationale)

            review_decision = self._review_with_signals(
                reviewer, analyst_signals, analyst_text,
                review_memory_table, draft_order, response.rationale,
                or_rec.recommended_order)

            final_order = review_decision.final_order

            pre_step_demand = env.demands[env.t - 1] if env.t <= len(env.demands) else 0
            result = env.step(final_order)
            obs = result["observation"]

            period_traces.append(H2UPerodTrace(
                period=env.t - 1,
                demand=pre_step_demand,
                ordered=final_order,
                draft_order=draft_order,
                sold=0,
                reward=result["reward"],
                or_recommended=or_rec.recommended_order,
                decider_rationale=response.rationale,
                decider_short_rationale=response.short_rationale,
                carry_over_insight=response.carry_over_insight,
                analyst_summary=report.summary,
                analyst_alerts=report.alerts,
                pipe_status=analyst_signals["pipe_status"],
                trend_dir=analyst_signals["trend_dir"],
                or_trust=analyst_signals["trust_level"],
                reviewer_rationale=review_decision.review_rationale,
                approved=review_decision.approved,
                risk_flag=review_decision.risk_flag,
                adjustment_pct=review_decision.adjustment_pct,
            ))

            # Add to memory for next period
            memory.add(PeriodMemory(
                period=env.t - 1,
                demand=pre_step_demand,
                ordered=final_order,
                sold=0,
                reward=result["reward"],
                or_recommended=or_rec.recommended_order,
                pipe_status=analyst_signals["pipe_status"],
                trend_dir=analyst_signals["trend_dir"],
                or_trust=analyst_signals["trust_level"],
            ))

        # Fix sold/reward from env
        for i, pr in enumerate(env.period_results):
            if i < len(period_traces):
                period_traces[i].sold = pr.sold
                period_traces[i].reward = pr.daily_reward
                memory.history[i].sold = pr.sold
                memory.history[i].reward = pr.daily_reward

        nr = normalized_reward(env.total_reward, p=p, total_demand=sum(demands))

        from meta_harness.evaluator import InstanceTrace
        return InstanceTrace(
            instance_label=cfg["label"],
            item_id=config["item_id"],
            lead_time=lead_time, p=p, h=h,
            rho=p / (p + h),
            total_demand=sum(demands),
            total_reward=env.total_reward,
            normalized_reward=nr,
            periods=period_traces,
        )

    @staticmethod
    def _review_with_signals(reviewer: Reviewer,
                              analyst_signals: dict,
                              analyst_text: str,
                              memory_table: str,
                              draft_order: int,
                              draft_rationale: str,
                              or_recommended: int) -> ReviewerDecision:
        """Enhanced review: injects Analyst signals into the memory table for cross-checking."""
        signals_blob = (
            f"\nANALYST SIGNALS (FACT — for cross-check):\n"
            f"  Pipeline: {analyst_signals['pipe_status']} "
            f"(IP={analyst_signals['ip']}, B={analyst_signals['B']})\n"
            f"  Demand Trend: {analyst_signals['trend_dir']} "
            f"(gap={analyst_signals['gap_pct']:.1%})\n"
            f"  OR Trust: {analyst_signals['trust_level']}\n"
        )
        enhanced_memory = signals_blob + "\n" + memory_table
        return reviewer.review(analyst_text, enhanced_memory, draft_order, draft_rationale, or_recommended)
