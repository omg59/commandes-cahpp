# Validation de Commandes CAHPP

Ce document est la checklist commune à toutes les versions. Les changements
propres à une version sont décrits dans le [changelog](../CHANGELOG.md).
Les cases ci-dessous sont à remplir lors de chaque validation : leur présence
ne signifie pas que les essais manuels ont déjà été réalisés.

## Contrôles automatiques

Installer les dépendances de test : `python -m pip install -r requirements-dev.txt`.
Lancer `python -m ruff check .` puis `python -m unittest discover -s tests -v`.
Vérifier aussi `python tools/release_checks.py`. Sous Windows,
`build_release.bat` enchaîne ces contrôles et la fabrication de l'installateur.

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
partage SMB réel. Les tests graphiques couvrent les neuf pages, une recherche,
les fiches fournisseur/article et un parcours brouillon, PDF puis reprise avant
envoi, avec fermeture et réouverture. Ils ne couvrent pas encore tous les
dialogues ni tous les parcours utilisateur. L'import mensuel couvre aussi
l'annulation de l'aperçu, une panne de sauvegarde, la vérification d'un article
et son passage en commande.
La construction PyInstaller n'est pas un test du lancement de l'EXE installé.

L'essai utilisateur de la 1.6.0 compilée sous Windows est consigné ci-dessous.
Les cases de validation restent une checklist à reprendre pour chaque
déploiement, notamment pour le partage SMB réel.

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
- [ ] Importer un fichier **Evo TARIFS** : aperçu, mois, sauvegarde préalable,
      conservation des références absentes et application de `ARTICLEACTIF`.
- [ ] Annuler l'aperçu et simuler une sauvegarde impossible : aucune modification.
- [ ] Tester le refus d'un mois manquant et d'un mois antérieur, la confirmation
      d'une révision et la réimportation identique sans nouvel import.
- [ ] Filtrer les articles à vérifier, confirmer un colisage puis commander ;
      tester le blocage d'un article non validé et la nouvelle vérification après
      une évolution qui change à nouveau le conditionnement.
- [ ] Reprendre un brouillon préparé avant un changement de conditionnement :
      actualiser sa ligne avant l'enregistrement ou la génération du PDF.
- [ ] Saisir rapidement une recherche, changer de filtre et afficher davantage
      de résultats : seule la dernière recherche est affichée et l'interface répond.
- [ ] Dans **Paramètres → Collaboration → Diagnostic**, cliquer sur **Reconstruire
      l'index** : l'interface reste réactive, le rapport confirme l'intégrité FTS5
      et la recherche avec classement ; refaire une recherche connue du catalogue.
- [ ] Sur le poste rencontrant l'erreur, exporter le rapport après la tentative,
      même si elle échoue ; vérifier que les commandes et corrections sont conservées.
- [ ] Sur le poste lent, essayer les recherches qui dépassaient le délai,
      puis une recherche sans résultat. Exporter le diagnostic après l'essai :
      statistiques du planificateur **OK**, plan FTS avant lecture des produits.
      Il n'est pas nécessaire de reconstruire un index déjà sain pour ce test.
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
- [ ] Reprendre une commande générée puis une commande avec e-mail préparé :
      même numéro, retour au brouillon, PDF à régénérer, reprise visible sur
      le second poste ; vérifier le refus pour une commande envoyée ou suivie.
- [ ] Quitter avec des quantités ou notes non enregistrées : Annuler conserve
      les saisies ; vérifier aussi la confirmation avant de remplacer la commande.
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
- [ ] Avec les deux postes en 1.6.0, appliquer deux mois sur le premier puis
      recevoir directement le dernier catalogue sur le second resté hors ligne.
      Refaire sur une base vide ; contrôler retraits, quantités et vérifications.
- [ ] Couper le partage pendant la publication ; relancer le même fichier après
      reconnexion : pas de double application et catalogue distant complet.
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

- [ ] Intégrité, recherche plein texte et cohérence de l'index : OK ; schéma 15.
- [ ] En collaboration : identité et empreinte du catalogue cohérentes,
      synchronisation à jour et absence de verrou expiré hors test volontaire.
- [ ] Exporter le diagnostic ; vérifier les événements récents et l'absence de
      recherches saisies, d'articles ou de tarifs dans le journal technique.
- [ ] En cas d'anomalie, noter les étapes et exporter les diagnostics des deux
      postes avant de modifier les données de test.
- [ ] Consigner la version, la date, les postes testés et le résultat du déploiement.

## Validation de la 1.6.0

