BEGIN;

CREATE OR REPLACE FUNCTION helpdesk.sync_from_legacy_helpdesk_tickets()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_category_code TEXT;
    v_status_code TEXT;
    v_ticket_id BIGINT;
BEGIN
    IF NEW.ticket_id IS NULL
        OR btrim(NEW.ticket_id) = ''
        OR btrim(NEW.ticket_id) = 'PENDING'
    THEN
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

DELETE FROM helpdesk.tickets t
WHERE t.ticket_key = 'PENDING'
  AND NOT EXISTS (
      SELECT 1
      FROM public.helpdesk_tickets p
      WHERE p.ticket_id = t.ticket_key
  );

INSERT INTO ops.migrations_meta(version, description)
VALUES ('2026_05_08_fix_pending_ticket_sync', 'Ignore transient PENDING ticket key and remove orphan normalized row')
ON CONFLICT (version) DO NOTHING;

COMMIT;
