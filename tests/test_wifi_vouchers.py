import unittest
import json
from datetime import date

from app.network.wifi.models import WifiVoucherSearchResult
from app.network.wifi.voucher_parser import parse_wifi_vouchers
from app.network.wifi.voucher_service import WifiVoucherService
from app.network.wifi.voucher_texts import render_voucher_search_result
from app.observability.services import ObservabilityService
from config.config import WifiLinkConfig
from tests.test_observability_service import FakeObservabilityRepository


_HTML = """
<table>
  <tbody>
    <tr>
      <td>1</td>
      <td>dmitrych80gmailcom_3:2116:sukhin</td>
      <td>secret-password</td>
      <td>15</td>
      <td>0.83</td>
      <td>1180.17</td>
      <td>68.64</td>
      <td>0</td>
      <td>Годен</td>
      <td>12.05.26</td>
      <td>actions</td>
    </tr>
    <tr>
      <td>2</td>
      <td>dmitrych80gmailcom_3:325:ichalov</td>
      <td>1</td>
      <td>15</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>Годен</td>
      <td>12.05.26</td>
      <td>actions</td>
    </tr>
  </tbody>
</table>
"""


class _FakeWifiLinkClient:
    def __init__(self, pages: list[str]) -> None:
        self.pages = pages
        self.calls = 0
        self.until_calls = 0

    async def fetch_voucher_pages(self) -> list[str]:
        self.calls += 1
        return self.pages

    async def fetch_voucher_pages_until(self, predicate) -> list[str]:
        self.until_calls += 1
        collected: list[str] = []
        for page in self.pages:
            collected.append(page)
            if predicate(page):
                break
        return collected


class _FailingWifiLinkClient:
    async def fetch_voucher_pages_until(self, predicate):
        raise TimeoutError("request timeout")


def _wifi_config() -> WifiLinkConfig:
    return WifiLinkConfig(
        base_url="https://lk.wi-fi.link",
        email="admin@example.test",
        password="secret",
        timeout_sec=10,
        max_pages=20,
        cache_ttl_sec=120,
    )


class WifiVoucherTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_wifi_vouchers_excludes_sensitive_remaining_fields(self) -> None:
        vouchers = parse_wifi_vouchers(_HTML)

        self.assertEqual(len(vouchers), 2)
        self.assertEqual(vouchers[0].login, "dmitrych80gmailcom_3:2116:sukhin")
        self.assertEqual(vouchers[0].room, "2116")
        self.assertEqual(vouchers[0].guest, "sukhin")
        self.assertEqual(vouchers[0].speed_mbps, "15")
        self.assertEqual(vouchers[0].elapsed_hours, "0.83")
        self.assertEqual(vouchers[0].remaining_hours, "1180.17")
        self.assertEqual(vouchers[0].downloaded_mb, "68.64")
        self.assertEqual(vouchers[0].validity, "Годен")
        self.assertEqual(vouchers[0].created_date, date(2026, 5, 12))
        self.assertFalse(hasattr(vouchers[0], "password"))
        self.assertFalse(hasattr(vouchers[0], "remaining_mb"))

    def test_parse_wifi_vouchers_extracts_room_and_guest_from_login(self) -> None:
        html = _HTML.replace("dmitrych80gmailcom_3:2116:sukhin", "dmitrych80gmailcom_3:3219:moiseenko")

        vouchers = parse_wifi_vouchers(html)

        self.assertEqual(vouchers[0].login, "dmitrych80gmailcom_3:3219:moiseenko")
        self.assertEqual(vouchers[0].room, "3219")
        self.assertEqual(vouchers[0].guest, "moiseenko")

    async def test_find_first_by_room_returns_first_matching_room_ignoring_date(self) -> None:
        client = _FakeWifiLinkClient([_HTML])
        repository = FakeObservabilityRepository()
        service = WifiVoucherService(
            _wifi_config(),
            client=client,
            observability=ObservabilityService(repository=repository),
        )

        result = await service.find_first_by_room(
            "2116",
            actor_user_id=1001,
            actor_name="Admin",
            chat_type="dialog",
            room_exists_in_netarium=True,
            guest_found_in_netarium=True,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.room, "2116")
        self.assertEqual(len(result.vouchers), 1)
        self.assertEqual(result.vouchers[0].guest, "sukhin")
        self.assertEqual(client.until_calls, 1)
        run = repository.network_runs[0]
        self.assertEqual(run.tool, "wifi_voucher_lookup")
        self.assertEqual(run.status, "success")
        self.assertEqual(run.actor_user_id, 1001)
        self.assertTrue(run.metadata["voucher_found"])
        self.assertEqual(run.metadata["pages_scanned"], 1)
        self.assertEqual(run.metadata["login_masked"], "***:2116:***")
        serialized = json.dumps(run.metadata, ensure_ascii=False)
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn(_HTML, serialized)

    async def test_find_first_by_room_returns_first_match_from_newest_order(self) -> None:
        html = _HTML.replace("12.05.26", "10.05.26", 1)
        html = html.replace(
            "</tbody>",
            """
    <tr>
      <td>3</td>
      <td>dmitrych80gmailcom_3:2116:older</td>
      <td>1</td>
      <td>15</td>
      <td>7</td>
      <td>1173</td>
      <td>10</td>
      <td>0</td>
      <td>Годен</td>
      <td>09.05.26</td>
      <td>actions</td>
    </tr>
  </tbody>
""",
        )
        client = _FakeWifiLinkClient([html])
        service = WifiVoucherService(_wifi_config(), client=client)

        result = await service.find_first_by_room("2116")

        self.assertTrue(result.ok)
        self.assertEqual(len(result.vouchers), 1)
        self.assertEqual(result.vouchers[0].guest, "sukhin")
        self.assertEqual(result.vouchers[0].created_date, date(2026, 5, 10))

    async def test_find_first_by_room_fetches_pages_until_first_match(self) -> None:
        page_without_room = _HTML.replace("2116", "9999").replace("325", "9998")
        page_with_room = _HTML.replace("2116", "3109").replace("sukhin", "eroshova")
        page_after_match = _HTML.replace("2116", "3109").replace("sukhin", "older")
        client = _FakeWifiLinkClient([page_without_room, page_with_room, page_after_match])
        service = WifiVoucherService(_wifi_config(), client=client)

        result = await service.find_first_by_room("3109")

        self.assertTrue(result.ok)
        self.assertEqual(len(result.vouchers), 1)
        self.assertEqual(result.vouchers[0].guest, "eroshova")
        self.assertEqual(client.until_calls, 1)
        self.assertEqual(client.calls, 0)
        self.assertEqual(len(service._cached_vouchers), 4)

    async def test_find_first_by_room_uses_cache(self) -> None:
        client = _FakeWifiLinkClient([_HTML])
        repository = FakeObservabilityRepository()
        service = WifiVoucherService(
            _wifi_config(),
            client=client,
            observability=ObservabilityService(repository=repository),
        )

        await service.find_first_by_room("2116")
        await service.find_first_by_room("325")

        self.assertEqual(client.until_calls, 1)
        self.assertTrue(repository.network_runs[-1].metadata["cache_hit"])
        self.assertTrue(repository.network_runs[-1].metadata["cache_partial"])

    async def test_find_first_by_room_refetches_when_partial_cache_misses_room(self) -> None:
        page_with_first_room = _HTML.replace("2116", "101").replace("sukhin", "koltsova")
        page_with_second_room = _HTML.replace("2116", "3111").replace("sukhin", "matyushkina")
        client = _FakeWifiLinkClient([page_with_first_room, page_with_second_room])
        service = WifiVoucherService(_wifi_config(), client=client)

        first_result = await service.find_first_by_room("101")
        second_result = await service.find_first_by_room("3111")

        self.assertTrue(first_result.ok)
        self.assertEqual(first_result.vouchers[0].guest, "koltsova")
        self.assertTrue(second_result.ok)
        self.assertEqual(second_result.vouchers[0].guest, "matyushkina")
        self.assertEqual(client.until_calls, 2)
        self.assertTrue(service._cached_vouchers)

    async def test_observability_records_not_found(self) -> None:
        client = _FakeWifiLinkClient([_HTML])
        repository = FakeObservabilityRepository()
        service = WifiVoucherService(
            _wifi_config(),
            client=client,
            observability=ObservabilityService(repository=repository),
        )

        result = await service.find_first_by_room("9999")

        self.assertTrue(result.ok)
        self.assertEqual(result.vouchers, ())
        run = repository.network_runs[0]
        self.assertEqual(run.status, "not_found")
        self.assertFalse(run.metadata["voucher_found"])

    async def test_observability_records_external_timeout(self) -> None:
        repository = FakeObservabilityRepository()
        service = WifiVoucherService(
            _wifi_config(),
            client=_FailingWifiLinkClient(),
            observability=ObservabilityService(repository=repository),
        )

        result = await service.find_first_by_room("2116")

        self.assertFalse(result.ok)
        run = repository.network_runs[0]
        self.assertEqual(run.status, "timeout")
        self.assertEqual(run.metadata["external_status"], "timeout")

    def test_render_voucher_search_result_hides_password_and_remaining_values(self) -> None:
        voucher = parse_wifi_vouchers(_HTML)[0]
        text = render_voucher_search_result(
            WifiVoucherSearchResult(ok=True, room="2116", vouchers=(voucher,))
        )

        self.assertIn("<b>WiFi ваучер: комната 2116</b>", text)
        self.assertIn("Логин: <code>dmitrych80gmailcom_3:2116:sukhin</code>", text)
        self.assertIn("Гость: sukhin", text)
        self.assertIn("Скорость: 15 Мбит/сек", text)
        self.assertIn("Времени прошло: 0.83 ч", text)
        self.assertIn("Времени осталось: 1180.17 ч", text)
        self.assertIn("Скачано: 68.64 МБ", text)
        self.assertNotIn("Пароль", text)
        self.assertNotIn("secret-password", text)
        self.assertNotIn("Трафика осталось", text)


if __name__ == "__main__":
    unittest.main()
