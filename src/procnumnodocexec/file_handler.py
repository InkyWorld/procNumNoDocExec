from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from aiofile import AIOFile

from .config import PROJECT_ROOT
from .decision_llm import detect_status_with_llm
from .execution_doc_llm import extract_execution_doc_data_with_llm
from .remote_client import RemoteFileClient
from .schemas import DecisionAnalysisResult


class FileProcessor(ABC):
    """Interface for handling files referenced by ProcNumWithoutVP records."""

    @abstractmethod
    async def process(self, record: str) -> DecisionAnalysisResult | None:
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

    async def _parse_decision_in_file(self, local_file: Path) -> DecisionAnalysisResult:
        async with AIOFile(local_file, "rb") as afd:
            raw_content: bytes | str = await afd.read()
            if isinstance(raw_content, bytes):
                content = self._decode_bytes(raw_content)
            else:
                content = str(raw_content)

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

    async def process(self, record: str) -> DecisionAnalysisResult | None:
        """
        Docstring for process

        :param self: Description
        :param records: Description
        :type records: list[str]
        :return: Description
        :rtype: Decision | None (None if process failed)
        """
        # 2. Визначаємо, куди зберігати тимчасово
        temp_dir = PROJECT_ROOT / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        local_file = None
        try:
            # pass str(...) to satisfy type checkers that expect a string path
            local_file = await self._client.download_file(str(record), temp_dir)
            result = await self._parse_decision_in_file(local_file)
            return result

        except Exception as e:
            print(f"Не вдалося обробити файл: {e}")
        finally:
            if local_file and local_file.exists():
                local_file.unlink()
            pass

        return None


__all__ = ["FileProcessor", "DecisionFileProcessor"]
