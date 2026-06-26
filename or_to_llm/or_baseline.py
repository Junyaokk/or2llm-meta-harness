"""
OR 基线 -- 数据驱动的上限基准库存策略.
对应论文 Appendix A "OR Baseline: Data-driven Capped Base-stock Policy".
"""

from dataclasses import dataclass
from typing import List

import numpy as np
from scipy.stats import norm


@dataclass
class ORRecommendation:
    """OR 基线推荐及全部统计量 -- 对应论文 Appendix A"""
    base_stock_level: float
    inventory_position: float
    demand_mean: float
    demand_std: float
    mu_hat: float
    sigma_hat: float
    order_cap: float
    recommended_order: int
    critical_fractile: float
    z_star: float


class ORBaseline:
    """数据驱动的上限基准库存策略 (Capped Base-stock Policy)."""

    def __init__(self, anticipated_lead_time: int, p: float, h: float):
        self.L = anticipated_lead_time
        self.p = p
        self.h = h
        self.rho = p / (p + h)
        self.z_star = norm.ppf(self.rho)
        self.z_cap = norm.ppf(0.95)

    def compute(
        self, demand_history: List[int], on_hand: int, in_transit_total: int
    ) -> ORRecommendation:
        demands = np.array(demand_history, dtype=np.float64)
        n = len(demands)
        d_bar = float(demands.mean())
        s_d = float(demands.std(ddof=1)) if n > 1 else 0.0

        mu_hat = (1 + self.L) * d_bar
        sigma_hat = np.sqrt(1 + self.L) * s_d

        B = mu_hat + self.z_star * sigma_hat
        IP = on_hand + in_transit_total

        cap = mu_hat / (1 + self.L) + self.z_cap * sigma_hat / np.sqrt(1 + self.L)

        q_uncapped = max(0.0, B - IP)
        q = int(np.floor(max(0.0, min(q_uncapped, max(cap, 0.0)))))

        return ORRecommendation(
            base_stock_level=B,
            inventory_position=IP,
            demand_mean=d_bar,
            demand_std=s_d,
            mu_hat=mu_hat,
            sigma_hat=sigma_hat,
            order_cap=cap,
            recommended_order=q,
            critical_fractile=self.rho,
            z_star=self.z_star,
        )
