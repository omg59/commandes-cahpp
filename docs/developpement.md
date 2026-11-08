# Développement Horizon

La branche `feature/horizon-ui` contient l'interface Qt et le moteur métier.
La version stable historique reste sur `main`.

## Organisation

- `main_horizon.py` : sélection du profil puis démarrage.
- `cahpp_app/horizon/` : écrans Qt, formulaires et services Horizon.
- `cahpp_app/` : base, import, recherche, synchronisation et exports communs.
- `tests/` : tests métier et parcours Qt, avec données temporaires.
- `Horizon.spec`, `Horizon.iss` : portable Windows et installateur.
- `tools/build_horizon_linux.py` : portable Linux et AppImage.

## Environnement et contrôles

Utiliser Python 3.15 64 bits et un environnement virtuel :

```bash
python -m venv .venv-horizon-py315
# Activer cet environnement selon le système, puis :
python -m pip install -r requirements-horizon.txt -r requirements-dev.txt
python -m ruff check .
python tools/release_checks.py
python -m unittest discover -s tests -v
python main_horizon.py
```

Les tests Qt utilisent des profils temporaires et le rendu hors écran. En CI,
`CAHPP_REQUIRE_HORIZON_GUI=1` impose la présence de PySide6. Les tests des paquets
Linux utilisent aussi Xvfb et le véritable plugin X11.

## Compilation

Sous Windows, `horizon_windows.bat build` lance les contrôles et PyInstaller.
`build_horizon_installer.bat` produit ensuite l'installateur avec Inno Setup.
Sous Linux x86_64, `bash build_horizon_linux.sh` produit l'AppImage et l'archive
portable. Les commandes et prérequis sont détaillés dans [le guide](horizon.md).

La version publique est définie dans `cahpp_app/horizon/__init__.py` et
`Horizon.iss`. Le contrôle `tools/release_checks.py` vérifie leur cohérence.
Son option `--manifest` produit l'empreinte SHA-256 de l'installateur Windows.
Le numéro du moteur dans `cahpp_app/__init__.py` reste distinct de celui d'Horizon.

Le workflow `.github/workflows/horizon.yml` valide Linux et Windows, construit
les paquets puis vérifie leur démarrage, les profils et l'installation Windows.
Les artefacts sont conservés 30 jours. Une release stable nécessite également
les essais utilisateurs et réseau décrits dans [la validation](validation.md).
