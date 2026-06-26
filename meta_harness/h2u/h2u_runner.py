"""
H2U Runner — Meta-Harness loop for H2U architecture.

Combines H2's deterministic Analyst with H2X's Memory Buffer + Decider-Reviewer.
Evaluates candidates, feeds traces to Claude Code Proposer, iterates.

Architecture files per candidate:
  - analyst_config.py   (H2 AnalystConfig thresholds)
  - decider_prompt.py   (LLM Decider with Analyst signal trust)
  - reviewer_prompt.py  (LLM Reviewer with Analyst signal cross-check)
  - memory_config.py    (MEMORY_WINDOW integer)
"""
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from meta_harness.config import (
    HOLDOUT_INSTANCES, N_PERIODS, EVAL_MODEL, EVAL_API_KEY, EVAL_BASE_URL,
)
from meta_harness.h2u.h2u_evaluator import H2UEvaluator
from meta_harness.trace_store import TraceStore
from meta_harness.reporter import HtmlReporter
from meta_harness.proposer import propose_claude, update_evolution_summary
from meta_harness.validator import validate_candidates

# H2U paths
H2U_CANDIDATES_DIR = Path(__file__).resolve().parent.parent / "candidates"
H2U_TRACE_STORE_DIR = Path(__file__).resolve().parent.parent / "traces" / "trace_store_h2u"
H2U_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
H2U_N_ITERATIONS = 5
BASELINE_ID = "candidate_h2u_000"


