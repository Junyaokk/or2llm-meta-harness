"""
库存环境 -- 固定提前期模式 (L=0 或 L=4).
对应论文 Section 3 "Problem Formulation".
"""

from dataclasses import dataclass
from typing import List


@dataclass
class InTransitOrder:
    """在途订单"""
    period_placed: int
    quantity: int
    lead_time: int

    @property
    def arrival_period(self) -> int:
        return self.period_placed + self.lead_time


@dataclass
class PeriodResult:
    """每周期结账日志"""
    period: int
    ordered: int
    arrived: int
    starting_inventory: int
    demand: int
    sold: int
    ending_inventory: int
    daily_profit: float
    daily_holding_cost: float
    daily_reward: float


class InventoryEnv:
    """多周期库存控制环境 -- 固定提前期模式 (L=0 或 L=4)."""

    def __init__(
        self,
        demands: List[int],
        lead_time: int,
        p: float,
        h: float,
        initial_demands: List[int],
    ):
        if lead_time not in (0, 4):
            raise ValueError(f"Only L=0 or L=4 supported, got {lead_time}")

        self.demands = list(demands)
        self.T = len(demands)
        self.lead_time = lead_time
        self.p = p
        self.h = h

        self.t: int = 1
        self.on_hand: int = 0
        self.in_transit: List[InTransitOrder] = []
        self.demand_history: List[int] = list(initial_demands)
        self.period_results: List[PeriodResult] = []
        self.total_reward: float = 0.0

    @property
    def critical_fractile(self) -> float:
        return self.p / (self.p + self.h)

    @property
    def done(self) -> bool:
        return self.t > self.T

    def step(self, q_t: int) -> dict:
        if self.done:
            raise RuntimeError("Episode already finished")

        # === Step 1: Place order (Decision Phase) ===
        if q_t > 0:
            self.in_transit.append(InTransitOrder(
                period_placed=self.t,
                quantity=q_t,
                lead_time=self.lead_time,
            ))

        # === Step 2: Arrival Resolution ===
        arrivals = sum(
            o.quantity for o in self.in_transit if o.arrival_period == self.t
        )
        self.in_transit = [o for o in self.in_transit if o.arrival_period > self.t]
        self.on_hand += arrivals

        # === Step 3: Demand Resolution ===
        d_t = self.demands[self.t - 1]
        starting_inv = self.on_hand
        sold = min(d_t, self.on_hand)
        self.on_hand -= sold
        ending_inv = self.on_hand

        daily_profit = self.p * sold
        daily_holding_cost = self.h * ending_inv
        daily_reward = daily_profit - daily_holding_cost
        self.total_reward += daily_reward

        result = PeriodResult(
            period=self.t,
            ordered=q_t,
            arrived=arrivals,
            starting_inventory=starting_inv,
            demand=d_t,
            sold=sold,
            ending_inventory=ending_inv,
            daily_profit=daily_profit,
            daily_holding_cost=daily_holding_cost,
            daily_reward=daily_reward,
        )
        self.period_results.append(result)

        self.demand_history.append(d_t)

        self.t += 1
        obs = self._build_observation()

        return {
            "period": self.t - 1,
            "reward": daily_reward,
            "done": self.done,
            "observation": obs,
        }

    def get_initial_observation(self) -> dict:
        return self._build_observation()

    def _build_observation(self) -> dict:
        in_transit_info = []
        for o in self.in_transit:
            waited = self.t - o.period_placed
            in_transit_info.append({
                "period_placed": o.period_placed,
                "quantity": o.quantity,
                "lead_time": o.lead_time,
                "arrival_period": o.arrival_period,
                "waited_periods": waited,
            })

        last_result = self.period_results[-1] if self.period_results else None
        conclude_msg = None
        if last_result:
            conclude_msg = (
                f"Period {last_result.period} conclude: "
                f"ordered={last_result.ordered}, "
                f"arrived={last_result.arrived}, "
                f"starting on-hand inventory={last_result.starting_inventory}, "
                f"demand={last_result.demand}, "
                f"sold={last_result.sold}, "
                f"ending on-hand inventory={last_result.ending_inventory}"
            )

        return {
            "period": self.t,
            "total_periods": self.T,
            "on_hand_inventory": self.on_hand,
            "in_transit_orders": in_transit_info,
            "in_transit_total": sum(o.quantity for o in self.in_transit),
            "demand_history": list(self.demand_history),
            "last_period_conclude": conclude_msg,
        }
