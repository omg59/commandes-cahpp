"""Garantit une fermeture déterministe, même sans passage du ramasse-miettes."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cahpp_app.database import Database


class DatabaseResourcesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "resources.sqlite3")

    def assert_closed(self, connection):
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_context_commits_and_closes(self):
        with self.db.connect() as connection:
            connection.execute("INSERT INTO settings(key, value) VALUES ('resource', 'ok')")
        self.assert_closed(connection)
        self.assertEqual(self.db.get_settings()["resource"], "ok")

    def test_context_rolls_back_and_closes_on_error(self):
        with self.assertRaises(ValueError):
            with self.db.connect() as connection:
                connection.execute("INSERT INTO settings(key, value) VALUES ('resource', 'ko')")
                raise ValueError("Interruption simulée")
        self.assert_closed(connection)
        self.assertNotIn("resource", self.db.get_settings())

    def test_initializer_and_read_helpers_release_all_connections(self):
        original = sqlite3.connect
        handles = []

        def track(*args, **kwargs):
            connection = original(*args, **kwargs)
            handles.append(connection)  # Empêche toute fermeture par le ramasse-miettes.
            return connection

        with patch("cahpp_app.database.sqlite3.connect", side_effect=track):
            database = Database(self.root / "tracked.sqlite3")
            for _ in range(20):
                database.get_settings()
                database.search_products()
                database.dashboard_stats()
        self.assertGreater(len(handles), 60)
        for connection in handles:
            self.assert_closed(connection)

    def test_session_closes_after_success_and_rollback(self):
        with self.db.session() as connection:
            connection.execute("SELECT 1").fetchone()
        self.assert_closed(connection)
        with self.assertRaises(RuntimeError):
            with self.db.session() as connection:
                raise RuntimeError("Interruption simulée")
        self.assert_closed(connection)
