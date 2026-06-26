"""
H2X Chain Runner — H2X progressive optimization with trace saving.
Architecture: Memory Buffer + Decider + Reviewer
Baseline: candidate_h2x_000
Trace store: trace_store_h2x_chain/

Uses Claude Code subprocess proposer (Stanford Meta-Harness pattern).
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meta_harness.config import (
    HOLDOUT_INSTANCES, N_PERIODS, EVAL_MODEL, EVAL_API_KEY, EVAL_BASE_URL,
)
from meta_harness.h2x.h2x_evaluator import H2XEvaluator
from meta_harness.trace_store import TraceStore
from meta_harness.proposer import propose_claude, update_evolution_summary
from meta_harness.validator import validate_candidates

H2X_CHAIN_TRACE_DIR = Path(__file__).resolve().parent.parent / "traces" / "trace_store_h2x_chain"
H2X_CHAIN_CANDIDATES_DIR = Path(__file__).resolve().parent / "candidates"
H2X_CHAIN_N_ITERATIONS = 10
BASELINE_ID = "candidate_h2x_000"


class H2XChainRunner:
    """H2X progressive optimization with trace saving."""

    def __init__(self):
        self.candidates_dir = Path(H2X_CHAIN_CANDIDATES_DIR)
        self.trace_store = TraceStore(Path(H2X_CHAIN_TRACE_DIR))
        self.run_log = []
        self.start_time = datetime.now()

    def run(self, proposer_func=None):
        print("=" * 70)
        print("H2X CHAIN META-HARNESS — Memory + Decider + Reviewer Optimization")
        print(f"  Instances: {len(HOLDOUT_INSTANCES)}")
        print(f"  Periods/instance: {N_PERIODS}")
        print(f"  Iterations: {H2X_CHAIN_N_ITERATIONS}")
        print(f"  Baseline: {BASELINE_ID}")
        print(f"  Trace store: {H2X_CHAIN_TRACE_DIR}")
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
        })
        self._print_scoreboard()

        # Step 2: Iterate
        for iteration in range(1, H2X_CHAIN_N_ITERATIONS + 1):
            print(f"\n{'=' * 70}")
            print(f"ITERATION {iteration}: Claude Code Proposer -> New Candidates -> Evaluate")
            print(f"{'=' * 70}")

            # Build proposer context
            context = self.trace_store.build_proposer_context(max_candidates=3, worst_instances=2)
            ctx_path = self.trace_store.store_dir / f"proposer_context_iter{iteration}.txt"
            ctx_path.write_text(context)
            print(f"  Proposer context: {len(context)} chars -> {ctx_path}")

            # Call Claude Code to propose candidates
            print(f"  Invoking Claude Code (opus)...", flush=True)
            candidates = propose_claude(iteration, "H2X")
            if not candidates:
                print(f"  No candidates, skipping iteration")
                continue

            print(f"  Got {len(candidates)} candidate(s)")

            valid = validate_candidates(candidates, "H2X")
            if not valid:
                print(f"  0 valid, skipping iteration")
                continue
            print(f"  {len(valid)} valid")

            # Save context + evaluate each
            val_scores = {}
            for ci, c in enumerate(valid):
                cand_id = c["name"]
                cand_dir = self.candidates_dir / cand_id
                shutil.copy(ctx_path, cand_dir / "proposer_context.txt")

                print(f"    [{ci+1}/{len(valid)}] Evaluating {cand_id}...", flush=True)
                result = self._evaluate(cand_id)
                self.trace_store.save(result)
                mean_nr = sum(result.per_instance_nr.values()) / len(result.per_instance_nr) if result.per_instance_nr else 0
                val_scores[cand_id] = mean_nr
                self.run_log.append({
                    "iteration": iteration,
                    "candidate_id": cand_id,
                    "mean_nr": mean_nr,
                    "per_instance_nr": result.per_instance_nr,
                })
                print(f"      NR={mean_nr:.4f}")

            update_evolution_summary(iteration, valid, val_scores)
            self._print_scoreboard()

            # Convergence check
            if iteration >= 5:
                recent = [r["mean_nr"] for r in self.run_log[-5:]]
                if max(recent) - min(recent) < 0.005:
                    print("\n  [CONVERGED] Stopping early.")
                    break

        self._print_final_summary()
        return self.run_log

    def _evaluate(self, candidate_id: str):
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

    def _propose(self, iteration: int):
        """Call Claude Code to propose new H2X chain candidates."""
        candidates = propose_claude(iteration, "H2X")
        if not candidates:
            return []
        return validate_candidates(candidates, "H2X")

    def _write_analyst_config(self, cand_dir: Path, overrides: dict,
                               cand_id: str, iteration: int):
        from meta_harness.h2.analyst import AnalystConfig
        base = AnalystConfig()
        for k, v in overrides.items():
            if hasattr(base, k):
                setattr(base, k, v)

        lines = [f'"""\n{cand_id} — H2X iteration {iteration}.\n"""',
                 'from meta_harness.h2.analyst import AnalystConfig', '',
                 'ANALYST_CONFIG = AnalystConfig(']
        for f in type(base).__dataclass_fields__.values():
            lines.append(f'    {f.name}={repr(getattr(base, f.name))},')
        lines.append(')')
        (cand_dir / "analyst_config.py").write_text('\n'.join(lines))

    def _write_decider_prompt(self, cand_dir: Path, prompt: str,
                               cand_id: str, iteration: int):
        if not prompt:
            from meta_harness.candidates.candidate_h2x_000.decider_prompt import SYSTEM_PROMPT
            prompt = SYSTEM_PROMPT
        content = f'''"""
{cand_id} — H2X Decider Prompt (iteration {iteration}).
"""
SYSTEM_PROMPT = """{prompt}"""
'''
        (cand_dir / "decider_prompt.py").write_text(content)

    def _write_reviewer_prompt(self, cand_dir: Path, prompt: str,
                                cand_id: str, iteration: int):
        if not prompt:
            from meta_harness.candidates.candidate_h2x_000.reviewer_prompt import SYSTEM_PROMPT
            prompt = SYSTEM_PROMPT
        content = f'''"""
{cand_id} — H2X Reviewer Prompt (iteration {iteration}).
"""
SYSTEM_PROMPT = """{prompt}"""
'''
        (cand_dir / "reviewer_prompt.py").write_text(content)

    def _write_memory_config(self, cand_dir: Path, window: int,
                              cand_id: str, iteration: int):
        content = f'''"""
{cand_id} — H2X Memory Config (iteration {iteration}).
"""
MEMORY_WINDOW = {window}
'''
        (cand_dir / "memory_config.py").write_text(content)

    def _print_scoreboard(self):
        scores = self.trace_store.get_all_scores()
        if not scores:
            return
        print(f"\n  {'Rank':<5} {'Candidate':<22} {'Mean NR':<10}")
        print(f"  {'-' * 40}")
        for rank, s in enumerate(scores, 1):
            print(f"  {rank:<5} {s['candidate_id']:<22} {s['mean_nr']:<10.4f}")

    def _print_final_summary(self):
        scores = self.trace_store.get_all_scores()
        if not scores:
            return
        best = scores[0]
        baseline = next((s for s in scores if s["candidate_id"] == BASELINE_ID), None)
        print(f"\n  Best: {best['candidate_id']} NR={best['mean_nr']:.4f}")
        if baseline:
            delta = best["mean_nr"] - baseline["mean_nr"]
            print(f"  Baseline ({BASELINE_ID}): NR={baseline['mean_nr']:.4f}")
            print(f"  Delta: {delta:+.4f} ({delta/baseline['mean_nr']*100:+.1f}%)")
        print(f"\n  H1(004) target: 0.7425")


def evaluate_baseline():
    """One-shot: evaluate H2X baseline and save traces."""
    runner = H2XChainRunner()
    print("Evaluating H2X baseline (candidate_h2x_000)...")
    result = runner._evaluate(BASELINE_ID)
    runner.trace_store.save(result)
    runner.run_log.append({
        "iteration": 0,
        "candidate_id": BASELINE_ID,
        "mean_nr": result.mean_nr,
        "per_instance_nr": result.per_instance_nr,
    })
    runner._print_scoreboard()
    print(f"\nTraces saved to {H2X_CHAIN_TRACE_DIR / BASELINE_ID}")


if __name__ == "__main__":
    evaluate_baseline()
