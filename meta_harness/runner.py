"""
Runner -- Meta-Harness outer loop orchestrator (H1 architecture).

Flow:
  1. Evaluate baseline candidate_000
  2. For each iteration:
     a. Claude Code proposes N new candidates (reads traces, writes code)
     b. Validate candidates (import check)
     c. Evaluate each valid candidate against holdout instances
     d. Store traces, update evolution summary
  3. Generate HTML report
"""
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import (
    CANDIDATES_DIR, TRACE_STORE_DIR, REPORT_DIR,
    HOLDOUT_INSTANCES, N_PERIODS, N_ITERATIONS,
    EVAL_MODEL, EVAL_API_KEY, EVAL_BASE_URL,
    PROPOSER_MAX_PRIOR_CANDIDATES, PROPOSER_WORST_INSTANCES,
)
from .evaluator import Evaluator, CandidateResult
from .trace_store import TraceStore
from .reporter import HtmlReporter
from .proposer import propose_claude, update_evolution_summary
from .validator import validate_candidates


class MetaHarnessRunner:
    """Orchestrates the full Meta-Harness loop."""

    def __init__(self):
        self.candidates_dir = Path(CANDIDATES_DIR)
        self.trace_store = TraceStore(Path(TRACE_STORE_DIR))
        self.report_dir = Path(REPORT_DIR)
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # Ensure baseline candidate exists
        self._ensure_baseline()

        self.run_log: List[dict] = []
        self.start_time = datetime.now()

    def _ensure_baseline(self):
        """Verify candidate_000 exists with a system_prompt.py."""
        baseline = self.candidates_dir / "candidate_000"
        baseline.mkdir(parents=True, exist_ok=True)
        prompt_file = baseline / "system_prompt.py"
        if not prompt_file.exists():
            # Copy from or_to_llm agent.py baseline
            from or_to_llm.agent import SYSTEM_PROMPT_TEMPLATE
            content = f'''"""
Candidate 000 -- Baseline (current prompt, unchanged).
"""

SYSTEM_PROMPT = """{SYSTEM_PROMPT_TEMPLATE}"""
'''
            prompt_file.write_text(content)
            print(f"[RUNNER] Created baseline candidate_000/system_prompt.py")

    def run(self, proposer_func: Optional[callable] = None):
        """
        Execute the full Meta-Harness loop.

        Args:
            proposer_func: (Deprecated) Kept for backward compatibility.
                           When None (default), uses Claude Code subprocess proposer.
        """
        if proposer_func is not None:
            print("  NOTE: proposer_func provided, using legacy mode (single-candidate per iter)")

        print("=" * 70)
        print("META-HARNESS RUNNER (H1) — Claude Code Proposer")
        print(f"  Instances: {len(HOLDOUT_INSTANCES)}")
        print(f"  Periods/instance: {N_PERIODS}")
        print(f"  Iterations: {N_ITERATIONS}")
        print(f"  Start: {self.start_time.isoformat()}")
        print("=" * 70)

        # === Step 1: Evaluate baseline ===
        print("\n" + "=" * 70)
        print("ITERATION 0: Evaluating BASELINE (candidate_000)")
        print("=" * 70)

        result_000 = self._evaluate_candidate("candidate_000")
        self.trace_store.save(result_000)
        self.run_log.append({
            "iteration": 0,
            "candidate_id": "candidate_000",
            "mean_nr": result_000.mean_nr,
            "per_instance_nr": result_000.per_instance_nr,
            "timestamp": datetime.now().isoformat(),
        })
        self._print_scoreboard()

        # === Step 2: Iterate ===
        for iteration in range(1, N_ITERATIONS + 1):
            print(f"\n{'=' * 70}")
            print(f"ITERATION {iteration}: Claude Code Proposer -> New Candidates -> Evaluate")
            print(f"{'=' * 70}")

            iter_start = time.time()

            # Build proposer context and save for traceability
            context = self.trace_store.build_proposer_context(
                max_candidates=PROPOSER_MAX_PRIOR_CANDIDATES,
                worst_instances=PROPOSER_WORST_INSTANCES,
            )
            context_path = self.trace_store.store_dir / f"proposer_context_iter{iteration}.txt"
            context_path.write_text(context)
            print(f"  Proposer context: {len(context)} chars -> {context_path}")

            # Call Claude Code to propose candidates (writes to filesystem)
            propose_start = time.time()
            print(f"  Invoking Claude Code (opus, max 40min)...", flush=True)
            candidates = propose_claude(iteration, "H1")
            propose_time = time.time() - propose_start

            if not candidates:
                print(f"  No candidates produced, skipping iteration")
                continue

            print(f"  Got {len(candidates)} candidate(s) in {propose_time:.0f}s")

            # Validate
            valid = validate_candidates(candidates, "H1")
            if not valid:
                print(f"  0/{len(candidates)} valid, skipping iteration")
                continue
            print(f"  {len(valid)}/{len(candidates)} valid")

            # Evaluate each valid candidate
            bench_start = time.time()
            val_scores = {}
            for ci, c in enumerate(valid):
                cand_id = c["name"]
                print(f"    [{ci+1}/{len(valid)}] Evaluating {cand_id}...", flush=True)
                t0 = time.time()
                result = self._evaluate_candidate(cand_id)
                elapsed = time.time() - t0

                # Store traces
                self.trace_store.save(result)

                # Compute mean NR
                if result.per_instance_nr:
                    mean_nr = sum(result.per_instance_nr.values()) / len(result.per_instance_nr)
                else:
                    mean_nr = 0
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

            # Convergence check
            if iteration >= 3:
                recent = [r["mean_nr"] for r in self.run_log[-3:]]
                if max(recent) - min(recent) < 0.005:
                    print("\n  [CONVERGED] Last 3 iterations within 0.005 NR. Stopping early.")
                    break

        # === Step 3: Generate HTML Report ===
        print(f"\n{'=' * 70}")
        print("GENERATING HTML REPORT")
        print(f"{'=' * 70}")

        reporter = HtmlReporter(
            run_log=self.run_log,
            trace_store=self.trace_store,
            start_time=self.start_time,
            config={
                "n_instances": len(HOLDOUT_INSTANCES),
                "n_periods": N_PERIODS,
                "n_iterations": N_ITERATIONS,
                "holdout_labels": [h["label"] for h in HOLDOUT_INSTANCES],
            },
        )
        report_path = reporter.generate()
        print(f"  Report: {report_path}")

        # === Step 4: Summary ===
        print(f"\n{'=' * 70}")
        print("META-HARNESS RUN COMPLETE")
        print(f"{'=' * 70}")
        self._print_final_summary()

        return self.run_log

    def _evaluate_candidate(self, candidate_id: str) -> CandidateResult:
        """Evaluate one candidate against all holdout instances."""
        cand_dir = self.candidates_dir / candidate_id
        evaluator = Evaluator(
            candidate_dir=cand_dir,
            holdout_configs=HOLDOUT_INSTANCES,
            n_periods=N_PERIODS,
            model=EVAL_MODEL,
            api_key=EVAL_API_KEY,
            base_url=EVAL_BASE_URL,
        )
        return evaluator.evaluate(candidate_id)

    def _propose(self, iteration: int) -> List[dict]:
        """Call Claude Code to propose new H1 candidates. Returns list of valid candidate dicts."""
        candidates = propose_claude(iteration, "H1")
        if not candidates:
            return []
        return validate_candidates(candidates, "H1")

    def _print_scoreboard(self):
        """Print current scoreboard."""
        all_scores = self.trace_store.get_all_scores()
        if not all_scores:
            return
        print(f"\n  {'Rank':<5} {'Candidate':<18} {'Mean NR':<10}")
        print(f"  {'-' * 35}")
        for rank, s in enumerate(all_scores, 1):
            marker = " ← NEW" if s["candidate_id"] == self.run_log[-1]["candidate_id"] else ""
            print(f"  {rank:<5} {s['candidate_id']:<18} {s['mean_nr']:<10.4f}{marker}")

    def _print_final_summary(self):
        """Print final run summary."""
        all_scores = self.trace_store.get_all_scores()
        if not all_scores:
            print("  No results.")
            return

        best = all_scores[0]
        baseline = next((s for s in all_scores if s["candidate_id"] == "candidate_000"), None)

        print(f"  Best candidate:  {best['candidate_id']} (NR={best['mean_nr']:.4f})")
        if baseline:
            delta = best["mean_nr"] - baseline["mean_nr"]
            print(f"  Baseline:        candidate_000 (NR={baseline['mean_nr']:.4f})")
            print(f"  Delta:           {delta:+.4f} ({delta/baseline['mean_nr']*100:+.1f}%)")
        print(f"  Total candidates evaluated: {len(all_scores)}")
        print(f"  Trace store:     {self.trace_store.store_dir}")
        print(f"  HTML report:     {self.report_dir / 'meta_harness_report.html'}")


def run_cli():
    """Entry point: python -m meta_harness.runner"""
    runner = MetaHarnessRunner()
    runner.run()


if __name__ == "__main__":
    run_cli()
