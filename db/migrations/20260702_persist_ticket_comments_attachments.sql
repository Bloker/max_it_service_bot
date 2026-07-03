BEGIN;

ALTER TABLE helpdesk.ticket_comments
    ADD COLUMN IF NOT EXISTS author_role TEXT NULL,
    ADD COLUMN IF NOT EXISTS source_message_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS target_message_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_comments_direction
ON helpdesk.ticket_comments(ticket_id, direction, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_comments_target_mid
ON helpdesk.ticket_comments(target_message_id)
WHERE target_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_comments_attached_reply
ON helpdesk.ticket_comments(ticket_id, created_at DESC)
WHERE direction = 'user_reply' AND (meta->>'attached_to_card') = 'true';

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_attachments_ticket
ON helpdesk.ticket_attachments(ticket_id, created_at);

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_attachments_comment
ON helpdesk.ticket_attachments(comment_id)
WHERE comment_id IS NOT NULL;

COMMIT;
