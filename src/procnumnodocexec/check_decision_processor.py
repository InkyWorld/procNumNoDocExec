from __future__ import annotations

import asyncio
from pathlib import Path

from decouple import AutoConfig
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI

from .decision_llm import (
    CLASSIFY_PROMPT,
    EXTRACT_PROMPT,
    detect_status_with_llm,
)
from .file_handler import DecisionFileProcessor


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _get_config():
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
    """Read file content; try UTF-8 then Windows-1251."""
    raw = path.read_bytes()
    for encoding in ("utf-8", "windows-1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


async def main() -> None:
    load_dotenv()
    load_dotenv(_project_root() / ".env")

    project_root = _project_root()
    azure = _load_azure_config()

    if not azure["endpoint"] or not azure["api_key"]:
        print("Missing Azure config. Set in .env: AZURE_OPENAI_ENDPOINT, AZURE_API_KEY")
        print("Using keyword-only fallback (no LLM).")
        extract_chain = None
        classify_chain = None
    else:
        try:
            llm = AzureChatOpenAI(
                azure_endpoint=azure["endpoint"].rstrip("/"),
                api_key=azure["api_key"],
                api_version=azure["api_version"],
                azure_deployment=azure["model"],
                temperature=0,
            )
        except TypeError:
            llm = AzureChatOpenAI(
                azure_endpoint=azure["endpoint"].rstrip("/"),
                api_key=azure["api_key"],
                api_version=azure["api_version"],
                deployment_name=azure["model"],
                temperature=0,
            )
        extract_chain = EXTRACT_PROMPT | llm
        classify_chain = CLASSIFY_PROMPT | llm
        print("Using Azure OpenAI:", azure["model"])

    file_processor = DecisionFileProcessor(
        extract_chain=extract_chain, classify_chain=classify_chain
    )

    archive_path = _get_config()(
        "TEST_ARCHIVE_PATH",
        default=str(project_root / "src" / "New Архив WinRAR"),
    )
    archive_dir = Path(archive_path)
    if not archive_dir.is_absolute():
        archive_dir = project_root / archive_dir

    if not archive_dir.exists():
        print(f"Archive folder not found: {archive_dir}")
        return

    files = sorted(archive_dir.glob("*.html"))
    if not files:
        files = sorted(archive_dir.iterdir())
    print(f"Testing {len(files)} files from {archive_dir}\n")

    for path in files:
        if not path.is_file():
            continue
        try:
            content = _read_file_text(path)
            decision = await detect_status_with_llm(
                content,
                file_processor._extract_chain,
                file_processor._classify_chain,
            )
            print(f"  {path.name}  ->  {decision.value}")
        except Exception as e:
            print(f"  {path.name}  ->  ERROR: {e}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
