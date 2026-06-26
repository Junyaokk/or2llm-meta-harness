from typing import Optional
from openai import OpenAI
from .config import ConfigManager


class AgentFactory:
    def __init__(self, config: ConfigManager):
        self.config = config
        self._llm_client: Optional[OpenAI] = None

    @property
    def llm_client(self) -> OpenAI:
        if self._llm_client is None:
            llm = self.config.llm_config
            self._llm_client = OpenAI(
                api_key=llm.get("api_key"),
                base_url=llm.get("base_url", "https://api.deepseek.com/v1"),
                timeout=llm.get("timeout", 180.0),
                max_retries=llm.get("max_retries", 2),
            )
        return self._llm_client

    def create_agent(self, item_id: str, L: int, p: float, h: float):
        from ..agent import ORToLLMAgent
        agent_conf = self.config.agent_config
        return ORToLLMAgent(
            item_id=item_id,
            anticipated_lead_time=L,
            p=p, h=h,
            model=agent_conf.get("model", "deepseek-chat"),
            client=self.llm_client,
        )

    def create_reviewer(self, p: float, h: float):
        from ..reviewer import ReviewerAgent
        rev_conf = self.config.reviewer_config
        return ReviewerAgent(
            p=p, h=h,
            model=rev_conf.get("model", "deepseek-chat"),
            client=self.llm_client,
            deviation_threshold=rev_conf.get("deviation_threshold", 2.0),
        )
