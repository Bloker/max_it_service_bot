"""
Заглушка под миграции БД.

План:
- Перейти на Alembic и хранить миграции в app/infrastructure/database/migrations/
- Первичная схема (v1):
  * users
  * incidents
  * messages (dedup по platform_message_id)
  * outbox (PENDING/SENT/FAILED, attempts, last_error)
- Индексы:
  * users.platform_user_id unique
  * messages.platform_message_id unique
  * incidents.user_id + last_activity_at
  * outbox.status + updated_at (или next_attempt_at)
"""