"""Création et suivi de commandes mobiles avec les validations du moteur PC."""
import base64
import hashlib
from datetime import date
from pathlib import Path

from ..local_services import portable_path, safe_filename, resolve_portable_path

from ..pdf_export import default_order_pdf_path, generate_order_pdf
from .mobile_catalog import product_snapshot
from .services import Cart


def generate_pdf(db, order_id):
    directory = db.path.parent.parent / "exports"
    return generate_order_pdf(db, order_id, default_order_pdf_path(db, order_id, directory))


def apply_action(op, key, body):
    db = op.database
    uid = key if body["kind"] == "create" else body["order_id"]
    with op.resource("commande", uid):
        with db.connect() as c:
            existing = c.execute("SELECT id,shared_revision,deleted_at,archived_at,pdf_path,sent_at FROM orders WHERE shared_uid=?", (uid,)).fetchone()
            marker = c.execute("SELECT order_id FROM order_comments WHERE comment_uid=?", (key,)).fetchone()
        if marker:
            if not existing or marker["order_id"] != existing["id"]:
                raise ValueError("Identité de l’action mobile incohérente.")
            oid = existing["id"]
            if body["kind"] == "create" and not existing["pdf_path"]:
                generate_pdf(db, oid)
            return {"order_id": uid}
        if body["kind"] == "create":
            if existing:
                raise ValueError("Cet identifiant appartient déjà à une commande.")
            cart = Cart()
            for line in body["lines"]:
                with db.connect() as c:
                    row = c.execute("SELECT id FROM products WHERE code_cahpp=?", (line["code"],)).fetchone()
                if not row:
                    raise ValueError("Une référence du panier a été supprimée. Rechargez le catalogue.")
                product = db.get_product(row["id"])
                supplier = db.get_supplier(product["supplier_id"])
                if product_snapshot(db, product, supplier)["fingerprint"] != line["fingerprint"]:
                    raise ValueError(f"Les informations de « {product['designation']} » ont changé. Vérifiez le panier avec le catalogue actualisé.")
                cart.add(product, quantity=line["cartons"])
            # Le numéro et le marqueur sont enregistrés avec les lignes dans la même transaction.
            number = op.manager.reserve_order_number(date.today())
            oid = db.save_order(cart.supplier_id, [line.as_mapping() for line in cart.lines],
                                shared_uid=uid, order_number=number, notes=body.get("notes", ""),
                                requester_service=body.get("service", ""), creation_comment_uid=key)
            generate_pdf(db, oid)
            return {"order_id": uid}
        if not existing or existing["deleted_at"]:
            raise ValueError("Commande supprimée ou introuvable.")
        existing_document = False
        if body["kind"] == "document":
            filename = safe_filename(Path(body["name"]).stem[:120] + "-" + key + Path(body["name"]).suffix)
            attachment = next((a for a in db.list_order_attachments(existing["id"]) if a["display_name"] == filename), None)
            if attachment:
                stored = resolve_portable_path(attachment["stored_path"])
                existing_document = stored.is_file() and hashlib.sha256(stored.read_bytes()).digest() == hashlib.sha256(base64.b64decode(body["data"])).digest()
        if not existing_document and existing["shared_revision"] != body["revision"]:
            raise ValueError("La commande a été modifiée sur un autre poste. Actualisez-la avant de recommencer.")
        if existing["archived_at"] and body["kind"] != "archive":
            raise ValueError("Restaurez d’abord la commande archivée depuis le PC.")
        oid = existing["id"]
        kind = body["kind"]
        if kind == "comment":
            db.add_order_comment(oid, body["text"], comment_uid=key)
            return {"order_id": uid}
        if kind == "sent":
            if not existing["pdf_path"]:
                raise ValueError("Générez le bon de commande avant de marquer l’envoi.")
            db.update_order_status(oid, "Envoyée")
        elif kind == "confirm":
            db.mark_order_confirmed(oid)
        elif kind == "invoiced":
            db.mark_order_invoiced(oid)
        elif kind == "archive":
            db.set_order_archived(oid, True)
        elif kind == "generate_pdf":
            generate_pdf(db, oid)
        elif kind == "document":
            if not existing_document:
                folder = db.path.parent.parent / "documents" / "mobile" / uid / key
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / filename
                temp = folder / "incoming.tmp"
                temp.write_bytes(base64.b64decode(body["data"], validate=True))
                temp.replace(path)
                db.add_order_attachment(oid, body["document_kind"], filename, portable_path(path))
        else:
            raise ValueError("Action mobile inconnue.")
        db.add_order_comment(oid, "Action depuis Horizon Mobile : " + kind, comment_uid=key)
        return {"order_id": uid}
