"""Narrative script: H1→H2→H2X→H2M causal chain with all data.

Reads trace stores and prints the full causal story for NIO interview preparation.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Load all summaries
h1_base = json.load(open(BASE / "traces/trace_store/candidate_000/scores.json"))
h2_base = json.load(open(BASE / "traces/trace_store_h2/candidate_006/scores.json"))
h1_best_5 = json.load(open(BASE / "traces/trace_store/test_set_results.json"))
h1_best_10 = json.load(open(BASE / "traces/trace_store_h1_10nev/summary.json"))
h2_best_10 = json.load(open(BASE / "traces/trace_store_h2_10nev/summary.json"))
h2x_best_10 = json.load(open(BASE / "traces/trace_store_h2x_10inst/summary.json"))
h2m_best_10 = json.load(open(BASE / "traces/trace_store_h2m_10inst/summary.json"))

def nr(pct):
    """Format NR as percentage string."""
    return f"{pct*100:.2f}%"

def delta(a, b):
    d = b - a
    sign = "+" if d >= 0 else ""
    return f"{sign}{d*100:.1f}%"

print("=" * 75)
print("  H1 → H2 → H2X → H2M  因果链全景分析")
print("  NIO 新能源供应链 AI Agent 算法工程师面试准备")
print("=" * 75)

# ============================================================================
# CHAPTER 1: H1 BASELINE FAILURES
# ============================================================================
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ CHAPTER 1: H1 基线为何失败？                                              │
│ 单 Agent 系统提示词 = 计算 + 判断混在一起 → LLM 幻觉计算                    │
└─────────────────────────────────────────────────────────────────────────┘
""")

print(f"H1 基线 (candidate_000) 5-instance Mean NR: {nr(h1_base['mean_nr'])}")
print(f"\n  实例                        NR      问题描述")
print(f"  ──────────────────────────────────────────────────")
print(f"  p01_stationary_L0        {nr(0.8845)}   稳态需求，表现尚可")
print(f"  p04_increasing_trend_L0  {nr(0.8832)}   趋势需求，表现尚可")
print(f"  p08_changepoint_L0       {nr(0.8558)}   变点需求，表现尚可")
print(f"  p07_seasonal_L4          {nr(0.3964)}   ← L=4 季节性，灾难性失败")
print(f"  p06_variance_L4          {nr(0.2966)}   ← L=4 波动变化，灾难性失败")

print(f"""
关键发现：H1 基线在 L=4（长提前期）场景上崩溃。
  - p06 波动变化: NR={nr(0.2966)} — 几乎随机决策
  - p07 季节性:   NR={nr(0.3964)} — 无法捕捉周期模式

根因分析（从 H1 baseline traces 提取）：
  1. LLM 需要同时做计算（趋势检测、安全库存、OR对比）和判断（下多少单）
  2. 在 L=4 的复杂场景下，LLM 频繁算错 pipeline、OR 偏差百分比
  3. 一个错误计算 → 错误下单 → 下一期基于错误状态继续 → 级联失败
  4. 提示词里虽然写了公式，但 LLM 不是计算器——它"猜测"数字
""")

