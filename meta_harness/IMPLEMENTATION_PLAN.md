# Meta-Harness 自动化实现方案

## 总览

将当前 "你→Claude Code→Python" 的手动控制流，改造为 Stanford 论文的 "Python→Claude Code→Python" 自动化循环。

改动范围：4个 runner + 1个 config + 3个新文件。总代码量约 800 行新增，200 行修改。

---

## Step 0: 备份 (1 min)

```bash
cd /Users/junyaoyu/Downloads/oragent/core
cp -r meta_harness meta_harness_backup_$(date +%Y%m%d_%H%M%S)
```

---

## Step 1: 复制 claude_wrapper.py (10 min)

**文件**: `core/meta_harness/claude_wrapper.py`

直接从 Stanford `/tmp/meta-harness/reference_examples/text_classification/claude_wrapper.py` 复制，仅需修改两处：

1. `_EMPTY_PLUGIN_DIR` 的默认路径改为当前项目目录
2. 去掉末尾 `__main__` 测试代码（保留前 672 行）

无需改动核心逻辑 —— `build_command()`, `parse_stream_events()`, `run()`, `load_skills()`, `log_session()` 全部通用。

---

## Step 2: 写 SKILL.md (45 min)

**文件**: `core/meta_harness/.claude/skills/meta-harness-inventory/SKILL.md`

这是最关键的产物 —— Proposer 的行为规范说明书。按 Stanford 的 5 层结构写，但内容针对库存优化领域。

### 5 层结构设计

**L1: YAML frontmatter**
```yaml
---
name: meta-harness-inventory
description: Run one iteration of inventory optimization harness evolution.
---
```

**L2: CRITICAL CONSTRAINTS**
- 每轮 3 个 candidate（1 exploitation + 1 exploration + 1 hybrid）
- 禁止参数微调：如果 `SYSTEM_PROMPT` 仅改了数字 → 不合格
- 禁止数据集特定提示：不提 "p01_stationary", "p07_seasonal" 等实例名
- 允许提到通用模式：trend, seasonality, variance change 等
- 每个 candidate 必须对应一个 falsifiable hypothesis
- H1: 只改 `system_prompt.py` 中的 `SYSTEM_PROMPT` 字符串
- H2: 改 `analyst_config.py` + `decider_prompt.py`
- H2X: 改 `analyst_config.py` + `decider_prompt.py` + `reviewer_prompt.py` + `memory_config.py`

**L3: WORKFLOW (4步)**

Step 1 — Analyze:
- 读取 `evolution_summary.jsonl`（跑分历史）
- 读取 `frontier.json`（当前最佳 per-instance）
- 读取 worst instances 的 full trace（每周期 decision rationale）
- 提出 3 个 hypothesis，每个指向不同机制

Step 2 — Prototype:
- 写 `/tmp/` 脚本验证核心机制
- 从 `trace_store/` 拉真实数据测试
- 试 2-3 变体选最优

Step 3 — Implement:
- 复制当前最佳 candidate 目录 → 新 candidate 目录
- 按 hypothesis 修改对应文件
- 自检：和 base candidate 对比，verify 引入了全新机制而非参数微调

Step 4 — Write pending_eval.json:
```json
{
  "iteration": <N>,
  "architecture": "H1|H2|H2X",
  "candidates": [...]
}
```

**L4: File Format Contracts**

H1 candidate 结构：
```
candidates/candidate_XXX/
  system_prompt.py   # 定义 SYSTEM_PROMPT = """..."""
```

H2 candidate 结构：
```
candidates/candidate_XXX/
  analyst_config.py  # 定义 ANALYST_CONFIG = AnalystConfig(...)
  decider_prompt.py  # 定义 SYSTEM_PROMPT = """..."""
```

H2X candidate 结构：
```
candidates/candidate_XXX/
  analyst_config.py  # 同上
  decider_prompt.py  # 同上
  reviewer_prompt.py # 定义 SYSTEM_PROMPT = """..."""
  memory_config.py   # 定义 MEMORY_WINDOW = N
```

