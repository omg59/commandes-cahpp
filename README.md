> **Branche de développement.** Correctifs de stabilisation en cours de validation.
> La [version officielle](https://github.com/omg59/horizon-pc/releases/latest) reste diffusée depuis `main`.
Lot de développement **3.0.1a10**. [Association des téléphones](docs/acces-mobiles.md) · [Corrections des audits et migration](docs/audit-consolidation.md) · [Montants et schéma 17](docs/montants.md).

# Horizon — Commandes CAHPP

**Windows et Linux · Version 3.0.0**

Horizon permet pour simplifier les commandes fournisseurs : rechercher dans
le catalogue CAHPP, préparer un bon de commande, puis suivre les livraisons.
Je peux travailler sur un seul poste ou avec mes collègues via un dossier partagé.

## Télécharger

| Système | Téléchargement |
| --- | --- |
| **Windows 64 bits** | [Installateur EXE](https://github.com/omg59/horizon-pc/releases/download/v3.0.0/CommandesCAHPP-Horizon-Setup-3.0.0.exe) · [ZIP portable](https://github.com/omg59/horizon-pc/releases/download/v3.0.0/CommandesCAHPP-Horizon-3.0.0-Windows-portable.zip) |
| **Linux x86_64** | [AppImage](https://github.com/omg59/horizon-pc/releases/download/v3.0.0/CommandesCAHPP-Horizon-3.0.0-x86_64.AppImage) · [Archive portable](https://github.com/omg59/horizon-pc/releases/download/v3.0.0/CommandesCAHPP-Horizon-3.0.0-x86_64.tar.gz) |

Python est inclus. Sous Linux, rendre l’AppImage exécutable avant de la lancer.
[Notes de version et empreintes SHA-256](https://github.com/omg59/horizon-pc/releases/tag/v3.0.0) · [Installation et reprise des données](docs/horizon.md)

## Au quotidien

- Catalogue, favoris, fournisseurs et évolutions tarifaires CAHPP.
- Commandes, brouillons, bons PDF et préparation de l’e-mail au fournisseur.
- Réceptions partielles, documents, historique et statistiques.
- Sauvegardes, diagnostics et synchronisation entre postes.

![Horizon 3.0.0 — préparation d’une commande avec des données fictives](docs/images/horizon-apercu.png)

Sur Android, je peux consulter le catalogue, préparer des commandes et pointer
les réceptions, avec ou sans photo du bon de livraison. Cette extension utilise
[Horizon Mobile](https://github.com/omg59/horizon-mobile) et un
[relais auto-hébergé](https://github.com/omg59/horizon-server), facultatifs pour le PC.

[Guide utilisateur](docs/horizon.md) · [Collaboration](docs/collaboration.md) ·
[Android et relais](docs/android.md) · [Changelog](CHANGELOG.md) · [Documentation technique](docs/developpement.md)

La version historique 1.6 est conservée dans la [branche legacy](https://github.com/omg59/horizon-pc/tree/legacy).
Le développement se poursuit dans `horizon-pc-dev`.
