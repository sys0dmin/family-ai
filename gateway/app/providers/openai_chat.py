"""OpenAI-compatible chat provider adapter."""

from typing import Any, Literal

from gateway.app.providers.contracts import ChatProvider
from gateway.app.providers.openai_client import create_openai_client
from gateway.app.providers.schemas import (
    ChatRequest,
    ChatResponse,
    ProviderTool,
)


class OpenAIChatProvider(ChatProvider):
    """Chat-only adapter for OpenAI-compatible completion APIs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        web_search_tool_type: Literal["disabled", "browser_search"] = "disabled",
    ) -> None:
        resolved_base_url = base_url
        if resolved_base_url is None and "deepseek" in model.lower():
            resolved_base_url = "https://api.deepseek.com/v1"
        self._client = create_openai_client(api_key, resolved_base_url)
        self._model = model
        self._web_search_tool_type = web_search_tool_type

    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
        ]
        parameters: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if (
            ProviderTool.WEB_SEARCH in request.tools
            and self._web_search_tool_type == "browser_search"
        ):
            parameters["tools"] = [{"type": "browser_search"}]
        response = await self._client.chat.completions.create(**parameters)
        content = response.choices[0].message.content or ""
        return ChatResponse(content=content, raw_response=response)
