import os
import unittest
from unittest.mock import patch

from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base
from app.db.engine import create_sqlalchemy_engine
from app.db.models import (
    AuditLog,
    KnowledgeArticle,
    KnowledgeScope,
    NetworkToolRun,
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketEvent,
)
from app.db.session import create_session_factory
from app.db.url import make_sqlalchemy_url, mask_sqlalchemy_url
from config.config import get_config


class SqlAlchemyFoundationTests(unittest.TestCase):
    def _config(self):
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_TICKET_BACKEND": "postgres",
            "MAX_TICKET_PG_HOST": "127.0.0.1",
            "MAX_TICKET_PG_PORT": "5432",
            "MAX_TICKET_PG_DB": "test_dev_max",
            "MAX_TICKET_PG_USER": "postgres",
            "MAX_TICKET_PG_PASSWORD": "secret",
            "MAX_TICKET_PG_SSLMODE": "disable",
            "MAX_TICKET_PG_CONNECT_TIMEOUT_SEC": "5",
            "MAX_WIFI_LINK_EMAIL": "",
            "MAX_WIFI_LINK_PASSWORD": "",
            "MAX_NETARIUM_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            return get_config()

    def test_url_builder_and_masking(self) -> None:
        cfg = self._config()

        url = make_sqlalchemy_url(cfg)
        masked = mask_sqlalchemy_url(url)

        self.assertEqual(url.drivername, "postgresql+psycopg")
        self.assertEqual(url.database, "test_dev_max")
        self.assertEqual(url.query["sslmode"], "disable")
        self.assertNotIn("secret", masked)
        self.assertIn("***", masked)

    def test_engine_and_session_factory_can_be_created_without_connecting(self) -> None:
        cfg = self._config()

        engine = create_sqlalchemy_engine(cfg)
        session_factory = create_session_factory(engine)

        self.assertIsInstance(engine, Engine)
        self.assertIsNotNone(session_factory)
        engine.dispose()

    def test_metadata_contains_expected_tables(self) -> None:
        expected = {
            "helpdesk.tickets",
            "helpdesk.ticket_events",
            "helpdesk.ticket_comments",
            "helpdesk.ticket_attachments",
            "helpdesk.knowledge_articles",
            "helpdesk.knowledge_scopes",
            "ops.audit_log",
            "network.tool_runs",
        }

        self.assertTrue(expected.issubset(set(Base.metadata.tables.keys())))

    def test_model_schema_names(self) -> None:
        self.assertEqual(Ticket.__table__.schema, "helpdesk")
        self.assertEqual(TicketEvent.__table__.schema, "helpdesk")
        self.assertEqual(TicketComment.__table__.schema, "helpdesk")
        self.assertEqual(TicketAttachment.__table__.schema, "helpdesk")
        self.assertEqual(KnowledgeArticle.__table__.schema, "helpdesk")
        self.assertEqual(KnowledgeScope.__table__.schema, "helpdesk")
        self.assertEqual(AuditLog.__table__.schema, "ops")
        self.assertEqual(NetworkToolRun.__table__.schema, "network")

    def test_jsonb_columns_are_postgresql_jsonb(self) -> None:
        self.assertIsInstance(TicketEvent.__table__.c.payload.type, JSONB)
        self.assertIsInstance(TicketComment.__table__.c.meta.type, JSONB)
        self.assertIsInstance(TicketAttachment.__table__.c.meta.type, JSONB)
        self.assertIsInstance(KnowledgeArticle.__table__.c.metadata.type, JSONB)
        self.assertIsInstance(KnowledgeScope.__table__.c.metadata.type, JSONB)
        self.assertIsInstance(AuditLog.__table__.c.payload.type, JSONB)
        self.assertIsInstance(AuditLog.__table__.c.metadata.type, JSONB)
        self.assertIsInstance(NetworkToolRun.__table__.c.metadata.type, JSONB)


if __name__ == "__main__":
    unittest.main()
