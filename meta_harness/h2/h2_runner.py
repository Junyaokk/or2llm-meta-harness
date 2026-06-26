"""
H2 Runner — Meta-Harness loop for Analyst + Decider architecture.
Evaluates candidates, feeds traces to Claude Code Proposer, iterates.
"""
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from meta_harness.config import (
    HOLDOUT_INSTANCES, N_PERIODS, EVAL_MODEL, EVAL_API_KEY, EVAL_BASE_URL,
)
from meta_harness.h2.h2_evaluator import H2Evaluator, H2CandidateResult
from meta_harness.trace_store import TraceStore
from meta_harness.reporter import HtmlReporter
from meta_harness.proposer import propose_claude, update_evolution_summary
from meta_harness.validator import validate_candidates

# H2-specific paths
H2_CANDIDATES_DIR = Path(__file__).resolve().parent.parent / "candidates"
H2_TRACE_STORE_DIR = Path(__file__).resolve().parent.parent / "traces" / "trace_store_h2"
H2_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
H2_N_ITERATIONS = 5

# Proposer params
PROPOSER_MAX_PRIOR = 3
PROPOSER_WORST_INSTANCES = 2


class H2Runner:
    """Orchestrates H2 Meta-Harness loop for Analyst + Decider candidates."""

    def __init__(self):
        self.candidates_dir = Path(H2_CANDIDATES_DIR)
        self.trace_store = TraceStore(Path(H2_TRACE_STORE_DIR))
        self.report_dir = Path(H2_REPORT_DIR)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_baseline()
        self.run_log = []
        self.start_time = datetime.now()

    def _ensure_baseline(self):
        """Ensure candidate_006 exists as H2 baseline."""
        baseline = self.candidates_dir / "candidate_006"
        baseline.mkdir(parents=True, exist_ok=True)

        analyst_file = baseline / "analyst_config.py"
        if not analyst_file.exists():
            content = '''"""
Candidate 006 -- H2 Baseline: Analyst + Decider architecture.
All analyst modules enabled, default thresholds.
"""
from meta_harness.h2.analyst import AnalystConfig

ANALYST_CONFIG = AnalystConfig(
    pipe_overfill_ratio=1.0,
    pipe_adequate_ratio=0.7,
    overdue_tolerance=1,
    trend_window=5,
    trend_evidence_periods=4,
    trend_gap_threshold=0.15,
    volatility_cv_threshold=0.5,
    or_bias_threshold=0.12,
    iid_window=10,
    iid_trend_threshold=0.10,
    z_score_threshold=3.0,
    sustained_deviation_periods=4,
    enable_pipeline=True,
    enable_demand=True,
    enable_or_audit=True,
    enable_anomaly=True,
)
'''
            analyst_file.write_text(content)
            print("[H2 RUNNER] Created baseline analyst_config.py")

        decider_file = baseline / "decider_prompt.py"
        if not decider_file.exists():
            from meta_harness.candidates.candidate_006.decider_prompt import SYSTEM_PROMPT
            content = f'''"""
Candidate 006 -- H2 Baseline Decider Prompt.
Decider receives pre-computed analysis, exercises judgment only.
"""
SYSTEM_PROMPT = """{SYSTEM_PROMPT}"""
'''
            decider_file.write_text(content)
            print("[H2 RUNNER] Created baseline decider_prompt.py")

    def run(self, proposer_func: Optional[Callable] = None):
        """Execute full H2 Meta-Harness loop.

        Args:
            proposer_func: (Deprecated) Kept for backward compatibility.
                           When None (default), uses Claude Code subprocess proposer.
        """
        print("=" * 70)
        print("H2 META-HARNESS RUNNER — Analyst + Decider (Claude Code Proposer)")
        print(f"  Instances: {len(HOLDOUT_INSTANCES)}")
        print(f"  Periods/instance: {N_PERIODS}")
        print(f"  Iterations: {H2_N_ITERATIONS}")
        print(f"  Start: {self.start_time.isoformat()}")
        print("=" * 70)

        # Step 1: Evaluate baseline
        print("\n" + "=" * 70)
        print("ITERATION 0: Evaluating H2 BASELINE (candidate_006)")
        print("=" * 70)

        result = self._evaluate_candidate("candidate_006")
        self.trace_store.save(result)
        self.run_log.append({
            "iteration": 0,
            "candidate_id": "candidate_006",
            "mean_nr": result.mean_nr,
            "per_instance_nr": result.per_instance_nr,
            "timestamp": datetime.now().isoformat(),
        })
        self._print_scoreboard()

        # Step 2: Iterate
        for iteration in range(1, H2_N_ITERATIONS + 1):
            print(f"\n{'=' * 70}")
            print(f"ITERATION {iteration}: Claude Code Proposer -> New Candidates -> Evaluate")
            print(f"{'=' * 70}")

            iter_start = time.time()

            # Build proposer context
            context = self.trace_store.build_proposer_context(
                max_candidates=PROPOSER_MAX_PRIOR,
                worst_instances=PROPOSER_WORST_INSTANCES,
            )
            ctx_path = self.trace_store.store_dir / f"proposer_context_iter{iteration}.txt"
            ctx_path.write_text(context)
            print(f"  Proposer context: {len(context)} chars")

            # Call Claude Code to propose candidates
            propose_start = time.time()
            print(f"  Invoking Claude Code (opus, max 40min)...", flush=True)
            candidates = propose_claude(iteration, "H2")
            propose_time = time.time() - propose_start

            if not candidates:
                print(f"  No candidates, skipping iteration")
                continue

            print(f"  Got {len(candidates)} candidate(s) in {propose_time:.0f}s")

            # Validate
            valid = validate_candidates(candidates, "H2")
            if not valid:
                print(f"  0/{len(candidates)} valid, skipping iteration")
                continue
            print(f"  {len(valid)}/{len(candidates)} valid")

            # Save proposer context alongside each candidate
            for c in valid:
                cand_dir = self.candidates_dir / c["name"]
                shutil.copy(ctx_path, cand_dir / "proposer_context.txt")

            # Evaluate each valid candidate
            bench_start = time.time()
            val_scores = {}
            for ci, c in enumerate(valid):
                cand_id = c["name"]
                print(f"    [{ci+1}/{len(valid)}] Evaluating {cand_id}...", flush=True)
                t0 = time.time()
                result = self._evaluate_candidate(cand_id)
                elapsed = time.time() - t0

                self.trace_store.save(result)
                mean_nr = sum(result.per_instance_nr.values()) / len(result.per_instance_nr) if result.per_instance_nr else 0
                val_scores[cand_id] = mean_nr

                self.run_log.append({
                    "iteration": iteration,
                    "candidate_id": cand_id,
                    "mean_nr": mean_nr,
                    "per_instance_nr": result.per_instance_nr,
                    "timestamp": datetime.now().isoformat(),
                })
                print(f"      NR={mean_nr:.4f} ({elapsed:.0f}s)")

            bench_time = time.time() - bench_start
            wall_time = time.time() - iter_start

            update_evolution_summary(
                iteration, valid, val_scores,
                propose_time=propose_time, bench_time=bench_time, wall_time=wall_time,
            )

            self._print_scoreboard()

            if iteration >= 3:
                recent = [r["mean_nr"] for r in self.run_log[-3:]]
                if max(recent) - min(recent) < 0.005:
                    print("\n  [CONVERGED] Stopping early.")
                    break

        # Step 3: Report
        print(f"\n{'=' * 70}")
        print("GENERATING H2 HTML REPORT")
        print(f"{'=' * 70}")

        reporter = HtmlReporter(
            run_log=self.run_log,
            trace_store=self.trace_store,
            start_time=self.start_time,
            config={
                "n_instances": len(HOLDOUT_INSTANCES),
                "n_periods": N_PERIODS,
                "n_iterations": H2_N_ITERATIONS,
                "holdout_labels": [h["label"] for h in HOLDOUT_INSTANCES],
            },
            title="H2 Analyst + Decider Optimization",
            baseline_id="candidate_006",
        )
        report_path = reporter.generate(self.report_dir / "meta_harness_h2_report.html")
        print(f"  Report: {report_path}")

        print(f"\n{'=' * 70}")
        print("H2 META-HARNESS RUN COMPLETE")
        print(f"{'=' * 70}")
        self._print_final_summary()
        return self.run_log

    def _evaluate_candidate(self, candidate_id: str):
        cand_dir = self.candidates_dir / candidate_id
        evaluator = H2Evaluator(
            candidate_dir=cand_dir,
            holdout_configs=HOLDOUT_INSTANCES,
            n_periods=N_PERIODS,
            model=EVAL_MODEL,
            api_key=EVAL_API_KEY,
            base_url=EVAL_BASE_URL,
        )
        return evaluator.evaluate(candidate_id)

    def _propose(self, iteration: int):
        """Call Claude Code to propose new H2 candidates. Returns list of valid candidate dicts."""
        candidates = propose_claude(iteration, "H2")
        if not candidates:
            return []
        return validate_candidates(candidates, "H2")

    def _write_analyst_config(self, cand_dir: Path, config_override,
                               cand_id: str, iteration: int):
        """Write analyst_config.py, merging overrides onto baseline defaults."""
        from meta_harness.h2.analyst import AnalystConfig
        base = AnalystConfig()

        if config_override is None:
            config_override = {}

        if isinstance(config_override, AnalystConfig):
            cfg = config_override
        elif isinstance(config_override, dict) and config_override:
            # Merge dict overrides
            for k, v in config_override.items():
                if hasattr(base, k):
                    setattr(base, k, v)
            cfg = base
        else:
            cfg = base

        lines = [f'"""\n{cand_id} — H2 Proposer-generated (iteration {iteration}).\n"""',
                 'from meta_harness.h2.analyst import AnalystConfig', '',
                 'ANALYST_CONFIG = AnalystConfig(']
        for field_name in [f.name for f in type(cfg).__dataclass_fields__.values()]:
            val = getattr(cfg, field_name)
            lines.append(f'    {field_name}={repr(val)},')
        lines.append(')')
        lines.append('')

        (cand_dir / "analyst_config.py").write_text('\n'.join(lines))

    def _write_decider_prompt(self, cand_dir: Path, prompt: str,
                               cand_id: str, iteration: int):
        """Write decider_prompt.py."""
        if not prompt:
            # Copy baseline decider prompt
            from meta_harness.candidates.candidate_006.decider_prompt import SYSTEM_PROMPT
            prompt = SYSTEM_PROMPT

        content = f'''"""
{cand_id} — H2 Decider Prompt (iteration {iteration}).
"""
SYSTEM_PROMPT = """{prompt}"""
'''
        (cand_dir / "decider_prompt.py").write_text(content)

    def _print_scoreboard(self):
        scores = self.trace_store.get_all_scores()
        print("\n  SCOREBOARD:")
        for s in scores:
            print(f"    {s['candidate_id']}: NR={s['mean_nr']:.4f}")

    def _print_final_summary(self):
        scores = self.trace_store.get_all_scores()
        if len(scores) < 2:
            return
        best = scores[0]
        baseline = next((s for s in scores if "006" in s["candidate_id"]), None)
        if baseline and best != baseline:
            delta = best["mean_nr"] - baseline["mean_nr"]
            print(f"  Best: {best['candidate_id']} NR={best['mean_nr']:.4f}")
            print(f"  Baseline: NR={baseline['mean_nr']:.4f}")
            print(f"  Delta: {delta:+.4f} ({delta/baseline['mean_nr']*100:+.1f}%)")
