"""Échange explicite avec le relais depuis un poste du partage."""
import base64
import gzip
import io
import hashlib
import json
import os
import logging
import ssl
import tempfile
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import UUID

import certifi

from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from ..collaboration import ResourceLockedError, SyncConflictError
from ..local_services import portable_path, resolve_portable_path, order_mail_content
from .mobile_catalog import CatalogTransferPaused, publish_catalog
from .mobile_commands import apply_action
from .mobile_identity import mobile_actor
from .mobile_space import connect_workspace


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class RelayNetworkError(URLError):
    """Erreur réseau présentable, sans adresse, clé ni message brut de socket."""
    def __init__(self, *, timeout, endpoint, block):
        self.network_cause = "timeout" if timeout else "connection"
        place = " du catalogue" if endpoint == "catalog-sync" else " avec le relais"
        detail = f" (bloc {block + 1})" if block is not None else ""
        self.message = ("Délai réseau dépassé" if timeout else "Connexion interrompue") + place + detail + "."
        super().__init__(self.message)

    def __str__(self):
        return self.message


class RelayHTTPError(ValueError):
    def __init__(self, error, route):
        self.http_status = error.code
        self.http_endpoint = route.split("/")[0]
        server = error.headers.get("Server", "").lower()
        self.http_server = next((name for name in ("openresty", "nginx", "cloudflare", "envoy", "squid")
                                 if name in server), "unknown")
        content_type = error.headers.get("Content-Type", "")
        self.http_origin = "html" if "text/html" in content_type else "unknown"
        messages = {
            "Identité d’espace incompatible. Reconnectez cette base depuis les réglages.": "Le relais ou sa base a changé. Les données de cet espace sont conservées ; reconnectez le bon espace dans les réglages.",
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
        super().__init__(f"HTTP {error.code} sur /v1/{self.http_endpoint} — {message} (serveur : {self.http_server})")


class Relay:
    def __init__(self, url, token, *, use_system_proxy=False):
        self.url = url.rstrip("/")
        parts = urlsplit(self.url)
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or not (
            parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"})
        ):
            raise ValueError("Indiquez une URL HTTPS pour le relais.")
        if not token:
            raise ValueError("La clé PC du relais est manquante.")
        self.token = token
        self.catalog_gzip = False
        self.instance_id = ""
        self.workspace_id = ""
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=certifi.where())
        self.use_system_proxy = use_system_proxy
        self.opener = build_opener(
            ProxyHandler() if use_system_proxy else ProxyHandler({}),
            NoRedirect(), HTTPSHandler(context=context),
        )

    def connect_workspace(self, workspace_id, *, adopt_existing=False):
        return connect_workspace(self, workspace_id, adopt_existing=adopt_existing)

    def call(self, route, body=None):
        data = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        endpoint, *tail = route.split("/")
        block = int(tail[1]) if endpoint == "catalog-sync" and len(tail) == 2 and tail[1].isdigit() else None
        size = len(data or b"")
        compressed = data is not None and endpoint == "catalog-sync" and self.catalog_gzip and size >= 1024
        if compressed:
            data = gzip.compress(data, compresslevel=5, mtime=0)
        logger = logging.getLogger(__name__)
        logger.info(
            "relais_requete methode=%s route=%s transport=%s bloc=%s octets=%s bruts=%s gzip=%s",
            "GET" if data is None else "PUT", endpoint,
            "proxy-systeme" if self.use_system_proxy else "direct",
            block + 1 if block is not None else "-", len(data or b""), size, compressed,
        )
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                   "X-Horizon-Mobile-Protocol": "3"}
        if self.workspace_id:
            headers["X-Horizon-Workspace"] = self.workspace_id
            headers["X-Horizon-Instance"] = self.instance_id
        if compressed:
            headers["Content-Encoding"] = "gzip"
        req = Request(f"{self.url}/v1/{route}", data=data, method="GET" if data is None else "PUT",
                      headers=headers)
        started = time.monotonic()
        try:
            # La publication initiale est un transfert volumineux, distinct du suivi courant.
            with self.opener.open(req, timeout=90 if endpoint == "catalog-sync" and data is not None else 30) as result:
                raw = result.read(17 * 1024 * 1024 + 1)
                if len(raw) > 17 * 1024 * 1024:
                    raise ValueError("Réponse du relais trop volumineuse.")
        except HTTPError as exc:
            logger.warning("relais_refus route=%s bloc=%s http=%s", endpoint,
                           block + 1 if block is not None else "-", exc.code)
            raise RelayHTTPError(exc, route) from exc
        except (URLError, OSError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise ValueError(
                    "Le certificat HTTPS du relais ne peut pas être validé. "
                    "Vérifiez que le domaine correspond au certificat et que "
                    "Nginx Proxy Manager présente la chaîne de certificats complète. "
                    f"Détail TLS : {reason.verify_message}"
                ) from exc
            timed_out = isinstance(reason, TimeoutError)
            logger.warning("relais_interruption route=%s bloc=%s cause=%s octets=%s duree_ms=%s",
                           endpoint, block + 1 if block is not None else "-", "timeout" if timed_out else "connection",
                           len(data or b""), round((time.monotonic() - started) * 1000))
            raise RelayNetworkError(timeout=timed_out, endpoint=endpoint, block=block) from exc
        logger.info("relais_reponse route=%s bloc=%s duree_ms=%s", endpoint,
                    block + 1 if block is not None else "-", round((time.monotonic() - started) * 1000))
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
    with mobile_actor(db, receipt), op.resource("commande", uid):
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
            pages = receipt.get("pages", [])
            if not pages:
                if receipt.get("without_document") is not True:
                    raise ReceiptConflict("Confirmez la réception sans bon de livraison.")
                try:
                    db.add_receipt(order["id"], date.fromisoformat(receipt["date"]), receipt["quantities"],
                                   reference=receipt.get("reference", ""), receipt_uid=key,
                                   notes="Saisie depuis Horizon Mobile — bon de livraison non fourni")
                except ValueError as exc:
                    # Un refus métier ne doit pas bloquer les réceptions suivantes.
                    # Les erreurs de stockage restent récupérables au prochain cycle.
                    raise ReceiptConflict(str(exc)) from exc
                return
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
        if receipt.get("pages") and not any(d["display_name"] == name and resolve_portable_path(d["stored_path"]).is_file() for d in docs):
            raise RuntimeError("Bon de livraison introuvable sur le poste. Archivage à vérifier.")
    # La sortie du verrou a publié la commande et le PDF sur le partage.


def publish_orders(op, relay):
    db = op.database
    state = relay.call("mobile-state")
    versions = state["orders"]
    documents = set(state["documents"])
    with db.connect() as c:
        orders = list(c.execute("SELECT id, shared_uid, shared_revision FROM orders WHERE sync_state='Synchronisée'"))
    for row in orders:
        uid = row["shared_uid"]
        if not uid or versions.get(uid, [-1, 0]) >= [row["shared_revision"], 3]:
            continue
        summary = db.receipt_summary(row["id"])
        order = summary["order"]
        snapshot = None
        if not order["deleted_at"]:
            lines = [{"id": line["line_uid"], "label": line["designation"], "reference": line["supplier_ref"],
                      "code": line["code_cahpp"], "cartons": line["cartons"], "pack": line["units_per_carton"],
                      "units": line["total_units"], "price": line["unit_price"], "vat": line["vat"],
                      "received": line["received_units"], "remaining": line["remaining_units"]}
                     for line in summary["lines"]]
            receivable = bool(order["sent_at"] and not order["archived_at"] and any(line["remaining"] > 0 for line in lines))
            subject, mail_body = order_mail_content(db, row["id"])
            snapshot = {
                "format": 3, "id": uid, "revision": row["shared_revision"], "number": order["order_number"],
                "supplier": order["supplier_name"], "date": order["order_date"], "status": order["status"],
                "sent": bool(order["sent_at"]), "confirmed": bool(order["confirmed_at"]),
                "invoiced": bool(order["invoiced_at"]), "archived": bool(order["archived_at"]),
                "receivable": receivable, "total_ht": order["total_ht"], "total_ttc": order["total_ttc"],
                "delivery": order["delivery_status"], "notes": order["notes"], "lines": lines,
                "service": order["requester_service"], "created_by": order["created_by"], "updated_by": order["updated_by"],
                "receipts": [{"date": r["receipt_date"], "reference": r["reference"], "units": r["total_received"],
                              "received_by": r["received_by"]}
                             for r in summary["receipts"]],
                "subject": subject, "mail_body": mail_body, "documents": [],
            }
            full, _ = db.get_order(row["id"])
            snapshot["email"] = full["supplier_email"]
            with db.connect() as c:
                snapshot["comments"] = [dict(r) for r in c.execute(
                    "SELECT body,author_name,created_at FROM order_comments WHERE order_id=? ORDER BY id", (row["id"],))]
            files = ([{"display_name": Path(order["pdf_path"]).name, "stored_path": order["pdf_path"],
                       "kind": "Bon de commande", "main": True}] if order["pdf_path"] else [])
            files += [dict(r) | {"main": False} for r in db.list_order_attachments(row["id"])]
            for item in files:
                path = resolve_portable_path(item["stored_path"])
                mime = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(path.suffix.lower())
                if not mime or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
                    continue
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                if digest not in documents:
                    relay.call("documents/" + digest, {"name": item["display_name"], "mime": mime,
                                                      "data": base64.b64encode(data).decode()})
                    documents.add(digest)
                snapshot["documents"].append({"id": digest, "name": item["display_name"], "kind": item["kind"],
                                              "main": item["main"], "mime": mime})
        relay.call("orders/" + uid, {"revision": row["shared_revision"], "order": snapshot})


def synchronize(op, relay):
    if not op.manager:
        raise ValueError("Activez le dossier partagé sur ce profil avant la synchronisation mobile.")
    archived = rejected = deferred = 0
    with op.write():
        if op.editing_order is not None:
            raise ValueError("Fermez la commande en cours de modification avant la synchronisation mobile.")
        relay.connect_workspace(op.manager.workspace_id)
        op.last_mobile_maintenance = relay.call("maintenance", {})
        op.manager.sync_team_state()
        op.manager.sync_orders()
        for item in relay.call("pending-actions"):
            key = str(UUID(item))
            route = "actions/" + key
            result = relay.call(route)
            if result["state"] != "pending":
                continue
            try:
                value = apply_action(op, key, result["action"])
            except (ResourceLockedError, SyncConflictError):
                deferred += 1
                continue
            except ValueError as exc:
                relay.call(route + "/result", {"state": "rejected", "reason": str(exc)[:500]})
                rejected += 1
            else:
                relay.call(route + "/result", {"state": "archived", "result": value})
                archived += 1
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
    try:
        catalog_status = publish_catalog(op.database, relay)
    except CatalogTransferPaused as exc:
        # Les opérations métier ont déjà été traitées. Le catalogue reprendra au prochain cycle.
        catalog_status = str(exc)
    return (f"{archived} opération(s) archivée(s), {rejected} à corriger, "
            f"{deferred} en attente de déverrouillage ou de résolution de conflit. " + catalog_status)
