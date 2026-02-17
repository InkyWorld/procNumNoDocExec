from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .schemas import DecisionAnalysisResult, DecisionEnum

logger = logging.getLogger(__name__)

UK_MONTHS = {
    "січня": 1,
    "лютого": 2,
    "березня": 3,
    "квітня": 4,
    "травня": 5,
    "червня": 6,
    "липня": 7,
    "серпня": 8,
    "вересня": 9,
    "жовтня": 10,
    "листопада": 11,
    "грудня": 12,
}


# Timeout per LLM call
DEFAULT_LLM_TIMEOUT = 60
# Retry: 3 attempts
LLM_RETRY_ATTEMPTS = 3
LLM_RETRY_MIN_WAIT = 1
LLM_RETRY_MAX_WAIT = 10


EXTRACT_PROMPT = PromptTemplate(
    input_variables=["text"],
    template="""Знайди у тексті резолютивну частину рішення.

Звертай особливу увагу на формулювання після слів "УХВАЛИВ" / "ВИРІШИВ" / "ПОСТАНОВИВ".
Поверни 10-20 речень резолютивної частини, включаючи фрази зі сумами (стягнення, судовий збір, правнича допомога).

Документ:
{text}

Витягни резолютивну частину (всю доступну інформацію):""",
)

CLASSIFY_PROMPT = PromptTemplate(
    input_variables=["result"],
    template="""На основі витягнутого результату (резолютивної частини) визнач:
1) Статус рішення для нашого клієнта (позивача).
2) Основну суму стягнення (якщо є).
3) Судовий збір (якщо є).
4) Правничу допомогу (якщо є).
5) Дату рішення, яка зазвичай вгорі документа.

Правила визначення статусу:
- "Позитивне" — якщо рішення на користь позивача.
- "Негативне" — якщо у задоволенні вимог відмовлено.
- "Часткове" — якщо вимоги задоволено частково або є змішані результати.
- Якщо статус неможливо визначити з резолютивної частини, повертай "Невідоме".

ВАЖЛИВО:
* Аналізуй ТІЛЬКИ резолютивну частину рішення.
* Не вигадуй суми. Якщо сума не вказана, поверни null.
* Сума може бути вказана з копійками або без.
* Суми повертай у гривнях як число з крапкою (наприклад 12345.67), без тексту і без пробілів.
* Дату повертай у форматі yyyy-mm-dd або null.

Результат:
{result}

Відповідай ТІЛЬКИ у валідному JSON без пояснень:
{{
    "status": "Позитивне | Негативне | Часткове | Невідоме",
    "main_amount_uah": 12345.67,
    "court_fee_uah": 123.45,
    "legal_aid_uah": 1000.00,
    "decision_date": "2025-12-02"
}}
""",
)


def _is_valid_text(text: str) -> bool:
    letters = sum(c.isalpha() for c in text)
    return letters > 100


def _normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_resolution_block(text: str) -> str:
    normalized = _normalize_text(text)
    marker_re = re.compile(
        r"(у\s*х\s*в\s*а\s*л\s*и\s*в|в\s*и\s*р\s*і\s*ш\s*и\s*в|п\s*о\s*с\s*т\s*а\s*н\s*о\s*в\s*и\s*в)",
        re.IGNORECASE,
    )
    match = None
    for m in marker_re.finditer(normalized):
        tail = normalized[m.end() : m.end() + 6]
        if ":" in tail or " -" in tail or "–" in tail:
            match = m
            break
        if match is None:
            match = m
    if match:
        return normalized[match.end() :]
    return normalized[-3000:]


def _response_text_from_chain_result(result: Any) -> str:
    if hasattr(result, "content"):
        return result.content.strip()
    if isinstance(result, dict):
        out = result.get("text", result.get("content", "")).strip()
        if not out and result:
            out = str(next(iter(result.values()))).strip()
        return out
    return str(result).strip()


def _extract_json_block(text: str) -> str:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else text


def _parse_decision_status(value: str | None) -> DecisionEnum | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if "позитив" in normalized:
        return DecisionEnum.POSITIVE
    if "негатив" in normalized:
        return DecisionEnum.NEGATIVE
    if "частков" in normalized:
        return DecisionEnum.PARTIAL
    if "невідом" in normalized:
        return DecisionEnum.UNKNOWN
    return None


