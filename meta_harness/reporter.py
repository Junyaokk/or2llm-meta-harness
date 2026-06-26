"""
HTML Reporter — generates a comprehensive, self-contained HTML report
of the full Meta-Harness optimization process.

Plan B (深 Trace): includes full rationale traces, decision tables,
score progression, and proposer context history.
"""
import difflib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from .trace_store import TraceStore
from collections import Counter


class HtmlReporter:
    """Generates a single self-contained HTML report."""

    def __init__(self, run_log: List[dict], trace_store: TraceStore,
                 start_time: datetime, config: dict, title: str = "H1 System Prompt Optimization",
                 baseline_id: str = "candidate_000"):
        self.run_log = run_log
        self.trace_store = trace_store
        self.start_time = start_time
        self.config = config
        self.title = title
        self.baseline_id = baseline_id

    def generate(self, output_path: Optional[Path] = None) -> Path:
        """Generate the full HTML report. Returns the output path."""
        if output_path is None:
            from .config import REPORT_DIR
            output_path = Path(REPORT_DIR) / "meta_harness_report.html"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html = self._build_html()
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def _build_html(self) -> str:
        """Assemble the complete HTML document."""
        sections = [
            self._render_head(),
            self._render_header(),
            self._render_executive_summary(),
            self._render_score_progression(),
            self._render_evolution_timeline(),
            self._render_candidate_cards(),
            self._render_instance_breakdown(),
            self._render_proposer_contexts(),
            self._render_footer(),
        ]
        body = "\n".join(sections)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
{body}
</html>"""

    # ====================================================================
    # CSS and Head
    # ====================================================================

    def _render_head(self) -> str:
        return f"""<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Meta-Harness Report — {self.title}</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --red: #f85149; --yellow: #d2991d;
    --purple: #a371f7; --orange: #f0883e;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
    background: var(--bg); color: var(--text); line-height: 1.5;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 1.8em; color: var(--accent); margin-bottom: 4px; }}
  h2 {{ font-size: 1.3em; color: var(--accent); margin: 32px 0 16px;
        border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
  h3 {{ font-size: 1.1em; color: var(--text); margin: 20px 0 10px; }}
  h4 {{ font-size: 0.95em; color: var(--muted); margin: 16px 0 8px; }}

  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 20px; margin-bottom: 16px;
  }}

  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
  .grid-5 {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }}

  .kpi-box {{ text-align: center; padding: 16px; }}
  .kpi-value {{ font-size: 2.2em; font-weight: 700; }}
  .kpi-label {{ font-size: 0.8em; color: var(--muted); margin-top: 4px; }}
  .kpi-sub  {{ font-size: 0.75em; margin-top: 2px; }}

  .text-green {{ color: var(--green); }}
  .text-red {{ color: var(--red); }}
  .text-yellow {{ color: var(--yellow); }}
  .text-purple {{ color: var(--purple); }}
  .text-muted {{ color: var(--muted); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; }}
  th {{ background: var(--border); color: var(--text); padding: 8px 10px;
        text-align: left; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid var(--border);
        vertical-align: top; }}
  tr:hover {{ background: rgba(88,166,255,0.05); }}

  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 0.75em; font-weight: 600;
  }}
  .badge-best {{ background: rgba(63,185,80,0.2); color: var(--green); }}
  .badge-baseline {{ background: rgba(139,148,158,0.2); color: var(--muted); }}
  .badge-improved {{ background: rgba(88,166,255,0.2); color: var(--accent); }}
  .badge-worse {{ background: rgba(248,81,73,0.2); color: var(--red); }}

  .bar-container {{ height: 8px; background: var(--border); border-radius: 4px;
                    overflow: hidden; margin: 4px 0; }}
  .bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}

  .rationale-box {{
    background: #0d1117; border: 1px solid var(--border); border-radius: 4px;
    padding: 12px; font-size: 0.82em; max-height: 300px; overflow-y: auto;
    white-space: pre-wrap; word-break: break-word; margin: 8px 0;
    font-family: 'SF Mono', 'Fira Code', monospace; line-height: 1.4;
  }}

  .sparkline {{ display: flex; align-items: flex-end; gap: 4px; height: 60px; }}
  .sparkline-bar {{
    flex: 1; background: var(--accent); border-radius: 2px 2px 0 0;
    min-height: 2px; transition: height 0.3s; position: relative;
  }}
  .sparkline-bar.baseline {{ background: var(--muted); }}
  .sparkline-bar.best {{ background: var(--green); }}

  .diff-arrow {{ font-size: 1.2em; }}

  .collapsible {{ cursor: pointer; user-select: none; }}
  .collapsible::before {{ content: '▸ '; display: inline-block; transition: 0.2s; }}
  .collapsible.open::before {{ content: '▾ '; }}
  .collapsible-content {{ display: none; }}
  .collapsible-content.open {{ display: block; }}

  .proposer-ctx {{
    background: #0d1117; border: 1px solid var(--border); border-radius: 4px;
    padding: 16px; font-size: 0.78em; max-height: 500px; overflow-y: auto;
    white-space: pre-wrap; word-break: break-word;
    font-family: 'SF Mono', 'Fira Code', monospace; line-height: 1.3;
  }}

  .timeline {{ position: relative; padding-left: 24px; }}
  .timeline::before {{
    content: ''; position: absolute; left: 8px; top: 0; bottom: 0;
    width: 2px; background: var(--border);
  }}
  .timeline-item {{ position: relative; margin-bottom: 16px; }}
  .timeline-item::before {{
    content: ''; position: absolute; left: -20px; top: 6px;
    width: 10px; height: 10px; border-radius: 50%; background: var(--accent);
  }}

  .tag {{
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-size: 0.7em; font-weight: 600; margin-right: 4px;
  }}
  .tag-L0 {{ background: rgba(88,166,255,0.15); color: var(--accent); }}
  .tag-L4 {{ background: rgba(163,113,247,0.15); color: var(--purple); }}
  .tag-rho {{ background: rgba(210,153,29,0.15); color: var(--yellow); }}

  @media (max-width: 900px) {{
    .grid-2, .grid-3, .grid-5 {{ grid-template-columns: 1fr; }}
    body {{ padding: 12px; }}
  }}
