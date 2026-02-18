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
from procnumnodocexec.llm_provider import (
    get_azure_chains,
    get_azure_execution_doc_chains,
)


async def _run() -> None:
    """Wire up repositories and run parser service."""

    Session = get_async_sessionmaker()
    company = CompanyEnum.Unit
    view_repo = AsyncViewMessageDocumentRepository(company, Session)
    exec_repo = AsyncMessageDocumentDecisionRepository(company, Session)
    extract_chain, classify_chain = get_azure_chains()
    exec_extract_chain, exec_classify_chain = get_azure_execution_doc_chains()

    file_processor = DecisionFileProcessor(
        extract_chain=extract_chain,
        classify_chain=classify_chain,
        execution_extract_chain=exec_extract_chain,
        execution_classify_chain=exec_classify_chain,
    )

    service = ParserService(
        view_repo=view_repo,
        exec_repo=exec_repo,
        file_processor=file_processor,
        company=company,
    )
    # await service.run()
    await service.run_exec()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
