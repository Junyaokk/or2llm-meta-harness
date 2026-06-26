"""
H2M Conversation Loop — multi-turn Decider ↔ Reviewer dialogue.

Unlike H2X where the Reviewer unilaterally adjusts the Decider's draft,
H2M lets the Decider RESPOND to the Reviewer's critique. The Decider
can defend its reasoning, partially accept the critique, or fully revise.

This mirrors real enterprise decision-making: analyst proposes, manager
challenges, analyst responds — consensus emerges from dialogue, not dictate.

LLM calls/period: 2 (agree) or 3 (disagree → revision round).
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional, List

from openai import OpenAI


# ====================================================================
# Conversation data types
# ====================================================================

@dataclass
class DraftOrder:
    """Decider's initial proposal (Round 1)."""
    order: int
    rationale: str
    short_rationale: str


@dataclass
class ReviewerCritique:
    """Reviewer's structured feedback (Round 2)."""
    agreed: bool
    critique: str
    concern_level: str       # "none" | "minor" | "major"
    suggested_order: int      # Reviewer's counter-proposal (meaningful only if disagreed)
    risk_flag: str            # "safe" | "caution" | "override"

    @classmethod
    def approve(cls, draft_order: int, reason: str = ""):
        return cls(
            agreed=True,
            critique=reason or "Draft looks reasonable.",
            concern_level="none",
            suggested_order=draft_order,
            risk_flag="safe",
        )


@dataclass
class DeciderRevision:
    """Decider's response to critique (Round 3)."""
    final_order: int
    accepted_critique: bool
    revision_rationale: str


@dataclass
class ConversationTrace:
    """Full record of the multi-turn conversation for one period."""
    draft: DraftOrder
    critique: ReviewerCritique
    revision: Optional[DeciderRevision] = None  # None if Reviewer agreed
    rounds: int = 2

    @property
    def final_order(self) -> int:
        if self.critique.agreed or self.revision is None:
            return self.draft.order
        return self.revision.final_order

    @property
    def reviewer_adjusted(self) -> bool:
        return not self.critique.agreed

    @property
    def decider_accepted_critique(self) -> bool:
        if self.revision is None:
            return False
        return self.revision.accepted_critique


# ====================================================================
# Default prompt templates
# ====================================================================

DEFAULT_REVIEWER_CRITIQUE_PROMPT = """You are a Supply Chain Manager reviewing a draft order for SKU "{item_id}". Lead time L={anticipated_lead_time}. p={p}, h={h}. OR cap={or_cap}. p={p} means stockouts are expensive — better to order slightly too much than too little.

**Your role:** Review the Analyst's draft order. If you see problems, provide a specific, reasoned CRITIQUE so the Analyst can respond. This is a COLLABORATIVE review, not a unilateral override.

**Check these in order. If ANY check fails, disagree and explain why:**

1. HARD BOUNDS: If draft < 0 or draft > cap → disagree, flag as "override".

2. PIPELINE CHECK:
   - OVERFILLED + draft > 10% of cap → disagree. The pipeline is full, ordering more is pure waste.
   - ADEQUATE + draft differs from OR by >30% with no clear reason → disagree.
   - UNDERFILLED + draft < OR → disagree. Stockout risk is real.

3. HISTORY CHECK: Look at the recent reward column.
   - Any negative rewards in last 3 periods? → disagree. The current strategy is failing.
   - Consistently positive rewards? → agree, strategy works.

4. DEMAND CHECK:
   - Trend "volatile" + draft deviates >20% from OR → disagree. Don't chase noise.
   - Trend "down" with evidence + draft > OR → disagree.
   - Trend "up" with evidence + draft < OR → disagree.

5. If no checks fail, AGREE.

**Output (JSON only):**
{{
  "agreed": true,
  "critique": "Draft looks reasonable. All checks passed." or "Specific concern: ...",
  "concern_level": "none",
  "suggested_order": <draft order if agreed, your counter-proposal if disagreed>,
  "risk_flag": "safe"
}}

concern_level must be "none" (agree), "minor" (small concern), or "major" (clear error).
risk_flag must be "safe", "caution", or "override".

Respond ONLY with JSON."""


