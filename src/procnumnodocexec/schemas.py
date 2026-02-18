from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class DecisionEnum(Enum):
    POSITIVE = "позитивне"
    NEGATIVE = "негативне"
    PARTIAL = "часткове"
    UNKNOWN = "невідоме"


@dataclass(slots=True)
class DecisionAnalysisResult:
    decision: DecisionEnum
    main_amount: Decimal | None = None
    court_fee: Decimal | None = None
    legal_aid: Decimal | None = None
    date_of_decision: date | None = None
    execution_doc_issue_date: date | None = None

@dataclass(slots=True)
class ExecAnalysisResult:
    date_of_issuance: date | None = None
    main_amount: Decimal | None = None
    court_fee: Decimal | None = None
    legal_aid: Decimal | None = None


class CompanyEnum(Enum):
    Ace = "Ace"
    Unit = "Unit"


@dataclass(slots=True)
class message_document_DTO:
    """Record sourced from view used for file processing."""

    message_createdAt: datetime
    message_description: str
    procNum: str
    caseNum: str
    local_path: str


@dataclass(slots=True)
class DocumentDecisionInsertDTO:
    """Entity abstraction for inserting data into DB."""

    createdAt: datetime
    caseNum: str
    procNum: str
    decision: DecisionEnum
    main_amount: Decimal | None
    court_fee: Decimal | None
    legal_aid: Decimal | None
    collector: str
    date_of_decision: date | None
    docType: str
    local_file_path: str
    date_of_issuance: date | None = None


@dataclass
class SMBConfig:
    server: str
    share: str
    username: str
    password: str
    domain: str = ""

@dataclass
class DateRange:
    start_year: int
    start_month: int
    start_day: int
    end_year: int
    end_month: int
    end_day: int
