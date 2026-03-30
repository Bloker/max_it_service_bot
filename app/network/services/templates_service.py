class NetworkTemplatesService:
    def wifi_troubleshooting(self) -> str:
        return (
            "Wi-Fi troubleshooting:\n"
            "1) Проверить SSID и уровень сигнала.\n"
            "2) Переподключить устройство к корпоративной сети.\n"
            "3) Проверить IP/Gateway/DNS на устройстве.\n"
            "4) Проверить доступ до внутреннего DNS.\n"
            "5) При необходимости открыть заявку в Help Desk."
        )

    def device_template(self, device_type: str) -> str:
        normalized = device_type.lower()
        if normalized in {"android_tv", "tv_box"}:
            return (
                f"Шаблон диагностики для {normalized}:\n"
                "• Проверить LAN/Wi-Fi и IP устройства.\n"
                "• Проверить доступ к внутреннему endpoint контента.\n"
                "• Проверить DNS-резолв внутренних доменов.\n"
                "• TODO: добавить vendor-specific health checks."
            )

        return (
            f"Шаблон диагностики для {normalized}:\n"
            "• Проверить сетевое подключение и адресацию.\n"
            "• Проверить доступ к целевому внутреннему сервису.\n"
            "• TODO: добавить специализированные проверки типа устройства."
        )