DEFAULT_DECIDER_REVISE_PROMPT = """You are a Supply Chain Analyst. You drafted an order for SKU "{item_id}", and your manager reviewed it and DISAGREED with your draft.

**Context:** Lead time L={anticipated_lead_time}. p={p}, h={h}. OR cap={or_cap}.

**Your draft order was {draft_order}.** Your rationale: {draft_rationale}

**Your manager's critique:**
{critique_text}

**The manager suggests ordering {suggested_order}.** Concern level: {concern_level}.

**Your response options:**
1. ACCEPT the critique: If the manager makes a valid point, revise your order toward their suggestion. Explain what you missed.
2. PARTIALLY ACCEPT: If the critique has some merit but goes too far, adjust partway toward the suggestion.
3. DEFEND: If you believe your original draft was correct and the manager misunderstood the situation, keep your original order and explain why.

**Key principle:** As the Analyst, you see the detailed data. The manager sees the big picture. If their concern is valid, accept it. If their concern would cause worse outcomes (e.g., ordering too little when stockout risk is high), defend your position.

**Output (JSON only):**
{{
  "accepted_critique": true,
  "final_order": <integer between 0 and cap>,
  "rationale": "Explain: did you accept, partially accept, or defend? Why this final order?"
}}

Respond ONLY with JSON."""


# ====================================================================
# H2M Decider — supports draft + revision rounds
# ====================================================================

class H2MDecider:
    """Decider that can draft initial orders AND respond to Reviewer critique."""

    def __init__(self, item_id: str, model: str, api_key: str, base_url: str,
                 anticipated_lead_time: int, p: float, h: float,
                 draft_prompt_template: str, revise_prompt_template: str = ""):
        self.item_id = item_id
        self.L = anticipated_lead_time
        self.p = p
        self.h = h
        self.model = model

        from scipy.stats import norm
        rho = p / (p + h)
        z_star = float(norm.ppf(rho))

        self.draft_system_prompt = draft_prompt_template.format(
            item_id=item_id, anticipated_lead_time=anticipated_lead_time,
            p=p, h=h, critical_fractile=rho, z_star=z_star,
        )

        self.revise_template = revise_prompt_template or DEFAULT_DECIDER_REVISE_PROMPT

        self.client = OpenAI(
            api_key=api_key, base_url=base_url, timeout=180.0, max_retries=2,
        )

    def draft(self, analyst_report_text: str,
              or_recommended: int) -> DraftOrder:
        """Round 1: Draft initial order based on analyst report + history."""
        llm_output = self._call_llm(self.draft_system_prompt, analyst_report_text)
        try:
            data = self._parse_json(llm_output)
        except Exception:
            return DraftOrder(
                order=or_recommended,
                rationale="(parse error — using OR recommendation)",
                short_rationale="Following OR recommendation",
            )

        action = data.get("action", {})
        if isinstance(action, dict):
            qty = int(list(action.values())[0]) if action else or_recommended
        else:
            qty = int(action)

        return DraftOrder(
            order=max(0, qty),
            rationale=data.get("rationale", ""),
            short_rationale=data.get("short_rationale_for_human", ""),
        )

    def revise(self, analyst_report_text: str, or_recommended: int,
               draft_order: int, draft_rationale: str,
               critique_text: str, suggested_order: int,
               concern_level: str) -> DeciderRevision:
        """Round 3: Respond to Reviewer's critique — revise or defend."""
        system_prompt = self.revise_template.format(
            item_id=self.item_id, anticipated_lead_time=self.L,
            p=self.p, h=self.h, or_cap=9999,
            draft_order=draft_order, draft_rationale=draft_rationale[:400],
            critique_text=critique_text,
            suggested_order=suggested_order,
            concern_level=concern_level,
        )

        user_msg = f"""{analyst_report_text}

─── REVISION TASK ───
Your draft: {draft_order}. Manager suggests: {suggested_order}.
Critique: {critique_text}

Respond to the critique. Revise or defend."""

        llm_output = self._call_llm(system_prompt, user_msg, max_tokens=2048)
        try:
            data = self._parse_json(llm_output)
        except Exception:
            return DeciderRevision(
                final_order=draft_order,
                accepted_critique=False,
                revision_rationale="(parse error — keeping original draft)",
            )

        final_order = int(data.get("final_order", draft_order))
        return DeciderRevision(
            final_order=max(0, final_order),
            accepted_critique=bool(data.get("accepted_critique", False)),
            revision_rationale=data.get("rationale", ""),
        )

    def _call_llm(self, system_prompt: str, user_message: str,
                  max_tokens: int = 4096, max_retries: int = 3) -> str:
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"H2M Decider LLM call failed: {e}")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("H2M Decider LLM call failed after retries")

    @staticmethod
    def _parse_json(llm_output: str) -> dict:
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
        return json.loads(json_str)


# ====================================================================
# H2M Reviewer — critique-focused, not dictating
# ====================================================================

