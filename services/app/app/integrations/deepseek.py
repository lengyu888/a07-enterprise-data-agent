from dataclasses import dataclass

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
