"""Script to generate proposer context files from trace data and regenerate report."""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meta_harness.trace_store import TraceStore
from meta_harness.reporter import HtmlReporter


def main():
    base = Path(__file__).resolve().parent
    store_dir = base / "traces" / "trace_store"
    report_dir = base / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    trace_store = TraceStore(store_dir=store_dir)

    # --- Generate proposer context files for each iteration ---
    all_scores = trace_store.get_all_scores()
    # chronological order: candidate_000, 001, 002, 003, 004, 005
    chronological = list(reversed(all_scores))

    for i, s in enumerate(chronological):
        cid = s["candidate_id"]
        iter_num = int(cid.split("_")[1])
        ctx_path = store_dir / f"proposer_context_iter{iter_num}.txt"

        if ctx_path.exists():
            continue

        ctx_text = trace_store.build_proposer_context(
            max_candidates=3,
            worst_instances=2,
        )
        ctx_path.write_text(ctx_text)
        print(f"  Generated: {ctx_path} ({len(ctx_text)} chars)")

    # --- Regenerate HTML report ---
    run_log = []
    for s in chronological:
        run_log.append({
            "candidate_id": s["candidate_id"],
            "mean_nr": s["mean_nr"],
            "per_instance_nr": s["per_instance_nr"],
        })

    config = {
        "n_instances": 5,
        "n_periods": 20,
        "n_iterations": 5,
        "holdout_labels": list(all_scores[0]["per_instance_nr"].keys()),
    }

    start_time = datetime(2026, 5, 17, 18, 0, 0)

    reporter = HtmlReporter(
        run_log=run_log,
        trace_store=trace_store,
        start_time=start_time,
        config=config,
    )

    report_path = reporter.generate(report_dir / "meta_harness_report.html")
    print(f"\nReport generated: {report_path}")
    print(f"Size: {report_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
