"""Création et suivi de commandes mobiles avec les validations du moteur PC."""
import base64
import hashlib
from datetime import date
from pathlib import Path

from ..local_services import portable_path, safe_filename, resolve_portable_path
from ..money_storage import decimal_text

from ..pdf_export import default_order_pdf_path, generate_order_pdf
from .mobile_catalog import product_snapshot
from .mobile_documents import MAX_DOCUMENT_BYTES, check_mobile_attachment, document_filename, validate_document
from .mobile_identity import mobile_actor
from .services import Cart


def generate_pdf(db, order_id):
    directory = db.path.parent.parent / "exports"
    return generate_order_pdf(db, order_id, default_order_pdf_path(db, order_id, directory))


def apply_action(op, key, body):
    db = op.database
    cart_action = body["kind"] in ("create", "save_draft")
    uid = body.get("order_id", key) if cart_action else body["order_id"]
    with mobile_actor(db, body), op.resource("commande", uid):
        with db.connect() as c:
            existing = c.execute("SELECT id,shared_revision,status,order_date,deleted_at,archived_at,pdf_path,sent_at,confirmed_at,invoiced_at FROM orders WHERE shared_uid=?", (uid,)).fetchone()
            marker = c.execute(
                "SELECT order_id FROM order_audit WHERE event_uid=? UNION SELECT order_id FROM order_comments WHERE comment_uid=?",
                (key, key)).fetchone()
        if marker:
            if not existing or marker["order_id"] != existing["id"]:
                raise ValueError("Identité de l’action mobile incohérente.")
            oid = existing["id"]
            db.record_mobile_action(oid, key, body["kind"])
            if body["kind"] == "create" and not existing["pdf_path"]:
                expected = body["revision"] + 1 if "order_id" in body else 1
                if existing["shared_revision"] != expected:
                    raise ValueError("Le brouillon a changé après son enregistrement. Générez le bon depuis sa dernière version.")
                generate_pdf(db, oid)
            return {"order_id": uid}
        if cart_action:
            updating = "order_id" in body
            if existing and not updating:
                raise ValueError("Cet identifiant appartient déjà à une commande.")
            if updating and (not existing or existing["deleted_at"] or existing["archived_at"]
                             or existing["status"] != "Brouillon" or existing["sent_at"]):
                raise ValueError("Ce brouillon n’est plus modifiable. Actualisez les commandes.")
            if updating and existing["shared_revision"] != body["revision"]:
                raise ValueError("Le brouillon a changé sur un autre poste. Reprenez sa dernière version depuis Commandes.")
            cart = Cart()
            for line in body["lines"]:
                with db.connect() as c:
                    row = c.execute("SELECT id FROM products WHERE code_cahpp=?", (line["code"],)).fetchone()
                if not row:
                    raise ValueError("Une référence du panier a été supprimée. Rechargez le catalogue.")
                product = db.get_product(row["id"])
                supplier = db.get_supplier(product["supplier_id"])
                snapshot = product_snapshot(db, product, supplier)
                if snapshot["fingerprint"] != line["fingerprint"]:
                    # Les anciennes demandes restent valides quand le prix
                    # numérique transmis auparavant représentait la même valeur.
                    legacy = product_snapshot(db, product, supplier, legacy_price=True)
                    if legacy["fingerprint"] != line["fingerprint"] or decimal_text(legacy["price"]) != snapshot["price"]:
                        raise ValueError(f"Les informations de « {product['designation']} » ont changé. Vérifiez le panier avec le catalogue actualisé.")
                cart.add(product, quantity=line["cartons"])
            # Le numéro et le marqueur sont enregistrés avec les lignes dans la même transaction.
            number = None if updating else op.manager.reserve_order_number(date.today())
            oid = db.save_order(cart.supplier_id, [line.as_mapping() for line in cart.lines],
                                order_id=existing["id"] if updating else None,
                                selected_date=date.fromisoformat(existing["order_date"]) if updating else None,
                                shared_uid=uid, order_number=number, notes=body.get("notes", ""),
                                requester_service=body.get("service", ""), save_event_uid=key)
            if body["kind"] == "create":
                generate_pdf(db, oid)
            return {"order_id": uid}
        if not existing or existing["deleted_at"]:
            raise ValueError("Commande supprimée ou introuvable.")
        existing_document = False
        if body["kind"] == "document":
            mime = body.get("mime")
            filename = document_filename(body.get("name"), key, mime)
            encoded = body.get("data")
            if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_DOCUMENT_BYTES + 2) // 3):
                raise ValueError("Document mobile invalide ou trop volumineux.")
            data = base64.b64decode(encoded, validate=True)
            validate_document(data, mime)
            original = Path(body["name"])
            previous_name = safe_filename(original.stem[:120] + "-" + key + original.suffix)
            attachment = next((a for a in db.list_order_attachments(existing["id"])
                               if a["display_name"] in (filename, previous_name)), None)
            if attachment:
                stored = resolve_portable_path(attachment["stored_path"])
                if stored.is_file():
                    check_mobile_attachment(stored, attachment["display_name"])
                    existing_document = hashlib.sha256(stored.read_bytes()).digest() == hashlib.sha256(data).digest()
        completed_fields = {"sent": "sent_at", "confirm": "confirmed_at", "invoiced": "invoiced_at", "archive": "archived_at"}
        if existing["shared_revision"] != body["revision"] and body["kind"] in completed_fields and existing[completed_fields[body["kind"]]]:
            db.record_mobile_action(existing["id"], key, body["kind"])
            return {"order_id": uid}
        if not existing_document and existing["shared_revision"] != body["revision"]:
            raise ValueError("La commande a été modifiée sur un autre poste. Actualisez-la avant de recommencer.")
        if existing["archived_at"] and body["kind"] != "archive":
            raise ValueError("Restaurez d’abord la commande archivée depuis le PC.")
        oid = existing["id"]
        kind = body["kind"]
        if kind == "comment":
            db.add_order_comment(oid, body["text"], comment_uid=key)
            db.record_mobile_action(oid, key, kind)
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
                try:
                    temp.write_bytes(data)
                    temp.replace(path)
                finally:
                    temp.unlink(missing_ok=True)
                db.add_order_attachment(oid, body["document_kind"], filename, portable_path(path))
        else:
            raise ValueError("Action mobile inconnue.")
        db.record_mobile_action(oid, key, kind)
        return {"order_id": uid}
