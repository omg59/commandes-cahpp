"""Clé d’appareil générée sur le PC, empreinte seule conservée au relais."""

import secrets
import json
import time
from urllib.parse import urlsplit
from uuid import uuid4


def enroll_device(relay, name, device_label, *, device_id=None, token=None):
    key = device_id or str(uuid4())
    secret = token or secrets.token_urlsafe(36)
    result = relay.call("devices/" + key, {"name": name, "label": device_label, "token": secret})
    return result | {"token": secret}


def pairing_invitation(relay, pc_user_id, name, label):
    if urlsplit(relay.url).scheme != "https" or not relay.url.isascii() or len(relay.url) > 512:
        raise ValueError("Indiquez une adresse HTTPS valide pour associer le téléphone.")
    deadline = time.monotonic() + 300
    result = relay.call("pairing", {"pc_user_id": pc_user_id, "name": name, "label": label})
    payload = json.dumps({
        "horizon_pairing": 1,
        "url": relay.url,
        "instance_id": relay.instance_id,
        "workspace_id": relay.workspace_id,
        "device_id": result["device_id"],
        "name": result["name"],
        "code": result["code"],
    }, separators=(",", ":"))
    return result["device_id"], result["name"], deadline, payload

