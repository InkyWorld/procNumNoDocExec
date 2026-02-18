from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from datetime import datetime
from itertools import islice
from typing import TypeVar

from sqlalchemy import MetaData, Table, and_, delete, func, insert, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from .models import DocsDecisionTable
from .schemas import (
    CompanyEnum,
    DocumentDecisionInsertDTO,
    message_document_DTO,
    DateRange,
)

T = TypeVar("T")


class ViewRepository(ABC):
    """Interface for reading records from view."""

    @abstractmethod
    async def all_recent(
        self,
        date_range: DateRange,
        ilike_filter: list[list[str]] | str | None,
    ) -> list[message_document_DTO]:
        """Return records pending processing; limit caps the number fetched."""


class TablesRepository(ABC):
    """Interface for writing processed records into procDocsDecision table."""

    @abstractmethod
    async def bulk_insert(
        self,
        records: list[DocumentDecisionInsertDTO],
    ) -> None:
        """Insert a new execution record and return the persisted entity."""

    @abstractmethod
    async def delete_all(self) -> None:
        """Delete all records from the table."""
        pass


class AsyncViewMessageDocumentRepository(ViewRepository):
    """Async implementation reading from view ProcNumWithoutVP."""

    def __init__(
        self, company: CompanyEnum, session_factory: async_sessionmaker[AsyncSession]
    ):
        self._session_factory = session_factory
        self.company: CompanyEnum = company

    def _get_reflected_view(self, session: Session) -> Table:
        return Table(
            f"_message_documents_{self.company.value}",
            MetaData(),
            autoload_with=session.connection(),
            schema="dbo",
        )

    async def all_recent(
        self,
        date_range: DateRange,
        ilike_filter: list[list[str]] | str | None,
    ) -> list[message_document_DTO]:
        async with self._session_factory() as session:
            # Викликаємо синхронну функцію рефлексії через run_sync
            procDocsDecision_view = await session.run_sync(self._get_reflected_view)
            #             yesterday = date.today() - timedelta(days=1)
            # yesterday_midnight = datetime.combine(yesterday, time.min)

            # stmt = select(procDocsDecision_view).where(
            #     procDocsDecision_view.c.createdAt >= yesterday_midnight
            # )
            # Повертаємо записи за локальним діапазоном 2026-01-21..2026-01-24.
            range_start = datetime(
                date_range.start_year, date_range.start_month, date_range.start_day
            )
            range_end = datetime(
                date_range.end_year, date_range.end_month, date_range.end_day
            )

            stmt = select(procDocsDecision_view).where(
                func.timezone("Europe/Kyiv", procDocsDecision_view.c.message_createdAt)
                >= range_start,
                func.timezone("Europe/Kyiv", procDocsDecision_view.c.message_createdAt)
                < range_end,
                procDocsDecision_view.c.local_path.isnot(None),
            )
            if ilike_filter:
                # 1️⃣ Якщо це рядок
                if isinstance(ilike_filter, str):
                    stmt = stmt.where(
                        procDocsDecision_view.c.message_description.ilike(
                            f"%{ilike_filter}%"
                        )
                    )

                # 2️⃣ Якщо це список
                if isinstance(ilike_filter, list):
                    # Перевіряємо: список списків?
                    stmt = stmt.where(
                        or_(
                            *[
                                and_(
                                    *[
                                        procDocsDecision_view.c.message_description.ilike(f"%{word}%")
                                        for word in group
                                    ]
                                )
                                for group in ilike_filter
                                if group
                            ]
                        )
                    )
            result = await session.execute(stmt)
            rows = result.mappings().all()
        records: list[message_document_DTO] = []
        for row in rows:
            # row._mapping надає доступ до колонок за назвою
            records.append(
                message_document_DTO(
                    message_createdAt=row["message_createdAt"],
                    message_description=row["message_description"],
                    procNum=row["procNum"],
                    caseNum=row["caseNum"],
                    local_path=row["local_path"],
                )
            )
        return records


class AsyncMessageDocumentDecisionRepository(TablesRepository):
    """Async implementation writing into procDocsDecision table."""

    def __init__(
        self, company: CompanyEnum, session_factory: async_sessionmaker[AsyncSession]
    ):
        self._session_factory = session_factory
        self.company: CompanyEnum = company
        table_name = (
            "docs_decision_ace" if company == CompanyEnum.Ace else "docs_decision_unit"
        )
        self._target_table = DocsDecisionTable.__table__.to_metadata(
            MetaData(),
            name=table_name,
            schema="dbo",
        )

    async def delete_all(self) -> None:
        """Видаляє всі записи з таблиці."""
        stmt = delete(self._target_table)

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

    async def bulk_insert(self, records: list[DocumentDecisionInsertDTO]) -> None:
        """
        Docstring for bulk_insert

        :param self: Description
        :param records: Description
        :type records: list[DocumentDecisionInsertDTO]
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
                    await session.execute(insert(self._target_table), batch)


__all__ = [
    "ViewRepository",
    "TablesRepository",
    "AsyncViewMessageDocumentRepository",
    "AsyncMessageDocumentDecisionRepository",
]
