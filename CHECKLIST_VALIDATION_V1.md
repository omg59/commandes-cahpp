# Checklist de validation avant la V1.0

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

## Commandes et numérotation

- [ ] Une commande créée sur le poste A apparaît sur le poste B.
- [ ] Une commande créée sur le poste B apparaît sur le poste A.
- [ ] Les deux commandes possèdent des numéros différents et consécutifs.
- [ ] Le créateur affiché dans l'historique est correct.
- [ ] Le journal de chaque commande reprend les actions et le bon utilisateur.
- [ ] La duplication d'une commande est synchronisée.
- [ ] Une commande marquée envoyée affiche la date et l'utilisateur attendus.

## Travail simultané

- [ ] Deux commandes différentes peuvent être modifiées en même temps.
- [ ] Un brouillon ouvert sur le poste A est protégé contre la modification
      depuis le poste B.
- [ ] Le verrou disparaît normalement lorsque le brouillon est fermé.
- [ ] Un article en cours de correction est protégé de la même manière.
- [ ] Après fermeture brutale d'un test, le verrou finit par expirer.

## Produits et catalogue

- [ ] Un favori ajouté sur A apparaît sur B.
- [ ] Une quantité habituelle modifiée sur B apparaît sur A.
- [ ] Une correction de conditionnement CAHPP est synchronisée.
- [ ] Le rétablissement de la valeur CAHPP est synchronisé.
- [ ] Un produit hors catalogue créé sur A peut être utilisé sur B.
- [ ] Sa modification puis son archivage sont répercutés.

## PDF et documents

- [ ] Le PDF d'une commande est ouvrable depuis l'autre poste.
- [ ] Un bon de livraison ajouté sur A est visible et ouvrable sur B.
- [ ] Une pièce marquée « Joint au mail » est proposée sur l'autre poste.
- [ ] Le rapport de diagnostic ne contient aucun nom d'article ou tarif.

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
- [ ] Schéma : 9.
- [ ] Recherche plein texte : OK.
- [ ] Lecture, Écriture et Renommage atomique : OK.
- [ ] Identifiant cohérent : OK.
- [ ] Intégrité du catalogue : OK.
- [ ] Anomalies : aucune.
- [ ] Commandes à synchroniser : 0.
- [ ] Verrous expirés : 0, hors test volontaire.

## Résultat

- [ ] Tous les contrôles obligatoires sont validés : la candidate peut être
      promue en V1.0.
- [ ] Une anomalie est constatée : exporter le diagnostic des deux postes,
      noter l'action effectuée et conserver les dossiers avant correction.

