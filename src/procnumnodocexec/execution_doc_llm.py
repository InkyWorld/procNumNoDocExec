from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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

DEFAULT_LLM_TIMEOUT = 60
LLM_RETRY_ATTEMPTS = 3
LLM_RETRY_MIN_WAIT = 1
LLM_RETRY_MAX_WAIT = 10


@dataclass(slots=True)
class ExecutionDocAnalysisResult:
    main_amount: Decimal | None = None
    court_fee: Decimal | None = None
    legal_aid: Decimal | None = None
    execution_doc_issue_date: date | None = None
    mode: str = "fallback"
    main_amount_source: str | None = None
    court_fee_source: str | None = None
    legal_aid_source: str | None = None
    execution_doc_issue_date_source: str | None = None
    main_amount_confidence: float | None = None
    court_fee_confidence: float | None = None
    legal_aid_confidence: float | None = None
    execution_doc_issue_date_confidence: float | None = None
    main_amount_snippet: str | None = None
    court_fee_snippet: str | None = None
    legal_aid_snippet: str | None = None
    execution_doc_issue_date_snippet: str | None = None


class ExecutionDocLLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_amount_uah: Decimal | None = None
    court_fee_uah: Decimal | None = None
    legal_aid_uah: Decimal | None = None
    execution_doc_issue_date: date | None = None

    @field_validator("main_amount_uah", "court_fee_uah", "legal_aid_uah", mode="before")
    @classmethod
    def _validate_amount_field(cls, value: Any) -> Decimal | None:
        parsed = _parse_amount(value)
        if value is None:
            return None
        if parsed is None:
            raise ValueError(f"Invalid amount format: {value!r}")
        return parsed

    @field_validator("execution_doc_issue_date", mode="before")
    @classmethod
    def _validate_issue_date_field(cls, value: Any) -> date | None:
        if value is None:
            return None
        parsed = _parse_date(value)
        if parsed is None:
            raise ValueError(f"Invalid date format: {value!r}")
        return parsed


EXTRACT_EXEC_DOC_PROMPT = PromptTemplate(
    input_variables=["text"],
    template="""Знайди у тексті фрагменти, які містять:
1) Основну суму стягнення за виконавчим листом (зазвичай заборгованість за кредитним договором).
2) Судовий збір або судові витрати.
3) Витрати на правничу (правову) допомогу.
4) Дату видачі виконавчого листа / виконавчого документа.

Витягни 8-20 найрелевантніших речень/рядків без пояснень.

Документ:
{text}
""",
)

CLASSIFY_EXEC_DOC_PROMPT = PromptTemplate(
    input_variables=["result"],
    template="""На основі фрагментів визнач:
1) main_amount_uah: основна сума стягнення.
2) court_fee_uah: сума судового збору/судових витрат.
3) legal_aid_uah: сума правничої допомоги.
4) execution_doc_issue_date: дата видачі виконавчого документа.

Правила:
- Не вигадуй значення. Якщо поля немає, поверни null.
- Суми повертай як число в гривнях (крапка як десятковий роздільник), без тексту.
- Дату повертай у форматі yyyy-mm-dd або null.
- Для execution_doc_issue_date використовуй саме фразу про видачу виконавчого листа/документа
  ("Виконавчий лист видано", "Дата видачі виконавчого листа" тощо), а не дату рішення.

Текст:
{result}

Відповідай тільки валідним JSON:
{{
  "main_amount_uah": 12345.67,
  "court_fee_uah": 123.45,
  "legal_aid_uah": 1000.00,
  "execution_doc_issue_date": "2026-02-03"
}}
""",
)


def _normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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

    dot_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if dot_match:
        day, month, year = dot_match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    short_dot_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2})(?!\d)", text)
    if short_dot_match:
        day, month, year = short_dot_match.groups()
        yy = int(year)
        full_year = 2000 + yy if yy <= 69 else 1900 + yy
        try:
            return date(full_year, int(month), int(day))
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


def _find_first_amount_by_patterns(text: str, patterns: list[str]) -> Decimal | None:
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = _parse_amount(match.group(1))
            if value is not None:
                return value
    return None


def _build_snippet(text: str, start: int, end: int, pad: int = 80) -> str:
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    return text[left:right].strip()


def _find_first_amount_with_snippet(
    text: str, patterns: list[str]
) -> tuple[Decimal | None, str | None]:
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = _parse_amount(match.group(1))
            if value is not None:
                snippet = _build_snippet(text, match.start(), match.end())
                return value, snippet
    return None, None


def _extract_amount_near_keyword(text: str, keyword_pattern: str) -> Decimal | None:
    amount_pattern = re.compile(
        r"([0-9][0-9\s.,]*)(?:\s*\([^)]{1,120}\))?\s*(?:грн\.?|грив[а-я]*)",
        flags=re.IGNORECASE,
    )
    for keyword_match in re.finditer(keyword_pattern, text, flags=re.IGNORECASE):
        start = max(0, keyword_match.start() - 220)
        end = min(len(text), keyword_match.end() + 180)
        window = text[start:end]

        candidates: list[tuple[int, Decimal]] = []
        for amount_match in amount_pattern.finditer(window):
            parsed = _parse_amount(amount_match.group(1))
            if parsed is None:
                continue
            absolute_start = start + amount_match.start()
            distance = abs(absolute_start - keyword_match.start())
            candidates.append((distance, parsed))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
    return None


