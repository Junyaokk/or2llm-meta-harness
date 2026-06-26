"""
Proposer — calls Claude Code via subprocess to generate new harness candidates.

Replaces the manual "you tell Claude → Claude tells Python" loop with
automated Python→Claude→Python control flow (Stanford Meta-Harness pattern).

Claude Code reads trace files, prototypes new mechanisms, writes candidate
code, and outputs pending_eval.json summarizing what was produced.
"""
import json
import os
import time
from pathlib import Path
from typing import List, Optional

from .config import (
    PROPOSER_MODEL,
    PROPOSER_TIMEOUT,
    PROPOSER_SKILL,
    PROPOSER_ALLOWED_TOOLS,
    EVOLUTION_LOG_DIR,
    EVOLUTION_SUMMARY,
    PENDING_EVAL,
)
from . import claude_wrapper


def render_task_prompt(iteration: int, architecture: str) -> str:
    """Build the prompt that tells Claude Code where everything is and what to do."""
    return (
        f"Run iteration {iteration} of the inventory optimization harness evolution.\n\n"
        f"## Current Architecture\n"
        f"You are optimizing the **{architecture}** architecture.\n\n"
        f"## Run Directories\n"
        f"- Evolution summary (read): `{EVOLUTION_SUMMARY}`\n"
        f"- Pending eval (write): `{PENDING_EVAL}`\n"
        f"- Candidates directory: `candidates/`\n"
        f"- Trace stores: `traces/trace_store/`, `traces/trace_store_h2/`, "
        f"`traces/trace_store_h2_chain/`, `traces/trace_store_h2x/`, "
        f"`traces/trace_store_h2x_chain/`, `traces/trace_store_h2u/`\n"
        f"- Config: `config.py`\n"
        f"- Analyst definition: `h2/analyst.py`\n\n"
        f"## Instructions\n"
        f"1. Read evolution_summary.jsonl and worst-instance trace files\n"
        f"2. Formulate 2 falsifiable hypotheses targeting different mechanisms\n"
        f"3. Prototype each mechanism in /tmp/ with real trace data\n"
        f"4. Implement 2 new candidates under candidates/ (next available IDs)\n"
        f"5. Write pending_eval.json to: `{PENDING_EVAL}`\n\n"
        f"Output the line: CANDIDATES: <name1>, <name2>, <name3>"
    )


def propose_claude(
    iteration: int,
    architecture: str,
    timeout: Optional[int] = None,
) -> List[dict]:
    """Call Claude Code to propose, prototype, and implement new candidates.

    Returns list of candidate dicts from pending_eval.json, or empty list on failure.
    """
    if timeout is None:
        timeout = PROPOSER_TIMEOUT

    EVOLUTION_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Clean previous pending_eval so we can detect fresh output
    if PENDING_EVAL.exists():
        PENDING_EVAL.unlink()

    task_prompt = render_task_prompt(iteration, architecture)

    # Strip ANTHROPIC_API_KEY so claude CLI uses subscription auth (avoids rate limits)
    saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)

    t0 = time.time()
    result = claude_wrapper.run(
        prompt=task_prompt,
        model=PROPOSER_MODEL,
        allowed_tools=PROPOSER_ALLOWED_TOOLS,
        skills=[str(PROPOSER_SKILL)],
        cwd=str(Path(__file__).resolve().parent),
        log_dir=str(EVOLUTION_LOG_DIR / "claude_sessions"),
        name=f"iter{iteration}-{architecture}",
        timeout_seconds=timeout,
        effort="max",
    )
    elapsed = time.time() - t0

    # Restore API key
    if saved_key:
        os.environ["ANTHROPIC_API_KEY"] = saved_key

    if result.exit_code != 0:
        print(f"  Proposer FAILED after {elapsed:.0f}s: exit={result.exit_code}")
        if result.stderr:
            print(f"  stderr: {result.stderr[:500]}")
        return []

    result.show()

    if not PENDING_EVAL.exists():
        print(f"  Proposer completed but pending_eval.json NOT found at {PENDING_EVAL}")
        print(f"  Response text (truncated): {result.text[:500]}")
        return []

    try:
        data = json.loads(PENDING_EVAL.read_text())
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Failed to parse pending_eval.json: {e}")
        return []

    candidates = data.get("candidates", [])
    print(f"  Parsed {len(candidates)} candidate(s) from pending_eval.json")
    return candidates


def load_pending_candidates() -> List[dict]:
    """Read pending_eval.json. Returns list of candidate dicts."""
    if not PENDING_EVAL.exists():
        return []
    return json.loads(PENDING_EVAL.read_text()).get("candidates", [])


def update_evolution_summary(
    iteration: int,
    candidates: List[dict],
    val_scores: dict,
    propose_time: Optional[float] = None,
    bench_time: Optional[float] = None,
    wall_time: Optional[float] = None,
):
    """Append one JSONL row per evaluated candidate to evolution_summary.jsonl."""
    EVOLUTION_SUMMARY.parent.mkdir(parents=True, exist_ok=True)

    with open(EVOLUTION_SUMMARY, "a") as f:
        for i, c in enumerate(candidates):
            name = c.get("name", "unknown")
            mean_nr = val_scores.get(name, 0)
            row = {
                "iteration": iteration,
                "candidate_id": name,
                "architecture": c.get("architecture", "?"),
                "mean_nr": round(mean_nr, 4),
                "axis": c.get("axis", "?"),
                "hypothesis": c.get("hypothesis", ""),
            }
            if "components" in c:
                row["components"] = c["components"]
            if i == 0 and wall_time is not None:
                row["timing_s"] = {
                    "propose": round(propose_time, 1) if propose_time else None,
                    "bench": round(bench_time, 1) if bench_time else None,
                    "wall": round(wall_time, 1),
                }
            f.write(json.dumps(row) + "\n")
