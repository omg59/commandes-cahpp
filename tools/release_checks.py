"""Contrôle les versions et produit une empreinte de l'installateur compilé."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path


def check_versions(root: Path) -> str:
    tree = ast.parse((root / "cahpp_app/__init__.py").read_text(encoding="utf-8"))
    version = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets)
    )
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Le numéro de version doit utiliser le format X.Y.Z.")
    installer = (root / "CommandesCAHPP.iss").read_text(encoding="utf-8")
    for expected in (
        f'#define MyAppVersion "{version}"',
        f"VersionInfoVersion={version}.0",
        f"VersionInfoProductVersion={version}",
    ):
        if expected not in installer.splitlines():
            raise ValueError(
                f"Version incohérente dans CommandesCAHPP.iss : {expected}"
            )
    if (
        f"CommandesCAHPP-Setup-{version}.exe"
        not in (root / "build_installer_windows.bat").read_text()
    ):
        raise ValueError(
            "Le script d'installation affiche un ancien numéro de version."
        )
    return version


def installer_manifest(root: Path) -> dict[str, object]:
    version = check_versions(root)
    executable = root / "dist-installer" / f"CommandesCAHPP-Setup-{version}.exe"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    digest = hashlib.sha256()
    with executable.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "version": version,
        "file": executable.name,
        "size_bytes": executable.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = check_versions(root)
    if args.manifest:
        manifest = installer_manifest(root)
        output = root / "dist-installer" / f"CommandesCAHPP-{version}-manifest.json"
        output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        checksum = output.with_suffix(".sha256")
        checksum.write_text(
            f"{manifest['sha256']}  {manifest['file']}\n", encoding="ascii"
        )
        print(output)
    else:
        print(f"Versions cohérentes : {version}")


if __name__ == "__main__":
    main()
