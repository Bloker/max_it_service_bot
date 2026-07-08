# Jamaica Room Ticket Flow

Документ фиксирует подготовку Stage 1 для будущего hotel-specific HelpDesk-flow
отеля `Джамайка`.

## Stage 1: Test-Only Schema And Seed

Статус: подготовлено локально и применено только к `test_dev_max`.

Production freeze:

```text
production changed: no
production service restarted: no
production DB migrated: no
production commit: fadf6d3 add integration observability events
production health: OK, mode=webhook
production reconciliation: clean, 130 legacy / 130 normalized / PENDING=0
production dump: /root/db_backups/max_it_helpdesk_bot_20260707_135742_prod_freeze_before_jamaica_flow.dump
production dump sha256: 4098fa3c56fd7279462a432598dd7bd907b5b6ed12163a7c622732c6254ed4f3
production env backup: /root/maxbot_env_backups/.env.before_jamaica_flow_20260707_135743
local stable tag: prod-stable-before-jamaica-flow-20260707
old rollback bot 192.168.1.222: not changed; SSH check returned No route to host
```

Test DB:

```text
database: test_dev_max
migration: db/migrations/20260707_jamaica_room_ticket_context.sql
seed: scripts/seed_jamaica_test_data.py
schema mode: legacy
reconciliation: clean, 85 legacy / 85 normalized / PENDING=0
```

Created/used tables:

```text
auth.user_hotel_memberships: existing table reused, no duplicate auth.user_hotels
helpdesk.locations: created for hotel locations
helpdesk.issue_categories: created for room-ticket categories
helpdesk.hotel_issue_categories: created for hotel-category mapping
helpdesk.ticket_context: created for future ticket location/category snapshots
```

Jamaica catalog:

```text
total locations: 253
1 корпус / room: 100
2 корпус / room: 61
3 корпус / room: 62
Домики / cottage: 30
unique key: (hotel_id, room_number)
```

Sample locations:

```text
101  -> Джамайка · 1 корпус · номер 101
2105 -> Джамайка · 2 корпус · номер 2105
3120 -> Джамайка · 3 корпус · номер 3120
15   -> Джамайка · Домик 15
```

Categories:

```text
tv        -> ТВ
telephony -> Телефония
internet  -> Интернет
lock      -> Замок
other     -> Прочее
```

Test user membership seed:

```text
active Jamaica memberships after seed: 5
seed policy: active auth.users without active hotel membership are assigned to jamaica
idempotency: second seed run added 0 memberships and did not duplicate locations/categories
```

Prepared read-only code:

```text
app/helpdesk/repositories/location_repository.py
app/helpdesk/repositories/postgres_location_repository.py
app/helpdesk/services/location_service.py
app/helpdesk/services/jamaica_seed_data.py
```

Future UX target:

```text
Главное меню — Джамайка
[Заявка по номеру]
[Прочее]
[Мои заявки]
[Помощь]
```

Building buttons are intentionally not needed. User enters only room/cottage number,
then the bot resolves hotel/building/location by `(hotel_id, room_number)`.

## Stage 2.1 Status

Статус: локально стабилизировано, test-only, production unchanged.

Git / rollout status:

```text
base local commit: 5c65675 add jamaica test room ticket flow
production changed: no
production commit: fadf6d3 add integration observability events
test DB: test_dev_max
```

Текущее UX-поведение Jamaica flow:

```text
Главное меню:
  [Заявка по номеру]
  [Прочее]
  [Мои заявки]
  [Помощь]

После "Заявка по номеру":
  текстовый ввод номера
  только кнопка [Отмена]

После найденного номера:
  кнопки категорий из БД:
    ТВ
    Телефония
    Интернет
    Замок
    Прочее
  без кнопки "Главное меню"

После выбора категории:
  запрос описания
  только кнопка [Отмена]

Неизвестный номер:
  "Такого номера не существует"
  [Ввести заново]
  [Создать как Прочее]
  [Главное меню]
```

Формат Jamaica room-ticket карточки в группе:

```text
Статус: ...
Исполнитель: ...
Объект: Номер 112 (ТВ)
Пользователь: ...
Тел: +7...
Описание:
...
```

Правила карточки:

```text
отдельная строка "Категория" не выводится, если есть ticket_context;
нижний блок "Объект / Категория объекта" убран;
для домиков формат:
  Объект: Домик 15 (Интернет)
если телефона нет:
  Тел: не указан
если ticket_context отсутствует:
  legacy fallback карточки сохраняется
```

Проверки Stage 2.1:

```text
compileall: OK
unittest: OK
reconciliation test_dev_max: expected clean
ticket_context latest rows checked read-only
manual smoke by Codex in this run: not executed
manual smoke через тестового MAX-бота все еще обязателен перед production rollout
```

## Next Stage

```text
История номера по location_id
```
