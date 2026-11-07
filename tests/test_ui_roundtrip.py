from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class InterfaceRoundtripTest(unittest.TestCase):
    def test_forms_orders_and_reopening_in_isolated_application(self):
        self.run_scenario("tests.gui_roundtrip")

    def test_manual_index_repair_in_background(self):
        self.run_scenario("tests.gui_index_repair")

    def test_monthly_import_review_and_order(self):
        self.run_scenario("tests.gui_monthly_import")

    def run_scenario(self, module):
        if (
            sys.platform != "win32"
            and not os.environ.get("DISPLAY")
            and os.environ.get("CAHPP_REQUIRE_GUI") != "1"
        ):
            self.skipTest("Pas d'écran : utiliser xvfb-run.")
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, CAHPP_PORTABLE_ROOT=directory)
            result = subprocess.run(
                [sys.executable, "-m", module],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
                timeout=40,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
