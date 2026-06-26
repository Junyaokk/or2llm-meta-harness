# OR→LLM 库存控制实验框架

> 论文 "AI Agents for Inventory Control" 复现 —— 固定提前期模式 (L=0, L=4)，DeepSeek Chat 作为 LLM 后端。

---

## 论文 → 代码映射

```
论文结构                             代码模块
─────────                           ────────
Section 3: Problem Formulation  →  env.py          (InventoryEnv, 状态转移)
Appendix A: OR Baseline         →  or_baseline.py  (Capped Base-stock Policy)
Appendix B: System Prompt       →  agent.py        (SYSTEM_PROMPT_TEMPLATE)
Section 3.1: LLM Agent Design   →  agent.py        (ORToLLMAgent, UserMessageBuilder)
Section 4: Experimental Setup   →  data.py         (InstanceLoader, InventoryBench 480实例)
Section 4.2: Evaluation Metrics →  data.py         (normalized_reward)
```

---

## 工程架构总图

```text
╔═══════════════════════════════════════════════════════════════════════╗
║                   OR→LLM 库存控制实验框架                              ║
║         论文 "AI Agents for Inventory Control" 复现                   ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  ┌─────────────────────────────────────────────────────────────┐     ║
║  │                     run.py  通用实验入口                      │     ║
║  │  python run.py --index <1-480> --periods <T> [--verbose]    │     ║
║  └─────┬──────────────┬────────────────────┬───────────────────┘     ║
║        │              │                    │                          ║
║        ▼              ▼                    ▼                          ║
║  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐           ║
║  │ 数据加载  │  │  库存环境     │  │  OR→LLM 智能体       │           ║
║  │ data.py  │  │  env.py      │  │  agent.py            │           ║
║  │          │  │              │  │                      │           ║
║  │Instance  │  │InventoryEnv  │  │ ORToLLMAgent         │           ║
║  │Loader    │  │              │  │  ├─ ORBaseline       │           ║
║  │          │  │ .step(q)     │  │  │  (or_baseline.py) │           ║
║  │.load()   │  │ .get_obs()   │  │  ├─ UserMsgBuilder   │           ║
║  │          │  │              │  │  ├─ DeepSeek API     │           ║
║  │normalized│  │InTransitOrder│  │  └─ ResponseParser   │           ║
║  │_reward() │  │PeriodResult  │  │                      │           ║
║  └─────┬────┘  └──────┬───────┘  └──────────┬───────────┘           ║
║        │              │                     │                        ║
║        │     ┌────────┴────────┐            │                        ║
║        │     │  每周期循环      │◀───────────┘                        ║
║        │     │                │                                      ║
║        │     │ ① obs = env.get_initial_observation()                 ║
║        │     │ ② q = agent.decide(obs, context)                      ║
║        │     │     ├─ or_rec = ORBaseline.compute(history, oh, it)   ║
║        │     │     ├─ msg = UserMessageBuilder.build(obs, or, ins)   ║
║        │     │     ├─ json = DeepSeek(messages=[sys, msg])           ║
║        │     │     └─ parsed = ResponseParser.parse(json, item_id)   ║
║        │     │ ③ result = env.step(q)                                ║
║        │     │     ├─ 下单: InTransitOrder(t, q, L)                  ║
║        │     │     ├─ 到货: arrived = sum(o for o if o.arrives@t)    ║
║        │     │     ├─ 销售: sold = min(d_t, on_hand)                 ║
║        │     │     └─ 结账: R = p·sold - h·end_inv                   ║
║        │     │ ④ obs = result["observation"]                         ║
║        │     │ ⑤ 如果 !done, goto ②                                  ║
║        │     └────────────────────────────┘                          ║
║        │                                                            ║
║        ▼                                                            ║
║  ┌──────────────────────────────────────────┐                       ║
║  │  评估输出                                │                       ║
║  │  NR = total_reward / (p × sum(demand))   │                       ║
║  │  → run_result_{index}.json               │                       ║
║  └──────────────────────────────────────────┘                       ║
║                                                                       ║
╠═══════════════════════════════════════════════════════════════════════╣
║  论文对照                                                             ║
╠═══════════════════════════════════════════════════════════════════════╣
║  §3  Problem Formulation     → env.py      InventoryEnv, step()     ║
║  §3.1 LLM Agent Design       → agent.py    ORToLLMAgent, decide()   ║
║  App A OR Baseline           → or_baseline.py ORBaseline.compute()  ║
║  App B System Prompt         → agent.py    SYSTEM_PROMPT_TEMPLATE   ║
║  §4   Experimental Setup     → data.py     InstanceLoader, 480实例  ║
║  §4.2 Evaluation             → data.py     normalized_reward()      ║
║  Fig 2 Agent Architecture    → 下图        每周期决策循环 A-B-C-D    ║
╚═══════════════════════════════════════════════════════════════════════╝
```

