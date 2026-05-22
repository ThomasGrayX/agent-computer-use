from __future__ import annotations

import os
from typing import Any

from ai_cursor.json_utils import extract_json_object
from ai_cursor.providers.base import ModelProvider, SYSTEM_PROMPT, build_decision_prompt
from ai_cursor.providers.http import env_required, image_as_data_url, post_json
from ai_cursor.types import ActionDecision, History, Observation


class OpenAIProvider(ModelProvider):
    name = "openai"

    def decide(
        self,
        task: str,
        observation: Observation,
        history: History,
        allow_shell: bool,
    ) -> ActionDecision:
        api_key = env_required("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        prompt = build_decision_prompt(task, observation, history, allow_shell)
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": SYSTEM_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": image_as_data_url(observation.image_path),
                            "detail": "high",
                        },
                    ],
                }
            ],
            "max_output_tokens": self.max_output_tokens,
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}

        response = post_json(
            f"{base_url.rstrip('/')}/responses",
            payload,
            {"authorization": f"Bearer {api_key}"},
            self.timeout,
        )
        return ActionDecision.from_dict(extract_json_object(_extract_openai_text(response)))


def _extract_openai_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    parts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])

    if parts:
        return "\n".join(parts)

    if response.get("status") == "incomplete":
        reason = (response.get("incomplete_details") or {}).get("reason", "unknown")
        raise RuntimeError(
            "OpenAI response was incomplete before producing an action "
            f"(reason: {reason}). Try increasing --model-output-tokens or lowering --reasoning-effort."
        )

    raise RuntimeError(f"OpenAI response did not include output text: {response}")