Le 7 novembre 2026, sous Linux avec Python 3.12, les 66 tests automatisés passent,
y compris les quatre scénarios avec interface Tk, ainsi que Ruff et le contrôle
des versions. Les tests couvrent notamment la chronologie des mois, le rollback,
les réimports concurrents, les corrections et commandes conservées, les
vérifications de colisage et la reprise après échec de publication.

Le fichier de novembre fourni, contenant 2 758 références distinctes, a été
appliqué à une copie d'une base fictive de 158 488 articles : ces articles
absents du fichier restent actifs et les 378 références explicitement inactives
du fichier sont respectées. L'import programmatique, hors sauvegarde préalable,
a pris environ 4,2 secondes dans cet environnement.

Les codes de cette base fictive étant distincts, le catalogue reconstitué compte
161 246 lignes. Sa publication a pris environ 42 secondes et son import sur
une seconde base vide environ 77 secondes. Les comptes actifs/inactifs, jetons de
contrôle et entrées FTS concordent ; l'intégrité SQLite et FTS5 est valide.
Le nombre d'ajouts et d'articles à vérifier sur les postes réels dépend de leur
base existante. Ces mesures ne prédisent pas les délais du partage SMB ou des PC.

### Essai utilisateur sous Windows

Le 7 novembre 2026, l'utilisateur confirme son essai de la 1.6.0 compilée sous
Windows 11 : nouvelles références, changements de prix et de référence, arrêts
de commercialisation vérifiés sans erreur apparente. Le diagnostic fourni
confirme le schéma 15, deux imports, le mois 2026-11 et 165 articles à vérifier.
L'intégrité SQLite est valide ; les 158 865 articles sont indexés sans entrée
manquante, orpheline ou texte différent. La reconstruction après import réussit
en 1 595 ms. Le plan témoin part de FTS5 et lit les produits par clé primaire ;
les recherches journalisées prennent généralement 2 à 4 ms, avec une recherche
isolée à 774 ms après l'import. Le journal présenté ne contient aucune erreur.

La collaboration est désactivée dans ce diagnostic. L'essai sur le partage SMB
réel et sur le poste de la collègue reste à effectuer ; les scénarios automatisés
de publication et de réception sur deux bases temporaires passent.

### Enchaînement sur les deux fichiers réels d'octobre et novembre

Le catalogue complet d'octobre fourni contient 158 484 références et une
colonne réservée `ARTICLEACTIF` vide. Le lecteur conserve le comportement
historique de ce catalogue complet ; les fichiers mensuels exigent toujours
un statut explicite. Un test de régression couvre cette différence.

L'application des 2 758 lignes de novembre retrouve 2 384 références existantes
et en ajoute 374, dont 79 actives et 295 déjà inactives. Elle retire 83 références
existantes et signale 165 articles actifs dont le conditionnement est à vérifier.
Les articles absents du fichier mensuel sont identiques champ par champ ; le
favori et la commande témoins sont conservés, ainsi que les identifiants et
conditionnements des références retrouvées. Les tarifs et statuts correspondent
au fichier mensuel, avec conservation du dernier tarif des retraits sans prix.

Le catalogue reconstitué compte 158 858 références, dont 158 480 actives. Sa
réception sur une seconde base vide reproduit exactement les statuts, quantités,
tarifs et contrôles en attente. Les vérifications SQLite et FTS5 réussissent.
Ces essais utilisent des bases temporaires, sans modification des fichiers Excel
sources ni des installations des utilisateurs.

## Mesure de préparation de la 1.5.2

Sur un catalogue fictif de 158 488 articles, sous Linux avec SQLite 3.49.1 et
des statistiques périmées, l'ancienne requête a pris environ 6,9 s pour 33
résultats et 15,6 s sans résultat. Après actualisation des statistiques et
correction de la jointure, ces recherches ont pris respectivement environ
1,4 ms et 0,5 ms ; une recherche très large retournant 101 lignes a pris
environ 108 ms. L'actualisation des statistiques a pris environ 31 ms.

Ces mesures sur données fictives reproduisent un mécanisme de lenteur ; elles
ne garantissent pas les mêmes temps sur les postes utilisateurs. Le diagnostic
fourni confirme un dépassement de délai avec un index sain, sans prouver à lui
seul que les statistiques sont la cause sur ce poste. L'essai Windows reste requis.

## Suite proposée

1. Étendre les scénarios graphiques aux réceptions partielles.
2. Séparer progressivement les domaines de persistance sans modifier le schéma.
3. Auditer les montants, leur stockage et leurs arrondis dans un chantier dédié.

Le découpage de l'interface et les tests de réouverture des fiches sont intégrés
à la préparation de la 1.5.0. Le découpage de la persistance et l'audit monétaire
complet restent à réaliser.
