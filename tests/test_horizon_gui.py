"""Le parcours Qt s'exécute dans un processus et un profil indépendants."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class HorizonGuiTest(unittest.TestCase):
    def test_first_launch_creates_empty_working_profile_and_remembers_it(self):
        self.run_scenario("tests.gui_horizon_startup")

    def test_catalog_cart_review_pdf_and_reopening(self):
        self.run_scenario("tests.gui_horizon")

    def test_complete_workflow_and_debugging(self):
        self.run_scenario("tests.gui_horizon_workflow")

    def test_pdf_to_supplier_without_changing_pages(self):
        self.run_scenario("tests.gui_horizon_dispatch")

    def run_scenario(self, module):
        if importlib.util.find_spec("PySide6") is None:
            if os.environ.get("CAHPP_REQUIRE_HORIZON_GUI") == "1":
                self.fail("PySide6 est requis pour valider Horizon.")
            self.skipTest("Installer requirements-horizon.txt pour tester Qt.")
        with tempfile.TemporaryDirectory() as folder:
            env = dict(
                os.environ,
                QT_QPA_PLATFORM="offscreen",
                CAHPP_HORIZON_ROOT=folder,
                CAHPP_HORIZON_GUI_TEST="1",
            )
            run = subprocess.run(
                [sys.executable, "-m", module],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
                timeout=50,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
