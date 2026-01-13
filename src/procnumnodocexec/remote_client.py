from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

import smbclient  # type: ignore[import]

from .config import get_smb_settings

logger = logging.getLogger(__name__)


class RemoteFileClient:
    """Асинхронний клієнт для роботи з віддаленими файлами через протокол SMB."""

    def __init__(self):
        self._config = get_smb_settings()
        self._session_registered = False
        # Лок для запобігання одночасній реєстрації сесії з кількох тасок
        self._session_lock = asyncio.Lock()

    async def _ensure_session(self):
        """Реєструє сесію, якщо вона ще не створена (Thread-safe)."""
        if self._session_registered:
            return

        async with self._session_lock:
            # Перевіряємо ще раз всередині лока (double-check locking pattern)
            if not self._session_registered:
                try:
                    username = self._config.username
                    if self._config.domain:
                        username = f"{self._config.domain}\\{username}"

                    # register_session — блокуюча операція, виносимо в потік
                    await asyncio.to_thread(
                        smbclient.register_session,  # type: ignore
                        self._config.server,
                        username=username,
                        password=self._config.password,
                    )
                    self._session_registered = True
                    logger.info(f"SMB session registered for {self._config.server}")

                except Exception as e:
                    logger.error(f"Failed to register SMB session: {e}")
                    raise

    def _sync_download_task(self, unc_path: str, local_dest: Path) -> None:
        """
        Синхронна функція, яка виконує блокуюче IO.
        Буде запущена в окремому потоці.
        """
        # smbclient.open_file та shutil.copyfileobj блокують виконання
        with smbclient.open_file(unc_path, mode="rb") as remote_f:  # type: ignore
            with open(local_dest, "wb") as local_f:
                shutil.copyfileobj(remote_f, local_f)

    async def download_file(
        self, remote_rel_path: Path | str, local_dest: Path
    ) -> Path:
        """
        Асинхронно завантажує файл у вказану папку.

        Args:
            remote_rel_path: Шлях на сервері (наприклад 'data/doc.pdf' or Path('data/doc.pdf'))
            local_dest: ПОВНИЙ локальний шлях до ПАПКИ, куди зберігати файл.

        Returns:
            Path до збереженого локального файлу (папка + ім'я файлу).
        """
        await self._ensure_session()

        # 1. Готуємо шлях для SMB (Windows-стандарт)
        clean_remote_path = str(remote_rel_path).replace("/", "\\").lstrip("\\")

        # 2. Формуємо повний локальний шлях до файлу
        # Витягуємо ім'я файлу (працює коректно, навіть якщо скрипт на Linux)
        file_name: str = clean_remote_path.split("\\")[-1]
        final_local_path = local_dest / file_name

        try:
            logger.info(f"Starting download: {clean_remote_path} -> {final_local_path}")

            # 3. Запускаємо скачування, передаючи повний шлях до файлу
            await asyncio.to_thread(
                self._sync_download_task, clean_remote_path, final_local_path
            )

            return final_local_path

        except Exception as e:
            logger.error(f"Error downloading file {clean_remote_path}: {e}")
            raise
