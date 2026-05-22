from __future__ import annotations

from ai_cursor.providers.base import ModelProvider
from ai_cursor.types import ActionDecision, History, Observation


class MockProvider(ModelProvider):
    name = "mock"

    def decide(
        self,
        task: str,
        observation: Observation,
        history: History,
        allow_shell: bool,
    ) -> ActionDecision:
        if self.model == "click-center" and not history:
            return ActionDecision(
                action="click",
                x=observation.width // 2,
                y=observation.height // 2,
                reason="mock click at the center of the screenshot",
                confidence=1.0,
            )
        if self.model == "wait":
            return ActionDecision(action="wait", seconds=1.0, reason="mock wait", confidence=1.0)
        return ActionDecision(
            action="done",
            reason=f"mock provider completed without acting on: {task}",
            confidence=1.0,
        )
