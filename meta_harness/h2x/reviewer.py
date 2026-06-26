"""
Reviewer — second LLM call that sanity-checks the Decider's draft order.
Implements the "four-eyes principle" for enterprise supply chain decisions.
Meta-Harness search object ④: Reviewer prompt template.
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional


class _SafeDict(dict):
    """Dict that returns placeholder unchanged for missing keys, preventing KeyError on format."""
    def __missing__(self, key):
        return '{' + key + '}'


def _safe_format(template: str, **kwargs) -> str:
    """Format a template string, leaving unknown placeholders as-is."""
    return template.format_map(_SafeDict(**kwargs))

from openai import OpenAI


@dataclass
class ReviewerDecision:
    """Reviewer output — may approve or adjust the Decider's draft."""
    final_order: int
    approved: bool
    adjustment_pct: float
    review_rationale: str
    risk_flag: str  # "safe" | "caution" | "override"

    @classmethod
    def approve_draft(cls, draft_order: int, rationale: str = "Approved as is."):
        return cls(
            final_order=draft_order,
            approved=True,
            adjustment_pct=0.0,
            review_rationale=rationale,
            risk_flag="safe",
        )


REVIEWER_SYSTEM_PROMPT_TEMPLATE = """You are a Supply Chain Manager reviewing a Supply Chain Analyst's draft order. Your job: sanity-check the draft before execution.

**Context:** SKU "{item_id}". Lead time L={anticipated_lead_time}. p={p}, h={h}. OR cap={or_cap}.

**Your role:** You see the same analysis and history the Analyst saw, plus their draft order and rationale. You check for obvious mistakes:
1. Is the order between 0 and cap? (hard constraint — if violated, override to 0 or cap)
2. Does the order make sense given pipeline status? (OVERFILLED + large order = suspicious)
3. Does the order align with the demand trend visible in history?
4. Is there a pattern of bad decisions in the reward history?

**Adjustment rules:**
- If the draft looks reasonable, APPROVE it (same quantity).
- If you see a clear mistake, ADJUST within ±30% of the draft (or cap limit).
- If the Decider clearly misread the pipeline or trend, flag as "override" and adjust more aggressively.
- When in doubt, bias toward the OR recommendation — it's the mathematically safe fallback.
- Do NOT change the order just because you have a different opinion. Only change if you see a clear ERROR.

**Output (JSON only):**
{{
  "approved": true or false,
  "final_order": <integer between 0 and cap>,
  "adjustment_reason": "Why you changed it, or 'No change needed' if approved",
  "risk_flag": "safe" or "caution" or "override"
}}

Respond ONLY with JSON."""


class Reviewer:
    """Second LLM call that reviews the Decider's draft before execution."""

    def __init__(self, item_id: str, model: str, api_key: str, base_url: str,
                 anticipated_lead_time: int, p: float, h: float,
                 or_cap: int, system_prompt_template: str = ""):
        self.item_id = item_id
        self.L = anticipated_lead_time
        self.p = p
        self.h = h
        self.or_cap = or_cap
        self.model = model

        template = system_prompt_template or REVIEWER_SYSTEM_PROMPT_TEMPLATE
        self.system_prompt = _safe_format(template,
            item_id=item_id,
            anticipated_lead_time=anticipated_lead_time,
            p=p, h=h,
            or_cap=or_cap,
        )

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=180.0,
            max_retries=2,
        )

    def review(self, analyst_report_text: str, memory_table: str,
               draft_order: int, draft_rationale: str,
               or_recommended: int) -> ReviewerDecision:
        """Review the Decider's draft. Returns final order (may differ from draft)."""
        user_message = self._build_review_message(
            analyst_report_text, memory_table,
            draft_order, draft_rationale, or_recommended)

        llm_output = self._call_llm(user_message)

        try:
            decision = self._parse_response(llm_output, draft_order)
        except Exception:
            decision = ReviewerDecision.approve_draft(
                draft_order, "(parse error — approving draft as-is)")

        # Enforce hard bounds
        decision.final_order = max(0, min(self.or_cap, decision.final_order))
        return decision

    def _build_review_message(self, analyst_report: str, memory_table: str,
                              draft_order: int, draft_rationale: str,
                              or_recommended: int) -> str:
        parts = []
        parts.append("=" * 60)
        parts.append("REVIEW TASK: Check the Analyst's draft order before execution.")
        parts.append("=" * 60)
        parts.append("")
        parts.append(memory_table)
        parts.append("")
        parts.append("─── CURRENT STATE (Analyst Report) ───")
        parts.append(analyst_report)
        parts.append("")
        parts.append(f"─── DECIDER'S DRAFT ───")
        parts.append(f"Draft order: {draft_order}")
        parts.append(f"OR recommendation: {or_recommended}")
        parts.append(f"Cap: {self.or_cap}")
        parts.append(f"Draft rationale: {draft_rationale[:400]}")
        parts.append("")
        parts.append("Review this draft. Is it reasonable given the history and current state?")
        return "\n".join(parts)

    def _call_llm(self, user_message: str, max_retries: int = 3) -> str:
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.0,
                    max_tokens=1024,
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Reviewer LLM call failed: {e}")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("Reviewer LLM call failed after retries")

    def _parse_response(self, llm_output: str,
                        draft_order: int) -> ReviewerDecision:
        raw = llm_output.strip()
        json_str = raw

        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:])
            if json_str.endswith("```"):
                json_str = json_str[:-3]

        if not json_str.startswith("{"):
            start = json_str.find("{")
            if start >= 0:
                depth = 0
                end = -1
                for i in range(start, len(json_str)):
                    if json_str[i] == "{":
                        depth += 1
                    elif json_str[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    json_str = json_str[start:end]

        data = json.loads(json_str)

        final_order = int(data.get("final_order", draft_order))
        approved = bool(data.get("approved", True))
        risk_flag = str(data.get("risk_flag", "safe"))
        review_rationale = data.get("adjustment_reason", "")

        adjustment_pct = 0.0
        if draft_order > 0:
            adjustment_pct = (final_order - draft_order) / draft_order * 100

        return ReviewerDecision(
            final_order=final_order,
            approved=approved,
            adjustment_pct=round(adjustment_pct, 1),
            review_rationale=review_rationale,
            risk_flag=risk_flag,
        )
