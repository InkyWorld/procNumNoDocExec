from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from procnumnodocexec.schemas import DecisionEnum



class Base(DeclarativeBase):
    """Shared declarative base."""


class ProcNumNoDocExec(Base):
    __tablename__ = "procNumNoDocExec"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    received_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Дата отримання документу"
    )
    case_number: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Номер справи"
    )
    proceeding_number: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Номер провадження"
    )
    decision: Mapped[DecisionEnum] = mapped_column(
        SAEnum(DecisionEnum, name="decision_enum"),
        nullable=False,
        comment="Рішення (позитивне, негативне, часткове)",
    )
    local_file_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="Посилання на локал файл"
    )



__all__ = ["Base", "ProcNumNoDocExec"]