# ============================================================================
# CHAPTER 2: H1 OPTIMIZATION WORKS
# ============================================================================
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ CHAPTER 2: H1 优化有效，但有天花板                                          │
│ 提示词工程 = 把计算步骤显式化 → +5.6% 提升                                   │
└─────────────────────────────────────────────────────────────────────────┘
""")

print(f"H1 best (candidate_004) 5-instance Mean NR: {nr(h1_best_5['candidate_004_mean_nr'])}")
print(f"提升: {nr(h1_best_5['baseline_mean_nr'])} → {nr(h1_best_5['candidate_004_mean_nr'])} (Δ={delta(h1_best_5['baseline_mean_nr'], h1_best_5['candidate_004_mean_nr'])})")

print(f"\n  实例                       基线         004         提升")
print(f"  ──────────────────────────────────────────────────────")
for inst in h1_best_5['per_instance_baseline']:
    base_nr = h1_best_5['per_instance_baseline'][inst]
    best_nr = h1_best_5['per_instance_cand_004'][inst]
    print(f"  {inst:<25s} {nr(base_nr):>8s}   {nr(best_nr):>8s}   {delta(base_nr,best_nr):>8s}")

print(f"""
关键发现：
  1. H1 优化在 L=4 上效果显著：p01_stationary_L4 {nr(0.5166)}→{nr(0.6573)} (+{delta(0.5166,0.6573)})
  2. 但 L=4 的 NR 仍然偏低（0.65 vs L=0 的 0.88+）
  3. 提示词工程的本质：把"容易算错的东西"用自然语言约束住
  4. 问题：每换一个 demand pattern，提示词可能需要重新调整 → 脆弱

H1 的 10-instance NEV 评估（candidate_004）:
  Mean NR: {nr(h1_best_10['mean_nr'])}
  L=0 avg: 0.8883  |  L=4 avg: 0.5740
""")

# ============================================================================
# CHAPTER 3: H2 — 架构解决根本问题
# ============================================================================
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ CHAPTER 3: H2 — 架构层面消除 H1 的失败模式                                  │
│ Analyst(Python 计算) + Decider(LLM 判断) = 计算不再被幻觉污染               │
└─────────────────────────────────────────────────────────────────────────┘
""")

print(f"H2 基线 (candidate_006) 5-instance Mean NR: {nr(h2_base['mean_nr'])}")
print(f"相比 H1 基线: {nr(h1_base['mean_nr'])} → {nr(h2_base['mean_nr'])} (Δ={delta(h1_base['mean_nr'], h2_base['mean_nr'])})")

print(f"\n  L=4 实例对比（基线 vs 基线，无任何优化）：")
print(f"  实例                  H1基线       H2基线       提升")
print(f"  ──────────────────────────────────────────────────")
print(f"  p07_seasonal_L4       {nr(0.3964)}       {nr(0.5426)}       {delta(0.3964,0.5426)}")
print(f"  p06_variance_L4       {nr(0.2966)}       {nr(0.4777)}       {delta(0.2966,0.4777)}")

print(f"""
H2 架构设计（直接从 H1 失败分析中提取的 insights）：

  H1 失败模式                        →  H2 设计方案
  ─────────────────────────────────────────────────────────────
  1. LLM 算错 pipeline 状态          →  Python 精确计算 IP, B, pipe_status
     "IP = on_hand + sum(in_transit)  →  确定性代码，永不错误
     B = (L+1) * d_bar + safety"

  2. LLM 判断错需求趋势              →  Python 统计检验
     "trend is up" (but it's not)     →  线性回归 slope + R² + 证据期数
                                      →  trend_dir ∈ {{up,down,flat,volatile}}

  3. LLM 不知道该信 OR 还是信自己     →  Python 计算 trust 信号
     "OR seems wrong" (based on feel)  →  gap = (d_bar_emp - d_bar_or) / d_bar_or
                                      →  or_trust ∈ {{high,medium,low}}

  4. LLM 看不到决策后果              →  carry_over_insight 传递信息
     (blind to last period's outcome)  →  (但不完美——见 Chapter 4)

H2 的核心洞察：
  "LLM 擅长判断，不擅长计算。把计算还给代码，把判断留给 LLM。"
  这是真正的 Algorithm Engineer 思维——不是调参，是重新设计信息流。
""")

# After optimization
print(f"""H2 best (candidate_011) 10-instance NEV Mean NR: {nr(h2_best_10['mean_nr'])}
  vs H1 best (004): {nr(h1_best_10['mean_nr'])} (Δ={delta(h1_best_10['mean_nr'], h2_best_10['mean_nr'])})

  10-instance head-to-head: H1赢4场, H2赢5场, 平1场
  - L=0 场景: H1 优势 (4/6 获胜)
  - L=4 场景: H2 优势 (3/4 获胜) ← 复杂场景 H2 更强
""")

