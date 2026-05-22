from __future__ import annotations

from dataclasses import dataclass

from ai_cursor.providers.anthropic import AnthropicProvider
from ai_cursor.providers.base import ModelProvider
from ai_cursor.providers.mock import MockProvider
from ai_cursor.providers.openai import OpenAIProvider


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str


def parse_model_spec(value: str) -> ModelSpec:
    if ":" not in value:
        return ModelSpec(provider="openai", model=value)
    provider, model = value.split(":", 1)
    provider = provider.strip().lower()
    model = model.strip()
    if not provider or not model:
        raise ValueError("Model must look like provider:model, for example openai:gpt-5.5")
    return ModelSpec(provider=provider, model=model)


def create_provider(
    value: str,
    timeout: float = 120.0,
    max_output_tokens: int = 4096,
    reasoning_effort: str | None = "low",
) -> ModelProvider:
    spec = parse_model_spec(value)
    if spec.provider == "openai":
        return OpenAIProvider(
            spec.model,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
        )
    if spec.provider in {"anthropic", "claude"}:
        return AnthropicProvider(
            spec.model,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
        )
    if spec.provider == "mock":
        return MockProvider(
            spec.model,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
        )
    raise ValueError(f"Unknown provider '{spec.provider}'. Use openai, anthropic, or mock.")
