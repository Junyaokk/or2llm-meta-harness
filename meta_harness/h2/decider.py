"""
Decider — LLM decision layer. Receives AnalystReport (pre-computed),
exercises judgment, returns order quantity. The SYSTEM_PROMPT is the
Meta-Harness search object ②.
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


class _SafeDict(dict):
    """Dict that returns placeholder unchanged for missing keys."""
    def __missing__(self, key):
        return '{' + key + '}'


def _safe_format(template: str, **kwargs) -> str:
    """Format a template string, leaving unknown placeholders as-is."""
    return template.format_map(_SafeDict(**kwargs))


@dataclass
class DeciderResponse:
    """Parsed LLM decision output."""
    rationale: str
    short_rationale: str
    carry_over_insight: str
    order_quantity: int
    raw_json: dict
    raw_output: str


class Decider:
    """LLM that judges pre-analyzed state. No arithmetic, only judgment."""

    def __init__(self, item_id: str, system_prompt_template: str,
                 model: str, api_key: str, base_url: str,
                 anticipated_lead_time: int, p: float, h: float):
        self.item_id = item_id
        self.L = anticipated_lead_time
        self.p = p
        self.h = h
        self.model = model
        self.carry_over_insights = ""

        rho = p / (p + h)
        from scipy.stats import norm
        z_star = float(norm.ppf(rho))

        self.system_prompt = _safe_format(system_prompt_template,
            item_id=item_id,
            anticipated_lead_time=anticipated_lead_time,
            p=p, h=h,
            critical_fractile=rho,
            z_star=z_star,
        )

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=180.0,
            max_retries=2,
        )

    def decide(self, analyst_report_text: str,
               or_recommended: int) -> DeciderResponse:
        """Call LLM with analyst report as user message. Return parsed response."""
        llm_output = self._call_llm(analyst_report_text)

        try:
            parsed = self._parse_response(llm_output)
        except Exception:
            parsed = DeciderResponse(
                rationale="(parse error — using OR recommendation)",
                short_rationale="Following OR recommendation",
                carry_over_insight="",
                order_quantity=or_recommended,
                raw_json={},
                raw_output=llm_output,
            )

        # Update carry-over
        if parsed.carry_over_insight and parsed.carry_over_insight.strip():
            self.carry_over_insights = parsed.carry_over_insight.strip()

        return parsed

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
                    max_tokens=4096,
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"LLM call failed: {e}")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("LLM call failed after retries")

    def _parse_response(self, llm_output: str) -> DeciderResponse:
        raw = llm_output.strip()
        json_str = raw

        # Strip markdown fences
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:])
            if json_str.endswith("```"):
                json_str = json_str[:-3]

        # Extract JSON object by bracket matching
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

        # Extract order quantity
        action = data.get("action", {})
        if isinstance(action, dict):
            qty = int(list(action.values())[0]) if action else 0
        else:
            qty = int(action)

        return DeciderResponse(
            rationale=data.get("rationale", ""),
            short_rationale=data.get("short_rationale_for_human", ""),
            carry_over_insight=data.get("carry_over_insight", ""),
            order_quantity=qty,
            raw_json=data,
            raw_output=raw,
        )
