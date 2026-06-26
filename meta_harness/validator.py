"""
Validator — import-check candidates before benchmarking to catch errors early.

Each architecture (H1, H2, H2X) has a different file structure. The validator
verifies that all required files exist and import correctly.
"""
import subprocess
import sys
from pathlib import Path
from typing import List, Dict

CANDIDATES_DIR = Path(__file__).resolve().parent / "candidates"
META_HARNESS_PARENT = Path(__file__).resolve().parent.parent  # core/


def validate_h1(candidate_id: str) -> bool:
    """Check system_prompt.py exists and SYSTEM_PROMPT is a non-empty string."""
    cand_dir = CANDIDATES_DIR / candidate_id
    prompt_file = cand_dir / "system_prompt.py"
    if not prompt_file.exists():
        print(f"    MISSING: {prompt_file}")
        return False

    result = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, '{META_HARNESS_PARENT}'); "
            f"from meta_harness.candidates.{candidate_id}.system_prompt import SYSTEM_PROMPT; "
            f"assert isinstance(SYSTEM_PROMPT, str) and len(SYSTEM_PROMPT) > 50, 'SYSTEM_PROMPT too short or missing'",
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(META_HARNESS_PARENT),
    )
    if result.returncode != 0:
        print(f"    FAIL {candidate_id}: {result.stderr[:300]}")
        return False
    return True


def validate_h2(candidate_id: str) -> bool:
    """Check analyst_config.py + decider_prompt.py both import correctly."""
    cand_dir = CANDIDATES_DIR / candidate_id
    for fname in ["analyst_config.py", "decider_prompt.py"]:
        if not (cand_dir / fname).exists():
            print(f"    MISSING: {cand_dir / fname}")
            return False

    result = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, '{META_HARNESS_PARENT}'); "
            f"from meta_harness.candidates.{candidate_id}.analyst_config import ANALYST_CONFIG; "
            f"from meta_harness.candidates.{candidate_id}.decider_prompt import SYSTEM_PROMPT; "
            f"assert isinstance(SYSTEM_PROMPT, str) and len(SYSTEM_PROMPT) > 50, 'SYSTEM_PROMPT invalid'; "
            f"print('OK')",
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(META_HARNESS_PARENT),
    )
    if result.returncode != 0:
        print(f"    FAIL {candidate_id}: {result.stderr[:300]}")
        return False
    return True


def validate_h2x(candidate_id: str) -> bool:
    """Check all 4 files: analyst_config.py, decider_prompt.py, reviewer_prompt.py, memory_config.py."""
    cand_dir = CANDIDATES_DIR / candidate_id
    for fname in ["analyst_config.py", "decider_prompt.py", "reviewer_prompt.py", "memory_config.py"]:
        if not (cand_dir / fname).exists():
            print(f"    MISSING: {cand_dir / fname}")
            return False

    result = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, '{META_HARNESS_PARENT}'); "
            f"from meta_harness.candidates.{candidate_id}.analyst_config import ANALYST_CONFIG; "
            f"from meta_harness.candidates.{candidate_id}.decider_prompt import SYSTEM_PROMPT as DP; "
            f"from meta_harness.candidates.{candidate_id}.reviewer_prompt import SYSTEM_PROMPT as RP; "
            f"from meta_harness.candidates.{candidate_id}.memory_config import MEMORY_WINDOW; "
            f"assert isinstance(DP, str) and len(DP) > 50; "
            f"assert isinstance(RP, str) and len(RP) > 50; "
            f"assert isinstance(MEMORY_WINDOW, int) and 1 <= MEMORY_WINDOW <= 20; "
            f"print('OK')",
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(META_HARNESS_PARENT),
    )
    if result.returncode != 0:
        print(f"    FAIL {candidate_id}: {result.stderr[:300]}")
        return False
    return True


VALIDATORS = {
    "H1": validate_h1,
    "H2": validate_h2,
    "H2X": validate_h2x,
    "H2U": validate_h2x,  # H2U has same 4-file structure as H2X
}


def validate_candidates(candidates: List[dict], architecture: str) -> List[dict]:
    """Validate a batch of candidates for a given architecture.
    Returns only the valid ones.
    """
    validate_fn = VALIDATORS.get(architecture, validate_h1)
    valid = []
    for c in candidates:
        name = c.get("name", "unknown")
        if validate_fn(name):
            print(f"    OK {name}")
            valid.append(c)
        else:
            print(f"    REJECTED {name}")
    return valid
