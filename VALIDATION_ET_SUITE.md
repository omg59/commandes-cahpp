# Validation et prochaines étapes

## Contrôles automatiques

Installer les dépendances de test : `python -m pip install -r requirements-dev.txt`.
Lancer `python -m ruff check .` puis `python -m unittest discover -s tests -v`.

Le test graphique s'exécute dans un processus isolé avec une base temporaire.
Sous Linux sans écran, utiliser `xvfb-run -a python -m unittest discover -s tests -v`.
La variable `CAHPP_REQUIRE_GUI=1` interdit de passer silencieusement ce test
en l'absence d'écran. Elle est activée dans GitHub Actions.

Le workflow `.github/workflows/validation.yml` exécute ces contrôles à chaque
push et pull request, sur Python 3.12 sous Windows et Linux. Il vérifie aussi
que PyInstaller peut produire l'application Windows. Il ne fabrique pas encore
l'installateur Inno Setup et ne publie pas automatiquement de release.
Ruff cible les erreurs certaines ; ce n'est pas un contrôle de style exhaustif.

## Limites des tests actuels

Les pannes réseau sont simulées : elles ne remplacent pas un essai sur le
partage SMB réel. Le test graphique couvre les neuf pages et une recherche,
pas encore tous les dialogues ni tous les parcours utilisateur.
La construction PyInstaller n'est pas un test du lancement de l'EXE installé.

## Suite proposée

1. Ajouter des tests graphiques des fiches fournisseur et article avec
   saisie, enregistrement, fermeture et réouverture.
2. Extraire progressivement les composants communs puis un onglet de `ui.py`,
   avec contrôles à chaque déplacement ; conserver l'API `cahpp_app.ui.App`.
3. Séparer progressivement les domaines de persistance sans modifier le schéma.
4. Auditer les montants, leur stockage et leurs arrondis dans un chantier dédié.

La version 1.4.2 prépare ce découpage ; elle ne prétend pas l'avoir réalisé.
