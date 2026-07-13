CREATE TABLE IF NOT EXISTS helpdesk.knowledge_articles (
    id BIGSERIAL PRIMARY KEY,
    hotel_id BIGINT NULL,
    category_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source_ticket_key TEXT NULL,
    source_location_id BIGINT NULL,
    author_user_id BIGINT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_helpdesk_knowledge_articles_hotel_category_active
    ON helpdesk.knowledge_articles(hotel_id, category_id, is_active);

CREATE INDEX IF NOT EXISTS idx_helpdesk_knowledge_articles_source_ticket
    ON helpdesk.knowledge_articles(source_ticket_key);

CREATE INDEX IF NOT EXISTS idx_helpdesk_knowledge_articles_source_location
    ON helpdesk.knowledge_articles(source_location_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'maxbot') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA helpdesk TO maxbot';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE helpdesk.knowledge_articles TO maxbot';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA helpdesk TO maxbot';
    END IF;
END $$;
