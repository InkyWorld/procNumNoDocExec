from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from aiofile import AIOFile
from .remote_client import RemoteFileClient

from .config import PROJECT_ROOT
from .decision_llm import detect_status_with_llm
from .schemas import DecisionEnum


class FileProcessor(ABC):
    """Interface for handling files referenced by ProcNumWithoutVP records."""

    @abstractmethod
    async def process(self, record: str) -> DecisionEnum | None:
        """Process the file at local folder"""


class DecisionFileProcessor(FileProcessor):
    """Placeholder implementation to be replaced with real processing logic."""

    def __init__(self, extract_chain=None, classify_chain=None) -> None:
        self._extract_chain = extract_chain
        self._classify_chain = classify_chain

    async def _parse_decision_in_file(self, local_file: Path) -> DecisionEnum:
        print(f"Парсинг файлу: {local_file}")
        async with AIOFile(local_file, "rb") as afd:
            raw_content: bytes | str = await afd.read()
            if isinstance(raw_content, bytes):
                content: str = raw_content.decode("Windows-1251")
            else:
                content = str(raw_content)
            return await detect_status_with_llm(
                content,
                self._extract_chain,
                self._classify_chain,
            )

    async def process(self, record: str) -> DecisionEnum | None:
        """
        Docstring for process

        :param self: Description
        :param records: Description
        :type records: list[str]
        :return: Description
        :rtype: Decision | None (None if process failed)
        """
        client = RemoteFileClient()

        # 2. Визначаємо, куди зберігати тимчасово
        temp_dir = PROJECT_ROOT / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        local_file = None
        try:
            # pass str(...) to satisfy type checkers that expect a string path
            local_file = await client.download_file(str(record), temp_dir)
            decision = await self._parse_decision_in_file(local_file)
            return decision

        except Exception as e:
            print(f"Не вдалося обробити файл: {e}")
        finally:
            if local_file and local_file.exists():
                local_file.unlink()
            pass

        return None


__all__ = ["FileProcessor", "DecisionFileProcessor"]
