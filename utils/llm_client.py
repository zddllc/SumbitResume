"""Key-authenticated LLM calls extracted from self_media, without DB or globals."""

from dataclasses import dataclass
from types import TracebackType
from typing import Literal

import httpx
from openai import AzureOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessageParam


Provider = Literal[
    "openai", "azure_openai", "azure_deepseek", "deepseek"
]

_DEFAULT_MODELS: dict[Provider, str] = {
    "azure_openai": "gpt-6.1-sol",
    "azure_deepseek": "DeepSeek-V4-Flash",
    "deepseek": "deepseek-flash",
}
_DEFAULT_BASE_URLS: dict[Provider, str] = {
    "deepseek": "https://api.deepseek.com",
}
_PROVIDERS = {
    "openai", "azure_openai", "azure_deepseek", "deepseek"
}


class LLMResponseError(RuntimeError):
    """The API returned no usable, complete text response."""


@dataclass(frozen=True)
class LLMResponse:
    content: str
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_content: str | None = None


class LLMClient:
    def __init__(
        self,
        *,
        provider: Provider,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        api_version: str = "2024-12-01-preview",
        timeout: float = 300,
        max_retries: int = 0,
        http_client: httpx.Client | None = None,
    ) -> None:
        if provider not in _PROVIDERS:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        resolved_model = _DEFAULT_MODELS.get(provider) if model is None else model
        if not resolved_model or not resolved_model.strip():
            raise ValueError("model is required for this provider")
        if base_url is not None and not base_url.strip():
            raise ValueError("base_url must not be blank")
        if provider in {"azure_openai", "azure_deepseek"} and not base_url:
            raise ValueError(f"base_url is required for {provider}")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if provider == "azure_openai" and not api_version.strip():
            raise ValueError("api_version must not be blank")

        self.provider = provider
        self.model = resolved_model
        self._client: OpenAI
        if provider == "azure_openai":
            if base_url is None:
                raise ValueError("base_url is required for azure_openai")
            self._client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=base_url,
                api_version=api_version,
                timeout=timeout,
                max_retries=max_retries,
                http_client=http_client,
            )
        else:
            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url or _DEFAULT_BASE_URLS.get(provider),
                timeout=timeout,
                max_retries=max_retries,
                http_client=http_client,
            )

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        thinking: bool | None = None,
    ) -> LLMResponse:
        if not prompt.strip():
            raise ValueError("prompt must not be blank")
        if max_tokens is not None and max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if thinking is not None and self.provider not in {"deepseek", "azure_deepseek"}:
            raise ValueError("thinking is only supported by DeepSeek providers")

        messages: list[ChatCompletionMessageParam] = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        extra_body: dict[str, object] | None = None
        if self.provider in {"deepseek", "azure_deepseek"}:
            extra_body = {
                "thinking": {"type": "enabled" if thinking else "disabled"}
            }

        create = self._client.chat.completions.create
        if max_tokens is None:
            response = create(
                model=self.model, messages=messages, stream=False, extra_body=extra_body
            )
        elif self.provider in {"openai", "azure_openai"}:
            response = create(
                model=self.model, messages=messages, stream=False, extra_body=extra_body,
                max_completion_tokens=max_tokens,
            )
        else:
            response = create(
                model=self.model, messages=messages, stream=False, extra_body=extra_body,
                max_tokens=max_tokens,
            )
        if not response.choices:
            raise LLMResponseError("LLM API returned no choices")
        choice = response.choices[0]
        if choice.finish_reason != "stop":
            raise LLMResponseError(
                f"LLM API did not return complete text: {choice.finish_reason}"
            )
        content = choice.message.content
        if content is None or not content.strip():
            raise LLMResponseError("LLM API returned empty text")
        extras = choice.message.model_extra or {}
        reasoning = extras.get("reasoning_content") or extras.get("reason_content")
        if reasoning is not None and not isinstance(reasoning, str):
            raise LLMResponseError("LLM API returned non-text reasoning content")
        usage = response.usage
        return LLMResponse(
            content=content,
            prompt_tokens=usage.prompt_tokens if usage is not None else None,
            completion_tokens=usage.completion_tokens if usage is not None else None,
            reasoning_content=reasoning,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
