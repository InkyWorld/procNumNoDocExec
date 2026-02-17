from __future__ import annotations

from datetime import date
from pathlib import Path
from decimal import Decimal
import unittest

from pydantic import ValidationError

from procnumnodocexec.execution_doc_llm import (
    ExecutionDocLLMResponse,
    _parse_date,
    extract_execution_doc_data_with_llm,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_file_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "windows-1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class ExecutionDocLLMTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_extracts_expected_values_for_1_html(self) -> None:
        text = _read_file_text(_project_root() / "data test html" / "1.html")
        result = await extract_execution_doc_data_with_llm(text, None, None)

        self.assertEqual(result.mode, "fallback")
        self.assertEqual(result.main_amount, Decimal("12724"))
        self.assertEqual(result.court_fee, Decimal("2422.40"))
        self.assertEqual(result.legal_aid, Decimal("4000"))
        self.assertEqual(result.execution_doc_issue_date, date(2026, 2, 3))
        self.assertEqual(result.main_amount_source, "regex")
        self.assertEqual(result.execution_doc_issue_date_source, "regex")
        self.assertIsNotNone(result.execution_doc_issue_date_snippet)

    async def test_fallback_extracts_expected_values_for_2_html(self) -> None:
        text = _read_file_text(_project_root() / "data test html" / "2.html")
        result = await extract_execution_doc_data_with_llm(text, None, None)

        self.assertEqual(result.main_amount, Decimal("38485"))
        self.assertIsNone(result.court_fee)
        self.assertIsNone(result.legal_aid)
        self.assertEqual(result.execution_doc_issue_date, date(2026, 2, 2))
        self.assertEqual(result.main_amount_source, "regex")
        self.assertEqual(result.execution_doc_issue_date_source, "regex")

    async def test_fallback_extracts_expected_values_for_3_html(self) -> None:
        text = _read_file_text(_project_root() / "data test html" / "3.html")
        result = await extract_execution_doc_data_with_llm(text, None, None)

        self.assertEqual(result.main_amount, Decimal("15750.90"))
        self.assertEqual(result.court_fee, Decimal("2422.40"))
        self.assertEqual(result.legal_aid, Decimal("3500.00"))
        self.assertEqual(result.execution_doc_issue_date, date(2026, 2, 3))
        self.assertEqual(result.court_fee_source, "regex")
        self.assertEqual(result.legal_aid_source, "regex")

    def test_parse_short_year_date(self) -> None:
        self.assertEqual(_parse_date("08.12.25"), date(2025, 12, 8))

    def test_llm_schema_validation_rejects_unknown_field(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionDocLLMResponse.model_validate(
                {
                    "main_amount_uah": 100,
                    "court_fee_uah": 10,
                    "legal_aid_uah": 5,
                    "execution_doc_issue_date": "2026-02-03",
                    "unexpected": "x",
                }
            )


if __name__ == "__main__":
    unittest.main()
