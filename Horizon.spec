# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
from importlib.metadata import distribution
from packaging.requirements import Requirement
from PySide6.QtCore import QLibraryInfo
import PySide6

datas=collect_data_files("reportlab")
datas += collect_data_files("certifi")
# Livrer les notices des dépendances réellement installées pour cette plateforme.
pending = ["openpyxl", "reportlab", "Pillow", "PySide6-Essentials", "certifi", "keyring"]
seen = set()
while pending:
    package = pending.pop()
    dist = distribution(package)
    name = dist.metadata["Name"]
    if name.casefold() in seen:
        continue
    seen.add(name.casefold())
    datas += copy_metadata(name)
    for dependency in dist.requires or []:
        requirement = Requirement(dependency)
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            pending.append(requirement.name)

datas += [("ressources/horizon", "ressources/horizon"),
          ("assets/app_icon.png", "assets"),
          ("assets/app_icon.ico", "assets"),
          ("ressources/DejaVuSans.ttf", "ressources"),
          ("ressources/DejaVuSans-Bold.ttf", "ressources"),
          ("ressources/DEJAVU-LICENSE.txt", "ressources"),
          ("docs/horizon.md", "documentation")]
translations=Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
relative_translations=translations.relative_to(Path(PySide6.__file__).parent)
datas += [(str(translations/"qtbase_fr.qm"), "PySide6/"+relative_translations.as_posix())]

a=Analysis(["main_horizon.py"],pathex=[],binaries=[],datas=datas,
           hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],
           excludes=["tkinter","_tkinter","PySide6.QtQuick","PySide6.QtQml","PySide6.QtWebEngineCore","PySide6.QtWebEngineWidgets"],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name="CommandesCAHPP-Horizon",
        debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
        console=False,disable_windowed_traceback=False,icon="assets/app_icon.ico")
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name="CommandesCAHPP-Horizon-portable")
