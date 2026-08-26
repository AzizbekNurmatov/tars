"""Backward-compatible re-export of the agent orchestrator."""

from tars.core.agent import LLMOrchestrator, SYSTEM_PROMPT, complete_isolated

__all__ = ["LLMOrchestrator", "SYSTEM_PROMPT", "complete_isolated"]
