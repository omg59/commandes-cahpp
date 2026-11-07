"""Build Linux autonome : PyInstaller → AppDir → AppImage et tar.gz.

Les outils AppImage sont téléchargés depuis leurs versions officielles figées,
vérifiés puis exécutés après extraction : aucune dépendance FUSE du constructeur.
La CI construit sous Ubuntu 22.04 pour ne pas imposer la glibc d'un Linux récent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from cahpp_app.horizon import VERSION

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "CommandesCAHPP-Horizon"
ICON_NAME = "commandes-cahpp-horizon"
ARCH = "x86_64"
APPIMAGETOOL = {
    "name": "appimagetool-1.9.1-x86_64.AppImage",
    "url": "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage",
    "sha256": "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
}
RUNTIME = {
    "name": "runtime-20251108-x86_64",
    "url": "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
    "sha256": "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d",
}

APPRUN = """#!/bin/sh
set -eu
CAHPP_APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Qt doit charger les plugins livrés avec Horizon, pas ceux du bureau hôte.
unset QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH QML2_IMPORT_PATH
exec "$CAHPP_APPDIR/usr/lib/CommandesCAHPP-Horizon/CommandesCAHPP-Horizon" "$@"
"""


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def run(args, **kwargs):
    print("+ " + " ".join(map(str, args)), flush=True)
    subprocess.run([str(value) for value in args], check=True, **kwargs)


def download_pinned(spec: dict, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / spec["name"]
    if destination.is_file() and digest(destination) == spec["sha256"]:
        return destination
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        request = Request(
            spec["url"], headers={"User-Agent": "CommandesCAHPP-Horizon-build"}
        )
        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        if digest(temporary) != spec["sha256"]:
            raise ValueError(
                "L'empreinte de l'outil téléchargé ne correspond pas : " + spec["name"]
            )
        temporary.replace(destination)
        destination.chmod(0o755)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def create_appdir(bundle: Path, destination: Path, *, version=VERSION) -> Path:
    executable = bundle / APP_NAME
    if not executable.is_file() or not (bundle / "_internal").is_dir():
        raise ValueError("Dossier PyInstaller Linux incomplet : " + str(bundle))
    if destination.is_symlink():
        raise ValueError("Le dossier AppDir ne doit pas être un lien symbolique.")
    if destination.exists():
        shutil.rmtree(destination)
    payload = destination / "usr/lib" / APP_NAME
    shutil.copytree(bundle, payload, symlinks=True)
    (payload / APP_NAME).chmod(0o755)
    entry = destination / "AppRun"
    entry.write_text(APPRUN, encoding="utf-8")
    entry.chmod(0o755)
    binary = destination / "usr/bin" / APP_NAME
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.symlink_to("../lib/" + APP_NAME + "/" + APP_NAME)
    applications = destination / "usr/share/applications"
    applications.mkdir(parents=True, exist_ok=True)
    desktop = applications / (ICON_NAME + ".desktop")
    desktop.write_text(
        "[Desktop Entry]\nType=Application\nName=Commandes CAHPP Horizon\n"
        "Comment=Catalogue et commandes fournisseurs CAHPP\n"
        f"Exec={APP_NAME}\nIcon={ICON_NAME}\nTerminal=false\n"
        f"Categories=Office;\nStartupNotify=true\nX-AppImage-Version={version}\n"
        f"X-AppImage-Arch={ARCH}\n",
        encoding="utf-8",
    )
    (destination / desktop.name).symlink_to(desktop.relative_to(destination))
    # Les tailles d'icône sont produites pour l'intégration bureau uniquement.
    from PIL import Image

    icon_dir = destination / "usr/share/icons/hicolor/256x256/apps"
    icon_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(ROOT / "assets/app_icon.png") as image:
        image.convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS).save(
            icon_dir / (ICON_NAME + ".png")
        )
    (destination / (ICON_NAME + ".png")).symlink_to(
        (icon_dir / (ICON_NAME + ".png")).relative_to(destination)
    )
    (destination / ".DirIcon").symlink_to(ICON_NAME + ".png")
    for path in destination.rglob("*"):
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Lien sortant de l'AppDir : " + str(path))
    return destination


def archive_portable(appdir: Path, destination: Path, *, version=VERSION):
    with tarfile.open(destination, "w:gz", dereference=False) as archive:
        archive.add(appdir, arcname=f"{APP_NAME}-{version}-{ARCH}")


def verify_graphics_dependencies(bundle: Path):
    plugin = bundle / "_internal/PySide6/Qt/plugins/platforms/libqxcb.so"
    if not plugin.is_file():
        raise ValueError("Le plugin graphique X11 de Qt est absent du dossier compilé.")
    environment = dict(os.environ)
    environment["LD_LIBRARY_PATH"] = (
        str(bundle / "_internal") + os.pathsep + environment.get("LD_LIBRARY_PATH", "")
    )
    result = subprocess.run(
        ["ldd", str(plugin)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    missing = sorted(
        set(re.findall(r"(\S+)\s+=>\s+not found", result.stdout + result.stderr))
    )
    if result.returncode or missing:
        raise ValueError(
            "Dépendances graphiques Linux manquantes : "
            + (", ".join(missing) or result.stderr.strip())
        )
    for library in ("libxcb-cursor.so.0", "libxcb-shape.so.0"):
        if not (bundle / "_internal" / library).is_file():
            raise ValueError(
                "Bibliothèque Qt/X11 non embarquée : "
                + library
                + ". Installez ses dépendances sur le système de compilation et reconstruisez."
            )


def build(*, output: Path, cache: Path, skip_tests=False, reuse_bundle=False):
    if sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise ValueError("Ce constructeur prend en charge Linux x86_64 uniquement.")
    output.mkdir(parents=True, exist_ok=True)
    if not skip_tests:
        run([sys.executable, "-m", "ruff", "check", "."], cwd=ROOT)
        run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=ROOT,
        )
    if not reuse_bundle:
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "Horizon.spec",
                "--noconfirm",
                "--clean",
            ],
            cwd=ROOT,
        )
    bundle = ROOT / "dist" / (APP_NAME + "-portable")
    verify_graphics_dependencies(bundle)
    appdir = create_appdir(bundle, ROOT / "build/Horizon.AppDir")
    portable = output / f"{APP_NAME}-{VERSION}-{ARCH}.tar.gz"
    archive_portable(appdir, portable)
    tool = download_pinned(APPIMAGETOOL, cache)
    runtime = download_pinned(RUNTIME, cache)
    tool_work = ROOT / "build" / ("appimagetool-" + APPIMAGETOOL["sha256"][:12])
    tool_work.mkdir(parents=True, exist_ok=True)
    extracted = tool_work / "squashfs-root/AppRun"
    if not extracted.is_file():
        tool.chmod(0o755)
        run([tool, "--appimage-extract"], cwd=tool_work, stdout=subprocess.DEVNULL)
    appimage = output / f"{APP_NAME}-{VERSION}-{ARCH}.AppImage"
    env = dict(os.environ, ARCH=ARCH, VERSION=VERSION)
    run(
        [
            extracted,
            "--no-appstream",
            "--runtime-file",
            runtime,
            "--comp",
            "zstd",
            "--mksquashfs-opt=-processors",
            "--mksquashfs-opt=2",
            appdir,
            appimage,
        ],
        env=env,
    )
    appimage.chmod(0o755)
    artifacts = [appimage, portable]
    manifest = {
        "application": APP_NAME,
        "version": VERSION,
        "architecture": ARCH,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "build_system": platform.platform(),
        "build_glibc": platform.libc_ver()[1],
        "appimagetool": APPIMAGETOOL,
        "runtime": RUNTIME,
        "artifacts": [
            {"name": p.name, "sha256": digest(p), "size_bytes": p.stat().st_size}
            for p in artifacts
        ],
    }
    (output / f"{APP_NAME}-{VERSION}-{ARCH}.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest(p)}  {p.name}\n" for p in artifacts), encoding="utf-8"
    )
    print("AppImage : " + str(appimage))
    print("Portable : " + str(portable))
    return appimage, portable


def main():
    parser = argparse.ArgumentParser(description="Construire Horizon pour Linux x86_64")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist-linux")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache-horizon-build")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Pour CI après une validation déjà réussie",
    )
    parser.add_argument(
        "--reuse-bundle",
        action="store_true",
        help="Réutiliser un dossier PyInstaller Linux déjà construit",
    )
    args = parser.parse_args()
    try:
        build(
            output=args.output_dir.resolve(),
            cache=args.cache_dir.resolve(),
            skip_tests=args.skip_tests,
            reuse_bundle=args.reuse_bundle,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("Construction Linux impossible : " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