</style>
</head>"""

    # ====================================================================
    # Header
    # ====================================================================

    def _render_header(self) -> str:
        duration = (datetime.now() - self.start_time).total_seconds()
        mins = int(duration // 60)
        secs = int(duration % 60)
        return f"""<body>
<h1>Meta-Harness Report</h1>
<div class="text-muted" style="margin-bottom:24px;">
  {self.title} · Plan B (深 Trace) · {self.start_time.strftime('%Y-%m-%d %H:%M')}
  · Duration: {mins}m{secs}s
  · {len(self.run_log)} candidates · {self.config['n_instances']} instances · {self.config['n_periods']} periods/instance
</div>"""

    # ====================================================================
    # Executive Summary
    # ====================================================================

    def _render_executive_summary(self) -> str:
        all_scores = self.trace_store.get_all_scores()
        if not all_scores:
            return "<div class='card'><p>No results yet.</p></div>"

        best = all_scores[0]
        baseline = next((s for s in all_scores if s["candidate_id"] == self.baseline_id), None)
        delta = 0.0
        delta_pct = 0.0
        improved = False
        if baseline and best["candidate_id"] != self.baseline_id:
            delta = best["mean_nr"] - baseline["mean_nr"]
            delta_pct = delta / baseline["mean_nr"] * 100 if baseline["mean_nr"] > 0 else 0
            improved = delta > 0

        n_better_than_baseline = sum(
            1 for s in all_scores
            if baseline and s["mean_nr"] > baseline["mean_nr"]
        )

        delta_color = "text-green" if improved else "text-red"
        delta_sign = "+" if delta >= 0 else ""

        return f"""<h2>📊 Executive Summary</h2>
<div class="card">
  <div class="grid-3">
    <div class="kpi-box">
      <div class="kpi-value text-green">{best['mean_nr']:.4f}</div>
      <div class="kpi-label">Best Candidate NR</div>
      <div class="kpi-sub text-muted">{best['candidate_id']}</div>
    </div>
    <div class="kpi-box">
      <div class="kpi-value {delta_color}">{delta_sign}{delta:.4f}</div>
      <div class="kpi-label">Delta vs Baseline</div>
      <div class="kpi-sub {delta_color}">{delta_sign}{delta_pct:.1f}%</div>
    </div>
    <div class="kpi-box">
      <div class="kpi-value text-purple">{n_better_than_baseline}/{len(all_scores)-1}</div>
      <div class="kpi-label">Candidates Improving on Baseline</div>
      <div class="kpi-sub text-muted">Excluding baseline itself</div>
    </div>
  </div>
