from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .schemas import DecisionEnum

SCHEMA_NAME = "dbo"


class Base(DeclarativeBase):
    """Shared declarative base."""


class DocsDecisionTable(Base):
    __tablename__ = "docs_decision"
    __table_args__ = {"schema": SCHEMA_NAME}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Дата отримання документу"
    )
    caseNum: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Номер справи"
    )
    procNum: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Номер провадження"
    )
    decision: Mapped[DecisionEnum] = mapped_column(
        SAEnum(DecisionEnum, name="decision_enum", schema=SCHEMA_NAME),
        nullable=False,
        comment="Рішення (позитивне, негативне, часткове)",
    )
    main_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Основна сума (UAH)",
    )
    court_fee: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Судовий збір (UAH)",
    )
    legal_aid: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Правнича допомога (UAH)",
    )
    collector: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Стягувач",
    )
    date_of_decision: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Дата рішення (з тексту)",
    )
    docType: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Тип документу"
    )
    local_file_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="Посилання на локальний файл"
    )


__all__ = ["Base", "DocsDecisionTable", "SCHEMA_NAME"]
