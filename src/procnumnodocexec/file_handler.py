from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from aiofile import AIOFile

from .config import PROJECT_ROOT
from .decision_llm import detect_status_with_llm
from .execution_doc_llm import extract_execution_doc_data_with_llm
from .remote_client import RemoteFileClient
from .schemas import DecisionAnalysisResult, ExecAnalysisResult

TResult = TypeVar("TResult")


class FileProcessor(ABC):
    """Interface for handling files referenced by ProcNumWithoutVP records."""

    @abstractmethod
    async def process_decision(self, record: str) -> DecisionAnalysisResult | None:
        """Process the file at local folder"""

    @abstractmethod
    async def process_exec(self, record: str) -> ExecAnalysisResult | None:
        """Process the file at local folder"""


class DecisionFileProcessor(FileProcessor):
    """Placeholder implementation to be replaced with real processing logic."""

    def __init__(
        self,
        extract_chain=None,
        classify_chain=None,
        execution_extract_chain=None,
        execution_classify_chain=None,
    ) -> None:
        self._extract_chain = extract_chain
        self._classify_chain = classify_chain
        self._execution_extract_chain = execution_extract_chain
        self._execution_classify_chain = execution_classify_chain
        self._client = RemoteFileClient()

    @staticmethod
    def _decode_bytes(raw_content: bytes) -> str:
        for encoding in ("windows-1251", "utf-8"):
            try:
                return raw_content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw_content.decode("utf-8", errors="replace")

    async def _read_text_file(self, local_file: Path) -> str:
        async with AIOFile(local_file, "rb") as afd:
            raw_content: bytes | str = await afd.read()
            if isinstance(raw_content, bytes):
                return self._decode_bytes(raw_content)
            return str(raw_content)

    async def _parse_decision_in_file(self, local_file: Path) -> DecisionAnalysisResult:
        content = await self._read_text_file(local_file)

        decision_result = await detect_status_with_llm(
            content,
            self._extract_chain,
            self._classify_chain,
        )
        exec_doc_result = await extract_execution_doc_data_with_llm(
            content,
            self._execution_extract_chain,
            self._execution_classify_chain,
        )
        return DecisionAnalysisResult(
            decision=decision_result.decision,
            main_amount=exec_doc_result.main_amount or decision_result.main_amount,
            court_fee=exec_doc_result.court_fee or decision_result.court_fee,
            legal_aid=exec_doc_result.legal_aid or decision_result.legal_aid,
            date_of_decision=decision_result.date_of_decision,
            execution_doc_issue_date=exec_doc_result.execution_doc_issue_date,
        )

    async def _parse_execution_doc_in_file(self, local_file: Path) -> ExecAnalysisResult:
        content = await self._read_text_file(local_file)
        exec_doc_result = await extract_execution_doc_data_with_llm(
            content,
            self._execution_extract_chain,
            self._execution_classify_chain,
        )
        return ExecAnalysisResult(
            date_of_issuance=exec_doc_result.execution_doc_issue_date,
            main_amount=exec_doc_result.main_amount,
            court_fee=exec_doc_result.court_fee,
            legal_aid=exec_doc_result.legal_aid,
        )

    async def _process_file(
        self,
        record: str,
        parser: Callable[[Path], Awaitable[TResult]],
    ) -> TResult | None:
        temp_dir = PROJECT_ROOT / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        local_file = None
        try:
            local_file = await self._client.download_file(str(record), temp_dir)
            return await parser(local_file)
        except Exception as e:
            print(f"Не вдалося обробити файл: {e}")
            return None
        finally:
            if local_file and local_file.exists():
                local_file.unlink()

    async def process_decision(self, record: str) -> DecisionAnalysisResult | None:
        return await self._process_file(record, self._parse_decision_in_file)

    async def process_exec(self, record: str) -> ExecAnalysisResult | None:
        return await self._process_file(record, self._parse_execution_doc_in_file)


__all__ = ["FileProcessor", "DecisionFileProcessor"]
