# H2U 统一架构 — 实现方案

## 动机：为什么需要 H2U

H2 和 H2X 目前各自独立进化，改进互不共享：

```
H2:  Analyst → Decider (carry_over string) → env.step
     进化了: analyst_config 阈值 + decider 5步决策树       (candidate_006~017)

H2X: Analyst → MemoryBuffer → Decider → Reviewer → env.step
     进化了: reviewer 审查策略 + memory_window 大小         (candidate_h2x_000~001)
```

**断层**：H2 优化的 5 步决策树从未在 Memory+Reviewer 框架下运行过。H2X 优化的 Reviewer 从未见过 H2 的完整决策树。两组搜索各自为战，无法实现组合增益。

**H2U 的目标**：跨架构杂交育种。取 H2 最优 Decider + H2X 最优 Memory/Reviewer + H2 最优 AnalystConfig → 一个基线更强的统一架构 → 再次进化。

---

## 架构设计

```
H2U: Analyst → MemoryBuffer → Decider → Reviewer → env.step
       |            |            |           |
       v            v            v           v
  AnalystConfig  MEMORY_WINDOW  SYSTEM_PROMPT  SYSTEM_PROMPT
  (15个参数)     (int)          (5步决策树)    (审查规则)
```

### 与 H2X 的关键差异

| 维度 | H2X | H2U |
|------|-----|-----|
| Decider 起点 | 4步简化决策树 | **H2 5步完整决策树** (TRUST→TREND→VARIANCE/MEAN→PIPELINE→FINAL) |
| Memory 给 Decider | `memory.render_for_decider()` 结构表 | 同 H2X（不改） |
| Reviewer 给 Reviewer | 基础上下文 | **增强为 Analyst 信号感知**：看到 pipeline/trend/or_trust |
| AnalystConfig | 默认阈值 | **H2 最优阈值** (来自 candidate_006) |
| 进化焦点 | 各自独立 | **四文件联合进化** |

### 数据流（单周期）

```
1. ORBaseline.compute(demand_history, on_hand, in_transit)
   → or_rec (recommended_order, order_cap, B, z*)

2. Analyst.analyze(obs, or_rec)
   → report (pipeline: OVERFILLED/ADEQUATE/UNDERFILLED,
              demand: trend_dir, gap_pct, CV,
              or_audit: trust_level, bias,
              alerts: anomaly flags)

3. MemoryBuffer.render_for_decider()
   → memory_table (结构化的历史表：P,Dem,Ord,OR,Sold,Rew,Dev,Pipe,Trend,Trust)

4. Decider.decide(analyst_report + memory_table, or_rec)
   → draft_order + rationale + carry_over_insight
   使用 H2 5步决策树: TRUST→TREND→VARIANCE/MEAN→PIPELINE→FINAL

5. Reviewer.review(analyst_report + memory_for_reviewer, draft)
   → 批准 或 ±30% 调整，risk_flag: safe/caution/override

6. env.step(final_order)
   → reward, next_obs

7. MemoryBuffer.add(period_outcome)
   → 更新滑动窗口 (含 analyst 信号)
```

---

## Baseline 组合策略

### 文件来源

| 文件 | 来源 | 理由 |
|------|------|------|
| `analyst_config.py` | H2 candidate_006 | H2 搜索验证过的最优 Analyst 阈值组合 |
| `decider_prompt.py` | H2 candidate_006 | H2 5步决策树 + "Analyst signals are FACTUAL" 原则 |
| `reviewer_prompt.py` | H2X candidate_h2x_000 | 基础 Reviewer + 增强 Analyst 信号感知 |
| `memory_config.py` | H2X candidate_h2x_000 | MEMORY_WINDOW=5（通过 H2X 验证） |

### Decider Prompt 适配

H2 candidate_006 的 Decider 使用单字符串 `carry_over_insights`。在 H2U 中需要适配为接收 Memory 结构表：

