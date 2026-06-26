"""
H2X Runner — Meta-Harness loop for Memory + Decider + Reviewer architecture.
Evaluates candidates, feeds traces to Proposer, iterates.
"""
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from meta_harness.config import (
    HOLDOUT_INSTANCES, N_PERIODS, EVAL_MODEL, EVAL_API_KEY, EVAL_BASE_URL,
    H2X_TRACE_STORE_DIR, H2X_N_ITERATIONS, H2X_DEFAULT_MEMORY_WINDOW,
)
from meta_harness.h2x.h2x_evaluator import H2XEvaluator
from meta_harness.trace_store import TraceStore
from meta_harness.reporter import HtmlReporter

H2X_CANDIDATES_DIR = Path(__file__).resolve().parent.parent / "candidates"
H2X_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"

PROPOSER_MAX_PRIOR = 3
PROPOSER_WORST_INSTANCES = 2


class H2XRunner:
    """Orchestrates H2X Meta-Harness loop for Memory + Decider + Reviewer."""

    def __init__(self):
        self.candidates_dir = Path(H2X_CANDIDATES_DIR)
        self.trace_store = TraceStore(Path(H2X_TRACE_STORE_DIR))
        self.report_dir = Path(H2X_REPORT_DIR)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.run_log = []
        self.start_time = datetime.now()

    def run(self, proposer_func: Optional[Callable] = None):
        print("=" * 70)
        print("H2X META-HARNESS RUNNER — Memory + Decider + Reviewer")
        print(f"  Instances: {len(HOLDOUT_INSTANCES)}")
        print(f"  Periods/instance: {N_PERIODS}")
        print(f"  Iterations: {H2X_N_ITERATIONS}")
        print(f"  Start: {self.start_time.isoformat()}")
        print("=" * 70)

        # Step 1: Evaluate baseline (candidate_012)
        print("\n" + "=" * 70)
        print("ITERATION 0: Evaluating H2X BASELINE (candidate_012)")
        print("=" * 70)

        result = self._evaluate_candidate("candidate_012")
        self.trace_store.save(result)
        self.run_log.append({
            "iteration": 0,
            "candidate_id": "candidate_012",
            "mean_nr": result.mean_nr,
            "per_instance_nr": result.per_instance_nr,
            "timestamp": datetime.now().isoformat(),
        })
        self._print_scoreboard()

        # Step 2: Iterate
        h2x_start_idx = 13
        for iteration in range(1, H2X_N_ITERATIONS + 1):
            print(f"\n{'=' * 70}")
            print(f"ITERATION {iteration}: Proposer → New Candidate → Evaluate")
            print(f"{'=' * 70}")

            cand_id = f"candidate_{h2x_start_idx + iteration - 1:03d}"

            # Build proposer context
            context = self.trace_store.build_proposer_context(
                max_candidates=PROPOSER_MAX_PRIOR,
                worst_instances=PROPOSER_WORST_INSTANCES,
            )
            ctx_path = self.trace_store.store_dir / f"proposer_context_iter{iteration}.txt"
            ctx_path.write_text(context)
            print(f"  Proposer context: {len(context)} chars → {ctx_path}")

            # Evaluate
            cand_dir = self.candidates_dir / cand_id
            if not cand_dir.exists():
                print(f"  [SKIP] {cand_id} not found — stopping iteration.")
                break

            result = self._evaluate_candidate(cand_id)
            self.trace_store.save(result)
            self.run_log.append({
                "iteration": iteration,
                "candidate_id": cand_id,
                "mean_nr": result.mean_nr,
                "per_instance_nr": result.per_instance_nr,
                "timestamp": datetime.now().isoformat(),
            })
            self._print_scoreboard()

        # Step 3: Report
        print(f"\n{'=' * 70}")
        print("GENERATING H2X HTML REPORT")
        print(f"{'=' * 70}")

        reporter = HtmlReporter(
            run_log=self.run_log,
            trace_store=self.trace_store,
            start_time=self.start_time,
            config={
                "n_instances": len(HOLDOUT_INSTANCES),
                "n_periods": N_PERIODS,
                "n_iterations": H2X_N_ITERATIONS,
                "holdout_labels": [h["label"] for h in HOLDOUT_INSTANCES],
            },
            title="H2X Memory + Reviewer Architecture",
            baseline_id="candidate_012",
        )
        report_path = reporter.generate(self.report_dir / "meta_harness_h2x_report.html")
        print(f"  Report: {report_path}")

        print(f"\n{'=' * 70}")
        print("H2X META-HARNESS RUN COMPLETE")
        print(f"{'=' * 70}")
        self._print_final_summary()
        return self.run_log

    def _evaluate_candidate(self, candidate_id: str):
        cand_dir = self.candidates_dir / candidate_id
        evaluator = H2XEvaluator(
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
        print("\n  SCOREBOARD:")
        for s in scores:
            print(f"    {s['candidate_id']}: NR={s['mean_nr']:.4f}")

    def _print_final_summary(self):
        scores = self.trace_store.get_all_scores()
        if len(scores) < 2:
            return
        best = scores[0]
        baseline = next((s for s in scores if "012" in s["candidate_id"]), None)
        if baseline and best != baseline:
            delta = best["mean_nr"] - baseline["mean_nr"]
            print(f"  Best: {best['candidate_id']} NR={best['mean_nr']:.4f}")
            print(f"  Baseline (012): NR={baseline['mean_nr']:.4f}")
            print(f"  Delta: {delta:+.4f} ({delta/baseline['mean_nr']*100:+.1f}%)")


def main():
    runner = H2XRunner()
    runner.run()


if __name__ == "__main__":
    main()
