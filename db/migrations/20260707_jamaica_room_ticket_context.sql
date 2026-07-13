-- Jamaica room-ticket schema. Apply only through the approved rollout procedure.

CREATE TABLE IF NOT EXISTS helpdesk.locations (
    id BIGSERIAL PRIMARY KEY,
    hotel_id INTEGER NOT NULL REFERENCES auth.hotels(id),
    location_code TEXT NOT NULL,
    location_type TEXT NOT NULL,
    building_name TEXT,
    room_number TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_helpdesk_locations_type
        CHECK (location_type IN ('room', 'cottage', 'common')),
    CONSTRAINT uq_helpdesk_locations_hotel_room
        UNIQUE (hotel_id, room_number),
    CONSTRAINT uq_helpdesk_locations_hotel_code
        UNIQUE (hotel_id, location_code)
);

CREATE INDEX IF NOT EXISTS idx_helpdesk_locations_hotel_active
ON helpdesk.locations(hotel_id, is_active, sort_order);

CREATE INDEX IF NOT EXISTS idx_helpdesk_locations_hotel_building
ON helpdesk.locations(hotel_id, building_name, sort_order);

CREATE TABLE IF NOT EXISTS helpdesk.issue_categories (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    requires_location BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_helpdesk_issue_categories_active
ON helpdesk.issue_categories(is_active, sort_order);

CREATE TABLE IF NOT EXISTS helpdesk.hotel_issue_categories (
    hotel_id INTEGER NOT NULL REFERENCES auth.hotels(id),
    category_id BIGINT NOT NULL REFERENCES helpdesk.issue_categories(id),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    default_priority TEXT,
    route_group_code TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (hotel_id, category_id)
);

CREATE INDEX IF NOT EXISTS idx_helpdesk_hotel_issue_categories_enabled
ON helpdesk.hotel_issue_categories(hotel_id, is_enabled, sort_order);

CREATE TABLE IF NOT EXISTS helpdesk.ticket_context (
    id BIGSERIAL PRIMARY KEY,
    ticket_key TEXT NOT NULL UNIQUE,
    hotel_id INTEGER NOT NULL REFERENCES auth.hotels(id),
    location_id BIGINT REFERENCES helpdesk.locations(id),
    issue_category_id BIGINT REFERENCES helpdesk.issue_categories(id),
    room_number_snapshot TEXT,
    location_display_snapshot TEXT,
    category_snapshot TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_context_ticket_key
ON helpdesk.ticket_context(ticket_key);

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_context_hotel_location
ON helpdesk.ticket_context(hotel_id, location_id);

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_context_hotel_category
ON helpdesk.ticket_context(hotel_id, issue_category_id);

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_context_created_at
ON helpdesk.ticket_context(created_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'maxbot') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA auth, helpdesk TO maxbot';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE auth.hotels TO maxbot';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE helpdesk.locations TO maxbot';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE helpdesk.issue_categories TO maxbot';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE helpdesk.hotel_issue_categories TO maxbot';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE helpdesk.ticket_context TO maxbot';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA auth TO maxbot';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA helpdesk TO maxbot';
    END IF;
END $$;
