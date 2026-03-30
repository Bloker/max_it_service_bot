import logging
import platform
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

        args = [executable, "-n" if self.is_windows else "-c", "2", target]
        ok, output = await self.runner.run(args)
        return DiagnosticResult(ok=ok, title="Ping", details=output)

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
        return DiagnosticResult(
            ok=ping_result.ok,
            title="Host check",
            details=ping_result.details,
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
