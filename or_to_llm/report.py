"""
Markdown report builder for interview demo.
Generates a well-structured .md file from run results + trace log content.
No CDN dependency -- renders correctly on GitHub, Typora, VS Code, etc.
"""

from typing import List, Dict, Any


class ReportBuilder:
    """Build a comprehensive Markdown report from run results."""

    def __init__(self, output_path: str = "report.md"):
        self.output_path = output_path

    def build(
        self,
        period_log: List[Dict[str, Any]],
        decision_history: list,
        config: Dict[str, Any],
        total_reward: float,
        normalized_reward: float,
        instance_info: Dict[str, str] = None,
    ) -> str:
        n = len(period_log)
        inst = instance_info or {}
        pattern_desc = config.get("description", "") or f"{inst.get('pattern', '')}/{inst.get('variant', '')}/{inst.get('instance', '')}"
        p_val = config["p"]
        h_val = config["h"]
        rho = p_val / (p_val + h_val)
        L_val = config["lead_time"]
        item_id = config.get("item_id", "N/A")

        # Extract data
        demands = [e["demand"] for e in period_log]
        llm_orders = [e["ordered"] for e in period_log]
        solds = [e["sold"] for e in period_log]
        on_hand_after = [e["on_hand_after"] for e in period_log]
        arriveds = [e["arrived"] for e in period_log]
        rewards = [e["reward"] for e in period_log]

        or_orders = []
        rationales = []
        insights = []
        for rec in decision_history:
            or_orders.append(rec.or_recommendation.recommended_order)
            rationales.append(rec.agent_response.short_rationale_for_human)
            c = rec.agent_response.carry_over_insight
            insights.append(c if (c and c.strip()) else None)

        cum_reward = []
        running = 0.0
        for r in rewards:
            running += r
            cum_reward.append(running)

        override_count = sum(1 for llm, o in zip(llm_orders, or_orders) if abs(llm - o) > 0.5)
        stockout_count = sum(1 for inv in on_hand_after if inv == 0)
        insight_count = sum(1 for i in insights if i)

        lines = []

        # ===================================================================
        # Title & Metadata
        # ===================================================================
        lines.extend([
            f"# OR→LLM Inventory Control Agent — Experiment Report",
            "",
            "| Parameter | Value |",
            "|-----------|-------|",
            f"| **Item** | `{item_id}` |",
            f"| **Lead Time (L)** | {L_val} |",
            f"| **Selling Price (p)** | {p_val} |",
            f"| **Holding Cost (h)** | {h_val} |",
            f"| **Critical Fractile (ρ)** | {rho:.4f} |",
            f"| **Instance** | {pattern_desc} |",
            f"| **Periods** | {n} |",
            f"| **Model** | DeepSeek Chat (temperature=0) |",
            "",
            "---",
            "",
        ])

        # ===================================================================
        # Results Summary
        # ===================================================================
        lines.extend([
            "## Results Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| **Total Reward** | ${total_reward:,.2f} |",
            f"| **Normalized Reward** | {normalized_reward:.4f} |",
            f"| **LLM Override Rate** | {override_count}/{n} ({100*override_count/n:.0f}%) |",
            f"| **Stockout Periods** | {stockout_count} |",
            f"| **Insights Generated** | {insight_count} |",
            f"| **Avg Period Reward** | ${running/n:,.1f} |",
            f"| **Avg Demand** | {sum(demands)/n:.1f} |",
            f"| **Service Level (fill rate)** | {sum(solds)/sum(demands)*100:.1f}% |",
            "",
            "---",
            "",
        ])

        # ===================================================================
        # Algorithm Overview (LaTeX formulas)
        # ===================================================================
        lines.extend([
            "## Algorithm: Capped Base-Stock Policy (OR Baseline)",
            "",
            "The OR baseline computes a data-driven order recommendation each period.",
            "The LLM agent observes this recommendation and decides whether to accept or override it.",
            "",
            "**Step 1 — Demand Estimation (from historical samples $x_1, \\ldots, x_n$):**",
            "",
            "$$\\bar{d} = \\frac{1}{n}\\sum_{i=1}^{n} x_i \\qquad s_d = \\sqrt{\\frac{1}{n-1}\\sum_{i=1}^{n}(x_i - \\bar{d})^2}$$",
            "",
            "**Step 2 — Lead Time Projection:**",
            "",
            "$$\\hat{\\mu} = (1+L) \\cdot \\bar{d} \\qquad \\hat{\\sigma} = \\sqrt{1+L} \\cdot s_d$$",
            "",
            "**Step 3 — Safety Factor (Critical Fractile):**",
            "",
            "$$\\rho = \\frac{p}{p+h} \\qquad z^* = \\Phi^{-1}(\\rho)$$",
            "",
            "**Step 4 — Base-Stock Level:**",
            "",
            "$$B = \\hat{\\mu} + z^* \\cdot \\hat{\\sigma}$$",
            "",
            "**Step 5 — Capped Order:**",
            "",
            "$$q_t^{\\text{OR}} = \\max\\left(0,\\; \\min(B - IP_t,\\; \\text{cap})\\right)$$",
            "",
            f"where $\\text{{cap}} = \\frac{{\\hat{{\\mu}}}}{{1+L}} + \\Phi^{{-1}}(0.95) \\cdot \\frac{{\\hat{{\\sigma}}}}{{\\sqrt{{1+L}}}}$ and $IP_t$ = on-hand + all in-transit orders.",
            "",
            "**LLM Agent's Role:** Override $q_t^{\\text{OR}}$ when detecting demand regime shifts, lead time discrepancies, or seasonality.",
            "",
            "---",
            "",
        ])

        # ===================================================================
        # Per-Period Decision Table
        # ===================================================================
        lines.extend([
            "## Period-by-Period Decision Log",
            "",
            "| P | Demand | LLM Order | OR Rec | Δ | Sold | Arrived | End Inv | Reward | Stockout | Insight |",
            "|---|--------|-----------|--------|---|------|---------|---------|--------|----------|---------|",
        ])

        for i in range(n):
            delta = llm_orders[i] - or_orders[i]
            delta_str = f"+{delta}" if delta > 0 else str(delta)
            so = "⚠️" if on_hand_after[i] == 0 else ""
            ins = "💡" if insights[i] else ""
            lines.append(
                f"| {i+1} | {demands[i]} | **{llm_orders[i]}** | {or_orders[i]} | {delta_str} | {solds[i]} | {arriveds[i]} | {on_hand_after[i]} | ${rewards[i]:,.0f} | {so} | {ins} |"
            )

        lines.append("")
        lines.append(f"> **Δ = LLM − OR**. Positive = LLM orders more aggressively. Negative = LLM is more conservative.")
        lines.append(f"> 💡 = carry-over insight generated this period. ⚠️ = stockout (ending inventory = 0).")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ===================================================================
        # LLM Decision Rationale (each period)
        # ===================================================================
        lines.extend([
            "## LLM Decision Rationale (per period)",
            "",
        ])

        for i in range(n):
            lines.extend([
                f"### Period {i+1}",
                "",
                f"| | Value |",
                f"|---|-------|",
                f"| Demand | {demands[i]} |",
                f"| **LLM Order** | **{llm_orders[i]}** |",
                f"| OR Recommendation | {or_orders[i]} |",
                f"| Sold | {solds[i]} |",
                f"| Ending Inventory | {on_hand_after[i]} |",
                f"| Period Reward | ${rewards[i]:,.1f} |",
                f"| Cumulative Reward | ${cum_reward[i]:,.1f} |",
                "",
                f"> **{rationales[i]}**",
                "",
            ])

            if insights[i]:
                lines.append(f"💡 **New Insight:** {insights[i]}")
                lines.append("")

        # ===================================================================
        # Insight Evolution Timeline
        # ===================================================================
        if insight_count > 0:
            lines.extend([
                "---",
                "",
                "## Insight Evolution Timeline",
                "",
                "The LLM agent maintains **cross-period memory** via carry-over insights.",
                "New insights are generated when the agent detects sustained demand shifts or lead time anomalies.",
                "",
                "| Period | Insight |",
                "|--------|---------|",
            ])
            for i in range(n):
                if insights[i]:
                    lines.append(f"| {i+1} | {insights[i]} |")
            lines.append("")

        # ===================================================================
        # OR Baseline Stats Evolution
        # ===================================================================
        lines.extend([
            "---",
            "",
            "## OR Baseline Parameter Evolution",
            "",
            "How the OR algorithm's internal estimates changed as more demand data arrived:",
            "",
            "| P | $\\bar{d}$ | $s_d$ | $\\hat{\\mu}$ | $\\hat{\\sigma}$ | $z^*$ | $B$ | $q^{OR}$ |",
            "|---|----------|------|-----------|--------------|------|----|----|",
        ])

        for i, rec in enumerate(decision_history):
            o = rec.or_recommendation
            lines.append(
                f"| {i+1} | {o.demand_mean:.1f} | {o.demand_std:.1f} | {o.mu_hat:.1f} | {o.sigma_hat:.1f} | {o.z_star:.4f} | {o.base_stock_level:.1f} | **{o.recommended_order}** |"
            )

        lines.extend([
            "",
            "---",
            "",
            "*Report generated by OR→LLM Inventory Control Agent framework. Powered by DeepSeek Chat.*",
            "",
        ])

        md = "\n".join(lines)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(md)

        return self.output_path
