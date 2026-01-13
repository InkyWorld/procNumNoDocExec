from __future__ import annotations

from .file_handler import FileProcessor
from .repositories import ViewRepository, TablesRepository
from .schemas import DecisionEnum, ProcNumExecutionInsertDTO

from tqdm.asyncio import tqdm # type: ignore

class ParserService:
    """Coordinates reading view records, processing files, and writing results."""

    def __init__(
        self,
        view_repo: ViewRepository,
        exec_repo: TablesRepository,
        file_processor: FileProcessor,
    ) -> None:
        self._view_repo = view_repo
        self._exec_repo = exec_repo
        self._file_processor = file_processor

    async def run(self) -> None:
        """Process records from view and persist results.

        Args:
            decision: Decision to store with each inserted row.
            limit: Optional cap on number of records to process.

        Returns:
            Count of processed records.
        """

        records = await self._view_repo.all()
        exec_records: list[ProcNumExecutionInsertDTO] = []
        for record in tqdm(records, desc="Обробка файлів", unit="record"):
            try:
                original_local_path = record.original_local_path
                decision = await self._file_processor.process(original_local_path)
                exec_record = ProcNumExecutionInsertDTO(
                    received_date=record.updated_at,
                    case_number=record.case_num,
                    proceeding_number=record.proc_num,
                    decision=decision or DecisionEnum.UNKNOWN,
                    local_file_path=original_local_path,
                )
                exec_records.append(exec_record)
            except Exception as e:
                print(f"Помилка обробки запису {record.proc_num}: {e}")
        await self._exec_repo.bulk_insert(exec_records)


__all__ = ["ParserService"]
