"""Rotation des générations locales sans supprimer un transfert en cours."""
import json
import os
import re
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_horizon_operations as fixtures
from cahpp_app.file_lock import FileLockBusy
from cahpp_app.horizon.mobile_catalog import _cache_guard, catalog_cache


class CacheRetentionTest(unittest.TestCase):
    setUp = fixtures.HorizonOperationsTest.setUp

    def test_only_current_and_previous_generations_are_retained(self):
        for index in range(6):
            self.db.create_manual_product(self.sid, f"CACHE-{index}", "Article", 1, 1, 20)
            active, manifest = catalog_cache(self.db)
            self.assertTrue((active / 'manifest.json').is_file())
        root = active.parent
        generations = [p for p in root.iterdir() if re.fullmatch('[a-f0-9]{64}', p.name)]
        self.assertEqual(len(generations), 2)
        self.assertIn(active, generations)
        self.assertEqual(json.loads((root / 'manifest.json').read_text())['generation'], manifest['generation'])

    def test_transfer_guard_blocks_another_builder_and_keeps_its_files(self):
        active, _ = catalog_cache(self.db)
        with _cache_guard(self.db), ThreadPoolExecutor(1) as pool:
            self.db.create_manual_product(self.sid, 'PENDING', 'Nouveau', 1, 1, 20)
            with self.assertRaises(FileLockBusy):
                pool.submit(catalog_cache, self.db).result()
            self.assertTrue((active / '0.json').is_file())
        self.assertNotEqual(catalog_cache(self.db)[0], active)

    def test_failed_manifest_write_preserves_old_generation_and_removes_temporary_files(self):
        active, _ = catalog_cache(self.db)
        manifest = (active.parent / 'manifest.json').read_bytes()
        self.db.create_manual_product(self.sid, 'CHANGE', 'Nouveau', 1, 1, 20)
        with patch('cahpp_app.horizon.mobile_catalog.os.replace', side_effect=OSError('indisponible')):
            with self.assertRaises(OSError):
                catalog_cache(self.db)
        self.assertEqual((active.parent / 'manifest.json').read_bytes(), manifest)
        self.assertEqual([p for p in active.parent.glob('tmp*.json')], [])
        self.assertNotEqual(catalog_cache(self.db)[0], active)

    def test_only_abandoned_incoming_folders_are_removed(self):
        active, _ = catalog_cache(self.db)
        old, recent = active.parent / 'incoming-old', active.parent / 'incoming-recent'
        old.mkdir(); recent.mkdir()
        os.utime(old, (time.time() - 2 * 86400,) * 2)
        catalog_cache(self.db)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