def _extract_amount_near_keyword_with_snippet(
    text: str, keyword_pattern: str
) -> tuple[Decimal | None, str | None]:
    amount_pattern = re.compile(
        r"([0-9][0-9\s.,]*)(?:\s*\([^)]{1,120}\))?\s*(?:грн\.?|грив[а-я]*)",
        flags=re.IGNORECASE,
    )
    for keyword_match in re.finditer(keyword_pattern, text, flags=re.IGNORECASE):
        start = max(0, keyword_match.start() - 220)
        end = min(len(text), keyword_match.end() + 180)
        window = text[start:end]

        candidates: list[tuple[int, Decimal, int, int]] = []
        for amount_match in amount_pattern.finditer(window):
            parsed = _parse_amount(amount_match.group(1))
            if parsed is None:
                continue
            absolute_start = start + amount_match.start()
            absolute_end = start + amount_match.end()
            distance = abs(absolute_start - keyword_match.start())
            candidates.append((distance, parsed, absolute_start, absolute_end))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            _, parsed, abs_start, abs_end = candidates[0]
            return parsed, _build_snippet(text, abs_start, abs_end)
    return None, None


def _fallback_extract_main_amount(text: str) -> tuple[Decimal | None, str | None]:
    patterns = [
        r"заборгован(?:ість|ості).{0,500}?у\s+розмірі\s*([0-9][0-9\s.,]*)",
        r"загальн(?:у|ої)\s+сум[ауи].{0,120}?([0-9][0-9\s.,]*)",
    ]
    return _find_first_amount_with_snippet(text, patterns)


def _fallback_extract_court_fee(text: str) -> tuple[Decimal | None, str | None]:
    explicit_after, explicit_snippet = _find_first_amount_with_snippet(
        text,
        [
            r"судов(?:ий|ого|і|их)\s+(?:збір|витрат).{0,180}?([0-9][0-9\s.,]*)\s*(?:грн\.?|грив[а-я]*)",
        ],
    )
    if explicit_after is not None:
        return explicit_after, explicit_snippet
    return _extract_amount_near_keyword_with_snippet(
        text, r"судов(?:ий|ого|і|их)\s+(?:збір|витрат)"
    )


def _fallback_extract_legal_aid(text: str) -> tuple[Decimal | None, str | None]:
    return _extract_amount_near_keyword_with_snippet(text, r"правнич(?:у|ої|а)\s+допомог")


