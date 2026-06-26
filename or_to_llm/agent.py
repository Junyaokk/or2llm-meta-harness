"""
OR->LLM 智能体 -- 用户消息构建、LLM 响应解析、主决策循环.
对应论文 Section 3.1 "LLM Agents", Figure 2.
"""

import json
import re
import time
from dataclasses import dataclass
from typing import List, Tuple

from openai import OpenAI
from scipy.stats import norm

from .or_baseline import ORBaseline, ORRecommendation

# ============================================================================
# 系统提示词 -- 严格对齐论文 Appendix B
# ============================================================================

SYSTEM_PROMPT_TEMPLATE = """You control the vending machine for a single SKU "{item_id}" while collaborating with an OR baseline. Maximize total reward R_t = Profit x units_sold - HoldingCost x ending_inventory each period.

**Period execution sequence:**
1. **VM Decision Phase:** You receive observation (including OR recommendation) and place orders for Period N
2. **Arrival Resolution:** Orders scheduled to arrive in Period N are added to on-hand inventory
3. **Demand Resolution:** Customer demand is satisfied from on-hand inventory
4. **Period Conclusion:** System generates "Period N conclude" message (visible in Period N+1)

Important: Steps 2-4 happen AFTER your decision. You will see their results in the next period.

**Lead time definition.** Promised lead time: {anticipated_lead_time} period(s). An order placed in Period N arrives during Period (N+L)'s arrival resolution, becomes visible in the "Period (N+L) conclude" message, and is read at the start of Period (N+L+1)'s decision phase. There is always a 1-period observation delay. Actual lead time may differ from promised; orders may also be lost (never arrive).

**The OR agent uses a capped base-stock policy:**

1. **Demand estimation** (from historical samples x_1, ..., x_n):
   Empirical mean: m = (1/n) sum_i x_i
   Std dev: s = sqrt(1/(n-1) sum_i (x_i - m)^2)
   Over lead time horizon: mu_hat = (1+L) * m, sigma_hat = sqrt(1+L) * s

2. **Safety factor:** q = p/(p+h), z* = Phi^{{-1}}(q)
   Current: p={p}, h={h}, q={critical_fractile:.4f}, z*={z_star:.4f}

3. **Base stock:** B = mu_hat + z* * sigma_hat

4. **Capped order:** q_t = max(0, min(B - IP_t, cap))
   where cap = mu_hat/(1+L) + Phi^{{-1}}(0.95) * sigma_hat/sqrt(1+L)
   and IP_t = on-hand + all in-transit orders

5. **OR limitations:** Uses promised (not actual) lead time; weights all historical samples equally; cannot detect lost orders or regime shifts; assumes i.i.d. demand.

**Your role:** The OR recommendation is a data-driven baseline. Override it when you detect: actual vs. promised lead time discrepancies, demand regime changes, seasonality (from dates + product description), or lost shipments.

**Decision checklist:**
1. Use world knowledge and SKU description to assess demand outlook.
2. Reconcile on-hand + pipeline with expected arrivals; flag overdue/lost shipments.
3. Inspect the OR recommendation (quantity + stats) and decide how to adapt it.
4. Justify final quantity by tying it to demand outlook, lead-time belief, and OR's baseline.

**Carry-over insights:** Record only NEW, evidence-backed insights about sustained shifts (demand mean/variance, lead time, seasonality). Stay conservative; provide concrete stats. Remove insights once they stop being true.

**Output format** (JSON):
{{
  "rationale": "full step-by-step analysis",
  "short_rationale_for_human": "1-3 sentence summary",
  "carry_over_insight": "new sustained discoveries, or empty string",
  "action": {{"{item_id}": quantity}}
}}

Respond ONLY with the JSON object, no other text."""


# ============================================================================
# 用户消息构建器
# ============================================================================

class UserMessageBuilder:
    """构建每周期动态用户消息 -- 对应论文 Per-period user message."""

    @staticmethod
    def build(
        obs: dict,
        or_rec: ORRecommendation,
        carry_over_insights: str,
        item_id: str,
        context: str = "",
    ) -> str:
        parts = []

        # Part 1: 跨期洞察
        if carry_over_insights and carry_over_insights.strip():
            parts.append(
                "=" * 70 + "\n" +
                "CARRY-OVER INSIGHTS (Key Discoveries):\n" +
                "=" * 70 + "\n" +
                carry_over_insights + "\n" +
                "=" * 70
            )

        # Part 2: 当前观测
        in_transit_lines = []
        for o in obs.get("in_transit_orders", []):
            in_transit_lines.append(
                f"  Period {o['period_placed']}: {o['quantity']} units "
                f"(lead_time={o['lead_time']}, waited {o['waited_periods']} periods)"
            )
        in_transit_str = "\n".join(in_transit_lines) if in_transit_lines else "  (none)"

        recent_n = min(10, len(obs["demand_history"]))
        recent_demands = obs["demand_history"][-recent_n:]
        all_demands = obs["demand_history"]

        obs_lines = [
            f"PERIOD {obs['period']} / {obs['total_periods']}",
            "",
            "=== CURRENT STATUS ===",
            f"Item: {item_id}",
            f"On-hand inventory: {obs['on_hand_inventory']}",
            f"In-transit orders ({obs['in_transit_total']} total):",
            in_transit_str,
        ]

        if context:
            obs_lines.append(f"\nProduct context: {context}")

        if obs.get("last_period_conclude"):
            obs_lines.append("")
            obs_lines.append("=== LAST PERIOD CONCLUDE ===")
            obs_lines.append(obs["last_period_conclude"])

        obs_lines.append("")
        obs_lines.append(f"Recent demand history (last {recent_n} periods): {recent_demands}")
        obs_lines.append(f"All demand history ({len(all_demands)} periods): {all_demands}")

        parts.append("\n".join(obs_lines))

        # Part 3: OR 推荐
        or_lines = [
            "",
            "=" * 70,
            "OR ALGORITHM RECOMMENDATIONS (capped base-stock policy):",
            "",
            f"  Demand mean (d_bar): {or_rec.demand_mean:.1f}",
            f"  Demand std (s_d): {or_rec.demand_std:.1f}",
            f"  Lead time demand mean (mu_hat): {or_rec.mu_hat:.1f}",
            f"  Lead time demand std (sigma_hat): {or_rec.sigma_hat:.1f}",
            f"  Critical fractile (rho): {or_rec.critical_fractile:.4f}",
            f"  Safety factor (z*): {or_rec.z_star:.4f}",
            f"  Base-stock level (B): {or_rec.base_stock_level:.1f}",
            f"  Inventory position (IP): {or_rec.inventory_position:.1f}",
            f"  Order cap: {or_rec.order_cap:.1f}",
            f"  OR recommended order: {or_rec.recommended_order}",
            "",
            "Note: OR uses the promised lead time and historical demand only.",
            "It cannot see lost shipments, or actual lead-time shifts -- adjust accordingly.",
            "=" * 70,
        ]
        parts.append("\n".join(or_lines))

        return "\n".join(parts)


