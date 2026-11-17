"""Concurrence réelle : pause, reprise, renouvellement et publication périmée."""

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from cahpp_app.collaboration import (
    CollaborationError, CollaborationManager, ResourceLockedError,
    _atomic_json, _read_json,
)
from cahpp_app.database import Database
from cahpp_app.file_lock import FileLockBusy, exclusive_file


CHILD = """
import json,sys
from pathlib import Path
from cahpp_app.file_lock import FileLockBusy, exclusive_file
path=Path(sys.argv[1])
try:
    with exclusive_file(path):
        print('owned',flush=True)
        if len(sys.argv)>2: sys.stdin.readline()
except FileLockBusy:
    print('busy',flush=True)
"""


class FencingTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = Database(self.root / "local.sqlite3")
        with self.db.session() as c:
            self.sid = c.execute("INSERT INTO suppliers(name) VALUES ('FICTIF')").lastrowid
        self.oid = self.db.save_order(self.sid, [{"designation": "ESSAI", "cartons": 1,
                    "units_per_carton": 1, "unit_price": 1, "vat": 20}])
        self.a = CollaborationManager(self.db, "a", "A", self.root / "shared")
        self.a.initialize_workspace()
        self.b = CollaborationManager(self.db, "b", "B", self.root / "shared")
        self.b.initialize_workspace()
        self.addCleanup(self.a.release_all_locks)
        self.addCleanup(self.b.release_all_locks)

    def child(self, path):
        result = subprocess.run([sys.executable, "-c", CHILD, str(path)],
                                capture_output=True, text=True, check=True, timeout=15)
        return result.stdout.strip()

    def test_native_exclusion_and_reentrance_across_processes(self):
        path = self.root / "native.guard"
        with exclusive_file(path), exclusive_file(path):
            self.assertEqual(self.child(path), "busy")
        self.assertEqual(self.child(path), "owned")
        # Le fichier reste en place après déverrouillage, même inode.
        self.assertTrue(path.exists())

    def test_crashed_process_releases_native_lock(self):
        path = self.root / "crash.guard"
        process = subprocess.Popen([sys.executable, "-c", CHILD, str(path), "hold"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "owned")
            with self.assertRaises(FileLockBusy):
                with exclusive_file(path):
                    self.fail("Le processus enfant détient le verrou")
        finally:
            process.kill()
            process.communicate(timeout=15)
        with exclusive_file(path):
            pass

    def test_stale_owner_cannot_publish_after_takeover(self):
        uid = self.db.get_order(self.oid)[0]["shared_uid"]
        old = self.a.acquire_lock("commande", uid, ttl_seconds=-1)
        current = self.b.acquire_lock("commande", uid)
        with self.assertRaises(ResourceLockedError):
            self.a.publish_order(self.oid)
        self.assertFalse((self.a._order_dir(uid) / "commande.json").exists())
        old.release()  # Ne supprime jamais le nouveau jeton.
        self.assertEqual(_read_json(current.path)["token"], current.token)
        self.b.publish_order(self.oid)
        self.assertTrue((self.b._order_dir(uid) / "commande.json").exists())

    def test_expiry_and_takeover_cannot_interleave_with_publication(self):
        uid = self.db.get_order(self.oid)[0]["shared_uid"]
        old = self.a.acquire_lock("commande", uid, ttl_seconds=-1)
        original = self.a._copy_order_files

        def paused(*args):
            # Autre processus pendant la fenêtre lecture -> publication.
            self.assertEqual(self.child(old.path.with_suffix(".guard")), "busy")
            self.assertEqual(self.b.cleanup_expired_locks(), 0)
            return original(*args)

        with patch.object(self.a, "_copy_order_files", side_effect=paused):
            self.a.publish_order(self.oid)
        new = self.b.acquire_lock("commande", uid)
        with self.assertRaises(ResourceLockedError):
            old.refresh()
        self.assertEqual(_read_json(new.path)["token"], new.token)

    def test_renewed_lease_is_not_deleted_by_stale_cleanup(self):
        old = self.a.acquire_lock("produit", "P", ttl_seconds=-1)
        old.ttl_seconds = 180
        old.refresh()
        self.assertEqual(self.b.cleanup_expired_locks(), 0)
        with self.assertRaises(ResourceLockedError):
            self.b.acquire_lock("produit", "P")

    def test_clock_skew_cannot_allow_old_owner_to_overwrite(self):
        uid = self.db.get_order(self.oid)[0]["shared_uid"]
        old = self.a.acquire_lock("commande", uid)
        record = _read_json(old.path)
        record["expires_at"] = (datetime.now() - timedelta(days=1)).isoformat()
        _atomic_json(old.path, record)
        self.b.acquire_lock("commande", uid)
        with self.assertRaises(ResourceLockedError):
            self.a.publish_order(self.oid)

    def test_second_process_takes_over_only_after_the_commit_fence_is_released(self):
        uid = self.db.get_order(self.oid)[0]["shared_uid"]
        old = self.a.acquire_lock("commande", uid, ttl_seconds=-1)
        source = """
import sys
from cahpp_app.database import Database
from cahpp_app.collaboration import CollaborationManager, ResourceLockedError
db = Database(sys.argv[1])
manager = CollaborationManager(db, 'child', 'Enfant', sys.argv[2])
manager.initialize_workspace()
try:
    with manager.acquire_lock('commande', sys.argv[3]):
        manager.publish_order(int(sys.argv[4]))
        print('published')
except ResourceLockedError:
    print('busy')
"""

        def attempt():
            return subprocess.run(
                [sys.executable, "-c", source, str(self.db.path), str(self.a.root), uid, str(self.oid)],
                capture_output=True, text=True, check=True, timeout=15,
            ).stdout.strip()

        with old.fenced():
            self.assertEqual(attempt(), "busy")
            old.refresh()  # Renouvellement réentrant, pendant la publication.
        record = _read_json(old.path)
        record["expires_at"] = (datetime.now() - timedelta(seconds=1)).isoformat()
        _atomic_json(old.path, record)
        self.assertEqual(attempt(), "published")
        with self.assertRaises(ResourceLockedError):
            self.a.publish_order(self.oid)

    def test_unsupported_native_lock_fails_closed(self):
        with patch("cahpp_app.file_lock._native_lock", side_effect=OSError("non pris en charge")):
            with self.assertRaises(OSError):
                self.a.acquire_lock("produit", "P")
        self.assertEqual(list((self.a.root / "verrous" / "produit").glob("*.lock")), [])

    def test_explicit_protocol_upgrade_preserves_identity_and_refuses_live_leases(self):
        target = self.a.root / "espace-collaboratif.json"
        original = _read_json(target)
        _atomic_json(target, dict(original, format=1))
        with self.assertRaises(CollaborationError):
            self.a.initialize_workspace()
        path = self.a.root / "verrous" / "commande" / "legacy.lock"
        _atomic_json(path, {"expires_at": (datetime.now() + timedelta(minutes=3)).isoformat()})
        with self.assertRaises(CollaborationError):
            CollaborationManager.upgrade_workspace(self.a.root)
        path.unlink()
        CollaborationManager.upgrade_workspace(self.a.root)
        self.a.initialize_workspace()
        self.assertEqual(_read_json(target)["workspace_id"], original["workspace_id"])
        self.assertEqual(_read_json(target)["format"], 2)
        self.assertEqual(_read_json(target.with_name("espace-collaboratif.format-1.json"))["format"], 1)

    def test_replaced_workspace_stops_existing_writer(self):
        uid = self.db.get_order(self.oid)[0]["shared_uid"]
        self.a.acquire_lock("commande", uid)
        target = self.a.root / "espace-collaboratif.json"
        manifest = _read_json(target)
        _atomic_json(target, dict(manifest, workspace_id="autre"))
        with self.assertRaises(CollaborationError):
            self.a.publish_order(self.oid)


if __name__ == "__main__":
    unittest.main()
