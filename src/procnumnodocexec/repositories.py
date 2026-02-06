from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from datetime import datetime, timedelta
from itertools import islice
from typing import TypeVar

from sqlalchemy import MetaData, Table, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from .models import ProcNumNoDocExec
from .schemas import CompanyEnum, ProcNumExecutionInsertDTO, ProcNumWithoutVP_DTO

T = TypeVar("T")


class ViewRepository(ABC):
    """Interface for reading records from view."""

    @abstractmethod
    async def all_recent(self) -> list[ProcNumWithoutVP_DTO]:
        """Return records pending processing; limit caps the number fetched."""


class TablesRepository(ABC):
    """Interface for writing processed records into procNumNoDocExec table."""

    @abstractmethod
    async def bulk_insert(
        self,
        records: list[ProcNumExecutionInsertDTO],
    ) -> None:
        """Insert a new execution record and return the persisted entity."""

    @abstractmethod
    async def delete_all(self) -> None:
        """Delete all records from the table."""
        pass


class AsyncViewProcNumWithoutVPRepository(ViewRepository):
    """Async implementation reading from view ProcNumWithoutVP."""

    def __init__(
        self, company: CompanyEnum, session_factory: async_sessionmaker[AsyncSession]
    ):
        self._session_factory = session_factory
        self.company: CompanyEnum = company

    def _get_reflected_view(self, session: Session) -> Table:
        return Table(
            f"ProcNumWithoutVP{self.company.value}",
            MetaData(),
            autoload_with=session.connection(),
            schema="dbo",
        )

    async def all_recent(self) -> list[ProcNumWithoutVP_DTO]:
        async with self._session_factory() as session:
            # Викликаємо синхронну функцію рефлексії через run_sync
            procNumNoDocExec_view = await session.run_sync(self._get_reflected_view)
            #             yesterday = date.today() - timedelta(days=1)
            # yesterday_midnight = datetime.combine(yesterday, time.min)

            # stmt = select(procNumNoDocExec_view).where(
            #     procNumNoDocExec_view.c.createdAt >= yesterday_midnight
            # )
            # Повертаємо тільки записи за останні 7 днів за полем `createdAt`.
            seven_days_ago = datetime.utcnow() - timedelta(days=7)

            stmt = select(procNumNoDocExec_view).where(
                procNumNoDocExec_view.c.createdAt >= seven_days_ago
            )
            result = await session.execute(stmt)
            rows = result.mappings().all()

        records: list[ProcNumWithoutVP_DTO] = []
        for row in rows:
            # row._mapping надає доступ до колонок за назвою
            records.append(
                ProcNumWithoutVP_DTO(
                    created_at=row["createdAt"],
                    proc_num=row["procNum"],
                    case_num=row["caseNum"],
                    doc_type_name=row["docTypeName"],
                    description=row["description"],
                    original_local_path=row["originalLocalPath"],
                )
            )
        return records


class AsyncProcNumNoDocExecRepository(TablesRepository):
    """Async implementation writing into procNumNoDocExec table."""

    def __init__(
        self, company: CompanyEnum, session_factory: async_sessionmaker[AsyncSession]
    ):
        self._session_factory = session_factory
        self.company: CompanyEnum = company

    async def delete_all(self) -> None:
        """Видаляє всі записи з таблиці."""
        stmt = delete(ProcNumNoDocExec)

        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(stmt)

    @staticmethod
    def _chunked(iterable: Iterable[T], n: int) -> Iterator[list[T]]:
        """
        Розбиває ітерабельний об'єкт на списки (чанки) довжиною n.
        """
        it = iter(iterable)
        while batch := list(islice(it, n)):
            yield batch

    async def bulk_insert(self, records: list[ProcNumExecutionInsertDTO]) -> None:
        """
        Docstring for bulk_insert

        :param self: Description
        :param records: Description
        :type records: list[ProcNumExecutionInsertDTO]
        """
        # dataclasses may use slots and therefore have no __dict__; use asdict() which supports both
        values_list = [asdict(record) for record in records]

        # Defensive normalization: ensure required NOT NULL columns are present and non-null
        for v in values_list:
            if "local_file_path" not in v or v["local_file_path"] is None:
                v["local_file_path"] = ""

        async with self._session_factory() as session:
            async with session.begin():
                for batch in self._chunked(values_list, 2000):
                    await session.execute(insert(ProcNumNoDocExec), batch)


__all__ = [
    "ViewRepository",
    "TablesRepository",
    "AsyncViewProcNumWithoutVPRepository",
    "AsyncProcNumNoDocExecRepository",
]
