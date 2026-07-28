"""Shared construction helper for OpenAI-compatible async clients."""

from openai import AsyncOpenAI


def create_openai_client(api_key: str, base_url: str | None) -> AsyncOpenAI:
    if base_url:
        return AsyncOpenAI(api_key=api_key, base_url=base_url)
    return AsyncOpenAI(api_key=api_key)