</div>"""

    # ====================================================================
    # Score Progression (SVG Sparkline)
    # ====================================================================

    @staticmethod
    def _get_chronological_scores(all_scores):
        """Sort scores by candidate_id number, not by NR."""
        return sorted(all_scores, key=lambda s: int(s["candidate_id"].rsplit("_", 1)[-1]))

    def _get_baseline_nr(self, all_scores):
        """Get the NR of the baseline candidate."""
        b = next((s for s in all_scores if s["candidate_id"] == self.baseline_id), None)
        if not b:
            # Fallback: first chronological candidate
            chronological = self._get_chronological_scores(all_scores)
            b = chronological[0] if chronological else None
        return b["mean_nr"] if b else 0.0

    def _render_score_progression(self) -> str:
        all_scores = self.trace_store.get_all_scores()
        if not all_scores:
            return ""

        chronological = self._get_chronological_scores(all_scores)
        nrs = [s["mean_nr"] for s in chronological]
        labels = [s["candidate_id"] for s in chronological]
        min_nr, max_nr = min(nrs), max(nrs)
        nr_range = max_nr - min_nr or 0.01

        baseline_nr = self._get_baseline_nr(all_scores)

        bars = []
        for i, (nr, label) in enumerate(zip(nrs, labels)):
            height_pct = (nr - min_nr) / nr_range * 100 + 10
            css_class = "sparkline-bar"
            if label == self.baseline_id:
                css_class += " baseline"
            elif nr == max_nr:
                css_class += " best"
            bars.append(
                f'<div class="{css_class}" style="height:{height_pct:.0f}%" '
                f'title="{label}: {nr:.4f}"></div>'
            )

        sparkline = "\n".join(bars)

        # Table below
        rows = []
        for s in chronological:
            delta = s["mean_nr"] - baseline_nr
            d_sign = "+" if delta >= 0 else ""
            d_color = "text-green" if delta >= 0 else "text-red"
            badge = ""
            if s["candidate_id"] == self.baseline_id:
                badge = '<span class="badge badge-baseline">BASELINE</span>'
            elif s["mean_nr"] == max_nr:
                badge = '<span class="badge badge-best">BEST</span>'

            per_inst = "<br>".join(
                f"{k}: {v:.4f}" for k, v in s["per_instance_nr"].items()
            )
            rows.append(f"""<tr>
              <td>{badge} {s['candidate_id']}</td>
              <td><strong>{s['mean_nr']:.4f}</strong></td>
              <td class="{d_color}">{d_sign}{delta:.4f}</td>
              <td class="text-muted" style="font-size:0.8em;">{per_inst}</td>
            </tr>""")

        return f"""<h2>📈 Score Progression</h2>
