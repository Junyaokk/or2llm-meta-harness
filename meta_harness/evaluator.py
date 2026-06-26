"""
Evaluator -- runs a single candidate against holdout instances.

Plan B (深 Trace): stores per-period rationale + decision outcome.
"""
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict

import numpy as np

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from or_to_llm import (
    InventoryEnv, ORToLLMAgent, InstanceLoader, normalized_reward,
)
from or_to_llm.agent import SYSTEM_PROMPT_TEMPLATE as _ORIGINAL_TEMPLATE


@dataclass
class PeriodTrace:
    """Plan B trace for a single period. Stored per instance."""
    period: int
    demand: int
    ordered: int
    sold: int
    reward: float
    or_recommended: int
    llm_rationale: str
    llm_short_rationale: str
    carry_over_insight: str


@dataclass
class InstanceTrace:
    """Full trace for one instance."""
    instance_label: str
    item_id: str
    lead_time: int
    p: float
    h: float
    rho: float
    total_demand: int
    total_reward: float
    normalized_reward: float
    periods: List[PeriodTrace] = field(default_factory=list)


@dataclass
class CandidateResult:
    """Aggregated result for one candidate across all holdout instances."""
    candidate_id: str
    instance_traces: List[InstanceTrace] = field(default_factory=list)

    @property
    def mean_nr(self) -> float:
        if not self.instance_traces:
            return 0.0
        return float(np.mean([t.normalized_reward for t in self.instance_traces]))

    @property
    def per_instance_nr(self) -> Dict[str, float]:
        return {t.instance_label: t.normalized_reward for t in self.instance_traces}


class Evaluator:
    """Evaluates a single harness candidate against holdout instances."""

    def __init__(self, candidate_dir: Path, holdout_configs: List[dict],
                 n_periods: int = 20, model: str = "deepseek-chat",
                 api_key: str = "", base_url: str = ""):
        self.candidate_dir = Path(candidate_dir)
        self.holdout_configs = holdout_configs
        self.n_periods = n_periods
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

        # Load the candidate's system prompt
        self._load_candidate_prompt()

    def _load_candidate_prompt(self):
        """Load SYSTEM_PROMPT from candidate's system_prompt.py."""
        prompt_file = self.candidate_dir / "system_prompt.py"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Candidate prompt not found: {prompt_file}")

        # Execute the candidate's prompt module to get SYSTEM_PROMPT
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f"candidate_{self.candidate_dir.name}", prompt_file
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.system_prompt_template = mod.SYSTEM_PROMPT

    def evaluate(self, candidate_id: str) -> CandidateResult:
        """Run candidate against all holdout instances."""
        result = CandidateResult(candidate_id=candidate_id)

        for cfg in self.holdout_configs:
            inst_dir = Path(__file__).resolve().parent.parent / "InventoryBench-main" / \
                       "benchmark" / "synthetic_trajectory" / cfg["path"]

            if not inst_dir.exists():
                print(f"  [SKIP] Instance not found: {cfg['path']}")
                continue

            try:
                inst_trace = self._evaluate_one_instance(inst_dir, cfg)
                result.instance_traces.append(inst_trace)
                print(f"  [{cfg['label']}] NR={inst_trace.normalized_reward:.4f}  "
                      f"Reward=${inst_trace.total_reward:.1f}")
            except Exception as e:
                print(f"  [FAIL] {cfg['label']}: {e}")

        return result

    def _evaluate_one_instance(self, inst_dir: Path, cfg: dict) -> InstanceTrace:
        """Run one instance with this candidate's prompt and collect Plan B trace."""
        loader = InstanceLoader(str(inst_dir))
        config = loader.load()

        demands = config["test_demands"][:self.n_periods]

        env = InventoryEnv(
            demands=demands,
            lead_time=config["lead_time"],
            p=config["p"],
            h=config["h"],
            initial_demands=config["initial_demands"],
        )

        # Create agent that uses THIS candidate's system prompt
        agent = _CandidateAgent(
            item_id=config["item_id"],
            anticipated_lead_time=config["lead_time"],
            p=config["p"],
            h=config["h"],
            system_prompt_template=self.system_prompt_template,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )

        # Run episode, collecting period-level traces
        period_traces = []
        obs = env.get_initial_observation()

        while not env.done:
            record = agent.decide_with_trace(obs, context=config["description"])
            q = record.order_quantity

            # Capture pre-step state
            pre_step_demand = env.demands[env.t - 1] if env.t <= len(env.demands) else 0

            result = env.step(q)
            obs = result["observation"]

            period_traces.append(PeriodTrace(
                period=env.t - 1,
                demand=pre_step_demand,
                ordered=q,
                sold=min(pre_step_demand, q),  # approximate, env tracks exact
                reward=result["reward"],
                or_recommended=record.or_recommendation.recommended_order,
                llm_rationale=record.agent_response.rationale,
                llm_short_rationale=record.agent_response.short_rationale_for_human,
                carry_over_insight=record.agent_response.carry_over_insight,
            ))

        # Fix sold values from env's period results
        for i, pr in enumerate(env.period_results):
            if i < len(period_traces):
                period_traces[i].sold = pr.sold
                period_traces[i].reward = pr.daily_reward

        nr = normalized_reward(env.total_reward, p=config["p"],
                               total_demand=sum(demands))

        return InstanceTrace(
            instance_label=cfg["label"],
            item_id=config["item_id"],
            lead_time=config["lead_time"],
            p=config["p"],
            h=config["h"],
            rho=config["p"] / (config["p"] + config["h"]),
            total_demand=sum(demands),
            total_reward=env.total_reward,
            normalized_reward=nr,
            periods=period_traces,
        )


