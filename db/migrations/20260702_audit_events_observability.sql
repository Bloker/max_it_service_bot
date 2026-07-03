BEGIN;

ALTER TABLE helpdesk.ticket_events
    ADD COLUMN IF NOT EXISTS actor_role TEXT NULL,
    ADD COLUMN IF NOT EXISTS source TEXT NULL,
    ADD COLUMN IF NOT EXISTS related_message_id TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_events_type
ON helpdesk.ticket_events(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_helpdesk_ticket_events_actor
ON helpdesk.ticket_events(actor_user_id, created_at DESC)
WHERE actor_user_id IS NOT NULL;

ALTER TABLE ops.audit_log
    ADD COLUMN IF NOT EXISTS actor_role TEXT NULL,
    ADD COLUMN IF NOT EXISTS resource_type TEXT NULL,
    ADD COLUMN IF NOT EXISTS resource_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS result TEXT NULL,
    ADD COLUMN IF NOT EXISTS reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE ops.audit_log
SET resource_type = COALESCE(resource_type, entity_type),
    resource_id = COALESCE(resource_id, entity_id),
    metadata = COALESCE(metadata, payload, '{}'::jsonb)
WHERE resource_type IS NULL OR resource_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_ops_audit_log_action
ON ops.audit_log(action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_audit_log_actor
ON ops.audit_log(actor_user_id, created_at DESC)
WHERE actor_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ops_audit_log_resource
ON ops.audit_log(resource_type, resource_id, created_at DESC);

ALTER TABLE network.tool_runs
    ADD COLUMN IF NOT EXISTS status TEXT NULL,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS output_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS feature_enabled BOOLEAN NULL,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE network.tool_runs
SET status = COALESCE(status, CASE WHEN success THEN 'success' ELSE 'failed' END),
    started_at = COALESCE(started_at, created_at),
    finished_at = COALESCE(finished_at, created_at)
WHERE status IS NULL OR started_at IS NULL OR finished_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_network_tool_runs_actor
ON network.tool_runs(actor_user_id, created_at DESC)
WHERE actor_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_network_tool_runs_tool
ON network.tool_runs(tool, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_network_tool_runs_status
ON network.tool_runs(status, created_at DESC);

COMMIT;
