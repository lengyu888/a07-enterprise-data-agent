from dataclasses import dataclass
import json
import re
from typing import Any

from openai import OpenAI

from app.core.config import Settings


@dataclass(frozen=True)
class DeepSeekProbeResult:
    model: str
    content: str


class DeepSeekGateway:
    """Small server-side adapter for DeepSeek's OpenAI-compatible API."""

    def __init__(self, settings: Settings) -> None:
        if not settings.deepseek_configured:
            raise ValueError("DEEPSEEK_API_KEY is not configured")

        self._settings = settings
        self._client = OpenAI(
            api_key=settings.resolved_deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    def probe(self) -> DeepSeekProbeResult:
        response = self._client.chat.completions.create(
            model=self._settings.deepseek_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are the connectivity probe for an industrial data analysis system.",
                },
                {
                    "role": "user",
                    "content": "Reply with exactly: A07 DeepSeek connection ready",
                },
            ],
            stream=False,
            reasoning_effort=self._settings.deepseek_reasoning_effort,
            extra_body={"thinking": {"type": "enabled"}},
        )
        content = response.choices[0].message.content or ""
        return DeepSeekProbeResult(model=response.model, content=content.strip())

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self._settings.deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            stream=False,
            reasoning_effort=self._settings.deepseek_reasoning_effort,
            extra_body={"thinking": {"type": "enabled"}},
        )
        content = (response.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek JSON response must be an object")
        return parsed

    def complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._settings.deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            reasoning_effort=self._settings.deepseek_reasoning_effort,
            extra_body={"thinking": {"type": "enabled"}},
        )
        return (response.choices[0].message.content or "").strip()
