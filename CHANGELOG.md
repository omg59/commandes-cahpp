# Historique des versions

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
