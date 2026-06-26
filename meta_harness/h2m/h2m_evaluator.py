"""
H2M Evaluator — evaluates conversational multi-agent candidates.
Loop: ORBaseline → Analyst → Memory → H2MConversation (Decider↔Reviewer) → env.step
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
from meta_harness.h2x.memory import MemoryBuffer, PeriodMemory
from meta_harness.h2m.conversation import (
    H2MDecider, H2MReviewer, H2MConversation,
    ConversationTrace,
)


@dataclass
class H2MPeriodTrace:
    """Extended period trace with full conversation data."""
    period: int
    demand: int
    ordered: int           # Final order after conversation
    draft_order: int       # Decider's original proposal
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
    # H2M conversation fields
    reviewer_critique: str = ""
    reviewer_agreed: bool = True
    concern_level: str = "none"
    risk_flag: str = "safe"
    revision_rationale: str = ""
    decider_accepted_critique: bool = False
    conversation_rounds: int = 2

    @property
    def llm_rationale(self) -> str:
        return self.decider_rationale

    @property
    def llm_short_rationale(self) -> str:
        return self.decider_short_rationale

    @property
    def approved(self) -> bool:
        return self.reviewer_agreed

    @property
    def reviewer_rationale(self) -> str:
        return self.reviewer_critique

    @property
    def adjustment_pct(self) -> float:
        if self.draft_order > 0:
            return (self.ordered - self.draft_order) / self.draft_order * 100
        return 0.0


@dataclass
class H2MCandidateResult:
    """Aggregated result for one H2M candidate."""
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


class H2MEvaluator:
    """Evaluates an H2M candidate with multi-turn Decider↔Reviewer conversation."""

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
        # Load analyst config
        config_file = self.candidate_dir / "analyst_config.py"
        if not config_file.exists():
            raise FileNotFoundError(f"Analyst config not found: {config_file}")
        spec = importlib.util.spec_from_file_location(
            f"{self.candidate_dir.name}_analyst_config", config_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.analyst_config = mod.ANALYST_CONFIG

        # Load decider draft prompt
        prompt_file = self.candidate_dir / "decider_prompt.py"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Decider prompt not found: {prompt_file}")
        spec = importlib.util.spec_from_file_location(
            f"{self.candidate_dir.name}_decider_prompt", prompt_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.decider_prompt_template = mod.SYSTEM_PROMPT

        # Load reviewer critique prompt
        rev_file = self.candidate_dir / "reviewer_prompt.py"
        self.reviewer_prompt_template = ""
        if rev_file.exists():
            spec = importlib.util.spec_from_file_location(
                f"{self.candidate_dir.name}_reviewer_prompt", rev_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.reviewer_prompt_template = mod.SYSTEM_PROMPT

        # Load decider revision prompt
        revp_file = self.candidate_dir / "decider_revise_prompt.py"
        self.decider_revise_template = ""
        if revp_file.exists():
            spec = importlib.util.spec_from_file_location(
                f"{self.candidate_dir.name}_decider_revise_prompt", revp_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.decider_revise_template = getattr(mod, "SYSTEM_PROMPT", "")

        # Load memory config
        mem_file = self.candidate_dir / "memory_config.py"
        self.memory_window = 5
        if mem_file.exists():
            spec = importlib.util.spec_from_file_location(
                f"{self.candidate_dir.name}_memory_config", mem_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.memory_window = getattr(mod, "MEMORY_WINDOW", 5)

    def evaluate(self, candidate_id: str) -> H2MCandidateResult:
        result = H2MCandidateResult(candidate_id=candidate_id)

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

        decider = H2MDecider(
            item_id=config["item_id"],
            model=self.model, api_key=self.api_key, base_url=self.base_url,
            anticipated_lead_time=lead_time, p=p, h=h,
            draft_prompt_template=self.decider_prompt_template,
            revise_prompt_template=self.decider_revise_template,
        )

        reviewer = H2MReviewer(
            item_id=config["item_id"],
            model=self.model, api_key=self.api_key, base_url=self.base_url,
            anticipated_lead_time=lead_time, p=p, h=h,
            or_cap=9999,
            critique_prompt_template=self.reviewer_prompt_template,
        )

        conversation = H2MConversation(decider=decider, reviewer=reviewer)
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

            # Build memory tables
            mem_for_decider = memory.render_for_decider()
            report_text = analyst.render_for_decider(
                report, obs, or_rec, config["item_id"],
                carry_over=mem_for_decider)

            # Run multi-turn conversation (Round 1 first to get draft)
            # We use a two-step approach to build reviewer context with actual draft
            draft = decider.draft(report_text, or_rec.recommended_order)
            draft.order = max(0, min(or_rec.order_cap, draft.order))

            mem_for_reviewer = memory.render_for_reviewer(draft.order, draft.rationale)

            # Reviewer critiques the draft
            critique = reviewer.critique(
                report_text, mem_for_reviewer,
                draft.order, draft.rationale, or_rec.recommended_order)
            critique.suggested_order = max(0, min(or_rec.order_cap, critique.suggested_order))

            # If Reviewer disagrees: Decider revises or defends
            revision = None
            if not critique.agreed:
                revision = decider.revise(
                    report_text, or_rec.recommended_order,
                    draft.order, draft.rationale,
                    critique.critique, critique.suggested_order,
                    critique.concern_level,
                )
                revision.final_order = int(max(0, min(or_rec.order_cap, revision.final_order)))

            final_order = revision.final_order if revision else draft.order
            final_order = int(final_order)

            from meta_harness.h2m.conversation import ConversationTrace
            trace = ConversationTrace(
                draft=draft, critique=critique, revision=revision,
                rounds=3 if revision else 2,
            )

            final_order = trace.final_order

            pre_step_demand = env.demands[env.t - 1] if env.t <= len(env.demands) else 0
            result = env.step(final_order)
            obs = result["observation"]

            period_traces.append(H2MPeriodTrace(
                period=env.t - 1,
                demand=pre_step_demand,
                ordered=final_order,
                draft_order=trace.draft.order,
                sold=0,
                reward=result["reward"],
                or_recommended=or_rec.recommended_order,
                decider_rationale=trace.draft.rationale,
                decider_short_rationale=trace.draft.short_rationale,
                carry_over_insight="",
                analyst_summary=report.summary,
                analyst_alerts=report.alerts,
                pipe_status=report.pipeline.get("pipe_status", ""),
                trend_dir=report.demand.get("trend_dir", ""),
                or_trust=report.or_audit.get("trust_level", ""),
                reviewer_critique=trace.critique.critique,
                reviewer_agreed=trace.critique.agreed,
                concern_level=trace.critique.concern_level,
                risk_flag=trace.critique.risk_flag,
                revision_rationale=trace.revision.revision_rationale if trace.revision else "",
                decider_accepted_critique=trace.decider_accepted_critique,
                conversation_rounds=trace.rounds,
            ))

            # Add to memory for next period
            memory.add(PeriodMemory(
                period=env.t - 1,
                demand=pre_step_demand,
                ordered=final_order,
                sold=0,
                reward=result["reward"],
                or_recommended=or_rec.recommended_order,
                pipe_status=report.pipeline.get("pipe_status", ""),
                trend_dir=report.demand.get("trend_dir", ""),
                or_trust=report.or_audit.get("trust_level", ""),
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