class H2URunner:
    """Orchestrates H2U Meta-Harness loop (Analyst + Memory + Decider + Reviewer)."""

    def __init__(self):
        self.candidates_dir = Path(H2U_CANDIDATES_DIR)
        self.trace_store = TraceStore(Path(H2U_TRACE_STORE_DIR))
        self.report_dir = Path(H2U_REPORT_DIR)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_baseline()
        self.run_log = []
        self.start_time = datetime.now()

    def _ensure_baseline(self):
        """Verify candidate_h2u_000 exists with all 4 files."""
        baseline = self.candidates_dir / BASELINE_ID
        baseline.mkdir(parents=True, exist_ok=True)
        required = ["analyst_config.py", "decider_prompt.py",
                    "reviewer_prompt.py", "memory_config.py"]
        missing = [f for f in required if not (baseline / f).exists()]
        if missing:
            print(f"[H2U RUNNER] WARNING: baseline missing files: {missing}")

    def run(self) -> List[dict]:
        """Execute full H2U Meta-Harness loop with Claude Code proposer."""
        print("=" * 70)
        print("H2U META-HARNESS RUNNER — Analyst + Memory + Decider + Reviewer")
        print(f"  Instances: {len(HOLDOUT_INSTANCES)}")
        print(f"  Periods/instance: {N_PERIODS}")
        print(f"  Iterations: {H2U_N_ITERATIONS}")
        print(f"  Baseline: {BASELINE_ID}")
        print(f"  Trace store: {H2U_TRACE_STORE_DIR}")
        print(f"  Start: {self.start_time.isoformat()}")
        print("=" * 70)

        # Step 1: Evaluate baseline
        print(f"\n{'=' * 70}")
        print(f"ITERATION 0: Evaluating BASELINE ({BASELINE_ID})")
        print(f"{'=' * 70}")

        result_0 = self._evaluate(BASELINE_ID)
        self.trace_store.save(result_0)
        self.run_log.append({
            "iteration": 0,
            "candidate_id": BASELINE_ID,
            "mean_nr": result_0.mean_nr,
            "per_instance_nr": result_0.per_instance_nr,
            "timestamp": datetime.now().isoformat(),
        })
        update_evolution_summary(
            iteration=0,
            candidates=[{"name": BASELINE_ID, "architecture": "H2U",
                         "hypothesis": "Baseline: H2 Analyst + H2X Memory/Decider/Reviewer",
                         "axis": "baseline"}],
            val_scores={BASELINE_ID: result_0.mean_nr},
        )
        self._print_scoreboard()

        # Step 2: Iterate
        for iteration in range(1, H2U_N_ITERATIONS + 1):
            print(f"\n{'=' * 70}")
            print(f"ITERATION {iteration}: Claude Code -> Propose -> Evaluate")
            print(f"{'=' * 70}")

            iter_start = time.time()

            # Build proposer context
            context = self.trace_store.build_proposer_context(
                max_candidates=3, worst_instances=2,
            )
            ctx_path = self.trace_store.store_dir / f"proposer_context_iter{iteration}.txt"
            ctx_path.write_text(context)
            print(f"  Proposer context: {len(context)} chars -> {ctx_path}")

            # Claude Code proposes candidates
            print(f"  Invoking Claude Code (opus)...", flush=True)
            propose_start = time.time()
            candidates = propose_claude(iteration, "H2U")
            propose_time = time.time() - propose_start

            if not candidates:
                print(f"  No candidates, skipping iteration")
                continue

            print(f"  Got {len(candidates)} candidate(s) in {propose_time:.0f}s")

            # Validate
            valid = validate_candidates(candidates, "H2U")
            if not valid:
                print(f"  0 valid, skipping iteration")
                continue
            print(f"  {len(valid)}/{len(candidates)} valid")

            # Save context + evaluate each
            bench_start = time.time()
            val_scores = {}
            for ci, c in enumerate(valid):
                cand_id = c["name"]
                cand_dir = self.candidates_dir / cand_id
                shutil.copy(ctx_path, cand_dir / "proposer_context.txt")

                print(f"    [{ci+1}/{len(valid)}] Evaluating {cand_id}...", flush=True)
                t0 = time.time()
                result = self._evaluate(cand_id)
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

            # Convergence check
            if iteration >= 3:
                recent = [r["mean_nr"] for r in self.run_log[-3:]]
                if max(recent) - min(recent) < 0.005:
                    print("\n  [CONVERGED] Last 3 iterations within 0.005 NR. Stopping early.")
                    break

        # Step 3: Report
        print(f"\n{'=' * 70}")
        print("GENERATING H2U HTML REPORT")
        print(f"{'=' * 70}")

        reporter = HtmlReporter(
            run_log=self.run_log,
            trace_store=self.trace_store,
            start_time=self.start_time,
            config={
                "n_instances": len(HOLDOUT_INSTANCES),
                "n_periods": N_PERIODS,
                "n_iterations": H2U_N_ITERATIONS,
                "holdout_labels": [h["label"] for h in HOLDOUT_INSTANCES],
            },
            title="H2U — Analyst + Memory + Decider + Reviewer",
            baseline_id=BASELINE_ID,
        )
        report_path = reporter.generate(self.report_dir / "meta_harness_h2u_report.html")
        print(f"  Report: {report_path}")

        print(f"\n{'=' * 70}")
        print("H2U META-HARNESS RUN COMPLETE")
        print(f"{'=' * 70}")
        self._print_final_summary()
        return self.run_log

    def _evaluate(self, candidate_id: str):
        cand_dir = self.candidates_dir / candidate_id
        evaluator = H2UEvaluator(
            candidate_dir=cand_dir,
            holdout_configs=HOLDOUT_INSTANCES,
            n_periods=N_PERIODS,
            model=EVAL_MODEL,
            api_key=EVAL_API_KEY,
            base_url=EVAL_BASE_URL,
        )
        return evaluator.evaluate(candidate_id)

    def _print_scoreboard(self):
        scores = self.trace_store.get_all_scores()
        if not scores:
            return
        print(f"\n  {'Rank':<5} {'Candidate':<22} {'Mean NR':<10}")
        print(f"  {'-' * 40}")
        for rank, s in enumerate(scores, 1):
            marker = " ← NEW" if s["candidate_id"] == self.run_log[-1]["candidate_id"] else ""
            print(f"  {rank:<5} {s['candidate_id']:<22} {s['mean_nr']:<10.4f}{marker}")

    def _print_final_summary(self):
        scores = self.trace_store.get_all_scores()
        if not scores:
            print("  No results.")
            return
        best = scores[0]
        baseline = next((s for s in scores if s["candidate_id"] == BASELINE_ID), None)
        print(f"\n  Best candidate:  {best['candidate_id']} (NR={best['mean_nr']:.4f})")
        if baseline:
            delta = best["mean_nr"] - baseline["mean_nr"]
            print(f"  Baseline:        {BASELINE_ID} (NR={baseline['mean_nr']:.4f})")
            print(f"  Delta:           {delta:+.4f} ({delta/baseline['mean_nr']*100:+.1f}%)")
        print(f"  Total candidates evaluated: {len(scores)}")
        print(f"  Trace store:     {self.trace_store.store_dir}")
        print(f"  HTML report:     {self.report_dir / 'meta_harness_h2u_report.html'}")


def evaluate_baseline():
    """One-shot: evaluate H2U baseline and save traces."""
    runner = H2URunner()
    print("Evaluating H2U baseline (candidate_h2u_000)...")
    result = runner._evaluate(BASELINE_ID)
    runner.trace_store.save(result)
    runner.run_log.append({
        "iteration": 0,
        "candidate_id": BASELINE_ID,
        "mean_nr": result.mean_nr,
        "per_instance_nr": result.per_instance_nr,
    })
    runner._print_scoreboard()
    print(f"\nTraces saved to {H2U_TRACE_STORE_DIR / BASELINE_ID}")


if __name__ == "__main__":
    runner = H2URunner()
    runner.run()
