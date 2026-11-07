"""Valider les vrais livrables Linux, sans dépendre d'une installation Python."""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from pathlib import Path

from cahpp_app.horizon import VERSION
from tools.build_horizon_linux import APP_NAME, ARCH, ROOT, digest


def verify(output: Path, platform="offscreen"):
    manifest = json.loads((output / f"{APP_NAME}-{VERSION}-{ARCH}.json").read_text())
    for item in manifest["artifacts"]:
        path = output / item["name"]
        if digest(path) != item["sha256"]:
            raise ValueError("Empreinte incorrecte : " + path.name)
    appimage = output / f"{APP_NAME}-{VERSION}-{ARCH}.AppImage"
    with appimage.open("rb") as stream:
        stream.seek(8)
        if stream.read(3) != b"AI\x02":
            raise ValueError("Le livrable n'est pas un AppImage de type 2.")
    portable = output / f"{APP_NAME}-{VERSION}-{ARCH}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="horizon-linux-validation-") as folder:
        root = Path(folder)
        unpacked = root / "dossier avec espaces"
        unpacked.mkdir()
        with tarfile.open(portable) as archive:
            archive.extractall(unpacked, filter="data")
        launcher = unpacked / f"{APP_NAME}-{VERSION}-{ARCH}/AppRun"
        image_copy = root / "Horizon avec espaces.AppImage"
        shutil.copy2(appimage, image_copy)
        image_copy.chmod(0o755)
        profile = root / "profil conservé"
        env = dict(
            os.environ,
            QT_QPA_PLATFORM=platform,
            QT_DEBUG_PLUGINS="1",
            APPIMAGE_EXTRACT_AND_RUN="1",
            PYTHONHOME="/python-non-installe",
            PYTHONPATH="/aucun-module-externe",
            CAHPP_HORIZON_ROOT=str(root / "profils"),
        )

        def smoke(command, target_profile):
            run = subprocess.run(
                command, env=env, capture_output=True, text=True, timeout=60
            )
            if run.returncode:
                raise RuntimeError(
                    "Démarrage Linux en échec :\n" + run.stdout + run.stderr
                )
            report = json.loads((target_profile / "startup-ok.json").read_text())
            if report["version"] != VERSION or not report["qt_translated"]:
                raise ValueError(
                    "Version ou ressources françaises absentes : " + str(report)
                )

        smoke([str(launcher), "--profile", str(profile), "--smoke-test"], profile)
        database = profile / "data/commandes_cahpp.sqlite3"
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES ('linux_package_test','conservé')"
            )
            connection.commit()
        finally:
            connection.close()
        smoke([str(image_copy), "--profile", str(profile), "--smoke-test"], profile)
        connection = sqlite3.connect(database)
        try:
            assert (
                connection.execute(
                    "SELECT value FROM settings WHERE key='linux_package_test'"
                ).fetchone()[0]
                == "conservé"
            )
        finally:
            connection.close()
        # L'AppImage accepte aussi la reprise d'une base et produit un profil
        # autonome, sans dépendre de l'emplacement de l'archive portable.
        result = subprocess.run(
            [str(image_copy), "--copy-database", str(database), "--smoke-test"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            raise RuntimeError(
                "Reprise de base depuis l'AppImage en échec :\n"
                + result.stdout
                + result.stderr
            )
        markers = list((root / "profils/profils").glob("copie-*/startup-ok.json"))
        if len(markers) != 1:
            raise ValueError("Le profil copié n'a pas été validé.")
        print(
            "Linux validé : archive portable, AppImage, français, conservation et copie du profil."
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist-linux")
    parser.add_argument(
        "--platform", default="offscreen", choices=["offscreen", "xcb", "wayland"]
    )
    args = parser.parse_args()
    verify(args.output_dir.resolve(), args.platform)


if __name__ == "__main__":
    main()
