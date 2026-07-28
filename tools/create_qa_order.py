from __future__ import annotations

import sys
from pathlib import Path

from cahpp_app.database import Database
from cahpp_app.pdf_export import generate_order_pdf


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(
            "Usage: python -m tools.create_qa_order BASE.sqlite3 SORTIE.pdf [long]"
        )
    database = Database(Path(sys.argv[1]))
    output = Path(sys.argv[2])
    database.save_settings(
        {
            "establishment_name": "Clinique de démonstration",
            "establishment_subtitle": "Service de soins",
            "address_line1": "10 rue de l'Exemple",
            "postal_city": "59220 Denain",
            "phone": "03 00 00 00 00",
            "email": "commandes@exemple.fr",
            "finess": "590000000",
            "siret": "000 000 000 00000",
            "ape": "8610Z",
        }
    )
    products = []
    if len(sys.argv) == 4 and sys.argv[3] == "long":
        suppliers = {
            row["name"]: row["id"] for row in database.list_suppliers(used_only=True)
        }
        products = database.search_products(
            supplier_id=suppliers["HARTMANN"], limit=35
        )
    else:
        for reference in ("992260", "303073", "416521", "947792", "995077"):
            found = database.search_products(reference, limit=10)
            product = next(
                (
                    row
                    for row in found
                    if row["supplier_name"] == "HARTMANN"
                    and row["supplier_ref"] == reference
                ),
                None,
            )
            if product:
                products.append(product)
    if not products:
        raise RuntimeError("Produits HARTMANN introuvables")
    supplier_id = int(products[0]["supplier_id"])
    database.update_supplier(
        supplier_id,
        customer_number="18001105",
        email="commandes@hartmann.example",
        phone="",
        franco_ht=325,
        notes="Livraison au service logistique.",
    )
    quantities = [1, 2, 1, 1, 1] if len(products) == 5 else [1] * len(products)
    lines = [
        {
            "product_id": product["id"],
            "code_cahpp": product["code_cahpp"],
            "supplier_ref": product["supplier_ref"],
            "designation": product["designation"],
            "cartons": quantities[index],
            "units_per_carton": product["conditionnement"],
            "unit_price": product["unit_price"],
            "vat": product["vat"],
        }
        for index, product in enumerate(products)
    ]
    order_id = database.save_order(
        supplier_id,
        lines,
        notes="Merci d'indiquer le numéro de commande sur le bon de livraison.",
    )
    generate_order_pdf(database, order_id, output)
    print(output)


if __name__ == "__main__":
    main()
