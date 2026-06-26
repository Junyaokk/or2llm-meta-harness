"""
Meta-Harness for H1 Optimization (Plan B: 深 Trace).

Optimizes the OR->LLM system prompt via outer-loop search.
A coding agent (proposer) reads full rationale traces from prior
candidates and proposes improved prompt variants.

Usage:
  python -m meta_harness.runner --candidates 5 --periods 20
"""

from .evaluator import Evaluator, CandidateResult
from .trace_store import TraceStore
from .runner import MetaHarnessRunner
