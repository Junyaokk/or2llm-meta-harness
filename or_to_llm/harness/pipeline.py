import time
from typing import Optional
from dataclasses import dataclass, field

from .services.cache import ResponseCache
from .services.metrics import MetricsCollector
from .services.insight import InsightManager
from .services.fallback import FallbackHandler


@dataclass
class PipelineContext:
    obs: dict = field(default_factory=dict)
    order_quantity: int = 0
    reviewer_override: bool = False
    llm_raw_output: str = ""
    user_message: str = ""
    or_recommended: int = 0


class DecisionPipeline:
    def __init__(self, agent, cache=None, metrics=None,
                 fallback=None, insight_manager=None, reviewer=None):
        self.agent = agent
        self.cache = cache
        self.metrics = metrics
        self.fallback = fallback
        self.insight = insight_manager
        self.reviewer = reviewer

    def run_cycle(self, obs: dict, context: str, period: int) -> PipelineContext:
        ctx = PipelineContext(obs=obs)

        # Pre: try cache
        cache_hit = False
        if self.cache:
            dbg_msg = _make_fingerprint(obs, context)
            cached = self.cache.get(dbg_msg, self.agent.system_prompt)
            if cached:
                cache_hit = True
                if self.metrics:
                    self.metrics.record("cache_hits", 1)

        # Core: agent.decide() — unchanged
        t0 = time.perf_counter()
        try:
            record = self.agent.decide(obs, context)
        except Exception as e:
            or_q = _compute_or_q(self.agent, obs)
            if self.fallback:
                fallback_q = self.fallback.handle(e, or_q, "decide")
            else:
                raise
            from ..agent import DecisionRecord, AgentResponse
            record = DecisionRecord(
                or_recommendation=_make_fake_or_rec(or_q),
                user_message="", llm_raw_output="",
                agent_response=AgentResponse(
                    rationale=f"Fallback: {e}",
                    short_rationale_for_human="Fallback",
                    carry_over_insight="",
                    order_quantity=fallback_q,
                    raw_json={},
                ),
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        ctx.llm_raw_output = record.llm_raw_output
        ctx.user_message = record.user_message
        ctx.order_quantity = record.agent_response.order_quantity
        or_q = record.or_recommendation.recommended_order
        ctx.or_recommended = or_q

        # Post: cache write
        if self.cache and not cache_hit:
            self.cache.set(record.user_message, self.agent.system_prompt, record.llm_raw_output)

        # Post: ReviewerAgent check (Phase 2)
        if self.reviewer:
            review = self.reviewer.review(
                ctx.order_quantity, record.or_recommendation,
                record.agent_response.rationale, obs,
            )
            if not review.approved:
                ctx.order_quantity = review.adjusted_qty
                ctx.reviewer_override = True
                if self.metrics:
                    self.metrics.record("review_overrides", 1)
            else:
                if self.metrics:
                    self.metrics.record("review_overrides", 0)

        # Side: metrics
        if self.metrics:
            self.metrics.record("period", period)
            self.metrics.record("llm_duration_ms", elapsed_ms)
            self.metrics.record("deviation_from_or", abs(ctx.order_quantity - or_q))
            self.metrics.record("order_quantity", ctx.order_quantity)

        # Side: structured insight
        if self.insight and record.agent_response.carry_over_insight:
            self.insight.ingest(record.agent_response.carry_over_insight, period)
            self.insight.expire_old(period)
            self.agent.carry_over_insights = self.insight.to_prompt_string()

        if self.fallback:
            self.fallback.update(ctx.order_quantity)

        return ctx


def _compute_or_q(agent, obs) -> int:
    try:
        rec = agent.or_baseline.compute(
            demand_history=obs["demand_history"],
            on_hand=obs["on_hand_inventory"],
            in_transit_total=obs.get("in_transit_total", 0),
        )
        return rec.recommended_order
    except Exception:
        return 0


def _make_fake_or_rec(q: int):
    from ..or_baseline import ORRecommendation
    return ORRecommendation(
        base_stock_level=0, inventory_position=0,
        demand_mean=0, demand_std=0, mu_hat=0, sigma_hat=0,
        order_cap=0, recommended_order=q,
        critical_fractile=0, z_star=0,
    )


def _make_fingerprint(obs: dict, context: str) -> str:
    dh = obs.get("demand_history", [])
    recent = dh[-3:] if len(dh) >= 3 else dh
    return f"oh={obs['on_hand_inventory']}|itt={obs.get('in_transit_total',0)}|dh={list(recent)}|ctx={context}"
