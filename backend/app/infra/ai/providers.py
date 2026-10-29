"""AIProvider adapters. Pick one with AI_PROVIDER; with no key, AI tools report themselves unavailable."""

import logging

import httpx

from app.domain.errors import ServiceUnavailable, ToolFailed

log = logging.getLogger(__name__)


class NoAIProvider:
    available = False

    def complete(self, *, system: str, prompt: str, max_tokens: int = 2048) -> str:
        raise ServiceUnavailable("AI features are not configured yet. Add an AI provider key to enable them.")


class AnthropicProvider:
    """Claude via the official Anthropic SDK."""

    def __init__(self, api_key: str, model: str = "claude-opus-5-5"):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=3)
        self._model = model

    @property
    def available(self) -> bool:
        return True

    def complete(self, *, system: str, prompt: str, max_tokens: int = 2048) -> str:
        a = self._anthropic
        try:
            # Streaming avoids HTTP timeouts on long documents; "default" fallbacks reroute policy declines.
            with self._client.beta.messages.stream(
                model=self._model,
                max_tokens=max(max_tokens, 4096),
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                message = stream.get_final_message()
        except a.RateLimitError:
            raise ServiceUnavailable("The AI service is busy. Try again in a minute.") from None
        except a.AuthenticationError:
            log.error("Anthropic API key rejected")
            raise ServiceUnavailable("The AI service is misconfigured.") from None
        except a.APIStatusError as exc:
            log.warning("Anthropic API error %s: %s", exc.status_code, exc.message)
            raise ToolFailed("The AI service returned an error.") from None
        except a.APIConnectionError:
            raise ServiceUnavailable("The AI service is unreachable.") from None
        if message.stop_reason == "refusal":
            raise ToolFailed("The AI declined to process this document.")
        return "".join(block.text for block in message.content if block.type == "text").strip()


class OpenAICompatibleProvider:
    """Any server speaking the OpenAI chat-completions protocol (Ollama, vLLM, LM Studio, OpenAI...)."""

    def __init__(self, api_key: str | None, model: str, base_url: str = "https://api.openai.com/v1"):
        self._key = api_key
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"

    @property
    def available(self) -> bool:
        return True

    def complete(self, *, system: str, prompt: str, max_tokens: int = 2048) -> str:
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        try:
            response = httpx.post(self._url, json=body, headers=headers, timeout=600)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("AI provider error: %s", exc)
            raise ServiceUnavailable("The AI service is unreachable.") from None
        return response.json()["choices"][0]["message"]["content"].strip()
