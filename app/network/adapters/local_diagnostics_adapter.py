import logging
import platform
import re
import socket
from shutil import which

from app.network.adapters.command_runner import CommandRunner
from app.network.models.diagnostic import DiagnosticResult


logger = logging.getLogger(__name__)


class LocalDiagnosticsAdapter:
    """Local OS adapter. Designed for future swap to external diagnostic service."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner
        self.is_windows = platform.system().lower().startswith("win")

    async def ping(self, target: str) -> DiagnosticResult:
        executable = "ping"
        if which(executable) is None:
            return DiagnosticResult(ok=False, title="Ping", details="Утилита ping недоступна.")

        sent_count = 5
        if self.is_windows:
            args = [executable, "-n", str(sent_count), "-w", "1000", target]
        else:
            # Ubuntu-friendly profile: 5 packets, 1s reply timeout, hard deadline.
            args = [executable, "-c", str(sent_count), "-W", "1", "-w", "8", target]

        ok, output = await self.runner.run(args, timeout_sec=max(self.runner.timeout_sec, 12))
        details = self._build_ping_summary(
            target=target,
            ok=ok,
            output=output,
            sent_count=sent_count,
        )
        return DiagnosticResult(ok=ok, title="Ping", details=details)

    async def dns_lookup(self, target: str) -> DiagnosticResult:
        try:
            addresses = socket.gethostbyname_ex(target)[2]
        except Exception as exc:
            logger.warning("DNS lookup failed for %s: %s", target, exc)
            return DiagnosticResult(ok=False, title="DNS lookup", details=f"Ошибка: {exc}")

        if not addresses:
            return DiagnosticResult(ok=False, title="DNS lookup", details="Адреса не найдены.")

        details = "\n".join(addresses)
        return DiagnosticResult(ok=True, title="DNS lookup", details=details)

    async def host_check(self, target: str) -> DiagnosticResult:
        try:
            socket.getaddrinfo(target, None)
        except Exception as exc:
            logger.warning("Host resolve failed for %s: %s", target, exc)
            return DiagnosticResult(ok=False, title="Host check", details=f"Resolve error: {exc}")

        ping_result = await self.ping(target)
        dns_state = "OK"
        return DiagnosticResult(
            ok=ping_result.ok,
            title="Host check",
            details=f"DNS resolve: {dns_state}\n{ping_result.details}",
        )

    async def traceroute(self, target: str) -> DiagnosticResult:
        executable = "tracert" if self.is_windows else "traceroute"
        if which(executable) is None:
            return DiagnosticResult(
                ok=False,
                title="Traceroute",
                details="Traceroute утилита недоступна в этой среде.",
            )

        args = [executable]
        if self.is_windows:
            args.extend(["-d", target])
        else:
            args.extend(["-n", target])

        ok, output = await self.runner.run(args)
        return DiagnosticResult(ok=ok, title="Traceroute", details=output)

    async def nslookup(self, target: str) -> DiagnosticResult:
        executable = "nslookup"
        if which(executable) is None:
            return DiagnosticResult(
                ok=False,
                title="NSLookup",
                details="Утилита nslookup недоступна в этой среде.",
            )

        ok, output = await self.runner.run([executable, target])
        return DiagnosticResult(ok=ok, title="NSLookup", details=output)

    async def whois(self, target: str) -> DiagnosticResult:
        executable = "whois"
        if which(executable) is None:
            return DiagnosticResult(
                ok=False,
                title="Whois",
                details=(
                    "Whois пока недоступен. "
                    "TODO: подключить безопасный internal whois adapter."
                ),
            )

        ok, output = await self.runner.run([executable, target])
        return DiagnosticResult(ok=ok, title="Whois", details=output)

    def _build_ping_summary(self, target: str, ok: bool, output: str, sent_count: int) -> str:
        sent, received, loss_pct = self._extract_ping_packets(output, sent_count=sent_count)
        avg_ms = self._extract_ping_avg_ms(output)

        lines = [f"Хост: {target}"]
        if sent is not None and received is not None:
            lines.append(f"Ответы: {received}/{sent}")
        if loss_pct is not None:
            lines.append(f"Потери: {loss_pct}%")
        if avg_ms is not None:
            lines.append(f"Средняя задержка: {avg_ms} мс")

        if len(lines) == 1:
            lines.append("Результат: доступен" if ok else "Результат: недоступен")

        if not ok and sent is None and received is None and loss_pct is None:
            first_line = (output or "").splitlines()
            if first_line:
                lines.append(first_line[0].strip())

        return "\n".join(lines)

    @staticmethod
    def _extract_ping_packets(
        output: str,
        *,
        sent_count: int,
    ) -> tuple[int | None, int | None, int | None]:
        windows = re.search(
            r"(?is)(?:sent|отправлено)\s*=\s*(\d+).*?"
            r"(?:received|получено)\s*=\s*(\d+).*?"
            r"(?:lost|потеряно)\s*=\s*(\d+).*?\((\d+)\s*%",
            output,
        )
        if windows:
            sent = int(windows.group(1))
            received = int(windows.group(2))
            loss_pct = int(windows.group(4))
            return sent, received, loss_pct

        unix = re.search(
            r"(?i)(\d+)\s+packets transmitted,\s+(\d+)\s+"
            r"(?:packets\s+)?received.*?(\d+)\s*%\s*packet loss",
            output,
        )
        if unix:
            return int(unix.group(1)), int(unix.group(2)), int(unix.group(3))

        reply_count = len(re.findall(r"(?im)\bttl\s*=", output))
        if reply_count > 0:
            sent = sent_count
            received = min(reply_count, sent_count)
            loss_pct = int(round(((sent - received) / sent) * 100))
            return sent, received, loss_pct

        return None, None, None

    @staticmethod
    def _extract_ping_avg_ms(output: str) -> int | None:
        windows = re.search(
            r"(?i)(?:average|среднее)\s*=\s*<?\s*(\d+)\s*(?:ms|мс)",
            output,
        )
        if windows:
            return int(windows.group(1))

        unix = re.search(r"(?i)=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms", output)
        if unix:
            return int(float(unix.group(1)))

        sample_times = [
            int(value)
            for value in re.findall(r"(?i)(?:time|время)\s*[=<]\s*(\d+)\s*(?:ms|мс)?", output)
        ]
        if sample_times:
            return int(round(sum(sample_times) / len(sample_times)))

        return None

