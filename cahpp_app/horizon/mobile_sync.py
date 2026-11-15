"""Échange explicite avec le relais depuis un poste du partage."""
import base64
import io
import json
import os
import ssl
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID

import certifi

from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from ..collaboration import ResourceLockedError, SyncConflictError
from ..local_services import portable_path, resolve_portable_path


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class RelayHTTPError(ValueError):
    def __init__(self, error, route):
        self.http_status = error.code
        self.http_endpoint = route.split("/")[0]
        content_type = error.headers.get("Content-Type", "")
        self.http_origin = "html" if "text/html" in content_type else "unknown"
        messages = {
            "Clé invalide.": "La clé PC est refusée. Vérifiez HORIZON_PC_TOKEN dans Portainer.",
            "Action non autorisée.": "Cette clé ne permet pas une synchronisation PC. Utilisez HORIZON_PC_TOKEN.",
            "Ressource inconnue.": "La route demandée est indisponible. Vérifiez l’adresse du relais et sa version.",
            "API inconnue.": "Vérifiez l’adresse du relais : elle doit désigner la racine du service.",
        }
        try:
            raw = error.read(4096)
            payload = json.loads(raw)
            message = messages.get(payload.get("error")) if isinstance(payload, dict) else None
        except (ValueError, UnicodeError, OSError):
            message = None
        finally:
            error.close()
        if message:
            self.http_origin = "relay"
        elif error.headers.get("cf-mitigated", "").lower() == "challenge":
            self.http_origin = "cloudflare-challenge"
            message = "Cloudflare exige une vérification interactive pour la connexion au relais."
        elif self.http_origin == "html":
            message = ("Le serveur renvoie une page HTML. Vérifiez la règle du domaine "
                       "dans Nginx Proxy Manager et les règles d’accès de Cloudflare.")
        else:
            message = "Vérifiez la clé PC, la destination du proxy et les règles d’accès au relais."
        super().__init__(f"HTTP {error.code} sur /v1/{self.http_endpoint} — {message}")