class H2MReviewer:
    """Reviewer that provides structured CRITIQUE rather than final order."""

    def __init__(self, item_id: str, model: str, api_key: str, base_url: str,
                 anticipated_lead_time: int, p: float, h: float,
                 or_cap: int, critique_prompt_template: str = ""):
        self.item_id = item_id
        self.L = anticipated_lead_time
        self.p = p
        self.h = h
        self.or_cap = or_cap
        self.model = model

        template = critique_prompt_template or DEFAULT_REVIEWER_CRITIQUE_PROMPT
        self.system_prompt = template.format(
            item_id=item_id, anticipated_lead_time=anticipated_lead_time,
            p=p, h=h, or_cap=or_cap,
        )

        self.client = OpenAI(
            api_key=api_key, base_url=base_url, timeout=180.0, max_retries=2,
        )

    def critique(self, analyst_report_text: str, memory_table: str,
                 draft_order: int, draft_rationale: str,
                 or_recommended: int) -> ReviewerCritique:
        """Round 2: Review the draft and provide structured critique."""
        user_msg = self._build_message(analyst_report_text, memory_table,
                                       draft_order, draft_rationale,
                                       or_recommended)
        llm_output = self._call_llm(user_msg)

        try:
            return self._parse_critique(llm_output, draft_order)
        except Exception:
            return ReviewerCritique.approve(
                draft_order, "(parse error — approving draft as-is)")

    def _build_message(self, analyst_report: str, memory_table: str,
                       draft_order: int, draft_rationale: str,
                       or_recommended: int) -> str:
        parts = []
        parts.append("=" * 60)
        parts.append("REVIEW TASK: Critique the Analyst's draft order.")
        parts.append("=" * 60)
        parts.append("")
        parts.append(memory_table)
        parts.append("")
        parts.append("─── CURRENT STATE ───")
        parts.append(analyst_report)
        parts.append("")
        parts.append(f"─── DRAFT ORDER: {draft_order} ───")
        parts.append(f"OR recommendation: {or_recommended}")
        parts.append(f"Cap: {self.or_cap}")
        parts.append(f"Rationale: {draft_rationale[:400]}")
        parts.append("")
        parts.append("Provide your structured critique. AGREE if no checks fail.")
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
                    raise RuntimeError(f"H2M Reviewer LLM call failed: {e}")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("H2M Reviewer LLM call failed after retries")

    @staticmethod
    def _parse_critique(llm_output: str, draft_order: int) -> ReviewerCritique:
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

        agreed = bool(data.get("agreed", True))
        concern_level = str(data.get("concern_level", "none"))
        risk_flag = str(data.get("risk_flag", "safe"))

        suggested_order = draft_order
        if "suggested_order" in data:
            suggested_order = int(data["suggested_order"])

        return ReviewerCritique(
            agreed=agreed,
            critique=data.get("critique", ""),
            concern_level=concern_level,
            suggested_order=suggested_order,
            risk_flag=risk_flag,
        )


# ====================================================================
# Conversation orchestrator
# ====================================================================

class H2MConversation:
    """Orchestrates multi-turn Decider ↔ Reviewer dialogue for one period."""

    def __init__(self, decider: H2MDecider, reviewer: H2MReviewer,
                 max_rounds: int = 3):
        self.decider = decider
        self.reviewer = reviewer
        self.max_rounds = max_rounds

    def run(self, analyst_report_text: str, memory_table_for_decider: str,
            memory_table_for_reviewer: str, or_recommended: int) -> ConversationTrace:
        """Execute the full conversation for one period.

        Round 1: Decider drafts
        Round 2: Reviewer critiques
        Round 3 (if disagreement): Decider revises or defends

        Returns full conversation trace.
        """
        # Round 1: Decider drafts
        draft = self.decider.draft(analyst_report_text, or_recommended)

        # Round 2: Reviewer critiques
        critique = self.reviewer.critique(
            analyst_report_text, memory_table_for_reviewer,
            draft.order, draft.rationale, or_recommended)

        # Enforce hard bounds on suggested_order
        cap = self.reviewer.or_cap
        critique.suggested_order = max(0, min(cap, critique.suggested_order))

        # If Reviewer agrees, done
        if critique.agreed:
            return ConversationTrace(
                draft=draft,
                critique=critique,
                revision=None,
                rounds=2,
            )

        # Round 3: Decider responds to critique
        revision = self.decider.revise(
            analyst_report_text, or_recommended,
            draft.order, draft.rationale,
            critique.critique, critique.suggested_order,
            critique.concern_level,
        )
        revision.final_order = int(max(0, min(cap, revision.final_order)))

        return ConversationTrace(
            draft=draft,
            critique=critique,
            revision=revision,
            rounds=3,
        )
