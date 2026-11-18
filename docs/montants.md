# Prix et montants — schéma 17

Horizon PC 3.0.1a8 stocke les prix du catalogue, ses corrections et son
historique, les seuils fournisseurs et les montants des commandes sous forme
de décimaux exacts. SQLite les conserve en texte décimal normalisé, sans
conversion en flottants. Ce choix préserve aussi les prix unitaires qui
comportent plus de quatre décimales.

## Première ouverture

Horizon crée une copie SQLite cohérente nommée
`commandes_cahpp-avant-montants-v17-….sqlite3` dans le dossier `data` du profil,
puis convertit les tables monétaires dans une transaction. Le diagnostic
indique la présence de cette copie. Si un montant est illisible ou si une
référence SQLite est invalide, la conversion est annulée et la copie est
conservée. L’import d’une base 1.6 travaille toujours sur une copie.

Les valeurs des commandes existantes sont reprises telles qu’elles étaient
enregistrées, sans appliquer le prix actuel du catalogue et sans arrondir leurs
totaux au centime. Les PDF et pièces jointes existants restent en place.
Pour une valeur anciennement stockée en `REAL`, Horizon reprend sa représentation
décimale lisible. Il ne peut pas retrouver des chiffres que l’ancien stockage
avait déjà perdus.

Pour revenir à une version précédente, fermer Horizon et restaurer la copie
du schéma précédent ou une sauvegarde complète correspondante. Une copie
automatique de la base ne remplace pas la sauvegarde ZIP des documents.

## Calcul et échanges

Pour une nouvelle commande, Horizon multiplie le prix unitaire intégral par
le nombre d’unités, puis arrondit le HT et la TVA de chaque ligne à quatre
décimales, au plus proche avec les demis arrondis vers l’extérieur. Le panier
et la commande utilisent la même règle. Les totaux affichés et les e-mails
sont présentés au centime. Le PDF affiche la précision du prix unitaire.

Les statistiques agrègent les valeurs exactes. Le classeur de statistiques
conserve les cellules monétaires numériques dans la limite des 15 chiffres
significatifs pris en charge par Excel. Au-delà, il exporte la valeur en texte
pour conserver tous ses chiffres. Les instantanés de catalogue partagés
écrivent les prix en texte décimal, interprété à l’import.

Les données échangées entre PC et avec le relais utilisent des chaînes
décimales pour les montants. Horizon accepte aussi les anciens champs JSON
numériques. Le relais 0.5.0-dev5 transporte les deux formes et la projection 4
republie les montants sans modifier la révision métier des commandes.
Android 0.6.0-dev6 lit les deux formes et calcule son panier avec la même règle.

Une demande mobile créée avant la mise à jour reste traitable si l’ancien
prix numérique représentait exactement le même prix. Si le prix ne peut pas
être confirmé, le panier reste disponible pour une actualisation du catalogue.
