from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .schemas import DecisionEnum

logger = logging.getLogger(__name__)


# Timeout per LLM call
DEFAULT_LLM_TIMEOUT = 60
# Retry: 3 attempts
LLM_RETRY_ATTEMPTS = 3
LLM_RETRY_MIN_WAIT = 1
LLM_RETRY_MAX_WAIT = 10


EXTRACT_PROMPT = PromptTemplate(
    input_variables=["text"],
    template="""Знайди у тексті фінальний результат судового рішення (1-2 речення).

Звертай особливу увагу на формулювання у резолютивній частині після слів "УХВАЛИВ", такі як:
"задовольнити", "відмовити", "задовольнити частково", "залишити без задоволення".

Документ:
{text}

Витягни фінальний результат рішення (1-2 речення):""",
)

CLASSIFY_PROMPT = PromptTemplate(
    input_variables=["result"],
    template="""Визнач статус судового рішення з точки зору нашого клієнта (позивача) на основі витягнутого результату. Цей аналіз призначений для юристів.

Правила визначення статусу:
- "Позитивне" — якщо судове рішення ухвалене на користь нашого клієнта (позивача), тобто ключові вимоги нашої сторони задоволено.
- "Негативне" — якщо рішення ухвалене не на користь нашого клієнта, тобто у задоволенні ключових вимог нашої сторони відмовлено.
- "Часткове" — якщо вимоги нашого клієнта задоволено частково або рішення містить змішані результати для нашої сторони.

ВАЖЛИВО:
* Аналізуй ТІЛЬКИ резолютивну частину рішення.
* Ігноруй опис справи, аргументи сторін та мотивувальну частину.
* Формулювання "залишити без задоволення" або "відмовити" завжди означають НЕГАТИВНЕ рішення.
* Не роби припущень.

Фінальний результат рішення:
{result}

Відповідай у наступному форматі:
Статус: [Позитивне / Негативне / Часткове]
Коментар: [1-2 речення, що пояснюють обґрунтування статусу]""",
)


def _is_valid_text(text: str) -> bool:
    letters = sum(c.isalpha() for c in text)
    return letters > 100


def extract_resolution_block(text: str) -> str:
    markers = ["У Х В А Л И В", "УХВАЛИВ"]
    for m in markers:
        if m in text:
            return text.split(m, 1)[1]
    return text[-3000:]


def _hard_rule_decision(text: str) -> DecisionEnum | None:
    t = text.lower()
    if "залишити без задоволення" in t or "відмовити у задоволенні" in t:
        return DecisionEnum.NEGATIVE
    if "задовольнити частково" in t:
        return DecisionEnum.PARTIAL
    if "задовольнити позов" in t and "частково" not in t:
        return DecisionEnum.POSITIVE
    return None


def _response_text_from_chain_result(result: Any) -> str:
    if hasattr(result, "content"):
        return result.content.strip()
    if isinstance(result, dict):
        out = result.get("text", result.get("content", "")).strip()
        if not out and result:
            out = str(next(iter(result.values()))).strip()
        return out
    return str(result).strip()


def fallback_keyword_decision(text: str) -> DecisionEnum:
    content_lower = text.lower()
    if "позитивне" in content_lower:
        return DecisionEnum.POSITIVE
    if "негативне" in content_lower:
        return DecisionEnum.NEGATIVE
    if "часткове" in content_lower:
        return DecisionEnum.PARTIAL
    return DecisionEnum.UNKNOWN


@retry(
    stop=stop_after_attempt(LLM_RETRY_ATTEMPTS),
    wait=wait_exponential(min=LLM_RETRY_MIN_WAIT, max=LLM_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
    reraise=True,
)
async def _ainvoke_with_timeout(
    chain: Runnable,
    input_dict: dict[str, str],
    timeout: float = DEFAULT_LLM_TIMEOUT,
) -> Any:
    return await asyncio.wait_for(chain.ainvoke(input_dict), timeout=timeout)


async def detect_status_with_llm(
    text: str,
    extract_chain: Runnable | None,
    classify_chain: Runnable | None,
    *,
    timeout: float = DEFAULT_LLM_TIMEOUT,
) -> DecisionEnum:
    resolution = extract_resolution_block(text)
    text_for_analysis = resolution[-8000:] if len(resolution) > 8000 else resolution

    if not _is_valid_text(text_for_analysis):
        logger.info("Text not valid for analysis (too few letters); skipping LLM")
        return DecisionEnum.UNKNOWN

    hard = _hard_rule_decision(text_for_analysis)
    if hard is not None:
        logger.debug("Hard rule matched: %s", hard)
        return hard

    if extract_chain is None or classify_chain is None:
        logger.info(
            "LLM chains not configured; using keyword fallback for decision"
        )
        return fallback_keyword_decision(text_for_analysis)

    try:
        result_text = _response_text_from_chain_result(
            await _ainvoke_with_timeout(
                extract_chain, {"text": text_for_analysis}, timeout=timeout
            )
        )
        if not result_text or result_text.startswith("Помилка"):
            result_text = result_text or ""

        response_text = _response_text_from_chain_result(
            await _ainvoke_with_timeout(
                classify_chain, {"result": result_text}, timeout=timeout
            )
        )
        return fallback_keyword_decision(response_text)
    except (TimeoutError, ConnectionError, OSError) as e:
        logger.warning(
            "LLM call failed after retries; using keyword fallback: %s",
            e,
            exc_info=False,
        )
        return fallback_keyword_decision(text_for_analysis)
    except Exception:
        logger.exception(
            "Unexpected error in detect_status_with_llm; using keyword fallback"
        )
        return fallback_keyword_decision(text_for_analysis)
