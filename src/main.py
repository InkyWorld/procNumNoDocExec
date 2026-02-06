from __future__ import annotations

import asyncio

from procnumnodocexec import (
    AsyncMessageDocumentDecisionRepository,
    AsyncViewMessageDocumentRepository,
    CompanyEnum,
    DecisionFileProcessor,
    ParserService,
    get_async_sessionmaker,
)
from procnumnodocexec.llm_provider import get_azure_chains


async def _run() -> None:
    """Wire up repositories and run parser service."""

    Session = get_async_sessionmaker()
    view_repo = AsyncViewMessageDocumentRepository(CompanyEnum.Ace, Session)
    exec_repo = AsyncMessageDocumentDecisionRepository(CompanyEnum.Ace, Session)
    extract_chain, classify_chain = get_azure_chains()

    file_processor = DecisionFileProcessor(
        extract_chain=extract_chain, classify_chain=classify_chain
    )

    service = ParserService(
        view_repo=view_repo, exec_repo=exec_repo, file_processor=file_processor
    )
    await service.run()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
