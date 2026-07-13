CREATE TABLE IF NOT EXISTS helpdesk.knowledge_scopes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    hotel_id BIGINT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT knowledge_scopes_type_chk
        CHECK (scope_type IN ('hotel', 'global', 'infrastructure', 'system'))
);

CREATE INDEX IF NOT EXISTS idx_helpdesk_knowledge_scopes_active_sort
    ON helpdesk.knowledge_scopes(is_active, sort_order);

ALTER TABLE helpdesk.knowledge_articles
    ADD COLUMN IF NOT EXISTS scope_id BIGINT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'knowledge_articles_scope_id_fkey'
          AND connamespace = 'helpdesk'::regnamespace
    ) THEN
        ALTER TABLE helpdesk.knowledge_articles
            ADD CONSTRAINT knowledge_articles_scope_id_fkey
            FOREIGN KEY (scope_id) REFERENCES helpdesk.knowledge_scopes(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_knowledge_articles_scope_category_active
    ON helpdesk.knowledge_articles(scope_id, category_id, is_active, sort_order, created_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'maxbot') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA helpdesk TO maxbot';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE helpdesk.knowledge_scopes TO maxbot';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA helpdesk TO maxbot';
    END IF;
END $$;
