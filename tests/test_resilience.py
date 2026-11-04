from __future__ import annotations

import logging
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cahpp_app import app_logging
from cahpp_app.collaboration import (
    CollaborationError, CollaborationManager, _atomic_json, _read_json,
)
from cahpp_app.database import Database
from cahpp_app.diagnostics import build_diagnostic_report


class ResilienceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "local.sqlite3")
        with self.db.session() as connection:
            self.supplier = connection.execute(
                "INSERT INTO suppliers(name) VALUES ('FICTIF')"
            ).lastrowid
        self.order_id = self.db.save_order(self.supplier, [
            {"designation": "TEST", "cartons": 1, "units_per_carton": 1,
             "unit_price": 1, "vat": 20},
        ])
        self.manager = CollaborationManager(self.db, "test", "Test", self.root / "shared")
        self.manager.initialize_workspace()

    def test_failed_atomic_replace_preserves_original_and_cleans_temp(self):
        target = self.root / "record.json"
        _atomic_json(target, {"revision": 1})
        with patch("cahpp_app.collaboration.os.replace", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                _atomic_json(target, {"revision": 2})
        self.assertEqual(_read_json(target), {"revision": 1})
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_publication_failure_keeps_local_order_pending_then_retries(self):
        original_replace = os.replace

        def fail_current(source, target):
            if Path(target).name == "commande.json":
                raise OSError("offline")
            return original_replace(source, target)

        before, lines = self.db.get_order(self.order_id)
        with patch("cahpp_app.collaboration.os.replace", side_effect=fail_current):
            with self.assertRaises(OSError):
                self.manager.publish_order(self.order_id)
        after, remaining = self.db.get_order(self.order_id)
        self.assertEqual(dict(before), dict(after))
        self.assertEqual(len(lines), len(remaining))
        self.assertIn(self.order_id, self.db.pending_order_ids())
        self.assertEqual(list((self.root / "shared").rglob("*.tmp")), [])
        self.manager.sync_orders()
        self.assertNotIn(self.order_id, self.db.pending_order_ids())

    def test_corrupt_shared_json_does_not_overwrite_local_order(self):
        self.manager.publish_order(self.order_id)
        target = next(self.manager.orders_dir.glob("*/commande.json"))
        target.write_text('{"order":', encoding="utf-8")
        before, lines = self.db.get_order(self.order_id)
        with self.assertRaises(CollaborationError):
            self.manager.sync_orders()
        after, remaining = self.db.get_order(self.order_id)
        self.assertEqual(dict(before), dict(after))
        self.assertEqual(len(lines), len(remaining))

    def test_logging_rotates_and_does_not_export_exception_payload(self):
        previous = app_logging.logging_snapshot()
        path = app_logging.configure_logging(self.root / "logs")
        self.addCleanup(app_logging.configure_logging,
                        Path(previous["path"]).parent if previous["path"]
                        else app_logging.LOG_DIR)
        logger = logging.getLogger("cahpp_app.tests")
        try:
            raise ValueError("secret-commandes@example.test prix=123.45")
        except ValueError as exc:
            app_logging.log_failure(logger, "test_echec", exc)
        report = build_diagnostic_report(self.db, None, "test")
        self.assertIn("JOURNAL TECHNIQUE", report)
        self.assertIn("ValueError", report)
        self.assertNotIn("secret-commandes", report)
        self.assertNotIn("123.45", report)
        handler = logging.getLogger("cahpp_app").handlers[0]
        handler.maxBytes = 200
        for _ in range(30):
            logger.info("evenement_technique")
        self.assertTrue(path.with_name(path.name + ".1").exists())
        self.assertLessEqual(len(list(path.parent.glob("*.log*"))), 4)

    def test_lost_lock_is_not_reused_for_publication(self):
        order, _ = self.db.get_order(self.order_id)
        lock = self.manager.acquire_lock("commande", str(order["shared_uid"]))
        with patch.object(lock, "refresh", side_effect=OSError("offline")):
            self.manager.refresh_active_locks()
        self.assertTrue(lock.released)
        self.assertNotIn(lock.resource, self.manager._active_locks)

    def test_unwritable_log_directory_does_not_prevent_use(self):
        with patch("cahpp_app.app_logging.RotatingFileHandler",
                   side_effect=PermissionError("secret")):
            self.assertIsNone(app_logging.configure_logging(self.root / "logs"))
        self.addCleanup(app_logging.configure_logging, app_logging.LOG_DIR)
        self.assertEqual(app_logging.logging_snapshot()["error"], "PermissionError")
        self.assertIsNotNone(self.db.get_order(self.order_id)[0])

    def test_unhandled_worker_error_is_recorded_without_its_payload(self):
        previous_sys = sys.excepthook
        previous_thread = threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", previous_sys)
        self.addCleanup(setattr, threading, "excepthook", previous_thread)
        app_logging.configure_logging(self.root / "logs")
        self.addCleanup(app_logging.configure_logging, app_logging.LOG_DIR)
        app_logging.install_exception_hooks()

        def fail():
            raise RuntimeError("confidentiel@example.test")

        worker = threading.Thread(target=fail)
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        journal = "".join(app_logging.logging_snapshot()["recent"])
        self.assertIn("worker_exception", journal)
        self.assertIn("RuntimeError", journal)
        self.assertNotIn("confidentiel@", journal)