---

## 算法架构图（对齐论文 Figure 2）

```text
                   ┌──────────────────────────────┐
                   │   System Prompt (Appendix B)  │
                   │   p, h, L → q, z*, cap 公式    │
                   └──────────────┬───────────────┘
                                  │ 每周期注入
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Per-Period Agent Decision Loop (Fig. 2 in paper)              │
│                                                                 │
│  输入: Observation o_t                                          │
│       ├── on_hand_inventory                                    │
│       ├── in_transit_orders[]                                  │
│       ├── demand_history[]                                     │
│       └── last_period_conclude                                 │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Step A: OR Baseline (Appendix A)                     │      │
│  │   d̄ = mean(history)    s_d = std(history)           │      │
│  │   μ̂ = (1+L)·d̄          σ̂ = √(1+L)·s_d               │      │
│  │   B = μ̂ + z*·σ̂         z* = Φ⁻¹(p/(p+h))           │      │
│  │   cap = μ̂/(1+L) + Φ⁻¹(0.95)·σ̂/√(1+L)              │      │
│  │   q_or = max(0, min(B - IP, cap))                   │      │
│  └──────────────────────┬───────────────────────────────┘      │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Step B: User Message Assembly                        │      │
│  │   Part 1: carry_over_insights (跨期记忆)              │      │
│  │   Part 2: current observation                       │      │
│  │   Part 3: OR recommendation (全部统计量)              │      │
│  └──────────────────────┬───────────────────────────────┘      │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Step C: LLM Inference (DeepSeek Chat)                │      │
│  │   Input: system_prompt + user_message                │      │
│  │   Output: JSON {rationale, short_rationale,          │      │
│  │                 carry_over_insight, action}          │      │
│  │   Fallback: parse失败 → 使用 q_or                    │      │
│  └──────────────────────┬───────────────────────────────┘      │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Step D: State Transition (env.step)                  │      │
│  │   1. 订单登记 (InTransitOrder)                       │      │
│  │   2. 到货结算 (arrival_period == t 的订单到库)        │      │
│  │   3. 需求满足 (sold = min(d_t, on_hand))             │      │
│  │   4. 奖励计算 (R_t = p·sold - h·ending_inv)          │      │
│  │   5. 产出 o_{t+1}                                    │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                 │
│  输出: order_quantity q_t, next_observation o_{t+1}, reward R_t│
└─────────────────────────────────────────────────────────────────┘
```

---

## 各步骤输入输出详细清单（逐文件）

### `data.py` — 数据加载层

| 函数/类 | 输入 | 来源 | 输出 | 去向 |
|---------|------|------|------|------|
| `InstanceLoader(instance_dir)` | 目录路径 str | run.py CLI | loader 对象 | run.py |
| `.load()` | train.csv + test.csv | InventoryBench 文件系统 | `config` dict (9个字段) | run.py → env + agent 初始化 |
| `_read_csv(path)` | CSV 路径 (含 git-lfs header) | 同上 | pandas DataFrame | `.load()` 内部 |
| `normalized_reward(R, p, Σd)` | total_reward, p, total_demand | env + config | float ∈ [0,1] | 终端输出 + JSON |
| `build_instance_index(base_dir)` | benchmark 根目录 | 文件系统 | list[dict] (480条) | run.py --list |
| `run_single_instance(dir, model, periods)` | 实例目录 + model + 截断周期 | 外部调用 | dict (结果汇总) | save_results() |
| `save_results(results, path)` | 结果 dict + 输出路径 | 调用方 | JSON 文件 | 磁盘 |

