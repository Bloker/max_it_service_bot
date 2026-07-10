BEGIN;

ALTER TABLE helpdesk.knowledge_articles
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE helpdesk.knowledge_articles
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS visibility,
    DROP COLUMN IF EXISTS published_at,
    DROP COLUMN IF EXISTS source,
    DROP COLUMN IF EXISTS tags;

UPDATE helpdesk.knowledge_articles article
SET scope_id = scope.id
FROM helpdesk.knowledge_scopes scope
WHERE article.scope_id IS NULL
  AND scope.scope_type = 'hotel'
  AND scope.hotel_id = article.hotel_id;

UPDATE helpdesk.knowledge_articles article
SET scope_id = scope.id
FROM helpdesk.knowledge_scopes scope
WHERE article.scope_id IS NULL
  AND scope.code = 'jamaica';

ALTER TABLE helpdesk.knowledge_articles
    ALTER COLUMN scope_id SET NOT NULL,
    ALTER COLUMN category_id SET NOT NULL;

ALTER TABLE helpdesk.knowledge_articles
    DROP CONSTRAINT IF EXISTS knowledge_articles_scope_id_fkey;

ALTER TABLE helpdesk.knowledge_articles
    ADD CONSTRAINT knowledge_articles_scope_id_fkey
    FOREIGN KEY (scope_id) REFERENCES helpdesk.knowledge_scopes(id);

DROP TABLE IF EXISTS helpdesk.ticket_knowledge_links;

UPDATE helpdesk.ticket_comments comment
SET meta = COALESCE(comment.meta, '{}'::jsonb) || jsonb_build_object(
    'knowledge_article_id', article.id,
    'knowledge_title', article.title,
    'added_to_knowledge_base', TRUE,
    'source', 'ticket_note'
)
FROM helpdesk.tickets ticket
JOIN helpdesk.knowledge_articles article
  ON article.source_ticket_key = ticket.ticket_key
WHERE comment.ticket_id = ticket.id
  AND comment.direction = 'specialist_comment'
  AND comment.meta ? 'knowledge_title'
  AND article.title = comment.meta ->> 'knowledge_title';

DROP INDEX IF EXISTS helpdesk.idx_helpdesk_knowledge_articles_hotel_category;
DROP INDEX IF EXISTS helpdesk.idx_knowledge_articles_scope_category_status;
DROP INDEX IF EXISTS helpdesk.idx_helpdesk_knowledge_articles_hotel_category_active;
DROP INDEX IF EXISTS helpdesk.idx_knowledge_articles_scope_category_active;

CREATE INDEX IF NOT EXISTS idx_knowledge_articles_scope_category_active
    ON helpdesk.knowledge_articles (scope_id, category_id, is_active, sort_order, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_helpdesk_knowledge_articles_source_ticket
    ON helpdesk.knowledge_articles (source_ticket_key);

CREATE INDEX IF NOT EXISTS idx_helpdesk_knowledge_articles_source_location
    ON helpdesk.knowledge_articles (source_location_id);

COMMIT;
