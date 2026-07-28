# Historique des versions

## 1.0.0-rc1

- ajout d'un diagnostic accessible depuis **Paramètres > Collaboration** ;
- contrôle SQLite `quick_check`, version du schéma, mode de journalisation,
  disponibilité de la recherche et détection d'enregistrements orphelins ;
- contrôle en lecture/écriture du dossier partagé, du renommage atomique, de
  l'identifiant de l'espace et de l'intégrité du catalogue publié ;
- affichage du nombre de commandes locales en attente et du bilan du dernier
  échange dans les paramètres et la barre latérale ;
- recensement des verrous actifs ou expirés et des utilisateurs concernés ;
- export ou copie d'un rapport de dépannage ne contenant ni tarif, ni ligne de
  commande, ni contenu de document ;
- ajout d'une checklist de validation à deux postes avant promotion en V1.0.

## 0.9.0

- ajout d'un mode collaboratif sans serveur : chaque poste conserve sa base
  SQLite locale et échange uniquement des fichiers versionnés dans un dossier
  réseau partagé ;
- création d'un profil nominatif au premier lancement, modifiable dans les
  paramètres, sans notion de poste ou d'emplacement ;
- choix, test, ouverture et modification du dossier partagé depuis l'onglet
  **Collaboration** ;
- synchronisation automatique et manuelle des commandes, fournisseurs,
  favoris, corrections du catalogue, articles hors catalogue et paramètres
  communs ;
- publication versionnée des catalogues CAHPP avec contrôle d'intégrité SHA-256
  et proposition d'installation sur les autres postes ;
- numérotation commune des commandes afin d'éviter les doublons ;
- verrou temporaire d'une commande ou d'un article pendant sa modification ;
- consultation locale maintenue lorsque le partage est indisponible, avec
  indication **Hors ligne — cache local** ;
- copie locale des PDF et documents reçus pour préserver leur consultation
  hors connexion ;
- ajout du créateur et de l'état de synchronisation dans l'historique ;
- ajout d'un journal nominatif des actions de chaque commande ;
- conservation de révisions récentes des données d'équipe et des commandes
  dans le dossier partagé ;
- retrait de la base de développement lors de la compilation du dossier
  portable : chaque poste démarre désormais avec sa propre base locale.

## 0.8.1b

- suppression de la fenêtre explicative après **Préparer le mail** ;
- conservation de l'ouverture automatique du message et du dossier contenant
  les pièces à joindre.

## 0.8.1

- retrait de la colonne redondante « Date du BC » dans l'historique ; la date
  reste conservée dans la base, le PDF et le nom du fichier ;
- suppression automatique du dossier temporaire
  `envois/<numero de commande>` lorsque la commande est marquée comme envoyée ;
- conservation du PDF original et des documents liés lors de ce nettoyage.

## 0.8.0

- ajout des dates de création et de premier envoi dans l'historique des
  commandes ;
- conservation de la première date d'envoi lorsqu'une commande est marquée
  plusieurs fois comme envoyée ;
- corrections locales des articles CAHPP sans modifier les valeurs importées,
  avec possibilité de rétablir les valeurs du catalogue ;
- modification et archivage des références créées par l'utilisateur ;
- suppression du code CAHPP dans le tableau du bon de commande PDF ;
- affichage automatique de la version du logiciel dans la barre latérale ;
- préparation des e-mails rendue plus générique, avec prise en charge de Gmail,
  des URL de composition génériques et des liens `mailto:` ;
- aide intégrée recensant les expressions utilisables dans l'objet et le corps
  des e-mails, dont `{date}` et `{total_ttc}`.

## 0.7.0

- remplacement des fenêtres de confirmation après enregistrement par un retour
  visuel temporaire directement sur le bouton concerné ;
- confirmation non bloquante pour les paramètres, les fournisseurs, les
  brouillons, la génération ou régénération des PDF et les sauvegardes ;
- affichage permanent de la section active dans la navigation latérale avec
  fond renforcé, texte en gras et liseré coloré ;
- conservation des fenêtres uniquement pour les erreurs, avertissements,
  décisions importantes et bilans détaillés.

## 0.6.1

- correction de la fenêtre des documents liés : la barre d'actions reste
  visible avec la mise à l'échelle de Windows et la hauteur s'adapte désormais
  au contenu et à l'écran.

## 0.6.0

- préparation locale des messages dans Gmail avec destinataire, objet et corps
  configurables ;
- regroupement automatique du PDF et des pièces jointes dans un dossier d'envoi ;
- duplication d'une ancienne commande en nouveau brouillon ;
- recherche dans l'historique par numéro, fournisseur, note, référence, code CAHPP
  ou désignation ;
- rattachement de bons de livraison et d'autres documents aux commandes ;
- intégration des documents liés dans la sauvegarde complète ZIP ;
- alerte après import pour les changements de prix ou de conditionnement
  concernant des articles déjà commandés ;
- coordonnées fournisseur enrichies, minimum de commande et franco ;
- contrôle des nombres de cartons non entiers et des seuils avant enregistrement ;
- affichage enrichi du conditionnement et favoris proposés par fournisseur ;
- migration automatique des bases créées avec les versions précédentes.

## 0.4.0

- nouveau nom PDF : `BC-AAAA-MM-JJ_Fournisseur.pdf` ;
- incrément journalier par fournisseur à partir de la deuxième commande.

## 0.3.0

- recherche par saisie dans la liste des fournisseurs ;
- création d'une commande directement depuis un article du catalogue ;
- choix du nom et de la destination lors de chaque génération PDF ;
- dossier PDF par défaut configurable.

## 0.2.0

- ajout de la modification des brouillons depuis l'historique ;
- conservation du numéro et de la date lors de la réédition ;
- titre du PDF personnalisable ;
- texte du pied de page personnalisable et vide par défaut ;
- affichage du numéro de page désactivable.

## 0.1.0

- import et mise à jour du catalogue CAHPP ;
- recherche, favoris, commandes et fournisseurs ;
- génération PDF et base SQLite portable.