**H2 原文 (candidate_006)**:
```
**Analyst signals are FACTUAL — trust them:**
- Pipeline: IP, B, pipe_status (UNDERFILLED/ADEQUATE/OVERFILLED)
- Demand: trend_dir, gap_vs_d_bar, volatility (CV), evidence count
- OR Audit: or_trust (high/medium/low), bias direction
- Alerts: anomaly flags
```

**H2U 适配版**:
```
**Analyst signals are FACTUAL — trust them:**
- Pipeline: IP, B, pipe_status (UNDERFILLED/ADEQUATE/OVERFILLED) ← COMPUTED, never wrong
- Demand: trend_dir, gap_pct, CV, evidence count
- OR Audit: trust_level, bias direction
- Alerts: anomaly flags

**Period History (structured memory):**
{memory_table}  ← 插入 MemoryBuffer 的结构化历史表

**Decision tree (5 steps):** ← 保留 H2 完整决策树
STEP 1: TRUST vs SHIFT (gap_pct < 15% + or_trust → TRUST OR)
STEP 2: TREND direction (trend_dir + evidence >= 4)
STEP 3: VARIANCE vs MEAN (high CV + flat → VARIANCE; sustained direction → MEAN SHIFT)
STEP 4: PIPELINE check (OVERFILLED→0, ADEQUATE→room, UNDERFILLED→cap)
STEP 5: FINAL quantity (integer, 0 ≤ q ≤ cap)
```

### Reviewer Prompt 增强

H2X reviewer 目前看不到 Analyst 信号。H2U 增强版：

**H2X 原文**: 只看 draft_order + rationale + history 表

**H2U 增强**: 增加 Pipeline + Trend 信号输入
```
**Analyst signals (for cross-check):**
- Pipeline: {pipe_status}, IP={ip}, B={B}
- Trend: {trend_dir}, gap={gap_pct}%
- OR trust: {trust_level}

→ Reviewer 可以判断 "Decider 在 OVERFILLED 时大量下单" 这类基础错误
```

---

## 文件结构

```
core/meta_harness/h2u/
├── __init__.py              # 空
├── h2u_evaluator.py         # 新：H2U 评估器
├── h2u_runner.py            # 新：H2U Meta-Harness Runner

core/meta_harness/candidates/
└── candidate_h2u_000/       # 新：H2U baseline
    ├── analyst_config.py    # 从 candidate_006 复制
    ├── decider_prompt.py    # H2 5步决策树 + Memory 适配
    ├── reviewer_prompt.py   # H2X Reviewer + Analyst 信号感知
    └── memory_config.py     # MEMORY_WINDOW = 5
```

### 需要修改的已有文件

| 文件 | 修改 |
|------|------|
| `config.py` | +H2U_N_ITERATIONS, +H2U_TRACE_STORE_DIR |
| `.claude/skills/meta-harness-inventory/SKILL.md` | +H2U 架构在 Architecture File Formats 章节 |
| `validator.py` | +validate_h2u() → 校验 4 个文件 |

---

## Evaluator 设计 (h2u_evaluator.py)

核心差异点（相对 H2X Evaluator）：

### H2X 的 Decider 输入
```python
# H2X: analyst report + memory table 混合传给 Decider
report_text = analyst.render_for_decider(report, obs, or_rec, item_id, 
                                          carry_over=memory_table)
response = decider.decide(report_text, or_rec.recommended_order)
```

### H2U 的 Decider 输入
```python
# H2U: 分离 Analyst 信号和 Memory 表，Decider 各自独立接收
analyst_text = analyst.render_for_decider(report, obs, or_rec, item_id, carry_over="")
memory_table = memory.render_for_decider()

# H2U 的 Decider prompt 中有 {memory_table} 占位符
# evaluator 做 format() 注入
decider_prompt_filled = self.decider_prompt_template.format(
    item_id=item_id,
    anticipated_lead_time=lead_time,
    p=p, h=h,
    critical_fractile=...,
    z_star=...,
    memory_table=memory_table,    # ← H2U 新增
)
response = decider.decide_with_filled_prompt(
    analyst_text, decider_prompt_filled, or_rec)
```

