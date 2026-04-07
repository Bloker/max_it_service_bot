BEGIN;

CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS helpdesk;
CREATE SCHEMA IF NOT EXISTS integration;
CREATE SCHEMA IF NOT EXISTS network;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS auth.users (
    id BIGSERIAL PRIMARY KEY,
    external_user_id BIGINT NOT NULL UNIQUE,
    display_name TEXT,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth.roles (
    id SMALLSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth.user_roles (
    user_id BIGINT NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role_id SMALLINT NOT NULL REFERENCES auth.roles(id),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ NULL,
    assigned_by BIGINT NULL,
    PRIMARY KEY (user_id, role_id, valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_user_roles_active
ON auth.user_roles(user_id, role_id)
WHERE valid_to IS NULL;

CREATE TABLE IF NOT EXISTS auth.hotels (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS auth.features (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS auth.hotel_features (
    hotel_id INTEGER NOT NULL REFERENCES auth.hotels(id) ON DELETE CASCADE,
    feature_id INTEGER NOT NULL REFERENCES auth.features(id) ON DELETE CASCADE,
    PRIMARY KEY (hotel_id, feature_id)
);

CREATE TABLE IF NOT EXISTS auth.user_hotel_memberships (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    hotel_id INTEGER NOT NULL REFERENCES auth.hotels(id),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ NULL,
    assigned_by BIGINT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_user_hotel_active
ON auth.user_hotel_memberships(user_id)
WHERE valid_to IS NULL;

CREATE TABLE IF NOT EXISTS auth.access_requests (
    id BIGSERIAL PRIMARY KEY,
    external_user_id BIGINT NOT NULL,
    requested_name TEXT,
    requested_phone TEXT,
    status TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ NULL,
    processed_by BIGINT NULL,
    rejection_reason TEXT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_access_requests_pending
ON auth.access_requests(external_user_id)
WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS helpdesk.categories (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS helpdesk.statuses (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS helpdesk.tickets (
    id BIGSERIAL PRIMARY KEY,
    ticket_key TEXT NOT NULL UNIQUE,
    requester_user_id BIGINT NOT NULL,
    requester_name TEXT,
    requester_phone TEXT,
    requester_department TEXT,
    category_code TEXT NOT NULL REFERENCES helpdesk.categories(code),
    status_code TEXT NOT NULL REFERENCES helpdesk.statuses(code),
    assignee_user_id BIGINT NULL,
    assignee_name TEXT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_helpdesk_tickets_requester
ON helpdesk.tickets(requester_user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_helpdesk_tickets_status
ON helpdesk.tickets(status_code, updated_at DESC);

CREATE TABLE IF NOT EXISTS helpdesk.ticket_events (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES helpdesk.tickets(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor_user_id BIGINT NULL,
    actor_name TEXT NULL,
    old_status_code TEXT NULL,
    new_status_code TEXT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_events_ticket
ON helpdesk.ticket_events(ticket_id, created_at);

CREATE TABLE IF NOT EXISTS helpdesk.ticket_comments (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES helpdesk.tickets(id) ON DELETE CASCADE,
    author_user_id BIGINT NULL,
    author_name TEXT NULL,
    direction TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS helpdesk.ticket_attachments (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES helpdesk.tickets(id) ON DELETE CASCADE,
    comment_id BIGINT NULL REFERENCES helpdesk.ticket_comments(id) ON DELETE CASCADE,
    platform_attachment_type TEXT NULL,
    platform_attachment_ref TEXT NULL,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS integration.chats (
    id BIGSERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    external_chat_id TEXT NOT NULL,
    chat_type TEXT NOT NULL,
    title TEXT NULL,
    UNIQUE (platform, external_chat_id)
);

CREATE TABLE IF NOT EXISTS integration.message_links (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES helpdesk.tickets(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS integration.outbox (
    id BIGSERIAL PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS integration.inbox_dedup (
    platform TEXT NOT NULL,
    update_id TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (platform, update_id)
);

CREATE TABLE IF NOT EXISTS network.tool_runs (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id BIGINT NULL,
    actor_name TEXT NULL,
    tool TEXT NOT NULL,
    target TEXT NOT NULL,
    normalized_target TEXT NULL,
    policy_decision TEXT NULL,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    duration_ms INTEGER NULL,
    output_excerpt TEXT NULL,
    error_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ops.audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id BIGINT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ops.settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ops.migrations_meta (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO auth.roles(code, name) VALUES
    ('user', 'Пользователь'),
    ('it_specialist', 'IT специалист'),
    ('admin', 'Администратор')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO auth.hotels(code, name, is_active) VALUES
    ('jamaica', 'Отель Джамайка', TRUE),
    ('old_anapa', 'Отель Старинная Анапа', TRUE)
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_active = EXCLUDED.is_active;

INSERT INTO auth.features(code, name, is_active) VALUES
    ('wifi_guest_issue', 'Проблема Wi-Fi у гостя', TRUE),
    ('tv_guest_issue', 'Проблема TV у гостя', TRUE),
    ('create_ticket', 'Создание обращения', TRUE),
    ('my_tickets', 'Просмотр моих обращений', TRUE)
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, is_active = EXCLUDED.is_active;

INSERT INTO auth.hotel_features(hotel_id, feature_id)
SELECT h.id, f.id
FROM auth.hotels h
JOIN auth.features f ON f.code IN ('wifi_guest_issue', 'tv_guest_issue')
WHERE h.code = 'jamaica'
ON CONFLICT (hotel_id, feature_id) DO NOTHING;

INSERT INTO auth.hotel_features(hotel_id, feature_id)
SELECT h.id, f.id
FROM auth.hotels h
JOIN auth.features f ON f.code = 'wifi_guest_issue'
WHERE h.code = 'old_anapa'
ON CONFLICT (hotel_id, feature_id) DO NOTHING;

INSERT INTO helpdesk.statuses(code, display_name, is_terminal) VALUES
    ('new', 'новое', FALSE),
    ('in_progress', 'в работе', FALSE),
    ('waiting_user', 'ожидает пользователя', FALSE),
    ('closed', 'закрыто', TRUE)
ON CONFLICT (code) DO UPDATE
SET display_name = EXCLUDED.display_name, is_terminal = EXCLUDED.is_terminal;

INSERT INTO helpdesk.categories(code, display_name, is_active) VALUES
    ('cat_access', 'Доступы и учетные записи', TRUE),
    ('cat_pc_software', 'ПК и программное обеспечение', TRUE),
    ('cat_printers', 'Принтеры', TRUE),
    ('cat_network_wifi', 'Сеть / Wi-Fi', TRUE),
    ('cat_vpn', 'VPN', TRUE),
    ('cat_telephony', 'Телефония', TRUE),
    ('cat_other', 'Прочее', TRUE)
ON CONFLICT (code) DO UPDATE
SET display_name = EXCLUDED.display_name, is_active = EXCLUDED.is_active;

INSERT INTO helpdesk.categories(code, display_name, is_active)
SELECT
    'cat_' || SUBSTRING(md5(btrim(t.category)) FROM 1 FOR 12) AS code,
    btrim(t.category) AS display_name,
    TRUE AS is_active
FROM public.helpdesk_tickets t
WHERE t.category IS NOT NULL AND btrim(t.category) <> ''
ON CONFLICT (display_name) DO NOTHING;

INSERT INTO helpdesk.tickets(
    ticket_key,
    requester_user_id,
    requester_name,
    requester_phone,
    requester_department,
    category_code,
    status_code,
    assignee_user_id,
    assignee_name,
    description,
    created_at,
    updated_at,
    closed_at
)
SELECT
    l.ticket_id,
    l.requester_user_id,
    l.requester_name,
    l.requester_phone,
    l.requester_department,
    c.code AS category_code,
    CASE l.status
        WHEN 'новое' THEN 'new'
        WHEN 'в работе' THEN 'in_progress'
        WHEN 'ожидает пользователя' THEN 'waiting_user'
        WHEN 'закрыто' THEN 'closed'
        ELSE 'new'
    END AS status_code,
    l.assignee_user_id,
    l.assignee_name,
    l.text,
    l.created_at,
    l.updated_at,
    CASE WHEN l.status = 'закрыто' THEN l.updated_at ELSE NULL END AS closed_at
FROM public.helpdesk_tickets l
JOIN helpdesk.categories c ON c.display_name = l.category
WHERE l.ticket_id IS NOT NULL AND btrim(l.ticket_id) <> ''
ON CONFLICT (ticket_key) DO NOTHING;

INSERT INTO helpdesk.ticket_events(ticket_id, event_type, actor_user_id, actor_name, old_status_code, new_status_code, payload)
SELECT
    t.id,
    'migrated_from_legacy',
    NULL,
    'migration',
    NULL,
    t.status_code,
    '{"source":"public.helpdesk_tickets"}'::jsonb
FROM helpdesk.tickets t
LEFT JOIN helpdesk.ticket_events e ON e.ticket_id = t.id
WHERE e.id IS NULL;

CREATE OR REPLACE FUNCTION helpdesk.sync_from_legacy_helpdesk_tickets()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_category_code TEXT;
    v_status_code TEXT;
    v_ticket_id BIGINT;
BEGIN
    IF NEW.ticket_id IS NULL OR btrim(NEW.ticket_id) = '' THEN
        RETURN NEW;
    END IF;

    IF NEW.category IS NULL OR btrim(NEW.category) = '' THEN
        NEW.category := 'Прочее';
    END IF;

    SELECT code INTO v_category_code
    FROM helpdesk.categories
    WHERE display_name = NEW.category;

    IF v_category_code IS NULL THEN
        v_category_code := 'cat_' || SUBSTRING(md5(NEW.category) FROM 1 FOR 12);
        INSERT INTO helpdesk.categories(code, display_name, is_active)
        VALUES (v_category_code, NEW.category, TRUE)
        ON CONFLICT (code) DO UPDATE
        SET display_name = EXCLUDED.display_name, is_active = EXCLUDED.is_active;
    END IF;

    v_status_code := CASE NEW.status
        WHEN 'новое' THEN 'new'
        WHEN 'в работе' THEN 'in_progress'
        WHEN 'ожидает пользователя' THEN 'waiting_user'
        WHEN 'закрыто' THEN 'closed'
        ELSE 'new'
    END;

    INSERT INTO helpdesk.tickets(
        ticket_key,
        requester_user_id,
        requester_name,
        requester_phone,
        requester_department,
        category_code,
        status_code,
        assignee_user_id,
        assignee_name,
        description,
        created_at,
        updated_at,
        closed_at
    )
    VALUES (
        NEW.ticket_id,
        NEW.requester_user_id,
        NEW.requester_name,
        NEW.requester_phone,
        NEW.requester_department,
        v_category_code,
        v_status_code,
        NEW.assignee_user_id,
        NEW.assignee_name,
        NEW.text,
        NEW.created_at,
        NEW.updated_at,
        CASE WHEN v_status_code = 'closed' THEN NEW.updated_at ELSE NULL END
    )
    ON CONFLICT (ticket_key) DO UPDATE
    SET requester_user_id = EXCLUDED.requester_user_id,
        requester_name = EXCLUDED.requester_name,
        requester_phone = EXCLUDED.requester_phone,
        requester_department = EXCLUDED.requester_department,
        category_code = EXCLUDED.category_code,
        status_code = EXCLUDED.status_code,
        assignee_user_id = EXCLUDED.assignee_user_id,
        assignee_name = EXCLUDED.assignee_name,
        description = EXCLUDED.description,
        created_at = EXCLUDED.created_at,
        updated_at = EXCLUDED.updated_at,
        closed_at = EXCLUDED.closed_at;

    SELECT id INTO v_ticket_id
    FROM helpdesk.tickets
    WHERE ticket_key = NEW.ticket_id;

    INSERT INTO helpdesk.ticket_events(
        ticket_id,
        event_type,
        actor_user_id,
        actor_name,
        old_status_code,
        new_status_code,
        payload
    )
    VALUES (
        v_ticket_id,
        'synced_from_legacy',
        NEW.assignee_user_id,
        NEW.assignee_name,
        NULL,
        v_status_code,
        jsonb_build_object('op', TG_OP, 'source', 'legacy_trigger')
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_legacy_helpdesk_tickets ON public.helpdesk_tickets;
CREATE TRIGGER trg_sync_legacy_helpdesk_tickets
AFTER INSERT OR UPDATE ON public.helpdesk_tickets
FOR EACH ROW
EXECUTE FUNCTION helpdesk.sync_from_legacy_helpdesk_tickets();

INSERT INTO ops.migrations_meta(version, description)
VALUES ('2026_04_07_normalized_schema', 'Normalized schemas and legacy sync trigger')
ON CONFLICT (version) DO NOTHING;

COMMIT;