**L5: Trace Context Format**
- `evolution_summary.jsonl`: 每行一个 candidate 的跑分
- `trace_store/<candidate_id>/<instance_label>.json`: 每周期完整 decision rationale
- `proposer_context_iter<N>.txt`: 预格式化的分析文本（含 scoreboard + worst instance rationale）

---

## Step 3: 添加 Proposer 配置 (5 min)

**修改**: `core/meta_harness/config.py`

新增：
```python
# --- Claude Code Proposer Configuration ---
PROPOSER_MODEL = "opus"           # Claude model for proposal (NOT DeepSeek)
PROPOSER_TIMEOUT = 2400           # 40 min timeout for Claude Code subprocess
PROPOSER_SKILL = Path(__file__).resolve().parent / ".claude" / "skills" / "meta-harness-inventory"
PROPOSER_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Write", "Edit", "Bash"]

# --- Evolution Logging ---
EVOLUTION_LOG_DIR = Path(__file__).resolve().parent / "logs" / "evolution"
EVOLUTION_SUMMARY = EVOLUTION_LOG_DIR / "evolution_summary.jsonl"
PENDING_EVAL = EVOLUTION_LOG_DIR / "pending_eval.json"
```

---

## Step 4: 写 propose_claude() 核心函数 (30 min)

**新文件**: `core/meta_harness/proposer.py`

```python
"""
Proposer — calls Claude Code via subprocess to generate new harness candidates.
Replaces the manual "you tell Claude → Claude tells Python" loop.
"""
import json
import os
import time
from pathlib import Path
from .config import (
    PROPOSER_MODEL, PROPOSER_TIMEOUT, PROPOSER_SKILL,
    PROPOSER_ALLOWED_TOOLS, EVOLUTION_LOG_DIR,
    EVOLUTION_SUMMARY, PENDING_EVAL,
)
from . import claude_wrapper


def render_task_prompt(iteration: int, architecture: str, 
                       evolution_summary_path: Path,
                       pending_eval_path: Path) -> str:
    """Build the prompt string that tells Claude Code where everything is."""
    return (
        f"Run iteration {iteration} of the inventory optimization harness evolution.\n\n"
        f"## Architecture\n"
        f"Current architecture: **{architecture}**\n\n"
        f"## Run directories\n"
        f"- Evolution summary: `{evolution_summary_path}`\n"
        f"- Trace store: `trace_store/` (candidate subdirs with per-instance JSON traces)\n"
        f"- Candidates: `candidates/` (existing candidates to analyze)\n"
        f"- Config: `config.py` (holdout instances, N periods, etc.)\n"
        f"- Write pending_eval.json to: `{pending_eval_path}`\n\n"
        f"## Instructions\n"
        f"Read evolution_summary.jsonl and the worst-instance trace files, then "
        f"propose, implement, and validate 3 new candidates. Write the summary to "
        f"pending_eval.json when done."
    )


def propose_claude(iteration: int, architecture: str, 
                   trace_store_dir: Path,
                   timeout: int = None) -> bool:
    """
    Call Claude Code to propose new candidates.
    
    Returns True if pending_eval.json was produced, False otherwise.
    """
    if timeout is None:
        timeout = PROPOSER_TIMEOUT
    
    EVOLUTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Clean previous pending_eval
    if PENDING_EVAL.exists():
        PENDING_EVAL.unlink()
    
    task_prompt = render_task_prompt(
        iteration, architecture, EVOLUTION_SUMMARY, PENDING_EVAL
    )
    
    # Strip ANTHROPIC_API_KEY so claude CLI uses subscription auth
    saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    
    result = claude_wrapper.run(
        prompt=task_prompt,
        model=PROPOSER_MODEL,
        allowed_tools=PROPOSER_ALLOWED_TOOLS,
        skills=[str(PROPOSER_SKILL)],
        cwd=str(Path(__file__).resolve().parent),
        log_dir=str(EVOLUTION_LOG_DIR / "claude_sessions"),
        name=f"iter{iteration}",
        timeout_seconds=timeout,
        effort="max",
    )
    
    if saved_key:
        os.environ["ANTHROPIC_API_KEY"] = saved_key
    
    if result.exit_code != 0:
        print(f"  Proposer FAILED: exit={result.exit_code}")
        if result.stderr:
            print(f"  {result.stderr[:500]}")
        return False
    
    result.show()
    return PENDING_EVAL.exists()


def load_pending_candidates() -> list[dict]:
    """Read pending_eval.json. Returns list of candidate dicts."""
    if not PENDING_EVAL.exists():
        return []
    return json.loads(PENDING_EVAL.read_text()).get("candidates", [])
```