def _fallback_extract_issue_date(text: str) -> tuple[date | None, str | None]:
    patterns = [
        r"(?:Виконавч(?:ий|ого)\s+лист(?:а)?\s+видан[оаі]\s*:?\s*)([^<\n]{0,120})",
        r"(?:Дата\s+видачі\s+виконавч(?:ого|ий)\s+лист(?:а)?\s*:?\s*)([^<\n]{0,120})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            parsed = _parse_date(match.group(1))
            if parsed is not None:
                return parsed, _build_snippet(text, match.start(), match.end())

    for m in re.finditer(r"(\d{1,2}\.\d{1,2}\.\d{4})", text):
        left = text[max(0, m.start() - 90) : m.start()].lower()
        if "виконавч" in left and ("видан" in left or "видач" in left):
            parsed = _parse_date(m.group(1))
            if parsed is not None:
                return parsed, _build_snippet(text, m.start(), m.end())
    return None, None


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


def _regex_fallback_result(text: str) -> ExecutionDocAnalysisResult:
    normalized = _normalize_text(text)
    main_amount, main_snippet = _fallback_extract_main_amount(normalized)
    court_fee, court_snippet = _fallback_extract_court_fee(normalized)
    legal_aid, legal_snippet = _fallback_extract_legal_aid(normalized)
    issue_date, issue_date_snippet = _fallback_extract_issue_date(normalized)

    return ExecutionDocAnalysisResult(
        main_amount=main_amount,
        court_fee=court_fee,
        legal_aid=legal_aid,
        execution_doc_issue_date=issue_date,
        mode="fallback",
        main_amount_source="regex" if main_amount is not None else None,
        court_fee_source="regex" if court_fee is not None else None,
        legal_aid_source="regex" if legal_aid is not None else None,
        execution_doc_issue_date_source="regex" if issue_date is not None else None,
        main_amount_confidence=0.75 if main_amount is not None else None,
        court_fee_confidence=0.80 if court_fee is not None else None,
        legal_aid_confidence=0.80 if legal_aid is not None else None,
        execution_doc_issue_date_confidence=0.92 if issue_date is not None else None,
        main_amount_snippet=main_snippet,
        court_fee_snippet=court_snippet,
        legal_aid_snippet=legal_snippet,
        execution_doc_issue_date_snippet=issue_date_snippet,
    )


async def extract_execution_doc_data_with_llm(
    text: str,
    extract_chain: Runnable | None,
    classify_chain: Runnable | None,
    *,
    timeout: float = DEFAULT_LLM_TIMEOUT,
) -> ExecutionDocAnalysisResult:
    text_for_analysis = _normalize_text(text)[-12000:]

    if extract_chain is None or classify_chain is None:
        return _regex_fallback_result(text_for_analysis)

    try:
        extracted = _response_text_from_chain_result(
            await _ainvoke_with_timeout(
                extract_chain, {"text": text_for_analysis}, timeout=timeout
            )
        )
        if not extracted:
            extracted = text_for_analysis
        response = _response_text_from_chain_result(
            await _ainvoke_with_timeout(
                classify_chain, {"result": extracted}, timeout=timeout
            )
        )
        parsed_json_text = _extract_json_block(response)
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(parsed_json_text)
        except json.JSONDecodeError:
            logger.debug("Failed to parse JSON in execution doc classifier response")
        validated: ExecutionDocLLMResponse | None = None
        if parsed:
            try:
                validated = ExecutionDocLLMResponse.model_validate(parsed)
            except ValidationError as exc:
                logger.debug("Execution doc LLM JSON schema validation failed: %s", exc)

        llm_result = ExecutionDocAnalysisResult(
            main_amount=validated.main_amount_uah if validated else None,
            court_fee=validated.court_fee_uah if validated else None,
            legal_aid=validated.legal_aid_uah if validated else None,
            execution_doc_issue_date=(
                validated.execution_doc_issue_date if validated else None
            ),
            mode="llm",
            main_amount_source="llm" if validated and validated.main_amount_uah is not None else None,
            court_fee_source="llm" if validated and validated.court_fee_uah is not None else None,
            legal_aid_source="llm" if validated and validated.legal_aid_uah is not None else None,
            execution_doc_issue_date_source=(
                "llm" if validated and validated.execution_doc_issue_date is not None else None
            ),
            main_amount_confidence=0.88 if validated and validated.main_amount_uah is not None else None,
            court_fee_confidence=0.88 if validated and validated.court_fee_uah is not None else None,
            legal_aid_confidence=0.88 if validated and validated.legal_aid_uah is not None else None,
            execution_doc_issue_date_confidence=(
                0.90 if validated and validated.execution_doc_issue_date is not None else None
            ),
        )

        fallback_result = _regex_fallback_result(text_for_analysis)
        return ExecutionDocAnalysisResult(
            main_amount=llm_result.main_amount or fallback_result.main_amount,
            court_fee=llm_result.court_fee or fallback_result.court_fee,
            legal_aid=llm_result.legal_aid or fallback_result.legal_aid,
            execution_doc_issue_date=(
                llm_result.execution_doc_issue_date
                or fallback_result.execution_doc_issue_date
            ),
            mode=(
                "llm+fallback"
                if (
                    (llm_result.main_amount is None and fallback_result.main_amount is not None)
                    or (llm_result.court_fee is None and fallback_result.court_fee is not None)
                    or (llm_result.legal_aid is None and fallback_result.legal_aid is not None)
                    or (
                        llm_result.execution_doc_issue_date is None
                        and fallback_result.execution_doc_issue_date is not None
                    )
                )
                else "llm"
            ),
            main_amount_source=llm_result.main_amount_source or fallback_result.main_amount_source,
            court_fee_source=llm_result.court_fee_source or fallback_result.court_fee_source,
            legal_aid_source=llm_result.legal_aid_source or fallback_result.legal_aid_source,
            execution_doc_issue_date_source=(
                llm_result.execution_doc_issue_date_source
                or fallback_result.execution_doc_issue_date_source
            ),
            main_amount_confidence=llm_result.main_amount_confidence or fallback_result.main_amount_confidence,
            court_fee_confidence=llm_result.court_fee_confidence or fallback_result.court_fee_confidence,
            legal_aid_confidence=llm_result.legal_aid_confidence or fallback_result.legal_aid_confidence,
            execution_doc_issue_date_confidence=(
                llm_result.execution_doc_issue_date_confidence
                or fallback_result.execution_doc_issue_date_confidence
            ),
            main_amount_snippet=llm_result.main_amount_snippet or fallback_result.main_amount_snippet,
            court_fee_snippet=llm_result.court_fee_snippet or fallback_result.court_fee_snippet,
            legal_aid_snippet=llm_result.legal_aid_snippet or fallback_result.legal_aid_snippet,
            execution_doc_issue_date_snippet=(
                llm_result.execution_doc_issue_date_snippet
                or fallback_result.execution_doc_issue_date_snippet
            ),
        )
    except (TimeoutError, ConnectionError, OSError):
        logger.warning("Execution doc LLM failed; using regex fallback", exc_info=False)
        return _regex_fallback_result(text_for_analysis)
    except Exception:
        logger.warning(
            "Unexpected execution doc extraction error; using regex fallback",
            exc_info=False,
        )
        return _regex_fallback_result(text_for_analysis)


__all__ = [
    "CLASSIFY_EXEC_DOC_PROMPT",
    "EXTRACT_EXEC_DOC_PROMPT",
    "ExecutionDocAnalysisResult",
    "extract_execution_doc_data_with_llm",
]
