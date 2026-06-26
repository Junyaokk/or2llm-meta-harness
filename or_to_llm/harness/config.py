import os
from pathlib import Path
from typing import Any, Union
import yaml


class ConfigManager:
    def __init__(self, config_path: Union[str, Path]):
        self.path = Path(config_path)
        with open(self.path) as f:
            self.raw = yaml.safe_load(f)
        self.resolved = self._resolve_env_vars(self.raw)

    def _resolve_env_vars(self, node: Any) -> Any:
        if isinstance(node, str) and node.startswith("${") and node.endswith("}"):
            return os.environ.get(node[2:-1], "")
        if isinstance(node, dict):
            return {k: self._resolve_env_vars(v) for k, v in node.items()}
        if isinstance(node, list):
            return [self._resolve_env_vars(v) for v in node]
        return node

    @property
    def agent_config(self) -> dict:
        return self.resolved.get("agent", {})

    @property
    def llm_config(self) -> dict:
        return self.resolved.get("llm", {})

    @property
    def harness_config(self) -> dict:
        return self.resolved.get("harness", {})

    @property
    def pipeline_config(self) -> dict:
        return self.resolved.get("pipeline", {})

    @property
    def reviewer_config(self) -> dict:
        return self.pipeline_config.get("reviewer", {})

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        val = self.resolved
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return default
            if val is None:
                return default
        return val
