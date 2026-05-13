"""Обертка над запуском системных команд."""

import asyncio
import locale
import logging
import platform
import subprocess


logger = logging.getLogger(__name__)


class CommandRunner:
    """Безопасно запускает системные сетевые утилиты с timeout и лимитом вывода."""

    def __init__(self, timeout_sec: int, max_output_chars: int) -> None:
        self.timeout_sec = timeout_sec
        self.max_output_chars = max_output_chars

    async def run(self, args: list[str], timeout_sec: int | None = None) -> tuple[bool, str]:
        """Выполняет команду и возвращает статус успеха с нормализованным выводом."""

        if not args:
            return False, "Команда не задана."
        effective_timeout = timeout_sec if timeout_sec and timeout_sec > 0 else self.timeout_sec

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.warning("Utility not found: %s", args[0])
            return False, f"Утилита не найдена: {args[0]}"
        except Exception as exc:
            logger.exception("Command start failed: %s", args)
            return False, f"Ошибка запуска: {exc}"

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=effective_timeout,
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            logger.warning("Command timeout (%ss): %s", effective_timeout, args)
            return False, f"Превышен timeout ({effective_timeout}с)."

        output = self._decode_output(stdout or b"").strip()
        error_output = self._decode_output(stderr or b"").strip()
        combined = output
        if error_output:
            combined = f"{combined}\n{error_output}".strip()
        if not combined:
            combined = "(пустой вывод)"
        if len(combined) > self.max_output_chars:
            combined = combined[: self.max_output_chars] + "\n...[обрезано]"

        ok = process.returncode == 0
        if not ok:
            logger.warning("Command failed (code=%s): %s", process.returncode, args)
        return ok, combined

    @staticmethod
    def _decode_output(raw: bytes) -> str:
        """Декодирует вывод системной утилиты с учетом ОС и локали."""

        if not raw:
            return ""

        preferred = locale.getpreferredencoding(False) or ""
        if platform.system().lower().startswith("win"):
            # Консольные утилиты Windows обычно возвращают OEM-кодировку.
            encodings: list[str] = ["cp866", preferred, "cp1251", "utf-8"]
        else:
            encodings = [preferred, "utf-8", "cp1251", "cp866"]

        ranked: list[tuple[int, int, str]] = []
        seen: set[str] = set()
        for idx, encoding in enumerate(encodings):
            normalized = encoding.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            try:
                decoded = raw.decode(encoding, errors="replace")
            except LookupError:
                continue
            ranked.append((decoded.count("\ufffd"), idx, decoded))

        if not ranked:
            return raw.decode(errors="replace")
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked[0][2]
