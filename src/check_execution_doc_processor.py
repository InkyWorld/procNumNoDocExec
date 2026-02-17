from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

from decouple import AutoConfig
from dotenv import load_dotenv
from langchain_core.runnables import Runnable
from langchain_openai import AzureChatOpenAI

from procnumnodocexec.execution_doc_llm import (
    CLASSIFY_EXEC_DOC_PROMPT,
    EXTRACT_EXEC_DOC_PROMPT,
    extract_execution_doc_data_with_llm,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _get_config() -> AutoConfig:
    return AutoConfig(search_path=_project_root())


def _load_azure_config() -> dict[str, str]:
    config = _get_config()
    return {
        "endpoint": config("AZURE_OPENAI_ENDPOINT", default=""),
        "api_version": config("AZURE_OPENAI_API_VERSION", default="2025-04-01-preview"),
        "model": config("AZURE_MODEL", default="gpt-4.1-mini"),
        "api_key": config("AZURE_API_KEY", default=""),
    }


def _read_file_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "windows-1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _build_azure_chains(azure: dict[str, str]) -> tuple[Runnable | None, Runnable | None]:
    if not azure["endpoint"] or not azure["api_key"]:
        print("Missing Azure config. Using regex fallback (without LLM).")
        return None, None

    llm_kwargs: dict[str, Any] = {
        "azure_endpoint": azure["endpoint"].rstrip("/"),
        "api_key": azure["api_key"],
        "api_version": azure["api_version"],
        "temperature": 0,
    }
    try:
        llm = AzureChatOpenAI(azure_deployment=azure["model"], **llm_kwargs)
    except TypeError:
        llm = AzureChatOpenAI(deployment_name=azure["model"], **llm_kwargs)

    return EXTRACT_EXEC_DOC_PROMPT | llm, CLASSIFY_EXEC_DOC_PROMPT | llm


def _fmt_amount(value: Decimal | None) -> str:
    if value is None:
        return "None"
    return f"{value:.2f}"


async def main() -> None:
    load_dotenv()
    load_dotenv(_project_root() / ".env")

    azure = _load_azure_config()
    extract_chain, classify_chain = _build_azure_chains(azure)

    data_dir = Path(_get_config()("TEST_EXEC_DOC_PATH", default="data test html"))
    if not data_dir.is_absolute():
        data_dir = _project_root() / data_dir

    if not data_dir.exists():
        print(f"Test folder not found: {data_dir}")
        return

    files = sorted(data_dir.glob("*.html"))
    print(f"Processing {len(files)} files from {data_dir}\n")

    for path in files:
        content = _read_file_text(path)
        result = await extract_execution_doc_data_with_llm(
            content,
            extract_chain=extract_chain,
            classify_chain=classify_chain,
        )
        print(
            f"{path.name}: "
            f"mode={result.mode}, "
            f"main_amount={_fmt_amount(result.main_amount)}, "
            f"main_source={result.main_amount_source}, "
            f"main_conf={result.main_amount_confidence}, "
            f"court_fee={_fmt_amount(result.court_fee)}, "
            f"court_source={result.court_fee_source}, "
            f"court_conf={result.court_fee_confidence}, "
            f"legal_aid={_fmt_amount(result.legal_aid)}, "
            f"legal_source={result.legal_aid_source}, "
            f"legal_conf={result.legal_aid_confidence}, "
            f"execution_doc_issue_date={result.execution_doc_issue_date}, "
            f"date_source={result.execution_doc_issue_date_source}, "
            f"date_conf={result.execution_doc_issue_date_confidence}"
        )


if __name__ == "__main__":
    asyncio.run(main())