---

## Step 5: 写 Validator (15 min)

**新文件**: `core/meta_harness/validator.py`

```python
"""Validate candidates before benchmarking — catches import errors early."""
import subprocess
import sys
from pathlib import Path


CANDIDATES_DIR = Path(__file__).resolve().parent / "candidates"


def validate_h1(candidate_id: str) -> bool:
    """Check system_prompt.py imports and SYSTEM_PROMPT is a non-empty string."""
    cand_dir = CANDIDATES_DIR / candidate_id
    prompt_file = cand_dir / "system_prompt.py"
    if not prompt_file.exists():
        print(f"    MISSING: {prompt_file}")
        return False
    
    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{CANDIDATES_DIR.parent}'); "
         f"from meta_harness.candidates.{candidate_id}.system_prompt import SYSTEM_PROMPT; "
         f"assert isinstance(SYSTEM_PROMPT, str) and len(SYSTEM_PROMPT) > 50, 'Invalid prompt'"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"    FAIL {candidate_id}: {result.stderr[:200]}")
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
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{CANDIDATES_DIR.parent}'); "
         f"from meta_harness.candidates.{candidate_id} import analyst_config, decider_prompt; "
         f"assert hasattr(analyst_config, 'ANALYST_CONFIG'), 'Missing ANALYST_CONFIG'; "
         f"assert isinstance(decider_prompt.SYSTEM_PROMPT, str) and len(decider_prompt.SYSTEM_PROMPT) > 50"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"    FAIL {candidate_id}: {result.stderr[:200]}")
        return False
    return True


def validate_h2x(candidate_id: str) -> bool:
    """Check all 4 files import correctly."""
    cand_dir = CANDIDATES_DIR / candidate_id
    for fname in ["analyst_config.py", "decider_prompt.py", 
                  "reviewer_prompt.py", "memory_config.py"]:
        if not (cand_dir / fname).exists():
            print(f"    MISSING: {cand_dir / fname}")
            return False
    
    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{CANDIDATES_DIR.parent}'); "
         f"from meta_harness.candidates.{candidate_id} import analyst_config, decider_prompt, reviewer_prompt, memory_config; "
         f"assert hasattr(analyst_config, 'ANALYST_CONFIG'); "
         f"assert isinstance(decider_prompt.SYSTEM_PROMPT, str); "
         f"assert isinstance(reviewer_prompt.SYSTEM_PROMPT, str); "
         f"assert isinstance(memory_config.MEMORY_WINDOW, int)"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"    FAIL {candidate_id}: {result.stderr[:200]}")
        return False
    return True


VALIDATORS = {"H1": validate_h1, "H2": validate_h2, "H2X": validate_h2x}
```

---

## Step 6: 改造 Runner (10 min each = 40 min)

修改 4 个 runner，将 `_default_proposer()` 替换为 `propose_claude()` 调用。

### 6a: runner.py (H1)

```diff
-    def _default_proposer(self, context: str) -> str:
-        """..."""
-        # (25 lines of no-op code)
+    def _propose(self, iteration: int) -> list[dict]:
+        """Call Claude Code to propose new H1 candidates."""
+        from .proposer import propose_claude, load_pending_candidates
+        from .validator import validate_h1
+        
+        ok = propose_claude(iteration, "H1", self.trace_store.store_dir)
+        if not ok:
+            return []
+        candidates = load_pending_candidates()
+        return [c for c in candidates if validate_h1(c["name"])]
```

在 `run()` 中：
```diff
-            if proposer_func:
-                new_prompt = proposer_func(context)
-            else:
-                new_prompt = self._default_proposer(context)
-            cand_id = f"candidate_{iteration:03d}"
-            cand_dir.mkdir(parents=True, exist_ok=True)
-            prompt_file.write_text(...)
+            valid = self._propose(iteration)
+            if not valid:
+                print("  No valid candidates, skipping iteration")
+                continue
+            # Candidates already written by Claude Code to candidates/
+            # Just evaluate each one
```

