"""Тесты конфигурации webhook-режима."""

import os
import unittest
from unittest.mock import patch

from config import config as config_module


BASE_ENV = {
    "MAX_BOT_TOKEN": "test-token",
    "MAX_GROUP_CHAT_ID": "123",
    "MAX_WIFI_LINK_EMAIL": "",
    "MAX_WIFI_LINK_PASSWORD": "",
    "MAX_NETARIUM_API_KEY": "",
}


class WebhookConfigTests(unittest.TestCase):
    def test_update_mode_defaults_to_longpoll(self) -> None:
        with patch.dict(os.environ, BASE_ENV, clear=True):
            with patch.object(config_module, "_load_environment", lambda: None):
                cfg = config_module.get_config()

        self.assertEqual(cfg.bot.update_mode, "longpoll")
        self.assertEqual(cfg.bot.webhook_host, "127.0.0.1")
        self.assertEqual(cfg.bot.webhook_port, 8080)
        self.assertEqual(cfg.bot.webhook_path, "/max-webhook")
        self.assertEqual(cfg.bot.webhook_health_path, "/health")
        self.assertEqual(cfg.bot.webhook_secret, "")

    def test_update_mode_accepts_longpoll_and_webhook(self) -> None:
        for mode in ("longpoll", "webhook"):
            with self.subTest(mode=mode):
                env = {**BASE_ENV, "MAX_UPDATE_MODE": mode}
                with patch.dict(os.environ, env, clear=True):
                    with patch.object(config_module, "_load_environment", lambda: None):
                        cfg = config_module.get_config()

                self.assertEqual(cfg.bot.update_mode, mode)

    def test_update_mode_rejects_unknown_value(self) -> None:
        env = {**BASE_ENV, "MAX_UPDATE_MODE": "bad"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                with patch.object(config_module, "_load_environment", lambda: None):
                    config_module.get_config()

    def test_webhook_settings_are_parsed(self) -> None:
        env = {
            **BASE_ENV,
            "MAX_UPDATE_MODE": "webhook",
            "MAX_WEBHOOK_HOST": "127.0.0.2",
            "MAX_WEBHOOK_PORT": "9090",
            "MAX_WEBHOOK_PATH": "/hook",
            "MAX_WEBHOOK_HEALTH_PATH": "/ready",
            "MAX_WEBHOOK_SECRET": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.object(config_module, "_load_environment", lambda: None):
                cfg = config_module.get_config()

        self.assertEqual(cfg.bot.webhook_host, "127.0.0.2")
        self.assertEqual(cfg.bot.webhook_port, 9090)
        self.assertEqual(cfg.bot.webhook_path, "/hook")
        self.assertEqual(cfg.bot.webhook_health_path, "/ready")
        self.assertEqual(cfg.bot.webhook_secret, "secret")

    def test_webhook_path_must_start_with_slash(self) -> None:
        env = {**BASE_ENV, "MAX_WEBHOOK_PATH": "hook"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                with patch.object(config_module, "_load_environment", lambda: None):
                    config_module.get_config()

    def test_webhook_paths_must_be_different(self) -> None:
        env = {
            **BASE_ENV,
            "MAX_WEBHOOK_PATH": "/same",
            "MAX_WEBHOOK_HEALTH_PATH": "/same",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                with patch.object(config_module, "_load_environment", lambda: None):
                    config_module.get_config()


if __name__ == "__main__":
    unittest.main()
