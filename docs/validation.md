# Validation de Commandes CAHPP Horizon

Les cases sont à remplir pour chaque déploiement. Leur présence ne signifie pas
que les essais manuels ont été réalisés.

## Contrôles automatiques

Installer `requirements-horizon.txt` et `requirements-dev.txt`, puis lancer :

```bash
python -m ruff check .
python tools/release_checks.py
python -m unittest discover -s tests -v
```

La suite conserve les tests du moteur : imports mensuels, migrations SQLite,
recherche FTS5, calculs, documents, PDF, statistiques, sauvegardes, diagnostics,
réceptions et synchronisation. Les tests graphiques portent sur Horizon Qt :
premier lancement, profils, catalogue, panier, quantité entière, annulation,
PDF, fenêtre d'envoi, réouverture, réglages et suivi des commandes.

Le workflow `.github/workflows/horizon.yml` exécute les tests sous Linux et
Windows. Il fabrique puis lance le portable Windows, l'AppImage et le portable
Linux. Il vérifie aussi l'installation, la mise à jour et la désinstallation
Windows avec conservation du profil. Les anciens tests graphiques Tkinter
ont été retirés avec l'interface correspondante.

## Essais manuels avant passage en version stable

Utiliser une copie des données pour les essais, puis deux postes et le partage
SMB de l'établissement pour les scénarios collaboratifs.

- [ ] Créer un profil vide, le rouvrir et changer de profil.
- [ ] Importer une base 1.6 ; vérifier fournisseurs, paramètres, commandes,
      documents et conservation de la base source.
- [ ] Installer ou remplacer le programme et retrouver le même profil.
- [ ] Tester le redimensionnement, les thèmes et les onglets sur les postes réels.
- [ ] Chercher un article, renseigner une quantité entière, annuler un ajout,
      modifier le panier, enregistrer et reprendre un brouillon.
- [ ] Vérifier le PDF, ses montants et son nom de fichier en AAAA-MM-JJ.
- [ ] Ouvrir l'e-mail, joindre les fichiers et confirmer l'envoi dans Horizon.
- [ ] Tester les documents, confirmations, réceptions partielles et factures.
- [ ] Importer une évolution mensuelle, vérifier les articles signalés et les
      tarifs historiques ; contrôler la sauvegarde préalable.
- [ ] Tester les exports statistiques et les dates françaises à l'écran.
- [ ] Synchroniser deux postes : catalogue, commandes, documents et réceptions.
- [ ] Tester les modifications concurrentes, verrous, coupures réseau et reprise.
- [ ] Exporter une sauvegarde complète et vérifier sa restauration dans un
      profil de test, avec tous les documents.
- [ ] Exporter le diagnostic et vérifier l'accès aux journaux.

Les tests automatisés ne remplacent pas les essais du partage SMB réel, de la
messagerie choisie et de la restauration des données de l'établissement.
