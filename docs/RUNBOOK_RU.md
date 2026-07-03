# Инструкция по запуску и проверке (RU)

## 1) Локальный запуск
1. Установите Python 3.12+.
2. Создайте виртуальное окружение и активируйте его.
3. Установите зависимости:
   - `pip install -r requirements.txt`
4. Создайте `.env` на основе `.env.example` (или `config/.env.example`).
5. Запустите бота:
   - `python main.py`

## 2) Обязательные env-переменные
- `MAX_BOT_TOKEN` — токен бота VK MAX.
- `MAX_GROUP_CHAT_ID` — chat_id группового чата специалистов.

## 3) Важные env-переменные
- Роли:
  - `MAX_ADMIN_IDS`
  - `MAX_IT_SPECIALIST_IDS`
- Хранилище заявок:
  - `MAX_TICKET_BACKEND` (`sqlite`/`memory`/`postgres`)
  - `MAX_TICKET_SCHEMA_MODE` (`legacy`/`shadow_read`/`normalized`, default `legacy`)
  - `MAX_TICKET_DB_PATH`
  - `MAX_TICKET_PG_HOST`
  - `MAX_TICKET_PG_PORT`
  - `MAX_TICKET_PG_DB`
  - `MAX_TICKET_PG_USER`
  - `MAX_TICKET_PG_PASSWORD`
  - `MAX_TICKET_PG_SSLMODE`
  - `MAX_TICKET_PG_CONNECT_TIMEOUT_SEC`
- Network policy/feature flags:
  - `MAX_NET_ALLOWED_SUBNETS`
  - `MAX_NET_ALLOWED_DOMAIN_SUFFIXES`
  - `MAX_NET_ALLOWED_HOSTS`
  - `MAX_NET_ALLOWED_DEVICE_TYPES`
  - `MAX_NET_FEATURE_PING`, `MAX_NET_FEATURE_DNS_LOOKUP`, `MAX_NET_FEATURE_HOST_CHECK`, `MAX_NET_FEATURE_TRACEROUTE`, `MAX_NET_FEATURE_NSLOOKUP`, `MAX_NET_FEATURE_WHOIS`
  - `MAX_NET_COMMAND_TIMEOUT_SEC`, `MAX_NET_MAX_OUTPUT_CHARS`
- Логи:
  - `LOG_LEVEL`
  - `LOG_FORMAT`

## 4) Роли в системе
- `user`: пользовательские сценарии helpdesk.
- `IT specialist`: обработка заявок + сетевые инструменты.
- `admin`: расширенные права, включая административные действия.

## 5) Поддерживаемые пользовательские сценарии
- `/start`, `/menu` — вход в меню.
- Создание заявки: категория -> описание -> подтверждение.
- Просмотр своих заявок: `/my` и кнопка «Мои заявки».
- В группе специалистов:
  - взятие/снятие/закрытие/уточнение через кнопки и команды;
  - просмотр открытых заявок: `/open [limit]`.

## 6) Как работает групповой чат специалистов
- Новая заявка отправляется в `MAX_GROUP_CHAT_ID`.
- К заявке прикрепляются action-кнопки для специалиста.
- Для reply-команд используется runtime-связка `ticket_id <-> message_id` (в памяти процесса).

## 7) Как работают сетевые инструменты
- Доступ только для `admin` и `IT specialist`.
- Перед запуском инструмента target проходит:
  1. нормализацию и форматную валидацию;
  2. проверку corporate policy (подсети/домены/allowlist).
- Фактическое выполнение делается локальными системными утилитами (`ping`, `traceroute`, `nslookup` и т.д.) с таймаутом и ограничением вывода.

## 8) Ограничения безопасности
- Запрещены внешние адреса вне корпоративной policy.
- Нельзя включать network tools для обычных пользователей.
- Нельзя хранить секреты в коде — только env.

## 9) Что проверить после запуска
1. Бот стартует без исключений и пишет стартовые логи.
2. Пользователь создаёт заявку и видит её в списке `/my`.
3. В группе специалистов появляется карточка заявки.
4. Специалист меняет статус, карточка обновляется.
5. Пользователь без роли IT/Admin не получает доступ к network tools.
6. Запрещённые внешние target отклоняются policy.
7. Разрешённые корпоративные target проходят проверку.

См. детальный ручной список в docs/MANUAL_CHECKLIST_RU.md.

Команда автопроверки: `python -m unittest discover -s tests -v`.

## 10) Миграция в нормализованную PostgreSQL-схему
1. Убедитесь, что выставлен backend:
   - `MAX_TICKET_BACKEND=postgres`
2. Примените SQL-миграцию:
   - `python scripts/apply_postgres_migration.py`
3. Перенесите реестр пользователей из JSON в `auth.*`:
   - `python scripts/migrate_user_registry_to_auth.py`

## 11) Source of truth заявок
Для PostgreSQL backend доступен управляемый режим схемы:

- `MAX_TICKET_SCHEMA_MODE=legacy` — default и rollback-режим; заявки пишутся в `public.helpdesk_tickets`, `helpdesk.tickets` обновляется trigger sync.
- `MAX_TICKET_SCHEMA_MODE=shadow_read` — запись остаётся legacy, чтение legacy используется как основной результат, normalized чтение сверяется в warning-логах.
- `MAX_TICKET_SCHEMA_MODE=normalized` — заявки читаются и пишутся через `helpdesk.tickets`.

Production не переключать на `shadow_read` или `normalized` без отдельной команды владельца.

Read-only сверка legacy и normalized:

```bash
MAX_TICKET_BACKEND=postgres python scripts/reconcile_ticket_schemas.py --db test_dev_max
```

Rollback для dev/test:

```text
MAX_TICKET_SCHEMA_MODE=legacy
restart dev/test bot
```

Важно: в `normalized` режиме новые заявки пишутся только в `helpdesk.tickets`.
До production switch нужен отдельный этап reverse sync или dual-write, иначе legacy
таблица будет отставать и rollback с данными потребует backfill.

## 12) Production rollout 2026-07-03

Production обновлен до:

```text
commit: e437e04 prepare helpdesk rollout features
service: max-it-bot.service active/running
MAX_TICKET_SCHEMA_MODE=legacy
```

Перед миграциями создан backup:

```text
host: 192.168.1.221
path: /root/db_backups/max_it_helpdesk_bot_20260703_112816_before_rollout.dump
size: 92K
```

Применены production migrations:

```text
db/migrations/20260702_persist_ticket_comments_attachments.sql
db/migrations/20260702_audit_events_observability.sql
```

Проверки после rollout:

```text
compileall: OK
unittest: Ran 134 tests in 0.238s, OK
reconcile max_it_helpdesk_bot: pending=0, only_public=0, only_helpdesk=0, duplicates=0, orphan=0
fresh journal after restart: no traceback/error/db error/pydantic crash loop by grep
```

Важно: production не переключался на `shadow_read` или `normalized`.
Оставшийся ручной шаг: выполнить smoke в MAX по `docs/MANUAL_CHECKLIST_RU.md`
для создания заявки, уточнения, прикрепления ответа, закрытия с ответом и
проверки HTML `tel:` телефона в web-клиенте.