### 6b: h2/h2_runner.py (H2)

同理，替换为 `_propose(iteration, "H2")`，validator 用 `validate_h2`。

### 6c: scripts/h2_chain_runner.py (H2 Chain)

同理，替换为 `_propose(iteration, "H2")`。

### 6d: scripts/h2x_chain_runner.py (H2X Chain)

同理，替换为 `_propose(iteration, "H2X")`，validator 用 `validate_h2x`。

---

## Step 7: 添加 evolution_summary.jsonl 更新逻辑 (15 min)

在 `proposer.py` 中添加：

```python
def update_evolution_summary(iteration: int, candidates: list[dict],
                              val_scores: dict, wall_time: float = None):
    """Append one JSONL row per candidate."""
    with open(EVOLUTION_SUMMARY, "a") as f:
        for c in candidates:
            name = c["name"]
            avg_nr = val_scores.get(name, 0)
            row = {
                "iteration": iteration,
                "candidate_id": name,
                "architecture": c.get("architecture", "H1"),
                "mean_nr": round(avg_nr, 4),
                "axis": c.get("axis", "?"),
                "hypothesis": c.get("hypothesis", ""),
            }
            f.write(json.dumps(row) + "\n")
```

每个 runner 在 evaluate 完所有 candidate 后调用此函数。

---

## Step 8: 集成测试 (15 min)

```bash
cd /Users/junyaoyu/Downloads/oragent/core

# Test 1: Claude wrapper smoke test
python -c "
from meta_harness import claude_wrapper
result = claude_wrapper.run(
    'Say hello and list the files in meta_harness/',
    allowed_tools=['Read', 'Glob', 'Grep'],
    cwd='.',
    timeout_seconds=120,
)
print(f'exit={result.exit_code}, text={result.text[:100]}')
"

# Test 2: Proposer dry run (H1, iteration 1)
python -c "
from meta_harness.proposer import propose_claude
ok = propose_claude(1, 'H1', trace_store_dir=...)
print(f'Proposer produced candidates: {ok}')
"

# Test 3: Full H1 loop (1 iteration)
python -m meta_harness.runner
```

---

## 时间估算

| Step | 内容 | 时间 | 依赖 |
|------|------|------|------|
| 0 | 备份 | 1 min | - |
| 1 | 复制 claude_wrapper.py | 10 min | - |
| 2 | 写 SKILL.md | **45 min** | - |
| 3 | 配置扩展 | 5 min | - |
| 4 | proposer.py | 30 min | 1, 2, 3 |
| 5 | validator.py | 15 min | - |
| 6a | 改造 runner.py | 10 min | 4, 5 |
| 6b | 改造 h2_runner.py | 10 min | 4, 5 |
| 6c | 改造 h2_chain_runner.py | 10 min | 4, 5 |
| 6d | 改造 h2x_chain_runner.py | 10 min | 4, 5 |
| 7 | evolution_summary 逻辑 | 15 min | 4 |
| 8 | 集成测试 | 15 min | all |
| **总计** | | **~2h 50min** | |

关键路径：Step 2 (SKILL.md) → Step 4 (proposer.py) → Step 6 (runner 改造) → Step 8 (测试)

SKILL.md 是最耗时的部分，因为需要把库存优化的领域知识（AnalystConfig 的阈值语义、NR 计算公式、trace 格式等）编码为 Proposer 的行为规范。

---

## 文件改动总结

| 文件 | 操作 | 行数 |
|------|------|------|
| `claude_wrapper.py` | 新增 | ~670 |
| `.claude/skills/meta-harness-inventory/SKILL.md` | 新增 | ~150 |
| `proposer.py` | 新增 | ~120 |
| `validator.py` | 新增 | ~80 |
| `config.py` | 修改 | +10 |
| `runner.py` | 修改 | ~40 (删除+替换) |
| `h2/h2_runner.py` | 修改 | ~40 |
| `scripts/h2_chain_runner.py` | 修改 | ~40 |
| `scripts/h2x_chain_runner.py` | 修改 | ~40 |
| **合计** | 8 新/改 | ~1190 |