### H2U 的 Reviewer 输入
```python
# H2U: Reviewer 接收 Analyst 信号摘要用于交叉验证
review_decision = reviewer.review_with_analyst_signals(
    analyst_signals={
        "pipe_status": report.pipeline["pipe_status"],
        "ip": report.pipeline["ip"],
        "B": report.pipeline["B"],
        "trend_dir": report.demand["trend_dir"],
        "gap_pct": report.demand["gap_pct"],
        "trust_level": report.or_audit["trust_level"],
    },
    memory_table=memory.render_for_reviewer(draft_order, rationale),
    draft_order=draft_order,
    draft_rationale=rationale,
    or_recommended=or_rec.recommended_order,
)
```

---

## H2U Meta-Harness 进化策略

### Claude Code Proposer 搜索空间

| 文件 | 可修改内容 | 示例 hypothesis |
|------|-----------|----------------|
| `analyst_config.py` | 阈值 + 新模块 | "降低 trend_evidence_periods 从 4→3 可加速趋势检测，但增加误报" |
| `decider_prompt.py` | 决策树结构 + 阈值 + 推理逻辑 | "在 STEP 3 后增加 SEASONALITY_CHECK 步骤，减少季节性误判" |
| `reviewer_prompt.py` | 审查规则 + 调整幅度 + 批准条件 | "Reviewer 对比 Analyst signals 和 Decider rationale 的一致性" |
| `memory_config.py` | 窗口大小 + 存储内容 | "MEMORY_WINDOW 从 5 增加到 7，给 Decider 更长的趋势视野" |

### 反参数微调规则（同 SKILL.md）
- 如果某次 evolution 只改了 `pipe_overfill_ratio: 1.0 → 1.1` → 参数微调 → 拒绝
- 如果某次 evolution 在 decider_prompt 中增加了新的决策分支 + 调整了对应阈值 → 机制变化 → 接受

---

## 实施步骤

| Step | 内容 | 时间 | 依赖 |
|------|------|------|------|
| 1 | 创建 `candidate_h2u_000/` 基线 (4文件) | 45min | - |
| 2 | H2 Decider 适配 Memory table 格式 | 30min | 1 |
| 3 | H2X Reviewer 增强 Analyst 信号感知 | 20min | 1 |
| 4 | 写 `h2u/h2u_evaluator.py` (280行) | 30min | 2,3 |
| 5 | 写 `h2u/h2u_runner.py` (200行) | 20min | 4 |
| 6 | 改 `config.py` + `validator.py` + `SKILL.md` | 15min | 5 |
| 7 | 单实例 smoke test | 15min | 6 |
| **合计** | | **~2h 45min** | |

---

## 预期收益

1. **H2U baseline 应该优于 H2 best 和 H2X best**——因为它同时拥有两者的改进
2. **H2U 的进化潜力更大**——四文件联合搜索比各自独立搜索的覆盖度更大
3. **Reviewer 的 Analyst 信号感知减少了基础错误**（如 OVERFILLED + 大量下单这类矛盾）
4. **Memory 结构表给了 5 步决策树跨周期视野**——H2 Decider 之前只能靠单一 carry_over 字符串

---

## 风险和注意事项

1. **H2 5步决策树是围绕 Analyst 信号设计的**——加入 Memory 表后，Decider 可能过度依赖历史模式而忽略当前信号。需要在 prompt 中明确优先级：Analyst signals > Memory table。
2. **Reviewer 增加输入可能增加犹豫**——pipeline OVERFILLED + trend UP 的冲突场景下，Reviewer 需要更明确的优先级规则。
3. **两次 LLM 调用（Decider + Reviewer）延迟翻倍**——每个周期 ~4s vs H2 的 ~2s。但 H2X 已经承担了这个成本，不是新问题。