# ============================================================================
# CHAPTER 4: H2 → H2X — 信息架构升级
# ============================================================================
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ CHAPTER 4: H2 → H2X — 从"一句话"到"结构化记忆"                             │
│ H2 的 carry_over_insight 是单字符串 → 信息丢失 → 决策盲区                    │
└─────────────────────────────────────────────────────────────────────────┘
""")

print("""H2 carry_over_insight 的实际内容分析（来自 p06/p07 trace）：

  P14: "Up-trend signal from prior periods not confirmed by current flat trend"
  P17: "Flat trend persists with no evidence; continue monitoring"
  P18: "Flat trend persists with no evidence; continue monitoring"  ← 同一句话
  P19: "Flat trend persists with no evidence; continue monitoring"  ← 同一句话
  P20: "Flat trend persists with no evidence; continue monitoring"  ← 毫无增量信息

  P15: "Upward trend now has 3 periods evidence"     ← 说涨
  P16: "Downward trend now has 5 periods evidence"   ← 又说跌（自相矛盾）
  P17: "Downward trend... but not yet confirmed"      ← 不确定

H2 carry_over_insight 的三个结构性问题：
  1. 只传趋势判断，不传决策反馈
     → "我上期订了多少？卖了什么？赚了多少？"——这些信息根本没有
  2. 单字符串被每期覆盖 → 历史信息完全丢失
     → 无法回答："最近3期的 OR 偏差方向是什么？"
  3. 自然语言模糊 → "monitor" "persists" "not confirmed" = 没有可操作性
     → Decider 看到这些词等于没看到

H2X 的设计：结构化 Memory Buffer
  ┌─────────────────────────────────────────────────────┐
  │ PERIOD HISTORY (last 5):                            │
  │ P  | Dem | Ord | OR  | Sold | Rew  | Pipe     | Tr │
  │ 13 | 150 | 155 | 150 | 123  | +492 | ADEQUATE | fl │
  │ 14 | 124 | 130 | 131 | 100  | +400 | ADEQUATE | vo │
  │ 15 | 99  | 103 | 103 | 99   | +346 | ADEQUATE | fl │
  │ 16 | 58  | 100 | 95  | 58   | +167 | ADEQUATE | fl │
  │ 17 | 103 | 43  | 43  | 103  | +295 | ADEQUATE | vo │
  │                                                    │
  │ DRAFT ORDER: 101  |  OR REC: 95  |  RATIONALE: ... │
  └─────────────────────────────────────────────────────┘

  Decider 看到的不再是一句话，而是一张决策历史表。
  同时引入 Reviewer（四人原则）：检查明显错误后再执行。
""")

print(f"""H2X best (candidate_014) 10-instance Mean NR: {nr(h2x_best_10['mean_nr'])}
  vs H2: {nr(h2_best_10['mean_nr'])} (Δ={delta(h2_best_10['mean_nr'], h2x_best_10['mean_nr'])})
  vs H1: {nr(h1_best_10['mean_nr'])} (Δ={delta(h1_best_10['mean_nr'], h2x_best_10['mean_nr'])})
""")

# ============================================================================
# CHAPTER 5: H2X → H2M — 对话式 Multi-Agent
# ============================================================================
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ CHAPTER 5: H2X → H2M — 从单向审核到对话博弈                                │
│ Reviewer 不直接改单 → 给出 critique → Decider 有最终决定权（Last Word）      │
└─────────────────────────────────────────────────────────────────────────┘
""")

