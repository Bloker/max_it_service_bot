CREATE TABLE IF NOT EXISTS helpdesk.media_attachments (
    id BIGSERIAL PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_id BIGINT NULL,
    ticket_key TEXT NULL,
    hotel_id BIGINT NULL,
    location_id BIGINT NULL,
    media_type TEXT NOT NULL,
    mime_type TEXT NULL,
    file_name TEXT NULL,
    file_size BIGINT NULL,
    max_file_id TEXT NULL,
    max_attachment_id TEXT NULL,
    storage_path TEXT NULL,
    public_url TEXT NULL,
    checksum TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by BIGINT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT media_attachments_owner_type_chk
        CHECK (owner_type IN ('ticket_comment', 'knowledge_article')),
    CONSTRAINT media_attachments_media_type_chk
        CHECK (media_type IN ('photo', 'video', 'document'))
);

CREATE INDEX IF NOT EXISTS idx_media_attachments_owner
ON helpdesk.media_attachments (owner_type, owner_id);

CREATE INDEX IF NOT EXISTS idx_media_attachments_ticket
ON helpdesk.media_attachments (ticket_key);

CREATE INDEX IF NOT EXISTS idx_media_attachments_location
ON helpdesk.media_attachments (hotel_id, location_id);

CREATE INDEX IF NOT EXISTS idx_media_attachments_created_at
ON helpdesk.media_attachments (created_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'maxbot') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA helpdesk TO maxbot';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE helpdesk.media_attachments TO maxbot';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA helpdesk TO maxbot';
    END IF;
END $$;
