# Архитектурный Roadmap (RU)

## Текущее состояние
- Архитектура разделена на модули: `helpdesk`, `network`, `admin`, `common`, `config`.
- Роли и доступ централизованы в `access_service`.
- Заявки имеют минимальную модель (stage 4), репозитории: `memory` и `sqlite`.
- Network tools отделены в самостоятельный блок с policy-ограничениями и feature flags.

## Что уже реализовано
- Helpdesk flow: создание заявки, список заявок пользователя, обработка заявки специалистом.
- Групповой чат специалистов: action-кнопки + команды (`/take`, `/release`, `/close`, `/clarify`, `/open`).
- Corporate restrictions для network tools: allowed subnets/domain suffixes/hosts/device types.
- Конфиг через env + валидация в `config/config.py`.

## Сознательно оставленные слабые места
- Нет постоянного хранения связи `ticket <-> group message` (runtime-only).
- Нет полноценного audit trail/истории статусов/комментариев.
- Нет фоновых worker-процессов.
- SQLite подходит для малого объема, но ограничен для роста.

## Эволюция архитектуры

### Нужно уже скоро
1. Перейти на PostgreSQL как основной backend заявок.
2. Добавить минимальные миграции (schema versioning) для управляемого развития модели.
3. Вынести runtime-связку сообщений в персистентное хранилище (таблица/кэш) при сохранении текущего API.
4. Добавить базовую наблюдаемость: структурированные логи + correlation id.

### Полезно позже
1. Redis для:
   - session/runtime-state;
   - rate limit/cooldown;
   - быстрых lookup-связок по заявкам/сообщениям.
2. Вынос network diagnostics в отдельный backend/service с API.
3. Расширение модели заявок:
   - приоритет;
   - SLA-поля;
   - метки/очереди.
4. Объектное хранилище для вложений (если будут фото/файлы в тикетах).

### Пока рано
1. Полный event sourcing.
2. Сложная ITSM-модель с большим количеством сущностей.
3. Тяжелая контейнеризация и оркестрация без операционной потребности.

## Направления развития по темам
- PostgreSQL: оставить текущие service/repository границы, добавить новый repository adapter.
- Redis: подключать как инфраструктурный cache/state слой, не размазывая логику по handlers.
- Network service: заменить `LocalDiagnosticsAdapter` на API adapter, сохранив `NetworkToolsService` фасад.
- Ticket model: расширять строго инкрементально с миграциями и backward-compatible чтением.
- Message links: перейти от runtime-only к устойчивому storage с TTL/cleanup стратегией.
- Корпоративные устройства: расширять policy и templates через конфиг + отдельные справочники.

## Рекомендуемый backlog следующего этапа
1. PostgreSQL adapter + миграции + переключение backend через конфиг.
2. Персистентная таблица для `ticket <-> group message`.
3. Базовый telemetry набор (метрики ошибок, latency network tools, количество заявок по статусам).
4. Минимальный набор unit/integration тестов для ticket repository и network policy.
