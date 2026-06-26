"""
TraceLogger -- 每周期决策链路追踪输出, 对齐算法架构图 Step A/B/C/D.
"""

import sys
from .agent import DecisionRecord, AgentResponse
from .or_baseline import ORRecommendation


class TraceLogger:
    """格式化打印每周期四步决策的完整输入输出. 可同时写文件."""

    def __init__(self, file_path: str = None):
        self._file = None
        if file_path:
            self._file = open(file_path, "w")

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    def _emit(self, text: str):
        """同时输出到终端和文件."""
        print(text)
        sys.stdout.flush()
        if self._file:
            self._file.write(text + "\n")
            self._file.flush()

    def log_step_a(self, period: int, obs: dict, or_rec: ORRecommendation):
        """Step A: OR Baseline -- 数据驱动上限基准库存策略"""
        self._emit(f"\n{'─' * 60}")
        self._emit(f"[P{period}] Step A: OR Baseline (Capped Base-stock Policy)")
        self._emit(f"{'─' * 60}")
        self._emit(f"  INPUT:")
        self._emit(f"    demand_history (n={len(obs['demand_history'])}): {obs['demand_history']}")
        self._emit(f"    on_hand_inventory : {obs['on_hand_inventory']}")
        self._emit(f"    in_transit_total  : {obs.get('in_transit_total', 0)}")
        self._emit(f"  OUTPUT:")
        self._emit(f"    d_bar (需求均值)        : {or_rec.demand_mean:.2f}")
        self._emit(f"    s_d   (需求标准差)       : {or_rec.demand_std:.2f}")
        self._emit(f"    mu_hat = (1+L)*d_bar    : {or_rec.mu_hat:.2f}")
        self._emit(f"    sigma_hat = sqrt(1+L)*s_d: {or_rec.sigma_hat:.2f}")
        self._emit(f"    rho = p/(p+h)           : {or_rec.critical_fractile:.4f}")
        self._emit(f"    z* = Phi^-1(rho)        : {or_rec.z_star:.4f}")
        self._emit(f"    B (base-stock level)    : {or_rec.base_stock_level:.2f}")
        self._emit(f"    IP (inventory position) : {or_rec.inventory_position:.2f}")
        self._emit(f"    cap (order cap)         : {or_rec.order_cap:.2f}")
        self._emit(f"    q_or (OR recommendation): {or_rec.recommended_order}")

    def log_step_b(self, period: int, user_msg: str, carry_over: str):
        """Step B: User Message Assembly -- 三段式消息构建"""
        self._emit(f"\n{'─' * 60}")
        self._emit(f"[P{period}] Step B: User Message Assembly")
        self._emit(f"{'─' * 60}")
        has_insight = bool(carry_over and carry_over.strip())
        self._emit(f"  INPUT:")
        if has_insight:
            self._emit(f"    carry_over_insights ({len(carry_over)} chars):")
            for line in carry_over.split('\n'):
                self._emit(f"      | {line}")
        else:
            self._emit(f"    carry_over_insights: (none)")
        self._emit(f"  OUTPUT (user message, {len(user_msg)} chars):")
        self._emit(f"    " + "-" * 56)
        for line in user_msg.split('\n'):
            self._emit(f"    | {line}")
        self._emit(f"    " + "-" * 56)

    def log_step_c(self, period: int, llm_raw: str, parsed: AgentResponse):
        """Step C: LLM Inference + Parse"""
        self._emit(f"\n{'─' * 60}")
        self._emit(f"[P{period}] Step C: LLM Inference (DeepSeek Chat)")
        self._emit(f"{'─' * 60}")
        self._emit(f"  LLM RAW OUTPUT ({len(llm_raw)} chars):")
        self._emit(f"    " + "-" * 56)
        for line in llm_raw.split('\n'):
            self._emit(f"    | {line}")
        self._emit(f"    " + "-" * 56)
        self._emit(f"  PARSED AgentResponse:")
        self._emit(f"    rationale          : {parsed.rationale[:120]}{'...' if len(parsed.rationale) > 120 else ''}")
        self._emit(f"    short_rationale    : {parsed.short_rationale_for_human}")
        self._emit(f"    carry_over_insight : {'(new insight: ' + str(len(parsed.carry_over_insight)) + ' chars)' if parsed.carry_over_insight else '(none)'}")
        self._emit(f"    order_quantity     : {parsed.order_quantity}")

    def log_step_d(self, period: int, q_t: int, lead_time: int, arrivals: int, starting_inv: int,
                   demand: int, sold: int, ending_inv: int, p: float, h: float, reward: float):
        """Step D: State Transition -- 库存环境状态转移五子步骤"""
        self._emit(f"\n{'─' * 60}")
        self._emit(f"[P{period}] Step D: State Transition (env.step)")
        self._emit(f"{'─' * 60}")
        self._emit(f"  D1. PLACE ORDER")
        self._emit(f"      quantity={q_t}, lead_time={lead_time}")
        self._emit(f"      -> InTransitOrder(period_placed={period}, quantity={q_t}, lead_time={lead_time})")
        self._emit(f"  D2. ARRIVAL RESOLUTION")
        self._emit(f"      arrived_in_this_period = {arrivals}")
        self._emit(f"      -> on_hand += {arrivals}")
        self._emit(f"  D3. DEMAND RESOLUTION")
        self._emit(f"      demand = {demand}, on_hand (after arrival) = {starting_inv}")
        self._emit(f"      sold = min(demand={demand}, on_hand={starting_inv}) = {sold}")
        self._emit(f"      -> on_hand -= {sold}")
        self._emit(f"  D4. REWARD CALCULATION")
        self._emit(f"      profit = p * sold = {p} * {sold} = {p * sold:.1f}")
        self._emit(f"      holding_cost = h * ending_inv = {h} * {ending_inv} = {h * ending_inv:.1f}")
        self._emit(f"      reward = {p * sold:.1f} - {h * ending_inv:.1f} = {reward:.2f}")
        self._emit(f"  D5. NEXT OBSERVATION")
        self._emit(f"      ending_inventory = {ending_inv}")
        self._emit(f"      total_reward so far will include this period's reward")
