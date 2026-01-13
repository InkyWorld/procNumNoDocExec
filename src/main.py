from __future__ import annotations

import asyncio

from procnumnodocexec import (
    AsyncProcNumNoDocExecRepository,
    AsyncViewProcNumWithoutVPRepository,
    DecisionFileProcessor,
    get_async_sessionmaker,
    ParserService,
    CompanyEnum,
)




async def _run() -> None:
    """Wire up repositories and run parser service."""

    Session = get_async_sessionmaker()
    view_repo = AsyncViewProcNumWithoutVPRepository(CompanyEnum.Ace, Session)
    exec_repo = AsyncProcNumNoDocExecRepository(Session)
    file_processor = DecisionFileProcessor()

    service = ParserService(
        view_repo=view_repo, exec_repo=exec_repo, file_processor=file_processor
    )
    await service.run()


def main() -> None:
    asyncio.run(_run())

if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
