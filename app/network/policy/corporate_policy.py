"""Корпоративная policy сетевой диагностики."""

import ipaddress
from typing import Union

from config.config import NetworkPolicyConfig


class CorporateTargetPolicy:
    """Ограничивает сетевые проверки корпоративными адресами и доменами."""

    def __init__(self, cfg: NetworkPolicyConfig) -> None:
        self.allowed_domain_suffixes = cfg.allowed_domain_suffixes
        self.allowed_hosts = set(cfg.allowed_hosts)
        self.allowed_device_types = set(cfg.allowed_device_types)
        self.allowed_subnets = tuple(
            ipaddress.ip_network(subnet, strict=False)
            for subnet in cfg.allowed_subnets
        )

    def is_allowed_target(self, target: str) -> tuple[bool, str]:
        """Проверяет, разрешено ли диагностировать указанный target."""

        try:
            ip = ipaddress.ip_address(target)
            return self._is_allowed_ip(ip)
        except ValueError:
            return self._is_allowed_hostname(target)

    def _is_allowed_ip(
        self, ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
    ) -> tuple[bool, str]:
        for subnet in self.allowed_subnets:
            if ip in subnet:
                return True, ""
        return False, "Адрес не входит в корпоративные подсети."

    def _is_allowed_hostname(self, hostname: str) -> tuple[bool, str]:
        """Проверяет hostname по allow-list доменов и явных хостов."""

        if hostname in self.allowed_hosts:
            return True, ""

        for suffix in self.allowed_domain_suffixes:
            if hostname.endswith(suffix):
                return True, ""

        return False, "Хост не входит в корпоративный allowlist."

    def is_allowed_device_type(self, device_type: str) -> bool:
        """Проверяет, доступен ли шаблон диагностики для типа устройства."""

        return device_type.lower() in self.allowed_device_types