print("""H2X Review 是单向的：
  Decider → [draft order] → Reviewer → [approved/adjusted] → execute
  问题：Reviewer 可能理解错 Decider 的意图，或 Decider 的信息 Reviewer 看不到

H2M 是对话式的（3-round）：
  Round 1: Decider drafts → "基于历史表和分析报告，我建议订 95"
  Round 2: Reviewer critiques → "同意，但注意 pipeline UNDERFILLED，建议 +10%"
  Round 3: Decider revises/defends → "接受建议，最终订 105"

  Decider 拥有 Last Word —— 这符合企业现实：
  计划员提案 → 经理审核提意见 → 计划员最终决定并承担责任

  这不是"AI 替人决策"，而是"AI 辅助人做更好的决策"。
""")

print(f"""H2M best (candidate_016) 10-instance Mean NR: {nr(h2m_best_10['mean_nr'])}
  vs H2X: {nr(h2x_best_10['mean_nr'])} (Δ={delta(h2x_best_10['mean_nr'], h2m_best_10['mean_nr'])})
  vs H2:  {nr(h2_best_10['mean_nr'])} (Δ={delta(h2_best_10['mean_nr'], h2m_best_10['mean_nr'])})
  vs H1:  {nr(h1_best_10['mean_nr'])} (Δ={delta(h1_best_10['mean_nr'], h2m_best_10['mean_nr'])})
""")