<div class="card">
  <div class="sparkline" style="margin-bottom:16px;">
    {sparkline}
  </div>
  <table>
    <thead><tr>
      <th>Candidate</th><th>Mean NR</th><th>Δ Baseline</th><th>Per Instance</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""

    # ====================================================================
    # Candidate Cards
    # ====================================================================

    def _render_candidate_cards(self) -> str:
        all_scores = self.trace_store.get_all_scores()
        if not all_scores:
            return ""

        chronological = self._get_chronological_scores(all_scores)
        baseline_nr = self._get_baseline_nr(all_scores)
        baseline_prompt = self._load_candidate_prompt(self.baseline_id)
        baseline_text = self._extract_prompt_text(baseline_prompt)
        baseline_config = self._load_analyst_config(self.baseline_id)
        best_score = all_scores[0]  # highest NR

        cards = []
        for i, s in enumerate(chronological):
            cid = s["candidate_id"]

            prompt_text = self._load_candidate_prompt(cid)
            prompt_body = self._extract_prompt_text(prompt_text)

            inst_details = self._render_instance_mini_table(cid)

            # Diff from baseline (skip for baseline itself)
            diff_html = ""
            if cid != self.baseline_id and baseline_text and prompt_body:
                diff_html = self._render_diff(baseline_text, prompt_body, cid)

            # Evolution info: what changed from previous candidate
            evo_html = ""
            if i > 0:
                prev_cid = chronological[i-1]["candidate_id"]
                prev_nr = chronological[i-1]["mean_nr"]
                curr_nr = s["mean_nr"]
                delta = curr_nr - prev_nr
                evo_html = self._render_evolution_step(prev_cid, cid, delta)

            # Header comment from the prompt file
            header_comment = self._extract_header_comment(prompt_text)

            # H2: analyst config
            config_html = ""
            config_text = self._load_analyst_config(cid)
            if config_text:
                config_body = config_text
                config_diff_html = ""
                if cid != self.baseline_id and baseline_config:
                    config_diff_html = self._render_diff(baseline_config, config_text, f"{cid}_config")
                config_html = f"""<h4>Analyst Config <span class="text-muted" style="font-size:0.75em;">({len(config_text)} chars)</span></h4>
    {config_diff_html}"""

            # H2X: memory config + reviewer prompt
            h2x_html = ""
            memory_text = self._load_memory_config(cid)
            reviewer_text = self._load_reviewer_prompt(cid)
            baseline_memory = self._load_memory_config(self.baseline_id)
            baseline_reviewer = self._load_reviewer_prompt(self.baseline_id)

            if memory_text:
                mem_diff = ""
                if cid != self.baseline_id and baseline_memory:
                    mem_diff = self._render_single_value_diff("MEMORY_WINDOW", baseline_memory, memory_text, cid)
                h2x_html += f"""<h4>Memory Config</h4>
    <div class="rationale-box" style="font-size:0.82em;">{self._escape_html(memory_text.strip())}</div>
    {mem_diff}"""

            if reviewer_text:
                reviewer_body = self._extract_prompt_text(reviewer_text)
                rev_diff = ""
                if cid != self.baseline_id and baseline_reviewer:
                    baseline_body = self._extract_prompt_text(baseline_reviewer)
                    rev_diff = self._render_diff(baseline_body, reviewer_body, f"{cid}_reviewer")
                h2x_html += f"""<h4>Reviewer Prompt <span class="text-muted" style="font-size:0.75em;">({len(reviewer_body)} chars)</span></h4>
    {rev_diff}"""

            delta_baseline = s["mean_nr"] - baseline_nr
            d_sign = "+" if delta_baseline >= 0 else ""
            d_color = "text-green" if delta_baseline >= 0 else "text-red"

            prompt_label = "Decider Prompt" if config_text else "System Prompt"

            cards.append(f"""<div class="card">
  <h3>
    <span class="collapsible" onclick="toggleCollapsible(this)">{cid}</span>
    <span class="badge {'badge-best' if s == best_score else ('badge-baseline' if cid == self.baseline_id else 'badge-improved')}">
      NR={s['mean_nr']:.4f} <span class="{d_color}">({d_sign}{delta_baseline:.4f} vs {self.baseline_id})</span>
    </span>
  </h3>
  <div class="collapsible-content">
    {evo_html}
    {inst_details}
    {header_comment}
    {config_html}
    {h2x_html}
    <h4>{prompt_label} <span class="text-muted" style="font-size:0.75em;">({len(prompt_body)} chars)</span></h4>
    {diff_html}
  </div>
</div>""")

        return f"""<h2>Candidate Details</h2>
<script>
function toggleCollapsible(el) {{
  el.classList.toggle('open');
  el.parentElement.nextElementSibling.classList.toggle('open');
}}
function toggleDiff(id) {{
  var el = document.getElementById(id);
  if (el.style.display === 'none' || el.style.display === '') {{ el.style.display = 'block'; }}
  else {{ el.style.display = 'none'; }}
}}
</script>
{''.join(cards)}"""

    @staticmethod
    def _extract_prompt_text(file_content: str) -> str:
        """Extract just the SYSTEM_PROMPT string body from a candidate file."""
        # Find the SYSTEM_PROMPT = """...""" block
        match = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', file_content, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Try triple single quotes
        match = re.search(r"SYSTEM_PROMPT\s*=\s*'''(.*?)'''", file_content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return file_content

    @staticmethod
    def _extract_header_comment(file_content: str) -> str:
        """Extract the docstring/header comment from a candidate file."""
        match = re.search(r'"""(.*?)"""', file_content, re.DOTALL)
        if match:
            comment = match.group(1).strip()
            # Skip if it's the prompt itself (not file header)
            if 'SYSTEM_PROMPT' in comment[:100]:
                return ""
            return f"""<h4>Design Notes</h4>
    <div class="rationale-box" style="color:var(--yellow);">{HtmlReporter._escape_html(comment)}</div>"""
        return ""

    def _render_diff(self, baseline: str, candidate: str, cid: str) -> str:
        """Generate a side-by-side or unified diff between baseline and candidate prompt."""
        # Split into lines for diff
        base_lines = baseline.splitlines()
        cand_lines = candidate.splitlines()

        diff_id = f"diff_{cid}"
        toggle_id = f"toggle_{cid}"

        # Use unified diff
        differ = difflib.unified_diff(
            base_lines, cand_lines,
            fromfile=f'baseline ({self.baseline_id})', tofile=cid,
            lineterm=''
        )

        diff_lines = list(differ)
        if not diff_lines:
            return f'<p class="text-muted">No significant changes from baseline.</p>'

        # Render with syntax highlighting
        rendered = []
        line_count = 0
        for line in diff_lines:
            line_count += 1
            if line_count > 500:
                rendered.append('<div class="text-muted">... (truncated, showing first 500 lines)</div>')
                break
            escaped = self._escape_html(line)
            if line.startswith('@@'):
                rendered.append(f'<div style="color:var(--accent);font-weight:bold;margin-top:8px;">{escaped}</div>')
            elif line.startswith('+'):
                rendered.append(f'<div style="background:rgba(63,185,80,0.15);color:var(--green);padding:1px 4px;"><span style="color:var(--green);">+</span>{escaped[1:]}</div>')
            elif line.startswith('-'):
                rendered.append(f'<div style="background:rgba(248,81,73,0.15);color:var(--red);padding:1px 4px;"><span style="color:var(--red);">-</span>{escaped[1:]}</div>')
            elif line.startswith('---') or line.startswith('+++'):
                rendered.append(f'<div style="color:var(--muted);font-style:italic;">{escaped}</div>')

        # Stats
        additions = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
        deletions = sum(1 for l in diff_lines if l.startswith('-') and not l.startswith('---'))
        total_changes = additions + deletions

        return f"""<div style="margin-bottom:12px;">
  <span class="collapsible" onclick="toggleDiff('{diff_id}')" style="font-size:0.85em;">
    Diff vs Baseline: <span style="color:var(--green);">+{additions}</span> <span style="color:var(--red);">-{deletions}</span> lines ({total_changes} total changes)
  </span>
  <div id="{diff_id}" style="display:none; margin-top:8px; font-family:'SF Mono','Fira Code',monospace; font-size:0.78em; max-height:600px; overflow-y:auto; background:#0d1117; border:1px solid var(--border); border-radius:4px; padding:8px; line-height:1.4;">
    {''.join(rendered)}
  </div>
</div>"""

    @staticmethod
    def _render_evolution_step(prev_cid: str, curr_cid: str, delta_nr: float) -> str:
        """Show how this candidate evolved from the previous one."""
        d_color = "text-green" if delta_nr > 0 else "text-red"
        d_sign = "+" if delta_nr > 0 else ""
        arrow = "↑" if delta_nr > 0 else "↓"
        return f"""<div style="margin-bottom:8px; padding:6px 10px; background:rgba(88,166,255,0.08); border-left:3px solid var(--accent); border-radius:4px; font-size:0.85em;">
  <strong>Evolution:</strong> {prev_cid} → {curr_cid} · NR {d_sign}{delta_nr:.4f} <span class="{d_color}">{arrow}</span>
</div>"""

    def _render_evolution_timeline(self) -> str:
        """Render the full candidate evolution timeline as a new section."""
        all_scores = self.trace_store.get_all_scores()
        if not all_scores:
            return ""

        chronological = self._get_chronological_scores(all_scores)
        baseline_nr = self._get_baseline_nr(all_scores)
        best_score = all_scores[0]
        if len(chronological) < 2:
            return ""

        items = []
        for i, s in enumerate(chronological):
            cid = s["candidate_id"]
            nr = s["mean_nr"]
            prompt_text = self._load_candidate_prompt(cid)
            header = self._extract_header_comment(prompt_text)

            # Get the "changes" line from header
            changes_summary = ""
            for line in header.split("\n"):
                line = line.strip()
                if line.lower().startswith("changes from") or line.lower().startswith("hypothesis"):
                    changes_summary = line[:200]
                    break

            # Compute delta from previous candidate (by ID order, not NR order)
            delta_str = ""
            if i > 0:
                prev_nr = chronological[i-1]["mean_nr"]
                delta = nr - prev_nr
                d_color = "#3fb950" if delta > 0 else "#f85149"
                d_sign = "+" if delta > 0 else ""
                delta_str = f'<span style="font-size:0.8em; margin-left:8px;">vs prev: </span><span style="color:{d_color};">{d_sign}{delta:.4f}</span>'

            # Baseline delta: always vs candidate_000
            base_delta = nr - baseline_nr
            base_color = "#3fb950" if base_delta > 0 else "#f85149"
            base_sign = "+" if base_delta > 0 else ""

            best_badge = ' <span class="badge badge-best">BEST</span>' if s == best_score else ''
            base_badge = ' <span class="badge badge-baseline">BASELINE</span>' if cid == self.baseline_id else ''

            items.append(f"""<div class="timeline-item">
  <div style="display:flex; align-items:baseline; gap:8px;">
    <strong>{cid}</strong>{best_badge}{base_badge}
    <span style="font-size:1.1em; font-weight:700;">NR={nr:.4f}</span>
    {delta_str}
    <span class="text-muted" style="font-size:0.78em;">vs {self.baseline_id}: <span style="color:{base_color};">{base_sign}{base_delta:.4f} ({base_sign}{base_delta/baseline_nr*100:.1f}%)</span></span>
  </div>
  <div class="text-muted" style="font-size:0.82em; margin-top:4px;">{self._escape_html(changes_summary)}</div>
</div>""")

        return f"""<h2>Evolution Timeline</h2>
<div class="card">
  <div class="timeline">
    {''.join(items)}
  </div>
</div>"""

        return f"""<h2>Evolution Timeline</h2>
<div class="card">
  <div class="timeline">
    {''.join(items)}
  </div>
</div>"""

    def _render_instance_mini_table(self, candidate_id: str) -> str:
        """Mini per-instance score table with deviation count. Shows H2/H2X fields when available."""
        scores = self.trace_store.load_scores(candidate_id)
        if not scores:
            return ""

        rows = []
        is_h2x = False
        is_h2 = False
        for label, nr in scores["per_instance_nr"].items():
            trace = self.trace_store.load_instance_trace(candidate_id, label)
            n_deviations = 0
            pipe_summary = ""
            trend_summary = ""
            trust_summary = ""
            n_reviewed = 0
            n_overridden = 0
            if trace:
                n_deviations = sum(
                    1 for p in trace["periods"]
                    if p["ordered"] != p["or_recommended"]
                )
                # H2X fields
                if trace["periods"] and "draft_order" in trace["periods"][0]:
                    is_h2x = True
                    n_reviewed = sum(1 for p in trace["periods"] if not p.get("approved", True))
                    n_overridden = sum(1 for p in trace["periods"]
                                       if p.get("draft_order", p["ordered"]) != p["ordered"])
                # H2 fields
                if trace["periods"] and "pipe_status" in trace["periods"][0]:
                    is_h2 = True
                    pipes = Counter(p.get("pipe_status", "") for p in trace["periods"])
                    trends = Counter(p.get("trend_dir", "") for p in trace["periods"])
                    trusts = Counter(p.get("or_trust", "") for p in trace["periods"])
                    pipe_summary = pipes.most_common(1)[0][0] if pipes else ""
                    trend_summary = trends.most_common(1)[0][0] if trends else ""
                    trust_summary = trusts.most_common(1)[0][0] if trusts else ""

            if is_h2x:
                rows.append(f"""<tr>
              <td>{label}</td>
              <td><strong>{nr:.4f}</strong></td>
              <td class="text-muted">{n_deviations}</td>
              <td><span class="tag tag-L4">{pipe_summary}</span></td>
              <td><span class="tag tag-L0">{trend_summary}</span></td>
              <td><span class="tag tag-rho">{trust_summary}</span></td>
              <td class="text-muted">{n_reviewed} rejected / {n_overridden} adjusted</td>
            </tr>""")
            elif is_h2:
                rows.append(f"""<tr>
              <td>{label}</td>
              <td><strong>{nr:.4f}</strong></td>
              <td class="text-muted">{n_deviations}</td>
              <td><span class="tag tag-L4">{pipe_summary}</span></td>
              <td><span class="tag tag-L0">{trend_summary}</span></td>
              <td><span class="tag tag-rho">{trust_summary}</span></td>
            </tr>""")
            else:
                rows.append(f"""<tr>
              <td>{label}</td>
              <td><strong>{nr:.4f}</strong></td>
              <td class="text-muted">{n_deviations} deviations from OR</td>
            </tr>""")

        if is_h2x:
            header = """<thead><tr>
              <th>Instance</th><th>NR</th><th>Overrides</th><th>Pipeline</th><th>Trend</th><th>OR Trust</th><th>Reviewer</th>
            </tr></thead>"""
        elif is_h2:
            header = """<thead><tr>
              <th>Instance</th><th>NR</th><th>Overrides</th><th>Pipeline</th><th>Trend</th><th>OR Trust</th>
            </tr></thead>"""
        else:
            header = """<thead><tr><th>Instance</th><th>NR</th><th>LLM Override Behavior</th></tr></thead>"""

        return f"""<table style="margin-bottom:12px;">
  {header}
  <tbody>{''.join(rows)}</tbody>
</table>"""

    # ====================================================================
    # Instance Breakdown (deepest section — full per-period traces)
    # ====================================================================

    def _render_instance_breakdown(self) -> str:
        """Full per-period decision traces for every (candidate, instance) pair."""
        all_scores = self.trace_store.get_all_scores()
        if not all_scores:
            return ""

        # For each instance, show all candidates side by side
        instance_labels = [h["label"] for h in self._get_holdout_configs()]

        sections = []
        for label in instance_labels:
            sections.append(f"<h3>📋 Instance: {label}</h3>")

            # Per-candidate summary row
            summary_rows = []
            for s in all_scores:
                cid = s["candidate_id"]
                nr = s["per_instance_nr"].get(label, 0)
                trace = self.trace_store.load_instance_trace(cid, label)
                n_dev = 0
                if trace:
                    n_dev = sum(1 for p in trace["periods"]
                               if p["ordered"] != p["or_recommended"])
                summary_rows.append(f"""<tr>
                  <td>{cid}</td>
                  <td><strong>{nr:.4f}</strong></td>
                  <td class="text-muted">{n_dev} overrides</td>
                </tr>""")

            summary_table = f"""<table style="margin-bottom:16px;">
  <thead><tr><th>Candidate</th><th>NR</th><th>OR Overrides</th></tr></thead>
  <tbody>{''.join(summary_rows)}</tbody>
</table>"""

            # Best candidate's full trace for this instance
            best_id = all_scores[0]["candidate_id"]
            best_trace = self.trace_store.load_instance_trace(best_id, label)

            if best_trace:
                trace_table = self._render_period_trace_table(best_trace, best_id)
            else:
                trace_table = "<p class='text-muted'>No trace data.</p>"

            sections.append(f"""<div class="card">
  {summary_table}
  <h4>Best Candidate ({best_id}) — Full Decision Trace</h4>
  {trace_table}
</div>""")

        return f"""<h2>📋 Per-Instance Breakdown</h2>
{''.join(sections)}"""

    def _render_period_trace_table(self, trace: dict, candidate_id: str) -> str:
        """Full per-period table with rationale excerpts. Shows H2X Reviewer columns when available."""
        is_h2x = trace["periods"] and "draft_order" in trace["periods"][0] if trace["periods"] else False

        rows = []
        for p in trace["periods"]:
            deviated = p["ordered"] != p["or_recommended"]
            row_style = 'style="background:rgba(240,136,62,0.08);"' if deviated else ""
            rationale_preview = p["llm_rationale"][:120].replace("\n", " ")
            if len(p["llm_rationale"]) > 120:
                rationale_preview += "..."

            rationale_full = self._escape_html(p["llm_rationale"])
            period_id = f"{candidate_id}_{trace['instance_label']}_p{p['period']}"

            if is_h2x:
                draft = p.get("draft_order", p["ordered"])
                adjusted = draft != p["ordered"]
                risk_flag = p.get("risk_flag", "")
                rf_color = {"safe": "var(--green)", "caution": "var(--yellow)",
                            "override": "var(--red)"}.get(risk_flag, "var(--muted)")
                review_preview = p.get("reviewer_rationale", "")[:80].replace("\n", " ")
                review_full = self._escape_html(p.get("reviewer_rationale", ""))
                review_id = f"{period_id}_review"

                draft_cell = f'<td class="text-muted">{draft}</td>'
                if adjusted:
                    draft_cell = f'<td style="color:var(--yellow);">{draft} → <strong>{p["ordered"]}</strong></td>'
                else:
                    draft_cell = f'<td class="text-muted">{draft}</td>'

                rows.append(f"""<tr {row_style}>
  <td>{p['period']}</td>
  <td>{p['demand']}</td>
  {draft_cell}
  <td class="text-muted">{p['or_recommended']}</td>
  <td>{p['sold']}</td>
  <td>{p['reward']:.1f}</td>
  <td><span style="color:{rf_color}; font-weight:600;">{risk_flag}</span></td>
  <td>
    <span class="collapsible" onclick="toggleFullRationale('{period_id}')"
          style="font-size:0.8em;">{self._escape_html(rationale_preview)}</span>
    <div id="{period_id}" class="rationale-box" style="display:none; margin-top:4px;">{rationale_full}</div>
  </td>
  <td>
    <span class="collapsible" onclick="toggleFullRationale('{review_id}')"
          style="font-size:0.8em; color:var(--muted);">{self._escape_html(review_preview)}</span>
    <div id="{review_id}" class="rationale-box" style="display:none; margin-top:4px;">{review_full}</div>
  </td>
</tr>""")
            else:
                rows.append(f"""<tr {row_style}>
  <td>{p['period']}</td>
  <td>{p['demand']}</td>
  <td><strong>{p['ordered']}</strong></td>
  <td class="text-muted">{p['or_recommended']}</td>
  <td>{p['sold']}</td>
  <td>{p['reward']:.1f}</td>
  <td>
    <span class="collapsible" onclick="toggleFullRationale('{period_id}')"
          style="font-size:0.85em;">{self._escape_html(rationale_preview)}</span>
    <div id="{period_id}" class="rationale-box" style="display:none; margin-top:4px;">{rationale_full}</div>
  </td>
</tr>""")

        if is_h2x:
            header = """<thead><tr>
    <th>P</th><th>Demand</th><th>Draft→Final</th><th>OR Rec</th><th>Sold</th><th>Reward</th>
    <th>Risk</th><th style="min-width:200px;">Decider Rationale</th><th style="min-width:180px;">Reviewer Rationale</th>
  </tr></thead>"""
        else:
            header = """<thead><tr>
    <th>P</th><th>Demand</th><th>Order</th><th>OR Rec</th><th>Sold</th><th>Reward</th>
    <th style="min-width:300px;">LLM Rationale</th>
  </tr></thead>"""

        return f"""<script>
function toggleFullRationale(id) {{
  var el = document.getElementById(id);
  if (el.style.display === 'none') el.style.display = 'block';
  else el.style.display = 'none';
}}
</script>
<div style="max-height:600px; overflow-y:auto;">
<table>
  {header}
  <tbody>{''.join(rows)}</tbody>
</table>
</div>"""

    # ====================================================================
    # Proposer Contexts
    # ====================================================================

    def _render_proposer_contexts(self) -> str:
        """Show what the proposer saw at each iteration."""
        ctx_dir = self.trace_store.store_dir
        contexts = sorted(ctx_dir.glob("proposer_context_iter*.txt"))
        if not contexts:
            return ""

        sections = []
        for ctx_path in contexts:
            iter_num = ctx_path.stem.replace("proposer_context_iter", "")
            content = ctx_path.read_text()[:5000]
            if len(ctx_path.read_text()) > 5000:
                content += "\n\n... [truncated]"

            sections.append(f"""<div class="card">
  <h3 class="collapsible" onclick="toggleCollapsible(this)">
    Iteration {iter_num} — Proposer Context
  </h3>
  <div class="collapsible-content">
    <div class="proposer-ctx">{self._escape_html(content)}</div>
  </div>
</div>""")

        return f"""<h2>🧠 Proposer Context History</h2>
{''.join(sections)}"""

    # ====================================================================
    # Footer
    # ====================================================================

    def _render_footer(self) -> str:
        return f"""<div style="text-align:center; margin-top:48px; padding:24px;
  border-top:1px solid var(--border); color: var(--muted); font-size:0.8em;">
  Meta-Harness Report · Plan B (深 Trace) · Generated {datetime.now().isoformat()}
  · <a href="https://arxiv.org/abs/2603.28052" style="color:var(--accent);">
    arXiv:2603.28052</a>
</div>
</body>"""

    # ====================================================================
    # Helpers
    # ====================================================================

    def _load_candidate_prompt(self, candidate_id: str) -> str:
        """Load the prompt content for a candidate. Handles H1 (system_prompt.py) and H2 (decider_prompt.py)."""
        from .config import CANDIDATES_DIR
        cand_dir = Path(CANDIDATES_DIR) / candidate_id

        # H2: try decider_prompt.py first
        decider_file = cand_dir / "decider_prompt.py"
        if decider_file.exists():
            return decider_file.read_text()

        # H1: fall back to system_prompt.py
        prompt_file = cand_dir / "system_prompt.py"
        if prompt_file.exists():
            return prompt_file.read_text()

        return "(prompt file not found)"

    def _load_analyst_config(self, candidate_id: str) -> str:
        """Load analyst_config.py content for H2 candidates."""
        from .config import CANDIDATES_DIR
        config_file = Path(CANDIDATES_DIR) / candidate_id / "analyst_config.py"
        if config_file.exists():
            return config_file.read_text()
        return ""

    def _load_memory_config(self, candidate_id: str) -> str:
        """Load memory_config.py content for H2X candidates."""
        from .config import CANDIDATES_DIR
        config_file = Path(CANDIDATES_DIR) / candidate_id / "memory_config.py"
        if config_file.exists():
            return config_file.read_text()
        return ""

    def _load_reviewer_prompt(self, candidate_id: str) -> str:
        """Load reviewer_prompt.py content for H2X candidates."""
        from .config import CANDIDATES_DIR
        config_file = Path(CANDIDATES_DIR) / candidate_id / "reviewer_prompt.py"
        if config_file.exists():
            return config_file.read_text()
        return ""

    @staticmethod
    def _render_single_value_diff(label: str, baseline_text: str,
                                   candidate_text: str, cid: str) -> str:
        """Render a diff for a single config value (like MEMORY_WINDOW)."""
        import re
        b_match = re.search(rf'{label}\s*=\s*(\d+)', baseline_text)
        c_match = re.search(rf'{label}\s*=\s*(\d+)', candidate_text)
        if b_match and c_match:
            b_val = b_match.group(1)
            c_val = c_match.group(1)
            if b_val != c_val:
                return f"""<div style="font-size:0.82em; margin:4px 0;">
  <span style="color:var(--red);">- {label} = {b_val} (baseline)</span><br>
  <span style="color:var(--green);">+ {label} = {c_val}</span>
</div>"""
        return ""

    def _get_holdout_configs(self) -> List[dict]:
        from .config import HOLDOUT_INSTANCES
        return HOLDOUT_INSTANCES

    @staticmethod
    def _escape_html(text: str) -> str:
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))