### `env.py` — 库存环境层

| 方法 | 输入 | 来源 | 输出 | 去向 |
|------|------|------|------|------|
| `InventoryEnv.__init__` | demands[], L, p, h, initial_demands[] | InstanceLoader.load() | env 对象 (t=1, on_hand=0) | run.py |
| `get_initial_observation()` | 无 (读内部状态) | — | `obs` dict (7个字段) | agent.decide() |
| `step(q_t)` | 订货量 int | agent.decide() | `{period, reward, done, observation}` | run.py 主循环 |
| `_build_observation()` | 内部状态 (t, on_hand, in_transit, history) | env 自身 | `obs` dict | step() / get_initial_observation() |
| `critical_fractile` (property) | — | p, h | ρ = p/(p+h) | 仅展示 |

**`step()` 内部子步骤:**

| 子步骤 | 操作 | 影响的内部状态 |
|--------|------|---------------|
| ① 下单 | `InTransitOrder(period_placed=t, quantity=q, lead_time=L)` | `in_transit[]` append |
| ② 到货 | 遍历 `in_transit[]`, `arrival_period == t` 的加总 | `on_hand += arrivals`, 移除已到订单 |
| ③ 需求 | `sold = min(demands[t-1], on_hand)` | `on_hand -= sold` |
| ④ 结账 | `R = p*sold - h*ending_inv` | `total_reward += R`, `PeriodResult` 写入 `period_results[]` |
| ⑤ 记录 | `demand_history.append(d_t)` | `demand_history[]` 增长 |

### `or_baseline.py` — OR 基线层

| 方法 | 输入 | 来源 | 输出 | 去向 |
|------|------|------|------|------|
| `ORBaseline.__init__(L, p, h)` | L, p, h | config | `rho`, `z_star=Φ⁻¹(ρ)`, `z_cap=Φ⁻¹(0.95)` | agent 内部持有 |
| `.compute(demand_history, on_hand, in_transit_total)` | 历史需求 [], 在手库存, 在途总量 | obs dict | `ORRecommendation` (12字段) | agent.decide() → UserMessageBuilder + fallback |

**`compute()` 内部计算链:**

```text
demand_history[n]  ──▶  d̄ = mean, s_d = std(ddof=1)
                         │
                         ├──▶ μ̂ = (1+L)·d̄
                         ├──▶ σ̂ = √(1+L)·s_d
                         │
                         ├──▶ B = μ̂ + z*·σ̂
                         ├──▶ IP = on_hand + in_transit_total
                         ├──▶ cap = μ̂/(1+L) + z_cap·σ̂/√(1+L)
                         │
                         └──▶ q = max(0, min(B - IP, cap))
```

### `agent.py` — 智能体决策层

| 方法/类 | 输入 | 来源 | 输出 | 去向 |
|---------|------|------|------|------|
| `ORToLLMAgent.__init__` | item_id, L, p, h, model, api_key | config + 默认值 | agent (含 system_prompt, client, ORBaseline) | run.py |
| `_build_system_prompt()` | item_id, L, p, h (self) | `__init__` | 格式化的 System Prompt 字符串 | `_call_llm()` |
| `decide(obs, context)` | obs dict + SKU描述 | env.get_obs() + config | 订货量 int | env.step() |
| `_call_llm(user_msg, retries)` | user_message str | UserMessageBuilder | LLM JSON 字符串 | ResponseParser |
| `run_episode(env, context)` | env + context | 外部 | (orders[], total_reward, history[]) | run_single_instance() |

**`decide()` 内部子步骤:**

| 子步骤 | 方法/类 | 输入 | 输出 |
|--------|---------|------|------|
| OR推荐 | `ORBaseline.compute()` | demand_history, on_hand, in_transit_total | `ORRecommendation` |
| 消息构建 | `UserMessageBuilder.build()` | obs, or_rec, carry_over_insights, item_id, context | 3段式 user_message str |
| LLM调用 | `_call_llm()` | user_message | LLM JSON str |
| 解析 | `ResponseParser.parse()` | JSON str, item_id | `AgentResponse` |
| 容错 | try/except | 解析异常 | 降级为 `AgentResponse(q=or_rec.recommended_order)` |
| 更新洞察 | `carry_over_insights = parsed.carry_over_insight` | LLM洞察文本 | 下周期注入 |

