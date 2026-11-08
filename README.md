# Commandes CAHPP Horizon

**Version bêta 2.0.0b5 — branche `feature/horizon-ui`.**
Application indépendante de préparation et de suivi des commandes fournisseurs.
Après validation du PDF, une fenêtre propose l'envoi au fournisseur et sa
confirmation sans quitter la commande. Les fiches fournisseurs sont regroupées
dans **Paramètres → Fournisseurs**.
Le menu **Commandes** regroupe la préparation, le suivi et les recommandations.
L'onglet **Paramètres → À propos** présente l'auteur Damien Macq et les crédits.

- [Lancement, fonctions et limites d'Horizon](docs/horizon.md)
- Windows : `horizon_windows.bat` pour lancer les sources ;
  `horizon_windows.bat build` pour fabriquer le dossier portable.
- Linux x86_64 : **AppImage** autonome, sans installation de Python ;
  `bash build_horizon_linux.sh` pour le construire depuis les sources.
- [Builds Windows/Linux et contrôles automatiques](https://github.com/omg59/commandes-cahpp/actions/workflows/horizon.yml) :
  ouvrir le dernier run réussi de la branche `feature/horizon-ui`, puis choisir
  **Artifacts** → **CommandesCAHPP-Horizon-Linux-x86_64**, **CommandesCAHPP-Horizon-Windows**
  ou **CommandesCAHPP-Horizon-Installer-Windows**. Il faut être connecté à GitHub
  pour télécharger ces artefacts.

Au premier lancement, choisissez **Créer une base vide**, **Importer une base
CAHPP 1.6…** ou un profil existant. Horizon conserve ce choix et rouvre le même
profil aux lancements suivants. **Paramètres → Changer de profil…** permet d'en
ouvrir un autre. Les bases, réglages, commandes et documents des anciens profils
sont conservés. Une importation crée une copie autonome et ne modifie pas la
base source ; le partage se réactive dans les paramètres du nouveau profil.

![Horizon bêta : préparation d'une commande, avec données fictives](docs/images/horizon-apercu.png)

## Documentation

- [Guide Horizon : installation, profils et fonctionnalités](docs/horizon.md)
- [Mode collaboratif](docs/collaboration.md)
- [Validation avant déploiement](docs/validation.md)
- [Développement et compilation](docs/developpement.md)
- [Historique des versions](CHANGELOG.md)

## Organisation du dépôt

Cette branche contient l'application Horizon Qt/PySide6, lancée par
`main_horizon.py`. Ses écrans sont dans `cahpp_app/horizon/`.
Le reste de `cahpp_app/` contient le moteur métier utilisé par Horizon : base
SQLite, imports CAHPP, recherche, synchronisation, PDF, exports et diagnostics.
Les tests de ce moteur sont conservés, y compris ceux des migrations anciennes.

L'ancienne interface Tkinter et ses scripts de compilation ont été retirés de
cette branche. La version 1.6.0 reste disponible dans l'historique Git et sur
la [branche principale](https://github.com/omg59/commandes-cahpp/tree/main).
L'import d'une base 1.6 reste accessible dans Horizon.
