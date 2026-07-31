# Checklist de validation de la V1.0

Cette checklist permet de valider la version collaborative dans les conditions
réelles du service. Elle doit être effectuée avec deux installations locales et
un même dossier partagé.

## Préparation

- [ ] L'application est installée dans un dossier local sur chacun des deux PC.
- [ ] Aucun fichier `commandes_cahpp.sqlite3` n'est placé sur le réseau.
- [ ] Les deux utilisateurs ont un nom de profil différent.
- [ ] Les deux applications affichent exactement le même identifiant d'espace
      dans **Paramètres > Collaboration**.
- [ ] **Tester l'accès** indique Lecture, Écriture et Renommage sécurisé à OK.

## Première synchronisation

- [ ] Le poste principal publie le catalogue CAHPP actuel.
- [ ] Le second poste propose l'installation de ce catalogue.
- [ ] Le nombre d'articles actifs est comparable sur les deux diagnostics.
- [ ] Les fournisseurs configurés apparaissent sur le second poste.
- [ ] Les favoris, corrections et produits hors catalogue sont récupérés.
- [ ] Les anciennes commandes du poste principal apparaissent sur le second.
- [ ] Après synchronisation, aucun poste n'indique de commande en attente.
- [ ] Le délai automatique choisi dans les paramètres est conservé après
      redémarrage.
- [ ] Une fiche établissement non enregistrée ne se vide pas pendant une
      synchronisation.
- [ ] Une fiche fournisseur non enregistrée ne se vide pas pendant une
      synchronisation.

## Commandes et numérotation

- [ ] Une commande créée sur le poste A apparaît sur le poste B.
- [ ] Une commande créée sur le poste B apparaît sur le poste A.
- [ ] Les deux commandes possèdent des numéros différents et consécutifs.
- [ ] Le créateur affiché dans l'historique est correct.
- [ ] Le journal de chaque commande reprend les actions et le bon utilisateur.
- [ ] La duplication d'une commande est synchronisée.
- [ ] Un brouillon supprimé sur A disparaît de l'historique sur B.
- [ ] Un brouillon supprimé ne réapparaît pas après redémarrage et
      synchronisation des deux postes.
- [ ] Une commande déjà générée ne peut pas être supprimée.
- [ ] Une commande marquée envoyée affiche la date et l'utilisateur attendus.

## Travail simultané

- [ ] Deux commandes différentes peuvent être modifiées en même temps.
- [ ] Un brouillon ouvert sur le poste A est protégé contre la modification
      depuis le poste B.
- [ ] Le verrou disparaît normalement lorsque le brouillon est fermé.
- [ ] Un article en cours de correction est protégé de la même manière.
- [ ] Après fermeture brutale d'un test, le verrou finit par expirer.

## Produits et catalogue

- [ ] Un clic sur chaque en-tête utile trie le catalogue dans le bon sens.
- [ ] Un second clic inverse le sens et la flèche affichée correspond.
- [ ] Le tri choisi est conservé après une nouvelle recherche.
- [ ] Le même comportement fonctionne dans les deux listes d'une commande.
- [ ] Un favori ajouté sur A apparaît sur B.
- [ ] Une quantité habituelle modifiée sur B apparaît sur A.
- [ ] Une correction de conditionnement CAHPP est synchronisée.
- [ ] Le rétablissement de la valeur CAHPP est synchronisé.
- [ ] Un produit hors catalogue créé sur A peut être utilisé sur B.
- [ ] Sa modification puis son archivage sont répercutés.

## PDF et documents

- [ ] Les actions de l'historique tiennent entièrement sur une seule ligne à
      la largeur minimale de la fenêtre.
- [ ] La fenêtre de choix du type de document s'ouvre centrée sur
      **Documents associés**.
- [ ] Le PDF d'une commande est ouvrable depuis l'autre poste.
- [ ] Le PDF ne contient aucune mention « Franco atteint » ou
      « Franco non atteint ».
- [ ] Un bon de livraison ajouté sur A est visible et ouvrable sur B.
- [ ] Une confirmation, une facture et un devis peuvent être classés
      séparément.
- [ ] Un type personnalisé peut être saisi puis modifié.
- [ ] Le type et le choix « Joint au mail » peuvent être modifiés
      indépendamment après l'ajout.
- [ ] Une pièce marquée « Joint au mail » est proposée sur l'autre poste.
- [ ] Le rapport de diagnostic ne contient aucun nom d'article ou tarif.

## Mise à jour de l'application

- [ ] L'installeur V1.0 s'exécute sans demander de droit administrateur.
- [ ] La première installation dans le dossier choisi démarre correctement.
- [ ] Une réinstallation V1.0 remplace l'application sans effacer la base.
- [ ] Les dossiers `documents`, `assets`, `exports` et `sauvegardes` sont
      conservés.
- [ ] Les raccourcis ouvrent l'application avec le bon dossier de travail.

## Coupure et reprise réseau

- [ ] Après déconnexion du partage, l'état **Hors ligne — cache local** apparaît.
- [ ] Le catalogue et l'historique restent consultables.
- [ ] Un PDF déjà synchronisé reste ouvrable.
- [ ] La modification d'une commande partagée est bloquée proprement.
- [ ] Après rétablissement du réseau, **Synchroniser maintenant** fonctionne.
- [ ] Les commandes en attente reviennent à zéro.

## Diagnostic final

Sur chaque poste, ouvrir **Paramètres > Collaboration > Diagnostic** :

- [ ] Contrôle d'intégrité : OK.
- [ ] Schéma : 10.
- [ ] Recherche plein texte : OK.
- [ ] Lecture, Écriture et Renommage atomique : OK.
- [ ] Identifiant cohérent : OK.
- [ ] Intégrité du catalogue : OK.
- [ ] Anomalies : aucune.
- [ ] Commandes à synchroniser : 0.
- [ ] Verrous expirés : 0, hors test volontaire.

## Résultat

- [ ] Tous les contrôles obligatoires sont validés : la V1.0 peut être
      déployée.
- [ ] Une anomalie est constatée : exporter le diagnostic des deux postes,
      noter l'action effectuée et conserver les dossiers avant correction.
