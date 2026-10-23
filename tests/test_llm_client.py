import json
import unittest
from unittest.mock import patch

import httpx
import openai
from openai import AzureOpenAI, OpenAI

from utils.llm_client import LLMClient, LLMResponseError


class LLMClientTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.status = 200
        self.payload = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "Hello"},
            }],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
            },
        }

        def handle(request):
            self.requests.append(request)
            return httpx.Response(self.status, json=self.payload)

        def client_factory(**kwargs):
            if kwargs.get("http_client") is None:
                kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(handle))
            return OpenAI(**kwargs)

        def azure_factory(**kwargs):
            if kwargs.get("http_client") is None:
                kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(handle))
            return AzureOpenAI(**kwargs)

        self.openai_patch = patch("utils.llm_client.OpenAI", side_effect=client_factory)
        self.azure_patch = patch("utils.llm_client.AzureOpenAI", side_effect=azure_factory)
        self.openai_constructor = self.openai_patch.start()
        self.azure_constructor = self.azure_patch.start()
        self.addCleanup(self.openai_patch.stop)
        self.addCleanup(self.azure_patch.stop)

    def request_body(self):
        return json.loads(self.requests[-1].content)

    def test_deepseek_request_and_response(self):
        self.payload["choices"][0]["message"]["reasoning_content"] = "Some reasoning"
        with LLMClient(provider="deepseek", api_key="test-key") as client:
            result = client.complete(
                "Hello", system_prompt="Be concise", max_tokens=100, thinking=True
            )
        self.assertEqual(result.content, "Hello")
        self.assertEqual((result.prompt_tokens, result.completion_tokens), (12, 3))
        self.assertEqual(result.reasoning_content, "Some reasoning")
        self.assertEqual(
            str(self.requests[0].url),
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(self.requests[0].headers["authorization"], "Bearer test-key")
        self.assertEqual(self.request_body(), {
            "model": "deepseek-flash",
            "messages": [
                {"role": "system", "content": "Be concise"},
                {"role": "user", "content": "Hello"},
            ],
            "stream": False,
            "max_tokens": 100,
            "thinking": {"type": "enabled"},
        })
        self.assertTrue(client._client.is_closed())

    def test_deepseek_defaults_to_chat_mode(self):
        with LLMClient(provider="deepseek", api_key="test-key") as client:
            client.complete("Hello")
        self.assertEqual(self.request_body()["thinking"], {"type": "disabled"})
        self.assertNotIn("max_tokens", self.request_body())

    def test_azure_openai_uses_deployment_and_completion_token_limit(self):
        with LLMClient(
            provider="azure_openai",
            api_key="azure-test-key",
            base_url="https://example.openai.azure.com",
            model="custom-deployment",
            api_version="2024-12-01-preview",
        ) as client:
            client.complete("Hello", max_tokens=80)
        request = self.requests[0]
        self.assertEqual(
            request.url.path,
            "/openai/deployments/custom-deployment/chat/completions",
        )
        self.assertEqual(request.url.params["api-version"], "2024-12-01-preview")
        self.assertEqual(request.headers["api-key"], "azure-test-key")
        self.assertEqual(self.request_body()["max_completion_tokens"], 80)
        self.assertNotIn("max_tokens", self.request_body())
        self.assertNotIn("thinking", self.request_body())

    def test_azure_deepseek_is_openai_compatible(self):
        with LLMClient(
            provider="azure_deepseek",
            api_key="test-key",
            base_url="https://example.test/openai/v1",
        ) as client:
            client.complete("Hello", max_tokens=90, thinking=False)
        self.assertEqual(self.request_body()["model"], "DeepSeek-V4-Flash")
        self.assertEqual(self.request_body()["max_tokens"], 90)
        self.assertEqual(self.request_body()["thinking"], {"type": "disabled"})
        self.assertEqual(
            self.requests[0].url.path, "/openai/v1/chat/completions"
        )
        self.azure_constructor.assert_not_called()

    def test_openai_requires_model_and_accepts_custom_base_url(self):
        with self.assertRaisesRegex(ValueError, "model is required"):
            LLMClient(provider="openai", api_key="test-key")
        with LLMClient(
            provider="openai",
            api_key="test-key",
            model="chosen-model",
            base_url="https://compatible.test/v1",
        ) as client:
            client.complete("Hello")
        self.assertEqual(self.request_body()["model"], "chosen-model")
        self.assertEqual(self.requests[0].url.host, "compatible.test")

    def test_missing_usage_remains_unknown(self):
        del self.payload["usage"]
        with LLMClient(provider="deepseek", api_key="test-key") as client:
            result = client.complete("Hello")
        self.assertIsNone(result.prompt_tokens)
        self.assertIsNone(result.completion_tokens)

    def test_invalid_responses_raise(self):
        for choices in (
            [],
            [{"index": 0, "finish_reason": "stop",
              "message": {"role": "assistant", "content": None}}],
            [{"index": 0, "finish_reason": "stop",
              "message": {"role": "assistant", "content": "  "}}],
            [{"index": 0, "finish_reason": "length",
              "message": {"role": "assistant", "content": "truncated"}}],
            [{"index": 0, "finish_reason": "content_filter",
              "message": {"role": "assistant", "content": "filtered"}}],
            [{"index": 0, "finish_reason": "stop",
              "message": {"role": "assistant", "content": "Hello",
                          "reasoning_content": {"unexpected": "object"}}}],
        ):
            with self.subTest(choices=choices):
                self.payload["choices"] = choices
                with LLMClient(provider="deepseek", api_key="test-key") as client:
                    with self.assertRaises(LLMResponseError):
                        client.complete("Hello")

    def test_provider_failures_propagate_without_retries_or_fallback(self):
        for status, error_type in (
            (401, openai.AuthenticationError),
            (429, openai.RateLimitError),
            (500, openai.InternalServerError),
        ):
            with self.subTest(status=status):
                self.requests.clear()
                self.status = status
                self.payload = {"error": {"message": "Provider error", "type": "test"}}
                with LLMClient(provider="deepseek", api_key="test-key") as client:
                    with self.assertRaises(error_type):
                        client.complete("Hello")
                self.assertEqual(len(self.requests), 1)

    def test_invalid_configuration_fails_before_constructing_sdk(self):
        cases = (
            {"provider": "unknown", "api_key": "test-key"},
            {"provider": "agnes", "api_key": "test-key"},
            {"provider": "deepseek", "api_key": " "},
            {"provider": "deepseek", "api_key": "test-key", "model": " "},
            {"provider": "deepseek", "api_key": "test-key", "base_url": " "},
            {"provider": "azure_openai", "api_key": "test-key"},
            {"provider": "azure_deepseek", "api_key": "test-key"},
            {"provider": "proxy", "api_key": "test-key"},
            {"provider": "deepseek", "api_key": "test-key", "timeout": 0},
            {"provider": "deepseek", "api_key": "test-key", "max_retries": -1},
            {"provider": "azure_openai", "api_key": "test-key",
             "base_url": "https://example.test", "api_version": " "},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LLMClient(**kwargs)
        self.openai_constructor.assert_not_called()
        self.azure_constructor.assert_not_called()

    def test_invalid_requests_never_contact_api(self):
        with LLMClient(
            provider="openai", api_key="test-key", model="test-model"
        ) as client:
            for prompt, kwargs in (
                (" ", {}),
                ("Hello", {"max_tokens": 0}),
                ("Hello", {"max_tokens": -1}),
                ("Hello", {"thinking": True}),
                ("Hello", {"thinking": False}),
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    client.complete(prompt, **kwargs)
        self.assertEqual(self.requests, [])

    def test_context_closes_client_on_exception(self):
        with self.assertRaisesRegex(RuntimeError, "caller failed"):
            with LLMClient(provider="deepseek", api_key="test-key") as client:
                raise RuntimeError("caller failed")
        self.assertTrue(client._client.is_closed())


if __name__ == "__main__":
    unittest.main()
