"""HTTP-клиент Netarium API."""

import aiohttp

from config.config import NetariumConfig


class NetariumClient:
    """HTTP-клиент Netarium API с авторизацией через X-API-Key."""

    def __init__(self, cfg: NetariumConfig) -> None:
        self.cfg = cfg

    async def fetch_objects(self) -> list[dict]:
        if not self.cfg.is_configured:
            raise RuntimeError("Netarium API is not configured")

        timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
        async with aiohttp.ClientSession(
            base_url=self.cfg.base_url,
            timeout=timeout,
            raise_for_status=False,
        ) as session:
            async with session.get(
                "/api/object",
                params={"class": self.cfg.object_class},
                headers={"X-API-Key": self.cfg.api_key},
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Netarium API request failed: HTTP {response.status}"
                    )
                payload = await response.json()

        if not isinstance(payload, list):
            raise RuntimeError("Netarium API returned unexpected payload")
        return payload
