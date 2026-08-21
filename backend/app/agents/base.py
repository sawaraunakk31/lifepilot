"""Base agent class with retry logic, timing, confidence scoring, and logging.

All agents inherit from BaseAgent and implement execute(). The run() wrapper
handles retries with exponential backoff, timing, and error recovery.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from app.agents.state import AgentState
from app.llm.provider import LLMProvider

logger = logging.getLogger("lifepilot.agents")


class BaseAgent(ABC):
    """Abstract base for all LifePilot agents."""

    name: str = "BaseAgent"
    description: str = ""
    max_retries: int = 2

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @abstractmethod
    def execute(self, state: AgentState) -> AgentState:
        """Core agent logic. Must be implemented by subclasses."""
        ...

    def run(self, state: AgentState) -> AgentState:
        """Execute the agent with retry logic, timing, and error handling."""
        start = time.perf_counter()
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                state = self.execute(state)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.info(f"{self.name} completed in {elapsed_ms}ms")
                # Update the last log entry with timing
                for log in reversed(state.logs):
                    if log.get("agent") == self.name:
                        log["duration_ms"] = elapsed_ms
                        break
                return state
            except Exception as e:
                last_error = e
                logger.warning(
                    f"{self.name} attempt {attempt + 1}/{self.max_retries + 1} "
                    f"failed: {e}"
                )
                if attempt < self.max_retries:
                    time.sleep(1.5 ** attempt)

        # All retries exhausted — log failure and continue pipeline
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        error_msg = f"{self.name} failed after {self.max_retries + 1} attempts: {last_error}"
        state.errors.append(error_msg)
        state.add_log(
            agent=self.name,
            message=f"Error: {last_error}",
            confidence=0.0,
            duration_ms=elapsed_ms,
            status="error",
        )
        logger.error(error_msg)
        return state
