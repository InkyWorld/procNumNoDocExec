from __future__ import annotations

import logging
from typing import Any, Tuple

from langchain_core.runnables import Runnable

from .config import get_azure_settings
from .decision_llm import CLASSIFY_PROMPT, EXTRACT_PROMPT

logger = logging.getLogger(__name__)


def get_azure_chains() -> Tuple[Runnable | None, Runnable | None]:
    """Return (extract_chain, classify_chain) built from Azure settings or (None, None).

    This isolates Azure wiring from `main.py` so the entrypoint stays tidy.
    """
    azure = get_azure_settings()
    if not (azure.endpoint and azure.api_key and azure.model):
        return None, None

    try:
        from langchain_openai import AzureChatOpenAI  # type: ignore
    except Exception:  # pragma: no cover - best-effort import
        logger.debug("langchain_openai not available; skipping Azure LLM")
        return None, None

    base_kwargs: dict[str, Any] = {
        "azure_endpoint": azure.endpoint.rstrip("/"),
        "api_key": azure.api_key,
        "api_version": azure.api_version,
    }

    llm = None
    try:
        kwargs: dict[str, Any] = dict(base_kwargs)
        kwargs["azure_deployment"] = azure.model
        kwargs["temperature"] = 0
        llm = AzureChatOpenAI(**kwargs)  # type: ignore[arg-type]
    except TypeError:
        kwargs = dict(base_kwargs)
        kwargs["deployment_name"] = azure.model
        # Some versions don't accept temperature; try with it then without
        try:
            kwargs["temperature"] = 0
            llm = AzureChatOpenAI(**kwargs)  # type: ignore[arg-type]
        except TypeError:
            kwargs.pop("temperature", None)
            llm = AzureChatOpenAI(**kwargs)  # type: ignore[arg-type]

    if llm is None:
        logger.debug("Failed to instantiate AzureChatOpenAI; skipping chains")
        return None, None

    extract_chain = EXTRACT_PROMPT | llm
    classify_chain = CLASSIFY_PROMPT | llm
    logger.info("Using Azure OpenAI deployment: %s", azure.model)
    return extract_chain, classify_chain


__all__ = ["get_azure_chains"]
