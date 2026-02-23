from __future__ import annotations

import asyncio
from datetime import date, timedelta

from tqdm.asyncio import tqdm  # type: ignore

from .file_handler import FileProcessor
from .repositories import TablesRepository, ViewRepository
from .schemas import (
    CompanyEnum,
    DateRange,
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

    @staticmethod
    def _yesterday_range() -> DateRange:
        today = date.today()
        yesterday = today - timedelta(days=1)
        return DateRange(
            start_year=yesterday.year,
            start_month=yesterday.month,
            start_day=yesterday.day,
            end_year=today.year,
            end_month=today.month,
            end_day=today.day,
        )

    @staticmethod
    def _format_date_range(date_range: DateRange) -> str:
        return (
            f"{date_range.start_year:04d}-{date_range.start_month:02d}-{date_range.start_day:02d} "
            f"-> {date_range.end_year:04d}-{date_range.end_month:02d}-{date_range.end_day:02d}"
        )

    async def run(self) -> None:
        await self.run_decision()

    async def run_decision(self, date_range: DateRange | None = None) -> None:
        target_range = date_range or self._yesterday_range()
        print(
            f"[{self._company.value}] decision: start, range={self._format_date_range(target_range)}"
        )
        records = await self._view_repo.all_recent(
            date_range=target_range,
            ilike_filter="рішен",
        )
        print(f"[{self._company.value}] decision: found {len(records)} records")

        semaphore = asyncio.Semaphore(10)
        success_count = 0
        error_count = 0

        async def process_record(record: message_document_DTO) -> None:
            nonlocal success_count, error_count
            async with semaphore:
                try:
                    result = await self._file_processor.process_decision(
                        record.local_path
                    )
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
                        date_of_issuance=None,
                        docType="рішен",
                        local_file_path=record.local_path,
                    )

                    await self._exec_repo.bulk_insert([exec_record])
                    success_count += 1

                except Exception as e:
                    error_count += 1
                    print(f"Помилка обробки запису {record.procNum}: {e}")

        tasks = []

        for record in records:
            tasks.append(asyncio.create_task(process_record(record)))

        await tqdm.gather(*tasks, desc="Processing records")
        print(
            f"[{self._company.value}] decision: done, success={success_count}, errors={error_count}"
        )

    async def run_exec(self, date_range: DateRange | None = None) -> None:
        target_range = date_range or self._yesterday_range()
        print(
            f"[{self._company.value}] exec: start, range={self._format_date_range(target_range)}"
        )
        records = await self._view_repo.all_recent(
            date_range=target_range,
            ilike_filter=[["викон", "лист"], ["викон", "докум"]],
        )
        print(f"[{self._company.value}] exec: found {len(records)} records")
        semaphore = asyncio.Semaphore(10)
        success_count = 0
        error_count = 0

        async def process_record(record: message_document_DTO) -> None:
            nonlocal success_count, error_count
            async with semaphore:
                try:
                    result = await self._file_processor.process_exec(record.local_path)
                    created_at = record.message_createdAt

                    exec_record = DocumentDecisionInsertDTO(
                        createdAt=created_at,
                        caseNum=record.caseNum,
                        procNum=record.procNum,
                        decision=DecisionEnum.UNKNOWN,
                        main_amount=result.main_amount if result else None,
                        court_fee=result.court_fee if result else None,
                        legal_aid=result.legal_aid if result else None,
                        collector=self._company.value,
                        date_of_decision=None,
                        date_of_issuance=(result.date_of_issuance if result else None),
                        docType="викон лист|докум",
                        local_file_path=record.local_path,
                    )

                    await self._exec_repo.bulk_insert([exec_record])
                    success_count += 1

                except Exception as e:
                    error_count += 1
                    print(f"Помилка обробки запису {record.procNum}: {e}")

        tasks = []

        for record in records:
            tasks.append(asyncio.create_task(process_record(record)))

        await tqdm.gather(*tasks, desc="Processing records")
        print(
            f"[{self._company.value}] exec: done, success={success_count}, errors={error_count}"
        )


__all__ = ["ParserService"]
