from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.providers.base import LLMProvider
from app.core.settings import settings


@dataclass
class ClaudeProviderError(Exception):
    message: str
    error_type: str = "provider_error"


class ClaudeProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "claude"

    @property
    def configured(self) -> bool:
        return bool(settings.claude_base_url and settings.claude_model)

    @property
    def supports_stream(self) -> bool:
        return True

    @property
    def base_url(self) -> str | None:
        return settings.claude_base_url

    @property
    def model(self) -> str | None:
        return settings.claude_model

    @property
    def transport(self) -> str | None:
        return settings.claude_transport

    async def diagnose(self) -> dict[str, Any]:
        if not self.configured:
            return {"reachable": False, "last_error": "provider not configured"}

        root_url = self._root_url((settings.claude_base_url or "").rstrip("/"))
        try:
            payload = await self._get_json(url=f"{root_url}/api/tags")
        except ClaudeProviderError as exc:
            return {"reachable": False, "last_error": exc.message}

        models = payload.get("models", [])
        if not isinstance(models, list):
            return {"reachable": False, "last_error": "invalid /api/tags payload"}

        model_names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
        if settings.claude_model not in model_names:
            return {"reachable": False, "tag_reachable": True, "generation_reachable": False, "last_error": f"model '{settings.claude_model}' not found"}

        try:
            for url, payload in self._candidate_requests(
                prompt="请只回复 ok",
                system_prompt=None,
                temperature=0.0,
                max_tokens=8,
                stream=False,
            ):
                if self._prefer_streaming_json(url=url):
                    # Ollama generate 非流式会等完整输出，远端模型诊断也用短流式避免误超时。
                    stream_payload = {**payload, "stream": True}
                    content = "".join(
                        [chunk async for chunk in self._post_stream(url=url, payload=stream_payload, headers=self._build_headers())]
                    )
                else:
                    response_json = await self._post_json(url=url, payload=payload, headers=self._build_headers())
                    content = self._extract_content(response_json)
                if content.strip():
                    return {"reachable": True, "tag_reachable": True, "generation_reachable": True, "last_error": None}
        except ClaudeProviderError as exc:
            return {"reachable": False, "tag_reachable": True, "generation_reachable": False, "last_error": exc.message}
        except Exception as exc:
            return {"reachable": False, "tag_reachable": True, "generation_reachable": False, "last_error": str(exc)}

        return {"reachable": False, "tag_reachable": True, "generation_reachable": False, "last_error": "model returned empty content"}

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        if not self.configured:
            raise ClaudeProviderError("Claude provider is not fully configured", error_type="config")

        system_prompt = kwargs.get("system_prompt")
        temperature = kwargs.get("temperature", 0.2)
        max_tokens = kwargs.get("max_tokens", 512)
        headers = self._build_headers()

        failures: list[str] = []
        for url, payload in self._candidate_requests(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        ):
            try:
                if self._prefer_streaming_json(url=url):
                    stream_payload = {**payload, "stream": True}
                    parts = [chunk async for chunk in self._post_stream(url=url, payload=stream_payload, headers=headers)]
                    content = "".join(parts)
                else:
                    response_json = await self._post_json(url=url, payload=payload, headers=headers)
                    content = self._extract_content(response_json)
                if not content.strip():
                    raise ClaudeProviderError("model returned empty content", error_type="empty_response")
                return content.strip()
            except ClaudeProviderError as exc:
                failures.append(f"{url}: {exc.message}")
            except Exception as exc:  # pragma: no cover - 防御性保护，统一收敛到 provider error。
                failures.append(f"{url}: {exc}")

        raise ClaudeProviderError("; ".join(failures) or "No available LLM endpoint", error_type="upstream")

    async def stream_generate(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        if not self.configured:
            raise ClaudeProviderError("Claude provider is not fully configured", error_type="config")

        system_prompt = kwargs.get("system_prompt")
        temperature = kwargs.get("temperature", 0.2)
        max_tokens = kwargs.get("max_tokens", 512)
        headers = self._build_headers()
        failures: list[str] = []

        for url, payload in self._candidate_requests(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        ):
            emitted = False
            try:
                async for chunk in self._post_stream(url=url, payload=payload, headers=headers):
                    emitted = True
                    yield chunk
                if emitted:
                    return
                raise ClaudeProviderError("model returned empty content", error_type="empty_response")
            except ClaudeProviderError as exc:
                failures.append(f"{url}: {exc.message}")
            except Exception as exc:  # pragma: no cover - defensive upstream guard.
                failures.append(f"{url}: {exc}")

        raise ClaudeProviderError("; ".join(failures) or "No available streaming endpoint", error_type="upstream")

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if settings.claude_api_key:
            headers["Authorization"] = f"Bearer {settings.claude_api_key}"
        return headers

    def _candidate_requests(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> list[tuple[str, dict[str, Any]]]:
        base_url = (settings.claude_base_url or "").rstrip("/")
        root_url = self._root_url(base_url)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        openai_payload = {
            "model": settings.claude_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        ollama_options = {"temperature": temperature, "num_predict": self._num_predict(max_tokens)}
        ollama_chat_payload = {
            "model": settings.claude_model,
            "messages": messages,
            "stream": stream,
            "think": False,
            "options": ollama_options,
        }
        merged_prompt = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
        ollama_generate_payload = {
            "model": settings.claude_model,
            "prompt": merged_prompt,
            "stream": stream,
            "think": False,
            "options": ollama_options,
        }

        transport = (settings.claude_transport or "ollama_chat").lower()
        transport_routes: dict[str, list[tuple[str, dict[str, Any]]]] = {
            "ollama_chat": [(f"{root_url}/api/chat", ollama_chat_payload)],
            "ollama_generate": [(f"{root_url}/api/generate", ollama_generate_payload)],
            "openai_chat": [(f"{root_url}/v1/chat/completions", openai_payload)],
            "auto": [
                (f"{root_url}/api/chat", ollama_chat_payload),
                (f"{root_url}/api/generate", ollama_generate_payload),
                (f"{root_url}/v1/chat/completions", openai_payload),
            ],
        }
        return transport_routes.get(transport, transport_routes["ollama_chat"])

    async def _get_json(self, *, url: str) -> dict[str, Any]:
        timeout = self._timeout()
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, headers=self._build_headers())
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or str(exc)
                raise ClaudeProviderError(detail, error_type="http_status") from exc
            except httpx.HTTPError as exc:
                raise ClaudeProviderError(str(exc), error_type="network") from exc
        return response.json()

    async def _post_json(self, *, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or str(exc)
                raise ClaudeProviderError(detail, error_type="http_status") from exc
            except httpx.HTTPError as exc:
                raise ClaudeProviderError(str(exc), error_type="network") from exc
        return response.json()

    async def _post_stream(self, *, url: str, payload: dict[str, Any], headers: dict[str, str]) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            try:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        content = self._extract_stream_content(line)
                        if content:
                            yield content
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or str(exc)
                raise ClaudeProviderError(detail, error_type="http_status") from exc
            except httpx.HTTPError as exc:
                raise ClaudeProviderError(str(exc), error_type="network") from exc

    @staticmethod
    def _extract_stream_content(line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return ""
        if stripped.startswith("data: "):
            stripped = stripped[6:].strip()
        if stripped == "[DONE]":
            return ""

        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return ""

        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            delta = choices[0].get("delta", {})
            content = delta.get("content") if isinstance(delta, dict) else None
            return content if isinstance(content, str) else ""

        message = payload.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            return content if isinstance(content, str) else ""

        response_text = payload.get("response")
        if isinstance(response_text, str):
            return response_text

        return ""

    @staticmethod
    def _extract_content(response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [item.get("text", "") for item in content if isinstance(item, dict)]
                return "".join(parts)

        message = response_json.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content

        response_text = response_json.get("response")
        if isinstance(response_text, str):
            return response_text

        raise ClaudeProviderError(f"Unsupported response payload: {response_json}", error_type="invalid_payload")

    @staticmethod
    def _root_url(base_url: str) -> str:
        parts = urlsplit(base_url)
        return f"{parts.scheme}://{parts.netloc}"

    @staticmethod
    def _timeout() -> httpx.Timeout:
        # 26B 远端模型首 token 较慢，给足 read timeout，避免真实请求被过早回退。
        effective_timeout = max(120.0, float(settings.claude_timeout_seconds))
        return httpx.Timeout(
            connect=min(5.0, effective_timeout),
            read=effective_timeout,
            write=min(15.0, effective_timeout),
            pool=min(15.0, effective_timeout),
        )

    @staticmethod
    def _prefer_streaming_json(*, url: str) -> bool:
        """Use streaming for Ollama generate because the remote server may time out on full JSON responses."""
        return url.endswith("/api/generate")

    @staticmethod
    def _num_predict(max_tokens: Any) -> int:
        """Map OpenAI-style max_tokens to Ollama's num_predict to avoid unbounded generations."""
        try:
            value = int(max_tokens)
        except (TypeError, ValueError):
            value = 512
        return max(1, min(value, 2048))