class Relay:
    def __init__(self, url, token):
        self.url = url.rstrip("/")
        parts = urlsplit(self.url)
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or not (
            parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"})
        ):
            raise ValueError("Indiquez une URL HTTPS pour le relais.")
        if not token:
            raise ValueError("La clé PC du relais est manquante.")
        self.token = token
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=certifi.where())
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=context))

    def call(self, route, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = Request(f"{self.url}/v1/{route}", data=data, method="GET" if data is None else "PUT",
                      headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            response = self.opener.open(req, timeout=30)
        except HTTPError as exc:
            raise RelayHTTPError(exc, route) from exc
        except URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise ValueError(
                    "Le certificat HTTPS du relais ne peut pas être validé. "
                    "Vérifiez que le domaine correspond au certificat et que "
                    "Nginx Proxy Manager présente la chaîne de certificats complète. "
                    f"Détail TLS : {exc.reason.verify_message}"
                ) from exc
            raise
        with response as result:
            raw = result.read(17 * 1024 * 1024 + 1)
            if len(raw) > 17 * 1024 * 1024:
                raise ValueError("Réponse du relais trop volumineuse.")
            return json.loads(raw)


def delivery_pdf(pages, destination):
    if not 1 <= len(pages) <= 8:
        raise ValueError("Le bon doit contenir une à huit pages.")
    pdf = Canvas(str(destination), pagesize=A4)
    for encoded in pages:
        try:
            with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as image:
                if image.format != "JPEG" or image.width * image.height > 20_000_000:
                    raise ValueError("Photo JPEG invalide ou trop grande.")
                photo = ImageOps.exif_transpose(image).convert("RGB")
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
            raise ValueError("Photo JPEG illisible.") from exc
        with photo:
            width, height = A4 if photo.height >= photo.width else tuple(reversed(A4))
            pdf.setPageSize((width, height))
            pdf.drawImage(ImageReader(photo), 12, 12, width - 24, height - 24,
                          preserveAspectRatio=True, anchor="c")
            pdf.showPage()
    pdf.save()


class ReceiptConflict(ValueError):
    pass


def apply_receipt(op, key, receipt):
    db = op.database
    uid = str(UUID(receipt["order_id"]))
    with op.resource("commande", uid):
        with db.connect() as c:
            order = c.execute("SELECT id, deleted_at, archived_at FROM orders WHERE shared_uid=?", (uid,)).fetchone()
            existing = c.execute("SELECT order_id FROM order_receipts WHERE receipt_uid=?", (key,)).fetchone()
        if not order:
            # Un poste peut ne pas encore avoir importé une commande du partage.
            raise RuntimeError("Commande absente du poste. Synchronisez le partage puis réessayez.")
        name = f"BL-{key}.pdf"
        if existing and existing["order_id"] != order["id"]:
            raise ReceiptConflict("Identifiant de réception déjà utilisé.")
        if not existing:
            if order["deleted_at"] or order["archived_at"]:
                raise ReceiptConflict("Commande supprimée ou archivée.")
            root = db.path.parent.parent / "documents" / "receptions-mobile" / uid
            root.mkdir(parents=True, exist_ok=True)
            path = root / name
            with tempfile.NamedTemporaryFile(dir=root, suffix=".pdf", delete=False) as stream:
                temp = Path(stream.name)
            try:
                try:
                    delivery_pdf(receipt["pages"], temp)
                except ValueError as exc:
                    raise ReceiptConflict("Photo illisible ou invalide.") from exc
                os.replace(temp, path)
                try:
                    db.add_receipt(order["id"], date.fromisoformat(receipt["date"]), receipt["quantities"],
                                   reference=receipt.get("reference", ""), receipt_uid=key,
                                   notes="Saisie depuis Horizon Mobile", delivery_note=(name, portable_path(path)))
                except ValueError as exc:
                    path.unlink(missing_ok=True)
                    raise ReceiptConflict(str(exc)) from exc
            finally:
                temp.unlink(missing_ok=True)
        docs = db.list_order_attachments(order["id"])
        if not any(d["display_name"] == name and resolve_portable_path(d["stored_path"]).is_file() for d in docs):
            raise RuntimeError("Bon de livraison introuvable sur le poste. Archivage à vérifier.")
    # La sortie du verrou a publié la commande et le PDF sur le partage.


def publish_orders(op, relay):
    db = op.database
    versions = relay.call("versions")
    with db.connect() as c:
        orders = list(c.execute("SELECT id, shared_uid, shared_revision, sent_at FROM orders WHERE sync_state='Synchronisée'"))
    for row in orders:
        uid = row["shared_uid"]
        if not uid or (not row["sent_at"] and uid not in versions) or versions.get(uid, -1) >= row["shared_revision"]:
            continue
        summary = db.receipt_summary(row["id"])
        order = summary["order"]
        lines = [{"id": line["line_uid"], "label": line["designation"], "remaining": line["remaining_units"]}
                 for line in summary["lines"] if line["remaining_units"] > 0]
        active = lines and order["sent_at"] and not (order["archived_at"] or order["deleted_at"] or order["delivered_at"])
        snapshot = {"id": uid, "number": order["order_number"], "supplier": order["supplier_name"],
                    "lines": lines} if active else None
        relay.call("orders/" + uid, {"revision": order["shared_revision"], "order": snapshot})


def synchronize(op, relay):
    if not op.manager:
        raise ValueError("Activez le dossier partagé sur ce profil avant la synchronisation mobile.")
    archived = rejected = deferred = 0
    with op.write():
        if op.editing_order is not None:
            raise ValueError("Fermez la commande en cours de modification avant la synchronisation mobile.")
        op.manager.sync_orders()
        publish_orders(op, relay)
        for item in relay.call("pending"):
            key = str(UUID(item))
            route = "receipts/" + key
            result = relay.call(route)
            if result["state"] != "pending":
                continue
            try:
                apply_receipt(op, key, result["receipt"])
            except (ResourceLockedError, SyncConflictError):
                deferred += 1
                continue
            except ReceiptConflict as exc:
                relay.call(route + "/result", {"state": "rejected", "reason": str(exc)[:500]})
                rejected += 1
            else:
                relay.call(route + "/result", {"state": "archived"})
                archived += 1
        publish_orders(op, relay)
    return (f"{archived} réception(s) archivée(s), {rejected} à corriger, "
            f"{deferred} en attente de déverrouillage ou de résolution de conflit.")