class _CandidateAgent(ORToLLMAgent):
    """ORToLLMAgent that uses a custom system prompt template."""

    def __init__(self, item_id, anticipated_lead_time, p, h,
                 system_prompt_template, model, api_key, base_url):
        # Bypass parent __init__ to inject custom prompt
        self.item_id = item_id
        self.L = anticipated_lead_time
        self.p = p
        self.h = h
        self.system_prompt_template = system_prompt_template

        from or_to_llm.or_baseline import ORBaseline
        self.system_prompt = self._build_custom_prompt()
        self.or_baseline = ORBaseline(anticipated_lead_time, p, h)

        from openai import OpenAI
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=180.0,
            max_retries=2,
        )
        self.model = model
        self.carry_over_insights = ""
        self.decision_history = []

    def _build_custom_prompt(self):
        from scipy.stats import norm
        rho = self.p / (self.p + self.h)
        return self.system_prompt_template.format(
            item_id=self.item_id,
            anticipated_lead_time=self.L,
            p=self.p,
            h=self.h,
            critical_fractile=rho,
            z_star=norm.ppf(rho),
        )

    def decide_with_trace(self, obs, context=""):
        """Same as decide() but returns the full DecisionRecord."""
        from or_to_llm.agent import DecisionRecord, UserMessageBuilder, ResponseParser, AgentResponse

        or_rec = self.or_baseline.compute(
            demand_history=obs["demand_history"],
            on_hand=obs["on_hand_inventory"],
            in_transit_total=obs.get("in_transit_total", 0),
        )

        user_msg = UserMessageBuilder.build(
            obs=obs, or_rec=or_rec,
            carry_over_insights=self.carry_over_insights,
            item_id=self.item_id, context=context,
        )

        llm_output = self._call_llm(user_msg)

        try:
            parsed = ResponseParser.parse(llm_output, self.item_id)
        except Exception:
            parsed = AgentResponse(
                rationale="(parse error)",
                short_rationale_for_human="Following OR recommendation",
                carry_over_insight="",
                order_quantity=or_rec.recommended_order,
                raw_json={},
            )

        if parsed.carry_over_insight:
            self.carry_over_insights = parsed.carry_over_insight

        self.decision_history.append(parsed)

        return DecisionRecord(
            or_recommendation=or_rec,
            user_message=user_msg,
            llm_raw_output=llm_output,
            agent_response=parsed,
        )
