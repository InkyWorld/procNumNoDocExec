from __future__ import annotations

from datetime import date

from .schemas import DecisionEnum
from sqlalchemy import DateTime, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base."""


class DocsDecisionTable(Base):
    __tablename__ = "docs_decision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    createdAt: Mapped[date] = mapped_column(
        DateTime, nullable=False, comment="Дата отримання документу"
    )
    caseNum: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Номер справи"
    )
    procNum: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Номер провадження"
    )
    decision: Mapped[DecisionEnum] = mapped_column(
        SAEnum(DecisionEnum, name="decision_enum"),
        nullable=False,
        comment="Рішення (позитивне, негативне, часткове)",
    )
    docType: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Тип документу"
    )
    local_file_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="Посилання на локал файл"
    )


__all__ = ["Base", "DocsDecisionTable"]
