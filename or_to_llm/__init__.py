"""
OR->LLM Inventory Control Agent -- 论文 "AI Agents for Inventory Control" 复现.
仅实现固定提前期模式 (L=0, L=4)，使用 DeepSeek Chat 作为 LLM 后端.
"""

from .env import InventoryEnv, InTransitOrder, PeriodResult
from .or_baseline import ORBaseline, ORRecommendation
from .agent import ORToLLMAgent, AgentResponse, ResponseParser, UserMessageBuilder, SYSTEM_PROMPT_TEMPLATE, DecisionRecord
from .data import InstanceLoader, normalized_reward, run_single_instance, save_results, validate_with_benchmark_data, build_instance_index
from .trace import TraceLogger
from .visualize import DashboardBuilder
from .report import ReportBuilder
