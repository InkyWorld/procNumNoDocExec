from __future__ import annotations

import asyncio

from tqdm.asyncio import tqdm  # type: ignore

from .file_handler import FileProcessor
from .repositories import TablesRepository, ViewRepository
from .schemas import (
    CompanyEnum,
    DecisionAnalysisResult,
    DecisionEnum,
    DocumentDecisionInsertDTO,
    message_document_DTO,
)


class ParserService:
    """Coordinates reading view records, processing files, and writing results."""

    def __init__(
        self,
        view_repo: ViewRepository,
        exec_repo: TablesRepository,
        file_processor: FileProcessor,
        company: CompanyEnum,
    ) -> None:
        self._view_repo = view_repo
        self._exec_repo = exec_repo
        self._file_processor = file_processor
        self._company = company

    async def run(self) -> None:
        records = await self._view_repo.all_recent()

        semaphore = asyncio.Semaphore(10)

        async def process_record(record: message_document_DTO) -> None:
            async with semaphore:
                try:
                    result = await self._file_processor.process(record.local_path)
                    created_at = record.message_createdAt

                    if isinstance(result, DecisionEnum):
                        result = DecisionAnalysisResult(decision=result)

                    exec_record = DocumentDecisionInsertDTO(
                        createdAt=created_at,
                        caseNum=record.caseNum,
                        procNum=record.procNum,
                        decision=(
                            result.decision
                            if result is not None
                            else DecisionEnum.UNKNOWN
                        ),
                        main_amount=result.main_amount if result else None,
                        court_fee=result.court_fee if result else None,
                        legal_aid=result.legal_aid if result else None,
                        collector=self._company.value,
                        date_of_decision=(result.date_of_decision if result else None),
                        docType="рішен",
                        local_file_path=record.local_path,
                    )

                    await self._exec_repo.bulk_insert([exec_record])

                except Exception as e:
                    print(f"Помилка обробки запису {record.procNum}: {e}")

        tasks = []

        for record in records:
            tasks.append(asyncio.create_task(process_record(record)))

        await tqdm.gather(*tasks, desc="Processing records")


__all__ = ["ParserService"]