**`UserMessageBuilder.build()` 输出结构:**

```text
Part 1 (有洞察时): ═══ CARRY-OVER INSIGHTS ═══
                   上次LLM发现的新趋势/变化

Part 2:             PERIOD 3 / 50
                    === CURRENT STATUS ===
                    Item: chips(Regular)
                    On-hand inventory: 50
                    In-transit orders (117 total):
                      Period 3: 117 units (lead_time=4, waited 1 periods)
                    === LAST PERIOD CONCLUDE ===
                    Period 2 conclude: ordered=120, arrived=0, ...
                    Recent demand history (last 10 periods): [...]
                    All demand history (12 periods): [...]

Part 3:             ═══ OR ALGORITHM RECOMMENDATIONS ═══
                    Demand mean (d_bar): 100.0
                    Demand std (s_d): 15.0
                    ...
                    OR recommended order: 73
```

**`AgentResponse` 字段:**

| 字段 | 类型 | 说明 |
|------|------|------|
| `rationale` | str | LLM 完整推理过程 |
| `short_rationale_for_human` | str | 1-3句摘要 (日志展示用) |
| `carry_over_insight` | str | 跨期洞察 (空串="无新发现") |
| `order_quantity` | int | 最终订货决策 |
| `raw_json` | dict | LLM 原始 JSON (调试用) |

---

## 论文公式 → 代码映射

| 论文符号 | 含义 | 代码变量 | 所在位置 |
|---------|------|---------|---------|
| L | 固定提前期 | `lead_time` | `InventoryEnv.__init__` |
| p | 单位销售利润 | `p` | `InventoryEnv.__init__` |
| h | 单位持货成本 | `h` | `InventoryEnv.__init__` |
| ρ = p/(p+h) | 关键分位数 | `critical_fractile` / `rho` | `InventoryEnv` property / `ORBaseline.__init__` |
| z* = Φ⁻¹(ρ) | 安全因子 | `z_star` | `ORBaseline.__init__` |
| d̄ | 需求样本均值 | `d_bar` | `ORBaseline.compute()` |
| s_d | 需求样本标准差 | `s_d` | `ORBaseline.compute()` |
| μ̂ = (1+L)·d̄ | 提前期内需求均值 | `mu_hat` | `ORBaseline.compute()` |
| σ̂ = √(1+L)·s_d | 提前期内需求标准差 | `sigma_hat` | `ORBaseline.compute()` |
| B = μ̂ + z*·σ̂ | 基准库存水平 | `base_stock_level` / `B` | `ORBaseline.compute()` |
| IP = on_hand + pipeline | 库存位置 | `inventory_position` / `IP` | `ORBaseline.compute()` |
| cap | 订货上限 | `order_cap` / `cap` | `ORBaseline.compute()` |
| q_t | 决策订货量 | `recommended_order` / `order_quantity` | `ORRecommendation` / `AgentResponse` |
| R_t = p·sold - h·end_inv | 单期奖励 | `daily_reward` | `PeriodResult` |
| NR = ΣR_t / (p·Σd_t) | 归一化奖励 | `normalized_reward()` | `data.py` |

---

## 快速开始

### 环境依赖

```bash
pip install numpy pandas scipy openai
```

### 数据准备

```bash
# 克隆 InventoryBench 数据集 (含 Git LFS)
git clone git@github.com:TianyiPeng/InventoryBench.git InventoryBench-main
cd InventoryBench-main
git sparse-checkout set benchmark/synthetic_trajectory/lead_time_0 benchmark/synthetic_trajectory/lead_time_4
git lfs pull
```

### 运行

```bash
# 列出所有 480 个实例
python run.py --list

# 运行单个实例 (默认 50 周期)
python run.py --index 1

# 指定周期数 + 详细输出
python run.py --index 1 --periods 30 -v

# 指定输出文件
python run.py --index 1 --output results/exp_001.json

# 全链路追踪 (Step A/B/C/D 详细日志)
python run.py --index 1 --periods 20 --trace --trace-file trace.log

# 生成交互式 Dashboard (Plotly HTML)
python run.py --index 1 --periods 30 --plot

# 追踪 + Dashboard + 报告 同时使用
python run.py --index 1 --periods 30 --trace --plot --report
```

