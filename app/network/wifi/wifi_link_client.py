"""HTTP-клиент личного кабинета WiFi.link."""

import logging
from html.parser import HTMLParser

import aiohttp

from config.config import WifiLinkConfig

logger = logging.getLogger(__name__)


class _AuthenticityTokenParser(HTMLParser):
    """Достает CSRF-токен из формы авторизации WiFi.link."""

    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "input":
            return
        values = dict(attrs)
        if values.get("name") == "authenticity_token" and values.get("value"):
            self.token = values["value"]


def extract_authenticity_token(html: str) -> str | None:
    parser = _AuthenticityTokenParser()
    parser.feed(html)
    return parser.token


class WifiLinkClient:
    """HTTP-клиент личного кабинета WiFi.link."""

    def __init__(self, cfg: WifiLinkConfig) -> None:
        self.cfg = cfg

    async def fetch_voucher_pages(self) -> list[str]:
        if not self.cfg.is_configured:
            raise RuntimeError("WiFi Link credentials are not configured")

        timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
        async with aiohttp.ClientSession(
            base_url=self.cfg.base_url,
            timeout=timeout,
            raise_for_status=False,
        ) as session:
            await self._login(session)
            pages: list[str] = []
            for page in range(1, self.cfg.max_pages + 1):
                path = "/vouchers" if page == 1 else f"/vouchers?page={page}"
                async with session.get(path) as response:
                    html = await response.text()
                    if response.status != 200:
                        raise RuntimeError(
                            "WiFi Link vouchers request failed: "
                            f"HTTP {response.status}"
                        )
                    if "/users/sign_in" in str(response.url) or 'id="new_user"' in html:
                        raise RuntimeError("WiFi Link session is not authenticated")
                    pages.append(html)
            return pages

    async def fetch_voucher_pages_until(self, predicate) -> list[str]:
        if not self.cfg.is_configured:
            raise RuntimeError("WiFi Link credentials are not configured")

        timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
        async with aiohttp.ClientSession(
            base_url=self.cfg.base_url,
            timeout=timeout,
            raise_for_status=False,
        ) as session:
            await self._login(session)
            pages: list[str] = []
            for page in range(1, self.cfg.max_pages + 1):
                path = "/vouchers" if page == 1 else f"/vouchers?page={page}"
                async with session.get(path) as response:
                    html = await response.text()
                    if response.status != 200:
                        raise RuntimeError(
                            "WiFi Link vouchers request failed: "
                            f"HTTP {response.status}"
                        )
                    if "/users/sign_in" in str(response.url) or 'id="new_user"' in html:
                        raise RuntimeError("WiFi Link session is not authenticated")
                    pages.append(html)
                    if predicate(html):
                        break
            return pages

    async def _login(self, session: aiohttp.ClientSession) -> None:
        # В кабинете используется обычная Rails-форма с authenticity_token.
        async with session.get("/users/sign_in") as response:
            login_html = await response.text()
            if response.status != 200:
                raise RuntimeError(f"WiFi Link login page request failed: HTTP {response.status}")

        token = extract_authenticity_token(login_html)
        if not token:
            raise RuntimeError("WiFi Link login token was not found")

        data = {
            "authenticity_token": token,
            "user[email]": self.cfg.email,
            "user[password]": self.cfg.password,
            "user[remember_me]": "0",
        }
        async with session.post("/users/sign_in", data=data, allow_redirects=True) as response:
            await response.text()
            if response.status >= 500:
                raise RuntimeError(f"WiFi Link login failed: HTTP {response.status}")
