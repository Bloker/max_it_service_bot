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
  [Проблема Wi-Fi у гостя]   если для отеля включен feature `wifi_guest_issue`
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

## Stage 3 Status

Статус: completed locally, test-only, production unchanged.

Git / rollout status:

```text
base local commit: 42e06c6 stabilize jamaica test room ticket ux
production changed: no
production service restarted: no
production DB changed/migrated: no
production commit: fadf6d3 add integration observability events
test DB: test_dev_max
```

Что добавлено:

```text
В групповую карточку Jamaica room-ticket добавлена кнопка `История номера`.
Кнопка показывается только если у заявки есть `ticket_context` с ненулевым `location_id`.
Для `Прочее` без номера кнопка не показывается.
История строится по `helpdesk.ticket_context.hotel_id + location_id`.
Источник статуса и времени: `helpdesk.ticket_context` + `helpdesk.tickets`.
Лимит: 10 последних заявок.
Текущая заявка из истории исключается.
История отправляется отдельным сообщением в группу и не заменяет основную карточку.
Кнопка `История номера` сохраняется после `Взять в работу` и `Закрыть`.
SQL defect fixed: nullable placeholder removed from WHERE construction.
```

Формат ответа:

```text
История номера

Объект:
Номер 112

Последние N заявок

T-xxxxx · Категория · Статус · 07.07 14:12
```

Локально добавленные файлы Stage 3:

```text
app/helpdesk/models/room_ticket_history.py
app/helpdesk/services/room_history_service.py
app/helpdesk/texts/room_history_texts.py
tests/test_room_history_service.py
tests/test_room_history_texts.py
```

Локально измененные файлы Stage 3:

```text
app/bot/handlers/callbacks.py
app/bot/handlers/messages.py
app/helpdesk/keyboards/helpdesk_keyboards.py
app/helpdesk/repositories/postgres_room_ticket_context_repository.py
app/helpdesk/repositories/room_ticket_context_repository.py
app/helpdesk/runtime.py
app/helpdesk/services/ticket_card_update_service.py
app/helpdesk/texts/formatters.py
app/helpdesk/texts/specialist_texts.py
tests/test_helpdesk_keyboards.py
tests/test_ticket_card_update_service.py
```

Проверки Stage 3:

```text
read-only production sanity:
  health: OK, mode=webhook
  service: active / enabled
  production HEAD: fadf6d3 add integration observability events

read-only test DB:
  current_database() = test_dev_max
  helpdesk.ticket_context rows = 11
  latest context rows include T-00099/T-00098/T-00097/T-00096/T-00095
  helpdesk.tickets uses status_code + created_at + closed_at

.venv/bin/python -m compileall app tests config scripts main.py: OK
.venv/bin/python -m unittest discover -s tests -v: OK, 211 tests
.venv/bin/python -m unittest tests.test_room_history_service tests.test_room_history_texts tests.test_helpdesk_keyboards tests.test_ticket_card_update_service -v: OK, 31 tests
git diff --check: OK
```

Manual smoke Stage 3:

```text
room history smoke: OK
cottage history smoke: OK
other without number has no history button: OK
history button preserved after status changes: OK
```

## Next Stage

```text
Stage 3.1: локальный commit без push;
после отдельной команды владельца — следующий hotel-specific UX шаг
```

## Stage 4.4 Internal Comments

```text
Кнопка «Комментарий» в карточке Jamaica-заявки предназначена только для
внутренней истории IT. Она не отправляет сообщение пользователю, не создаёт
knowledge_articles и не отображается в базе знаний.

Комментарий сохраняется в helpdesk.ticket_comments с direction=internal_comment.
Metadata содержит hotel_id, location_id, объект и категорию из ticket_context,
если контекст номера существует. В карточке показывается только последний блок
«Внутренний комментарий» с preview текста без служебных полей.

Кнопка расположена отдельной строкой после «Запросить уточнение». Для закрытой
заявки комментарий недоступен, а «История номера» остаётся доступной.

База знаний продолжает пополняться только вручную через
«База знаний -> Добавить запись». Статус: local/test-only; production не изменялся.

## Stage 4.7: Knowledge Base, internal comments and media MVP

Статус: реализация завершена локально для `test_dev_max`; production не изменялся.
Полный manual smoke, включая закрытие с media, выполняется отдельно на тестовом MAX-боте.

```text
KB: разделы -> категории -> темы -> карточка темы.
В карточке темы скрыты служебные source/object/status поля.
Ручная запись и «Заметка» из Jamaica-заявки используют flow: тема -> текст/media
-> 15 секунд тишины -> сохранение.

Внутренний «Комментарий» не спрашивает тему, сохраняется только в
helpdesk.ticket_comments с direction=internal_comment и не доступен пользователю.
Для room-ticket metadata включает location_id и категорию из ticket_context.

Поддерживаемые медиа MVP: фото, видео и файлы. Audio/voice намеренно исключены:
текущая версия maxapi не обеспечивает надёжную обработку голосовых сообщений.
Вложения хранятся в helpdesk.media_attachments как metadata и reusable MAX token;
binary-файлы и private media URL локально не сохраняются и не попадают в Git.

Закрытие с ответом собирает text/photo/video/file в том же 15-секундном окне,
после успешной доставки закрывает заявку. Пользователь получает «Ответ специалиста»
и кнопку «Главное меню».
```
```