# ============================================================================
# CHAPTER 6: FULL COMPARISON TABLE
# ============================================================================
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ CHAPTER 6: 10-Instance NEV Benchmark — 完整对比                           │
└─────────────────────────────────────────────────────────────────────────┘
""")

# Build comparison table
l0_insts_h1 = ["p01_标准件_稳态_L0","p02_新车上市_跃升_L0","p03_老车退市_下降_L0",
               "p04_市场增长_趋势_L0","p05_燃油车替代_下降_L0","p08_补贴退坡_变点_L0"]
l4_insts_h1 = ["p06_芯片短缺_波动_L4","p07_季度冲刺_季节_L4","p09_促销抢购_脉冲_L4","p10_电池排产_自相关_L4"]

# Map H2X/H2M keys back to H1/H2 keys
h2x_map = {
    "p01_stationary_L0":"p01_标准件_稳态_L0","p02_meanshift_up_L0":"p02_新车上市_跃升_L0",
    "p03_meanshift_down_L0":"p03_老车退市_下降_L0","p04_increasing_L0":"p04_市场增长_趋势_L0",
    "p05_decreasing_L0":"p05_燃油车替代_下降_L0","p08_changepoint_L0":"p08_补贴退坡_变点_L0",
    "p06_variance_L4":"p06_芯片短缺_波动_L4","p07_seasonal_L4":"p07_季度冲刺_季节_L4",
    "p09_tempsurge_L4":"p09_促销抢购_脉冲_L4","p10_autocorr_L4":"p10_电池排产_自相关_L4"
}

print(f"{'Instance':<25s} {'H1(004)':>8s} {'H2(011)':>8s} {'H2X(014)':>8s} {'H2M(016)':>8s} {'Best':>8s}")
print("-" * 75)

all_insts = l0_insts_h1 + l4_insts_h1
h1_l0_sum = h2_l0_sum = h2x_l0_sum = h2m_l0_sum = 0
h1_l4_sum = h2_l4_sum = h2x_l4_sum = h2m_l4_sum = 0

for inst in all_insts:
    h1v = h1_best_10["per_instance_nr"].get(inst, 0)
    h2v = h2_best_10["per_instance_nr"].get(inst, 0)

    # Find H2X/H2M key
    h2x_key = next((k for k,v in h2x_map.items() if v==inst), None)
    h2xv = h2x_best_10["per_instance_nr"].get(h2x_key, 0) if h2x_key else 0
    h2mv = h2m_best_10["per_instance_nr"].get(h2x_key, 0) if h2x_key else 0

    best = max(h1v, h2v, h2xv, h2mv)
    best_label = "H1" if best==h1v else ("H2" if best==h2v else ("H2X" if best==h2xv else "H2M"))

    is_l4 = inst in l4_insts_h1
    if is_l4:
        h1_l4_sum += h1v; h2_l4_sum += h2v; h2x_l4_sum += h2xv; h2m_l4_sum += h2mv
    else:
        h1_l0_sum += h1v; h2_l0_sum += h2v; h2x_l0_sum += h2xv; h2m_l0_sum += h2mv

    print(f"{inst:<25s} {nr(h1v):>8s} {nr(h2v):>8s} {nr(h2xv):>8s} {nr(h2mv):>8s} {best_label:>8s}")

# Averages
n_l0, n_l4 = len(l0_insts_h1), len(l4_insts_h1)
print("-" * 75)
print(f"{'L=0 avg ('+str(n_l0)+' inst)':<25s} {nr(h1_l0_sum/n_l0):>8s} {nr(h2_l0_sum/n_l0):>8s} {nr(h2x_l0_sum/n_l0):>8s} {nr(h2m_l0_sum/n_l0):>8s}")
print(f"{'L=4 avg ('+str(n_l4)+' inst)':<25s} {nr(h1_l4_sum/n_l4):>8s} {nr(h2_l4_sum/n_l4):>8s} {nr(h2x_l4_sum/n_l4):>8s} {nr(h2m_l4_sum/n_l4):>8s}")
print(f"{'MEAN NR':<25s} {nr(h1_best_10['mean_nr']):>8s} {nr(h2_best_10['mean_nr']):>8s} {nr(h2x_best_10['mean_nr']):>8s} {nr(h2m_best_10['mean_nr']):>8s}")

# ============================================================================
# CHAPTER 7: INTERVIEW NARRATIVE
# ============================================================================
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ CHAPTER 7: 面试叙事框架                                                    │
│ 这不是四个独立架构，而是一条因果链。每一步都是因为上一步的不足。              │
└─────────────────────────────────────────────────────────────────────────┘

面试自我介绍（2分钟版）：

  "我做了一个供应链 AI Agent 的元优化框架 Meta-Harness。
   核心问题是：如何让 LLM 在库存管理中做出正确的补货决策？

   第一版 H1 是单 Agent 系统提示词搜索。基线 NR 只有 66%，尤其在
   长提前期场景（L=4）上崩溃——季节性只拿到 39%，波动变化只拿到 29%。
   我分析 traces 发现 LLM 在'算数'——它把趋势检测、pipeline计算和下单
   判断混在一起，导致幻觉计算。

   第二版 H2 我做了一个架构决策：把计算和判断分离。Analyst 用
   确定性 Python 代码计算 pipeline 状态、趋势方向、OR 可信度，Decider
   只负责判断。这个改动让基线 NR 从 66% 直接跳到 73%（+9.8%），
   在 L=4 场景上：季节性 +36.9%，波动变化 +61.1%。没有任何优化。

   但 H2 的 carry_over_insight 是单字符串，信息在每个周期被覆盖。
   我看到 traces 里写着 'flat trend persists...monitor' 重复了5个周期
   毫无增量信息。Decider 看不到自己的决策后果。

   第三版 H2X 引入结构化 Memory Buffer——Decider 看到的不再是一句话，
   而是一张包含最近5期 demand/order/sold/reward/pipe 的历史表。
   同时引入 Reviewer（四人原则），在订单执行前做 sanity check。

   第四版 H2M 进一步把单向 review 变成对话博弈——Decider 提案，
   Reviewer 给 critique，Decider 有最终决定权。这更符合企业现实。

   最终在 10 个 NIO 新能源供应链场景上（涵盖标准件稳态、新车上市跃升、
   老车退市、市场增长、燃油车替代、芯片短缺、季度冲刺、补贴退坡、
   促销脉冲、电池排产自相关），四个架构的优化峰值都收敛到 ~76% NR。

   但这不是失败——这恰恰说明：架构决定的是 baseline（下限）和鲁棒性，
   不是 peak（上限）。H2 不需要任何优化就比 H1 基线高 10%。
   对于 NIO 这种供应链场景，鲁棒性比峰值性能更重要——你不能接受
   AI Agent 在某些零件上突然崩溃（NR=29%）。

   这套方法论的核心价值：
   1. 信息架构先于模型能力——先把计算做对，再谈判断质量
   2. 结构化记忆优于自然语言记忆——表格式 history > 一句话 insight
   3. 多角色协作优于单点决策——review 机制在关键决策场景不可或缺
   4. 搜索空间设计决定优化效率——H2 14个参数 5轮就能收敛"

为什么这个故事对 NIO 有吸引力：

  1. 新能源供应链 = 长提前期普遍（电池材料进口 4-8 周，芯片采购）
     → H2 在 L=4 上 +61% 的提升直接对应业务痛点

  2. NIO 是高端品牌 = 不能接受缺货
     → Reviewer 机制防止 Decider 在 UNDERFILLED 时错误地少下单

  3. 多车型多配置 = 需求模式多样化
     → 10个场景覆盖了稳态/跃升/下降/趋势/变点/季节/脉冲/波动/自相关
     → 直接映射到 NIO 的实际零件分类

  4. 算法工程师 JD = 不是调包侠，是架构设计
     → H1→H2 的计算/判断分离是真正的 Algorithm Engineering
     → prompt engineering + classical algorithm 的混合架构

  5. 成本意识
     → H2 每周期只需要 1 次 LLM 调用（H2M 2次，H2X 2次）
     → 对于每天需要为数万个 SKU 做决策的系统，成本差异显著
""")