def _parse_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a"}:
        return None
    cleaned = text.replace("\xa0", " ").replace(" ", "")
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    cleaned = re.sub(r"[^0-9.-]", "", cleaned)
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a"}:
        return None

    iso_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", text)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(1))
        except ValueError:
            pass

    try:
        return date.fromisoformat(text)
    except ValueError:
        pass

    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if match:
        day, month, year = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    word_month_match = re.search(
        r"['\"«»„“”]?\s*(\d{1,2})\s*['\"«»„“”]?\s+([а-щьюяіїєґ']+)\s+(\d{4})(?:\s*(?:року|р\.?))?",
        text.lower(),
    )
    if word_month_match:
        day, month_name, year = word_month_match.groups()
        month = UK_MONTHS.get(month_name)
        if month is not None:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None

    return None


def _extract_date_from_header(text: str) -> date | None:
    header = _normalize_text(text)[:1200]
    candidate_patterns = [
        r"\d{4}-\d{1,2}-\d{1,2}",
        r"\d{1,2}\.\d{1,2}\.\d{4}",
        r"['\"«»„“”]?\s*\d{1,2}\s*['\"«»„“”]?\s+[а-щьюяіїєґ']+\s+\d{4}(?:\s*(?:року|р\.?))?",
    ]
    matches: list[tuple[int, str]] = []
    for pattern in candidate_patterns:
        for m in re.finditer(pattern, header, flags=re.IGNORECASE):
            matches.append((m.start(), m.group(0)))

    for _, candidate in sorted(matches, key=lambda x: x[0]):
        parsed = _parse_date(candidate)
        if parsed is not None:
            return parsed

    return None


def fallback_keyword_decision(text: str) -> DecisionEnum:
    content_lower = _normalize_text(text).lower()
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
) -> DecisionAnalysisResult:
    resolution = extract_resolution_block(text)
    text_for_analysis = resolution[-8000:] if len(resolution) > 8000 else resolution
    header_text = _normalize_text(text)[:3000]
    logger.debug(
        "Resolution block length=%s, head=%r",
        len(text_for_analysis),
        text_for_analysis[:500],
    )

    if extract_chain is None or classify_chain is None:
        logger.info("LLM chains not configured; using keyword fallback for decision")
        return DecisionAnalysisResult(
            decision=fallback_keyword_decision(text_for_analysis)
        )

    try:
        result_text = _response_text_from_chain_result(
            await _ainvoke_with_timeout(
                extract_chain, {"text": text_for_analysis}, timeout=timeout
            )
        )
        logger.debug(
            "Extract LLM result length=%s, head=%r",
            len(result_text),
            result_text[:500],
        )
        if not result_text or result_text.startswith("Помилка"):
            result_text = ""
        if not result_text:
            result_text = text_for_analysis

        classify_input = result_text
        if text_for_analysis and text_for_analysis not in classify_input:
            classify_input = (
                f"{classify_input}\n\nРезолютивна частина:\n{text_for_analysis}"
            )
        if header_text and header_text not in classify_input:
            classify_input = f"{classify_input}\n\nШапка документа:\n{header_text}"
        response_text = _response_text_from_chain_result(
            await _ainvoke_with_timeout(
                classify_chain, {"result": classify_input}, timeout=timeout
            )
        )
        logger.debug(
            "Classify LLM response length=%s, head=%r",
            len(response_text),
            response_text[:500],
        )
        json_text = _extract_json_block(response_text)
        logger.debug("JSON block extracted: %r", json_text)
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError:
            logger.debug("Failed to parse JSON from LLM response")
        logger.debug("Parsed JSON: %s", parsed)

        decision = _parse_decision_status(parsed.get("status")) if parsed else None
        if decision is None:
            decision = fallback_keyword_decision(response_text)
        parsed_date = _parse_date(parsed.get("decision_date")) if parsed else None
        if parsed_date is None:
            parsed_date = _extract_date_from_header(header_text)

        return DecisionAnalysisResult(
            decision=decision,
            main_amount=_parse_amount(parsed.get("main_amount_uah"))
            if parsed
            else None,
            court_fee=_parse_amount(parsed.get("court_fee_uah")) if parsed else None,
            legal_aid=_parse_amount(parsed.get("legal_aid_uah")) if parsed else None,
            date_of_decision=parsed_date,
        )
    except (TimeoutError, ConnectionError, OSError) as e:
        logger.warning(
            "LLM call failed after retries; using keyword fallback: %s",
            e,
            exc_info=False,
        )
        return DecisionAnalysisResult(
            decision=fallback_keyword_decision(text_for_analysis)
        )
    except Exception:
        logger.exception(
            "Unexpected error in detect_status_with_llm; using keyword fallback"
        )
        return DecisionAnalysisResult(
            decision=fallback_keyword_decision(text_for_analysis)
        )
