"""
Meta-Harness configuration. All tunable parameters in one place.
"""
import os
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = PROJECT_ROOT / "InventoryBench-main" / "benchmark" / "synthetic_trajectory"
CANDIDATES_DIR = Path(__file__).resolve().parent / "candidates"
TRACE_STORE_DIR = Path(__file__).resolve().parent / "traces" / "trace_store"
H2_TRACE_STORE_DIR = Path(__file__).resolve().parent / "traces" / "trace_store_h2"
H2X_TRACE_STORE_DIR = Path(__file__).resolve().parent / "traces" / "trace_store_h2x"
REPORT_DIR = Path(__file__).resolve().parent / "reports"

# --- Search Parameters ---
N_INSTANCES = 5             # Holdout instances
N_PERIODS = 20              # Periods per instance (truncated from 50)
N_ITERATIONS = 5            # Proposer iterations (1 new candidate each)
TOTAL_CANDIDATES = 1 + N_ITERATIONS  # baseline + 5 improvements = 6

# --- Holdout Dev Set (5 instances × 20 periods = 100 decision points) ---
# Chosen to span: stationary + trend + seasonal + changepoint + variance
# L=0 and L=4 both represented, all rho=0.80
HOLDOUT_INSTANCES = [
    {
        "path": "lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_med",
        "label": "p01_stationary_L0",
        "description": "Stationary IID, L=0, rho=0.80",
    },
    {
        "path": "lead_time_0/p04_increasing_trend/v1_linear_100t/r1_med",
        "label": "p04_increasing_trend_L0",
        "description": "Increasing linear trend, L=0, rho=0.80",
    },
    {
        "path": "lead_time_4/p07_seasonal/v1_period10_amp30/r1_med",
        "label": "p07_seasonal_L4",
        "description": "Seasonal demand (period=10, amp=30), L=4, rho=0.80",
    },
    {
        "path": "lead_time_0/p08_multi_changepoint/v1_up_then_down/r1_med",
        "label": "p08_changepoint_L0",
        "description": "Multi-changepoint (up then down), L=0, rho=0.80",
    },
    {
        "path": "lead_time_4/p06_variance_change/v1_normal_to_uniform/r1_med",
        "label": "p06_variance_L4",
        "description": "Variance change (normal->uniform), L=4, rho=0.80",
    },
]

# --- LLM Configuration (Evaluator) ---
import os as _os
EVAL_MODEL = os.getenv("EVAL_MODEL", "deepseek-chat")
EVAL_API_KEY = os.getenv("EVAL_API_KEY", "")
EVAL_BASE_URL = os.getenv("EVAL_BASE_URL", "https://api.deepseek.com/v1")
EVAL_TEMPERATURE = 0.0
EVAL_MAX_TOKENS = 4096
EVAL_TIMEOUT = 180.0
EVAL_MAX_RETRIES = 3

# --- Trace Configuration (Plan B: 深 Trace) ---
TRACE_VERSION = "plan_b_v1"

# --- H2X Config ---
H2X_N_ITERATIONS = 5
H2X_DEFAULT_MEMORY_WINDOW = 5

# --- H2M Config ---
H2M_TRACE_STORE_DIR = Path(__file__).resolve().parent / "traces" / "trace_store_h2m"
H2M_N_ITERATIONS = 5
H2M_DEFAULT_MEMORY_WINDOW = 7

# --- H2U Config ---
H2U_TRACE_STORE_DIR = Path(__file__).resolve().parent / "traces" / "trace_store_h2u"
H2U_N_ITERATIONS = 5

# --- Proposer Configuration ---
PROPOSER_MAX_PRIOR_CANDIDATES = 3
PROPOSER_WORST_INSTANCES = 2

# --- Claude Code Proposer Configuration ---
PROPOSER_MODEL = "opus"                # Claude model for proposal (NOT DeepSeek)
PROPOSER_TIMEOUT = 2400                # 40 min timeout per propose step
PROPOSER_SKILL = Path(__file__).resolve().parent / ".claude" / "skills" / "meta-harness-inventory"
PROPOSER_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Write", "Edit", "Bash"]

# --- Evolution Logging ---
EVOLUTION_LOG_DIR = Path(__file__).resolve().parent / "logs" / "evolution"
EVOLUTION_SUMMARY = EVOLUTION_LOG_DIR / "evolution_summary.jsonl"
PENDING_EVAL = EVOLUTION_LOG_DIR / "pending_eval.json"
