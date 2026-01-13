from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from aiofile import AIOFile

from procnumnodocexec.remote_client import RemoteFileClient

from .config import PROJECT_ROOT
from .schemas import DecisionEnum


class FileProcessor(ABC):
    """Interface for handling files referenced by ProcNumWithoutVP records."""

    @abstractmethod
    async def process(self, record: str) -> DecisionEnum | None:
        """Process the file at local folder"""


class DecisionFileProcessor(FileProcessor):
    """Placeholder implementation to be replaced with real processing logic."""

    @staticmethod
    async def _parse_decision_in_file(local_file: Path) -> DecisionEnum:
        print(f"Парсинг файлу: {local_file}")
        async with AIOFile(local_file, "rb") as afd:
            raw_content = await afd.read()
            content = raw_content.decode("Windows-1251")  # type: ignore
            print(f"Вміст файлу: {content[:1000]}...")
            content_lower = content.lower()  # type: ignore
            if "позитивне" in content_lower:
                return DecisionEnum.POSITIVE  # type: ignore
            elif "негативне" in content_lower:
                return DecisionEnum.NEGATIVE  # type: ignore
            elif "часткове" in content_lower:
                return DecisionEnum.PARTIAL  # type: ignore
            else:
                return DecisionEnum.UNKNOWN  # type: ignore

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
            local_file = await client.download_file(
                str(record), temp_dir
            )
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