### 输出文件说明

| 参数 | 输出文件 | 用途 |
|------|---------|------|
| `--trace --trace-file FILE` | `.log` 文本 | Step A/B/C/D 全链路决策追踪 |
| `--plot` | `dashboard_<N>.html` | 交互式 Plotly 图表 + 算法公式(MathJax渲染) |
| `--report` | `report_<N>.md` | Markdown 报告：LaTeX公式 + 逐期决策表 + 推理时间线 + OR参数演化 |
| 默认 | `run_result_<N>.json` | 结构化 JSON 结果数据 |

### Dashboard 图表说明

`--plot` 生成一个自包含的 Plotly HTML 交互式 Dashboard，包含 4 张图表：

| # | 图表 | 交互方式 | 面试展示要点 |
|---|------|---------|------------|
| 1 | **决策对比图** | hover 查看数值 | LLM vs OR 下单量对比，Δ 柱标出覆盖方向 |
| 2 | **库存水位图** | hover 查看数值 | 在库 + 到货 vs 需求，红色 X 标记断货点 |
| 3 | **累计收益曲线** | hover 查看数值 | 累计 + 逐期收益，断货点 ⚠️ 标注 |
| 4 | **推理洞察时间线** | hover 看 LLM 推理 | 蓝点=LLM决策理由，金色星=跨期洞察生成 |

Dashboard 头部显示 6 个 KPI：Total Reward / Normalized / Periods / LLM Overrides OR / Stockouts / Insights

### 程序化调用

```python
from or_to_llm import InstanceLoader, InventoryEnv, ORToLLMAgent, normalized_reward

loader = InstanceLoader("InventoryBench-main/benchmark/synthetic_trajectory/lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_low")
config = loader.load()

env = InventoryEnv(
    demands=config["test_demands"][:50],
    lead_time=config["lead_time"],
    p=config["p"],
    h=config["h"],
    initial_demands=config["initial_demands"],
)

agent = ORToLLMAgent(
    item_id=config["item_id"],
    anticipated_lead_time=config["lead_time"],
    p=config["p"],
    h=config["h"],
)

orders, total_reward, history = agent.run_episode(env, context=config["description"])
nr = normalized_reward(total_reward, p=config["p"], total_demand=sum(config["test_demands"][:50]))
print(f"Normalized Reward: {nr:.4f}")
```

---

## 项目文件清单

```
nio/
├── run.py                      # 通用 CLI 实验脚本
├── README.md                   # 本文档
├── readme_index.md             # README 方案草稿 (可删除)
├── or_to_llm/                  # 核心包
│   ├── __init__.py             # 聚合导出
│   ├── env.py                  # 库存环境 (InventoryEnv, InTransitOrder, PeriodResult)
│   ├── or_baseline.py          # OR 基线策略 (ORBaseline, ORRecommendation)
│   ├── agent.py                # LLM 智能体 (ORToLLMAgent, System Prompt, ResponseParser)
│   └── data.py                 # 数据加载与评估 (InstanceLoader, normalized_reward)
└── InventoryBench-main/        # 数据集 (git clone 后生成)
    └── benchmark/synthetic_trajectory/
        ├── lead_time_0/        # L=0: 240 个实例
        └── lead_time_4/        # L=4: 240 个实例
```

---

## FAQ

**Q: 为什么只支持 L=0 和 L=4？**
论文中大多数实验使用这两个固定提前期。随机提前期 (lead_time_stochastic) 暂未适配。

**Q: 数据集的 480 个实例如何构成？**
10 种需求模式 × 4 种变体 × 3 种关键分位数 (ρ) × 2 次随机实现 × 2 种提前期 = 480。

**Q: LLM 调用失败怎么办？**
解析失败时自动降级为 OR 基线的推荐量。网络错误重试 3 次，间隔 5/10/15 秒。

**Q: 如何切换模型？**
`python run.py --index 1 --model deepseek-chat`。只要是 OpenAI-compatible API 即可。
