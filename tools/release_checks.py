"""Contrôle les versions et produit une empreinte de l'installateur compilé."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path


def check_versions(root: Path) -> str:
    tree = ast.parse((root / "cahpp_app/horizon/__init__.py").read_text(encoding="utf-8"))
    version = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in n.targets)
    )
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version):
        raise ValueError("Le numéro de version doit utiliser le format X.Y.Z, éventuellement suivi de aN, bN ou rcN.")
    installer = (root / "Horizon.iss").read_text(encoding="utf-8")
    for expected in (
        f'#define MyAppVersion "{version}"',
    ):
        if expected not in installer.splitlines():
            raise ValueError(
                f"Version incohérente dans Horizon.iss : {expected}"
            )
    numeric = re.search(r"^VersionInfoVersion=(\d+\.\d+\.\d+\.\d+)$", installer, re.MULTILINE)
    if not numeric or numeric.group(1).rsplit(".", 1)[0] != re.split(r"a|b|rc", version)[0]:
        raise ValueError("Version numérique incohérente dans Horizon.iss")
    if "OutputBaseFilename=CommandesCAHPP-Horizon-Setup-{#MyAppVersion}" not in installer:
        raise ValueError("Nom de l'installateur Horizon incohérent")
    return version


def installer_manifest(root: Path) -> dict[str, object]:
    version = check_versions(root)
    executable = root / "dist-installer-horizon" / f"CommandesCAHPP-Horizon-Setup-{version}.exe"
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
        output = root / "dist-installer-horizon" / f"CommandesCAHPP-Horizon-{version}-manifest.json"
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
