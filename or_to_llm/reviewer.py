import json
from dataclasses import dataclass, field
from typing import List
from openai import OpenAI


@dataclass
class ReviewResult:
    approved: bool
    original_qty: int
    adjusted_qty: int
    reason: str
    triggered_llm: bool = False


REVIEWER_SYSTEM_PROMPT = """You are an inventory decision auditor. Verify order quantities are consistent with the stated rationale and OR baseline.

Critical fractile: {rho:.2f} (p={p}, h={h})

Rules:
- If on-hand inventory is high and OR recommends 0, a large order needs strong justification
- If rationale says "demand is decreasing" but order > OR recommendation, flag it
- Order cap from OR baseline is a hard ceiling
- Deviation > 2 sigma from OR recommendation requires explicit, evidence-backed justification in the rationale

Reply with JSON only:
{{"approved": true/false, "adjusted_qty": <int>, "reason": "<one sentence>"}}"""


class ReviewerAgent:
    def __init__(self, p: float, h: float, client: OpenAI,
                 model: str = "deepseek-chat", deviation_threshold: float = 2.0,
                 system_prompt=None):
        self.p = p
        self.h = h
        self.rho = p / (p + h)
        self.client = client
        self.model = model
        self.deviation_threshold = deviation_threshold
        self.system_prompt = system_prompt or REVIEWER_SYSTEM_PROMPT.format(
            p=p, h=h, rho=self.rho,
        )
        self.history: List[ReviewResult] = []

    def review(self, qty: int, or_rec, llm_rationale: str, obs: dict) -> ReviewResult:
        # Phase 1: hard rules
        if qty < 0:
            return self._reject(qty, 0, "Negative quantity clamped")

        if qty > or_rec.order_cap * 1.5:
            return self._reject(qty, int(or_rec.order_cap),
                                f"Exceeds cap {or_rec.order_cap:.0f}")

        # Phase 2: LLM review if large deviation
        deviation = abs(qty - or_rec.recommended_order)
        sigma = max(or_rec.sigma_hat, 1.0)
        if deviation > self.deviation_threshold * sigma:
            return self._llm_review(qty, or_rec, llm_rationale, obs)

        return ReviewResult(True, qty, qty, "Within tolerance")

    def _llm_review(self, qty: int, or_rec, rationale: str, obs: dict) -> ReviewResult:
        user_msg = (
            f"OR Recommended: {or_rec.recommended_order}\n"
            f"LLM Decided: {qty}\n"
            f"LLM Rationale: {rationale}\n"
            f"Context: mean_demand={or_rec.demand_mean:.1f}, on_hand={obs['on_hand_inventory']}, "
            f"cap={or_rec.order_cap:.1f}, B={or_rec.base_stock_level:.1f}"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=256,
            )
            text = response.choices[0].message.content.strip()
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
            data = json.loads(text)
            result = ReviewResult(
                approved=data.get("approved", True),
                original_qty=qty,
                adjusted_qty=data.get("adjusted_qty", qty),
                reason=data.get("reason", ""),
                triggered_llm=True,
            )
        except Exception:
            result = ReviewResult(True, qty, qty, "Reviewer parse error", True)

        self.history.append(result)
        return result

    def _reject(self, original: int, adjusted: int, reason: str) -> ReviewResult:
        result = ReviewResult(False, original, adjusted, reason, False)
        self.history.append(result)
        return result

    @property
    def override_rate(self) -> float:
        if not self.history:
            return 0.0
        return sum(1 for r in self.history if not r.approved) / len(self.history)
