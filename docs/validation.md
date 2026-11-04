# Validation de Commandes CAHPP

Ce document est la checklist commune à toutes les versions. Les changements
propres à une version sont décrits dans le [changelog](../CHANGELOG.md).
Les cases ci-dessous sont à remplir lors de chaque validation : leur présence
ne signifie pas que les essais manuels ont déjà été réalisés.

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

## Validation manuelle avant déploiement

Effectuer ces contrôles sur une copie des données, avec deux installations
locales et un même dossier partagé pour les scénarios collaboratifs.

### Installation, affichage et mise à jour

- [ ] Vérifier la version attendue dans l'application et le nom de l'installateur.
- [ ] Installer sans droits administrateur, puis mettre à jour une installation
      existante : base, catalogue, documents, logo et paramètres sont conservés.
- [ ] Vérifier les raccourcis, leur icône et leur dossier de travail.
- [ ] Ouvrir les neuf pages ; vérifier l'ouverture maximisée et le redimensionnement.
- [ ] Ajuster le séparateur du tableau de bord, utiliser les deux ascenseurs et
      contrôler que les boutons et l'état de sauvegarde restent visibles.
- [ ] Déposer un installateur de version supérieure dans `mises-a-jour` :
      vérifier notification, report et lancement avec fermeture de l'application.

### Catalogue et coordonnées

- [ ] Importer un catalogue puis une mise à jour ; vérifier ajouts, retraits,
      variations de prix et conservation des anciennes lignes de commande.
- [ ] Saisir rapidement une recherche, changer de filtre et afficher davantage
      de résultats : seule la dernière recherche est affichée et l'interface répond.
- [ ] Tester le tri dans les deux sens et sa conservation après recherche.
- [ ] Ajouter un favori, modifier sa quantité habituelle, corriger un article,
      rétablir ses valeurs CAHPP ; créer, modifier puis archiver un article local.
- [ ] Enregistrer une fiche fournisseur et un article contenant des points,
      fermer complètement puis rouvrir : coordonnées, références et notes intactes.
- [ ] Contrôler les virgules décimales des montants, le destinataire du mail,
      les notes produit et la référence de remplacement.
- [ ] Dans **Nouvelle commande**, tester saisie, suggestions et liste déroulante
      fournisseur, puis déplacement du focus sans message d'erreur.

### Commandes, PDF et documents

- [ ] Enregistrer, reprendre et modifier un brouillon ; dupliquer une commande.
- [ ] Vérifier la numérotation distincte sur les deux postes et l'auteur des actions.
- [ ] Générer puis ouvrir le PDF, vérifier montants, service destinataire et logo.
- [ ] Vérifier l'absence de mention du franco dans le PDF.
- [ ] Préparer un mail, contrôler les pièces jointes puis marquer la commande envoyée.
- [ ] Supprimer une commande non envoyée, même générée ou avec un mail préparé ;
      vérifier sa disparition sur les deux postes, y compris après redémarrage.
- [ ] Vérifier le refus de suppression d'une commande envoyée ou déjà suivie.
- [ ] Ajouter BL, confirmation, facture et devis ; modifier les types de document,
      y compris un type personnalisé, et le choix **Joint au mail** indépendamment.
- [ ] Vérifier les documents et PDF sur l'autre poste, puis dans son cache hors ligne.

### Suivi, analyses et sauvegarde

- [ ] Confirmer une commande, saisir une date prévue et une note interne.
- [ ] Enregistrer une réception partielle puis totale : BL, quantités et reliquats
      concordent ; modifier/supprimer une réception de test et vérifier le recalcul.
- [ ] Marquer la commande facturée et contrôler filtres, journal et tableau de bord.
- [ ] Tester les alertes de confirmation et de retard avec ouverture de la commande.
- [ ] Vérifier les recommandations, la sélection d'articles à recommander et
      l'avertissement de doublon récent.
- [ ] Enregistrer, appliquer et supprimer un filtre d'historique.
- [ ] Comparer les statistiques HT/TTC et délais, tester une période personnalisée,
      les écarts de prix et l'export Excel multi-feuilles.
- [ ] Archiver des commandes livrées puis les retrouver avec **Inclure les archives**.
- [ ] Créer une sauvegarde complète, contrôler le rappel et tester sa restauration
      dans une installation de test indépendante.

### Collaboration et coupures réseau

- [ ] Les deux bases restent locales ; noms de profil distincts et identifiant
      d'espace commun ; lecture, écriture et renommage atomique indiqués OK.
- [ ] Le second poste reçoit le catalogue publié et les données d'équipe :
      fournisseurs, favoris, quantités, corrections, articles et paramètres communs.
- [ ] Vérifier le délai automatique après redémarrage et la préservation des
      fiches établissement/fournisseur contenant des saisies non enregistrées.
- [ ] Deux commandes différentes sont modifiables en parallèle ; un même
      brouillon ou article est protégé par un verrou, libéré après fermeture.
- [ ] Simuler un arrêt brutal ; vérifier l'expiration du verrou.
- [ ] Déconnecter le partage : état hors ligne, consultation locale disponible,
      documents déjà mis en cache accessibles et modifications protégées bloquées.
- [ ] Reconnecter, synchroniser et vérifier l'absence de perte, de doublon ou de
      réapparition d'une commande supprimée.

### Diagnostic final et résultat

- [ ] Intégrité, recherche plein texte et cohérence de l'index : OK ; schéma 14.
- [ ] En collaboration : identité et empreinte du catalogue cohérentes,
      synchronisation à jour et absence de verrou expiré hors test volontaire.
- [ ] Exporter le diagnostic ; vérifier les événements récents et l'absence de
      recherches saisies, d'articles ou de tarifs dans le journal technique.
- [ ] En cas d'anomalie, noter les étapes et exporter les diagnostics des deux
      postes avant de modifier les données de test.
- [ ] Consigner la version, la date, les postes testés et le résultat du déploiement.

## Suite proposée

1. Ajouter des tests graphiques des fiches fournisseur et article avec
   saisie, enregistrement, fermeture et réouverture.
2. Extraire progressivement les composants communs puis un onglet de `ui.py`,
   avec contrôles à chaque déplacement ; conserver l'API `cahpp_app.ui.App`.
3. Séparer progressivement les domaines de persistance sans modifier le schéma.
4. Auditer les montants, leur stockage et leurs arrondis dans un chantier dédié.

Le découpage des gros fichiers et l'audit monétaire restent à réaliser.
