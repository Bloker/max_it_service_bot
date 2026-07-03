# AGENTS.md

## Проект

Внутренний VK MAX IT Help Desk bot.

Основные блоки:

- `app/bot/handlers/*` — команды, callback, сообщения, group flow.
- `app/helpdesk/*` — заявки, lifecycle, тексты, клавиатуры, repositories.
- `app/network/*` — network tools, corporate policy, WiFi.link, Netarium.
- `app/admin/*` — роли, права доступа, registry пользователей.
- `config/*` — env parsing, runtime config, logging.
- `db/migrations/*` — SQL-миграции PostgreSQL.
- `scripts/*` — сервисные скрипты миграций.
- `docs/*` — runbook, roadmap, handoff-контекст.

## CODEX_PROJECT_CONTEXT_RU.md

- Перед началом каждой нетривиальной задачи Codex должен прочитать `docs/CODEX_PROJECT_CONTEXT_RU.md`, если файл есть.
- Этот файл является handoff-контекстом проекта: production, БД, миграции, известные риски, release policy, backlog.
- После существенных изменений Codex должен обновить `docs/CODEX_PROJECT_CONTEXT_RU.md`.

Обновлять файл обязательно, если изменились:

- архитектура проекта;
- env-переменные;
- схема БД или миграции;
- release policy;
- production/test deployment;
- systemd/service/runtime;
- MAX API integration;
- роли и права доступа;
- ticket lifecycle;
- network tools;
- WiFi.link / Netarium integrations;
- known issues;
- результаты тестов;
- рекомендуемый backlog.

Если файл не обновлялся, Codex должен явно написать в summary:

- почему обновление не требовалось;
- какие разделы контекста были проверены.

## Что важно не ломать

- Роли: `user`, `IT specialist`, `admin`.
- Централизованные проверки доступа в `app/admin/services/access_service.py`.
- Архитектурную границу `handler -> service -> repository`.
- HelpDesk lifecycle через `TicketLifecycleService`.
- Связь заявок с MAX-сообщениями через `TicketLinkService` / `PostgresTicketLinkService`.
- Network policy через `app/network/policy/target_validator.py` и `CorporateTargetPolicy`.
- PostgreSQL backend и fallback-режимы SQLite/memory.
- WiFi.link и Netarium integration flows.
- Production/test deployment порядок и release policy.

## Правила изменений

- Не хардкодить токены, chat_id, роли, policy и feature-флаги: только через `config/config.py` и env.
- Не вносить data-access логику в handlers.
- Новые сценарии по заявкам добавлять через `TicketLifecycleService` и repositories.
- Новые проверки прав сначала добавлять в `access_service`, потом подключать в handlers/services.
- Для network блока сначала policy/validation, потом выполнение команды.
- Секреты из `.env` не выводить в отчетах и не коммитить.

## Release policy

- Не выкатывать изменения на production без отдельной команды владельца.
- Не перезапускать production service без отдельного подтверждения.
- Не применять миграции к production-БД без отдельного подтверждения.
- Для проверки БД использовать `test_dev_max`, если задача не требует production.
- Секреты из `.env` не выводить в отчетах и не коммитить.

## MAX API

- Учитывать актуальные требования MAX API.
- Long Polling используется сейчас, но стратегическая рекомендация для production — Webhook.
- Учитывать ограничения polling: rate limit, timeout, batch size, TTL событий.
- При добавлении low-level HTTP adapter токен передавать через `Authorization`, не через query string.
- При работе с callback-кнопками предпочитать `POST /answers`.
- Для обновления сообщений бота использовать `PUT /messages`, если задача касается in-place update карточек заявок.
- На `maxapi>=1.2.1` для HTML использовать `format=ParseMode.HTML`; `parse_mode` не добавлять в новый код.
- Для callback update с заменой кнопок использовать `event.answer(new_text=..., attachments=..., format=...)` через `MaxMessageService`.

## Проверки перед итогом

- Синтаксис Python: `.venv/bin/python -m compileall app tests config main.py`.
- Тесты: `.venv/bin/python -m unittest discover -s tests -v`.
- Ручной smoke по HelpDesk + network при UX/runtime изменениях: `docs/MANUAL_CHECKLIST_RU.md`.

## Формат итогового отчета

В каждом нетривиальном изменении Codex должен указать:

- что изменено и зачем;
- какие файлы изменены;
- какие проверки запущены;
- результат проверок;
- обновлялся ли `docs/CODEX_PROJECT_CONTEXT_RU.md`;
- если не обновлялся — почему;
- что осталось проверить вручную;
- рекомендуемый backlog.
