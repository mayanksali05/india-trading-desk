"""AI wrapper for NEWS and SKEPTIC. Returns parsed JSON, or None on any failure (the desk then skips).

Providers (set llm.provider in settings.yaml):
  anthropic : Claude API (ANTHROPIC_API_KEY)
  openai    : any OpenAI-compatible endpoint. Free options:
              - Google Gemini   base_url https://generativelanguage.googleapis.com/v1beta/openai/
              - Groq            base_url https://api.groq.com/openai/v1
              - Ollama (local)  base_url http://localhost:11434/v1   (no key needed)
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("desk")


def extract_json(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class LLM:
    def __init__(self, cfg):
        self.provider = getattr(cfg, "provider", "anthropic")
        self.model = cfg.model
        self.max_tokens = cfg.max_tokens
        self.client = None

        if self.provider == "anthropic":
            key = os.getenv("ANTHROPIC_API_KEY")
            if key:
                import anthropic
                self.client = anthropic.Anthropic(api_key=key)
        elif self.provider == "openai":
            key_env = getattr(cfg, "api_key_env", "") or ""
            key = os.getenv(key_env) if key_env else "not-needed"   # Ollama needs no key
            if key:
                from openai import OpenAI
                self.client = OpenAI(api_key=key, base_url=cfg.base_url)
        else:
            raise ValueError(f"llm.provider must be anthropic or openai, got {self.provider!r}")

        self.enabled = self.client is not None
        if not self.enabled:
            log.warning("No AI key found for llm.provider=%s: NEWS finds no reasons and SKEPTIC skips everything.",
                        self.provider)

    def _complete(self, system: str, user: str) -> str:
        if self.provider == "anthropic":
            msg = self.client.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        resp = self.client.chat.completions.create(
            model=self.model, max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    def json(self, system: str, user: str) -> dict | None:
        if not self.enabled:
            return None
        try:
            return extract_json(self._complete(system, user))
        except Exception as e:  # network, rate limit, bad key, bad model name: fail closed
            log.error("LLM call failed: %s", e)
            return None
