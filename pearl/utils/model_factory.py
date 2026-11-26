from __future__ import annotations

from typing import Any

from smolagents import InferenceClientModel, OpenAIModel

from config import SETTINGS

def create_model(LLM_choice: str = "Default"):
    if LLM_choice == "Coder":
        return create_openai_compatible_or_hf_model(
            model_name=SETTINGS.coder_model_name,
            api_base=SETTINGS.coder_api_base,
            api_key=SETTINGS.coder_api_key,
            max_tokens=49152,
        )
    if LLM_choice == "ToolCall":
        return create_openai_compatible_or_hf_model(
            model_name=SETTINGS.toolcall_model_name,
            api_base=SETTINGS.toolcall_api_base,
            api_key=SETTINGS.toolcall_api_key,
            max_tokens=49152,
        )

    return create_openai_compatible_or_hf_model(
        model_name=SETTINGS.model_name,
        api_base=SETTINGS.api_base,
        api_key=SETTINGS.api_key,
        max_tokens=49152,
    )


def create_openai_compatible_or_hf_model(
    model_name: str,
    api_base: str = "",
    api_key: str = "",
    max_tokens: int | None = None,
):
    if api_base:
        kwargs: dict[str, Any] = dict(
            model_id=model_name,
            api_base=api_base,
            api_key=api_key or "EMPTY",
            temperature=0.0,
        )
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return OpenAIModel(**kwargs)
    return InferenceClientModel(model_id=model_name)
