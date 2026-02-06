from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DecisionEnum(Enum):
    POSITIVE = "позитивне"
    NEGATIVE = "негативне"
    PARTIAL = "часткове"
    UNKNOWN = "невідоме"

class CompanyEnum(Enum):
    Ace = "Ace"
    Unit = "Unit"

@dataclass(slots=True)
class message_document_DTO:
    """Record sourced from view used for file processing."""
    created_at: datetime
    proc_num: str
    case_num: str
    doc_type_name: str
    description: str
    original_local_path: str

@dataclass(slots=True)
class DocumentDecisionInsertDTO:
    """Entity abstraction for inserting data into DB."""
    created_at: datetime
    case_number: str
    proceeding_number: str
    decision: DecisionEnum
    local_file_path: str

@dataclass
class SMBConfig:
    server: str
    share: str
    username: str
    password: str
    domain: str = ""



