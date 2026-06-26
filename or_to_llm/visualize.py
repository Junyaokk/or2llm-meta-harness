"""
Interactive Plotly HTML dashboard for interview demo.
Generates a self-contained HTML file with architecture diagram, 4 charts + insights section.
"""

import json
import textwrap

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import List, Dict, Any


def _fig_to_json(fig) -> str:
    """Serialize figure WITHOUT the bloated plotly template (~8KB saved per figure)."""
    d = fig.to_dict()
    if "template" in d.get("layout", {}):
        del d["layout"]["template"]
    return json.dumps(d)


def _wrap_text(text: str, width: int = 60) -> str:
    """Wrap long text into multiple lines for display."""
    return "<br>".join(textwrap.wrap(text, width=width))


def _highlight_system_prompt(sp: str) -> str:
    """Add syntax-highlighting spans to the system prompt for HTML display."""
    import html as _html
    out = _html.escape(sp)
    # Bold headers (lines starting with **)
    lines = out.split("\n")
    result = []
    for line in lines:
        if line.startswith("**") and line.endswith("**"):
            result.append(f'<span class="sp-hl">{line}</span>')
        elif line.startswith(("1.", "2.", "3.", "4.", "5.")):
            result.append(f'<span class="sp-dim">{line}</span>')
        elif line.startswith("{"):
            result.append(f'<span class="sp-dim">{line}</span>')
        else:
            result.append(line)
    return "\n".join(result)


