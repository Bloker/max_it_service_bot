import asyncio
import logging
import subprocess


logger = logging.getLogger(__name__)


class CommandRunner:
    def __init__(self, timeout_sec: int, max_output_chars: int) -> None:
        self.timeout_sec = timeout_sec
        self.max_output_chars = max_output_chars

    async def run(self, args: list[str]) -> tuple[bool, str]:
        if not args:
            return False, "Команда не задана."

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
                timeout=self.timeout_sec,
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            logger.warning("Command timeout (%ss): %s", self.timeout_sec, args)
            return False, f"Превышен timeout ({self.timeout_sec}с)."

        output = (stdout or b"").decode(errors="replace").strip()
        error_output = (stderr or b"").decode(errors="replace").strip()
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
