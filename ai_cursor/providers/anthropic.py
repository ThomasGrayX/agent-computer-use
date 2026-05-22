from __future__ import annotations

import os
from typing import Any

from ai_cursor.json_utils import extract_json_object
from ai_cursor.providers.base import ModelProvider, SYSTEM_PROMPT, build_decision_prompt
from ai_cursor.providers.http import env_required, image_as_base64, post_json
from ai_cursor.types import ActionDecision, History, Observation


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def decide(
        self,
        task: str,
        observation: Observation,
        history: History,
        allow_shell: bool,
    ) -> ActionDecision:
        api_key = env_required("ANTHROPIC_API_KEY")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
        prompt = build_decision_prompt(task, observation, history, allow_shell)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_as_base64(observation.image_path),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        response = post_json(
            f"{base_url.rstrip('/')}/messages",
            payload,
            {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            self.timeout,
        )
        return ActionDecision.from_dict(extract_json_object(_extract_anthropic_text(response)))


def _extract_anthropic_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in response.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    if parts:
        return "\n".join(parts)
    raise RuntimeError(f"Anthropic response did not include text content: {response}")