# ============================================================================
# CHAPTER 8: KEY INSIGHT — ARCHITECTURE vs OPTIMIZATION
# ============================================================================
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ CHAPTER 8: 关键洞察 — 架构决定下限，优化决定上限                            │
└─────────────────────────────────────────────────────────────────────────┘

  Baseline (无优化)     Best (5轮搜索)      Δ (优化增益)
  ─────────────────────────────────────────────────────────
  H1:  66.3%            74.3% (5-inst)       +8.0%
  H2:  72.8%            74.0% (5-inst)       +1.2%
  H2X: 74.5%(估)        76.2% (10-inst)      +1.7%(估)
  H2M: 73.0%(估)        76.1% (10-inst)      +3.1%(估)

  解读：
  - H1 优化空间最大（+8.0%）但基线最低（66.3%）
  - H2 基线已经很高（72.8%），优化空间小（+1.2%）
  - 这说明 H2 的架构本身就解决了大部分问题
  - H2X/H2M 在 H2 基础上继续提升 baseline，但 peak 天花板相近

  面试话术：
  "如果面试官问我为什么不继续优化让 H2X 显著超越 H1——
   我会说：76% 的 NR 可能是单周期 LLM 决策在这个环境下的天花板。
   要突破这个天花板，需要的不是更好的 memory 或 reviewer，
   而是引入多步规划（multi-step lookahead）或 RL-based 决策策略。
   这是我知道的下一步方向，也恰好是 NIO 实际业务中需要的——"
""")

# Print full architecture comparison
print("""
┌─────────────────────────────────────────────────────────────────────────┐
│ APPENDIX: 四代架构对比                                                    │
└─────────────────────────────────────────────────────────────────────────┘

          H1           H2           H2X          H2M
  ─────────────────────────────────────────────────────────────
  Agent   1个          2个          3个          2个(对话)
  LLM/期  1次          1次          2次          2-3次
  Analyst 无           Python       Python       Python
  Memory  无           单字符串     结构化表      结构化表
  Review  无           无           单向审核      对话博弈
  LastWord Decider     Decider      Reviewer      Decider★
  L=0基线  0.87+       0.87+        0.87+         0.87+
  L=4基线  0.35(灾难)   0.51(可接受)  0.54          0.54
  10-NEV  76.26%      76.19%       76.16%        76.10%
  成本    最低         低           中             中高
  可解释性 差          好           很好           最好
""")
