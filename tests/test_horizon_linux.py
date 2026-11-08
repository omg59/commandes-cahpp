"""Contrats du paquet Linux et de l'ouverture indépendante des profils."""

import os
import io
import hashlib
from urllib.error import HTTPError
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cahpp_app.horizon.bootstrap import profile_launch_command
from tools.build_horizon_linux import (
    APP_NAME,
    create_appdir,
    archive_portable,
    digest,
    download_pinned,
    verify_graphics_dependencies,
)


class LinuxPackagingTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    @unittest.skipIf(
        sys.platform == "win32", "Les liens AppDir sont propres au paquet Linux"
    )
    def test_appdir_and_portable_archive_keep_links_resources_and_launcher(self):
        bundle = self.root / "bundle"
        internal = bundle / "_internal"
        internal.mkdir(parents=True)
        (bundle / APP_NAME).write_text("#!/bin/sh\nexit 0\n")
        (internal / "ressource.txt").write_text("ressource")
        (internal / "lien.txt").symlink_to("ressource.txt")
        appdir = create_appdir(bundle, self.root / "Horizon.AppDir")
        self.assertTrue((appdir / "AppRun").stat().st_mode & 0o111)
        self.assertTrue((appdir / ".DirIcon").is_file())
        self.assertTrue((appdir / "usr/bin" / APP_NAME).is_file())
        desktop = appdir / "commandes-cahpp-horizon.desktop"
        self.assertIn("Exec=" + APP_NAME, desktop.read_text())
        self.assertNotIn("python", (appdir / "AppRun").read_text())
        archive = self.root / "portable.tar.gz"
        archive_portable(appdir, archive)
        with tarfile.open(archive) as package:
            links = [member for member in package if member.issym()]
            self.assertTrue(
                any(member.name.endswith("_internal/lien.txt") for member in links)
            )
            self.assertTrue(
                all(not member.linkname.startswith("/") for member in links)
            )

    def test_valid_cached_packaging_tool_is_reused_without_network(self):
        cached = self.root / "tool"
        cached.write_bytes(b"tool fixture")
        with patch("tools.build_horizon_linux.urlopen") as network:
            result = download_pinned(
                {
                    "name": "tool",
                    "sha256": digest(cached),
                    "url": "https://example.invalid",
                },
                self.root,
            )
        network.assert_not_called()
        self.assertEqual(result, cached)

    def test_download_recovers_from_gateway_timeout_using_official_fallback(self):
        payload = b"verified tool"
        spec = {"name": "tool", "url": "https://example.invalid/api",
                "fallback_url": "https://example.invalid/release",
                "sha256": hashlib.sha256(payload).hexdigest()}
        failure = HTTPError(spec["url"], 504, "Gateway Timeout", {}, None)
        with patch("tools.build_horizon_linux.urlopen", side_effect=[failure, io.BytesIO(payload)]) as network, patch("tools.build_horizon_linux.time.sleep"):
            result = download_pinned(spec, self.root)
        self.assertEqual(result.read_bytes(), payload)
        self.assertEqual(network.call_args_list[1].args[0].full_url, spec["fallback_url"])
        self.assertFalse((self.root / "tool.part").exists())

    def test_corrupt_download_is_never_installed_or_retried(self):
        spec = {"name": "tool", "url": "https://example.invalid/api", "sha256": "0" * 64}
        with patch("tools.build_horizon_linux.urlopen", return_value=io.BytesIO(b"corrupt")) as network:
            with self.assertRaisesRegex(ValueError, "empreinte"):
                download_pinned(spec, self.root)
        self.assertEqual(network.call_count, 1)
        self.assertFalse((self.root / "tool").exists())
        self.assertFalse((self.root / "tool.part").exists())

    def test_download_retries_are_bounded_and_name_the_failing_tool(self):
        spec = {"name": "runtime", "url": "https://example.invalid/api", "sha256": "0" * 64}
        failure = HTTPError(spec["url"], 504, "Gateway Timeout", {}, None)
        with patch("tools.build_horizon_linux.urlopen", side_effect=failure) as network, patch("tools.build_horizon_linux.time.sleep"):
            with self.assertRaisesRegex(OSError, "runtime.*504"):
                download_pinned(spec, self.root)
        self.assertEqual(network.call_count, 4)
        self.assertFalse((self.root / "runtime.part").exists())

    def test_missing_x11_library_stops_packaging_with_library_name(self):
        plugin = self.root / "_internal/PySide6/Qt/plugins/platforms/libqxcb.so"
        plugin.parent.mkdir(parents=True)
        plugin.touch()
        with patch("tools.build_horizon_linux.subprocess.run") as ldd:
            ldd.return_value = subprocess.CompletedProcess(
                [], 0, "libxcb-shape.so.0 => not found\n", ""
            )
            with self.assertRaisesRegex(ValueError, r"libxcb-shape\.so\.0"):
                verify_graphics_dependencies(self.root)

    def test_new_appimage_profile_relaunches_outer_file_not_old_mount(self):
        image = self.root / "Horizon.AppImage"
        image.write_bytes(b"fixture")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "platform", "linux"),
            patch.dict(os.environ, {"APPIMAGE": str(image)}),
        ):
            program, arguments = profile_launch_command(
                ["--copy-database", "base avec espaces.sqlite3"]
            )
        self.assertEqual(program, str(image.resolve()))
        self.assertEqual(arguments, ["--copy-database", "base avec espaces.sqlite3"])

    def test_source_profile_relaunch_keeps_python_entry_point(self):
        with patch.object(sys, "frozen", False, create=True):
            program, arguments = profile_launch_command(["--profile", "essai"])
        self.assertEqual(program, sys.executable)
        self.assertTrue(arguments[0].endswith("main_horizon.py"))
        self.assertEqual(arguments[1:], ["--profile", "essai"])
