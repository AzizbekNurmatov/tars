"""Backward-compatible re-export of the agent orchestrator."""

from tars.core.agent import LLMOrchestrator, SYSTEM_PROMPT, complete_isolated
from tars.providers.base import complete_vision_isolated

__all__ = [
    "LLMOrchestrator",
    "SYSTEM_PROMPT",
    "complete_isolated",
    "complete_vision_isolated",
]