# ============================================================================
# 响应解析器
# ============================================================================

@dataclass
class AgentResponse:
    rationale: str
    short_rationale_for_human: str
    carry_over_insight: str
    order_quantity: int
    raw_json: dict


@dataclass
class DecisionRecord:
    """每周期完整决策链路 -- Step A/B/C 全部中间结果."""
    or_recommendation: "ORRecommendation"
    user_message: str
    llm_raw_output: str
    agent_response: AgentResponse

    @property
    def order_quantity(self) -> int:
        return self.agent_response.order_quantity


class ResponseParser:
    """解析 LLM JSON 响应 -- 对应论文 Output format."""

    @staticmethod
    def extract_json(text: str) -> dict:
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find('{')
        if start == -1:
            raise ValueError(f"No JSON found in response: {text[:200]}")

        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i + 1])

        raise ValueError(f"Unbalanced braces in response: {text[:200]}")

    @staticmethod
    def parse(llm_output: str, item_id: str) -> AgentResponse:
        data = ResponseParser.extract_json(llm_output)
        action = data.get("action", {})
        if isinstance(action, dict):
            quantity = action.get(item_id, action.get(list(action.keys())[0] if action else "qty", 0))
        else:
            quantity = action

        carry = data.get("carry_over_insight", "")
        if isinstance(carry, str):
            carry = carry.strip()
        else:
            carry = ""

        return AgentResponse(
            rationale=data.get("rationale", ""),
            short_rationale_for_human=data.get("short_rationale_for_human", ""),
            carry_over_insight=carry,
            order_quantity=int(quantity),
            raw_json=data,
        )


# ============================================================================
# OR->LLM 智能体主类
# ============================================================================

class ORToLLMAgent:
    """OR->LLM 库存控制智能体 -- 对应论文 Section 3.1, Figure 2."""

    def __init__(
        self,
        item_id: str,
        anticipated_lead_time: int,
        p: float,
        h: float,
        model: str = "deepseek-chat",
        api_key=None,
        base_url=None,
        client=None,
    ):
        self.item_id = item_id
        self.L = anticipated_lead_time
        self.p = p
        self.h = h

        self.system_prompt = self._build_system_prompt()
        self.or_baseline = ORBaseline(anticipated_lead_time, p, h)

        if client is not None:
            self.client = client
        else:
            self.client = OpenAI(
                api_key=api_key or "",
                base_url=base_url or "https://api.deepseek.com/v1",
                timeout=180.0,
                max_retries=2,
            )
        self.model = model

        self.carry_over_insights: str = ""
        self.decision_history: List[AgentResponse] = []

    def _build_system_prompt(self) -> str:
        rho = self.p / (self.p + self.h)
        return SYSTEM_PROMPT_TEMPLATE.format(
            item_id=self.item_id,
            anticipated_lead_time=self.L,
            p=self.p,
            h=self.h,
            critical_fractile=rho,
            z_star=norm.ppf(rho),
        )

    def decide(self, obs: dict, context: str = "") -> DecisionRecord:
        # Step A: OR Baseline
        or_rec = self.or_baseline.compute(
            demand_history=obs["demand_history"],
            on_hand=obs["on_hand_inventory"],
            in_transit_total=obs.get("in_transit_total", 0),
        )

        # Step B: User Message Assembly
        user_msg = UserMessageBuilder.build(
            obs=obs,
            or_rec=or_rec,
            carry_over_insights=self.carry_over_insights,
            item_id=self.item_id,
            context=context,
        )

        # Step C: LLM Inference + Parse
        llm_output = self._call_llm(user_msg)

        try:
            parsed = ResponseParser.parse(llm_output, self.item_id)
        except Exception:
            parsed = AgentResponse(
                rationale="(parse error -- using OR recommendation)",
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

    def _call_llm(self, user_message: str, max_retries: int = 3) -> str:
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.0,
                    max_tokens=4096,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")

    def run_episode(
        self, env, context: str = ""
    ) -> Tuple[List[int], float, List[AgentResponse]]:
        orders = []
        obs = env.get_initial_observation()

        while not env.done:
            record = self.decide(obs, context)
            q = record.order_quantity
            orders.append(q)
            result = env.step(q)
            obs = result["observation"]

        return orders, env.total_reward, self.decision_history