class DashboardBuilder:
    """Build an interactive Plotly HTML dashboard from run results."""

    def __init__(self, output_path: str = "dashboard.html"):
        self.output_path = output_path

    def build(
        self,
        period_log: List[Dict[str, Any]],
        decision_history: list,
        config: Dict[str, Any],
        total_reward: float,
        normalized_reward: float,
        instance_info: Dict[str, str] = None,
        system_prompt: str = "",
    ) -> str:
        n = len(period_log)
        periods = [e["period"] for e in period_log]
        demands = [e["demand"] for e in period_log]
        llm_orders = [e["ordered"] for e in period_log]
        solds = [e["sold"] for e in period_log]
        on_hand_after = [e["on_hand_after"] for e in period_log]
        on_hand_before = [e["on_hand_before"] for e in period_log]
        arriveds = [e["arrived"] for e in period_log]
        rewards = [e["reward"] for e in period_log]

        or_orders = []
        rationales = []
        carry_insights = []
        for rec in decision_history:
            or_orders.append(rec.or_recommendation.recommended_order)
            rationales.append(rec.agent_response.short_rationale_for_human)
            c = rec.agent_response.carry_over_insight
            carry_insights.append(c.strip() if (c and c.strip()) else None)

        cum_reward = []
        running = 0.0
        for r in rewards:
            running += r
            cum_reward.append(running)

        deltas = [llm - o for llm, o in zip(llm_orders, or_orders)]
        override_count = sum(1 for d in deltas if abs(d) > 0.5)
        stockout_count = sum(1 for inv in on_hand_after if inv == 0)
        insight_count = sum(1 for i in carry_insights if i)

        # ---- shared legend: below plot, never overlaps title ----
        legend_below = dict(
            orientation="h", y=-0.28, yanchor="top", x=0.5, xanchor="center",
            font=dict(size=11),
        )

        # ===================================================================
        # Chart 1: Decision Comparison
        # ===================================================================
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=periods, y=demands, name="Demand",
            marker_color="#778899", opacity=0.55,
            hovertemplate="P%{x}: Demand=%{y}<extra></extra>"
        ))
        fig1.add_trace(go.Bar(
            x=periods, y=solds, name="Sold",
            marker_color="mediumseagreen", opacity=0.75,
            hovertemplate="P%{x}: Sold=%{y}<extra></extra>"
        ))
        fig1.add_trace(go.Scatter(
            x=periods, y=llm_orders, name="LLM Order",
            mode="lines+markers", line=dict(color="#1f77b4", width=3),
            marker=dict(size=8),
            hovertemplate="P%{x}: LLM=%{y}<extra></extra>"
        ))
        fig1.add_trace(go.Scatter(
            x=periods, y=or_orders, name="OR Recommendation",
            mode="lines+markers", line=dict(color="darkorange", width=2, dash="dash"),
            marker=dict(size=6, symbol="diamond"),
            hovertemplate="P%{x}: OR=%{y}<extra></extra>"
        ))
        delta_colors = ["#1f77b4" if d >= 0 else "crimson" for d in deltas]
        fig1.add_trace(go.Bar(
            x=periods, y=deltas, name="Δ (LLM−OR)",
            marker_color=delta_colors, opacity=0.35, yaxis="y2",
            hovertemplate="P%{x}: Δ=%{y:+d}<extra></extra>"
        ))
        fig1.update_layout(
            title=dict(
                text=f"<b>Chart 1: Decision Comparison</b><br>"
                     f"<sub>LLM vs OR Baseline (overridden in {override_count}/{n} periods)</sub>",
                font=dict(size=15),
            ),
            xaxis=dict(title="Period", dtick=1),
            yaxis=dict(title="Order / Demand Quantity"),
            yaxis2=dict(title="Δ (LLM−OR)", overlaying="y", side="right", range=[-60, 60]),
            hovermode="x unified",
            legend=legend_below,
            barmode="overlay",
            margin=dict(t=70, b=60, l=55, r=55),
        )

        # ===================================================================
        # Chart 2: Inventory Water Level
        # ===================================================================
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=periods, y=on_hand_after, name="Ending Inventory",
            mode="lines+markers", fill="tozeroy", fillcolor="rgba(60,179,113,0.2)",
            line=dict(color="mediumseagreen", width=2.5), marker=dict(size=6),
            hovertemplate="P%{x}: EndInv=%{y}<extra></extra>"
        ))
        fig2.add_trace(go.Scatter(
            x=periods, y=arriveds, name="Arrived",
            mode="lines+markers", line=dict(color="steelblue", width=2), marker=dict(size=6),
            hovertemplate="P%{x}: Arrived=%{y}<extra></extra>"
        ))
        fig2.add_trace(go.Scatter(
            x=periods, y=on_hand_before, name="Starting Inventory",
            mode="lines", line=dict(color="darkseagreen", width=1.5, dash="dot"),
            hovertemplate="P%{x}: StartInv=%{y}<extra></extra>"
        ))
        fig2.add_trace(go.Bar(
            x=periods, y=demands, name="Demand",
            marker_color="lightcoral", opacity=0.4,
            hovertemplate="P%{x}: Demand=%{y}<extra></extra>"
        ))
        stockout_x = [periods[i] for i in range(n) if on_hand_after[i] == 0]
        if stockout_x:
            fig2.add_trace(go.Scatter(
                x=stockout_x, y=[0] * len(stockout_x), name="Stockout!",
                mode="markers", marker=dict(symbol="x", size=15, color="red", line=dict(width=2.5)),
                hovertemplate="P%{x}: STOCKOUT<extra></extra>"
            ))
        fig2.update_layout(
            title=dict(
                text=f"<b>Chart 2: Inventory Water Level</b><br>"
                     f"<sub>{stockout_count} stockout period(s)</sub>",
                font=dict(size=15),
            ),
            xaxis=dict(title="Period", dtick=1),
            yaxis=dict(title="Units"),
            hovermode="x unified",
            legend=legend_below,
            margin=dict(t=70, b=60, l=55, r=55),
        )

        # ===================================================================
        # Chart 3: Cumulative Reward + Period Reward
        # ===================================================================
        fig3 = make_subplots(specs=[[{"secondary_y": True}]])
        reward_colors = ["mediumseagreen" if r >= 0 else "crimson" for r in rewards]
        fig3.add_trace(go.Bar(
            x=periods, y=rewards, name="Period Reward",
            marker_color=reward_colors, opacity=0.35,
            hovertemplate="P%{x}: $%{y:.1f}<extra></extra>"
        ), secondary_y=True)
        fig3.add_trace(go.Scatter(
            x=periods, y=cum_reward, name="Cumulative Reward",
            mode="lines+markers", fill="tozeroy", fillcolor="rgba(31,119,180,0.1)",
            line=dict(color="#1f77b4", width=2.5), marker=dict(size=7),
            hovertemplate="P%{x}: Cum $%{y:.2f}<extra></extra>"
        ), secondary_y=False)
        for i in range(n):
            if on_hand_after[i] == 0:
                fig3.add_annotation(
                    x=periods[i], y=cum_reward[i],
                    text="⚠️0", showarrow=True, arrowhead=2, arrowsize=1,
                    arrowcolor="crimson", font=dict(size=10, color="crimson"), yshift=20,
                )
        fig3.update_layout(
            title=dict(
                text=f"<b>Chart 3: Cumulative Reward</b><br>"
                     f"<sub>Total ${total_reward:,.2f} | Normalized {normalized_reward:.4f}</sub>",
                font=dict(size=15),
            ),
            xaxis=dict(title="Period", dtick=1),
            yaxis=dict(title="Cumulative Reward ($)"),
            yaxis2=dict(title="Period Reward ($)", overlaying="y", side="right", showgrid=False),
            hovermode="x unified",
            legend=legend_below,
            margin=dict(t=70, b=60, l=55, r=55),
        )

        # ===================================================================
        # Chart 4: Order Timeline with rationale hover (insights as cards below)
        # ===================================================================
        fig4 = go.Figure()
        # LLM order trajectory
        fig4.add_trace(go.Scatter(
            x=periods, y=llm_orders, name="LLM Order",
            mode="lines+markers",
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=10, color="#1f77b4", opacity=0.7),
            hovertemplate=(
                "<b>P%{x}</b> | Order: %{y}<br>"
                + "%{customdata[0]}<extra></extra>"
            ),
            customdata=[[r] for r in rationales],
        ))
        # OR recommendation
        fig4.add_trace(go.Scatter(
            x=periods, y=or_orders, name="OR Recommendation",
            mode="lines+markers",
            line=dict(color="darkorange", width=1.5, dash="dash"),
            marker=dict(size=6, symbol="diamond", color="darkorange"),
            hovertemplate="P%{x}: OR=%{y}<extra></extra>"
        ))
        # Insight stars (just markers, text in cards below)
        insight_periods = []
        insight_labels = []
        for i, ins in enumerate(carry_insights):
            if ins:
                insight_periods.append(periods[i])
                insight_labels.append(f"P{periods[i]}")
        if insight_periods:
            fig4.add_trace(go.Scatter(
                x=insight_periods,
                y=[llm_orders[i - 1] for i in insight_periods],
                text=insight_labels,
                mode="markers+text",
                marker=dict(size=22, symbol="star", color="gold",
                            line=dict(color="darkorange", width=1.5)),
                textposition="top center",
                textfont=dict(size=10, color="#b8860b"),
                hovertemplate="P%{x}: 💡 Insight generated<extra></extra>",
                name="Insight (★)",
            ))
        fig4.update_layout(
            title=dict(
                text=f"<b>Chart 4: Order Timeline & Insight Markers</b><br>"
                     f"<sub>Hover blue dots for LLM reasoning. ★ = carry-over insight generated</sub>",
                font=dict(size=15),
            ),
            xaxis=dict(title="Period", dtick=1),
            yaxis=dict(title="Order Quantity"),
            hovermode="closest",
            legend=legend_below,
            margin=dict(t=70, b=60, l=55, r=55),
        )

        # ===================================================================
        # Metadata
        # ===================================================================
        inst = instance_info or {}
        pattern_desc = (
            config.get("description", "")
            or f"{inst.get('pattern', '')}/{inst.get('variant', '')}/{inst.get('instance', '')}"
        )
        L_val = config.get("lead_time", inst.get("lead_time", "?"))
        p_val = config.get("p", "?")
        h_val = config.get("h", "?")
        rho = (
            p_val / (p_val + h_val)
            if isinstance(p_val, (int, float)) and isinstance(h_val, (int, float))
            else 0
        )

        from scipy.stats import norm as _norm

        norm_z_star = _norm.ppf(rho) if 0 < rho < 1 else 0

        # ===================================================================
        # Insight cards HTML (replaces inline chart annotations)
        # ===================================================================
        insight_cards_html = ""
        if insight_count > 0:
            cards = []
            for i, ins in enumerate(carry_insights):
                if ins:
                    wrapped = _wrap_text(ins, width=55)
                    cards.append(
                        f'<div class="insight-card">'
                        f'<div class="insight-period">P{periods[i]}</div>'
                        f'<div class="insight-text">{wrapped}</div>'
                        f'</div>'
                    )
            insight_cards_html = (
                '<div class="section">\n'
                '<h2>Carry-Over Insights (Cross-Period Memory)</h2>\n'
                '<p style="font-size:12px;color:#888;margin-bottom:14px;">'
                "The LLM agent maintains cross-period memory. New insights are generated "
                "when sustained demand shifts or lead-time anomalies are detected. "
                "They feed into the next period&rsquo;s user message.</p>\n"
                '<div class="insight-grid">\n'
                + "\n".join(cards)
                + "\n</div>\n</div>"
            )
        else:
            insight_cards_html = (
                '<div class="section">\n'
                '<h2>Carry-Over Insights</h2>\n'
                '<p style="color:#999;">No carry-over insights were generated in this run.</p>\n'
                '</div>'
            )

        # ===================================================================
        # Per-period table rows
        # ===================================================================
        table_rows = ""
        for i in range(n):
            delta = llm_orders[i] - or_orders[i]
            delta_str = f"+{delta}" if delta > 0 else str(delta)
            row_class = ' class="stockout-row"' if on_hand_after[i] == 0 else ""
            so_mark = " ⚠️" if on_hand_after[i] == 0 else ""
            ins_mark = " 💡" if carry_insights[i] else ""
            table_rows += (
                f"<tr{row_class}>"
                f"<td>{periods[i]}</td><td>{demands[i]}</td><td><b>{llm_orders[i]}</b></td>"
                f"<td>{or_orders[i]}</td><td>{delta_str}</td><td>{solds[i]}</td>"
                f"<td>{on_hand_after[i]}{so_mark}</td><td>${rewards[i]:,.0f}</td>"
                f"<td>${cum_reward[i]:,.0f}</td><td>{ins_mark}</td>"
                f"</tr>\n"
            )

        # ===================================================================
        # Assemble HTML
        # ===================================================================
        system_prompt_html = _highlight_system_prompt(system_prompt) if system_prompt else "(system prompt not provided)"
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OR→LLM Agent Dashboard — {config.get('item_id', 'N/A')}</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<script>
window.MathJax = {{ tex: {{ inlineMath: [['$','$'], ['\\\\(','\\\\)']] }} }};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #333; line-height: 1.5; }}
.header {{ background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); color: #fff; padding: 28px 36px 18px; }}
.header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; letter-spacing: -0.3px; }}
.header .subtitle {{ font-size: 12px; color: #aab; }}
.kpis {{ display: flex; gap: 14px; margin-top: 14px; flex-wrap: wrap; }}
.kpi {{ background: rgba(255,255,255,0.07); border-radius: 10px; padding: 10px 16px; min-width: 80px; text-align: center; }}
.kpi .label {{ font-size: 10px; color: #8899aa; text-transform: uppercase; letter-spacing: 0.8px; }}
.kpi .value {{ font-size: 19px; font-weight: 700; color: #e8e8e8; margin-top: 2px; }}
.kpi .value.green {{ color: #4ecdc4; }}
.kpi .value.gold {{ color: #f0c040; }}
.kpi .value.red {{ color: #ff6b6b; }}
.kpi .unit {{ font-size: 11px; color: #99a; font-weight: 400; }}
.container {{ max-width: 1260px; margin: 0 auto; padding: 20px; }}
.section {{ background: #fff; border-radius: 12px; padding: 22px 26px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden; }}
.section h2 {{ font-size: 15px; margin-bottom: 12px; color: #1a1a2e; border-bottom: 2px solid #4ecdc4; padding-bottom: 6px; }}
.section h3 {{ font-size: 14px; margin: 10px 0 6px; color: #333; }}
.chart-box {{ width: 100%; }}
.row {{ display: flex; gap: 20px; }}
.row .section {{ flex: 1; min-width: 0; }}
@media (max-width: 960px) {{ .row {{ flex-direction: column; }} }}

/* Architecture flow diagram */
.arch-flow {{ margin: 0 auto; }}
.arch-flow .sysprompt-box {{ background: linear-gradient(135deg, #1a1a2e, #2a2a4e); color: #d0d0e0; border: 1px solid #4ecdc4; border-radius: 10px; padding: 14px 18px; margin-bottom: 12px; text-align: center; }}
.arch-flow .sysprompt-box .sp-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #4ecdc4; font-weight: 700; }}
.arch-flow .sysprompt-box .sp-desc {{ font-size: 12px; margin-top: 4px; color: #aab; }}
.arch-flow .arrow-down {{ text-align: center; font-size: 22px; color: #4ecdc4; margin: 2px 0 8px; }}
.arch-flow .steps-row {{ display: flex; align-items: stretch; gap: 0; justify-content: center; }}
.arch-flow .step-box {{ flex: 1; min-width: 120px; max-width: 220px; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.arch-flow .step-box .step-head {{ color: #fff; font-size: 12px; font-weight: 700; padding: 8px 10px; text-align: center; letter-spacing: -0.2px; }}
.arch-flow .step-box .step-body {{ background: #fafafa; padding: 10px 12px; font-size: 11px; line-height: 1.5; color: #555; }}
.arch-flow .step-box .step-body ul {{ margin: 0; padding-left: 14px; }}
.arch-flow .step-box .step-body li {{ margin-bottom: 2px; }}
.arch-flow .step-a .step-head {{ background: #3a7bd5; }}
.arch-flow .step-b .step-head {{ background: #5a4fcf; }}
.arch-flow .step-c .step-head {{ background: #c44d6e; }}
.arch-flow .step-d .step-head {{ background: #2ca02c; }}
.arch-flow .step-arrow {{ display: flex; align-items: center; justify-content: center; width: 36px; flex-shrink: 0; font-size: 20px; color: #999; font-weight: 700; }}
.arch-flow .feedback-row {{ display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 10px; font-size: 11px; color: #888; flex-wrap: wrap; }}
.arch-flow .feedback-row .fb-loop {{ background: #f0f0f0; border: 1px dashed #bbb; border-radius: 16px; padding: 6px 14px; white-space: nowrap; }}
.arch-flow .feedback-row .fb-arrow {{ color: #aaa; font-size: 14px; }}
@media (max-width: 800px) {{ .arch-flow .steps-row {{ flex-direction: column; align-items: center; }} .arch-flow .step-arrow {{ transform: rotate(90deg); }} .arch-flow .step-box {{ max-width: 100%; }} }}

/* System prompt display */
.sysprompt-display {{ background: #1e1e2e; color: #cdd6f4; font-family: 'SF Mono', 'Menlo', 'Monaco', 'Courier New', monospace; font-size: 11.5px; line-height: 1.55; padding: 16px 20px; border-radius: 10px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; max-height: 480px; overflow-y: auto; }}
.sysprompt-display .sp-hl {{ color: #89b4fa; font-weight: 700; }}
.sysprompt-display .sp-dim {{ color: #6c7086; }}
.sysprompt-display .sp-val {{ color: #a6e3a1; }}

/* Formula grid */
.formula-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px 24px; font-size: 14px; }}
.formula-grid .step {{ color: #666; font-size: 11px; font-weight: 600; }}
.formula-grid .eq {{ font-family: 'SF Mono', 'Menlo', 'Courier New', monospace; font-size: 13px; padding: 2px 0; }}
@media (max-width: 800px) {{ .formula-grid {{ grid-template-columns: 1fr; }} }}

/* Insight cards */
.insight-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }}
.insight-card {{ background: #fffdf0; border: 1px solid #e8d5a0; border-left: 3px solid #f0c040; border-radius: 8px; padding: 12px 14px; }}
.insight-period {{ font-size: 11px; font-weight: 700; color: #b8860b; margin-bottom: 4px; }}
.insight-text {{ font-size: 12px; line-height: 1.55; color: #555; }}

/* Period table */
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
thead tr {{ background: #f5f5f5; }}
th {{ padding: 8px 6px; text-align: right; font-weight: 600; border-bottom: 2px solid #ddd; }}
th:first-child, th:last-child {{ text-align: center; }}
td {{ padding: 6px; text-align: right; border-bottom: 1px solid #eee; }}
td:first-child, td:last-child {{ text-align: center; }}
.stockout-row {{ background: #fff5f5; }}

.footer {{ text-align: center; padding: 0 0 30px; font-size: 11px; color: #999; }}
</style>
</head>
<body>
<div class="header">
<h1>OR&rarr;LLM Inventory Control Agent</h1>
<div class="subtitle">{config.get('item_id', 'N/A')} &nbsp;|&nbsp; L={L_val} &nbsp;|&nbsp; p={p_val}, h={h_val} &nbsp;|&nbsp; &rho;={rho:.2f} &nbsp;|&nbsp; {pattern_desc[:80]}</div>
<div class="kpis">
<div class="kpi"><div class="label">Total Reward</div><div class="value green">${total_reward:,.2f}</div></div>
<div class="kpi"><div class="label">Normalized</div><div class="value gold">{normalized_reward:.4f}</div></div>
<div class="kpi"><div class="label">Periods</div><div class="value">{n}</div></div>
<div class="kpi"><div class="label">LLM Overrides</div><div class="value">{override_count}<span class="unit">/{n}</span></div></div>
<div class="kpi"><div class="label">Stockouts</div><div class="value red">{stockout_count}</div></div>
<div class="kpi"><div class="label">Insights</div><div class="value gold">{insight_count}</div></div>
</div>
</div>

<div class="container">

	<!-- ARCHITECTURE DIAGRAM -->
	<div class="section">
	<h2>Agent Architecture: Per-Period Decision Loop (A &rarr; B &rarr; C &rarr; D)</h2>
	<div class="arch-flow">

	<!-- System Prompt box feeding in -->
	<div class="sysprompt-box">
	<div class="sp-label">System Prompt (injected at t=0)</div>
	<div class="sp-desc">
	Role: inventory control agent collaborating with OR baseline &middot;
	OR algorithm: capped base-stock policy explained in full &middot;
	Output format: JSON &#123; rationale, action, carry_over_insight &#125;
	</div>
	</div>
	<div class="arrow-down">&#8595;</div>

	<!-- Step boxes A -> B -> C -> D -->
	<div class="steps-row">
	<div class="step-box step-a">
	<div class="step-head">Step A: OR Baseline</div>
	<div class="step-body">
	<ul>
	<li>d&#x304; = mean(history)</li>
	<li>s<sub>d</sub> = std(history)</li>
	<li>&mu;&#x302; = (1+L)&middot;d&#x304;</li>
	<li>&sigma;&#x302; = &radic;<span style="text-decoration:overline;">1+L</span>&middot;s<sub>d</sub></li>
	<li>B = &mu;&#x302; + z*&middot;&sigma;&#x302;</li>
	<li>q<sub>OR</sub> = max(0, min(B&minus;IP, cap))</li>
	</ul>
	</div>
	</div>
	<div class="step-arrow">&#9654;</div>
	<div class="step-box step-b">
	<div class="step-head">Step B: User Message</div>
	<div class="step-body">
	<ul>
	<li>&#9312; Carry-over insights</li>
	<li>&#9313; Current observation<br>(inv, pipeline, demand history, last-period conclude)</li>
	<li>&#9314; OR recommendation<br>(stats + q<sub>OR</sub>)</li>
	</ul>
	</div>
	</div>
	<div class="step-arrow">&#9654;</div>
	<div class="step-box step-c">
	<div class="step-head">Step C: LLM Inference</div>
	<div class="step-body">
	<ul>
	<li>DeepSeek Chat (temp=0)</li>
	<li>System Prompt + User Message &rarr; JSON response</li>
	<li>Parse: rationale, action, insight</li>
	<li>LLM may override q<sub>OR</sub></li>
	</ul>
	</div>
	</div>
	<div class="step-arrow">&#9654;</div>
	<div class="step-box step-d">
	<div class="step-head">Step D: State Transition</div>
	<div class="step-body">
	<ul>
	<li>D1. Place order q<sub>t</sub></li>
	<li>D2. Arrival resolution</li>
	<li>D3. Demand realization</li>
	<li>D4. Compute reward R<sub>t</sub></li>
	<li>D5. Build next observation</li>
	</ul>
	</div>
	</div>
	</div>

	<!-- Feedback loops -->
	<div class="feedback-row">
	<div class="fb-loop">&#x1F504; carry-over insights feed into next period&rsquo;s Step B</div>
	<span class="fb-arrow">&#8596;</span>
	<div class="fb-loop">&#x1F504; observation (on-hand, pipeline, demand) feeds into next period&rsquo;s Step A</div>
	</div>

	</div>
	</div>

	<!-- SYSTEM PROMPT -->
	<div class="section">
	<h2>System Prompt (Injected at t=0, Immutable Across Periods)</h2>
	<p style="font-size:12px;color:#888;margin-bottom:12px;">
	The complete system prompt sent to the LLM. Parameters in <span style="color:#a6e3a1;">green</span> are
	filled from instance config (p={p_val}, h={h_val}, L={L_val}, rho={rho:.4f}, z*={norm_z_star:.4f}).
	</p>
	<div class="sysprompt-display">{system_prompt_html}</div>
	</div>

<!-- ALGORITHM REFERENCE -->
<div class="section">
<h2>Capped Base-Stock Policy (OR Baseline Algorithm)</h2>
<div class="formula-grid">
<div>
<div class="step">Step 1 &mdash; Demand Estimation</div>
<div class="eq">$\\bar{{d}} = \\frac{{1}}{{n}}\\sum x_i$</div>
<div class="eq">$s_d = \\sqrt{{\\frac{{1}}{{n-1}}\\sum(x_i-\\bar{{d}})^2}}$</div>
</div>
<div>
<div class="step">Step 2 &mdash; Lead Time Projection</div>
<div class="eq">$\\hat{{\\mu}} = (1+L)\\cdot\\bar{{d}}$</div>
<div class="eq">$\\hat{{\\sigma}} = \\sqrt{{1+L}}\\cdot s_d$</div>
</div>
<div>
<div class="step">Step 3 &mdash; Safety Factor</div>
<div class="eq">$\\rho = \\frac{{p}}{{p+h}} = {rho:.4f}$</div>
<div class="eq">$z^* = \\Phi^{{-1}}(\\rho) = {norm_z_star:.4f}$</div>
</div>
<div>
<div class="step">Step 4 &mdash; Base Stock &amp; Capped Order</div>
<div class="eq">$B = \\hat{{\\mu}} + z^*\\cdot\\hat{{\\sigma}}$</div>
<div class="eq">$q_t = \\max(0,\\min(B-IP_t, cap))$</div>
</div>
</div>
<p style="margin-top:10px;font-size:12px;color:#888;">
LLM agent uses this as a <b>data-driven baseline</b> and overrides when detecting
demand regime shifts, lead time discrepancies, or seasonality.
&rho; = {rho:.4f} &rarr; optimal service level = {100*rho:.0f}%.
</p>
</div>

<!-- CHARTS ROW 1 -->
<div class="row">
<div class="section"><div class="chart-box" id="chart1"></div></div>
<div class="section"><div class="chart-box" id="chart2"></div></div>
</div>

<!-- CHART 3 -->
<div class="section"><div class="chart-box" id="chart3"></div></div>

<!-- CHART 4 -->
<div class="section"><div class="chart-box" id="chart4"></div></div>

<!-- INSIGHT CARDS (replaces overlapping chart annotations) -->
{insight_cards_html}

<!-- PERIOD TABLE -->
<div class="section">
<h2>Period-by-Period Summary</h2>
<table>
<thead><tr>
<th>P</th><th>Demand</th><th>LLM Order</th><th>OR Rec</th><th>&Delta;</th><th>Sold</th><th>End Inv</th><th>Reward</th><th>Cum</th><th></th>
</tr></thead>
<tbody>
{table_rows}
</tbody></table>
<p style="margin-top:8px;font-size:11px;color:#888;">
⚠️ = stockout &nbsp;|&nbsp; 💡 = carry-over insight &nbsp;|&nbsp; &Delta; = LLM &minus; OR
</p>
</div>

<div class="footer">
Hover chart markers for LLM reasoning &nbsp;|&nbsp;
OR&rarr;LLM Inventory Control Agent &nbsp;|&nbsp;
Powered by DeepSeek Chat
</div>
</div>

<script>
var fig1 = {_fig_to_json(fig1)};
var fig2 = {_fig_to_json(fig2)};
var fig3 = {_fig_to_json(fig3)};
var fig4 = {_fig_to_json(fig4)};
var cfg = {{responsive: true, displayModeBar: false}};
Plotly.newPlot('chart1', fig1.data, fig1.layout, cfg);
Plotly.newPlot('chart2', fig2.data, fig2.layout, cfg);
Plotly.newPlot('chart3', fig3.data, fig3.layout, cfg);
Plotly.newPlot('chart4', fig4.data, fig4.layout, cfg);
</script>
</body>
</html>"""

        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return self.output_path
