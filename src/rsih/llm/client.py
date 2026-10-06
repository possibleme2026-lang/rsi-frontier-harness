"""The frozen model endpoint.

One rule matters more than the rest: **a call is never silently retried into a
different conversation**.  Transport retries resend the identical payload; a
malformed tool call is handed back to the agent loop as an observation instead of
being repaired here, because repairing it here would make the trajectory lie
about what the model produced.
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings, settings as default_settings
from .pricing import Usage


class LLMError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments_raw: str
    arguments: dict[str, Any] = field(default_factory=dict)
    parse_error: str | None = None

    def as_message_part(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments_raw},
        }


@dataclass
class LLMResponse:
    content: str
    reasoning: str
    tool_calls: list[ToolCall]
    usage: Usage
    latency_s: float
    finish_reason: str | None
    raw: dict[str, Any]


def _parse_usage(payload: dict[str, Any] | None) -> Usage:
    if not payload:
        return Usage()
    details = payload.get("prompt_tokens_details") or {}
    completion_details = payload.get("completion_tokens_details") or {}
    cached = details.get("cached_tokens")
    if cached is None:
        # DeepSeek-native field names, seen on some gateways.
        cached = payload.get("prompt_cache_hit_tokens")
    return Usage(
        prompt_tokens=payload.get("prompt_tokens"),
        completion_tokens=payload.get("completion_tokens"),
        cached_tokens=cached,
        cache_write_tokens=payload.get("prompt_cache_miss_tokens"),
        reasoning_tokens=completion_details.get("reasoning_tokens"),
    )


def _parse_tool_calls(raw_calls: list[dict[str, Any]]) -> list[ToolCall]:
    parsed: list[ToolCall] = []
    for index, call in enumerate(raw_calls):
        function = call.get("function") or {}
        raw_args = function.get("arguments") or "{}"
        call_id = call.get("id") or f"call_{index}"
        arguments: dict[str, Any] = {}
        error: str | None = None
        if isinstance(raw_args, dict):
            arguments = raw_args
        else:
            try:
                loaded = json.loads(raw_args)
                if isinstance(loaded, dict):
                    arguments = loaded
                else:
                    error = f"arguments must be a JSON object, got {type(loaded).__name__}"
            except json.JSONDecodeError as exc:
                error = f"invalid JSON in arguments: {exc}"
        parsed.append(
            ToolCall(
                id=call_id,
                name=function.get("name") or "",
                arguments_raw=raw_args if isinstance(raw_args, str) else json.dumps(raw_args),
                arguments=arguments,
                parse_error=error,
            )
        )
    return parsed


class LLMClient:
    """OpenAI-compatible chat client with measured usage and honest retries."""

    def __init__(self, settings: Settings | None = None, log_path: Path | None = None):
        self.settings = settings or default_settings()
        if not self.settings.api_key:
            raise LLMError(
                "no API key: set TIERFLOW_API_KEY or put it in "
                f"{self.settings.workspace} configuration (.env)"
            )
        from openai import OpenAI  # imported lazily so unit tests need no network

        self._openai = OpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
            timeout=self.settings.request_timeout_s,
            max_retries=0,
        )
        self.log_path = log_path
        self.call_index = 0

    # ------------------------------------------------------------------ helpers

    def _log(self, record: dict[str, Any]) -> None:
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        text = str(exc).lower()
        status = getattr(exc, "status_code", None)
        if status in (408, 409, 429, 500, 502, 503, 504):
            return True
        for marker in ("timeout", "timed out", "connection", "rate limit", "overloaded", "502", "503", "504"):
            if marker in text:
                return True
        return False

    # -------------------------------------------------------------------- calls

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tool_choice: str | dict | None = None,
        label: str = "agent",
        extra_body: dict[str, Any] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if extra_body:
            payload.update(extra_body)

        self.call_index += 1
        attempt = 0
        started = time.time()
        last_error: Exception | None = None
        while attempt <= self.settings.max_retries:
            attempt += 1
            try:
                response = self._openai.chat.completions.create(**payload)
                latency = time.time() - started
                parsed = self._to_response(response, latency)
                self._log(
                    {
                        "call": self.call_index,
                        "label": label,
                        "attempt": attempt,
                        "latency_s": round(latency, 3),
                        "finish_reason": parsed.finish_reason,
                        "usage": parsed.usage.as_dict(),
                        "tool_calls": [
                            {"name": c.name, "arguments": c.arguments_raw, "error": c.parse_error}
                            for c in parsed.tool_calls
                        ],
                        "content_chars": len(parsed.content),
                        "reasoning_chars": len(parsed.reasoning),
                    }
                )
                return parsed
            except Exception as exc:  # noqa: BLE001 - gateway errors are heterogeneous
                last_error = exc
                if attempt > self.settings.max_retries or not self._retryable(exc):
                    break
                sleep_for = min(30.0, 2.0**attempt) * (0.5 + random.random() / 2)
                self._log(
                    {
                        "call": self.call_index,
                        "label": label,
                        "attempt": attempt,
                        "error": str(exc)[:400],
                        "sleep_s": round(sleep_for, 2),
                    }
                )
                time.sleep(sleep_for)
        raise LLMError(
            f"model call failed after {attempt} attempt(s): {type(last_error).__name__}: {last_error}"
        ) from last_error

    @staticmethod
    def _to_response(response: Any, latency: float) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message
        raw_calls = getattr(message, "tool_calls", None) or []
        serialised = []
        for call in raw_calls:
            serialised.append(
                {
                    "id": getattr(call, "id", None),
                    "type": "function",
                    "function": {
                        "name": getattr(call.function, "name", None),
                        "arguments": getattr(call.function, "arguments", None),
                    },
                }
            )
        return LLMResponse(
            content=(message.content or ""),
            reasoning=(getattr(message, "reasoning_content", None) or ""),
            tool_calls=_parse_tool_calls(serialised),
            usage=_parse_usage(response.usage.model_dump() if response.usage else None),
            latency_s=latency,
            finish_reason=getattr(choice, "finish_reason", None),
            raw=response.model_dump(),
        )


def client_from_env(log_path: Path | None = None) -> LLMClient:
    return LLMClient(settings=default_settings(), log_path=log_path)


def default_temperature() -> float:
    return float(os.environ.get("RSIH_TEMPERATURE", "0") or 0)
