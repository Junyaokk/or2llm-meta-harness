"""
Compare H1(004) vs H2(000) per-period decisions on p04 to find divergence.
Saves complete traces for analysis.
"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from or_to_llm import InventoryEnv, InstanceLoader, normalized_reward
from or_to_llm.or_baseline import ORBaseline
from meta_harness.h2.analyst import Analyst
from meta_harness.h2.decider import Decider

# Load H1(004) prompt
from meta_harness.candidates.candidate_004.system_prompt import SYSTEM_PROMPT as H1_PROMPT
# Load H2(000) config and prompt
from meta_harness.candidates.candidate_h2_000.analyst_config import ANALYST_CONFIG
from meta_harness.candidates.candidate_h2_000.decider_prompt import SYSTEM_PROMPT as H2_PROMPT

# Also run baseline H1(000) for comparison
from or_to_llm.agent import SYSTEM_PROMPT_TEMPLATE as H1_BASELINE_PROMPT

inst_dir = Path(__file__).resolve().parent.parent / "InventoryBench-main" / "benchmark" / \
           "synthetic_trajectory" / "lead_time_0" / "p04_increasing_trend" / \
           "v1_linear_100t" / "r1_med"

def run_h1(prompt_template):
    """Run H1 agent with given prompt on p04."""
    loader = InstanceLoader(str(inst_dir))
    config = loader.load()
    demands = config["test_demands"][:20]
    env = InventoryEnv(
        demands=demands, lead_time=config["lead_time"],
        p=config["p"], h=config["h"],
        initial_demands=config["initial_demands"],
    )
    or_bl = ORBaseline(config["lead_time"], config["p"], config["h"])
    from openai import OpenAI
    rho = config["p"] / (config["p"] + config["h"])
    from scipy.stats import norm
    z_star = float(norm.ppf(rho))
    system_prompt = prompt_template.format(
        item_id=config["item_id"], anticipated_lead_time=config["lead_time"],
        p=config["p"], h=config["h"], critical_fractile=rho, z_star=z_star,
    )
    client = OpenAI(api_key=os.getenv("EVAL_API_KEY", ""),
                    base_url="https://api.deepseek.com/v1", timeout=180.0, max_retries=2)
    from or_to_llm.agent import UserMessageBuilder, ResponseParser
    carry_over = ""
    decisions = []
    obs = env.get_initial_observation()
    while not env.done:
        or_rec = or_bl.compute(demand_history=obs["demand_history"],
                               on_hand=obs.get("on_hand_inventory", 0),
                               in_transit_total=obs.get("in_transit_total", 0))
        user_msg = UserMessageBuilder.build(obs=obs, or_rec=or_rec,
                                            carry_over_insights=carry_over,
                                            item_id=config["item_id"],
                                            context=config.get("description", ""))
        resp = client.chat.completions.create(
            model="deepseek-chat", temperature=0.0, max_tokens=4096,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_msg}],
        )
        parsed = ResponseParser.parse(resp.choices[0].message.content, config["item_id"])
        q = parsed.order_quantity
        carry_over = parsed.carry_over_insight if parsed.carry_over_insight else ""
        pre_demand = env.demands[env.t-1] if env.t <= len(env.demands) else 0
        decisions.append({"period": env.t, "demand": pre_demand,
                          "or_q": or_rec.recommended_order, "llm_q": q,
                          "rationale": parsed.rationale[:150]})
        result = env.step(q)
        obs = result["observation"]
    nr = normalized_reward(env.total_reward, p=config["p"], total_demand=sum(demands))
    return nr, decisions, env.total_reward

def run_h2():
    """Run H2(000) on p04."""
    loader = InstanceLoader(str(inst_dir))
    config = loader.load()
    demands = config["test_demands"][:20]
    env = InventoryEnv(
        demands=demands, lead_time=config["lead_time"],
        p=config["p"], h=config["h"],
        initial_demands=config["initial_demands"],
    )
    analyst = Analyst(config=ANALYST_CONFIG)
    or_bl = ORBaseline(config["lead_time"], config["p"], config["h"])
    decider = Decider(
        item_id=config["item_id"], system_prompt_template=H2_PROMPT,
        model="deepseek-chat", api_key=os.getenv("EVAL_API_KEY", ""),
        base_url="https://api.deepseek.com/v1",
        anticipated_lead_time=config["lead_time"], p=config["p"], h=config["h"],
    )
    decisions = []
    obs = env.get_initial_observation()
    while not env.done:
        or_rec = or_bl.compute(demand_history=obs["demand_history"],
                               on_hand=obs.get("on_hand_inventory", 0),
                               in_transit_total=obs.get("in_transit_total", 0))
        obs["lead_time"] = config["lead_time"]
        obs["p"] = config["p"]
        obs["h"] = config["h"]
        obs["context"] = config.get("description", "")
        report = analyst.analyze(obs, or_rec, item_id=config["item_id"],
                                 context=config.get("description", ""))
        report_text = analyst.render_for_decider(report, obs, or_rec,
                                                  config["item_id"],
                                                  carry_over=decider.carry_over_insights)
        resp = decider.decide(report_text, or_rec.recommended_order)
        q = resp.order_quantity
        pre_demand = env.demands[env.t-1] if env.t <= len(env.demands) else 0
        decisions.append({"period": env.t, "demand": pre_demand,
                          "or_q": or_rec.recommended_order, "llm_q": q,
                          "rationale": resp.rationale[:150],
                          "trend": report.demand.get("trend_dir"),
                          "gap": report.demand.get("gap_pct"),
                          "pipe": report.pipeline.get("pipe_status"),
                          "trust": report.or_audit.get("trust_level")})
        result = env.step(q)
        obs = result["observation"]
    nr = normalized_reward(env.total_reward, p=config["p"], total_demand=sum(demands))
    return nr, decisions, env.total_reward

print("Running H1(004) on p04...")
h1_nr, h1_decisions, h1_reward = run_h1(H1_PROMPT)
print(f"H1(004) NR={h1_nr:.4f} Reward={h1_reward:.0f}")

print("\nRunning H2(000) on p04...")
h2_nr, h2_decisions, h2_reward = run_h2()
print(f"H2(000) NR={h2_nr:.4f} Reward={h2_reward:.0f}")

print(f"\n{'='*80}")
print(f"{'P':<4} {'Dem':<6} {'H1(004)':<8} {'H2(000)':<8} {'OR':<8} {'H1 dev':<8} {'H2 dev':<8} {'H2 sig'}")
print(f"{'-'*80}")
for h1d, h2d in zip(h1_decisions, h2_decisions):
    h1_dev = h1d['llm_q'] - h1d['or_q']
    h2_dev = h2d['llm_q'] - h2d['or_q']
    h1_s = f"{'+' if h1_dev>=0 else ''}{h1_dev}" if h1_dev != 0 else "0"
    h2_s = f"{'+' if h2_dev>=0 else ''}{h2_dev}" if h2_dev != 0 else "0"
    sig = f"{h2d.get('trend','?')}/{h2d.get('pipe','?')[:4]}/T{h2d.get('trust','?')[:4]}"
    print(f"{h1d['period']:<4} {h1d['demand']:<6} {h1d['llm_q']:<8} {h2d['llm_q']:<8} {h1d['or_q']:<8} {h1_s:<8} {h2_s:<8} {sig}")

print(f"\nTotal overrides: H1={sum(1 for d in h1_decisions if d['llm_q']!=d['or_q'])} H2={sum(1 for d in h2_decisions if d['llm_q']!=d['or_q'])}")
