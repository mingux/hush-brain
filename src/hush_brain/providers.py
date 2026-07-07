"""LLM providers, OpenJarvis-style: local-first via Ollama, cloud when a key exists,
deterministic Echo for tests and keyless demos.

Selection order: HUSH_PROVIDER env override > Anthropic (if ANTHROPIC_API_KEY) >
Ollama (if reachable) > Echo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

OLLAMA_URL = os.environ.get("HUSH_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("HUSH_OLLAMA_MODEL", "llama3.1:8b")
ANTHROPIC_MODEL = os.environ.get("HUSH_ANTHROPIC_MODEL", "claude-opus-4-8")


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class EchoProvider:
    """Deterministic offline provider — powers tests and keyless demo mode."""

    name = "echo"

    async def complete(self, prompt: str, system: str | None = None) -> Completion:
        head = " ".join(prompt.split())[:160]
        text = f"[echo] There is no spoon. Received: {head}"
        return Completion(text=text, input_tokens=len(prompt) // 4, output_tokens=len(text) // 4)


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = OLLAMA_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def complete(self, prompt: str, system: str | None = None) -> Completion:
        body = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            body["system"] = system
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{self.base_url}/api/generate", json=body)
            r.raise_for_status()
            data = r.json()
        return Completion(
            text=data.get("response", "").strip(),
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
        )


class AnthropicProvider:
    def __init__(self, model: str = ANTHROPIC_MODEL):
        import anthropic

        self.model = model
        self.name = f"anthropic:{model}"
        self._client = anthropic.AsyncAnthropic()

    async def complete(self, prompt: str, system: str | None = None) -> Completion:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        text = "\n".join(b.text for b in response.content if b.type == "text")
        return Completion(
            text=text.strip(),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


async def resolve_provider():
    """Pick the best available provider; degrade gracefully down the chain."""
    forced = os.environ.get("HUSH_PROVIDER", "").lower()
    if forced == "echo":
        return EchoProvider()
    if forced == "anthropic":
        return AnthropicProvider()
    if forced == "ollama":
        return OllamaProvider()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    ollama = OllamaProvider()
    if await ollama.available():
        return ollama
    return EchoProvider()
