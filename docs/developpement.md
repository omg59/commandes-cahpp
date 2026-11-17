# Développement Horizon

La version officielle est dans **[horizon-pc](https://github.com/omg59/horizon-pc), branche `main`**.
La branche `legacy` conserve la version 1.6. Le développement se fait désormais
dans `dev`, à partir de la version officielle courante. L’ancien dépôt privé
`horizon-pc-dev` reste conservé pour son historique. Les historiques RC2 et 2.1.0a10 sont réunis par fusion,
sans réécrire leurs commits ni les tags déjà publiés.

## Organisation

- `main_horizon.py` : sélection du profil puis démarrage.
- `cahpp_app/horizon/` : écrans Qt, formulaires et services Horizon.
- `cahpp_app/` : base, import, recherche, synchronisation et exports communs.
- `tests/` : tests métier et parcours Qt, avec données temporaires.
- `Horizon.spec`, `Horizon.iss` : portable Windows et installateur.
- `tools/build_horizon_linux.py` : portable Linux et AppImage.

L'ancienne interface Tkinter et ses scripts de compilation ont été retirés de
cette branche. Le moteur conserve les migrations des bases 1.6 et leurs tests.
La version historique reste consultable sur la
[branche legacy](https://github.com/omg59/horizon-pc/tree/legacy) et dans
l'historique Git.

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

## Publier une version validée

Après validation utilisateur, renseigner `.github/releases/horizon.json` avec
la version, le commit exact, l’identifiant du workflow réussi et les trois
artefacts approuvés (identifiants et empreintes GitHub). Rédiger le changelog
dans `docs/releases/<version>.md`, puis pousser la demande activée (`enabled: true`) sur `main` du dépôt officiel.

Le workflow `horizon-release.yml` vérifie le build, récupère les artefacts sans
recompilation, prépare les fichiers et leurs SHA-256, puis publie la release
après contrôle des pièces jointes. Le tag vise le commit réellement compilé.
Les versions alpha, bêta et RC sont publiées comme préversions. La dernière
version stable reste inchangée lors de la publication d’une préversion. Une
version stable devient la release recommandée (`latest`). Une release déjà publiée n’est jamais remplacée
automatiquement ; un brouillon du même commit peut être repris après un échec.

Le fichier de demande constitue le déclencheur de publication. Pendant la
préparation et la compilation, conserver `enabled: false` : aucun appel de
publication n’est alors effectué. Activer uniquement après validation du build.
Les commits limités à cette demande ne relancent pas la compilation. Les tests automatiques des garde-fous peuvent
être lancés seuls avec `python -m unittest tests.test_horizon_release -v`.


## Dépôts associés et migration GitHub

- `horizon-pc` : ancien `commandes-cahpp`, dépôt public et releases officielles ;
- `horizon-pc-dev` : ancien dépôt privé de développement, conservé comme historique ;
- [horizon-mobile](https://github.com/omg59/horizon-mobile) : application Android ;
- [horizon-server](https://github.com/omg59/horizon-server) : relais auto-hébergé.

Mettre à jour les URL des remotes après le renommage. L’ancienne URL
`omg59/horizon-pc` désigne maintenant le dépôt officiel : un ancien clone de
développement doit donc explicitement viser `omg59/horizon-pc-dev`.
Les versions des composants serveur et mobile ne sont pas alignées artificiellement
sur le numéro 3.0.0 du PC. Leurs tests d’intégration se lancent avec les dépôts voisins.


## Stabilisation après l’audit du 17 novembre 2026

Les trois dépôts utilisent `dev` pour les évolutions. `main` et les tags publiés
restent les références diffusées. Préparer les correctifs PC dans `horizon-pc/dev`,
les tests et changements du relais dans `horizon-server/dev`, et Android dans
`horizon-mobile/dev`.

Les parcours HTTP avec le relais sont obligatoires dans la CI du dépôt privé
`horizon-server`. Cette CI récupère le PC public à un **SHA complet** défini dans
`.github/compatibility/pc.json`, puis exécute les vrais tests de réception et de
brouillons. Le programme de contrôle refuse les sources absentes, une mauvaise
révision, une suite vide ou un test ignoré. Un rapport JSON identifie les deux
commits et les tests exécutés. Aucun accès inter-dépôts privé n’est nécessaire.

Après un changement de protocole ou de traitement mobile sur PC, mettre à jour
le SHA candidat dans ce manifeste du relais : ce commit déclenche les contrôles
du couple exact. Vérifier ce rapport avant une fusion ou une diffusion. Les tests
unitaires et graphiques PC restent exécutés sous Windows et Linux dans leur propre
workflow ; un succès de ce workflow seul ne remplace pas la validation du couple.

Les contrôles périodiques du relais ne deviendront actifs qu’après promotion de
leur workflow sur sa branche par défaut. Pendant le travail dans `dev`, les
contrôles sont déclenchés par les commits de cette branche.
