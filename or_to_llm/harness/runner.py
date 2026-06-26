import time
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass, field

from .config import ConfigManager
from .factory import AgentFactory
from .pipeline import DecisionPipeline
from .services.cache import ResponseCache
from .services.metrics import MetricsCollector
from .services.insight import InsightManager
from .services.fallback import FallbackHandler


@dataclass
class EpisodeResult:
    total_reward: float
    periods: list
    metrics: dict
    insight_count: int
    insights: list = field(default_factory=list)
    reviewer_overrides: int = 0


class Harness:
    def __init__(self, config_path: Union[str, Path]):
        self.config = ConfigManager(config_path)
        self.factory = AgentFactory(self.config)
        hc = self.config.harness_config

        cache_cfg = hc.get("cache", {})
        self.cache = ResponseCache(
            max_size=cache_cfg.get("max_size", 1000),
            similarity_threshold=cache_cfg.get("similarity_threshold", 0.92),
            enabled=cache_cfg.get("enabled", True),
        )

        self.metrics = MetricsCollector()
        self.fallback = FallbackHandler(
            strategy=hc.get("fallback", {}).get("strategy", "or_baseline"),
        )
        self.insight = InsightManager(
            max_active=hc.get("insight", {}).get("max_active", 5),
        )

        self._agent = None
        self._pipeline: Optional[DecisionPipeline] = None
        self._reviewer = None

    @classmethod
    def from_config(cls, config_path: Union[str, Path]) -> "Harness":
        return cls(config_path)

    def create_agent(self, item_id: str, L: int, p: float, h: float):
        self._agent = self.factory.create_agent(item_id, L, p, h)

        pipeline_mode = self.config.pipeline_config.get("mode", "solo")
        if pipeline_mode == "solo_reviewer":
            self._reviewer = self.factory.create_reviewer(p, h)
        else:
            self._reviewer = None

        self._pipeline = DecisionPipeline(
            agent=self._agent,
            cache=self.cache,
            metrics=self.metrics,
            fallback=self.fallback,
            insight_manager=self.insight,
            reviewer=self._reviewer,
        )

    @property
    def agent(self):
        return self._agent

    @property
    def reviewer(self):
        return self._reviewer

    def run_episode(self, env, context: str = "") -> EpisodeResult:
        if self._pipeline is None:
            raise RuntimeError("Call create_agent() first")

        self.metrics.start_episode()
        obs = env.get_initial_observation()
        period_log = []

        while not env.done:
            period = env.t
            ctx = self._pipeline.run_cycle(obs, context, period)
            qty = ctx.order_quantity

            result = env.step(qty)
            obs = result["observation"]

            period_log.append({
                "period": period,
                "qty": qty,
                "or_q": ctx.or_recommended,
                "override": ctx.reviewer_override,
                "reward": result.get("reward", 0),
            })

        return EpisodeResult(
            total_reward=env.total_reward,
            periods=period_log,
            metrics=self.metrics.summary(),
            insight_count=len(self.insight.active),
            insights=[i.content for i in self.insight.active],
            reviewer_overrides=sum(1 for p in period_log if p["override"]),
        )
